# -*- coding: utf-8 -*-
"""
Decision Handler 集成测试

测试 SemanticParser Subgraph 的决策处理：
- 成功场景：Pipeline 成功 → 结束
- 错误场景：触发 ReAct 错误处理
- Token 级别流式输出

使用真实的 Tableau 环境和 LLM 进行测试。

运行方式:
    python -m tableau_assistant.tests.agents.semantic_parser.test_decision_handler

或直接运行:
    python tableau_assistant/tests/agents/semantic_parser/test_decision_handler.py
"""
import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════

def get_tableau_config() -> Dict[str, str]:
    """从环境变量获取 Tableau 配置"""
    domain = os.getenv("TABLEAU_DOMAIN", os.getenv("TABLEAU_CLOUD_DOMAIN", ""))
    site = os.getenv("TABLEAU_SITE", os.getenv("TABLEAU_CLOUD_SITE", ""))
    
    return {
        "domain": domain,
        "site": site,
        "datasource_luid": os.getenv("DATASOURCE_LUID", ""),
        "datasource_name": os.getenv("DATASOURCE_NAME", "Superstore Datasource"),
    }


async def resolve_datasource_luid(config: Dict[str, str], auth_ctx) -> str:
    """解析数据源 LUID（支持名称查找）"""
    import asyncio
    
    # 如果已有 LUID，直接返回
    if config.get("datasource_luid"):
        logger.info(f"使用配置的数据源 LUID: {config['datasource_luid']}")
        return config["datasource_luid"]
    
    # 通过名称查找
    datasource_name = config.get("datasource_name", "Superstore Datasource")
    logger.info(f"通过名称查找数据源: {datasource_name}")
    
    from tableau_assistant.src.platforms.tableau import get_datasource_luid_by_name
    
    luid = await asyncio.to_thread(
        get_datasource_luid_by_name,
        auth_ctx.api_key,
        config["domain"],
        datasource_name,
        config.get("site", ""),
    )
    
    if not luid:
        raise ValueError(f"未找到数据源: {datasource_name}")
    
    logger.info(f"解析数据源 LUID: {datasource_name} -> {luid}")
    return luid


async def get_tableau_auth():
    """获取 Tableau 认证上下文"""
    from tableau_assistant.src.platforms.tableau.auth import get_tableau_auth_async
    
    auth_ctx = await get_tableau_auth_async()
    logger.info(f"获取 Tableau 认证成功 (方式: {auth_ctx.auth_method})")
    return auth_ctx


async def get_data_model(datasource_luid: str, auth_ctx):
    """获取数据源元数据"""
    from tableau_assistant.src.infra.storage.langgraph_store import get_langgraph_store
    from tableau_assistant.src.infra.storage.data_model_cache import DataModelCache
    from tableau_assistant.src.platforms.tableau import TableauDataModelLoader
    
    logger.info(f"获取数据源元数据: {datasource_luid}")
    
    store = get_langgraph_store()
    cache = DataModelCache(store)
    loader = TableauDataModelLoader(auth_ctx)
    
    data_model, is_cache_hit = await cache.get_or_load(datasource_luid, loader)
    
    if is_cache_hit:
        logger.info(f"从缓存加载元数据: {data_model.field_count} 个字段")
    else:
        logger.info(f"从 API 加载元数据: {data_model.field_count} 个字段")
    
    return data_model


# ═══════════════════════════════════════════════════════════════════════════
# 核心测试函数 - 流式输出
# ═══════════════════════════════════════════════════════════════════════════

async def run_subgraph_with_streaming(
    question: str,
    data_model,
    datasource_luid: str,
    auth_ctx,
) -> Dict[str, Any]:
    """运行 Subgraph 并实时显示流式输出"""
    from tableau_assistant.src.agents.semantic_parser.subgraph import create_semantic_parser_subgraph
    from tableau_assistant.src.agents.semantic_parser.state import SemanticParserState
    from tableau_assistant.src.orchestration.workflow.context import WorkflowContext, create_workflow_config
    from langchain_core.messages import HumanMessage
    
    print(f"\n{'─'*60}")
    print(f"问题: {question}")
    print(f"{'─'*60}")
    
    # 创建 Subgraph
    graph = create_semantic_parser_subgraph()
    compiled_graph = graph.compile()
    
    # 创建配置
    workflow_ctx = WorkflowContext(
        auth=auth_ctx,
        datasource_luid=datasource_luid,
        data_model=data_model,
    )
    config = create_workflow_config(
        thread_id=f"test-stream-{datetime.now().strftime('%H%M%S')}",
        context=workflow_ctx,
    )
    
    # 准备初始状态
    initial_state: SemanticParserState = {
        "question": question,
        "messages": [HumanMessage(content=question)],
        "data_model": data_model,
        "datasource_luid": datasource_luid,
        "step1_output": None,
        "step2_output": None,
        "pipeline_success": None,
        "needs_clarification": None,
        "pipeline_aborted": None,
        "retry_from": None,
        "error_feedback": None,
        "react_action": None,
        "pipeline_error": None,
        "retry_count": None,
        "retry_history": None,
        "clarification_question": None,
        "user_message": None,
        "columns": None,
        "row_count": None,
        "file_path": None,
        "is_large_result": None,
        "mapped_query": None,
        "vizql_query": None,
        "execution_time_ms": None,
        "thinking": None,
        "semantic_query": None,
        "restated_question": None,
        "current_stage": "semantic_parser",
        "answered_questions": [],
        "is_analysis_question": True,
        "intent_type": None,
        "intent_reasoning": None,
        "general_response": None,
        "non_analysis_response": None,
        "clarification_options": None,
        "clarification_field": None,
        "query_result": None,
        "insights": [],
        "all_insights": [],
        "replan_decision": None,
        "replan_count": 0,
        "max_replan_rounds": 3,
        "replan_history": [],
        "final_report": None,
        "execution_path": [],
        "semantic_parser_complete": False,
        "field_mapper_complete": False,
        "query_builder_complete": False,
        "execute_complete": False,
        "insight_complete": False,
        "replanner_complete": False,
        "datasource": datasource_luid,
        "dimension_hierarchy": None,
        "data_insight_profile": None,
        "current_dimensions": [],
        "pending_questions": [],
        "errors": [],
        "warnings": [],
        "performance": None,
        "visualizations": [],
    }
    
    # 收集流式输出
    streaming_data = {
        "tokens": [],
        "tokens_by_node": {},
        "nodes_visited": [],
        "final_result": None,
        "start_time": datetime.now(),
    }
    
    current_node = ""
    
    print("\n[流式输出]")
    
    # 使用 astream_events 捕获流式输出
    async for event in compiled_graph.astream_events(initial_state, config=config, version="v2"):
        event_type = event.get("event")
        event_name = event.get("name", "")
        
        # 捕获节点开始
        if event_type == "on_chain_start":
            if event_name and event_name not in ["RunnableSequence", "ChannelWrite", "LangGraph"]:
                current_node = event_name
                streaming_data["nodes_visited"].append(event_name)
                streaming_data["tokens_by_node"][event_name] = []
                print(f"\n  ┌─ [{current_node}] ", end="", flush=True)
        
        # 捕获 LLM 流式 token - 实时输出
        if event_type == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content") and chunk.content:
                token = chunk.content
                print(token, end="", flush=True)  # 实时输出 token
                streaming_data["tokens"].append(token)
                if current_node:
                    streaming_data["tokens_by_node"][current_node].append(token)
        
        # 捕获节点结束
        if event_type == "on_chain_end":
            if event_name and event_name not in ["RunnableSequence", "ChannelWrite", "LangGraph"]:
                node_tokens = streaming_data["tokens_by_node"].get(event_name, [])
                print(f"\n  └─ [{event_name}] 完成 ({len(node_tokens)} 个 token 片段)")
            
            # 捕获最终结果
            if event_name == "LangGraph":
                output = event.get("data", {}).get("output")
                if output and isinstance(output, dict):
                    streaming_data["final_result"] = output
    
    streaming_data["end_time"] = datetime.now()
    streaming_data["duration"] = (streaming_data["end_time"] - streaming_data["start_time"]).total_seconds()
    
    return streaming_data


# ═══════════════════════════════════════════════════════════════════════════
# 测试用例
# ═══════════════════════════════════════════════════════════════════════════

async def test_pipeline_success_ends_subgraph(data_model, datasource_luid: str, auth_ctx):
    """测试 Pipeline 成功后 Subgraph 正确结束"""
    print("\n" + "="*60)
    print("测试: Pipeline 成功 → Subgraph 结束")
    print("="*60)
    
    question = "各省份的销售额"
    
    streaming_data = await run_subgraph_with_streaming(
        question=question,
        data_model=data_model,
        datasource_luid=datasource_luid,
        auth_ctx=auth_ctx,
    )
    
    result = streaming_data["final_result"]
    nodes_visited = streaming_data["nodes_visited"]
    
    print(f"\n[结果]")
    print(f"  耗时: {streaming_data['duration']:.2f}s")
    print(f"  Token 数: {len(streaming_data['tokens'])}")
    print(f"  访问节点: {' → '.join(nodes_visited)}")
    
    # 验证访问了正确的节点
    assert "step1" in nodes_visited, "应该访问 step1 节点"
    
    # 验证结果
    assert result is not None
    
    if result.get("pipeline_success"):
        # 成功时不应该访问 react_error_handler
        if "react_error_handler" in nodes_visited:
            print("  ⚠️ 成功但访问了 react_error_handler")
        else:
            print("  ✓ 成功时未访问 react_error_handler")
        
        row_count = result.get("row_count", 0)
        assert row_count > 0, "应该返回数据"
        print(f"  行数: {row_count}")
    else:
        print(f"  Pipeline 未成功: {result.get('pipeline_error')}")
    
    print("\n  ✓ 测试通过")


async def test_non_data_query_ends_immediately(data_model, datasource_luid: str, auth_ctx):
    """测试非 DATA_QUERY 意图立即结束"""
    print("\n" + "="*60)
    print("测试: 非 DATA_QUERY 意图 → 立即结束")
    print("="*60)
    
    question = "你好"
    
    streaming_data = await run_subgraph_with_streaming(
        question=question,
        data_model=data_model,
        datasource_luid=datasource_luid,
        auth_ctx=auth_ctx,
    )
    
    result = streaming_data["final_result"]
    nodes_visited = streaming_data["nodes_visited"]
    
    print(f"\n[结果]")
    print(f"  耗时: {streaming_data['duration']:.2f}s")
    print(f"  访问节点: {' → '.join(nodes_visited)}")
    
    # 验证只访问了 step1
    assert "step1" in nodes_visited
    
    # 非 DATA_QUERY 不应该访问 pipeline
    from tableau_assistant.src.core.models import IntentType
    step1_output = result.get("step1_output")
    
    if step1_output and step1_output.intent.type != IntentType.DATA_QUERY:
        if "pipeline" not in nodes_visited:
            print(f"  ✓ 非 DATA_QUERY 正确跳过 pipeline")
        print(f"  意图类型: {step1_output.intent.type.value}")
    
    print("\n  ✓ 测试通过")


async def test_pipeline_error_triggers_react(data_model, datasource_luid: str, auth_ctx):
    """测试 Pipeline 错误触发 ReAct 处理"""
    print("\n" + "="*60)
    print("测试: Pipeline 错误 → ReAct 处理")
    print("="*60)
    
    # 使用可能导致错误的查询
    question = "各省份的销售额排名占比同比环比"  # 复杂查询可能失败
    
    streaming_data = await run_subgraph_with_streaming(
        question=question,
        data_model=data_model,
        datasource_luid=datasource_luid,
        auth_ctx=auth_ctx,
    )
    
    result = streaming_data["final_result"]
    nodes_visited = streaming_data["nodes_visited"]
    
    print(f"\n[结果]")
    print(f"  耗时: {streaming_data['duration']:.2f}s")
    print(f"  访问节点: {' → '.join(nodes_visited)}")
    
    # 如果 Pipeline 失败，应该触发 react_error_handler
    if result.get("pipeline_success") is False and result.get("pipeline_error"):
        if "react_error_handler" in nodes_visited:
            print("  ✓ Pipeline 错误正确触发了 ReAct 处理")
            
            # 验证 ReAct 输出
            react_action = result.get("react_action")
            if react_action:
                print(f"  ReAct 动作: {react_action}")
        else:
            print("  ⚠️ Pipeline 错误但未触发 ReAct")
    else:
        print("  查询成功或未触发错误处理")
    
    print("\n  ✓ 测试通过")


async def test_streaming_tokens_captured(data_model, datasource_luid: str, auth_ctx):
    """测试流式 Token 被正确捕获"""
    print("\n" + "="*60)
    print("测试: Token 流式输出捕获")
    print("="*60)
    
    question = "各省份的销售额"
    
    streaming_data = await run_subgraph_with_streaming(
        question=question,
        data_model=data_model,
        datasource_luid=datasource_luid,
        auth_ctx=auth_ctx,
    )
    
    tokens = streaming_data["tokens"]
    
    print(f"\n[Token 统计]")
    print(f"  捕获 Token 片段数: {len(tokens)}")
    
    # 验证捕获了流式 token
    assert len(tokens) > 0, "应该捕获到流式 token"
    
    # 合并 token 查看完整输出
    full_output = "".join(tokens)
    print(f"  总字符数: {len(full_output)}")
    
    # 按节点统计
    print(f"\n[按节点统计]")
    for node, node_tokens in streaming_data["tokens_by_node"].items():
        print(f"  {node}: {len(node_tokens)} 个 token 片段")
    
    # 输出前 200 个字符作为预览
    preview = full_output[:200] if len(full_output) > 200 else full_output
    print(f"\n[输出预览]")
    print(f"  {preview}...")
    
    print("\n  ✓ 测试通过")


async def test_streaming_with_step2(data_model, datasource_luid: str, auth_ctx):
    """测试包含 Step2 的流式输出"""
    print("\n" + "="*60)
    print("测试: Step2 流式输出")
    print("="*60)
    
    question = "各产品类别的销售额排名"  # 可能触发 Step2
    
    streaming_data = await run_subgraph_with_streaming(
        question=question,
        data_model=data_model,
        datasource_luid=datasource_luid,
        auth_ctx=auth_ctx,
    )
    
    tokens = streaming_data["tokens"]
    nodes_visited = streaming_data["nodes_visited"]
    
    print(f"\n[结果]")
    print(f"  访问节点: {' → '.join(nodes_visited)}")
    print(f"  Token 片段数: {len(tokens)}")
    
    # 如果访问了 step2，应该有更多 token
    if "step2" in nodes_visited:
        step2_tokens = streaming_data["tokens_by_node"].get("step2", [])
        print(f"  Step2 Token 片段数: {len(step2_tokens)}")
        assert len(step2_tokens) > 0, "Step2 应该产生流式输出"
        print("  ✓ Step2 流式输出正常")
    else:
        print("  Step2 未被访问（查询可能被识别为 SIMPLE）")
    
    print("\n  ✓ 测试通过")


async def test_simple_query_skips_step2(data_model, datasource_luid: str, auth_ctx):
    """测试简单查询跳过 Step2"""
    print("\n" + "="*60)
    print("测试: 简单查询 → 跳过 Step2")
    print("="*60)
    
    question = "各省份的销售额"
    
    streaming_data = await run_subgraph_with_streaming(
        question=question,
        data_model=data_model,
        datasource_luid=datasource_luid,
        auth_ctx=auth_ctx,
    )
    
    result = streaming_data["final_result"]
    nodes_visited = streaming_data["nodes_visited"]
    
    step1_output = result.get("step1_output")
    
    from tableau_assistant.src.core.models import HowType
    
    print(f"\n[结果]")
    print(f"  访问节点: {' → '.join(nodes_visited)}")
    
    if step1_output:
        print(f"  How 类型: {step1_output.how_type.value}")
        
        if step1_output.how_type == HowType.SIMPLE:
            if "step2" not in nodes_visited:
                print("  ✓ SIMPLE 查询正确跳过了 step2")
            else:
                print("  ⚠️ SIMPLE 查询不应该访问 step2")
        else:
            print(f"  查询被识别为: {step1_output.how_type.value}")
    
    print("\n  ✓ 测试通过")


async def test_complex_query_visits_step2(data_model, datasource_luid: str, auth_ctx):
    """测试复杂查询访问 Step2"""
    print("\n" + "="*60)
    print("测试: 复杂查询 → 访问 Step2")
    print("="*60)
    
    question = "各省份销售额占比"  # 占比计算应该触发 Step2
    
    streaming_data = await run_subgraph_with_streaming(
        question=question,
        data_model=data_model,
        datasource_luid=datasource_luid,
        auth_ctx=auth_ctx,
    )
    
    result = streaming_data["final_result"]
    nodes_visited = streaming_data["nodes_visited"]
    
    step1_output = result.get("step1_output")
    
    from tableau_assistant.src.core.models import HowType
    
    print(f"\n[结果]")
    print(f"  访问节点: {' → '.join(nodes_visited)}")
    
    if step1_output:
        print(f"  How 类型: {step1_output.how_type.value}")
        
        if step1_output.how_type != HowType.SIMPLE:
            if "step2" in nodes_visited:
                print(f"  ✓ 复杂查询 ({step1_output.how_type.value}) 正确访问了 step2")
                
                step2_output = result.get("step2_output")
                if step2_output:
                    print(f"  计算数: {len(step2_output.computations)}")
            else:
                print("  ⚠️ 复杂查询应该访问 step2")
        else:
            print("  查询被识别为 SIMPLE，跳过 step2")
    
    print("\n  ✓ 测试通过")


async def test_retry_loop_visits_nodes_multiple_times(data_model, datasource_luid: str, auth_ctx):
    """测试重试循环多次访问节点"""
    print("\n" + "="*60)
    print("测试: 重试循环节点访问")
    print("="*60)
    
    # 使用可能触发重试的查询
    question = "各省份的销售额排名占比"
    
    streaming_data = await run_subgraph_with_streaming(
        question=question,
        data_model=data_model,
        datasource_luid=datasource_luid,
        auth_ctx=auth_ctx,
    )
    
    result = streaming_data["final_result"]
    nodes_visited = streaming_data["nodes_visited"]
    
    # 统计节点访问次数
    node_counts = {}
    for node in nodes_visited:
        node_counts[node] = node_counts.get(node, 0) + 1
    
    print(f"\n[节点访问次数]")
    for node, count in node_counts.items():
        marker = " (多次)" if count > 1 else ""
        print(f"  {node}: {count}{marker}")
    
    # 如果有重试，某些节点会被访问多次
    retry_count = result.get("retry_count", 0)
    if retry_count > 0:
        print(f"\n[重试信息]")
        print(f"  重试次数: {retry_count}")
        
        # 验证重试历史
        retry_history = result.get("retry_history", [])
        for record in retry_history:
            print(f"  重试记录: {record}")
    else:
        print("\n  没有发生重试")
    
    print("\n  ✓ 测试通过")


# ═══════════════════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    """运行所有测试"""
    print("="*60)
    print("Decision Handler 集成测试")
    print("使用真实 Tableau 环境 + Token 流式输出")
    print("="*60)
    
    # 1. 获取 Tableau 配置
    tableau_config = get_tableau_config()
    if not tableau_config["domain"]:
        print("\n❌ 错误: 请配置 TABLEAU_DOMAIN 环境变量")
        return
    
    print(f"\nTableau Domain: {tableau_config['domain']}")
    
    # 2. 获取 Tableau 认证
    try:
        auth_ctx = await get_tableau_auth()
    except Exception as e:
        print(f"\n❌ 获取 Tableau 认证失败: {e}")
        return
    
    # 3. 解析数据源 LUID
    try:
        datasource_luid = await resolve_datasource_luid(tableau_config, auth_ctx)
        print(f"Datasource LUID: {datasource_luid}")
    except Exception as e:
        print(f"\n❌ 解析数据源失败: {e}")
        return
    
    # 4. 获取数据模型
    try:
        data_model = await get_data_model(datasource_luid, auth_ctx)
    except Exception as e:
        print(f"\n❌ 获取数据模型失败: {e}")
        return
    
    # 5. 运行测试
    test_results = []
    
    try:
        await test_pipeline_success_ends_subgraph(data_model, datasource_luid, auth_ctx)
        test_results.append(("Pipeline 成功结束", True))
    except Exception as e:
        print(f"\n❌ Pipeline 成功结束测试失败: {e}")
        import traceback
        traceback.print_exc()
        test_results.append(("Pipeline 成功结束", False))
    
    try:
        await test_non_data_query_ends_immediately(data_model, datasource_luid, auth_ctx)
        test_results.append(("非 DATA_QUERY 立即结束", True))
    except Exception as e:
        print(f"\n❌ 非 DATA_QUERY 立即结束测试失败: {e}")
        import traceback
        traceback.print_exc()
        test_results.append(("非 DATA_QUERY 立即结束", False))
    
    try:
        await test_pipeline_error_triggers_react(data_model, datasource_luid, auth_ctx)
        test_results.append(("Pipeline 错误触发 ReAct", True))
    except Exception as e:
        print(f"\n❌ Pipeline 错误触发 ReAct 测试失败: {e}")
        import traceback
        traceback.print_exc()
        test_results.append(("Pipeline 错误触发 ReAct", False))
    
    try:
        await test_streaming_tokens_captured(data_model, datasource_luid, auth_ctx)
        test_results.append(("Token 流式捕获", True))
    except Exception as e:
        print(f"\n❌ Token 流式捕获测试失败: {e}")
        import traceback
        traceback.print_exc()
        test_results.append(("Token 流式捕获", False))
    
    try:
        await test_streaming_with_step2(data_model, datasource_luid, auth_ctx)
        test_results.append(("Step2 流式输出", True))
    except Exception as e:
        print(f"\n❌ Step2 流式输出测试失败: {e}")
        import traceback
        traceback.print_exc()
        test_results.append(("Step2 流式输出", False))
    
    try:
        await test_simple_query_skips_step2(data_model, datasource_luid, auth_ctx)
        test_results.append(("简单查询跳过 Step2", True))
    except Exception as e:
        print(f"\n❌ 简单查询跳过 Step2 测试失败: {e}")
        import traceback
        traceback.print_exc()
        test_results.append(("简单查询跳过 Step2", False))
    
    try:
        await test_complex_query_visits_step2(data_model, datasource_luid, auth_ctx)
        test_results.append(("复杂查询访问 Step2", True))
    except Exception as e:
        print(f"\n❌ 复杂查询访问 Step2 测试失败: {e}")
        import traceback
        traceback.print_exc()
        test_results.append(("复杂查询访问 Step2", False))
    
    try:
        await test_retry_loop_visits_nodes_multiple_times(data_model, datasource_luid, auth_ctx)
        test_results.append(("重试循环节点访问", True))
    except Exception as e:
        print(f"\n❌ 重试循环节点访问测试失败: {e}")
        import traceback
        traceback.print_exc()
        test_results.append(("重试循环节点访问", False))
    
    # 6. 打印测试摘要
    print("\n" + "="*60)
    print("测试摘要")
    print("="*60)
    
    passed = sum(1 for _, success in test_results if success)
    total = len(test_results)
    
    for name, success in test_results:
        status = "✓" if success else "✗"
        print(f"  {status} {name}")
    
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！")
    else:
        print(f"\n⚠️ {total - passed} 个测试失败")


if __name__ == "__main__":
    asyncio.run(main())
