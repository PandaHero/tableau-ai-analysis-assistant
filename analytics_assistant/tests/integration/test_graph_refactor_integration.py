# -*- coding: utf-8 -*-
"""
Graph 依赖方向重构 - 集成测试

使用真实 LLM 和真实环境验证重构后的 graph.py 能正常工作。

测试内容：
1. 图编译：create_semantic_parser_graph / compile_semantic_parser_graph 正常工作
2. 意图路由：intent_router_node 使用真实规则引擎正确分类
3. WorkflowContext 集成：通过 agents/base/context.py 的 get_context 正确获取上下文
4. 端到端流程：从 intent_router 到 semantic_understanding 的完整流程（真实 LLM）

注意：
- 集成测试禁止 Mock（Rule 6.1）
- 使用真实 LLM（DeepSeek R1）和真实 Embedding（Zhipu）
"""

import logging
import os
import sys
import pytest
from datetime import datetime
from typing import Any, Dict, List, Optional

# 确保项目根目录在 sys.path 中
project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 测试 1: 图编译测试（不需要 LLM）
# ═══════════════════════════════════════════════════════════════════════════


class TestGraphCompilation:
    """验证重构后的图能正常编译。"""

    def test_create_semantic_parser_graph(self) -> None:
        """create_semantic_parser_graph 应返回有效的 StateGraph。"""
        from analytics_assistant.src.agents.semantic_parser.graph import (
            create_semantic_parser_graph,
        )
        from langgraph.graph import StateGraph

        graph = create_semantic_parser_graph()
        assert isinstance(graph, StateGraph)

    def test_compile_semantic_parser_graph(self) -> None:
        """compile_semantic_parser_graph 应返回可执行的编译图。"""
        from analytics_assistant.src.agents.semantic_parser.graph import (
            compile_semantic_parser_graph,
        )

        compiled = compile_semantic_parser_graph()
        assert compiled is not None
        assert hasattr(compiled, "ainvoke") or hasattr(compiled, "invoke")

    def test_graph_has_expected_nodes(self) -> None:
        """图应包含所有预期的节点。"""
        from analytics_assistant.src.agents.semantic_parser.graph import (
            create_semantic_parser_graph,
        )

        graph = create_semantic_parser_graph()
        node_names = set(graph.nodes.keys())

        expected_nodes = {
            "intent_router",
            "query_cache",
            "rule_prefilter",
            "feature_cache",
            "feature_extractor",
            "field_retriever",
            "dynamic_schema_builder",
            "modular_prompt_builder",
            "few_shot_manager",
            "semantic_understanding",
            "output_validator",
            "filter_validator",
            "query_adapter",
            "error_corrector",
            "feedback_learner",
        }

        for node in expected_nodes:
            assert node in node_names, f"缺少节点: {node}"

    def test_graph_import_uses_agents_base_context(self) -> None:
        """graph.py 应从 agents/base/context 导入，而非 orchestration。"""
        import ast

        graph_path = os.path.join(
            project_root, "src", "agents", "semantic_parser", "graph.py"
        )
        with open(graph_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=graph_path)

        imports: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

        has_agents_base = any("agents.base.context" in imp for imp in imports)
        assert has_agents_base, "graph.py 应从 agents.base.context 导入"

        has_orchestration = any("orchestration" in imp for imp in imports)
        assert not has_orchestration, "graph.py 不应包含 orchestration 导入"


# ═══════════════════════════════════════════════════════════════════════════
# 测试 2: 意图路由集成测试（不需要 LLM，使用规则引擎）
# ═══════════════════════════════════════════════════════════════════════════


class TestIntentRouterIntegration:
    """验证意图路由节点在真实环境下正常工作。"""

    @pytest.mark.asyncio
    async def test_data_query_intent(self) -> None:
        """数据查询问题应被识别为 data_query 意图。"""
        from analytics_assistant.src.agents.semantic_parser.graph import (
            intent_router_node,
        )

        state = {"question": "上个月各地区的销售额是多少"}
        result = await intent_router_node(state)

        assert "intent_router_output" in result
        output = result["intent_router_output"]
        assert output["intent_type"] == "data_query"
        assert output["confidence"] > 0

    @pytest.mark.asyncio
    async def test_irrelevant_intent(self) -> None:
        """无关问题应被识别为非 data_query 意图。"""
        from analytics_assistant.src.agents.semantic_parser.graph import (
            intent_router_node,
        )

        state = {"question": "今天天气怎么样"}
        result = await intent_router_node(state)

        assert "intent_router_output" in result
        output = result["intent_router_output"]
        assert output["intent_type"] in ("irrelevant", "general", "clarification")

    @pytest.mark.asyncio
    async def test_empty_question(self) -> None:
        """空问题应返回 irrelevant 意图。"""
        from analytics_assistant.src.agents.semantic_parser.graph import (
            intent_router_node,
        )

        state = {"question": ""}
        result = await intent_router_node(state)

        assert "intent_router_output" in result
        output = result["intent_router_output"]
        assert output["intent_type"] == "irrelevant"


# ═══════════════════════════════════════════════════════════════════════════
# 测试 3: WorkflowContext 集成测试
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkflowContextIntegration:
    """验证 WorkflowContext 通过 agents/base/context.py 正确传递。"""

    def test_workflow_context_satisfies_protocol(self) -> None:
        """真实的 WorkflowContext 应满足 WorkflowContextProtocol。"""
        from analytics_assistant.src.core.interfaces import WorkflowContextProtocol
        from analytics_assistant.src.orchestration.workflow.context import (
            WorkflowContext,
        )

        ctx = WorkflowContext(datasource_luid="test-ds-001")
        assert isinstance(ctx, WorkflowContextProtocol)

    def test_get_context_from_config(self) -> None:
        """get_context 应能从 config 中提取 WorkflowContext。"""
        from analytics_assistant.src.agents.base.context import get_context
        from analytics_assistant.src.orchestration.workflow.context import (
            WorkflowContext,
            create_workflow_config,
        )

        ctx = WorkflowContext(datasource_luid="test-ds-002")
        config = create_workflow_config(thread_id="test-thread", context=ctx)

        extracted = get_context(config)
        assert extracted is ctx
        assert extracted.datasource_luid == "test-ds-002"

    @pytest.mark.asyncio
    async def test_query_cache_node_with_context(self) -> None:
        """query_cache_node 应能通过 config 获取 WorkflowContext。"""
        from analytics_assistant.src.agents.semantic_parser.graph import (
            query_cache_node,
        )
        from analytics_assistant.src.orchestration.workflow.context import (
            WorkflowContext,
            create_workflow_config,
        )

        ctx = WorkflowContext(datasource_luid="test-ds-003")
        config = create_workflow_config(thread_id="test-thread", context=ctx)

        state = {
            "question": "测试查询",
            "datasource_luid": "test-ds-003",
        }

        result = await query_cache_node(state, config)
        assert "cache_hit" in result
        assert result["cache_hit"] is False


# ═══════════════════════════════════════════════════════════════════════════
# 测试 4: 端到端流程测试（使用真实 LLM）
# ═══════════════════════════════════════════════════════════════════════════


class TestEndToEndWithRealLLM:
    """端到端集成测试，使用真实 LLM 验证重构后的图能正常运行。

    这些测试需要真实的 LLM API 连接（DeepSeek R1）。
    如果 API 不可用，测试会被跳过。
    """

    @pytest.fixture(autouse=True)
    def check_llm_available(self) -> None:
        """检查 LLM API 是否可用（通过 app.yaml 配置）。"""
        from analytics_assistant.src.infra.config import get_config

        config = get_config()
        ai_config = config.get("ai", {})
        llm_models = ai_config.get("llm_models", [])
        has_api_key = any(
            m.get("api_key") for m in llm_models if isinstance(m, dict)
        )
        assert has_api_key, (
            "LLM API Key 未配置，请在 config/app.yaml 的 ai.llm_models 中设置 api_key"
        )

    @pytest.mark.asyncio
    async def test_intent_router_to_rule_prefilter(self) -> None:
        """验证从意图路由到规则预处理的流程。

        流程：intent_router → query_cache → rule_prefilter
        """
        from analytics_assistant.src.agents.semantic_parser.graph import (
            intent_router_node,
            query_cache_node,
            rule_prefilter_node,
        )
        from analytics_assistant.src.orchestration.workflow.context import (
            WorkflowContext,
            create_workflow_config,
        )

        ctx = WorkflowContext(
            datasource_luid="test-e2e-ds",
            current_time=datetime.now().isoformat(),
        )
        config = create_workflow_config(thread_id="test-e2e", context=ctx)

        # 阶段 1: 意图路由
        state: Dict[str, Any] = {
            "question": "上个月各地区的销售额",
            "datasource_luid": "test-e2e-ds",
            "current_time": datetime.now().isoformat(),
        }
        intent_result = await intent_router_node(state)
        state.update(intent_result)
        assert state["intent_router_output"]["intent_type"] == "data_query"

        # 阶段 2: 查询缓存
        cache_result = await query_cache_node(state, config)
        state.update(cache_result)
        assert state["cache_hit"] is False

        # 阶段 3: 规则预处理
        prefilter_result = await rule_prefilter_node(state)
        state.update(prefilter_result)

        assert "prefilter_result" in state
        prefilter = state["prefilter_result"]
        # 应检测到时间提示（"上个月"）
        assert len(prefilter.get("time_hints", [])) > 0
        logger.info(
            f"规则预处理结果: time_hints={prefilter.get('time_hints')}, "
            f"match_confidence={prefilter.get('match_confidence')}"
        )

    @pytest.mark.asyncio
    async def test_semantic_understanding_with_real_llm(self) -> None:
        """验证语义理解节点使用真实 LLM 能正常工作。

        这是最关键的测试：验证重构后 graph.py 中的
        semantic_understanding_node 能通过 agents/base/context.py
        正确获取上下文并调用真实 LLM。
        """
        from analytics_assistant.src.agents.semantic_parser.graph import (
            semantic_understanding_node,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            SemanticOutput,
        )

        # 构建最小化 state，使用降级模式（不使用 modular_prompt）
        state: Dict[str, Any] = {
            "question": "各地区的销售额",
            "field_candidates": [
                {
                    "field_name": "Region",
                    "field_caption": "地区",
                    "field_type": "dimension",
                    "data_type": "string",
                    "description": "销售地区",
                    "confidence": 0.9,
                },
                {
                    "field_name": "Sales",
                    "field_caption": "销售额",
                    "field_type": "measure",
                    "data_type": "real",
                    "description": "销售金额",
                    "confidence": 0.95,
                },
            ],
            "few_shot_examples": [],
            "current_time": datetime.now().isoformat(),
        }

        result = await semantic_understanding_node(state)

        assert "semantic_output" in result
        semantic_output = result["semantic_output"]
        assert "query_id" in semantic_output
        assert "restated_question" in semantic_output

        parsed = SemanticOutput.model_validate(semantic_output)
        assert parsed.query_id is not None

        logger.info(
            f"语义理解结果: query_id={parsed.query_id}, "
            f"restated={parsed.restated_question}, "
            f"needs_clarification={parsed.needs_clarification}"
        )

    @pytest.mark.asyncio
    async def test_compiled_graph_irrelevant_query(self) -> None:
        """验证编译后的图对无关问题能正确终止。

        使用编译后的图执行，验证整个图的连接正确性。
        无关问题应在 intent_router 后直接到 END。
        """
        from analytics_assistant.src.agents.semantic_parser.graph import (
            compile_semantic_parser_graph,
        )
        from analytics_assistant.src.orchestration.workflow.context import (
            WorkflowContext,
            create_workflow_config,
        )
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()
        compiled = compile_semantic_parser_graph(checkpointer=checkpointer)

        ctx = WorkflowContext(
            datasource_luid="test-compiled-ds",
            current_time=datetime.now().isoformat(),
        )
        config = create_workflow_config(thread_id="test-compiled", context=ctx)

        initial_state: Dict[str, Any] = {
            "question": "今天天气怎么样",
            "datasource_luid": "test-compiled-ds",
            "current_time": datetime.now().isoformat(),
        }

        final_state = await compiled.ainvoke(initial_state, config)

        assert "intent_router_output" in final_state
        intent_output = final_state["intent_router_output"]
        assert intent_output["intent_type"] in (
            "irrelevant",
            "general",
            "clarification",
        )

        logger.info(
            f"编译图执行结果: intent_type={intent_output['intent_type']}, "
            f"confidence={intent_output['confidence']}"
        )
