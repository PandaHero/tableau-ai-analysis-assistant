"""
后端功能完整集成测试

测试完整的端到端工作流：
SemanticParser -> FieldMapper -> QueryBuilder -> Execute -> Insight -> Replanner

运行方式:
    python -m tableau_assistant.tests.integration.test_all_backend

或者使用 pytest:
    pytest tableau_assistant/tests/integration/test_all_backend.py -v -s
"""
import asyncio
import json
import logging
import os
import sys
import time
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from dotenv import load_dotenv
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 测试结果收集
# ═══════════════════════════════════════════════════════════════════════════

class TestResults:
    """测试结果收集器"""
    
    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self.start_time = time.time()
    
    def add(self, module: str, test_name: str, success: bool, 
            elapsed: float = 0, message: str = "", details: Any = None):
        self.results.append({
            "module": module,
            "test_name": test_name,
            "success": success,
            "elapsed": elapsed,
            "message": message,
            "details": details,
            "timestamp": datetime.now().isoformat(),
        })
        
        status = "✅" if success else "❌"
        logger.info(f"{status} [{module}] {test_name}: {message} ({elapsed:.2f}s)")
    
    def summary(self) -> Dict[str, Any]:
        total = len(self.results)
        passed = sum(1 for r in self.results if r["success"])
        failed = total - passed
        total_time = time.time() - self.start_time
        
        # 按模块统计
        by_module = {}
        for r in self.results:
            module = r["module"]
            if module not in by_module:
                by_module[module] = {"passed": 0, "failed": 0}
            if r["success"]:
                by_module[module]["passed"] += 1
            else:
                by_module[module]["failed"] += 1
        
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": f"{passed/total*100:.1f}%" if total > 0 else "N/A",
            "total_time": f"{total_time:.2f}s",
            "by_module": by_module,
            "failed_tests": [r for r in self.results if not r["success"]],
        }


# ═══════════════════════════════════════════════════════════════════════════
# 1. 基础设施测试
# ═══════════════════════════════════════════════════════════════════════════

async def test_tableau_auth(results: TestResults) -> Optional[Any]:
    """测试 Tableau 认证"""
    module = "infra"
    start = time.time()
    
    try:
        from tableau_assistant.src.platforms.tableau.auth import (
            get_tableau_auth_async,
            TableauAuthContext,
        )
        
        auth_ctx = await get_tableau_auth_async()
        
        assert auth_ctx.api_key, "api_key 为空"
        assert auth_ctx.site, "site 为空"
        assert auth_ctx.domain, "domain 为空"
        assert not auth_ctx.is_expired(), "认证已过期"
        
        results.add(
            module, "tableau_auth", True,
            time.time() - start,
            f"认证方式: {auth_ctx.auth_method}, site: {auth_ctx.site}",
        )
        return auth_ctx
        
    except Exception as e:
        results.add(module, "tableau_auth", False, time.time() - start, str(e))
        return None


async def test_store_manager(results: TestResults) -> Optional[Any]:
    """测试存储管理器（LangGraph SqliteStore）"""
    module = "infra"
    
    try:
        from tableau_assistant.src.infra.storage import get_langgraph_store, reset_langgraph_store
        
        # 使用默认 store
        store = get_langgraph_store()
        
        # 测试基本操作
        start = time.time()
        store.put(("test",), "key1", {"name": "测试数据", "value": 123})
        item = store.get(("test",), "key1")
        assert item is not None and item.value["name"] == "测试数据"
        
        # 清理测试数据
        store.delete(("test",), "key1")
        
        results.add(module, "store_manager", True, time.time() - start, "LangGraph Store 正常")
        return store
        
    except Exception as e:
        results.add(module, "store_manager", False, 0, str(e))
        return None


async def test_llm_connection(results: TestResults) -> bool:
    """测试 LLM 连接"""
    module = "infra"
    start = time.time()
    
    try:
        from tableau_assistant.src.infra.ai.llm import get_llm
        
        llm = get_llm()
        
        # 简单测试
        response = await llm.ainvoke("你好，请回复'OK'")
        
        results.add(
            module, "llm_connection", True,
            time.time() - start,
            f"LLM 连接正常, 模型: {llm.model_name if hasattr(llm, 'model_name') else 'unknown'}"
        )
        return True
        
    except Exception as e:
        results.add(module, "llm_connection", False, time.time() - start, str(e))
        return False


async def test_llm_streaming(results: TestResults) -> bool:
    """测试 LLM 流式输出"""
    module = "infra"
    start = time.time()
    
    try:
        from tableau_assistant.src.infra.ai.llm import get_llm
        
        llm = get_llm()
        
        logger.info("\n" + "-" * 50)
        logger.info("测试 LLM 流式输出...")
        logger.info("-" * 50)
        
        # 测试流式输出
        chunks = []
        chunk_count = 0
        
        logger.info("开始接收流式输出:")
        async for chunk in llm.astream("请用中文简单介绍一下你自己，50字以内"):
            if hasattr(chunk, 'content') and chunk.content:
                chunks.append(chunk.content)
                chunk_count += 1
                # 实时打印每个 chunk
                print(chunk.content, end='', flush=True)
        
        print()  # 换行
        
        full_response = "".join(chunks)
        elapsed = time.time() - start
        
        logger.info(f"\n流式输出完成:")
        logger.info(f"  - 总 chunk 数: {chunk_count}")
        logger.info(f"  - 响应长度: {len(full_response)} 字符")
        logger.info(f"  - 完整响应: {full_response[:100]}{'...' if len(full_response) > 100 else ''}")
        logger.info(f"  - 耗时: {elapsed:.2f}s")
        
        results.add(
            module, "llm_streaming", True,
            elapsed,
            f"流式输出正常: {chunk_count} chunks, {len(full_response)} 字符",
            {"chunk_count": chunk_count, "response_length": len(full_response)}
        )
        return True
        
    except Exception as e:
        import traceback
        results.add(module, "llm_streaming", False, time.time() - start, f"{str(e)}\n{traceback.format_exc()}")
        return False


async def test_workflow_streaming(results: TestResults, auth_ctx: Any) -> bool:
    """
    测试工作流流式输出（正式功能）
    
    使用 WorkflowExecutor.stream() 测试完整的流式输出功能，
    包括节点开始/完成事件和 LLM token 流式输出。
    """
    module = "workflow_stream"
    start = time.time()
    
    if auth_ctx is None:
        results.add(module, "workflow_streaming", False, 0, "认证上下文未获取")
        return False
    
    datasource_luid = os.getenv("DATASOURCE_LUID", "")
    if not datasource_luid:
        results.add(module, "workflow_streaming", False, 0, "DATASOURCE_LUID 未配置")
        return False
    
    try:
        from tableau_assistant.src.orchestration.workflow.executor import (
            WorkflowExecutor,
            EventType,
        )
        
        logger.info("\n" + "=" * 70)
        logger.info("测试工作流流式输出（正式功能）")
        logger.info("=" * 70)
        
        executor = WorkflowExecutor(datasource_luid=datasource_luid)
        
        test_question = "各省份的销售额是多少？"
        logger.info(f"问题: {test_question}")
        logger.info("-" * 70)
        
        # 统计
        node_events = []
        token_count = 0
        token_content = []
        current_node = None
        
        async for event in executor.stream(test_question):
            if event.type == EventType.NODE_START:
                current_node = event.node_name
                node_events.append(f"[START] {event.node_name}")
                print(f"\n🚀 [{event.node_name}] 开始执行...", flush=True)
            
            elif event.type == EventType.TOKEN:
                token_count += 1
                if event.content:
                    token_content.append(event.content)
                    # 实时打印 token
                    print(event.content, end='', flush=True)
            
            elif event.type == EventType.NODE_COMPLETE:
                node_events.append(f"[COMPLETE] {event.node_name}")
                print(f"\n✅ [{event.node_name}] 完成", flush=True)
                
                # 打印节点输出摘要
                if event.output:
                    output = event.output
                    if event.node_name == "semantic_parser" and output.semantic_query:
                        sq = output.semantic_query
                        dims = len(sq.dimensions or [])
                        measures = len(sq.measures or [])
                        print(f"   语义解析: {dims} 维度, {measures} 度量", flush=True)
                    
                    elif event.node_name == "field_mapper" and output.mapped_query:
                        mq = output.mapped_query
                        print(f"   字段映射: {len(mq.field_mappings)} 个字段, 置信度: {mq.overall_confidence:.2f}", flush=True)
                    
                    elif event.node_name == "execute" and output.query_result:
                        qr = output.query_result
                        row_count = len(qr.data) if hasattr(qr, 'data') and qr.data else 0
                        print(f"   查询结果: {row_count} 行数据", flush=True)
                    
                    elif event.node_name == "replanner" and output.replan_decision:
                        rd = output.replan_decision
                        print(f"   重规划: 完成度={rd.completeness_score:.1%}, 继续={rd.should_replan}", flush=True)
            
            elif event.type == EventType.ERROR:
                print(f"\n❌ 错误: {event.content}", flush=True)
                results.add(
                    module, "workflow_streaming", False,
                    time.time() - start,
                    f"流式执行错误: {event.content}"
                )
                return False
            
            elif event.type == EventType.COMPLETE:
                print(f"\n🎉 工作流完成!", flush=True)
                break
        
        elapsed = time.time() - start
        
        # 输出统计
        logger.info("\n" + "-" * 70)
        logger.info("流式输出统计:")
        logger.info(f"  - 节点事件: {len(node_events)}")
        logger.info(f"  - Token 数量: {token_count}")
        logger.info(f"  - Token 内容长度: {len(''.join(token_content))} 字符")
        logger.info(f"  - 总耗时: {elapsed:.2f}s")
        logger.info(f"  - 节点执行顺序: {' -> '.join([e.split('] ')[1] for e in node_events if 'START' in e])}")
        
        results.add(
            module, "workflow_streaming", True,
            elapsed,
            f"流式输出正常: {len(node_events)} 节点事件, {token_count} tokens",
            {
                "node_events": node_events,
                "token_count": token_count,
                "token_content_length": len(''.join(token_content)),
            }
        )
        return True
        
    except Exception as e:
        import traceback
        results.add(
            module, "workflow_streaming", False,
            time.time() - start,
            f"{str(e)}\n{traceback.format_exc()}"
        )
        return False


# ═══════════════════════════════════════════════════════════════════════════
# 2. 完整工作流测试
# ═══════════════════════════════════════════════════════════════════════════

async def test_complete_workflow(results: TestResults, auth_ctx: Any) -> Dict[str, Any]:
    """
    测试完整的端到端工作流
    
    工作流节点：
    1. SemanticParser - 语义解析，输出 SemanticQuery
    2. FieldMapper - 字段映射（RAG + LLM），输出 MappedQuery
    3. QueryBuilder - 构建 VizQL 查询
    4. Execute - 执行查询
    5. Insight - 洞察分析
    6. Replanner - 重规划决策
    """
    module = "workflow"
    
    if auth_ctx is None:
        results.add(module, "complete_workflow", False, 0, "认证上下文未获取")
        return {}
    
    datasource_luid = os.getenv("DATASOURCE_LUID", "")
    if not datasource_luid:
        results.add(module, "complete_workflow", False, 0, "DATASOURCE_LUID 未配置")
        return {}
    
    workflow_results = {}
    
    try:
        from tableau_assistant.src.orchestration.workflow.factory import create_workflow
        from tableau_assistant.src.orchestration.workflow.context import (
            WorkflowContext,
            create_workflow_config,
        )
        from tableau_assistant.src.orchestration.workflow.factory import inject_middleware_to_config
        from tableau_assistant.src.infra.storage import get_langgraph_store, DataModelCache
        from tableau_assistant.src.infra.storage.data_model_loader import TableauDataModelLoader
        
        # ========== 1. 创建工作流 ==========
        start = time.time()
        workflow = create_workflow(use_memory_checkpointer=True)
        results.add(module, "1_create_workflow", True, time.time() - start, "工作流创建成功")
        
        # ========== 2. 创建上下文并加载元数据 ==========
        start = time.time()
        store = get_langgraph_store()
        cache = DataModelCache(store)
        loader = TableauDataModelLoader(auth_ctx)
        data_model, is_cache_hit = await cache.get_or_load(datasource_luid, loader)
        
        ctx = WorkflowContext(
            auth=auth_ctx,
            datasource_luid=datasource_luid,
            data_model=data_model,
        )
        
        assert ctx.data_model is not None, "数据模型加载失败"
        
        results.add(
            module, "2_load_metadata", True,
            time.time() - start,
            f"数据模型加载成功: {data_model.field_count} 个字段, "
            f"{len(data_model.get_dimensions())} 维度, {len(data_model.get_measures())} 度量"
        )
        workflow_results["data_model"] = data_model
        
        # ========== 3. 执行完整工作流 ==========
        test_question = "各省份的销售额是多少？"
        
        start = time.time()
        config = create_workflow_config("test_thread_" + str(int(time.time())), ctx)
        
        # 注入 middleware
        if hasattr(workflow, 'middleware'):
            config = inject_middleware_to_config(config, workflow.middleware)
        
        initial_state = {
            "question": test_question,
            "messages": [],
        }
        
        logger.info(f"\n{'='*60}")
        logger.info(f"执行工作流: {test_question}")
        logger.info(f"{'='*60}")
        
        # 执行工作流
        final_state = await workflow.ainvoke(initial_state, config)
        total_elapsed = time.time() - start
        
        results.add(
            module, "3_workflow_invoke", True,
            total_elapsed,
            f"工作流执行完成, 总耗时: {total_elapsed:.2f}s"
        )
        
        # ========== 4. 检查各节点输出 ==========
        
        # 4.1 SemanticParser 输出
        semantic_query = final_state.get("semantic_query")
        if semantic_query:
            dims = len(semantic_query.dimensions or [])
            measures = len(semantic_query.measures or [])
            results.add(
                module, "4.1_semantic_parser", True, 0,
                f"语义解析完成: {dims} 维度, {measures} 度量",
                {
                    "dimensions": [d.field_name for d in (semantic_query.dimensions or [])],
                    "measures": [m.field_name for m in (semantic_query.measures or [])],
                }
            )
            workflow_results["semantic_query"] = semantic_query
        else:
            results.add(module, "4.1_semantic_parser", False, 0, "semantic_query 为空")
        
        # 4.2 FieldMapper 输出
        mapped_query = final_state.get("mapped_query")
        if mapped_query:
            mappings = mapped_query.field_mappings
            mapping_details = {
                term: f"{fm.technical_field} ({fm.mapping_source})"
                for term, fm in mappings.items()
            }
            results.add(
                module, "4.2_field_mapper", True, 0,
                f"字段映射完成: {len(mappings)} 个字段, 整体置信度: {mapped_query.overall_confidence:.2f}",
                {"mappings": mapping_details}
            )
            workflow_results["mapped_query"] = mapped_query
        else:
            results.add(module, "4.2_field_mapper", False, 0, "mapped_query 为空")
        
        # 4.3 QueryBuilder 输出
        vizql_query = final_state.get("vizql_query")
        if vizql_query:
            results.add(
                module, "4.3_query_builder", True, 0,
                f"VizQL 查询构建完成",
                {"query_keys": list(vizql_query.keys()) if isinstance(vizql_query, dict) else "N/A"}
            )
            workflow_results["vizql_query"] = vizql_query
        else:
            results.add(module, "4.3_query_builder", False, 0, "vizql_query 为空")
        
        # 4.4 Execute 输出
        query_result = final_state.get("query_result")
        if query_result:
            # query_result 可能是 Pydantic 对象或 dict
            if hasattr(query_result, 'data'):
                row_count = len(query_result.data) if query_result.data else 0
            elif isinstance(query_result, dict):
                row_count = len(query_result.get("data", [])) if isinstance(query_result.get("data"), list) else 0
            else:
                row_count = 0
            results.add(
                module, "4.4_execute", True, 0,
                f"查询执行完成: {row_count} 行数据"
            )
            workflow_results["query_result"] = query_result
        else:
            results.add(module, "4.4_execute", False, 0, "query_result 为空")
        
        # 4.5 Insight 输出
        insights = final_state.get("insights")
        if insights:
            insight_count = len(insights) if isinstance(insights, list) else 0
            results.add(
                module, "4.5_insight", True, 0,
                f"洞察分析完成: {insight_count} 个洞察"
            )
            workflow_results["insights"] = insights
        else:
            results.add(module, "4.5_insight", False, 0, "insights 为空")
        
        # 4.6 Replanner 输出
        replan_decision = final_state.get("replan_decision")
        if replan_decision:
            results.add(
                module, "4.6_replanner", True, 0,
                f"重规划决策: 完成度={replan_decision.completeness_score:.1%}, "
                f"继续={replan_decision.should_replan}",
                {
                    "completeness_score": replan_decision.completeness_score,
                    "should_replan": replan_decision.should_replan,
                    "reason": replan_decision.reason,
                }
            )
            workflow_results["replan_decision"] = replan_decision
        else:
            results.add(module, "4.6_replanner", False, 0, "replan_decision 为空")
        
        # ========== 5. 检查错误 ==========
        errors = final_state.get("errors", [])
        if errors:
            for err in errors:
                results.add(
                    module, f"error_{err.get('stage', 'unknown')}", False, 0,
                    f"错误: {err.get('error', 'Unknown')}"
                )
        
        workflow_results["final_state"] = final_state
        return workflow_results
        
    except Exception as e:
        import traceback
        results.add(module, "complete_workflow", False, 0, f"{str(e)}\n{traceback.format_exc()}")
        return workflow_results


# ═══════════════════════════════════════════════════════════════════════════
# 3. 单独组件测试（可选）
# ═══════════════════════════════════════════════════════════════════════════

async def test_data_model_cache(results: TestResults) -> None:
    """测试数据模型缓存"""
    module = "component"
    
    try:
        from tableau_assistant.src.infra.storage.langgraph_store import (
            get_langgraph_store,
            reset_langgraph_store,
        )
        from tableau_assistant.src.infra.storage.data_model_cache import DataModelCache
        
        reset_langgraph_store()
        store = get_langgraph_store()
        cache = DataModelCache(store)
        
        start = time.time()
        # 测试缓存未命中
        cached = cache._get_from_cache("non_existent_ds")
        assert cached is None, "缓存应该为空"
        
        results.add(module, "data_model_cache", True, time.time() - start, "数据模型缓存正常")
        
    except Exception as e:
        results.add(module, "data_model_cache", False, 0, str(e))


async def test_middleware_stack(results: TestResults) -> None:
    """测试中间件栈"""
    module = "component"
    
    try:
        from tableau_assistant.src.orchestration.workflow.factory import (
            create_middleware_stack,
            get_default_config,
        )
        
        start = time.time()
        config = get_default_config()
        middleware = create_middleware_stack(config=config)
        
        assert len(middleware) > 0, "中间件栈为空"
        
        middleware_names = [type(m).__name__ for m in middleware]
        
        results.add(
            module, "middleware_stack", True,
            time.time() - start,
            f"{len(middleware)} 个中间件: {', '.join(middleware_names)}"
        )
        
    except Exception as e:
        results.add(module, "middleware_stack", False, 0, str(e))


# ═══════════════════════════════════════════════════════════════════════════
# 主测试函数
# ═══════════════════════════════════════════════════════════════════════════

async def run_all_tests():
    """运行所有集成测试"""
    logger.info("=" * 70)
    logger.info("后端功能完整集成测试 - 端到端工作流")
    logger.info("=" * 70)
    
    results = TestResults()
    
    # 检查环境配置
    datasource_luid = os.getenv("DATASOURCE_LUID", "")
    tableau_domain = os.getenv("TABLEAU_DOMAIN", "")
    llm_provider = os.getenv("LLM_MODEL_PROVIDER", "")
    
    logger.info(f"Tableau Domain: {tableau_domain}")
    logger.info(f"Datasource LUID: {datasource_luid}")
    logger.info(f"LLM Provider: {llm_provider}")
    logger.info("-" * 70)
    
    # ========== 1. 基础设施测试 ==========
    logger.info("\n[1/5] 测试基础设施...")
    
    auth_ctx = await test_tableau_auth(results)
    await test_store_manager(results)
    await test_llm_connection(results)
    
    # ========== 2. LLM 流式输出测试 ==========
    logger.info("\n[2/5] 测试 LLM 流式输出...")
    await test_llm_streaming(results)
    
    # ========== 3. 工作流流式输出测试（正式功能）==========
    logger.info("\n[3/6] 测试工作流流式输出（正式功能）...")
    await test_workflow_streaming(results, auth_ctx)
    
    # ========== 4. 完整工作流测试 ==========
    logger.info("\n[4/6] 测试完整工作流...")
    
    workflow_results = await test_complete_workflow(results, auth_ctx)
    
    # ========== 5. 组件测试 ==========
    logger.info("\n[5/6] 测试组件...")
    
    await test_data_model_cache(results)
    await test_middleware_stack(results)
    
    # ========== 6. 输出测试结果 ==========
    logger.info("\n[6/6] 测试结果汇总...")
    
    summary = results.summary()
    
    logger.info("\n" + "=" * 70)
    logger.info("测试结果汇总")
    logger.info("=" * 70)
    logger.info(f"总计: {summary['total']} 个测试")
    logger.info(f"通过: {summary['passed']} ({summary['pass_rate']})")
    logger.info(f"失败: {summary['failed']}")
    logger.info(f"总耗时: {summary['total_time']}")
    
    logger.info("\n按模块统计:")
    for module, stats in summary["by_module"].items():
        logger.info(f"  {module}: {stats['passed']} 通过, {stats['failed']} 失败")
    
    if summary["failed_tests"]:
        logger.info("\n失败的测试:")
        for test in summary["failed_tests"]:
            logger.info(f"  ❌ [{test['module']}] {test['test_name']}: {test['message']}")
    
    # 输出工作流结果摘要
    if workflow_results:
        logger.info("\n" + "=" * 70)
        logger.info("工作流执行结果摘要")
        logger.info("=" * 70)
        
        if "semantic_query" in workflow_results:
            sq = workflow_results["semantic_query"]
            logger.info(f"SemanticQuery: {len(sq.dimensions or [])} 维度, {len(sq.measures or [])} 度量")
        
        if "mapped_query" in workflow_results:
            mq = workflow_results["mapped_query"]
            logger.info(f"MappedQuery: {len(mq.field_mappings)} 个字段映射, 置信度: {mq.overall_confidence:.2f}")
            for term, fm in mq.field_mappings.items():
                logger.info(f"  {term} -> {fm.technical_field} ({fm.mapping_source}, {fm.confidence:.2f})")
        
        if "query_result" in workflow_results:
            qr = workflow_results["query_result"]
            # query_result 可能是 Pydantic 对象或 dict
            if hasattr(qr, 'data'):
                row_count = len(qr.data) if qr.data else 0
            elif isinstance(qr, dict):
                row_count = len(qr.get("data", [])) if isinstance(qr.get("data"), list) else 0
            else:
                row_count = 0
            logger.info(f"QueryResult: {row_count} 行数据")
        
        if "insights" in workflow_results:
            insights = workflow_results["insights"]
            logger.info(f"Insights: {len(insights) if isinstance(insights, list) else 0} 个洞察")
        
        if "replan_decision" in workflow_results:
            rd = workflow_results["replan_decision"]
            logger.info(f"ReplanDecision: 完成度={rd.completeness_score:.1%}, 继续={rd.should_replan}")
    
    return summary


# ═══════════════════════════════════════════════════════════════════════════
# 入口点
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    summary = asyncio.run(run_all_tests())
    
    # 根据测试结果设置退出码
    exit_code = 0 if summary["failed"] == 0 else 1
    sys.exit(exit_code)
