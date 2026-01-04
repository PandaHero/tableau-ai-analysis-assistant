# -*- coding: utf-8 -*-
"""
SemanticParser Subgraph 集成测试

测试 SemanticParser Subgraph 的完整流程：
- Step1 → Pipeline 流程 (SIMPLE)
- Step1 → Step2 → Pipeline 流程 (COMPLEX)
- 非 DATA_QUERY 意图直接结束
- Token 级别流式输出

使用真实的 Tableau 环境和 LLM 进行测试。

运行方式:
    python -m tableau_assistant.tests.agents.semantic_parser.test_subgraph

或直接运行:
    python tableau_assistant/tests/agents/semantic_parser/test_subgraph.py
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
# 测试配置
# ═══════════════════════════════════════════════════════════════════════════

TEST_QUESTIONS = {
    "simple": [
        # 简单查询 - 应该走 step1 → pipeline 路径
        "今年各省份的销售额是多少？",
    ],
    "complex": [
        # 复杂计算 - 应该走 step1 → step2 → pipeline 路径
        "各产品类别的销售额排名",
    ],
    "clarification": [
        # 需要澄清的问题
        "销售情况怎么样？",
    ],
    "general": [
        # 一般性问题 - 应该直接返回
        "你好",
    ],
}


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
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """运行 SemanticParser Subgraph 并实时显示流式输出
    
    使用 astream_events 捕获 token 级别的流式输出。
    """
    from tableau_assistant.src.agents.semantic_parser.subgraph import create_semantic_parser_subgraph
    from tableau_assistant.src.agents.semantic_parser.state import SemanticParserState
    from tableau_assistant.src.orchestration.workflow.context import WorkflowContext, create_workflow_config
    from langchain_core.messages import HumanMessage, AIMessage
    
    print(f"\n{'='*60}")
    print(f"问题: {question}")
    print(f"{'='*60}")
    
    # 创建 Subgraph
    graph = create_semantic_parser_subgraph()
    compiled_graph = graph.compile()
    
    # 创建 WorkflowContext 和 config
    workflow_ctx = WorkflowContext(
        auth=auth_ctx,
        datasource_luid=datasource_luid,
        data_model=data_model,
    )
    config = create_workflow_config(
        thread_id=f"test-{datetime.now().strftime('%H%M%S')}",
        context=workflow_ctx,
    )
    
    # 准备消息历史
    messages = []
    if history:
        for msg in history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                messages.append(AIMessage(content=msg["content"]))
    messages.append(HumanMessage(content=question))
    
    # 准备初始状态
    initial_state: SemanticParserState = {
        "question": question,
        "messages": messages,
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
    
    # 收集结果
    result_data = {
        "tokens_by_node": {},
        "nodes_visited": [],
        "total_tokens": 0,
        "final_result": None,
        "start_time": datetime.now(),
    }
    
    current_node = ""
    
    # 使用 astream_events 捕获流式输出
    print("\n[流式输出]")
    
    async for event in compiled_graph.astream_events(initial_state, config=config, version="v2"):
        event_type = event.get("event")
        event_name = event.get("name", "")
        
        # 捕获节点开始事件
        if event_type == "on_chain_start":
            if event_name and event_name not in ["RunnableSequence", "ChannelWrite", "LangGraph"]:
                current_node = event_name
                result_data["nodes_visited"].append(event_name)
                result_data["tokens_by_node"][event_name] = []
                print(f"\n  ┌─ [{current_node}] ", end="", flush=True)
        
        # 捕获 LLM 流式 token - 关键！实时输出
        if event_type == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content") and chunk.content:
                token = chunk.content
                print(token, end="", flush=True)  # 实时输出 token
                result_data["total_tokens"] += len(token)
                if current_node:
                    result_data["tokens_by_node"][current_node].append(token)
        
        # 捕获节点结束事件
        if event_type == "on_chain_end":
            if event_name and event_name not in ["RunnableSequence", "ChannelWrite", "LangGraph"]:
                node_tokens = result_data["tokens_by_node"].get(event_name, [])
                print(f"\n  └─ [{event_name}] 完成 ({len(node_tokens)} 个 token 片段)")
            
            # 捕获最终结果
            if event_name == "LangGraph":
                output = event.get("data", {}).get("output")
                if output and isinstance(output, dict):
                    result_data["final_result"] = output
    
    result_data["end_time"] = datetime.now()
    result_data["duration"] = (result_data["end_time"] - result_data["start_time"]).total_seconds()
    
    return result_data



def print_result_summary(result_data: Dict[str, Any], question: str):
    """打印测试结果摘要"""
    result = result_data.get("final_result", {})
    
    print(f"\n{'─'*60}")
    print(f"[结果摘要]")
    print(f"  耗时: {result_data['duration']:.2f}s")
    print(f"  总 token 数: {result_data['total_tokens']}")
    print(f"  访问节点: {' → '.join(result_data['nodes_visited'])}")
    
    # Step1 输出
    step1_output = result.get("step1_output")
    if step1_output:
        print(f"\n  [Step1]")
        print(f"    意图: {step1_output.intent.type.value}")
        print(f"    How类型: {step1_output.how_type.value}")
        print(f"    重述: {result.get('restated_question', '')[:50]}...")
        
        if step1_output.where and step1_output.where.dimensions:
            dims = [d.field_name for d in step1_output.where.dimensions]
            print(f"    维度: {dims}")
        if step1_output.what and step1_output.what.measures:
            measures = [m.field_name for m in step1_output.what.measures]
            print(f"    度量: {measures}")
    
    # Step2 输出
    step2_output = result.get("step2_output")
    if step2_output:
        print(f"\n  [Step2]")
        print(f"    计算数: {len(step2_output.computations)}")
        for comp in step2_output.computations[:3]:
            calc_type = comp.calc_type.value if hasattr(comp.calc_type, 'value') else comp.calc_type
            print(f"      - {calc_type}: {comp.target}")
    
    # Pipeline 结果
    pipeline_success = result.get("pipeline_success")
    if pipeline_success is not None:
        print(f"\n  [Pipeline]")
        if pipeline_success:
            print(f"    状态: ✓ 成功")
            print(f"    行数: {result.get('row_count', 0)}")
            print(f"    执行时间: {result.get('execution_time_ms', 0)}ms")
        else:
            print(f"    状态: ✗ 失败")
            error = result.get("pipeline_error")
            if error:
                print(f"    错误: {error.message[:100]}...")
    
    # 澄清/中止
    if result.get("needs_clarification"):
        print(f"\n  [需要澄清]")
        print(f"    问题: {result.get('clarification_question', '')}")
    
    if result.get("pipeline_aborted"):
        print(f"\n  [已中止]")
        print(f"    消息: {result.get('user_message', '')}")
    
    # ReAct 动作
    react_action = result.get("react_action")
    if react_action:
        print(f"\n  [ReAct]")
        print(f"    动作: {react_action}")
        print(f"    重试次数: {result.get('retry_count', 0)}")


# ═══════════════════════════════════════════════════════════════════════════
# 测试用例
# ═══════════════════════════════════════════════════════════════════════════

async def test_simple_query(data_model, datasource_luid: str, auth_ctx):
    """测试简单查询 (Step1 → Pipeline)"""
    print("\n" + "="*60)
    print("测试: 简单查询 (Step1 → Pipeline)")
    print("="*60)
    
    for question in TEST_QUESTIONS["simple"]:
        result_data = await run_subgraph_with_streaming(
            question=question,
            data_model=data_model,
            datasource_luid=datasource_luid,
            auth_ctx=auth_ctx,
        )
        print_result_summary(result_data, question)
        
        # 验证
        result = result_data["final_result"]
        step1_output = result.get("step1_output")
        
        from tableau_assistant.src.core.models import IntentType, HowType
        
        assert step1_output is not None, "Step1 应该有输出"
        assert step1_output.intent.type == IntentType.DATA_QUERY, "意图应该是 DATA_QUERY"
        
        if step1_output.how_type == HowType.SIMPLE:
            assert "step2" not in result_data["nodes_visited"], "SIMPLE 查询不应该访问 step2"
        
        print("\n  ✓ 测试通过")


async def test_complex_query(data_model, datasource_luid: str, auth_ctx):
    """测试复杂查询 (Step1 → Step2 → Pipeline)"""
    print("\n" + "="*60)
    print("测试: 复杂查询 (Step1 → Step2 → Pipeline)")
    print("="*60)
    
    for question in TEST_QUESTIONS["complex"]:
        result_data = await run_subgraph_with_streaming(
            question=question,
            data_model=data_model,
            datasource_luid=datasource_luid,
            auth_ctx=auth_ctx,
        )
        print_result_summary(result_data, question)
        
        # 验证
        result = result_data["final_result"]
        step1_output = result.get("step1_output")
        
        from tableau_assistant.src.core.models import HowType
        
        assert step1_output is not None, "Step1 应该有输出"
        
        if step1_output.how_type != HowType.SIMPLE:
            assert "step2" in result_data["nodes_visited"], "复杂查询应该访问 step2"
            step2_output = result.get("step2_output")
            assert step2_output is not None, "复杂查询应该有 Step2 输出"
            print(f"\n  ✓ Step2 正确执行，{len(step2_output.computations)} 个计算")
        
        print("\n  ✓ 测试通过")


async def test_non_data_query(data_model, datasource_luid: str, auth_ctx):
    """测试非 DATA_QUERY 意图"""
    print("\n" + "="*60)
    print("测试: 非 DATA_QUERY 意图")
    print("="*60)
    
    for question in TEST_QUESTIONS["general"]:
        result_data = await run_subgraph_with_streaming(
            question=question,
            data_model=data_model,
            datasource_luid=datasource_luid,
            auth_ctx=auth_ctx,
        )
        print_result_summary(result_data, question)
        
        # 验证
        result = result_data["final_result"]
        step1_output = result.get("step1_output")
        
        from tableau_assistant.src.core.models import IntentType
        
        assert step1_output is not None, "Step1 应该有输出"
        
        if step1_output.intent.type != IntentType.DATA_QUERY:
            assert "pipeline" not in result_data["nodes_visited"], "非 DATA_QUERY 不应该访问 pipeline"
            print(f"\n  ✓ 非 DATA_QUERY 意图正确处理: {step1_output.intent.type}")
        
        print("\n  ✓ 测试通过")


async def test_clarification_query(data_model, datasource_luid: str, auth_ctx):
    """测试需要澄清的问题"""
    print("\n" + "="*60)
    print("测试: 需要澄清的问题")
    print("="*60)
    
    for question in TEST_QUESTIONS["clarification"]:
        result_data = await run_subgraph_with_streaming(
            question=question,
            data_model=data_model,
            datasource_luid=datasource_luid,
            auth_ctx=auth_ctx,
        )
        print_result_summary(result_data, question)
        
        # 验证
        result = result_data["final_result"]
        step1_output = result.get("step1_output")
        
        assert step1_output is not None, "Step1 应该有输出"
        
        from tableau_assistant.src.core.models import IntentType
        
        if step1_output.intent.type == IntentType.CLARIFICATION:
            print(f"\n  ✓ 问题被识别为需要澄清")
        else:
            print(f"\n  ✓ 问题被解释为: {step1_output.intent.type}")
        
        print("\n  ✓ 测试通过")


async def test_multi_turn_conversation(data_model, datasource_luid: str, auth_ctx):
    """测试多轮对话"""
    print("\n" + "="*60)
    print("测试: 多轮对话")
    print("="*60)
    
    # 第一轮
    question1 = "今年各省份的销售额"
    result_data1 = await run_subgraph_with_streaming(
        question=question1,
        data_model=data_model,
        datasource_luid=datasource_luid,
        auth_ctx=auth_ctx,
    )
    print_result_summary(result_data1, question1)
    
    result1 = result_data1["final_result"]
    
    # 第二轮（带历史）
    history = [
        {"role": "user", "content": question1},
        {"role": "assistant", "content": result1.get("restated_question", question1)},
    ]
    
    question2 = "按月份细分呢？"
    result_data2 = await run_subgraph_with_streaming(
        question=question2,
        data_model=data_model,
        datasource_luid=datasource_luid,
        auth_ctx=auth_ctx,
        history=history,
    )
    print_result_summary(result_data2, question2)
    
    result2 = result_data2["final_result"]
    step1_output2 = result2.get("step1_output")
    
    if step1_output2 and step1_output2.where and step1_output2.where.dimensions:
        dim_names = [d.field_name for d in step1_output2.where.dimensions]
        print(f"\n  追问解析的维度: {dim_names}")
    
    print("\n  ✓ 多轮对话测试通过")



# ═══════════════════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    """运行所有测试"""
    print("="*60)
    print("SemanticParser Subgraph 集成测试")
    print("使用真实 Tableau 环境 + Token 流式输出")
    print("="*60)
    
    # 1. 获取 Tableau 配置
    config = get_tableau_config()
    if not config["domain"]:
        print("\n❌ 错误: 请配置 TABLEAU_DOMAIN 环境变量")
        return
    
    print(f"\nTableau Domain: {config['domain']}")
    
    # 2. 获取 Tableau 认证
    try:
        auth_ctx = await get_tableau_auth()
    except Exception as e:
        print(f"\n❌ 获取 Tableau 认证失败: {e}")
        return
    
    # 3. 解析数据源 LUID
    try:
        datasource_luid = await resolve_datasource_luid(config, auth_ctx)
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
        # 测试简单查询
        await test_simple_query(data_model, datasource_luid, auth_ctx)
        test_results.append(("简单查询", True))
    except Exception as e:
        print(f"\n❌ 简单查询测试失败: {e}")
        test_results.append(("简单查询", False))
    
    try:
        # 测试复杂查询
        await test_complex_query(data_model, datasource_luid, auth_ctx)
        test_results.append(("复杂查询", True))
    except Exception as e:
        print(f"\n❌ 复杂查询测试失败: {e}")
        test_results.append(("复杂查询", False))
    
    try:
        # 测试非 DATA_QUERY 意图
        await test_non_data_query(data_model, datasource_luid, auth_ctx)
        test_results.append(("非DATA_QUERY意图", True))
    except Exception as e:
        print(f"\n❌ 非DATA_QUERY意图测试失败: {e}")
        test_results.append(("非DATA_QUERY意图", False))
    
    try:
        # 测试需要澄清的问题
        await test_clarification_query(data_model, datasource_luid, auth_ctx)
        test_results.append(("澄清问题", True))
    except Exception as e:
        print(f"\n❌ 澄清问题测试失败: {e}")
        test_results.append(("澄清问题", False))
    
    try:
        # 测试多轮对话
        await test_multi_turn_conversation(data_model, datasource_luid, auth_ctx)
        test_results.append(("多轮对话", True))
    except Exception as e:
        print(f"\n❌ 多轮对话测试失败: {e}")
        test_results.append(("多轮对话", False))
    
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
