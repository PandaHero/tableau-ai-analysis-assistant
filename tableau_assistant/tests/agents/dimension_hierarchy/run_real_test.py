# -*- coding: utf-8 -*-
"""
维度层级推断真实环境测试脚本

直接运行，查看完整输出：
    python -m tableau_assistant.tests.agents.dimension_hierarchy.run_real_test
"""
import asyncio
import os
import sys
from datetime import datetime

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from dotenv import load_dotenv
load_dotenv()

# 设置日志级别为 INFO（减少噪音）
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
# 降低一些噪音日志
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("faiss").setLevel(logging.WARNING)
logging.getLogger("langchain").setLevel(logging.WARNING)


def log(msg: str, level: str = "INFO"):
    """带时间戳的日志输出"""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"\n[{ts}] [{level}] {msg}")


async def main():
    log("=" * 60)
    log("维度层级推断 - 真实环境测试")
    log("=" * 60)
    
    # ═══════════════════════════════════════════════════════════════
    # 1. 获取 Tableau 认证
    # ═══════════════════════════════════════════════════════════════
    log("步骤 1: 获取 Tableau 认证...")
    start = datetime.now()
    
    from tableau_assistant.src.platforms.tableau.auth import get_tableau_auth_async
    auth_ctx = await get_tableau_auth_async()
    
    elapsed = (datetime.now() - start).total_seconds()
    log(f"  认证成功 (方式: {auth_ctx.auth_method}) - {elapsed:.2f}s")
    
    # ═══════════════════════════════════════════════════════════════
    # 2. 获取数据源 LUID
    # ═══════════════════════════════════════════════════════════════
    log("步骤 2: 获取数据源 LUID...")
    start = datetime.now()
    
    datasource_name = os.getenv("datasource_name", "Superstore Datasource")
    datasource_luid = os.getenv("DATASOURCE_LUID", "")
    
    if not datasource_luid:
        from tableau_assistant.src.platforms.tableau import get_datasource_luid_by_name
        domain = os.getenv("TABLEAU_DOMAIN", "")
        site = os.getenv("TABLEAU_SITE", "")
        
        datasource_luid = await asyncio.to_thread(
            get_datasource_luid_by_name,
            auth_ctx.api_key,
            domain,
            datasource_name,
            site,
        )
    
    elapsed = (datetime.now() - start).total_seconds()
    log(f"  数据源: {datasource_name}")
    log(f"  LUID: {datasource_luid} - {elapsed:.2f}s")
    
    # ═══════════════════════════════════════════════════════════════
    # 3. 加载数据模型
    # ═══════════════════════════════════════════════════════════════
    log("步骤 3: 加载数据模型...")
    start = datetime.now()
    
    from tableau_assistant.src.infra.storage.langgraph_store import get_langgraph_store
    from tableau_assistant.src.infra.storage.data_model_cache import DataModelCache
    from tableau_assistant.src.platforms.tableau import TableauDataModelLoader
    
    store = get_langgraph_store()
    cache = DataModelCache(store)
    loader = TableauDataModelLoader(auth_ctx)
    
    data_model, is_cache_hit = await cache.get_or_load(datasource_luid, loader)
    
    elapsed = (datetime.now() - start).total_seconds()
    cache_status = "缓存命中" if is_cache_hit else "API 加载"
    log(f"  {cache_status}: {data_model.field_count} 个字段 - {elapsed:.2f}s")
    
    dimensions = data_model.get_dimensions()
    measures = data_model.get_measures()
    log(f"  维度: {len(dimensions)} 个, 度量: {len(measures)} 个")
    
    # 显示维度字段
    log("\n  维度字段列表:")
    for i, dim in enumerate(dimensions[:10]):
        samples = dim.sample_values[:3] if dim.sample_values else []
        log(f"    {i+1}. {dim.fieldCaption} ({dim.dataType}) - 样例: {samples}")
    if len(dimensions) > 10:
        log(f"    ... 还有 {len(dimensions) - 10} 个")
    
    # ═══════════════════════════════════════════════════════════════
    # 4. 测试 LLM 连接
    # ═══════════════════════════════════════════════════════════════
    log("")
    log("=" * 60)
    log("步骤 4: 测试 LLM 连接")
    log("=" * 60)
    
    from tableau_assistant.src.infra.ai import get_llm
    from tableau_assistant.src.infra.ai.model_manager import get_model_manager, ModelType
    
    manager = get_model_manager()
    default_llm_config = manager.get_default(ModelType.LLM)
    
    if default_llm_config:
        log(f"  默认 LLM: {default_llm_config.name}")
        log(f"  API Base: {default_llm_config.api_base}")
        log(f"  API Endpoint: {default_llm_config.api_endpoint}")
        log(f"  Model: {default_llm_config.model_name}")
    else:
        log("  未找到默认 LLM 配置!", "ERROR")
        return
    
    # 简单测试 LLM
    log("\n  测试 LLM 调用...")
    start = datetime.now()
    
    try:
        llm = get_llm()
        from langchain_core.messages import HumanMessage
        response = await llm.ainvoke([HumanMessage(content="Say 'OK'")])
        elapsed = (datetime.now() - start).total_seconds()
        log(f"  LLM 响应: {response.content[:50]}... - {elapsed:.2f}s")
    except Exception as e:
        log(f"  LLM 调用失败: {e}", "ERROR")
        return
    
    # ═══════════════════════════════════════════════════════════════
    # 5. 测试 LLM 流式输出
    # ═══════════════════════════════════════════════════════════════
    log("")
    log("=" * 60)
    log("步骤 5: 测试 LLM 流式输出")
    log("=" * 60)
    
    from tableau_assistant.src.agents.base.node import stream_llm_call
    
    # 准备测试 prompt
    test_prompt = [
        {"role": "system", "content": "你是一个数据分析助手。"},
        {"role": "user", "content": "请用一句话解释什么是维度层级。"},
    ]
    
    log("  发送测试请求...")
    print("\n  [流式输出开始] ", end="", flush=True)
    
    tokens_received = []
    async def on_token(token: str):
        tokens_received.append(token)
        print(token, end="", flush=True)
    
    start = datetime.now()
    try:
        response = await stream_llm_call(
            llm,
            test_prompt,
            print_output=False,  # 我们自己处理输出
            on_token=on_token,
        )
        elapsed = (datetime.now() - start).total_seconds()
        print(f" [流式输出结束]\n")
        log(f"  收到 {len(tokens_received)} 个 tokens, 耗时 {elapsed:.2f}s")
    except Exception as e:
        print(f" [错误: {e}]\n")
        log(f"  流式输出失败: {e}", "ERROR")
    
    # ═══════════════════════════════════════════════════════════════
    # 6. 执行维度层级推断
    # ═══════════════════════════════════════════════════════════════
    log("")
    log("=" * 60)
    log("步骤 6: 执行维度层级推断 (force_refresh=True)")
    log("=" * 60)
    start = datetime.now()
    
    from tableau_assistant.src.agents.dimension_hierarchy.node import (
        dimension_hierarchy_node,
        get_inference_stats,
        reset_inference_stats,
    )
    
    await reset_inference_stats()
    
    log(f"  开始推断 {len(dimensions)} 个维度...")
    log("  RAG 检索 → LLM 推断 → RAG 存储")
    log("")
    
    result = await dimension_hierarchy_node(
        data_model=data_model,
        datasource_luid=datasource_luid,
        force_refresh=True,
    )
    
    elapsed = (datetime.now() - start).total_seconds()
    stats = await get_inference_stats()
    
    log("")
    log("=" * 60)
    log("推断完成!")
    log("=" * 60)
    log(f"  总耗时: {elapsed:.2f}s")
    log(f"  推断维度数: {len(result.dimension_hierarchy)}")
    
    if "error" not in stats:
        log(f"  RAG 命中数: {stats.get('rag_hits', 0)}")
        log(f"  LLM 推断数: {stats.get('llm_inferences', 0)}")
        log(f"  RAG 命中率: {stats.get('rag_hit_rate', 0):.1%}")
        log(f"  RAG 存储数: {stats.get('rag_stores', 0)}")
    
    # ═══════════════════════════════════════════════════════════════
    # 7. 显示推断结果
    # ═══════════════════════════════════════════════════════════════
    log("")
    log("推断结果:")
    log("-" * 60)
    
    for field_name, attrs in result.dimension_hierarchy.items():
        conf_bar = "█" * int(attrs.level_confidence * 10)
        log(f"  {field_name}")
        log(f"    → {attrs.category_detail} | L{attrs.level} ({attrs.granularity}) | {conf_bar} {attrs.level_confidence:.0%}")
    
    log("")
    log("=" * 60)
    log("测试完成!")
    log("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
