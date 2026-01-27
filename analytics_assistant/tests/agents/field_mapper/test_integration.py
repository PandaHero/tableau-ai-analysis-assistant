# -*- coding: utf-8 -*-
"""
FieldMapper Agent 集成测试

使用真实 Tableau 环境和真实大模型测试：
- FieldMapperNode 核心映射逻辑
- RAG 检索 + LLM 回退
- 缓存功能
- 批量映射

运行方式：
    python -m pytest analytics_assistant/tests/agents/field_mapper/test_integration.py -v -s

测试数据源：正大益生业绩总览数据 (IMPALA)
"""

import asyncio
import logging
import warnings
import time
from typing import List, Dict, Any

import pytest

# 忽略 SSL 警告
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 测试用数据源名称
TEST_DATASOURCE_NAME = "正大益生业绩总览数据 (IMPALA)"


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def reset_config():
    """重置配置单例"""
    from analytics_assistant.src.infra.config.config_loader import AppConfig
    AppConfig._instance = None
    yield
    AppConfig._instance = None


@pytest.fixture(scope="module")
def datasource_luid(reset_config):
    """获取测试用的数据源 LUID"""
    from analytics_assistant.src.platform.tableau.auth import get_tableau_auth
    from analytics_assistant.src.platform.tableau.client import VizQLClient

    auth = get_tableau_auth()
    
    async def get_luid():
        async with VizQLClient() as client:
            luid = await client.get_datasource_luid_by_name(
                datasource_name=TEST_DATASOURCE_NAME,
                api_key=auth.api_key,
            )
            return luid
    
    luid = asyncio.run(get_luid())
    if not luid:
        pytest.skip(f"未找到数据源: {TEST_DATASOURCE_NAME}")
    
    logger.info(f"测试数据源: {TEST_DATASOURCE_NAME} -> {luid}")
    return luid


@pytest.fixture(scope="module")
def data_model(reset_config, datasource_luid):
    """加载数据模型"""
    from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
    
    async def load():
        async with TableauDataLoader() as loader:
            return await loader.load_data_model(datasource_id=datasource_luid)
    
    model = asyncio.run(load())
    logger.info(f"数据模型加载完成: {len(model.fields)} 个字段")
    return model


@pytest.fixture
def field_mapper(data_model, datasource_luid):
    """创建 FieldMapper 实例"""
    from analytics_assistant.src.agents.field_mapper import FieldMapperNode, FieldMappingConfig
    
    config = FieldMappingConfig(
        high_confidence_threshold=0.9,
        low_confidence_threshold=0.7,
        max_concurrency=5,
        cache_ttl=3600,  # 1 小时
        top_k_candidates=10,
        enable_cache=True,
        enable_llm_fallback=True,
    )
    
    mapper = FieldMapperNode(config=config)
    mapper.load_metadata(
        fields=data_model.fields,
        datasource_luid=datasource_luid,
    )
    
    logger.info(f"FieldMapper 初始化完成: {mapper.field_count} 字段, RAG={mapper.rag_available}")
    return mapper


# ═══════════════════════════════════════════════════════════════════════════
# FieldMapperNode 基础测试
# ═══════════════════════════════════════════════════════════════════════════

class TestFieldMapperBasic:
    """FieldMapper 基础功能测试"""
    
    def test_mapper_initialization(self, field_mapper, data_model):
        """测试 FieldMapper 初始化"""
        assert field_mapper is not None
        assert field_mapper.field_count == len(data_model.fields)
        assert field_mapper.rag_available is True
        
        logger.info(f"FieldMapper 初始化测试通过: {field_mapper.field_count} 字段")
    
    def test_config_from_yaml(self, reset_config):
        """测试从 YAML 加载配置"""
        from analytics_assistant.src.agents.field_mapper import FieldMappingConfig
        
        config = FieldMappingConfig.from_yaml()
        
        assert config.high_confidence_threshold == 0.9
        assert config.low_confidence_threshold == 0.7
        assert config.max_concurrency == 5
        assert config.enable_cache is True
        assert config.enable_llm_fallback is True
        
        logger.info(f"配置加载测试通过: threshold={config.high_confidence_threshold}")


# ═══════════════════════════════════════════════════════════════════════════
# 单字段映射测试（真实 RAG + LLM）
# ═══════════════════════════════════════════════════════════════════════════

class TestSingleFieldMapping:
    """单字段映射测试 - 使用真实 RAG 和 LLM"""
    
    @pytest.mark.asyncio
    async def test_exact_match_mapping(self, field_mapper, datasource_luid, data_model):
        """测试精确匹配映射（应该走快速路径）"""
        # 使用数据源中实际存在的字段名
        if not data_model.fields:
            pytest.skip("数据源没有字段")
        
        # 找一个有 caption 的字段
        test_field = next(
            (f for f in data_model.fields if f.caption and f.caption != f.name),
            data_model.fields[0]
        )
        
        result = await field_mapper.map_field(
            term=test_field.caption or test_field.name,
            datasource_luid=datasource_luid,
        )
        
        assert result is not None
        assert result.technical_field is not None
        assert result.confidence >= 0.9  # 精确匹配应该高置信度
        assert result.mapping_source in ("rag_direct", "cache_hit")
        
        logger.info(
            f"精确匹配测试通过: '{test_field.caption}' -> '{result.technical_field}' "
            f"(confidence={result.confidence:.2f}, source={result.mapping_source})"
        )

    @pytest.mark.asyncio
    async def test_semantic_mapping_dimension(self, field_mapper, datasource_luid):
        """测试语义映射 - 维度字段"""
        # 测试常见的业务术语
        test_cases = [
            ("省份", "dimension"),
            ("城市", "dimension"),
            ("产品", "dimension"),
            ("日期", "dimension"),
            ("年份", "dimension"),
            ("月份", "dimension"),
        ]
        
        for term, expected_role in test_cases:
            result = await field_mapper.map_field(
                term=term,
                datasource_luid=datasource_luid,
                role_filter="dimension",
            )
            
            if result.technical_field:
                logger.info(
                    f"维度映射: '{term}' -> '{result.technical_field}' "
                    f"(confidence={result.confidence:.2f}, source={result.mapping_source})"
                )
            else:
                logger.warning(f"维度映射失败: '{term}' -> None")
    
    @pytest.mark.asyncio
    async def test_semantic_mapping_measure(self, field_mapper, datasource_luid):
        """测试语义映射 - 度量字段"""
        test_cases = [
            ("销售额", "measure"),
            ("数量", "measure"),
            ("金额", "measure"),
            ("利润", "measure"),
            ("成本", "measure"),
        ]
        
        for term, expected_role in test_cases:
            result = await field_mapper.map_field(
                term=term,
                datasource_luid=datasource_luid,
                role_filter="measure",
            )
            
            if result.technical_field:
                logger.info(
                    f"度量映射: '{term}' -> '{result.technical_field}' "
                    f"(confidence={result.confidence:.2f}, source={result.mapping_source})"
                )
            else:
                logger.warning(f"度量映射失败: '{term}' -> None")
    
    @pytest.mark.asyncio
    async def test_llm_fallback_mapping(self, field_mapper, datasource_luid):
        """测试 LLM 回退映射（模糊术语）"""
        # 使用模糊的业务术语，需要 LLM 理解
        fuzzy_terms = [
            "业绩",      # 可能映射到销售额、利润等
            "区域",      # 可能映射到省份、城市等
            "时间",      # 可能映射到日期、年份等
            "客户",      # 可能映射到客户名称、客户ID等
        ]
        
        for term in fuzzy_terms:
            result = await field_mapper.map_field(
                term=term,
                datasource_luid=datasource_luid,
                context="分析业绩数据",
            )
            
            logger.info(
                f"模糊映射: '{term}' -> '{result.technical_field}' "
                f"(confidence={result.confidence:.2f}, source={result.mapping_source}, "
                f"reasoning={result.reasoning[:50] if result.reasoning else 'N/A'}...)"
            )
    
    @pytest.mark.asyncio
    async def test_empty_term_handling(self, field_mapper, datasource_luid):
        """测试空术语处理"""
        result = await field_mapper.map_field(
            term="",
            datasource_luid=datasource_luid,
        )
        
        assert result.technical_field is None
        assert result.confidence == 0.0
        assert result.mapping_source == "error"
        
        logger.info("空术语处理测试通过")
    
    @pytest.mark.asyncio
    async def test_nonexistent_term_handling(self, field_mapper, datasource_luid):
        """测试不存在的术语处理"""
        result = await field_mapper.map_field(
            term="这是一个完全不存在的字段名称xyz123",
            datasource_luid=datasource_luid,
        )
        
        # 应该返回低置信度或 None
        logger.info(
            f"不存在术语处理: confidence={result.confidence:.2f}, "
            f"field={result.technical_field}, source={result.mapping_source}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 缓存功能测试
# ═══════════════════════════════════════════════════════════════════════════

class TestCacheFunction:
    """缓存功能测试"""
    
    @pytest.mark.asyncio
    async def test_cache_hit(self, field_mapper, datasource_luid, data_model):
        """测试缓存命中"""
        if not data_model.fields:
            pytest.skip("数据源没有字段")
        
        test_field = data_model.fields[0]
        term = test_field.caption or test_field.name
        
        # 第一次调用（缓存未命中）
        result1 = await field_mapper.map_field(
            term=term,
            datasource_luid=datasource_luid,
        )
        source1 = result1.mapping_source
        
        # 第二次调用（应该缓存命中）
        result2 = await field_mapper.map_field(
            term=term,
            datasource_luid=datasource_luid,
        )
        
        # 验证结果一致
        assert result1.technical_field == result2.technical_field
        assert result2.mapping_source == "cache_hit"
        
        logger.info(
            f"缓存测试通过: '{term}' "
            f"第一次={source1}, 第二次={result2.mapping_source}"
        )
    
    @pytest.mark.asyncio
    async def test_cache_stats(self, field_mapper, datasource_luid, data_model):
        """测试缓存统计"""
        if not data_model.fields:
            pytest.skip("数据源没有字段")
        
        # 执行几次映射
        for field in data_model.fields[:5]:
            term = field.caption or field.name
            await field_mapper.map_field(term=term, datasource_luid=datasource_luid)
            # 再次调用触发缓存命中
            await field_mapper.map_field(term=term, datasource_luid=datasource_luid)
        
        stats = field_mapper.get_stats()
        
        assert stats["total_mappings"] > 0
        assert stats["cache_hits"] > 0
        assert stats["cache_hit_rate"] > 0
        
        logger.info(
            f"缓存统计: total={stats['total_mappings']}, "
            f"cache_hits={stats['cache_hits']}, "
            f"hit_rate={stats['cache_hit_rate']:.2%}, "
            f"fast_path={stats['fast_path_hits']}, "
            f"llm_fallback={stats['llm_fallback_count']}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 批量映射测试
# ═══════════════════════════════════════════════════════════════════════════

class TestBatchMapping:
    """批量映射测试"""
    
    @pytest.mark.asyncio
    async def test_batch_mapping(self, field_mapper, datasource_luid):
        """测试批量映射"""
        terms = ["销售额", "省份", "日期", "产品", "数量"]
        
        start_time = time.time()
        results = await field_mapper.map_fields_batch(
            terms=terms,
            datasource_luid=datasource_luid,
            context="分析销售数据",
        )
        elapsed = time.time() - start_time
        
        assert len(results) == len(terms)
        
        for term, result in results.items():
            logger.info(
                f"批量映射: '{term}' -> '{result.technical_field}' "
                f"(confidence={result.confidence:.2f}, source={result.mapping_source})"
            )
        
        logger.info(f"批量映射完成: {len(terms)} 个术语, 耗时 {elapsed:.2f}s")
    
    @pytest.mark.asyncio
    async def test_batch_mapping_with_role_filters(self, field_mapper, datasource_luid):
        """测试带角色过滤的批量映射"""
        terms = ["销售额", "省份", "日期"]
        role_filters = {
            "销售额": "measure",
            "省份": "dimension",
            "日期": "dimension",
        }
        
        results = await field_mapper.map_fields_batch(
            terms=terms,
            datasource_luid=datasource_luid,
            role_filters=role_filters,
        )
        
        assert len(results) == len(terms)
        
        for term, result in results.items():
            logger.info(
                f"角色过滤映射: '{term}' (filter={role_filters[term]}) -> "
                f"'{result.technical_field}' (confidence={result.confidence:.2f})"
            )
    
    @pytest.mark.asyncio
    async def test_batch_mapping_concurrency(self, field_mapper, datasource_luid, data_model):
        """测试批量映射并发性能"""
        if len(data_model.fields) < 10:
            pytest.skip("字段数量不足")
        
        # 使用前 20 个字段的 caption
        terms = [
            f.caption or f.name 
            for f in data_model.fields[:20]
        ]
        
        start_time = time.time()
        results = await field_mapper.map_fields_batch(
            terms=terms,
            datasource_luid=datasource_luid,
        )
        elapsed = time.time() - start_time
        
        assert len(results) == len(terms)
        
        # 统计各种来源
        sources = {}
        for result in results.values():
            sources[result.mapping_source] = sources.get(result.mapping_source, 0) + 1
        
        logger.info(
            f"并发映射完成: {len(terms)} 个术语, 耗时 {elapsed:.2f}s, "
            f"来源分布: {sources}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# StateGraph 节点函数测试
# ═══════════════════════════════════════════════════════════════════════════

class TestFieldMapperNode:
    """field_mapper_node 节点函数测试"""
    
    @pytest.mark.asyncio
    async def test_node_function_basic(self, data_model, datasource_luid):
        """测试节点函数基本功能"""
        from analytics_assistant.src.agents.field_mapper import field_mapper_node
        from analytics_assistant.src.core.schemas import (
            SemanticQuery,
            MeasureField,
            DimensionField,
            AggregationType,
        )
        
        # 构建 SemanticQuery
        semantic_query = SemanticQuery(
            measures=[
                MeasureField(field_name="销售额", aggregation=AggregationType.SUM),
            ],
            dimensions=[
                DimensionField(field_name="省份"),
            ],
        )
        
        # 构建 state
        state = {
            "semantic_query": semantic_query,
            "datasource": datasource_luid,
            "question": "按省份统计销售额",
            "data_model": data_model,
        }
        
        # 调用节点函数
        result = await field_mapper_node(state)
        
        assert result is not None
        assert result.get("field_mapper_complete") is True
        assert result.get("mapped_query") is not None
        
        mapped_query = result["mapped_query"]
        assert len(mapped_query.field_mappings) > 0
        
        logger.info(
            f"节点函数测试通过: {len(mapped_query.field_mappings)} 个映射, "
            f"overall_confidence={mapped_query.overall_confidence:.2f}"
        )
        
        for term, mapping in mapped_query.field_mappings.items():
            logger.info(
                f"  {term} -> {mapping.technical_field} "
                f"(confidence={mapping.confidence:.2f})"
            )
    
    @pytest.mark.asyncio
    async def test_node_function_no_semantic_query(self):
        """测试节点函数 - 无 semantic_query"""
        from analytics_assistant.src.agents.field_mapper import field_mapper_node
        
        state = {
            "datasource": "test-luid",
            "question": "测试问题",
        }
        
        result = await field_mapper_node(state)
        
        assert result is not None
        assert result.get("field_mapper_complete") is True
        assert result.get("mapped_query") is None
        assert "errors" in result
        
        logger.info("无 semantic_query 测试通过")
    
    @pytest.mark.asyncio
    async def test_node_function_empty_terms(self, data_model, datasource_luid):
        """测试节点函数 - 空术语"""
        from analytics_assistant.src.agents.field_mapper import field_mapper_node
        from analytics_assistant.src.core.schemas import SemanticQuery
        
        # 构建空的 SemanticQuery
        semantic_query = SemanticQuery(
            measures=[],
            dimensions=[],
        )
        
        state = {
            "semantic_query": semantic_query,
            "datasource": datasource_luid,
            "data_model": data_model,
        }
        
        result = await field_mapper_node(state)
        
        assert result is not None
        assert result.get("field_mapper_complete") is True
        assert result.get("mapped_query") is not None
        assert result["mapped_query"].overall_confidence == 1.0
        
        logger.info("空术语测试通过")


# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数测试
# ═══════════════════════════════════════════════════════════════════════════

class TestHelperFunctions:
    """辅助函数测试"""
    
    def test_extract_terms_from_semantic_query(self):
        """测试从 SemanticQuery 提取术语"""
        from analytics_assistant.src.agents.field_mapper.node import _extract_terms_from_semantic_query
        from analytics_assistant.src.core.schemas import (
            SemanticQuery,
            MeasureField,
            DimensionField,
            DateRangeFilter,
            AggregationType,
        )
        
        semantic_query = SemanticQuery(
            measures=[
                MeasureField(field_name="销售额", aggregation=AggregationType.SUM),
                MeasureField(field_name="数量", aggregation=AggregationType.COUNT),
            ],
            dimensions=[
                DimensionField(field_name="省份"),
                DimensionField(field_name="日期"),
            ],
            filters=[
                DateRangeFilter(field_name="日期", start_date="2024-01-01", end_date="2024-12-31"),
            ],
        )
        
        terms = _extract_terms_from_semantic_query(semantic_query)
        
        assert "销售额" in terms
        assert "数量" in terms
        assert "省份" in terms
        assert "日期" in terms
        
        # 所有值应该是 None（不限制角色）
        for term, role in terms.items():
            assert role is None
        
        logger.info(f"提取术语测试通过: {list(terms.keys())}")
    
    def test_format_candidates(self):
        """测试格式化候选字段"""
        from analytics_assistant.src.agents.field_mapper.prompt import format_candidates
        from analytics_assistant.src.agents.field_mapper.node import FieldCandidate
        
        candidates = [
            FieldCandidate(
                field_name="SUM(Sales)",
                field_caption="销售额",
                role="measure",
                data_type="REAL",
                score=0.95,
                category="金额",
                sample_values=["100.5", "200.3", "300.1"],
            ),
            FieldCandidate(
                field_name="Province",
                field_caption="省份",
                role="dimension",
                data_type="STRING",
                score=0.85,
                category="地理",
            ),
        ]
        
        formatted = format_candidates(candidates)
        
        assert "SUM(Sales)" in formatted
        assert "销售额" in formatted
        assert "Province" in formatted
        assert "省份" in formatted
        assert "0.95" in formatted
        
        logger.info(f"格式化候选测试通过:\n{formatted}")


# ═══════════════════════════════════════════════════════════════════════════
# 性能测试
# ═══════════════════════════════════════════════════════════════════════════

class TestPerformance:
    """性能测试"""
    
    @pytest.mark.asyncio
    async def test_mapping_latency(self, field_mapper, datasource_luid):
        """测试映射延迟"""
        terms = ["销售额", "省份", "日期"]
        latencies = []
        
        for term in terms:
            start = time.time()
            result = await field_mapper.map_field(
                term=term,
                datasource_luid=datasource_luid,
            )
            latency = (time.time() - start) * 1000
            latencies.append(latency)
            
            logger.info(
                f"映射延迟: '{term}' -> {result.latency_ms}ms (实际: {latency:.0f}ms), "
                f"source={result.mapping_source}"
            )
        
        avg_latency = sum(latencies) / len(latencies)
        logger.info(f"平均延迟: {avg_latency:.0f}ms")
    
    @pytest.mark.asyncio
    async def test_batch_vs_sequential(self, field_mapper, datasource_luid, data_model):
        """测试批量 vs 顺序映射性能"""
        if len(data_model.fields) < 10:
            pytest.skip("字段数量不足")
        
        terms = [f.caption or f.name for f in data_model.fields[:10]]
        
        # 顺序映射
        start = time.time()
        for term in terms:
            await field_mapper.map_field(term=term, datasource_luid=datasource_luid)
        sequential_time = time.time() - start
        
        # 清除缓存统计（但保留缓存数据）
        field_mapper._total_mappings = 0
        field_mapper._cache_hits = 0
        
        # 批量映射（使用不同的术语避免缓存）
        new_terms = [f"{t}_test" for t in terms]
        start = time.time()
        await field_mapper.map_fields_batch(terms=new_terms, datasource_luid=datasource_luid)
        batch_time = time.time() - start
        
        logger.info(
            f"性能对比: 顺序={sequential_time:.2f}s, 批量={batch_time:.2f}s, "
            f"加速比={sequential_time/batch_time:.2f}x"
        )
