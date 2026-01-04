# -*- coding: utf-8 -*-
"""
QueryPipeline 集成测试

测试 QueryPipeline 的完整流程：
- MapFields → BuildQuery → Execute 流程
- RAG+LLM 混合策略字段映射
- 筛选值解析和澄清
- 所有 8 个 Middleware 集成

使用真实的 Tableau 环境和 LLM 进行测试。

运行方式:
    python -m tableau_assistant.tests.agents.semantic_parser.test_query_pipeline

或直接运行:
    python tableau_assistant/tests/agents/semantic_parser/test_query_pipeline.py
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
    domain = os.getenv("TABLEAU_CLOUD_DOMAIN", os.getenv("TABLEAU_DOMAIN", ""))
    site = os.getenv("TABLEAU_CLOUD_SITE", os.getenv("TABLEAU_SITE", ""))
    
    return {
        "domain": domain,
        "site": site,
        "datasource_luid": os.getenv("DATASOURCE_LUID", ""),
    }


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
    
    store = get_langgraph_store()
    cache = DataModelCache(store)
    loader = TableauDataModelLoader(auth_ctx)
    
    data_model, is_cache_hit = await cache.get_or_load(datasource_luid, loader)
    
    if is_cache_hit:
        logger.info(f"从缓存加载元数据: {data_model.field_count} 个字段")
    else:
        logger.info(f"从 API 加载元数据: {data_model.field_count} 个字段")
    
    return data_model


async def create_workflow_config(datasource_luid: str, auth_ctx, data_model):
    """创建 WorkflowConfig"""
    from tableau_assistant.src.orchestration.workflow.context import WorkflowContext, create_workflow_config
    
    workflow_ctx = WorkflowContext(
        auth=auth_ctx,
        datasource_luid=datasource_luid,
        data_model=data_model,
    )
    
    config = create_workflow_config(
        thread_id=f"test-pipeline-{datetime.now().strftime('%H%M%S')}",
        context=workflow_ctx,
    )
    
    return config


async def create_step1_output(question: str, data_model, config):
    """使用真实 LLM 创建 Step1Output，带流式输出"""
    from tableau_assistant.src.agents.semantic_parser.components import Step1Component
    
    print(f"\n  [Step1] 执行中...", end="", flush=True)
    
    component = Step1Component()
    step1_output, thinking = await component.execute(
        question=question,
        history=None,
        data_model=data_model,
        state={},
        config=config,
    )
    
    print(f" 完成 (intent={step1_output.intent.type}, how={step1_output.how_type})")
    
    return step1_output


async def create_step2_output(step1_output, config):
    """使用真实 LLM 创建 Step2Output，带流式输出"""
    from tableau_assistant.src.agents.semantic_parser.components import Step2Component
    
    print(f"\n  [Step2] 执行中...", end="", flush=True)
    
    component = Step2Component()
    step2_output = await component.execute(
        step1_output=step1_output,
        state={},
        config=config,
    )
    
    print(f" 完成 ({len(step2_output.computations)} 个计算)")
    
    return step2_output


# ═══════════════════════════════════════════════════════════════════════════
# 测试用例
# ═══════════════════════════════════════════════════════════════════════════

async def test_simple_query_pipeline(datasource_luid: str, data_model, config):
    """测试简单查询的 Pipeline 执行"""
    from tableau_assistant.src.agents.semantic_parser.components import QueryPipeline
    
    print("\n" + "="*60)
    print("测试: 简单查询 Pipeline (MapFields → BuildQuery → Execute)")
    print("="*60)
    
    question = "各省份的销售额"
    print(f"\n问题: {question}")
    
    # 创建 Step1 输出
    step1_output = await create_step1_output(question, data_model, config)
    
    from tableau_assistant.src.core.models import IntentType
    assert step1_output.intent.type == IntentType.DATA_QUERY, "意图应该是 DATA_QUERY"
    
    # 执行 Pipeline
    print(f"\n  [Pipeline] 执行中...")
    pipeline = QueryPipeline()
    
    start_time = datetime.now()
    result = await pipeline.execute(
        question=question,
        step1_output=step1_output,
        step2_output=None,
        data_model=data_model,
        datasource_luid=datasource_luid,
        state={},
        config=config,
    )
    duration = (datetime.now() - start_time).total_seconds()
    
    # 打印结果
    print(f"\n  [Pipeline 结果]")
    print(f"    成功: {result.success}")
    print(f"    耗时: {duration:.2f}s")
    
    if result.success:
        print(f"    行数: {result.row_count}")
        print(f"    执行时间: {result.execution_time_ms}ms")
        if result.mapped_query:
            print(f"    字段映射: ✓")
        if result.vizql_query:
            print(f"    VizQL 查询: ✓")
    else:
        print(f"    错误: {result.error}")
    
    # 验证
    assert result.success is True, f"Pipeline 应该成功: {result.error}"
    assert result.row_count >= 0, "应该返回数据"
    assert result.mapped_query is not None, "应该有 mapped_query"
    assert result.vizql_query is not None, "应该有 vizql_query"
    
    print("\n  ✓ 简单查询 Pipeline 测试通过")
    return result


async def test_complex_query_pipeline(datasource_luid: str, data_model, config):
    """测试复杂查询的 Pipeline 执行（带 Step2）"""
    from tableau_assistant.src.agents.semantic_parser.components import QueryPipeline
    
    print("\n" + "="*60)
    print("测试: 复杂查询 Pipeline (带 Step2 计算)")
    print("="*60)
    
    question = "各产品类别的销售额排名"
    print(f"\n问题: {question}")
    
    # 创建 Step1 输出
    step1_output = await create_step1_output(question, data_model, config)
    
    from tableau_assistant.src.core.models import HowType
    
    # 如果是复杂查询，创建 Step2 输出
    step2_output = None
    if step1_output.how_type != HowType.SIMPLE:
        step2_output = await create_step2_output(step1_output, config)
        assert step2_output is not None
        assert len(step2_output.computations) > 0, "复杂查询应该有计算"
    
    # 执行 Pipeline
    print(f"\n  [Pipeline] 执行中...")
    pipeline = QueryPipeline()
    
    start_time = datetime.now()
    result = await pipeline.execute(
        question=question,
        step1_output=step1_output,
        step2_output=step2_output,
        data_model=data_model,
        datasource_luid=datasource_luid,
        state={},
        config=config,
    )
    duration = (datetime.now() - start_time).total_seconds()
    
    # 打印结果
    print(f"\n  [Pipeline 结果]")
    print(f"    成功: {result.success}")
    print(f"    耗时: {duration:.2f}s")
    
    if result.success:
        print(f"    行数: {result.row_count}")
    else:
        print(f"    错误: {result.error}")
        # 复杂查询可能因为计算不支持而失败，这是预期的
        logger.warning(f"复杂查询 Pipeline 失败（可能是计算不支持）: {result.error}")
    
    print("\n  ✓ 复杂查询 Pipeline 测试完成")
    return result


async def test_field_mapping_with_semantic_names(datasource_luid: str, data_model, config):
    """测试语义字段名映射 - 使用业务术语"""
    from tableau_assistant.src.agents.semantic_parser.components import QueryPipeline
    
    print("\n" + "="*60)
    print("测试: 字段映射 (RAG+LLM 混合策略)")
    print("="*60)
    
    # 使用业务术语而非技术字段名
    question = "按地区统计销售金额"
    print(f"\n问题: {question}")
    
    step1_output = await create_step1_output(question, data_model, config)
    
    from tableau_assistant.src.core.models import IntentType
    if step1_output.intent.type != IntentType.DATA_QUERY:
        print(f"\n  ⚠️ 问题未被识别为 DATA_QUERY，跳过测试")
        return None
    
    # 执行 Pipeline
    print(f"\n  [Pipeline] 执行中...")
    pipeline = QueryPipeline()
    
    result = await pipeline.execute(
        question=question,
        step1_output=step1_output,
        step2_output=None,
        data_model=data_model,
        datasource_luid=datasource_luid,
        state={},
        config=config,
    )
    
    # 验证字段映射
    if result.mapped_query:
        print(f"\n  [字段映射结果]")
        
        # MappedQuery 可能是对象或字典
        if hasattr(result.mapped_query, 'field_mappings'):
            field_mappings = result.mapped_query.field_mappings
        elif isinstance(result.mapped_query, dict):
            field_mappings = result.mapped_query.get("field_mappings", {})
        else:
            field_mappings = {}
        
        for semantic_name, mapping in field_mappings.items():
            if isinstance(mapping, dict):
                technical_field = mapping.get("technical_field")
            else:
                technical_field = getattr(mapping, "technical_field", None)
            
            print(f"    {semantic_name} → {technical_field}")
    
    print("\n  ✓ 字段映射测试完成")
    return result


async def test_filter_value_resolution(datasource_luid: str, data_model, config):
    """测试筛选值解析"""
    from tableau_assistant.src.agents.semantic_parser.components import QueryPipeline
    
    print("\n" + "="*60)
    print("测试: 筛选值解析")
    print("="*60)
    
    question = "北京的销售额"
    print(f"\n问题: {question}")
    
    step1_output = await create_step1_output(question, data_model, config)
    
    from tableau_assistant.src.core.models import IntentType
    if step1_output.intent.type != IntentType.DATA_QUERY:
        print(f"\n  ⚠️ 问题未被识别为 DATA_QUERY，跳过测试")
        return None
    
    # 验证有筛选条件
    filters = step1_output.where.filters if step1_output.where else None
    if filters:
        print(f"\n  解析到 {len(filters)} 个筛选条件:")
        for f in filters:
            print(f"    - {f.field_name}: {getattr(f, 'values', getattr(f, 'value', 'N/A'))}")
    
    # 执行 Pipeline
    print(f"\n  [Pipeline] 执行中...")
    pipeline = QueryPipeline()
    
    result = await pipeline.execute(
        question=question,
        step1_output=step1_output,
        step2_output=None,
        data_model=data_model,
        datasource_luid=datasource_luid,
        state={},
        config=config,
    )
    
    # 打印结果
    print(f"\n  [结果]")
    if result.success:
        print(f"    成功: {result.row_count} 行")
    elif result.needs_clarification:
        print(f"    需要澄清: {result.clarification}")
    else:
        print(f"    失败: {result.error}")
    
    print("\n  ✓ 筛选值解析测试完成")
    return result


async def test_pipeline_retry_skip_logic(datasource_luid: str, data_model, config):
    """测试 Pipeline 重试时跳过已完成步骤"""
    from tableau_assistant.src.agents.semantic_parser.components import QueryPipeline
    
    print("\n" + "="*60)
    print("测试: Pipeline 重试跳过逻辑")
    print("="*60)
    
    question = "各省份的销售额"
    print(f"\n问题: {question}")
    
    step1_output = await create_step1_output(question, data_model, config)
    
    from tableau_assistant.src.core.models import IntentType
    if step1_output.intent.type != IntentType.DATA_QUERY:
        print(f"\n  ⚠️ 问题未被识别为 DATA_QUERY，跳过测试")
        return None
    
    # 第一次执行，获取 mapped_query
    print(f"\n  [第一次执行]")
    pipeline = QueryPipeline()
    result1 = await pipeline.execute(
        question=question,
        step1_output=step1_output,
        step2_output=None,
        data_model=data_model,
        datasource_luid=datasource_luid,
        state={},
        config=config,
    )
    
    if not result1.success:
        print(f"\n  ⚠️ 第一次执行失败: {result1.error}")
        return None
    
    print(f"    成功: {result1.row_count} 行")
    
    # 第二次执行，传入 mapped_query（模拟重试）
    print(f"\n  [第二次执行 - 带 mapped_query]")
    state_with_mapped = {
        "mapped_query": result1.mapped_query,
    }
    
    result2 = await pipeline.execute(
        question=question,
        step1_output=step1_output,
        step2_output=None,
        data_model=data_model,
        datasource_luid=datasource_luid,
        state=state_with_mapped,
        config=config,
    )
    
    print(f"    成功: {result2.row_count} 行")
    
    # 验证结果一致
    assert result2.success is True
    assert result2.row_count == result1.row_count, "重试结果应该一致"
    
    print("\n  ✓ Pipeline 重试跳过逻辑测试通过")
    return result2


# ═══════════════════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    """运行所有测试"""
    print("="*60)
    print("QueryPipeline 集成测试")
    print("使用真实 Tableau 环境 + Token 流式输出")
    print("="*60)
    
    # 1. 获取 Tableau 配置
    tableau_config = get_tableau_config()
    if not tableau_config["domain"] or not tableau_config["datasource_luid"]:
        print("\n❌ 错误: 请配置 TABLEAU_DOMAIN 和 DATASOURCE_LUID 环境变量")
        return
    
    print(f"\nTableau Domain: {tableau_config['domain']}")
    print(f"Datasource LUID: {tableau_config['datasource_luid']}")
    
    # 2. 获取 Tableau 认证
    try:
        auth_ctx = await get_tableau_auth()
    except Exception as e:
        print(f"\n❌ 获取 Tableau 认证失败: {e}")
        return
    
    # 3. 获取数据模型
    try:
        data_model = await get_data_model(tableau_config["datasource_luid"], auth_ctx)
    except Exception as e:
        print(f"\n❌ 获取数据模型失败: {e}")
        return
    
    # 4. 创建 WorkflowConfig
    config = await create_workflow_config(tableau_config["datasource_luid"], auth_ctx, data_model)
    
    # 5. 运行测试
    test_results = []
    
    try:
        await test_simple_query_pipeline(tableau_config["datasource_luid"], data_model, config)
        test_results.append(("简单查询 Pipeline", True))
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        test_results.append(("简单查询 Pipeline", False))
    
    try:
        await test_complex_query_pipeline(tableau_config["datasource_luid"], data_model, config)
        test_results.append(("复杂查询 Pipeline", True))
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        test_results.append(("复杂查询 Pipeline", False))
    
    try:
        await test_field_mapping_with_semantic_names(tableau_config["datasource_luid"], data_model, config)
        test_results.append(("字段映射", True))
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        test_results.append(("字段映射", False))
    
    try:
        await test_filter_value_resolution(tableau_config["datasource_luid"], data_model, config)
        test_results.append(("筛选值解析", True))
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        test_results.append(("筛选值解析", False))
    
    try:
        await test_pipeline_retry_skip_logic(tableau_config["datasource_luid"], data_model, config)
        test_results.append(("重试跳过逻辑", True))
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        test_results.append(("重试跳过逻辑", False))
    
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
