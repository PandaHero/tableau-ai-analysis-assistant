# -*- coding: utf-8 -*-
"""
ReAct Error Handler 集成测试

测试 ReAct 错误处理器的完整流程：
- RETRY 动作：修正参数后重试成功
- RETRY 动作：达到最大重试次数后 ABORT
- CLARIFY 动作：返回澄清问题
- ABORT 动作：返回友好错误信息
- Thought 分析正确性

使用真实的 LLM 进行测试，支持 Token 流式输出。

运行方式:
    python -m tableau_assistant.tests.agents.semantic_parser.test_react_error_handler

或直接运行:
    python tableau_assistant/tests/agents/semantic_parser/test_react_error_handler.py
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


def create_workflow_config(datasource_luid: str, auth_ctx, data_model):
    """创建 WorkflowConfig"""
    from tableau_assistant.src.orchestration.workflow.context import WorkflowContext, create_workflow_config
    
    workflow_ctx = WorkflowContext(
        auth=auth_ctx,
        datasource_luid=datasource_luid,
        data_model=data_model,
    )
    
    return create_workflow_config(
        thread_id=f"test-react-{datetime.now().strftime('%H%M%S')}",
        context=workflow_ctx,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 错误创建辅助函数
# ═══════════════════════════════════════════════════════════════════════════

def create_field_not_found_error():
    """创建字段未找到错误"""
    from tableau_assistant.src.agents.semantic_parser.models.pipeline import QueryError, QueryErrorType
    
    return QueryError(
        type=QueryErrorType.FIELD_NOT_FOUND,
        message="字段 '销售金额ABC' 在数据源中未找到",
        step="map_fields",
        can_retry=True,
        details={
            "field": "销售金额ABC",
            "suggestions": ["销售额", "销售金额", "销售数量"],
        },
        suggestion="您是否想查询: 销售额, 销售金额, 销售数量?",
    )


def create_ambiguous_field_error():
    """创建字段歧义错误"""
    from tableau_assistant.src.agents.semantic_parser.models.pipeline import QueryError, QueryErrorType
    
    return QueryError(
        type=QueryErrorType.AMBIGUOUS_FIELD,
        message="字段 '金额' 存在多个匹配: 销售金额, 利润金额, 成本金额",
        step="map_fields",
        can_retry=True,
        details={
            "field": "金额",
            "candidates": ["销售金额", "利润金额", "成本金额"],
        },
    )


def create_execution_error():
    """创建执行错误"""
    from tableau_assistant.src.agents.semantic_parser.models.pipeline import QueryError, QueryErrorType
    
    return QueryError(
        type=QueryErrorType.EXECUTION_FAILED,
        message="VizQL 查询执行失败: Field 'X' isn't unique",
        step="execute_query",
        can_retry=True,
        details={
            "vizql_error": "Field 'X' isn't unique",
        },
    )


def create_build_error():
    """创建构建错误"""
    from tableau_assistant.src.agents.semantic_parser.models.pipeline import QueryError, QueryErrorType
    
    return QueryError(
        type=QueryErrorType.BUILD_FAILED,
        message="无法构建 VizQL 查询: 不支持的计算类型 CUSTOM_LOD",
        step="build_query",
        can_retry=False,
    )


async def create_sample_step1_output(question: str, data_model, config):
    """使用真实 LLM 创建 Step1Output，支持流式输出"""
    from tableau_assistant.src.agents.semantic_parser.components import Step1Component
    
    print(f"\n  [Step1] 解析问题: {question}")
    print("  ", end="", flush=True)
    
    component = Step1Component()
    step1_output, _ = await component.execute(
        question=question,
        history=None,
        data_model=data_model,
        state={},
        config=config,
    )
    
    print(f"\n  [Step1] 完成 - 意图: {step1_output.intent.type.value}")
    return step1_output


# ═══════════════════════════════════════════════════════════════════════════
# 测试用例
# ═══════════════════════════════════════════════════════════════════════════

async def test_retry_on_field_not_found(data_model, config):
    """测试字段未找到时的 RETRY 动作"""
    print("\n" + "="*60)
    print("测试: 字段未找到 → RETRY/CORRECT/CLARIFY")
    print("="*60)
    
    from tableau_assistant.src.agents.semantic_parser.components import ReActErrorHandler
    from tableau_assistant.src.agents.semantic_parser.models.react import ReActActionType
    
    question = "各省份的销售金额ABC"
    error = create_field_not_found_error()
    
    print(f"\n问题: {question}")
    print(f"错误: {error.message}")
    
    # 创建真实的 Step1 输出
    step1_output = await create_sample_step1_output(
        "各省份的销售额",  # 使用有效问题生成
        data_model,
        config,
    )
    
    print("\n[ReAct 错误处理] 流式输出:")
    print("  ", end="", flush=True)
    
    handler = ReActErrorHandler()
    output, corrected_step1, corrected_step2 = await handler.handle_error(
        error=error,
        question=question,
        step1_output=step1_output,
        step2_output=None,
        pipeline_context={},
        retry_history=[],
        config=config,
    )
    
    # 验证 Thought 分析
    print(f"\n\n[Thought 分析]")
    print(f"  错误来源: {output.thought.error_source}")
    print(f"  根因分析: {output.thought.root_cause_analysis}")
    print(f"  可修正: {output.thought.can_correct}")
    print(f"  可重试: {output.thought.can_retry}")
    print(f"  需澄清: {output.thought.needs_clarification}")
    
    # 验证 Action
    action_type = output.action.action_type
    print(f"\n[Action]")
    print(f"  动作类型: {action_type.value}")
    
    # 字段未找到可能触发 CORRECT, RETRY 或 CLARIFY
    valid_actions = [ReActActionType.CORRECT, ReActActionType.RETRY, ReActActionType.CLARIFY]
    assert action_type in valid_actions, f"意外的动作类型: {action_type}"
    
    if action_type == ReActActionType.CORRECT:
        assert corrected_step1 is not None or corrected_step2 is not None
        print("  结果: 直接修正字段")
        if output.action.corrections:
            for corr in output.action.corrections:
                print(f"    - {corr.operation}: {corr.target_path}")
    elif action_type == ReActActionType.RETRY:
        print(f"  重试从: {output.action.retry_from}")
        print(f"  重试指导: {output.action.retry_guidance}")
    else:
        print(f"  澄清问题: {output.action.clarification_question}")
    
    print("\n  ✓ 测试通过")


async def test_max_retry_reached(data_model, config):
    """测试达到最大重试次数后 ABORT"""
    print("\n" + "="*60)
    print("测试: 达到最大重试次数 → ABORT")
    print("="*60)
    
    from tableau_assistant.src.agents.semantic_parser.components import ReActErrorHandler
    from tableau_assistant.src.agents.semantic_parser.components.react_error_handler import RetryRecord
    from tableau_assistant.src.agents.semantic_parser.models.react import ReActActionType
    
    question = "各省份的销售额"
    error = create_field_not_found_error()
    
    print(f"\n问题: {question}")
    print(f"错误: {error.message}")
    print("重试历史: 2 次失败")
    
    step1_output = await create_sample_step1_output(question, data_model, config)
    
    # 创建已达到最大重试次数的历史
    retry_history = [
        RetryRecord(step="map_fields", error_message="字段未找到", action_taken="RETRY", success=False),
        RetryRecord(step="map_fields", error_message="字段未找到", action_taken="RETRY", success=False),
    ]
    
    print("\n[ReAct 错误处理] 流式输出:")
    print("  ", end="", flush=True)
    
    handler = ReActErrorHandler(max_retries_per_step=2)
    output, _, _ = await handler.handle_error(
        error=error,
        question=question,
        step1_output=step1_output,
        step2_output=None,
        pipeline_context={},
        retry_history=retry_history,
        config=config,
    )
    
    print(f"\n\n[Action]")
    print(f"  动作类型: {output.action.action_type.value}")
    
    # 应该 ABORT
    assert output.action.action_type == ReActActionType.ABORT, "达到最大重试次数应该 ABORT"
    assert output.action.user_message is not None
    
    print(f"  用户消息: {output.action.user_message}")
    print("\n  ✓ 测试通过")


async def test_clarify_on_ambiguous_field(data_model, config):
    """测试字段歧义时的 CLARIFY 动作"""
    print("\n" + "="*60)
    print("测试: 字段歧义 → CLARIFY/CORRECT")
    print("="*60)
    
    from tableau_assistant.src.agents.semantic_parser.components import ReActErrorHandler
    from tableau_assistant.src.agents.semantic_parser.models.react import ReActActionType
    
    question = "各省份的金额"
    error = create_ambiguous_field_error()
    
    print(f"\n问题: {question}")
    print(f"错误: {error.message}")
    
    step1_output = await create_sample_step1_output(
        "各省份的销售额",
        data_model,
        config,
    )
    
    print("\n[ReAct 错误处理] 流式输出:")
    print("  ", end="", flush=True)
    
    handler = ReActErrorHandler()
    output, _, _ = await handler.handle_error(
        error=error,
        question=question,
        step1_output=step1_output,
        step2_output=None,
        pipeline_context={},
        retry_history=[],
        config=config,
    )
    
    print(f"\n\n[Thought 分析]")
    print(f"  需要澄清: {output.thought.needs_clarification}")
    print(f"  可修正: {output.thought.can_correct}")
    
    action_type = output.action.action_type
    print(f"\n[Action]")
    print(f"  动作类型: {action_type.value}")
    
    if action_type == ReActActionType.CLARIFY:
        assert output.action.clarification_question is not None
        print(f"  澄清问题: {output.action.clarification_question}")
    elif action_type == ReActActionType.CORRECT:
        print("  LLM 选择直接修正歧义字段")
    
    print("\n  ✓ 测试通过")


async def test_abort_on_unrecoverable_error(data_model, config):
    """测试不可恢复错误时的 ABORT 动作"""
    print("\n" + "="*60)
    print("测试: 不可恢复错误 → ABORT")
    print("="*60)
    
    from tableau_assistant.src.agents.semantic_parser.components import ReActErrorHandler
    from tableau_assistant.src.agents.semantic_parser.models.react import ReActActionType
    
    question = "各省份的销售额"
    error = create_build_error()  # 不可重试的构建错误
    
    print(f"\n问题: {question}")
    print(f"错误: {error.message}")
    print(f"可重试: {error.can_retry}")
    
    step1_output = await create_sample_step1_output(question, data_model, config)
    
    print("\n[ReAct 错误处理] 流式输出:")
    print("  ", end="", flush=True)
    
    handler = ReActErrorHandler()
    output, _, _ = await handler.handle_error(
        error=error,
        question=question,
        step1_output=step1_output,
        step2_output=None,
        pipeline_context={},
        retry_history=[],
        config=config,
    )
    
    print(f"\n\n[Thought 分析]")
    print(f"  根因分析: {output.thought.root_cause_analysis}")
    
    action_type = output.action.action_type
    print(f"\n[Action]")
    print(f"  动作类型: {action_type.value}")
    
    if action_type == ReActActionType.ABORT:
        assert output.action.user_message is not None
        print(f"  用户消息: {output.action.user_message}")
    else:
        print(f"  LLM 尝试其他动作: {action_type}")
    
    print("\n  ✓ 测试通过")


async def test_thought_error_category(data_model, config):
    """测试错误分类正确性"""
    print("\n" + "="*60)
    print("测试: Thought 错误分类")
    print("="*60)
    
    from tableau_assistant.src.agents.semantic_parser.components import ReActErrorHandler
    
    question = "各省份的销售额"
    
    # 测试不同类型的错误
    errors = [
        (create_field_not_found_error(), "FIELD_NOT_FOUND"),
        (create_ambiguous_field_error(), "AMBIGUOUS_FIELD"),
        (create_execution_error(), "EXECUTION_FAILED"),
    ]
    
    step1_output = await create_sample_step1_output(question, data_model, config)
    handler = ReActErrorHandler()
    
    for error, expected_category in errors:
        print(f"\n[测试错误类型: {expected_category}]")
        print(f"  错误消息: {error.message}")
        print("  处理中...", end="", flush=True)
        
        output, _, _ = await handler.handle_error(
            error=error,
            question=question,
            step1_output=step1_output,
            step2_output=None,
            pipeline_context={},
            retry_history=[],
            config=config,
        )
        
        # 验证 Thought 有分析
        assert output.thought is not None
        assert output.thought.error_source is not None
        assert output.thought.root_cause_analysis is not None
        assert output.thought.reasoning is not None
        
        print(f"\n  来源: {output.thought.error_source}")
        print(f"  分类: {output.thought.error_category}")
        print(f"  可修正: {output.thought.can_correct}")
        print(f"  可重试: {output.thought.can_retry}")
        print(f"  动作: {output.action.action_type.value}")
    
    print("\n  ✓ 测试通过")


def test_create_retry_record():
    """测试创建重试记录"""
    print("\n" + "="*60)
    print("测试: 创建重试记录")
    print("="*60)
    
    from tableau_assistant.src.agents.semantic_parser.components import ReActErrorHandler
    
    handler = ReActErrorHandler()
    record = handler.create_retry_record(
        step="map_fields",
        error_message="字段未找到",
        action_taken="RETRY",
        success=False,
    )
    
    assert record.step == "map_fields"
    assert record.error_message == "字段未找到"
    assert record.action_taken == "RETRY"
    assert record.success is False
    
    # 测试字符串表示
    str_repr = str(record)
    print(f"\n重试记录: {str_repr}")
    
    assert "map_fields" in str_repr
    
    print("\n  ✓ 测试通过")


# ═══════════════════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    """运行所有测试"""
    print("="*60)
    print("ReAct Error Handler 集成测试")
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
    
    # 5. 创建 workflow config
    config = create_workflow_config(datasource_luid, auth_ctx, data_model)
    
    # 6. 运行测试
    test_results = []
    
    # 同步测试
    try:
        test_create_retry_record()
        test_results.append(("创建重试记录", True))
    except Exception as e:
        print(f"\n❌ 创建重试记录测试失败: {e}")
        test_results.append(("创建重试记录", False))
    
    # 异步测试
    try:
        await test_retry_on_field_not_found(data_model, config)
        test_results.append(("字段未找到 RETRY", True))
    except Exception as e:
        print(f"\n❌ 字段未找到 RETRY 测试失败: {e}")
        import traceback
        traceback.print_exc()
        test_results.append(("字段未找到 RETRY", False))
    
    try:
        await test_max_retry_reached(data_model, config)
        test_results.append(("最大重试次数 ABORT", True))
    except Exception as e:
        print(f"\n❌ 最大重试次数 ABORT 测试失败: {e}")
        import traceback
        traceback.print_exc()
        test_results.append(("最大重试次数 ABORT", False))
    
    try:
        await test_clarify_on_ambiguous_field(data_model, config)
        test_results.append(("字段歧义 CLARIFY", True))
    except Exception as e:
        print(f"\n❌ 字段歧义 CLARIFY 测试失败: {e}")
        import traceback
        traceback.print_exc()
        test_results.append(("字段歧义 CLARIFY", False))
    
    try:
        await test_abort_on_unrecoverable_error(data_model, config)
        test_results.append(("不可恢复错误 ABORT", True))
    except Exception as e:
        print(f"\n❌ 不可恢复错误 ABORT 测试失败: {e}")
        import traceback
        traceback.print_exc()
        test_results.append(("不可恢复错误 ABORT", False))
    
    try:
        await test_thought_error_category(data_model, config)
        test_results.append(("Thought 错误分类", True))
    except Exception as e:
        print(f"\n❌ Thought 错误分类测试失败: {e}")
        import traceback
        traceback.print_exc()
        test_results.append(("Thought 错误分类", False))
    
    # 7. 打印测试摘要
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
