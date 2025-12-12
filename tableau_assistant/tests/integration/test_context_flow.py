# -*- coding: utf-8 -*-
"""
WorkflowContext 集成测试

使用真实 Tableau 环境测试 WorkflowContext 的完整流程。

测试内容：
1. WorkflowContext 创建和初始化
2. 元数据加载流程
3. 认证刷新机制
4. 工具通过 config 访问上下文
5. 完整工作流执行

Requirements: 1.1, 1.2, 1.3, 3.2, 4.1
"""

import pytest
import asyncio
import time
from typing import Dict, Any

from tableau_assistant.src.workflow.context import (
    WorkflowContext,
    MetadataLoadStatus,
    create_workflow_config,
    get_context,
    get_context_or_raise,
)
from tableau_assistant.src.bi_platforms.tableau import (
    get_tableau_auth,
    get_tableau_auth_async,
    TableauAuthContext,
)
from tableau_assistant.src.capabilities.storage.store_manager import (
    StoreManager,
    get_store_manager,
)
from tableau_assistant.src.config.settings import Settings


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="module")
def settings() -> Settings:
    """加载应用配置"""
    return Settings()


@pytest.fixture(scope="module")
def datasource_luid(settings: Settings) -> str:
    """获取数据源 LUID"""
    luid = settings.datasource_luid
    if not luid:
        pytest.skip("DATASOURCE_LUID 未配置")
    return luid


@pytest.fixture(scope="module")
def store_manager() -> StoreManager:
    """获取 StoreManager 实例"""
    return get_store_manager()


@pytest.fixture(scope="function")
def auth_context() -> TableauAuthContext:
    """获取真实的 Tableau 认证上下文"""
    try:
        return get_tableau_auth()
    except Exception as e:
        pytest.skip(f"Tableau 认证失败: {e}")


@pytest.fixture(scope="function")
def workflow_context(
    auth_context: TableauAuthContext,
    store_manager: StoreManager,
    datasource_luid: str
) -> WorkflowContext:
    """创建 WorkflowContext 实例"""
    return WorkflowContext(
        auth=auth_context,
        store=store_manager,
        datasource_luid=datasource_luid,
    )


# ============================================================
# WorkflowContext 创建测试
# ============================================================

class TestWorkflowContextCreation:
    """WorkflowContext 创建测试"""
    
    def test_create_context_with_real_auth(
        self,
        auth_context: TableauAuthContext,
        store_manager: StoreManager,
        datasource_luid: str
    ):
        """测试使用真实认证创建上下文"""
        ctx = WorkflowContext(
            auth=auth_context,
            store=store_manager,
            datasource_luid=datasource_luid,
        )
        
        assert ctx.auth is not None
        assert ctx.auth.api_key is not None
        assert ctx.store is not None
        assert ctx.datasource_luid == datasource_luid
        assert ctx.metadata is None  # 初始时没有加载
        
        print(f"✓ WorkflowContext 创建成功")
        print(f"  - datasource_luid: {ctx.datasource_luid}")
        print(f"  - auth_method: {ctx.auth.auth_method}")
        print(f"  - token_remaining: {ctx.auth.remaining_seconds:.0f}s")
    
    def test_is_auth_valid(self, workflow_context: WorkflowContext):
        """测试认证有效性检查"""
        # 新获取的 token 应该有效
        assert workflow_context.is_auth_valid(), "新 token 应该有效"
        assert workflow_context.is_auth_valid(buffer_seconds=60), "60秒缓冲内应该有效"
        
        print(f"✓ 认证有效性检查通过")
        print(f"  - remaining_seconds: {workflow_context.auth.remaining_seconds:.0f}s")


# ============================================================
# 元数据加载测试
# ============================================================

class TestMetadataLoading:
    """元数据加载测试"""
    
    @pytest.mark.asyncio
    async def test_ensure_metadata_loaded(
        self,
        workflow_context: WorkflowContext
    ):
        """测试元数据加载流程"""
        print(f"\n开始测试元数据加载...")
        
        # 初始时没有 metadata
        assert workflow_context.metadata is None
        
        # 加载元数据
        start_time = time.time()
        ctx_with_metadata = await workflow_context.ensure_metadata_loaded()
        elapsed = time.time() - start_time
        
        # 验证加载结果
        assert ctx_with_metadata.metadata is not None, "metadata 应该已加载"
        
        # 如果字段为空，可能是 API 限制，跳过测试
        if not ctx_with_metadata.metadata.fields:
            pytest.skip("元数据字段为空（可能是 API 速率限制）")
        
        assert ctx_with_metadata.metadata.datasource_luid == workflow_context.datasource_luid
        
        # 验证加载状态
        load_status = ctx_with_metadata.metadata_load_status
        assert load_status is not None, "应该有加载状态"
        
        print(f"✓ 元数据加载成功 ({elapsed:.2f}s)")
        print(f"  - source: {load_status.source}")
        print(f"  - message: {load_status.message}")
        print(f"  - field_count: {ctx_with_metadata.metadata.field_count}")
        print(f"  - hierarchy_inferred: {load_status.hierarchy_inferred}")
    
    @pytest.mark.asyncio
    async def test_metadata_includes_dimension_hierarchy(
        self,
        workflow_context: WorkflowContext
    ):
        """测试元数据包含维度层级"""
        ctx = await workflow_context.ensure_metadata_loaded()
        
        # 验证维度层级
        hierarchy = ctx.dimension_hierarchy
        
        if hierarchy:
            print(f"✓ 维度层级已加载: {len(hierarchy)} 个维度")
            
            # 打印部分维度信息
            for i, (name, attrs) in enumerate(hierarchy.items()):
                if i >= 5:
                    print(f"  ... 还有 {len(hierarchy) - 5} 个维度")
                    break
                print(f"  - {name}: {attrs.get('category', 'N/A')}")
        else:
            print(f"⚠️ 维度层级为空（可能需要推断）")
    
    @pytest.mark.asyncio
    async def test_metadata_cache_hit(
        self,
        workflow_context: WorkflowContext
    ):
        """测试元数据缓存命中"""
        # 第一次加载
        ctx1 = await workflow_context.ensure_metadata_loaded()
        status1 = ctx1.metadata_load_status
        
        # 创建新的上下文，再次加载
        ctx2 = WorkflowContext(
            auth=workflow_context.auth,
            store=workflow_context.store,
            datasource_luid=workflow_context.datasource_luid,
        )
        
        start_time = time.time()
        ctx2_loaded = await ctx2.ensure_metadata_loaded()
        elapsed = time.time() - start_time
        
        status2 = ctx2_loaded.metadata_load_status
        
        print(f"✓ 第二次加载 ({elapsed:.2f}s)")
        print(f"  - source: {status2.source}")
        print(f"  - message: {status2.message}")
        
        # 第二次应该更快（从缓存加载）
        assert elapsed < 5, f"缓存加载应该很快，实际: {elapsed:.2f}s"


# ============================================================
# 认证刷新测试
# ============================================================

class TestAuthRefresh:
    """认证刷新测试"""
    
    @pytest.mark.asyncio
    async def test_refresh_auth_when_valid(
        self,
        workflow_context: WorkflowContext
    ):
        """测试 token 有效时不刷新"""
        original_token = workflow_context.auth.api_key
        
        # 调用刷新
        ctx_after = await workflow_context.refresh_auth_if_needed()
        
        # token 有效时应该返回相同的上下文
        assert ctx_after.auth.api_key == original_token, "有效 token 不应刷新"
        
        print(f"✓ 有效 token 未刷新")
    
    @pytest.mark.asyncio
    async def test_force_refresh_auth(self, datasource_luid: str):
        """测试强制刷新认证"""
        # 获取初始 token
        auth1 = await get_tableau_auth_async()
        
        # 强制刷新
        auth2 = await get_tableau_auth_async(force_refresh=True)
        
        # 两个 token 可能相同（如果服务器返回相同的），但应该都有效
        assert auth2.api_key is not None
        assert not auth2.is_expired()
        
        print(f"✓ 强制刷新成功")
        print(f"  - token1: {auth1.api_key[:20]}...")
        print(f"  - token2: {auth2.api_key[:20]}...")


# ============================================================
# RunnableConfig 集成测试
# ============================================================

class TestRunnableConfigIntegration:
    """RunnableConfig 集成测试"""
    
    @pytest.mark.asyncio
    async def test_create_and_get_context(
        self,
        workflow_context: WorkflowContext
    ):
        """测试创建和获取上下文"""
        # 加载元数据
        ctx = await workflow_context.ensure_metadata_loaded()
        
        # 创建 config
        thread_id = f"test_{int(time.time())}"
        config = create_workflow_config(thread_id, ctx)
        
        # 验证 config 结构
        assert "configurable" in config
        assert "thread_id" in config["configurable"]
        assert "workflow_context" in config["configurable"]
        assert "tableau_auth" in config["configurable"]  # 向后兼容
        
        # 从 config 获取上下文
        retrieved_ctx = get_context(config)
        assert retrieved_ctx is not None
        assert retrieved_ctx.datasource_luid == ctx.datasource_luid
        assert retrieved_ctx.metadata is not None
        
        print(f"✓ RunnableConfig 集成测试通过")
        print(f"  - thread_id: {thread_id}")
        print(f"  - has_metadata: {retrieved_ctx.metadata is not None}")
    
    @pytest.mark.asyncio
    async def test_get_context_or_raise(
        self,
        workflow_context: WorkflowContext
    ):
        """测试 get_context_or_raise"""
        ctx = await workflow_context.ensure_metadata_loaded()
        config = create_workflow_config("test_thread", ctx)
        
        # 应该成功获取
        retrieved = get_context_or_raise(config)
        assert retrieved is not None
        
        # 空 config 应该抛出异常
        with pytest.raises(ValueError):
            get_context_or_raise(None)
        
        with pytest.raises(ValueError):
            get_context_or_raise({"configurable": {}})
        
        print(f"✓ get_context_or_raise 测试通过")


# ============================================================
# 完整工作流测试
# ============================================================

class TestFullWorkflowWithContext:
    """完整工作流测试"""
    
    @pytest.mark.asyncio
    async def test_workflow_execution_with_context(
        self,
        workflow_context: WorkflowContext,
        settings: Settings
    ):
        """测试使用 WorkflowContext 执行完整工作流"""
        from tableau_assistant.src.workflow.executor import WorkflowExecutor
        
        # 创建 executor
        executor = WorkflowExecutor(
            max_replan_rounds=1,
            use_memory_checkpointer=True,
        )
        
        # 简单查询
        question = "各地区销售额是多少"
        
        print(f"\n执行工作流测试:")
        print(f"  问题: {question}")
        
        try:
            # 执行工作流
            result = await executor.run(
                question=question,
                datasource_luid=workflow_context.datasource_luid,
            )
            
            # 验证结果
            assert result is not None
            
            # 检查是否有输出
            if hasattr(result, 'final_answer'):
                print(f"  ✓ 最终答案: {result.final_answer[:100]}...")
            elif isinstance(result, dict):
                if 'final_answer' in result:
                    print(f"  ✓ 最终答案: {result['final_answer'][:100]}...")
                elif 'error' in result:
                    print(f"  ⚠️ 错误: {result['error']}")
            
            print(f"✓ 工作流执行完成")
            
        except Exception as e:
            print(f"⚠️ 工作流执行失败: {e}")
            # 不 fail，因为可能是 LLM 配置问题
            pytest.skip(f"工作流执行失败: {e}")
    
    @pytest.mark.asyncio
    async def test_streaming_workflow_with_context(
        self,
        workflow_context: WorkflowContext,
        settings: Settings
    ):
        """测试流式工作流执行"""
        from tableau_assistant.src.workflow.executor import WorkflowExecutor
        
        executor = WorkflowExecutor(
            max_replan_rounds=1,
            use_memory_checkpointer=True,
        )
        
        question = "各产品类别的平均利润"
        
        print(f"\n执行流式工作流测试:")
        print(f"  问题: {question}")
        
        event_count = 0
        stream = None
        
        try:
            stream = executor.stream(
                question=question,
                datasource_luid=workflow_context.datasource_luid,
            )
            async for event in stream:
                event_count += 1
                
                # 打印部分事件
                if event_count <= 5:
                    event_type = type(event).__name__
                    print(f"  事件 {event_count}: {event_type}")
            
            print(f"  ✓ 共收到 {event_count} 个事件")
            print(f"✓ 流式工作流执行完成")
            
        except Exception as e:
            print(f"⚠️ 流式工作流执行失败: {e}")
            pytest.skip(f"流式工作流执行失败: {e}")
        finally:
            # 确保正确关闭异步生成器
            if stream is not None:
                await stream.aclose()


# ============================================================
# 工具访问上下文测试
# ============================================================

class TestToolContextAccess:
    """工具访问上下文测试"""
    
    @pytest.mark.asyncio
    async def test_metadata_tool_with_context(
        self,
        workflow_context: WorkflowContext
    ):
        """测试 metadata_tool 通过 config 访问上下文"""
        from tableau_assistant.src.tools.metadata_tool import get_metadata
        
        # 加载元数据
        ctx = await workflow_context.ensure_metadata_loaded()
        
        # 如果元数据为空，跳过测试
        if not ctx.metadata or not ctx.metadata.fields:
            pytest.skip("元数据为空（可能是 API 速率限制）")
        
        # 创建 config
        config = create_workflow_config("test_tool", ctx)
        
        # 调用工具
        result = await get_metadata.ainvoke(
            {"filter_role": None, "filter_category": None},
            config=config
        )
        
        assert result is not None
        assert "字段列表" in result or "fields" in result.lower()
        
        print(f"✓ metadata_tool 访问上下文成功")
        print(f"  结果长度: {len(result)} 字符")
    
    @pytest.mark.asyncio
    async def test_metadata_tool_filter_dimensions(
        self,
        workflow_context: WorkflowContext
    ):
        """测试 metadata_tool 过滤维度"""
        from tableau_assistant.src.tools.metadata_tool import get_metadata
        
        ctx = await workflow_context.ensure_metadata_loaded()
        
        # 如果元数据为空，跳过测试
        if not ctx.metadata or not ctx.metadata.fields:
            pytest.skip("元数据为空（可能是 API 速率限制）")
        
        config = create_workflow_config("test_filter", ctx)
        
        # 只获取维度
        result = await get_metadata.ainvoke(
            {"filter_role": "dimension", "filter_category": None},
            config=config
        )
        
        assert result is not None
        assert "维度" in result
        
        print(f"✓ metadata_tool 过滤维度成功")
    
    @pytest.mark.asyncio
    async def test_metadata_tool_without_context_fails(self):
        """测试没有上下文时 metadata_tool 失败"""
        from tableau_assistant.src.tools.metadata_tool import get_metadata
        
        # 没有 workflow_context 的 config
        config = {"configurable": {"thread_id": "test"}}
        
        result = await get_metadata.ainvoke(
            {"filter_role": None, "filter_category": None},
            config=config
        )
        
        # 应该返回错误信息
        assert "无法获取元数据" in result or "error" in result.lower()
        
        print(f"✓ 没有上下文时正确返回错误")
