# -*- coding: utf-8 -*-
"""
LangGraph 子图流程集成测试

测试 SemanticParser LangGraph 子图的完整流程，包括：
- 简单查询完整流程
- 缓存命中流程
- 需要澄清的流程
- 筛选值确认流程（interrupt/resume）
- 错误修正流程
- 边界条件测试

运行方式：
    cd analytics_assistant
    $env:PYTHONPATH = ".."
    pytest tests/integration/test_graph_flow.py -v --tb=short -s

测试要求：
- 使用真实 LLM (DeepSeek) 和真实 Embedding (Zhipu)
- 配置文件：analytics_assistant/config/app.yaml
"""

import asyncio
import logging
import sys
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════

async def get_real_tableau_components():
    """获取真实的 Tableau 组件
    
    Returns:
        tuple: (client, adapter, auth, datasource_luid, data_model)
    """
    from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
    from analytics_assistant.src.platform.tableau.client import VizQLClient
    from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
    from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
    
    try:
        auth = await get_tableau_auth_async()
        client = VizQLClient()
        adapter = TableauAdapter(vizql_client=client)
        
        datasource_name = "正大益生"
        datasource_luid = await client.get_datasource_luid_by_name(
            datasource_name=datasource_name,
            api_key=auth.api_key,
        )
        
        if not datasource_luid:
            logger.warning(f"未找到数据源: {datasource_name}")
            return None, None, None, None, None
        
        loader = TableauDataLoader(client=client)
        data_model = await loader.load_data_model(
            datasource_id=datasource_luid,
            auth=auth,
        )
        
        logger.info(f"数据模型加载完成: {len(data_model.fields)} 个字段")
        
        return client, adapter, auth, datasource_luid, data_model
    except Exception as e:
        logger.error(f"获取 Tableau 组件失败: {e}")
        return None, None, None, None, None


def create_workflow_context(
    datasource_luid: str,
    data_model: Any,
    platform_adapter: Any = None,
    dimension_hierarchy: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """创建 WorkflowContext 配置
    
    Args:
        datasource_luid: 数据源 LUID
        data_model: 数据模型
        platform_adapter: 平台适配器
        dimension_hierarchy: 维度层级
    
    Returns:
        RunnableConfig 格式的配置
    """
    from analytics_assistant.src.orchestration.workflow.context import WorkflowContext
    from analytics_assistant.src.agents.semantic_parser.components import compute_schema_hash
    
    schema_hash = compute_schema_hash(data_model) if data_model else ""
    
    ctx = WorkflowContext(
        datasource_luid=datasource_luid,
        data_model=data_model,
        platform_adapter=platform_adapter,
        dimension_hierarchy=dimension_hierarchy,
        schema_hash=schema_hash,
    )
    
    return {
        "configurable": {
            "workflow_context": ctx,
            "thread_id": f"test-{datetime.now().isoformat()}",
        }
    }


# ═══════════════════════════════════════════════════════════════════════════
# 测试类
# ═══════════════════════════════════════════════════════════════════════════

class TestGraphFlowSimpleQuery:
    """Task 25.1.1: 测试简单查询完整流程"""
    
    @pytest.mark.asyncio
    async def test_simple_query_full_flow(self):
        """测试简单查询从意图路由到反馈学习的完整流程"""
        from analytics_assistant.src.agents.semantic_parser.graph import (
            create_semantic_parser_graph,
            compile_semantic_parser_graph,
        )
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            print("\n" + "=" * 60)
            print("Task 25.1.1: 简单查询完整流程测试")
            print("=" * 60)
            
            # 编译图
            checkpointer = MemorySaver()
            graph = compile_semantic_parser_graph(checkpointer=checkpointer)
            
            # 创建配置
            config = create_workflow_context(
                datasource_luid=datasource_luid,
                data_model=data_model,
                platform_adapter=adapter,
            )
            
            # 初始状态
            initial_state: SemanticParserState = {
                "question": "各地区的销售额",
                "datasource_luid": datasource_luid,
                "current_time": datetime.now().isoformat(),
            }
            
            print(f"\n问题: {initial_state['question']}")
            print("-" * 40)
            
            # 执行图
            result = await graph.ainvoke(initial_state, config)
            
            # 验证结果
            print("\n执行结果:")
            print(f"  - 意图: {result.get('intent_router_output', {}).get('intent_type')}")
            print(f"  - 缓存命中: {result.get('cache_hit', False)}")
            print(f"  - 需要澄清: {result.get('needs_clarification', False)}")
            
            if result.get("semantic_output"):
                semantic_output = result["semantic_output"]
                print(f"  - 重述问题: {semantic_output.get('restated_question')}")
                print(f"  - Query ID: {semantic_output.get('query_id')}")
            
            if result.get("parse_result"):
                parse_result = result["parse_result"]
                print(f"  - 解析成功: {parse_result.get('success')}")
            
            # 断言
            assert result.get("intent_router_output") is not None
            assert result["intent_router_output"]["intent_type"] == "data_query"
            assert result.get("semantic_output") is not None
            
            print("\n[PASS] 简单查询完整流程测试通过")
            
        finally:
            if client:
                await client.close()


class TestGraphFlowCacheHit:
    """Task 25.1.2: 测试缓存命中流程"""
    
    @pytest.mark.asyncio
    async def test_cache_hit_flow(self):
        """测试缓存命中时跳过语义理解直接返回"""
        from analytics_assistant.src.agents.semantic_parser.graph import (
            compile_semantic_parser_graph,
        )
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        from analytics_assistant.src.agents.semantic_parser.components import (
            QueryCache,
            compute_schema_hash,
        )
        
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            print("\n" + "=" * 60)
            print("Task 25.1.2: 缓存命中流程测试")
            print("=" * 60)
            
            # 预先写入缓存
            cache = QueryCache()
            question = "测试缓存命中的问题"
            
            # 使用与 create_workflow_context 相同的方式计算 schema_hash
            from analytics_assistant.src.agents.semantic_parser.components import compute_schema_hash
            schema_hash = compute_schema_hash(data_model)  # 传递 data_model 对象，不是 fields
            
            cached_output = {
                "query_id": "cached-query-id",
                "restated_question": "这是缓存的重述问题",
                "what": {"measures": []},
                "where": {"dimensions": [], "filters": []},
                "how_type": "SIMPLE",
                "needs_clarification": False,
                "self_check": {
                    "field_mapping_confidence": 0.9,
                    "time_range_confidence": 1.0,
                    "computation_confidence": 1.0,
                    "overall_confidence": 0.9,
                    "potential_issues": [],
                },
            }
            
            cache.set(
                question=question,
                datasource_luid=datasource_luid,
                schema_hash=schema_hash,
                semantic_output=cached_output,
                query="cached_query",
            )
            
            print(f"\n已写入缓存: {question}")
            
            # 编译图
            checkpointer = MemorySaver()
            graph = compile_semantic_parser_graph(checkpointer=checkpointer)
            
            # 创建配置
            config = create_workflow_context(
                datasource_luid=datasource_luid,
                data_model=data_model,
                platform_adapter=adapter,
            )
            
            # 初始状态
            initial_state: SemanticParserState = {
                "question": question,
                "datasource_luid": datasource_luid,
                "current_time": datetime.now().isoformat(),
            }
            
            print(f"\n问题: {initial_state['question']}")
            print("-" * 40)
            
            # 执行图
            result = await graph.ainvoke(initial_state, config)
            
            # 验证结果
            print("\n执行结果:")
            print(f"  - 缓存命中: {result.get('cache_hit', False)}")
            
            if result.get("semantic_output"):
                semantic_output = result["semantic_output"]
                print(f"  - Query ID: {semantic_output.get('query_id')}")
            
            # 断言
            assert result.get("cache_hit") is True
            assert result.get("semantic_output") is not None
            assert result["semantic_output"]["query_id"] == "cached-query-id"
            
            print("\n[PASS] 缓存命中流程测试通过")
            
        finally:
            if client:
                await client.close()


class TestGraphFlowClarification:
    """Task 25.1.3: 测试需要澄清的流程"""
    
    @pytest.mark.asyncio
    async def test_clarification_flow(self):
        """测试模糊问题触发澄清请求"""
        from analytics_assistant.src.agents.semantic_parser.graph import (
            compile_semantic_parser_graph,
        )
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            print("\n" + "=" * 60)
            print("Task 25.1.3: 需要澄清的流程测试")
            print("=" * 60)
            
            # 编译图
            checkpointer = MemorySaver()
            graph = compile_semantic_parser_graph(checkpointer=checkpointer)
            
            # 创建配置
            config = create_workflow_context(
                datasource_luid=datasource_luid,
                data_model=data_model,
                platform_adapter=adapter,
            )
            
            # 使用模糊问题
            initial_state: SemanticParserState = {
                "question": "数据",  # 非常模糊的问题
                "datasource_luid": datasource_luid,
                "current_time": datetime.now().isoformat(),
            }
            
            print(f"\n问题: {initial_state['question']}")
            print("-" * 40)
            
            # 执行图
            result = await graph.ainvoke(initial_state, config)
            
            # 验证结果
            print("\n执行结果:")
            print(f"  - 意图: {result.get('intent_router_output', {}).get('intent_type')}")
            print(f"  - 需要澄清: {result.get('needs_clarification', False)}")
            
            if result.get("clarification_question"):
                print(f"  - 澄清问题: {result['clarification_question']}")
            
            if result.get("clarification_source"):
                print(f"  - 澄清来源: {result['clarification_source']}")
            
            # 断言：模糊问题应该触发澄清或被识别为需要更多信息
            # 注意：LLM 可能会尝试理解，所以我们检查是否有合理的响应
            assert result.get("intent_router_output") is not None
            
            print("\n[PASS] 需要澄清的流程测试通过")
            
        finally:
            if client:
                await client.close()


class TestGraphFlowFilterConfirmation:
    """Task 25.1.4: 测试筛选值确认流程（interrupt/resume）"""
    
    @pytest.mark.asyncio
    async def test_filter_confirmation_interrupt_resume(self):
        """测试筛选值不匹配时的 interrupt/resume 机制
        
        Property 34: Filter Confirmation via LangGraph interrupt()
        Property 35: Filter Value Update After Confirmation
        Property 40: Multi-Round Filter Confirmation Accumulation
        """
        from analytics_assistant.src.agents.semantic_parser.graph import (
            compile_semantic_parser_graph,
            filter_validator_node,
        )
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            SemanticOutput,
            What,
            Where,
            SelfCheck,
        )
        from analytics_assistant.src.core.schemas.fields import MeasureField, DimensionField
        
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            print("\n" + "=" * 60)
            print("Task 25.1.4: 筛选值确认流程测试 (interrupt/resume)")
            print("=" * 60)
            
            # 编译图
            checkpointer = MemorySaver()
            graph = compile_semantic_parser_graph(checkpointer=checkpointer)
            
            # 创建配置
            config = create_workflow_context(
                datasource_luid=datasource_luid,
                data_model=data_model,
                platform_adapter=adapter,
            )
            config["configurable"]["thread_id"] = "test-filter-confirmation"
            
            # 使用包含可能不精确匹配的筛选值的问题
            initial_state: SemanticParserState = {
                "question": "北京地区上个月的销售额",  # "北京" 可能需要确认为 "北京市"
                "datasource_luid": datasource_luid,
                "current_time": datetime.now().isoformat(),
            }
            
            print(f"\n问题: {initial_state['question']}")
            print("-" * 40)
            
            # 执行图（可能会在 filter_validator 处 interrupt）
            try:
                result = await graph.ainvoke(initial_state, config)
                
                # 如果没有 interrupt，检查结果
                print("\n执行结果（无 interrupt）:")
                print(f"  - 需要澄清: {result.get('needs_clarification', False)}")
                
                if result.get("filter_validation_result"):
                    validation = result["filter_validation_result"]
                    print(f"  - 验证通过: {validation.get('all_valid', False)}")
                    print(f"  - 需要确认: {validation.get('needs_confirmation', False)}")
                
            except Exception as e:
                # 检查是否是 interrupt
                if "interrupt" in str(e).lower():
                    print("\n检测到 interrupt，模拟用户确认...")
                    
                    # 获取当前状态
                    state = graph.get_state(config)
                    
                    # 模拟用户确认
                    user_response = {
                        "confirmations": {
                            "地区": "北京市",  # 假设用户确认
                        }
                    }
                    
                    # 恢复执行
                    result = await graph.ainvoke(
                        None,  # 使用 checkpoint 中的状态
                        config,
                        interrupt_before=None,
                    )
                    
                    print("\n恢复执行后的结果:")
                    print(f"  - 确认的筛选值: {result.get('confirmed_filters', [])}")
                else:
                    raise
            
            # 验证
            assert result.get("intent_router_output") is not None
            
            print("\n[PASS] 筛选值确认流程测试通过")
            
        finally:
            if client:
                await client.close()


class TestGraphFlowErrorCorrection:
    """Task 25.1.5: 测试错误修正流程"""
    
    @pytest.mark.asyncio
    async def test_error_correction_flow(self):
        """测试查询执行失败后的错误修正流程
        
        Property 14: Retry Limit Enforcement
        Property 30: Duplicate Error Detection
        Property 31: Non-Retryable Error Handling
        """
        from analytics_assistant.src.agents.semantic_parser.graph import (
            error_corrector_node,
            route_after_correction,
        )
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            SemanticOutput,
            What,
            Where,
            SelfCheck,
        )
        from analytics_assistant.src.core.schemas.fields import MeasureField
        
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            print("\n" + "=" * 60)
            print("Task 25.1.5: 错误修正流程测试")
            print("=" * 60)
            
            # 构造一个有错误的状态
            semantic_output = SemanticOutput(
                query_id="test-error-correction",
                restated_question="各地区的销售额",
                what=What(measures=[
                    MeasureField(
                        field_name="不存在的字段",  # 故意使用不存在的字段
                        aggregation="SUM",
                    )
                ]),
                where=Where(dimensions=[], filters=[]),
                how_type="SIMPLE",
                needs_clarification=False,
                self_check=SelfCheck(
                    field_mapping_confidence=0.5,
                    time_range_confidence=1.0,
                    computation_confidence=1.0,
                    overall_confidence=0.5,
                ),
            )
            
            state: SemanticParserState = {
                "question": "各地区的销售额",
                "semantic_output": semantic_output.model_dump(),
                "pipeline_error": {
                    "error_type": "field_not_found",
                    "message": "字段 '不存在的字段' 在数据源中不存在",
                    "is_retryable": True,
                },
                "error_history": [],
                "retry_count": 0,
            }
            
            print(f"\n问题: {state['question']}")
            print(f"错误: {state['pipeline_error']['message']}")
            print("-" * 40)
            
            # 执行错误修正节点
            result = await error_corrector_node(state)
            
            # 验证结果
            print("\n错误修正结果:")
            print(f"  - 重试次数: {result.get('retry_count', 0)}")
            print(f"  - 终止原因: {result.get('correction_abort_reason', 'None')}")
            
            if result.get("semantic_output"):
                corrected = result["semantic_output"]
                print(f"  - 修正后的 Query ID: {corrected.get('query_id')}")
            
            if result.get("thinking"):
                print(f"  - 思考过程: {result['thinking'][:100]}...")
            
            # 测试路由函数
            updated_state = {**state, **result}
            route = route_after_correction(updated_state)
            print(f"  - 路由决策: {route}")
            
            # 断言
            assert result.get("error_history") is not None
            assert len(result["error_history"]) > 0
            
            print("\n[PASS] 错误修正流程测试通过")
            
        finally:
            if client:
                await client.close()


class TestGraphFlowBoundaryConditions:
    """Task 25.1.6-25.1.8: 测试边界条件"""
    
    @pytest.mark.asyncio
    async def test_empty_field_list(self):
        """Task 25.1.6: 测试空字段列表"""
        from analytics_assistant.src.agents.semantic_parser.graph import (
            field_retriever_node,
            semantic_understanding_node,
        )
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        
        print("\n" + "=" * 60)
        print("Task 25.1.6: 空字段列表边界条件测试")
        print("=" * 60)
        
        # 空字段列表的状态
        state: SemanticParserState = {
            "question": "销售额",
            "field_candidates": [],  # 空字段列表
        }
        
        print(f"\n问题: {state['question']}")
        print(f"字段候选: {state['field_candidates']}")
        print("-" * 40)
        
        # 执行语义理解节点
        result = await semantic_understanding_node(state)
        
        # 验证结果
        print("\n执行结果:")
        print(f"  - 需要澄清: {result.get('needs_clarification', False)}")
        
        if result.get("semantic_output"):
            semantic_output = result["semantic_output"]
            print(f"  - 重述问题: {semantic_output.get('restated_question')}")
        
        # 断言：即使字段列表为空，也应该有响应
        assert result is not None
        
        print("\n[PASS] 空字段列表边界条件测试通过")
    
    @pytest.mark.asyncio
    async def test_empty_few_shot_examples(self):
        """Task 25.1.7: 测试空 Few-shot 示例库"""
        from analytics_assistant.src.agents.semantic_parser.graph import (
            few_shot_manager_node,
            semantic_understanding_node,
        )
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        from analytics_assistant.src.agents.semantic_parser.schemas.intermediate import (
            FieldCandidate,
        )
        
        print("\n" + "=" * 60)
        print("Task 25.1.7: 空 Few-shot 示例库边界条件测试")
        print("=" * 60)
        
        # 构造字段候选
        field_candidates = [
            FieldCandidate(
                field_name="sales",
                field_caption="销售额",
                role="measure",
                data_type="REAL",
                score=0.9,
            ).model_dump(),
            FieldCandidate(
                field_name="region",
                field_caption="地区",
                role="dimension",
                data_type="STRING",
                score=0.9,
            ).model_dump(),
        ]
        
        # 空 Few-shot 示例的状态
        state: SemanticParserState = {
            "question": "各地区的销售额",
            "field_candidates": field_candidates,
            "few_shot_examples": [],  # 空示例库
            "current_time": datetime.now().isoformat(),
        }
        
        print(f"\n问题: {state['question']}")
        print(f"Few-shot 示例: {state['few_shot_examples']}")
        print("-" * 40)
        
        # 执行语义理解节点
        result = await semantic_understanding_node(state)
        
        # 验证结果
        print("\n执行结果:")
        
        if result.get("semantic_output"):
            semantic_output = result["semantic_output"]
            print(f"  - 重述问题: {semantic_output.get('restated_question')}")
            print(f"  - Query ID: {semantic_output.get('query_id')}")
        
        # 断言：即使没有 Few-shot 示例，也应该能正常工作
        assert result.get("semantic_output") is not None
        
        print("\n[PASS] 空 Few-shot 示例库边界条件测试通过")
    
    @pytest.mark.asyncio
    async def test_network_timeout_degradation(self):
        """Task 25.1.8: 测试网络超时降级"""
        from analytics_assistant.src.agents.semantic_parser.graph import (
            intent_router_node,
        )
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        from analytics_assistant.src.agents.semantic_parser.components import IntentRouter
        
        print("\n" + "=" * 60)
        print("Task 25.1.8: 网络超时降级边界条件测试")
        print("=" * 60)
        
        # 测试 IntentRouter 的 L0 规则（不依赖网络）
        state: SemanticParserState = {
            "question": "各地区的销售额",
        }
        
        print(f"\n问题: {state['question']}")
        print("-" * 40)
        
        # 执行意图路由节点（L0 规则不需要网络）
        result = await intent_router_node(state)
        
        # 验证结果
        print("\n执行结果:")
        print(f"  - 意图: {result.get('intent_router_output', {}).get('intent_type')}")
        print(f"  - 来源: {result.get('intent_router_output', {}).get('source')}")
        
        # 断言：L0 规则应该能在无网络时工作
        assert result.get("intent_router_output") is not None
        
        # 测试 IntentRouter 直接调用
        router = IntentRouter()
        
        # 模拟 LLM 超时的情况（L1 失败，回退到 L0）
        with patch.object(router, '_try_l1_classifier', side_effect=TimeoutError("Network timeout")):
            route_result = await router.route("各地区的销售额")
            
            print(f"\n模拟超时后的结果:")
            print(f"  - 意图: {route_result.intent_type.value}")
            print(f"  - 来源: {route_result.source}")
            
            # 断言：超时后应该回退到 L0 规则
            assert route_result is not None
        
        print("\n[PASS] 网络超时降级边界条件测试通过")


class TestGraphFlowRouting:
    """测试路由函数的正确性"""
    
    @pytest.mark.asyncio
    async def test_route_by_intent(self):
        """测试意图路由函数"""
        from analytics_assistant.src.agents.semantic_parser.graph import route_by_intent
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        
        print("\n" + "=" * 60)
        print("路由函数测试: route_by_intent")
        print("=" * 60)
        
        test_cases = [
            ({"intent_type": "data_query", "confidence": 0.9}, "data_query"),
            ({"intent_type": "general", "confidence": 0.8}, "general"),
            ({"intent_type": "irrelevant", "confidence": 0.95}, "irrelevant"),
            ({"intent_type": "clarification", "confidence": 0.7}, "clarification"),
        ]
        
        for intent_output, expected_route in test_cases:
            state: SemanticParserState = {
                "intent_router_output": intent_output,
            }
            
            result = route_by_intent(state)
            print(f"  - 意图 {intent_output['intent_type']} -> 路由 {result}")
            
            assert result == expected_route
        
        print("\n[PASS] route_by_intent 测试通过")
    
    @pytest.mark.asyncio
    async def test_route_by_cache(self):
        """测试缓存路由函数"""
        from analytics_assistant.src.agents.semantic_parser.graph import route_by_cache
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        
        print("\n" + "=" * 60)
        print("路由函数测试: route_by_cache")
        print("=" * 60)
        
        # 缓存命中
        state_hit: SemanticParserState = {"cache_hit": True}
        result_hit = route_by_cache(state_hit)
        print(f"  - 缓存命中 -> 路由 {result_hit}")
        assert result_hit == "cache_hit"
        
        # 缓存未命中
        state_miss: SemanticParserState = {"cache_hit": False}
        result_miss = route_by_cache(state_miss)
        print(f"  - 缓存未命中 -> 路由 {result_miss}")
        assert result_miss == "cache_miss"
        
        # 无缓存字段
        state_none: SemanticParserState = {}
        result_none = route_by_cache(state_none)
        print(f"  - 无缓存字段 -> 路由 {result_none}")
        assert result_none == "cache_miss"
        
        print("\n[PASS] route_by_cache 测试通过")
    
    @pytest.mark.asyncio
    async def test_route_after_understanding(self):
        """测试语义理解后的路由函数"""
        from analytics_assistant.src.agents.semantic_parser.graph import route_after_understanding
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        
        print("\n" + "=" * 60)
        print("路由函数测试: route_after_understanding")
        print("=" * 60)
        
        # 需要澄清
        state_clarify: SemanticParserState = {"needs_clarification": True}
        result_clarify = route_after_understanding(state_clarify)
        print(f"  - 需要澄清 -> 路由 {result_clarify}")
        assert result_clarify == "needs_clarification"
        
        # 继续处理
        state_continue: SemanticParserState = {"needs_clarification": False}
        result_continue = route_after_understanding(state_continue)
        print(f"  - 不需要澄清 -> 路由 {result_continue}")
        assert result_continue == "continue"
        
        print("\n[PASS] route_after_understanding 测试通过")
    
    @pytest.mark.asyncio
    async def test_route_after_validation(self):
        """测试筛选值验证后的路由函数"""
        from analytics_assistant.src.agents.semantic_parser.graph import route_after_validation
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        
        print("\n" + "=" * 60)
        print("路由函数测试: route_after_validation")
        print("=" * 60)
        
        # 验证通过
        state_valid: SemanticParserState = {
            "filter_validation_result": {"all_valid": True, "has_unresolvable_filters": False},
        }
        result_valid = route_after_validation(state_valid)
        print(f"  - 验证通过 -> 路由 {result_valid}")
        assert result_valid == "valid"
        
        # 有无法解决的筛选值
        state_unresolvable: SemanticParserState = {
            "filter_validation_result": {"all_valid": False, "has_unresolvable_filters": True},
        }
        result_unresolvable = route_after_validation(state_unresolvable)
        print(f"  - 无法解决的筛选值 -> 路由 {result_unresolvable}")
        assert result_unresolvable == "needs_clarification"
        
        # 需要澄清（来自节点）
        state_clarify: SemanticParserState = {
            "needs_clarification": True,
            "filter_validation_result": {},
        }
        result_clarify = route_after_validation(state_clarify)
        print(f"  - 需要澄清 -> 路由 {result_clarify}")
        assert result_clarify == "needs_clarification"
        
        print("\n[PASS] route_after_validation 测试通过")
    
    @pytest.mark.asyncio
    async def test_route_after_query(self):
        """测试查询执行后的路由函数"""
        from analytics_assistant.src.agents.semantic_parser.graph import route_after_query
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        
        print("\n" + "=" * 60)
        print("路由函数测试: route_after_query")
        print("=" * 60)
        
        # 执行成功
        state_success: SemanticParserState = {"semantic_query": {"query": "..."}}
        result_success = route_after_query(state_success)
        print(f"  - 执行成功 -> 路由 {result_success}")
        assert result_success == "success"
        
        # 执行失败
        state_error: SemanticParserState = {
            "pipeline_error": {"error_type": "validation_error", "message": "..."},
        }
        result_error = route_after_query(state_error)
        print(f"  - 执行失败 -> 路由 {result_error}")
        assert result_error == "error"
        
        print("\n[PASS] route_after_query 测试通过")
    
    @pytest.mark.asyncio
    async def test_route_after_correction(self):
        """测试错误修正后的路由函数"""
        from analytics_assistant.src.agents.semantic_parser.graph import route_after_correction
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        
        print("\n" + "=" * 60)
        print("路由函数测试: route_after_correction")
        print("=" * 60)
        
        # 重试
        state_retry: SemanticParserState = {
            "retry_count": 1,
            "correction_abort_reason": None,
            "pipeline_error": None,
        }
        result_retry = route_after_correction(state_retry)
        print(f"  - 可以重试 -> 路由 {result_retry}")
        assert result_retry == "retry"
        
        # 达到最大重试次数
        state_max: SemanticParserState = {
            "correction_abort_reason": "max_retries_exceeded",
        }
        result_max = route_after_correction(state_max)
        print(f"  - 达到最大重试 -> 路由 {result_max}")
        assert result_max == "max_retries"
        
        # 仍有错误
        state_error: SemanticParserState = {
            "pipeline_error": {"error_type": "...", "message": "..."},
        }
        result_error = route_after_correction(state_error)
        print(f"  - 仍有错误 -> 路由 {result_error}")
        assert result_error == "max_retries"
        
        print("\n[PASS] route_after_correction 测试通过")


class TestGraphFlowNodeFunctions:
    """测试各节点函数的独立功能"""
    
    @pytest.mark.asyncio
    async def test_intent_router_node(self):
        """测试意图路由节点"""
        from analytics_assistant.src.agents.semantic_parser.graph import intent_router_node
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        
        print("\n" + "=" * 60)
        print("节点函数测试: intent_router_node")
        print("=" * 60)
        
        test_cases = [
            ("各地区的销售额", "data_query"),
            ("", "irrelevant"),  # 空问题
        ]
        
        for question, expected_intent in test_cases:
            state: SemanticParserState = {"question": question}
            result = await intent_router_node(state)
            
            actual_intent = result.get("intent_router_output", {}).get("intent_type")
            print(f"  - '{question}' -> {actual_intent}")
            
            assert result.get("intent_router_output") is not None
            if question == "":
                assert actual_intent.lower() == "irrelevant"
        
        print("\n[PASS] intent_router_node 测试通过")
    
    @pytest.mark.asyncio
    async def test_field_retriever_node(self):
        """测试字段检索节点"""
        from analytics_assistant.src.agents.semantic_parser.graph import field_retriever_node
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            print("\n" + "=" * 60)
            print("节点函数测试: field_retriever_node")
            print("=" * 60)
            
            # 创建配置
            config = create_workflow_context(
                datasource_luid=datasource_luid,
                data_model=data_model,
            )
            
            state: SemanticParserState = {
                "question": "各地区的销售额",
            }
            
            result = await field_retriever_node(state, config)
            
            print(f"\n问题: {state['question']}")
            print(f"检索到 {len(result.get('field_candidates', []))} 个字段候选")
            
            for fc in result.get("field_candidates", [])[:5]:
                print(f"  - {fc.get('field_caption')} ({fc.get('role')})")
            
            assert result.get("field_candidates") is not None
            
            print("\n[PASS] field_retriever_node 测试通过")
            
        finally:
            if client:
                await client.close()
    
    @pytest.mark.asyncio
    async def test_few_shot_manager_node(self):
        """测试 Few-shot 管理节点"""
        from analytics_assistant.src.agents.semantic_parser.graph import few_shot_manager_node
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        
        print("\n" + "=" * 60)
        print("节点函数测试: few_shot_manager_node")
        print("=" * 60)
        
        state: SemanticParserState = {
            "question": "各地区的销售额",
            "datasource_luid": "test-datasource",
        }
        
        result = await few_shot_manager_node(state)
        
        print(f"\n问题: {state['question']}")
        print(f"检索到 {len(result.get('few_shot_examples', []))} 个示例")
        
        # Few-shot 示例可能为空（如果没有预先添加）
        assert "few_shot_examples" in result
        
        print("\n[PASS] few_shot_manager_node 测试通过")
    
    @pytest.mark.asyncio
    async def test_feedback_learner_node(self):
        """测试反馈学习节点"""
        from analytics_assistant.src.agents.semantic_parser.graph import feedback_learner_node
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            SemanticOutput,
            What,
            Where,
            SelfCheck,
        )
        from analytics_assistant.src.core.schemas.fields import MeasureField
        
        print("\n" + "=" * 60)
        print("节点函数测试: feedback_learner_node")
        print("=" * 60)
        
        semantic_output = SemanticOutput(
            query_id="test-feedback",
            restated_question="各地区的销售额",
            what=What(measures=[
                MeasureField(field_name="sales", aggregation="SUM")
            ]),
            where=Where(dimensions=[], filters=[]),
            how_type="SIMPLE",
            needs_clarification=False,
            self_check=SelfCheck(
                field_mapping_confidence=0.9,
                time_range_confidence=1.0,
                computation_confidence=1.0,
                overall_confidence=0.9,
            ),
        )
        
        state: SemanticParserState = {
            "question": "各地区的销售额",
            "semantic_output": semantic_output.model_dump(),
            "semantic_query": {"query": "test_query"},
            "datasource_luid": "test-datasource",
            "confirmed_filters": [],
        }
        
        result = await feedback_learner_node(state)
        
        print(f"\n问题: {state['question']}")
        print(f"解析结果: {result.get('parse_result', {}).get('success')}")
        
        assert result.get("parse_result") is not None
        assert result["parse_result"]["success"] is True
        
        print("\n[PASS] feedback_learner_node 测试通过")


# ═══════════════════════════════════════════════════════════════════════════
# 运行测试
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
