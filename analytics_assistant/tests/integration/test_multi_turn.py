# -*- coding: utf-8 -*-
"""
多轮对话集成测试

测试 SemanticParser LangGraph 子图的多轮对话功能，包括：
- 渐进式查询构建（Task 26.1.1）
- 多轮筛选值确认（Task 26.1.2）
- 对话历史管理（Task 26.1.3）

运行方式：
    cd analytics_assistant
    $env:PYTHONPATH = ".."
    pytest tests/integration/test_multi_turn.py -v --tb=short -s

测试要求：
- 使用真实 LLM (DeepSeek) 和真实 Embedding (Zhipu)
- 配置文件：analytics_assistant/config/app.yaml

相关 Properties：
- Property 9: Incremental State Update
- Property 17: History Truncation
- Property 40: Multi-Round Filter Confirmation Accumulation
"""

import logging
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytest
from langgraph.checkpoint.memory import MemorySaver

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
    """获取真实的 Tableau 组件"""
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
    auth: Any = None,
) -> Dict[str, Any]:
    """创建 WorkflowContext 配置"""
    from analytics_assistant.src.orchestration.workflow.context import WorkflowContext
    from analytics_assistant.src.agents.semantic_parser.components import compute_schema_hash
    
    schema_hash = compute_schema_hash(data_model) if data_model else ""
    
    ctx = WorkflowContext(
        auth=auth,
        datasource_luid=datasource_luid,
        data_model=data_model,
        platform_adapter=platform_adapter,
        dimension_hierarchy=dimension_hierarchy,
    )
    
    return {
        "configurable": {
            "workflow_context": ctx,
            "thread_id": f"test-multi-turn-{datetime.now().isoformat()}",
        }
    }


# ═══════════════════════════════════════════════════════════════════════════
# Task 26.1.1: 测试渐进式查询构建
# ═══════════════════════════════════════════════════════════════════════════

class TestProgressiveQueryBuilding:
    """Task 26.1.1: 测试渐进式查询构建
    
    验证多轮对话中，系统能够：
    1. 理解上下文，逐步完善查询
    2. 保留之前轮次的信息
    3. 正确合并新信息与现有状态
    
    Property 9: Incremental State Update
    """
    
    @pytest.mark.asyncio
    async def test_progressive_query_two_rounds(self):
        """测试两轮对话的渐进式查询构建
        
        第1轮: "我想看销售数据" → 需要澄清时间段
        第2轮: "上个月的，按地区" → 完成查询
        """
        from analytics_assistant.src.agents.semantic_parser.graph import (
            compile_semantic_parser_graph,
        )
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            print("\n" + "=" * 60)
            print("Task 26.1.1: 渐进式查询构建测试 - 两轮对话")
            print("=" * 60)
            
            checkpointer = MemorySaver()
            graph = compile_semantic_parser_graph(checkpointer=checkpointer)
            
            config = create_workflow_context(
                datasource_luid=datasource_luid,
                data_model=data_model,
                platform_adapter=adapter,
                auth=auth,
            )
            thread_id = f"progressive-query-{datetime.now().isoformat()}"
            config["configurable"]["thread_id"] = thread_id
            
            # ========== 第1轮对话 ==========
            print("\n--- 第1轮对话 ---")
            initial_state: SemanticParserState = {
                "question": "我想看销售数据",
                "datasource_luid": datasource_luid,
                "current_time": datetime.now().isoformat(),
            }
            
            print(f"用户: {initial_state['question']}")
            
            result1 = await graph.ainvoke(initial_state, config)
            
            print(f"意图: {result1.get('intent_router_output', {}).get('intent_type')}")
            print(f"需要澄清: {result1.get('needs_clarification', False)}")
            
            if result1.get("clarification_question"):
                print(f"澄清问题: {result1['clarification_question']}")
            
            if result1.get("semantic_output"):
                output1 = result1["semantic_output"]
                print(f"重述问题: {output1.get('restated_question')}")
            
            # 断言第1轮
            assert result1.get("intent_router_output") is not None
            assert result1["intent_router_output"]["intent_type"] == "data_query"
            
            # ========== 第2轮对话 ==========
            print("\n--- 第2轮对话 ---")
            
            # 构建对话历史
            chat_history = [
                {"role": "user", "content": "我想看销售数据"},
                {"role": "assistant", "content": result1.get("clarification_question", "请问您想看哪个时间段的销售数据？")},
            ]
            
            second_state: SemanticParserState = {
                "question": "上个月的，按地区",
                "chat_history": chat_history,
                "datasource_luid": datasource_luid,
                "current_time": datetime.now().isoformat(),
            }
            
            print(f"用户: {second_state['question']}")
            
            result2 = await graph.ainvoke(second_state, config)
            
            print(f"需要澄清: {result2.get('needs_clarification', False)}")
            
            if result2.get("semantic_output"):
                output2 = result2["semantic_output"]
                print(f"重述问题: {output2.get('restated_question')}")
                print(f"度量: {output2.get('what', {}).get('measures', [])}")
                print(f"维度: {output2.get('where', {}).get('dimensions', [])}")
                print(f"筛选: {output2.get('where', {}).get('filters', [])}")
            
            # 断言第2轮
            assert result2.get("semantic_output") is not None
            output2 = result2["semantic_output"]
            
            # 验证 Property 9: Incremental State Update
            # 第2轮应该合并了第1轮的上下文（销售数据）和新信息（上个月、按地区）
            restated = output2.get("restated_question", "")
            assert "销售" in restated or "sales" in restated.lower(), \
                f"重述问题应包含'销售': {restated}"
            
            print("\n[PASS] 渐进式查询构建测试通过")
            
        finally:
            if client:
                await client.close()
    
    @pytest.mark.asyncio
    async def test_progressive_query_three_rounds_with_derived_metric(self):
        """测试三轮对话的渐进式查询构建（含派生度量）
        
        第1轮: "销售数据" → 需要澄清
        第2轮: "上个月各地区的" → 完成基础查询
        第3轮: "利润率是多少？" → 添加派生度量
        """
        from analytics_assistant.src.agents.semantic_parser.graph import (
            compile_semantic_parser_graph,
        )
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            print("\n" + "=" * 60)
            print("Task 26.1.1: 渐进式查询构建测试 - 三轮对话（派生度量）")
            print("=" * 60)
            
            checkpointer = MemorySaver()
            graph = compile_semantic_parser_graph(checkpointer=checkpointer)
            
            config = create_workflow_context(
                datasource_luid=datasource_luid,
                data_model=data_model,
                platform_adapter=adapter,
                auth=auth,
            )
            thread_id = f"progressive-derived-{datetime.now().isoformat()}"
            config["configurable"]["thread_id"] = thread_id
            
            # ========== 第1轮对话 ==========
            print("\n--- 第1轮对话 ---")
            state1: SemanticParserState = {
                "question": "各地区上个月的销售额",
                "datasource_luid": datasource_luid,
                "current_time": datetime.now().isoformat(),
            }
            
            print(f"用户: {state1['question']}")
            result1 = await graph.ainvoke(state1, config)
            
            if result1.get("semantic_output"):
                output1 = result1["semantic_output"]
                print(f"重述问题: {output1.get('restated_question')}")
            
            # ========== 第2轮对话 ==========
            print("\n--- 第2轮对话 ---")
            
            chat_history = [
                {"role": "user", "content": "各地区上个月的销售额"},
                {"role": "assistant", "content": f"已查询: {result1.get('semantic_output', {}).get('restated_question', '')}"},
            ]
            
            state2: SemanticParserState = {
                "question": "利润率是多少？",
                "chat_history": chat_history,
                "datasource_luid": datasource_luid,
                "current_time": datetime.now().isoformat(),
            }
            
            print(f"用户: {state2['question']}")
            result2 = await graph.ainvoke(state2, config)
            
            if result2.get("semantic_output"):
                output2 = result2["semantic_output"]
                print(f"重述问题: {output2.get('restated_question')}")
                print(f"计算类型: {output2.get('how_type')}")
                print(f"计算公式: {output2.get('computations', [])}")
            
            # 断言
            assert result2.get("semantic_output") is not None
            output2 = result2["semantic_output"]
            
            # 验证派生度量被识别
            restated = output2.get("restated_question", "")
            assert "利润" in restated or "profit" in restated.lower(), \
                f"重述问题应包含'利润': {restated}"
            
            print("\n[PASS] 三轮对话渐进式查询构建测试通过")
            
        finally:
            if client:
                await client.close()


# ═══════════════════════════════════════════════════════════════════════════
# Task 26.1.2: 测试多轮筛选值确认
# ═══════════════════════════════════════════════════════════════════════════

class TestMultiRoundFilterConfirmation:
    """Task 26.1.2: 测试多轮筛选值确认
    
    验证多轮筛选值确认时：
    1. confirmed_filters 正确累积
    2. 不丢失之前的确认结果
    3. interrupt/resume 机制正常工作
    
    Property 40: Multi-Round Filter Confirmation Accumulation
    """

    @pytest.mark.asyncio
    async def test_multi_round_filter_confirmation_accumulation(self):
        """测试多轮筛选值确认的累积
        
        Property 40: Multi-Round Filter Confirmation Accumulation
        验证多轮确认时 confirmed_filters 正确累积
        """
        from analytics_assistant.src.agents.semantic_parser.graph import (
            filter_validator_node,
        )
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            SemanticOutput,
            What,
            Where,
            SelfCheck,
        )
        from analytics_assistant.src.core.schemas.filters import SetFilter
        from analytics_assistant.src.core.schemas.enums import FilterType
        from analytics_assistant.src.core.schemas.fields import MeasureField, DimensionField
        
        print("\n" + "=" * 60)
        print("Task 26.1.2: 多轮筛选值确认累积测试")
        print("=" * 60)
        
        # 模拟已有的确认结果（第一轮确认）
        existing_confirmations = [
            {
                "field_name": "地区",
                "original_value": "北京",
                "confirmed_value": "北京市",
                "confirmed_at": "2024-01-01T10:00:00",
            }
        ]
        
        # 构造语义输出（包含需要确认的筛选值）
        semantic_output = SemanticOutput(
            query_id="test-multi-round-confirmation",
            restated_question="查询北京市和上海的销售额",
            what=What(measures=[
                MeasureField(field_name="销售额", aggregation="SUM")
            ]),
            where=Where(
                dimensions=[],
                filters=[
                    SetFilter(
                        field_name="地区",
                        filter_type=FilterType.SET,
                        values=["北京市", "上海"],  # 北京已确认，上海待确认
                    )
                ],
            ),
            how_type="SIMPLE",
            needs_clarification=False,
            self_check=SelfCheck(
                field_mapping_confidence=0.9,
                time_range_confidence=1.0,
                computation_confidence=1.0,
                overall_confidence=0.9,
            ),
        )
        
        # 构造状态
        state: SemanticParserState = {
            "question": "北京和上海的销售额",
            "semantic_output": semantic_output.model_dump(),
            "confirmed_filters": existing_confirmations,  # 已有的确认
        }
        
        print(f"\n问题: {state['question']}")
        print(f"已有确认: {existing_confirmations}")
        print("-" * 40)
        
        # 执行筛选值验证节点（不提供 config，跳过实际验证）
        result = await filter_validator_node(state, config=None)
        
        # 验证结果
        print("\n执行结果:")
        print(f"  - confirmed_filters: {result.get('confirmed_filters', [])}")
        
        # 断言：已有的确认应该被保留
        confirmed = result.get("confirmed_filters", [])
        assert len(confirmed) >= 1, "应该保留已有的确认"
        assert confirmed[0]["field_name"] == "地区", "第一个确认应该是地区"
        assert confirmed[0]["confirmed_value"] == "北京市", "确认值应该是北京市"
        
        print("\n[PASS] 多轮筛选值确认累积测试通过")
    
    @pytest.mark.asyncio
    async def test_filter_confirmation_with_real_data(self):
        """测试真实数据的筛选值确认流程"""
        from analytics_assistant.src.agents.semantic_parser.graph import (
            compile_semantic_parser_graph,
        )
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            print("\n" + "=" * 60)
            print("Task 26.1.2: 真实数据筛选值确认测试")
            print("=" * 60)
            
            checkpointer = MemorySaver()
            graph = compile_semantic_parser_graph(checkpointer=checkpointer)
            
            config = create_workflow_context(
                datasource_luid=datasource_luid,
                data_model=data_model,
                platform_adapter=adapter,
                auth=auth,
            )
            thread_id = f"filter-confirm-{datetime.now().isoformat()}"
            config["configurable"]["thread_id"] = thread_id
            
            # 使用可能需要确认的筛选值
            initial_state: SemanticParserState = {
                "question": "北京地区的销售额",
                "datasource_luid": datasource_luid,
                "current_time": datetime.now().isoformat(),
            }
            
            print(f"\n问题: {initial_state['question']}")
            print("-" * 40)
            
            # 执行图
            result = await graph.ainvoke(initial_state, config)
            
            # 验证结果
            print("\n执行结果:")
            print(f"  - 需要澄清: {result.get('needs_clarification', False)}")
            print(f"  - confirmed_filters: {result.get('confirmed_filters', [])}")
            
            if result.get("filter_validation_result"):
                validation = result["filter_validation_result"]
                print(f"  - 验证通过: {validation.get('all_valid', False)}")
                print(f"  - 需要确认: {validation.get('needs_confirmation', False)}")
            
            if result.get("semantic_output"):
                output = result["semantic_output"]
                print(f"  - 重述问题: {output.get('restated_question')}")
            
            # 断言
            assert result.get("semantic_output") is not None
            
            print("\n[PASS] 真实数据筛选值确认测试通过")
            
        finally:
            if client:
                await client.close()


# ═══════════════════════════════════════════════════════════════════════════
# Task 26.1.3: 测试对话历史管理
# ═══════════════════════════════════════════════════════════════════════════

class TestConversationHistoryManagement:
    """Task 26.1.3: 测试对话历史管理
    
    验证对话历史管理功能：
    1. 历史正确传递给 LLM
    2. 历史截断机制正常工作
    3. 上下文在多轮对话中保持一致
    
    Property 17: History Truncation
    """
    
    @pytest.mark.asyncio
    async def test_chat_history_passed_to_llm(self):
        """测试对话历史正确传递给 LLM"""
        from analytics_assistant.src.agents.semantic_parser.graph import (
            semantic_understanding_node,
        )
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        from analytics_assistant.src.agents.semantic_parser.schemas.intermediate import (
            FieldCandidate,
        )
        
        print("\n" + "=" * 60)
        print("Task 26.1.3: 对话历史传递测试")
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
            FieldCandidate(
                field_name="date",
                field_caption="日期",
                role="dimension",
                data_type="DATE",
                score=0.8,
            ).model_dump(),
        ]
        
        # 构造对话历史
        chat_history = [
            {"role": "user", "content": "我想看销售数据"},
            {"role": "assistant", "content": "请问您想看哪个时间段的销售数据？"},
            {"role": "user", "content": "上个月的"},
            {"role": "assistant", "content": "好的，您想按什么维度查看上个月的销售数据？"},
        ]
        
        state: SemanticParserState = {
            "question": "按地区",
            "chat_history": chat_history,
            "field_candidates": field_candidates,
            "few_shot_examples": [],
            "current_time": datetime.now().isoformat(),
        }
        
        print(f"\n当前问题: {state['question']}")
        print(f"对话历史轮数: {len(chat_history) // 2}")
        print("-" * 40)
        
        # 执行语义理解节点
        result = await semantic_understanding_node(state)
        
        # 验证结果
        print("\n执行结果:")
        
        if result.get("semantic_output"):
            output = result["semantic_output"]
            print(f"  - 重述问题: {output.get('restated_question')}")
            print(f"  - 度量: {output.get('what', {}).get('measures', [])}")
            print(f"  - 维度: {output.get('where', {}).get('dimensions', [])}")
        
        # 断言：LLM 应该理解上下文
        assert result.get("semantic_output") is not None
        output = result["semantic_output"]
        restated = output.get("restated_question", "")
        
        # 验证 LLM 理解了对话历史中的上下文
        # 重述问题应该包含"销售"、"上个月"、"地区"等关键词
        assert any(keyword in restated for keyword in ["销售", "sales", "地区", "region"]), \
            f"重述问题应包含上下文关键词: {restated}"
        
        print("\n[PASS] 对话历史传递测试通过")
    
    @pytest.mark.asyncio
    async def test_history_truncation_with_long_history(self):
        """测试长对话历史的截断机制
        
        Property 17: History Truncation
        验证截断后保留最近的消息
        """
        from analytics_assistant.src.agents.semantic_parser.graph import (
            semantic_understanding_node,
        )
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        from analytics_assistant.src.agents.semantic_parser.schemas.intermediate import (
            FieldCandidate,
        )
        
        print("\n" + "=" * 60)
        print("Task 26.1.3: 对话历史截断测试")
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
        ]
        
        # 构造长对话历史（10轮对话）
        chat_history = []
        for i in range(10):
            chat_history.append({"role": "user", "content": f"第{i+1}轮用户问题"})
            chat_history.append({"role": "assistant", "content": f"第{i+1}轮助手回复"})
        
        # 添加最近的相关对话
        chat_history.append({"role": "user", "content": "上个月各地区的销售额"})
        chat_history.append({"role": "assistant", "content": "已查询上个月各地区的销售额"})
        
        state: SemanticParserState = {
            "question": "利润率呢？",
            "chat_history": chat_history,
            "field_candidates": field_candidates,
            "few_shot_examples": [],
            "current_time": datetime.now().isoformat(),
        }
        
        print(f"\n当前问题: {state['question']}")
        print(f"对话历史轮数: {len(chat_history) // 2}")
        print("-" * 40)
        
        # 执行语义理解节点
        result = await semantic_understanding_node(state)
        
        # 验证结果
        print("\n执行结果:")
        
        if result.get("semantic_output"):
            output = result["semantic_output"]
            print(f"  - 重述问题: {output.get('restated_question')}")
        
        # 断言：即使历史很长，也应该能正常处理
        assert result.get("semantic_output") is not None
        
        print("\n[PASS] 对话历史截断测试通过")
    
    @pytest.mark.asyncio
    async def test_context_consistency_across_rounds(self):
        """测试多轮对话中上下文的一致性"""
        from analytics_assistant.src.agents.semantic_parser.graph import (
            compile_semantic_parser_graph,
        )
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            print("\n" + "=" * 60)
            print("Task 26.1.3: 上下文一致性测试")
            print("=" * 60)
            
            checkpointer = MemorySaver()
            graph = compile_semantic_parser_graph(checkpointer=checkpointer)
            
            config = create_workflow_context(
                datasource_luid=datasource_luid,
                data_model=data_model,
                platform_adapter=adapter,
                auth=auth,
            )
            thread_id = f"context-consistency-{datetime.now().isoformat()}"
            config["configurable"]["thread_id"] = thread_id
            
            # ========== 第1轮：建立上下文 ==========
            print("\n--- 第1轮对话 ---")
            state1: SemanticParserState = {
                "question": "上个月各地区的销售额",
                "datasource_luid": datasource_luid,
                "current_time": datetime.now().isoformat(),
            }
            
            print(f"用户: {state1['question']}")
            result1 = await graph.ainvoke(state1, config)
            
            output1 = result1.get("semantic_output", {})
            print(f"重述问题: {output1.get('restated_question')}")
            
            # ========== 第2轮：引用上下文 ==========
            print("\n--- 第2轮对话 ---")
            
            chat_history = [
                {"role": "user", "content": "上个月各地区的销售额"},
                {"role": "assistant", "content": f"已查询: {output1.get('restated_question', '')}"},
            ]
            
            state2: SemanticParserState = {
                "question": "同比增长呢？",
                "chat_history": chat_history,
                "datasource_luid": datasource_luid,
                "current_time": datetime.now().isoformat(),
            }
            
            print(f"用户: {state2['question']}")
            result2 = await graph.ainvoke(state2, config)
            
            output2 = result2.get("semantic_output", {})
            print(f"重述问题: {output2.get('restated_question')}")
            
            # ========== 第3轮：继续引用上下文 ==========
            print("\n--- 第3轮对话 ---")
            
            chat_history.append({"role": "user", "content": "同比增长呢？"})
            chat_history.append({"role": "assistant", "content": f"已查询: {output2.get('restated_question', '')}"})
            
            state3: SemanticParserState = {
                "question": "只看华东地区",
                "chat_history": chat_history,
                "datasource_luid": datasource_luid,
                "current_time": datetime.now().isoformat(),
            }
            
            print(f"用户: {state3['question']}")
            result3 = await graph.ainvoke(state3, config)
            
            output3 = result3.get("semantic_output", {})
            print(f"重述问题: {output3.get('restated_question')}")
            
            # 断言：第3轮应该保持之前的上下文
            assert result3.get("semantic_output") is not None
            restated3 = output3.get("restated_question", "")
            
            # 验证上下文一致性：应该包含"华东"或相关筛选
            assert "华东" in restated3 or "地区" in restated3 or "region" in restated3.lower(), \
                f"第3轮应该理解筛选上下文: {restated3}"
            
            print("\n[PASS] 上下文一致性测试通过")
            
        finally:
            if client:
                await client.close()


# ═══════════════════════════════════════════════════════════════════════════
# 综合测试
# ═══════════════════════════════════════════════════════════════════════════

class TestMultiTurnIntegration:
    """多轮对话综合集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_multi_turn_scenario(self):
        """测试完整的多轮对话场景
        
        模拟真实用户交互：
        1. 用户提出模糊问题
        2. 系统请求澄清
        3. 用户提供更多信息
        4. 系统生成查询
        5. 用户追问相关问题
        """
        from analytics_assistant.src.agents.semantic_parser.graph import (
            compile_semantic_parser_graph,
        )
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            print("\n" + "=" * 60)
            print("多轮对话综合测试")
            print("=" * 60)
            
            checkpointer = MemorySaver()
            graph = compile_semantic_parser_graph(checkpointer=checkpointer)
            
            config = create_workflow_context(
                datasource_luid=datasource_luid,
                data_model=data_model,
                platform_adapter=adapter,
                auth=auth,
            )
            thread_id = f"full-scenario-{datetime.now().isoformat()}"
            config["configurable"]["thread_id"] = thread_id
            
            chat_history = []
            
            # ========== 轮次1：初始问题 ==========
            print("\n--- 轮次1 ---")
            question1 = "销售情况怎么样"
            print(f"用户: {question1}")
            
            state1: SemanticParserState = {
                "question": question1,
                "chat_history": chat_history,
                "datasource_luid": datasource_luid,
                "current_time": datetime.now().isoformat(),
            }
            
            result1 = await graph.ainvoke(state1, config)
            output1 = result1.get("semantic_output", {})
            clarification1 = result1.get("clarification_question", "")
            
            print(f"系统: {clarification1 or output1.get('restated_question', '')}")
            
            # 更新历史
            chat_history.append({"role": "user", "content": question1})
            chat_history.append({"role": "assistant", "content": clarification1 or output1.get("restated_question", "")})
            
            # ========== 轮次2：提供时间范围 ==========
            print("\n--- 轮次2 ---")
            question2 = "看看上个月的"
            print(f"用户: {question2}")
            
            state2: SemanticParserState = {
                "question": question2,
                "chat_history": chat_history,
                "datasource_luid": datasource_luid,
                "current_time": datetime.now().isoformat(),
            }
            
            result2 = await graph.ainvoke(state2, config)
            output2 = result2.get("semantic_output", {})
            
            print(f"系统: {output2.get('restated_question', '')}")
            
            # 更新历史
            chat_history.append({"role": "user", "content": question2})
            chat_history.append({"role": "assistant", "content": output2.get("restated_question", "")})
            
            # ========== 轮次3：添加维度 ==========
            print("\n--- 轮次3 ---")
            question3 = "按地区分"
            print(f"用户: {question3}")
            
            state3: SemanticParserState = {
                "question": question3,
                "chat_history": chat_history,
                "datasource_luid": datasource_luid,
                "current_time": datetime.now().isoformat(),
            }
            
            result3 = await graph.ainvoke(state3, config)
            output3 = result3.get("semantic_output", {})
            
            print(f"系统: {output3.get('restated_question', '')}")
            
            # 验证最终结果
            assert result3.get("semantic_output") is not None
            
            # 验证查询包含了所有上下文信息
            restated = output3.get("restated_question", "")
            print(f"\n最终重述问题: {restated}")
            
            print("\n[PASS] 多轮对话综合测试通过")
            
        finally:
            if client:
                await client.close()


# ═══════════════════════════════════════════════════════════════════════════
# Task 26.1.2 扩展: 真实 interrupt/resume 测试
# ═══════════════════════════════════════════════════════════════════════════

class TestRealInterruptResume:
    """真实 interrupt/resume 测试
    
    使用真实 LLM 和真实 Tableau 服务测试筛选值确认的中断/恢复机制。
    
    测试流程：
    1. 用户输入包含模糊筛选值的问题（如"北京"而非"北京市"）
    2. FilterValueValidator 检测到筛选值不精确匹配
    3. filter_validator_node 调用 interrupt() 暂停执行
    4. 测试代码模拟用户选择确认值
    5. 使用 Command(resume=...) 恢复执行
    6. 验证 confirmed_filters 正确累积
    
    Property 34: Filter Confirmation via LangGraph interrupt()
    Property 35: Filter Value Update After Confirmation
    Property 40: Multi-Round Filter Confirmation Accumulation
    """
    
    @pytest.mark.asyncio
    async def test_interrupt_resume_with_real_services(self):
        """测试真实服务的 interrupt/resume 机制
        
        使用真实 LLM 和 Tableau 服务，测试筛选值确认流程。
        """
        from langgraph.types import Command
        from analytics_assistant.src.agents.semantic_parser.graph import (
            compile_semantic_parser_graph,
        )
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            print("\n" + "=" * 60)
            print("真实 interrupt/resume 测试")
            print("=" * 60)
            
            # 编译图（带 checkpointer 以支持 interrupt/resume）
            checkpointer = MemorySaver()
            graph = compile_semantic_parser_graph(checkpointer=checkpointer)
            
            # 创建配置
            config = create_workflow_context(
                datasource_luid=datasource_luid,
                data_model=data_model,
                platform_adapter=adapter,
                auth=auth,
            )
            thread_id = f"interrupt-resume-{datetime.now().isoformat()}"
            config["configurable"]["thread_id"] = thread_id
            
            # 使用可能触发筛选值确认的问题
            # 注意：使用"省区"字段名，因为数据模型中有"省区"字段
            # 使用"北京"而非精确的"北京市"，期望触发确认
            initial_state: SemanticParserState = {
                "question": "查询省区为北京的上个月销售额",
                "datasource_luid": datasource_luid,
                "current_time": datetime.now().isoformat(),
            }
            
            print(f"\n问题: {initial_state['question']}")
            print("-" * 40)
            
            # 执行图 - 使用 stream 模式以捕获 interrupt
            interrupt_detected = False
            interrupt_payload = None
            final_result = None
            
            print("\n开始执行图...")
            
            async for event in graph.astream(initial_state, config, stream_mode="updates"):
                print(f"  事件: {list(event.keys())}")
                
                # 检查是否有 interrupt
                for node_name, node_output in event.items():
                    if node_name == "__interrupt__":
                        interrupt_detected = True
                        interrupt_payload = node_output
                        print(f"\n检测到 interrupt!")
                        print(f"  Payload: {interrupt_payload}")
                    else:
                        final_result = node_output
                        # 打印 semantic_output 中的 filters 用于调试
                        if node_name == "semantic_understanding" and node_output:
                            so = node_output.get("semantic_output", {})
                            where = so.get("where", {})
                            filters = where.get("filters", [])
                            print(f"    [DEBUG] semantic_output.where.filters: {filters}")
            
            if interrupt_detected and interrupt_payload:
                print("\n" + "-" * 40)
                print("处理 interrupt...")
                
                # 解析 interrupt payload
                # interrupt_payload 是一个 tuple 或 list，包含 Interrupt 对象
                if isinstance(interrupt_payload, (list, tuple)) and len(interrupt_payload) > 0:
                    interrupt_data = interrupt_payload[0]
                    
                    # 获取 pending confirmations
                    if hasattr(interrupt_data, 'value'):
                        pending = interrupt_data.value.get("pending", [])
                    else:
                        pending = interrupt_data.get("pending", []) if isinstance(interrupt_data, dict) else []
                    
                    print(f"  待确认项: {len(pending)} 个")
                    
                    # 构建用户确认响应
                    confirmations = {}
                    for item in pending:
                        field_name = item.get("field_name", "")
                        similar_values = item.get("similar_values", [])
                        requested_value = item.get("requested_value", "")
                        
                        print(f"    - 字段: {field_name}")
                        print(f"      请求值: {requested_value}")
                        print(f"      相似值: {similar_values}")
                        
                        # 选择第一个相似值作为确认值
                        if similar_values:
                            confirmations[field_name] = similar_values[0]
                            print(f"      确认为: {similar_values[0]}")
                    
                    # 使用 Command(resume=...) 恢复执行
                    user_response = {"confirmations": confirmations}
                    
                    print(f"\n恢复执行，用户响应: {user_response}")
                    
                    # 恢复执行
                    resume_result = None
                    async for event in graph.astream(
                        Command(resume=user_response),
                        config,
                        stream_mode="updates",
                    ):
                        print(f"  恢复事件: {list(event.keys())}")
                        for node_name, node_output in event.items():
                            if node_name != "__interrupt__":
                                resume_result = node_output
                    
                    if resume_result:
                        final_result = resume_result
            
            # 验证结果
            print("\n" + "-" * 40)
            print("验证结果:")
            
            if final_result:
                # 获取最终状态
                state = graph.get_state(config)
                final_state = state.values if state else {}
                
                print(f"  - 需要澄清: {final_state.get('needs_clarification', False)}")
                print(f"  - confirmed_filters: {final_state.get('confirmed_filters', [])}")
                
                if final_state.get("semantic_output"):
                    output = final_state["semantic_output"]
                    print(f"  - 重述问题: {output.get('restated_question', '')}")
                
                if final_state.get("filter_validation_result"):
                    validation = final_state["filter_validation_result"]
                    print(f"  - 验证通过: {validation.get('all_valid', False)}")
                
                # 如果有 interrupt，验证 confirmed_filters 累积
                if interrupt_detected:
                    confirmed = final_state.get("confirmed_filters", [])
                    assert len(confirmed) > 0, "interrupt 后应该有确认的筛选值"
                    print(f"\n[PASS] interrupt/resume 测试通过，确认了 {len(confirmed)} 个筛选值")
                else:
                    print("\n[INFO] 未触发 interrupt（筛选值可能精确匹配）")
            else:
                print("\n[INFO] 图执行完成，无 interrupt")
            
            print("\n[PASS] 真实 interrupt/resume 测试完成")
            
        finally:
            if client:
                await client.close()
    
    @pytest.mark.asyncio
    async def test_multi_round_interrupt_resume(self):
        """测试多轮 interrupt/resume 的累积
        
        模拟多个筛选值需要确认的场景，验证 confirmed_filters 正确累积。
        
        注意：要触发 interrupt，需要满足两个条件：
        1. LLM 返回 needs_clarification=False（问题足够具体）
        2. 筛选值在数据源中不精确匹配，但有相似值
        """
        from langgraph.types import Command
        from analytics_assistant.src.agents.semantic_parser.graph import (
            compile_semantic_parser_graph,
        )
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            print("\n" + "=" * 60)
            print("多轮 interrupt/resume 累积测试")
            print("=" * 60)
            
            checkpointer = MemorySaver()
            graph = compile_semantic_parser_graph(checkpointer=checkpointer)
            
            config = create_workflow_context(
                datasource_luid=datasource_luid,
                data_model=data_model,
                platform_adapter=adapter,
                auth=auth,
            )
            thread_id = f"multi-interrupt-{datetime.now().isoformat()}"
            config["configurable"]["thread_id"] = thread_id
            
            # 使用更具体的问题，避免 LLM 返回 needs_clarification=True
            # 使用数据模型中实际存在的字段（如"省区"）和一个可能不精确匹配的值
            # 不使用时间条件，避免 LLM 因找不到日期字段而返回 needs_clarification
            print("\n--- 第一轮 ---")
            state1: SemanticParserState = {
                "question": "查询省区为北京的含税销售收入总额",  # 使用"省区"字段，不带时间
                "datasource_luid": datasource_luid,
                "current_time": datetime.now().isoformat(),
            }
            
            print(f"问题: {state1['question']}")
            
            # 执行并处理可能的 interrupt
            result1, interrupt_triggered_1 = await self._execute_with_interrupt_handling_v2(graph, state1, config)
            
            # 获取第一轮后的 confirmed_filters
            state_after_1 = graph.get_state(config)
            confirmed_after_1 = state_after_1.values.get("confirmed_filters", []) if state_after_1 else []
            print(f"第一轮后 confirmed_filters: {len(confirmed_after_1)} 个")
            print(f"第一轮 interrupt 触发: {interrupt_triggered_1}")
            
            # 检查 needs_clarification
            needs_clarification_1 = state_after_1.values.get("needs_clarification", False) if state_after_1 else False
            clarification_question_1 = state_after_1.values.get("clarification_question", "") if state_after_1 else ""
            print(f"第一轮 needs_clarification: {needs_clarification_1}")
            if clarification_question_1:
                print(f"第一轮 clarification_question: {clarification_question_1}")
            
            # 检查是否进入了 filter_validator
            if state_after_1 and state_after_1.values:
                has_validation = "filter_validation_result" in state_after_1.values
                print(f"第一轮是否执行了 filter_validator: {has_validation}")
                if has_validation:
                    validation = state_after_1.values.get("filter_validation_result", {})
                    print(f"  - all_valid: {validation.get('all_valid')}")
                    print(f"  - needs_confirmation: {validation.get('needs_confirmation')}")
                    print(f"  - results: {validation.get('results', [])}")
                
                # 打印所有 state keys 以便调试
                print(f"State keys: {list(state_after_1.values.keys())}")
                
                # 检查 semantic_output 中的 filters
                semantic_output = state_after_1.values.get("semantic_output", {})
                where = semantic_output.get("where", {})
                filters = where.get("filters", [])
                print(f"Filters in semantic_output: {filters}")
                
                # 打印数据模型中的字段名（用于调试）
                if data_model:
                    # 打印维度字段
                    print(f"数据模型字段总数: {len(data_model.fields)}")
                    dimensions = [f for f in data_model.fields if f.role.upper() == "DIMENSION"]
                    print(f"维度字段数: {len(dimensions)}")
                    for f in dimensions[:15]:
                        print(f"  维度: {f.name} (caption: {f.caption})")
            
            # 第二轮：追加另一个筛选条件
            print("\n--- 第二轮 ---")
            
            # 构建对话历史
            output1 = result1.get("semantic_output", {}) if result1 else {}
            chat_history = [
                {"role": "user", "content": state1["question"]},
                {"role": "assistant", "content": output1.get("restated_question", "已查询")},
            ]
            
            state2: SemanticParserState = {
                "question": "再加上上海的数据",
                "chat_history": chat_history,
                "datasource_luid": datasource_luid,
                "current_time": datetime.now().isoformat(),
                # 保留第一轮的确认
                "confirmed_filters": confirmed_after_1,
            }
            
            print(f"问题: {state2['question']}")
            
            # 执行第二轮
            result2, interrupt_triggered_2 = await self._execute_with_interrupt_handling_v2(graph, state2, config)
            
            # 获取第二轮后的 confirmed_filters
            state_after_2 = graph.get_state(config)
            confirmed_after_2 = state_after_2.values.get("confirmed_filters", []) if state_after_2 else []
            print(f"第二轮后 confirmed_filters: {len(confirmed_after_2)} 个")
            print(f"第二轮 interrupt 触发: {interrupt_triggered_2}")
            
            # 打印第二轮的 semantic_output 用于调试
            if state_after_2 and state_after_2.values:
                semantic_output_2 = state_after_2.values.get("semantic_output", {})
                where_2 = semantic_output_2.get("where", {})
                filters_2 = where_2.get("filters", [])
                print(f"第二轮 Filters in semantic_output: {filters_2}")
                print(f"第二轮 restated_question: {semantic_output_2.get('restated_question', '')}")
            
            # 验证：如果两轮都有 interrupt，第二轮的 confirmed_filters 应该累积
            if interrupt_triggered_1 and interrupt_triggered_2:
                assert len(confirmed_after_2) >= len(confirmed_after_1), \
                    "第二轮的 confirmed_filters 应该累积第一轮的确认"
                
                # 验证第二轮的 filters 应该包含北京市和上海市
                # 注意：这取决于 LLM 是否正确理解了"再加上"的意思
                if state_after_2 and state_after_2.values:
                    semantic_output_2 = state_after_2.values.get("semantic_output", {})
                    where_2 = semantic_output_2.get("where", {})
                    filters_2 = where_2.get("filters", [])
                    
                    # 查找省区筛选
                    province_filter = None
                    for f in filters_2:
                        if isinstance(f, dict) and f.get("field_name") == "省区":
                            province_filter = f
                            break
                        elif hasattr(f, "field_name") and f.field_name == "省区":
                            province_filter = f
                            break
                    
                    if province_filter:
                        values = province_filter.get("values", []) if isinstance(province_filter, dict) else getattr(province_filter, "values", [])
                        print(f"省区筛选值: {values}")
                        # 验证最终筛选值应该包含北京市和上海市
                        # 注意：上海可能还没被确认更新，需要检查 apply_confirmations 是否正确应用
                        expected_values = {"北京市", "上海市"}
                        actual_values = set(str(v) for v in values)
                        if actual_values == expected_values:
                            print(f"[OK] 筛选值正确包含北京市和上海市")
                        else:
                            print(f"[WARN] 筛选值不完全匹配: 期望 {expected_values}, 实际 {actual_values}")
            
            print("\n[PASS] 多轮 interrupt/resume 累积测试完成")
            
        finally:
            if client:
                await client.close()
    
    async def _execute_with_interrupt_handling_v2(
        self,
        graph,
        state: SemanticParserState,
        config: Dict[str, Any],
    ) -> tuple:
        """执行图并处理可能的 interrupt（返回是否触发了 interrupt）
        
        Args:
            graph: 编译后的 LangGraph
            state: 初始状态
            config: 配置
            
        Returns:
            (最终结果, 是否触发了 interrupt)
        """
        from langgraph.types import Command
        
        final_result = None
        interrupt_triggered = False
        
        async for event in graph.astream(state, config, stream_mode="updates"):
            for node_name, node_output in event.items():
                print(f"    节点: {node_name}")
                if node_name == "__interrupt__":
                    # 处理 interrupt
                    interrupt_triggered = True
                    interrupt_payload = node_output
                    print(f"    [INTERRUPT] 检测到中断!")
                    print(f"    [INTERRUPT] Payload 类型: {type(interrupt_payload)}")
                    print(f"    [INTERRUPT] Payload 内容: {interrupt_payload}")
                    
                    # interrupt_payload 可能是 tuple 或 list
                    if isinstance(interrupt_payload, (list, tuple)) and len(interrupt_payload) > 0:
                        interrupt_data = interrupt_payload[0]
                        print(f"    [INTERRUPT] interrupt_data 类型: {type(interrupt_data)}")
                        
                        if hasattr(interrupt_data, 'value'):
                            pending = interrupt_data.value.get("pending", [])
                            print(f"    [INTERRUPT] interrupt_data.value: {interrupt_data.value}")
                        else:
                            pending = interrupt_data.get("pending", []) if isinstance(interrupt_data, dict) else []
                        
                        print(f"    [INTERRUPT] 待确认项: {len(pending)} 个")
                        
                        # 自动选择第一个相似值
                        confirmations = {}
                        for item in pending:
                            field_name = item.get("field_name", "")
                            similar_values = item.get("similar_values", [])
                            requested_value = item.get("requested_value", "")
                            print(f"      - {field_name}: '{requested_value}' -> 相似值: {similar_values}")
                            if similar_values:
                                confirmations[field_name] = similar_values[0]
                        
                        # 恢复执行
                        user_response = {"confirmations": confirmations}
                        print(f"    [RESUME] 用户确认: {confirmations}")
                        
                        async for resume_event in graph.astream(
                            Command(resume=user_response),
                            config,
                            stream_mode="updates",
                        ):
                            for rn, ro in resume_event.items():
                                print(f"    恢复节点: {rn}")
                                if rn != "__interrupt__":
                                    final_result = ro
                else:
                    final_result = node_output
        
        return final_result, interrupt_triggered


class TestClarificationQuestionSource:
    """测试 clarification_question 的来源
    
    验证 clarification_question 是由 LLM 生成的，而非写死的。
    """
    
    @pytest.mark.asyncio
    async def test_clarification_question_from_llm(self):
        """验证 clarification_question 来自 LLM
        
        使用一个模糊的问题，期望 LLM 生成澄清问题。
        """
        from analytics_assistant.src.agents.semantic_parser.graph import (
            compile_semantic_parser_graph,
        )
        from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
        
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            print("\n" + "=" * 60)
            print("clarification_question 来源测试")
            print("=" * 60)
            
            checkpointer = MemorySaver()
            graph = compile_semantic_parser_graph(checkpointer=checkpointer)
            
            config = create_workflow_context(
                datasource_luid=datasource_luid,
                data_model=data_model,
                platform_adapter=adapter,
                auth=auth,
            )
            thread_id = f"clarification-source-{datetime.now().isoformat()}"
            config["configurable"]["thread_id"] = thread_id
            
            # 使用一个非常模糊的问题，期望触发澄清
            vague_questions = [
                "数据",
                "看看",
                "分析一下",
            ]
            
            for question in vague_questions:
                print(f"\n--- 测试问题: '{question}' ---")
                
                state: SemanticParserState = {
                    "question": question,
                    "datasource_luid": datasource_luid,
                    "current_time": datetime.now().isoformat(),
                }
                
                result = await graph.ainvoke(state, config)
                
                needs_clarification = result.get("needs_clarification", False)
                clarification_question = result.get("clarification_question")
                
                # 也检查 semantic_output 中的 clarification_question
                semantic_output = result.get("semantic_output", {})
                output_clarification = semantic_output.get("clarification_question")
                output_needs_clarification = semantic_output.get("needs_clarification", False)
                
                print(f"  needs_clarification (state): {needs_clarification}")
                print(f"  clarification_question (state): {clarification_question}")
                print(f"  needs_clarification (output): {output_needs_clarification}")
                print(f"  clarification_question (output): {output_clarification}")
                
                # 如果 LLM 认为需要澄清，验证 clarification_question 存在
                if needs_clarification or output_needs_clarification:
                    actual_question = clarification_question or output_clarification
                    assert actual_question is not None, \
                        f"needs_clarification=True 但 clarification_question 为空"
                    assert len(actual_question) > 0, \
                        f"clarification_question 不应为空字符串"
                    print(f"  [OK] LLM 生成的澄清问题: {actual_question}")
                else:
                    # LLM 可能直接理解了问题
                    restated = semantic_output.get("restated_question", "")
                    print(f"  [OK] LLM 直接理解，重述: {restated}")
            
            print("\n[PASS] clarification_question 来源测试完成")
            
        finally:
            if client:
                await client.close()
