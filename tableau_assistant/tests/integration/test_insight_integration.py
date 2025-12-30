# -*- coding: utf-8 -*-
"""
InsightAgent 集成测试

使用真实的 Tableau 环境、真实的 LLM 和真实数据进行测试。
测试完整的洞察分析流程：Profiler → Director ↔ Analyzer 循环

运行方式:
    python -m tableau_assistant.tests.integration.test_insight_integration

或者使用 pytest:
    pytest tableau_assistant/tests/integration/test_insight_integration.py -v -s
"""
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 测试配置
# ═══════════════════════════════════════════════════════════════════════════

# 测试问题列表 - 避免与模板示例重复，测试 LLM 的泛化能力
TEST_QUESTIONS = [
    "哪些城市的利润率最低？",
    "按季度统计退货订单数",
    "不同客户类型的平均订单金额对比",
    "上个月销量前5的子类别",
]


# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════

def get_tableau_config() -> Dict[str, str]:
    """从环境变量获取 Tableau 配置（支持多环境）"""
    # 优先使用 Cloud 配置，其次使用 Server 配置，最后使用默认配置
    domain = (
        os.getenv("TABLEAU_CLOUD_DOMAIN") or 
        os.getenv("TABLEAU_SERVER_DOMAIN") or 
        os.getenv("TABLEAU_DOMAIN", "")
    )
    site = (
        os.getenv("TABLEAU_CLOUD_SITE") or 
        os.getenv("TABLEAU_SERVER_SITE") or 
        os.getenv("TABLEAU_SITE", "")
    )
    return {
        "domain": domain,
        "site": site,
        "datasource_luid": os.getenv("DATASOURCE_LUID", ""),
        "pat_name": os.getenv("TABLEAU_CLOUD_PAT_NAME") or os.getenv("TABLEAU_PAT_NAME", ""),
        "pat_secret": os.getenv("TABLEAU_CLOUD_PAT_SECRET") or os.getenv("TABLEAU_PAT_SECRET", ""),
    }


async def get_tableau_auth_context():
    """获取 Tableau 认证上下文"""
    from tableau_assistant.src.platforms.tableau.auth import get_tableau_auth_async
    
    auth_ctx = await get_tableau_auth_async()
    logger.info(f"获取 Tableau 认证成功 (方式: {auth_ctx.auth_method})")
    return auth_ctx


async def get_metadata(
    datasource_luid: str,
    token: str,
    site: str,
    domain: str,
    auth_ctx: Any = None,
) -> "DataModel":
    """获取数据源元数据，使用 LangGraph SqliteStore 缓存"""
    from tableau_assistant.src.infra.storage.langgraph_store import get_langgraph_store
    from tableau_assistant.src.infra.storage.data_model_cache import DataModelCache
    from tableau_assistant.src.infra.storage.data_model_loader import TableauDataModelLoader
    
    logger.info(f"获取数据源元数据: {datasource_luid}")
    
    # 使用缓存机制
    store = get_langgraph_store()
    cache = DataModelCache(store)
    loader = TableauDataModelLoader(auth_ctx)
    
    data_model, is_cache_hit = await cache.get_or_load(datasource_luid, loader)
    
    if is_cache_hit:
        logger.info(f"从缓存加载元数据: {data_model.field_count} 个字段")
    else:
        logger.info(f"从 API 加载元数据: {data_model.field_count} 个字段")
    
    logger.info(f"  - 维度: {len(data_model.get_dimensions())} 个")
    logger.info(f"  - 度量: {len(data_model.get_measures())} 个")
    
    return data_model


# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数 1: Profiler 组件测试
# ═══════════════════════════════════════════════════════════════════════════

async def run_profiler_test(query_result_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """测试 Profiler 组件使用真实数据"""
    from tableau_assistant.src.agents.insight.components.profiler import EnhancedDataProfiler
    from tableau_assistant.src.agents.insight.components.chunker import SemanticChunker
    
    logger.info("\n" + "="*60)
    logger.info("测试 1: Profiler 组件")
    logger.info("="*60)
    
    start_time = datetime.now()
    
    # 创建 Profiler
    profiler = EnhancedDataProfiler()
    
    # 生成画像
    profile = profiler.profile(query_result_data)
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    logger.info(f"\n--- Profiler 结果 (耗时: {elapsed:.2f}s) ---")
    logger.info(f"行数: {profile.row_count}")
    logger.info(f"列数: {profile.column_count}")
    logger.info(f"推荐策略: {profile.recommended_strategy}")
    logger.info(f"策略原因: {profile.strategy_reason}")
    
    # 贡献者分析
    if profile.contributor_analyses:
        logger.info(f"\n贡献者分析: {len(profile.contributor_analyses)} 个")
        for ca in profile.contributor_analyses[:2]:
            logger.info(f"  - {ca.dimension}/{ca.measure}: Top贡献 {ca.top_contribution_pct:.1%}")
            if ca.top_contributors:
                top = ca.top_contributors[0]
                logger.info(f"    第一名: {top['value']} ({top['percentage']:.1%})")
    
    # 集中度风险
    if profile.concentration_risks:
        logger.info(f"\n集中度风险: {len(profile.concentration_risks)} 个")
        for cr in profile.concentration_risks[:2]:
            logger.info(f"  - {cr.dimension}/{cr.measure}: HHI={cr.hhi_index:.3f} ({cr.risk_level})")
    
    # 异常索引
    if profile.anomaly_index:
        ai = profile.anomaly_index
        logger.info(f"\n异常检测: {ai.total_anomalies} 个 ({ai.anomaly_ratio:.1%})")
    
    # 测试分块
    insight_profile = profiler.get_insight_profile(query_result_data)
    chunker = SemanticChunker()
    
    strategy_map = {
        "BY_ANOMALY": "by_anomaly",
        "BY_CHANGE_POINT": "by_change_point",
        "BY_PARETO": "by_pareto",
        "BY_SEMANTIC": "by_semantic",
        "BY_STATISTICS": "by_statistics",
        "BY_POSITION": "by_position",
    }
    strategy_str = strategy_map.get(profile.recommended_strategy.name, "by_position")
    
    chunks = chunker.chunk_by_strategy(
        data=query_result_data,
        strategy=strategy_str,
        insight_profile=insight_profile,
    )
    
    logger.info(f"\n分块结果: {len(chunks)} 个块")
    for chunk in chunks[:3]:
        logger.info(f"  - [{chunk.chunk_id}] {chunk.chunk_type}: {chunk.row_count}行, 优先级={chunk.priority}")
    
    return {
        "profile": profile,
        "chunks": chunks,
        "elapsed": elapsed,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数 2: InsightAgent Subgraph 测试
# ═══════════════════════════════════════════════════════════════════════════

async def run_insight_subgraph_test(
    question: str,
    query_result_data: List[Dict[str, Any]],
    semantic_query: Optional[Any] = None,
) -> Dict[str, Any]:
    """测试完整的 InsightAgent Subgraph - 带流式输出"""
    from tableau_assistant.src.agents.insight.subgraph import create_insight_subgraph
    from tableau_assistant.src.agents.insight.models import Insight
    
    logger.info("\n" + "="*60)
    logger.info(f"InsightAgent Subgraph")
    logger.info(f"问题: {question}")
    logger.info("="*60)
    
    start_time = datetime.now()
    
    # 创建 Subgraph
    subgraph = create_insight_subgraph()
    compiled = subgraph.compile()
    
    # 准备输入状态
    # 模拟 QueryResult
    class MockQueryResult:
        def __init__(self, data):
            self.data = data
            self.error = None
        def is_success(self):
            return True
    
    input_state = {
        "question": question,
        "query_result": MockQueryResult(query_result_data),
        "context": {
            "question": question,
            "dimensions": [],
            "measures": [],
        },
        "max_iterations": 3,  # 限制迭代次数以加快测试
        # InsightState 必需字段
        "messages": [],
        "answered_questions": [],
        "is_analysis_question": True,
        "insights": [],
        "all_insights": [],
        "errors": [],
        "warnings": [],
        "visualizations": [],
        "replan_history": [],
        "execution_path": [],
    }
    
    # 如果有 semantic_query，提取维度和度量
    if semantic_query:
        if hasattr(semantic_query, 'dimensions') and semantic_query.dimensions:
            input_state["context"]["dimensions"] = [
                {"name": d.field_name} for d in semantic_query.dimensions
            ]
        if hasattr(semantic_query, 'measures') and semantic_query.measures:
            input_state["context"]["measures"] = [
                {"name": m.field_name} for m in semantic_query.measures
            ]
    
    # 运行 Subgraph - 使用流式输出
    result_state = None
    try:
        current_node = ""
        token_count = 0
        iteration = 0
        
        async for event in compiled.astream_events(input_state, version="v2"):
            event_type = event.get("event")
            event_name = event.get("name", "")
            
            # 捕获节点开始事件
            if event_type == "on_chain_start":
                if event_name and event_name not in ["RunnableSequence", "ChannelWrite", "LangGraph"]:
                    if event_name == "director":
                        iteration += 1
                        print(f"\n  [迭代 {iteration}]", end="", flush=True)
                    current_node = event_name
                    print(f"\n    [{current_node}] ", end="", flush=True)
            
            # 捕获 LLM 流式 token
            if event_type == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    token = chunk.content
                    print(token, end="", flush=True)
                    token_count += len(token)
            
            # 捕获最终状态
            if event_type == "on_chain_end" and event_name == "LangGraph":
                output = event.get("data", {}).get("output")
                if output and isinstance(output, dict):
                    result_state = output
        
        print(f"\n  [OK] (total {token_count} chars)")
        
        # 如果没有从事件中获取到结果，使用 ainvoke 作为后备
        if result_state is None:
            logger.warning("未从 astream_events 获取到结果，使用 ainvoke 后备")
            result_state = await compiled.ainvoke(input_state)
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        # 提取结果
        insights = result_state.get("insights") or []
        final_summary = result_state.get("final_summary") or ""
        iteration_count = result_state.get("iteration_count") or 0
        analyzed_chunk_ids = result_state.get("analyzed_chunk_ids") or []
        error_message = result_state.get("error_message")
        
        logger.info(f"\n--- Insight 结果 (耗时: {elapsed:.2f}s) ---")
        
        if error_message:
            logger.error(f"错误: {error_message}")
            return {"success": False, "error": error_message, "elapsed": elapsed}
        
        logger.info(f"迭代次数: {iteration_count}")
        logger.info(f"分析块数: {len(analyzed_chunk_ids)}")
        logger.info(f"洞察数量: {len(insights)}")
        
        # 打印洞察
        if insights:
            logger.info("\n洞察列表:")
            for i, ins in enumerate(insights):
                if isinstance(ins, Insight):
                    logger.info(f"  [{i}] {ins.type}: {ins.title}")
                    if ins.description:
                        logger.info(f"      {ins.description[:100]}...")
                elif isinstance(ins, dict):
                    logger.info(f"  [{i}] {ins.get('type', 'unknown')}: {ins.get('title', 'N/A')}")
        
        # 打印最终摘要
        if final_summary:
            logger.info(f"\n最终摘要:")
            logger.info(f"  {final_summary[:500]}...")
        
        return {
            "success": True,
            "insights": insights,
            "final_summary": final_summary,
            "iteration_count": iteration_count,
            "analyzed_chunks": len(analyzed_chunk_ids),
            "elapsed": elapsed,
        }
        
    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.error(f"Subgraph 执行失败: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e), "elapsed": elapsed}


# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数 3: 完整工作流测试
# ═══════════════════════════════════════════════════════════════════════════

async def run_full_workflow_test(
    question: str,
    data_model: "DataModel",
    auth_ctx: Any,
    config: Dict[str, str],
) -> Dict[str, Any]:
    """测试完整工作流 - 带流式输出"""
    from tableau_assistant.src.agents.semantic_parser.subgraph import create_semantic_parser_subgraph
    from tableau_assistant.src.agents.semantic_parser.state import SemanticParserState
    from tableau_assistant.src.orchestration.workflow.context import WorkflowContext, create_workflow_config
    from tableau_assistant.src.core.models import IntentType
    from langchain_core.messages import HumanMessage
    
    logger.info("\n" + "#"*60)
    logger.info(f"测试完整工作流")
    logger.info(f"问题: {question}")
    logger.info("#"*60)
    
    total_start = datetime.now()
    
    # Step 1: 语义解析 (使用 Subgraph 架构，带流式输出)
    logger.info("\n--- Step 1: 语义解析 ---")
    
    # 创建 Subgraph
    graph = create_semantic_parser_subgraph()
    compiled_graph = graph.compile()
    
    # 创建 WorkflowContext 和 config
    workflow_ctx = WorkflowContext(
        auth=auth_ctx,
        datasource_luid=config["datasource_luid"],
        data_model=data_model,
    )
    run_config = create_workflow_config(
        thread_id=f"test-{question[:20]}",
        context=workflow_ctx,
    )
    
    # 准备初始状态
    initial_state: SemanticParserState = {
        "question": question,
        "messages": [HumanMessage(content=question)],
        "data_model": data_model,
        "datasource_luid": config["datasource_luid"],
        # 可选字段初始化
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
        # VizQLState 必需字段
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
        "datasource": None,
        "dimension_hierarchy": None,
        "data_insight_profile": None,
        "current_dimensions": [],
        "pending_questions": [],
        "errors": [],
        "warnings": [],
        "performance": None,
        "visualizations": [],
    }
    
    parse_start = datetime.now()
    final_state = None
    
    try:
        # 使用 astream_events 执行 Subgraph，捕获流式输出
        current_node = ""
        token_count = 0
        
        async for event in compiled_graph.astream_events(initial_state, config=run_config, version="v2"):
            event_type = event.get("event")
            event_name = event.get("name", "")
            
            # 捕获节点开始事件
            if event_type == "on_chain_start":
                if event_name and event_name not in ["RunnableSequence", "ChannelWrite", "LangGraph"]:
                    current_node = event_name
                    print(f"\n  [*] [{current_node}] ", end="", flush=True)
            
            # 捕获 LLM 流式 token
            if event_type == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    token = chunk.content
                    print(token, end="", flush=True)
                    token_count += len(token)
            
            # 捕获最终状态
            if event_type == "on_chain_end" and event_name == "LangGraph":
                output = event.get("data", {}).get("output")
                if output and isinstance(output, dict):
                    final_state = output
        
        print(f"\n  [OK] (total {token_count} chars)")
        
        # 如果没有从事件中获取到结果，使用 ainvoke 作为后备
        if final_state is None:
            logger.warning("未从 astream_events 获取到结果，使用 ainvoke 后备")
            final_state = await compiled_graph.ainvoke(initial_state, config=run_config)
        
        parse_elapsed = (datetime.now() - parse_start).total_seconds()
        
        restated_question = final_state.get("restated_question", "")
        intent_type = final_state.get("intent_type")
        semantic_query = final_state.get("semantic_query")
        step1_output = final_state.get("step1_output")
        
        logger.info(f"\n重述问题: {restated_question}")
        if step1_output:
            logger.info(f"意图类型: {step1_output.intent.type.value}")
            logger.info(f"How类型: {step1_output.how_type.value}")
        logger.info(f"解析耗时: {parse_elapsed:.2f}s")
        
        # 检查意图类型
        if step1_output and step1_output.intent.type != IntentType.DATA_QUERY:
            logger.warning(f"非数据查询意图，跳过后续步骤")
            return {
                "success": True,
                "intent_type": step1_output.intent.type.value,
                "message": "非数据查询意图",
            }
        
        if not semantic_query:
            logger.warning("无语义查询，跳过后续步骤")
            return {"success": False, "error": "无语义查询"}
            
    except Exception as e:
        logger.error(f"语义解析失败: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": f"语义解析失败: {e}"}
    
    # Step 2: 查询执行 (已在 Subgraph 中完成)
    logger.info("\n--- Step 2: 查询执行 ---")
    
    # 从 Subgraph 结果中获取查询数据
    query_result = final_state.get("query_result")
    row_count = final_state.get("row_count", 0)
    
    if not query_result:
        logger.warning("无查询结果，跳过洞察分析")
        return {"success": False, "error": "无查询结果"}
    
    # 转换为列表格式
    if isinstance(query_result, list):
        data = query_result
    elif hasattr(query_result, 'data'):
        data = query_result.data
    else:
        data = []
    
    logger.info(f"查询成功: {len(data)} 行数据")
    
    # 打印部分数据
    if data:
        logger.info(f"数据样本 (前3行):")
        for row in data[:3]:
            logger.info(f"  {row}")
    
    # Step 3: 洞察分析
    logger.info("\n--- Step 3: 洞察分析 ---")
    
    insight_result = await run_insight_subgraph_test(
        question=question,
        query_result_data=data,
        semantic_query=semantic_query,
    )
    
    total_elapsed = (datetime.now() - total_start).total_seconds()
    
    logger.info(f"\n--- 完整工作流完成 (总耗时: {total_elapsed:.2f}s) ---")
    
    return {
        "success": insight_result.get("success", False),
        "parse_elapsed": parse_elapsed,
        "insight_elapsed": insight_result.get("elapsed", 0),
        "total_elapsed": total_elapsed,
        "insights": insight_result.get("insights", []),
        "final_summary": insight_result.get("final_summary", ""),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Pytest 测试入口
# ═══════════════════════════════════════════════════════════════════════════

import pytest

@pytest.mark.asyncio
async def test_insight_integration():
    """Pytest 入口 - 运行完整的集成测试"""
    await run_all_tests()


# ═══════════════════════════════════════════════════════════════════════════
# 主测试入口
# ═══════════════════════════════════════════════════════════════════════════

async def run_all_tests():
    """运行所有测试"""
    logger.info("="*60)
    logger.info("InsightAgent 集成测试")
    logger.info("="*60)
    
    # 1. 获取 Tableau 配置
    config = get_tableau_config()
    if not config["domain"] or not config["datasource_luid"]:
        logger.error("请配置 TABLEAU_DOMAIN 和 DATASOURCE_LUID 环境变量")
        return
    
    logger.info(f"Tableau Domain: {config['domain']}")
    logger.info(f"Datasource LUID: {config['datasource_luid']}")
    
    # 2. 获取 Tableau 认证
    try:
        auth_ctx = await get_tableau_auth_context()
    except Exception as e:
        logger.error(f"获取 Tableau 认证失败: {e}")
        return
    
    # 3. 获取数据模型（使用缓存）
    try:
        data_model = await get_metadata(
            datasource_luid=config["datasource_luid"],
            token=auth_ctx.api_key,
            site=auth_ctx.site,
            domain=auth_ctx.domain,
            auth_ctx=auth_ctx,
        )
    except Exception as e:
        logger.error(f"获取数据模型失败: {e}")
        return
    
    # 4. 测试完整工作流
    results = []
    for question in TEST_QUESTIONS:
        try:
            result = await run_full_workflow_test(
                question=question,
                data_model=data_model,
                auth_ctx=auth_ctx,
                config=config,
            )
            results.append({
                "question": question,
                **result,
            })
        except Exception as e:
            logger.error(f"测试失败: {question}")
            logger.error(f"错误: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                "question": question,
                "success": False,
                "error": str(e),
            })
    
    # 5. 输出测试摘要
    logger.info("\n" + "="*60)
    logger.info("测试摘要")
    logger.info("="*60)
    
    success_count = sum(1 for r in results if r.get("success", False))
    logger.info(f"测试结果: {success_count}/{len(results)} 成功")
    
    for r in results:
        status = "✅" if r.get("success") else "❌"
        logger.info(f"  {status} {r['question'][:30]}...")
        if r.get("insights"):
            logger.info(f"      洞察数: {len(r['insights'])}")
        if r.get("error"):
            logger.info(f"      错误: {r['error'][:50]}...")
    
    # 平均耗时
    times = [r.get("total_elapsed", 0) for r in results if r.get("success")]
    if times:
        avg_time = sum(times) / len(times)
        logger.info(f"\n平均总耗时: {avg_time:.2f}s")


# ═══════════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    asyncio.run(run_all_tests())
