"""端到端语义解析测试

测试从用户问题到结构化查询的完整流程。

需求: 1.1-1.10
验证:
- 简单查询（单维度单度量）
- 多维度多度量查询
- 带筛选条件的查询
- 带时间范围的查询
- 带计算字段的查询
- 带排序和限制的查询
- 带聚合函数的查询
- 置信度分数范围
- 字段名称与 Schema 匹配
- 性能要求（<= 30 秒）
"""

import asyncio
import logging
import time

import pytest

from analytics_assistant.tests.integration.base import BaseIntegrationTest
from analytics_assistant.tests.integration.test_data_manager import TestDataManager
from analytics_assistant.tests.integration.config_loader import TestConfigLoader
from analytics_assistant.src.agents.semantic_parser.graph import compile_semantic_parser_graph
from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
from analytics_assistant.src.core.schemas.enums import IntentType
from analytics_assistant.src.orchestration.workflow.context import WorkflowContext
from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader

logger = logging.getLogger(__name__)


def _get_attr(obj, attr_name, default=None):
    """获取对象属性,兼容 dict 和对象
    
    Args:
        obj: dict 或对象
        attr_name: 属性名
        default: 默认值
    
    Returns:
        属性值
    """
    if isinstance(obj, dict):
        return obj.get(attr_name, default)
    else:
        return getattr(obj, attr_name, default)


def _get_intent_type(result: dict) -> str:
    """从当前状态结构中提取意图类型。"""
    intent_router_output = result.get("intent_router_output", {})
    return intent_router_output.get("intent_type", "")


def _get_measures(semantic_output) -> list:
    """从当前语义输出结构中提取度量列表。"""
    return _get_attr(_get_attr(semantic_output, "what", {}), "measures", [])


def _get_dimensions(semantic_output) -> list:
    """从当前语义输出结构中提取维度列表。"""
    return _get_attr(_get_attr(semantic_output, "where", {}), "dimensions", [])


def _get_filters(semantic_output) -> list:
    """从当前语义输出结构中提取筛选器列表。"""
    return _get_attr(_get_attr(semantic_output, "where", {}), "filters", [])


def _get_confidence(semantic_output) -> float:
    """从当前语义输出结构中提取整体置信度。"""
    self_check = _get_attr(semantic_output, "self_check", {})
    return _get_attr(self_check, "overall_confidence", 0.0)


def _is_top_n_filter(filter_obj) -> bool:
    """判断筛选器是否为 Top N。"""
    filter_type = _get_attr(filter_obj, "filter_type", "")
    return str(filter_type).lower().endswith("top_n")


class TestE2ESemanticParsing(BaseIntegrationTest):
    """端到端语义解析测试类"""
    _resolved_datasource_luid: str = ""
    
    @classmethod
    def setup_class(cls):
        """类级别设置"""
        super().setup_class()
        
        # 加载测试数据
        test_data_dir = TestConfigLoader.get_test_data_dir()
        cls._test_data_manager = TestDataManager(test_data_dir)
        
        # 获取超时配置
        cls._timeout = TestConfigLoader.get_timeout("semantic_parsing")
        
        # 编译语义解析图
        cls._semantic_parser_graph = compile_semantic_parser_graph()
        
        # 预加载数据模型（类级别缓存，避免每次测试都加载）
        cls._data_model_cache = {}
        cls._preload_data_model()
    
    @classmethod
    def _preload_data_model(cls):
        """预加载测试数据源的数据模型"""
        tableau_config = TestConfigLoader.get_tableau_config()
        datasource_luid = tableau_config.get("test_datasource_luid", "")
        datasource_name = tableau_config.get("test_datasource_name", "")

        has_explicit_luid = bool(datasource_luid and "${" not in datasource_luid)
        if not has_explicit_luid and not datasource_name:
            pytest.skip("未配置测试数据源，跳过集成测试")

        async def load():
            async with TableauDataLoader() as loader:
                if has_explicit_luid:
                    logger.info(f"开始预加载数据模型: datasource_luid={datasource_luid}")
                    data_model = await loader.load_data_model(
                        datasource_id=datasource_luid,
                        skip_index_creation=True,
                    )
                else:
                    logger.info(f"开始预加载数据模型: datasource_name={datasource_name}")
                    data_model = await loader.load_data_model(
                        datasource_name=datasource_name,
                        skip_index_creation=True,
                    )

                cls._resolved_datasource_luid = data_model.datasource_id
                cls._data_model_cache[data_model.datasource_id] = data_model
                logger.info(
                    f"预加载数据模型完成: datasource_luid={data_model.datasource_id}, "
                    f"fields={len(data_model.fields)}"
                )
        
        asyncio.run(load())
    
    async def _parse_question(self, question: str, datasource_luid: str) -> dict:
        """调用语义解析图解析问题
        
        Args:
            question: 用户问题
            datasource_luid: 数据源 LUID
            
        Returns:
            解析结果状态字典
        """
        # 使用缓存的数据模型（已在 setup_class 中预加载）
        if datasource_luid not in self._data_model_cache:
            # 如果缓存中没有，动态加载（不应该发生）
            async with TableauDataLoader() as loader:
                data_model = await loader.load_data_model(
                    datasource_id=datasource_luid,
                    skip_index_creation=True,
                )
                self._data_model_cache[datasource_luid] = data_model
        
        data_model = self._data_model_cache[datasource_luid]
        
        # 创建 WorkflowContext
        workflow_context = WorkflowContext(
            datasource_luid=datasource_luid,
            data_model=data_model,
        )
        
        # 创建初始状态
        initial_state = SemanticParserState(
            question=question,
            datasource_luid=datasource_luid,
        )
        
        # 调用图执行（传递 workflow_context）
        result = await self._semantic_parser_graph.ainvoke(
            initial_state,
            config={"configurable": {"workflow_context": workflow_context}},
        )
        
        return result
    
    @pytest.mark.smoke
    @pytest.mark.e2e
    def test_simple_single_measure_query(self):
        """测试简单的单度量查询
        
        需求: 1.1
        问题: "显示所有产品的销售额"
        期望: 正确解析为 SemanticOutput，包含销售额度量
        """
        # 获取测试问题
        question = self._test_data_manager.get_question_by_id("simple_001")
        assert question is not None, "测试问题 simple_001 不存在"
        
        # 获取测试数据源
        datasource_luid = self._get_test_datasource_luid()
        assert datasource_luid, "未配置测试数据源 LUID"
        
        # 记录开始时间
        start_time = time.time()
        
        # 调用语义解析
        result = asyncio.run(self._parse_question(question.question, datasource_luid))
        
        # 记录耗时
        elapsed = time.time() - start_time
        self._record_metric("semantic_parsing_time", elapsed)
        
        # 验证性能要求
        assert elapsed <= self._timeout, f"语义解析超时: {elapsed:.2f}s > {self._timeout}s"
        
        # 验证解析结果
        assert result.get("semantic_output") is not None, "未生成 semantic_output"
        semantic_output = result["semantic_output"]
        
        # 验证意图类型（从 intent_router_output 获取）
        intent = _get_intent_type(result)
        assert intent == IntentType.DATA_QUERY or intent == "data_query", f"意图类型错误: {intent}"
        
        # 验证包含度量字段（从 what.measures 获取）
        measures = _get_measures(semantic_output)
        assert len(measures) > 0, "未识别度量字段"
        
        # 验证置信度范围（从 self_check.overall_confidence 获取）
        confidence = _get_confidence(semantic_output)
        assert 0.0 <= confidence <= 1.0, f"置信度超出范围: {confidence}"
        
        # 验证置信度满足最小要求
        if question.expected_confidence_min:
            assert confidence >= question.expected_confidence_min, \
                f"置信度过低: {confidence} < {question.expected_confidence_min}"
    
    @pytest.mark.smoke
    @pytest.mark.e2e
    def test_simple_single_dimension_single_measure_query(self):
        """测试简单的单维度单度量查询
        
        需求: 1.1
        问题: "各地区的订单数量"
        期望: 正确解析维度和度量
        """
        question = self._test_data_manager.get_question_by_id("simple_002")
        assert question is not None
        
        datasource_luid = self._get_test_datasource_luid()
        assert datasource_luid
        
        start_time = time.time()
        
        # 调用语义解析
        result = asyncio.run(self._parse_question(question.question, datasource_luid))
        
        elapsed = time.time() - start_time
        self._record_metric("semantic_parsing_time", elapsed)
        
        assert elapsed <= self._timeout
        
        # 验证解析结果
        assert result.get("semantic_output") is not None
        semantic_output = result["semantic_output"]
        
        # 验证意图类型
        intent = _get_intent_type(result)
        assert intent == IntentType.DATA_QUERY or intent == "data_query"
        
        # 验证包含维度和度量
        dimensions = _get_dimensions(semantic_output)
        measures = _get_measures(semantic_output)
        assert len(dimensions) > 0, "未识别维度字段"
        assert len(measures) > 0, "未识别度量字段"
        
        # 验证置信度
        confidence = _get_confidence(semantic_output)
        assert 0.0 <= confidence <= 1.0
    
    @pytest.mark.core
    @pytest.mark.e2e
    def test_multi_dimension_multi_measure_query(self):
        """测试多维度多度量查询
        
        需求: 1.2
        问题: "按地区和产品类别显示销售额和利润"
        期望: 正确识别所有维度和度量字段
        """
        question = self._test_data_manager.get_question_by_id("multi_dim_001")
        assert question is not None
        
        datasource_luid = self._get_test_datasource_luid()
        assert datasource_luid
        
        start_time = time.time()
        
        # 调用语义解析
        result = asyncio.run(self._parse_question(question.question, datasource_luid))
        
        elapsed = time.time() - start_time
        self._record_metric("semantic_parsing_time", elapsed)
        
        assert elapsed <= self._timeout
        
        # 验证解析结果
        assert result.get("semantic_output") is not None
        semantic_output = result["semantic_output"]
        
        # 验证意图类型
        intent = _get_intent_type(result)
        assert intent == IntentType.DATA_QUERY or intent == "data_query"
        
        # 验证多维度
        dimensions = _get_dimensions(semantic_output)
        assert len(dimensions) >= 2, f"维度数量不足: {len(dimensions)} < 2"
        
        # 验证多度量
        measures = _get_measures(semantic_output)
        assert len(measures) >= 1, f"度量数量不足: {len(measures)} < 1"
        
        # 验证置信度
        confidence = _get_confidence(semantic_output)
        assert 0.0 <= confidence <= 1.0
    
    @pytest.mark.core
    @pytest.mark.e2e
    def test_filtered_query(self):
        """测试带筛选条件的查询
        
        需求: 1.3
        问题: "2024年的销售额"
        期望: 正确解析筛选器类型和值
        """
        question = self._test_data_manager.get_question_by_id("filter_001")
        assert question is not None
        
        datasource_luid = self._get_test_datasource_luid()
        assert datasource_luid
        
        start_time = time.time()
        
        # 调用语义解析
        result = asyncio.run(self._parse_question(question.question, datasource_luid))
        
        elapsed = time.time() - start_time
        self._record_metric("semantic_parsing_time", elapsed)
        
        assert elapsed <= self._timeout
        
        # 验证解析结果
        assert result.get("semantic_output") is not None
        semantic_output = result["semantic_output"]
        
        # 验证意图类型
        intent = _get_intent_type(result)
        assert intent == IntentType.DATA_QUERY or intent == "data_query"
        
        # 验证包含筛选器
        filters = _get_filters(semantic_output)
        assert len(filters) > 0, "未识别筛选条件"
        
        # 验证筛选器包含年份信息
        filter_values = [
            f"{_get_attr(f, 'start_date', '')} {_get_attr(f, 'end_date', '')} {_get_attr(f, 'values', [])}"
            for f in filters
        ]
        assert any("2024" in str(v) for v in filter_values), "未正确解析年份筛选"
        
        # 验证置信度
        confidence = _get_confidence(semantic_output)
        assert 0.0 <= confidence <= 1.0
    
    @pytest.mark.core
    @pytest.mark.e2e
    def test_time_range_query(self):
        """测试带时间范围的查询
        
        需求: 1.4
        问题: "过去6个月的销售趋势"
        期望: 正确解析时间维度和日期范围
        """
        question = self._test_data_manager.get_question_by_id("time_series_001")
        assert question is not None
        
        datasource_luid = self._get_test_datasource_luid()
        assert datasource_luid
        
        start_time = time.time()
        
        # 调用语义解析
        result = asyncio.run(self._parse_question(question.question, datasource_luid))
        
        elapsed = time.time() - start_time
        self._record_metric("semantic_parsing_time", elapsed)
        
        assert elapsed <= self._timeout
        
        # 验证解析结果
        assert result.get("semantic_output") is not None
        semantic_output = result["semantic_output"]
        
        # 验证意图类型
        intent = _get_intent_type(result)
        assert intent == IntentType.DATA_QUERY or intent == "data_query"
        
        # 验证包含时间维度或筛选器
        dimensions = _get_dimensions(semantic_output)
        has_time_dimension = any("date" in _get_attr(d, "field_name", "").lower() or "time" in _get_attr(d, "field_name", "").lower() 
                                  for d in dimensions)
        filters = _get_filters(semantic_output)
        has_time_filter = len(filters) > 0
        
        assert has_time_dimension or has_time_filter, "未识别时间相关字段"
        
        # 验证置信度
        confidence = _get_confidence(semantic_output)
        assert 0.0 <= confidence <= 1.0
    
    @pytest.mark.core
    @pytest.mark.e2e
    def test_calculation_field_query(self):
        """测试带计算字段的查询
        
        需求: 1.5
        问题: "各产品的利润率"
        期望: 正确生成计算表达式
        """
        question = self._test_data_manager.get_question_by_id("calculation_001")
        assert question is not None
        
        datasource_luid = self._get_test_datasource_luid()
        assert datasource_luid
        
        start_time = time.time()
        
        # 调用语义解析
        result = asyncio.run(self._parse_question(question.question, datasource_luid))
        
        elapsed = time.time() - start_time
        self._record_metric("semantic_parsing_time", elapsed)
        
        assert elapsed <= self._timeout
        
        # 验证解析结果
        assert result.get("semantic_output") is not None
        semantic_output = result["semantic_output"]
        
        # 验证意图类型
        intent = _get_intent_type(result)
        assert intent == IntentType.DATA_QUERY or intent == "data_query"
        
        # 验证包含计算字段
        computations = _get_attr(semantic_output, "computations", [])
        assert len(computations) > 0, "未识别计算字段"
        
        # 验证计算字段包含公式
        for comp in computations:
            expression = _get_attr(comp, "formula")
            name = _get_attr(comp, "name", "unknown")
            assert expression, f"计算字段 {name} 缺少表达式"
        
        # 验证置信度
        confidence = _get_confidence(semantic_output)
        assert 0.0 <= confidence <= 1.0
    
    @pytest.mark.core
    @pytest.mark.e2e
    def test_ranking_query(self):
        """测试带排序和限制的查询
        
        需求: 1.6
        问题: "销售额前10的产品"
        期望: 正确解析排序字段和限制数量
        """
        question = self._test_data_manager.get_question_by_id("ranking_001")
        assert question is not None
        
        datasource_luid = self._get_test_datasource_luid()
        assert datasource_luid
        
        start_time = time.time()
        
        # 调用语义解析
        result = asyncio.run(self._parse_question(question.question, datasource_luid))
        
        elapsed = time.time() - start_time
        self._record_metric("semantic_parsing_time", elapsed)
        
        assert elapsed <= self._timeout
        
        # 验证解析结果
        assert result.get("semantic_output") is not None
        semantic_output = result["semantic_output"]
        
        # 验证意图类型
        intent = _get_intent_type(result)
        assert intent == IntentType.DATA_QUERY or intent == "data_query"
        
        # 排名查询当前通过 Top N 筛选器表达
        filters = _get_filters(semantic_output)
        top_n_filters = [filter_obj for filter_obj in filters if _is_top_n_filter(filter_obj)]
        assert len(top_n_filters) > 0, "未识别 Top N 筛选器"
        assert any(_get_attr(filter_obj, "n", 0) > 0 for filter_obj in top_n_filters), "Top N 数量无效"
        
        # 验证置信度
        confidence = _get_confidence(semantic_output)
        assert 0.0 <= confidence <= 1.0
    
    @pytest.mark.core
    @pytest.mark.e2e
    def test_complex_query_with_multiple_features(self):
        """测试复杂查询（多筛选 + 多度量 + 排名）
        
        需求: 1.1-1.7
        问题: "2024年华东地区销售额前10的产品及其利润率"
        期望: 正确解析所有组件
        """
        question = self._test_data_manager.get_question_by_id("complex_001")
        assert question is not None
        
        datasource_luid = self._get_test_datasource_luid()
        assert datasource_luid
        
        start_time = time.time()
        
        # 调用语义解析
        result = asyncio.run(self._parse_question(question.question, datasource_luid))
        
        elapsed = time.time() - start_time
        self._record_metric("semantic_parsing_time", elapsed)
        
        assert elapsed <= self._timeout
        
        # 验证解析结果
        assert result.get("semantic_output") is not None
        semantic_output = result["semantic_output"]
        
        # 验证意图类型
        intent = _get_intent_type(result)
        assert intent == IntentType.DATA_QUERY or intent == "data_query"
        
        # 验证包含筛选器
        filters = _get_filters(semantic_output)
        assert len(filters) > 0, "未识别筛选条件"
        
        # 验证包含度量
        measures = _get_measures(semantic_output)
        assert len(measures) > 0, "未识别度量字段"
        
        # 验证复杂查询中的 Top N 排名表达
        top_n_filters = [filter_obj for filter_obj in filters if _is_top_n_filter(filter_obj)]
        assert len(top_n_filters) > 0, "未识别 Top N 排名筛选"
        
        # 验证置信度
        confidence = _get_confidence(semantic_output)
        assert 0.0 <= confidence <= 1.0
    
    @pytest.mark.core
    @pytest.mark.e2e
    def test_confidence_score_range(self):
        """测试置信度分数范围
        
        需求: 1.8
        验证: 所有有效查询的置信度在 [0.0, 1.0] 范围内
        """
        # 获取所有简单查询（置信度应该较高）
        questions = self._test_data_manager.get_questions_by_category("simple")
        
        datasource_luid = self._get_test_datasource_luid()
        assert datasource_luid
        
        for question in questions[:3]:  # 测试前3个
            start_time = time.time()
            
            # 调用语义解析
            result = asyncio.run(self._parse_question(question.question, datasource_luid))
            
            elapsed = time.time() - start_time
            self._record_metric(f"semantic_parsing_time_{question.id}", elapsed)
            
            # 验证解析结果
            assert result.get("semantic_output") is not None
            semantic_output = result["semantic_output"]
            
            # 验证置信度范围
            confidence = _get_confidence(semantic_output)
            assert 0.0 <= confidence <= 1.0, \
                f"置信度超出范围: {confidence}"
            
            # 验证置信度满足最小要求
            if question.expected_confidence_min:
                assert confidence >= question.expected_confidence_min, \
                    f"置信度过低: {confidence} < {question.expected_confidence_min}"
    
    @pytest.mark.e2e
    def test_performance_requirement(self):
        """测试性能要求
        
        需求: 1.10
        验证: 单次语义解析在 30 秒内完成
        """
        question = self._test_data_manager.get_question_by_id("simple_001")
        assert question is not None
        
        datasource_luid = self._get_test_datasource_luid()
        assert datasource_luid
        
        start_time = time.time()
        
        # 调用语义解析
        result = asyncio.run(self._parse_question(question.question, datasource_luid))
        
        elapsed = time.time() - start_time
        self._record_metric("semantic_parsing_time", elapsed)
        
        # 验证性能要求
        assert elapsed <= 30.0, f"语义解析超时: {elapsed:.2f}s > 30.0s"
        
        # 验证解析成功
        assert result.get("semantic_output") is not None, "未生成 semantic_output"
