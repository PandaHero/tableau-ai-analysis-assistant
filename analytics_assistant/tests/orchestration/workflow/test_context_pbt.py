# -*- coding: utf-8 -*-
"""
Property-Based Tests for WorkflowContext

Property 21: Context Data Model Caching
Property 22: Context State Persistence

测试框架：Hypothesis
运行方式：
    cd analytics_assistant
    $env:PYTHONPATH = ".."
    pytest tests/orchestration/workflow/test_context_pbt.py -v

使用真实 Tableau 服务进行测试。
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytest
from hypothesis import given, settings, strategies as st, assume

from analytics_assistant.src.orchestration.workflow.context import (
    WorkflowContext,
    create_workflow_config,
    get_context,
    get_context_or_raise,
)


# ═══════════════════════════════════════════════════════════════════════════
# 测试数据生成策略
# ═══════════════════════════════════════════════════════════════════════════

# 数据源 ID 生成策略
datasource_luid_strategy = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"),
    min_size=8,
    max_size=36,
).filter(lambda x: x.strip())

# 线程 ID 生成策略
thread_id_strategy = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"),
    min_size=8,
    max_size=64,
).filter(lambda x: x.strip())

# 时区生成策略
timezone_strategy = st.sampled_from([
    "Asia/Shanghai",
    "Asia/Tokyo",
    "America/New_York",
    "Europe/London",
    "UTC",
])

# 财年起始月份生成策略
fiscal_year_start_month_strategy = st.integers(min_value=1, max_value=12)

# 字段名生成策略
field_name_strategy = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"),
    min_size=1,
    max_size=50,
).filter(lambda x: x.strip())

# 字段值列表生成策略
field_values_strategy = st.lists(
    st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
    min_size=0,
    max_size=20,
)


# ═══════════════════════════════════════════════════════════════════════════
# 真实服务辅助函数
# ═══════════════════════════════════════════════════════════════════════════

async def get_real_tableau_components():
    """获取真实的 Tableau 组件
    
    Returns:
        tuple: (client, adapter, auth, datasource_luid, data_model)
    """
    from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
    from analytics_assistant.src.platform.tableau.client import VizQLClient
    from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
    from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
    
    # 获取真实认证
    auth = await get_tableau_auth_async()
    
    # 创建真实组件
    client = VizQLClient()
    adapter = TableauAdapter(vizql_client=client)
    
    # 获取数据源 LUID
    datasource_name = "正大益生"
    datasource_luid = await client.get_datasource_luid_by_name(
        datasource_name=datasource_name,
        api_key=auth.api_key,
    )
    print(datasource_luid)
    if not datasource_luid:
        return None, None, None, None, None
    
    # 加载真实数据模型
    loader = TableauDataLoader(client=client)
    data_model = await loader.load_data_model(
        datasource_id=datasource_luid,
        auth=auth,
    )
    print(client, adapter, auth, datasource_luid, data_model)
    return client, adapter, auth, datasource_luid, data_model


# ═══════════════════════════════════════════════════════════════════════════
# Property 21: Context Data Model Caching
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty21ContextDataModelCaching:
    """
    Property 21: Context Data Model Caching
    
    **Validates: Requirements 19.2**
    
    *For any* session, the data model SHALL be loaded only once and 
    cached in the WorkflowContext for subsequent accesses.
    
    验证同一会话内数据模型只加载一次。
    使用真实 Tableau 数据模型。
    """
    
    @pytest.mark.asyncio
    async def test_real_data_model_reference_preserved(self):
        """真实数据模型引用在上下文中保持不变"""
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            ctx = WorkflowContext(
                datasource_luid=datasource_luid,
                data_model=data_model,
                platform_adapter=adapter,
            )
            
            # 多次访问 data_model，应该返回同一个对象
            model1 = ctx.data_model
            model2 = ctx.data_model
            model3 = ctx.data_model
            
            assert model1 is model2
            assert model2 is model3
            assert model1 is data_model
            
            # 验证数据模型有真实字段
            assert len(data_model.fields) > 0
            assert len(data_model.dimensions) > 0 or len(data_model.measures) > 0
        finally:
            if client:
                await client.close()
    
    @pytest.mark.asyncio
    async def test_real_data_model_not_reloaded_on_config_access(self):
        """通过 config 访问上下文时不重新加载真实数据模型"""
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            ctx = WorkflowContext(
                datasource_luid=datasource_luid,
                data_model=data_model,
                platform_adapter=adapter,
            )
            
            config = create_workflow_config("thread_1", ctx)
            
            # 多次从 config 获取上下文
            ctx1 = get_context(config)
            ctx2 = get_context(config)
            ctx3 = get_context(config)
            
            # 验证是同一个上下文对象
            assert ctx1 is ctx2
            assert ctx2 is ctx3
            
            # 验证数据模型是同一个对象
            assert ctx1.data_model is data_model
            assert ctx2.data_model is data_model
            
            # 验证数据模型内容正确
            assert ctx1.data_model.fields == data_model.fields
        finally:
            if client:
                await client.close()
    
    @pytest.mark.asyncio
    async def test_real_data_model_cached_across_multiple_accesses(self):
        """真实数据模型在多次访问中保持缓存"""
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            ctx = WorkflowContext(
                datasource_luid=datasource_luid,
                data_model=data_model,
                platform_adapter=adapter,
            )
            
            config = create_workflow_config("thread_test", ctx)
            
            # 模拟多次节点访问
            for _ in range(10):
                retrieved_ctx = get_context(config)
                assert retrieved_ctx is not None
                assert retrieved_ctx.data_model is data_model
                # 验证字段数量一致
                assert len(retrieved_ctx.data_model.fields) == len(data_model.fields)
        finally:
            if client:
                await client.close()
    
    @pytest.mark.asyncio
    async def test_real_data_model_same_instance_in_workflow(self):
        """工作流中真实数据模型是同一实例"""
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            ctx = WorkflowContext(
                datasource_luid=datasource_luid,
                data_model=data_model,
                platform_adapter=adapter,
            )
            
            config = create_workflow_config("thread_workflow", ctx)
            
            # 模拟多个节点访问
            node_results = []
            for i in range(5):
                node_ctx = get_context(config)
                node_results.append(id(node_ctx.data_model))
            
            # 所有节点应该看到同一个数据模型实例
            assert len(set(node_results)) == 1
            assert node_results[0] == id(data_model)
        finally:
            if client:
                await client.close()


# ═══════════════════════════════════════════════════════════════════════════
# Property 22: Context State Persistence
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty22ContextStatePersistence:
    """
    Property 22: Context State Persistence
    
    **Validates: Requirements 19.3**
    
    *For any* state modification within a session, the changes SHALL 
    persist and be visible to subsequent accesses within the same session.
    
    验证上下文状态在会话内持久化。
    使用真实 Tableau 服务。
    """
    
    @pytest.mark.asyncio
    async def test_real_field_values_cache_persists(self):
        """真实字段值缓存在会话内持久化"""
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            ctx = WorkflowContext(
                datasource_luid=datasource_luid,
                data_model=data_model,
                platform_adapter=adapter,
            )
            
            # 从真实数据模型获取一些维度字段名
            dimension_names = [f.name for f in data_model.dimensions[:3]]
            
            if len(dimension_names) < 2:
                pytest.skip("数据模型维度字段不足")
            
            # 设置字段值（模拟从 Tableau 查询后缓存）
            ctx.set_field_values(dimension_names[0], ["值1", "值2", "值3"])
            ctx.set_field_values(dimension_names[1], ["A", "B"])
            
            # 验证值被持久化
            assert ctx.get_field_values(dimension_names[0]) == ["值1", "值2", "值3"]
            assert ctx.get_field_values(dimension_names[1]) == ["A", "B"]
            assert ctx.get_field_values("unknown_field") is None
        finally:
            if client:
                await client.close()
    
    @pytest.mark.asyncio
    async def test_real_field_values_cache_persists_through_config(self):
        """真实字段值缓存通过 config 访问时持久化"""
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            ctx = WorkflowContext(
                datasource_luid=datasource_luid,
                data_model=data_model,
                platform_adapter=adapter,
            )
            
            config = create_workflow_config("thread_1", ctx)
            
            # 获取真实字段名
            if len(data_model.dimensions) == 0:
                pytest.skip("数据模型没有维度字段")
            
            field_name = data_model.dimensions[0].name
            
            # 第一个节点设置缓存
            ctx1 = get_context(config)
            ctx1.set_field_values(field_name, ["北京", "上海"])
            
            # 第二个节点读取缓存
            ctx2 = get_context(config)
            values = ctx2.get_field_values(field_name)
            
            assert values == ["北京", "上海"]
        finally:
            if client:
                await client.close()
    
    @given(
        field_name=field_name_strategy,
        field_values=field_values_strategy,
    )
    @settings(max_examples=30, deadline=None)
    def test_field_values_round_trip(self, field_name: str, field_values: List[str]):
        """字段值设置后可以正确读取（PBT）"""
        ctx = WorkflowContext(
            datasource_luid="ds_round_trip",
        )
        
        # 设置值
        ctx.set_field_values(field_name, field_values)
        
        # 读取值
        retrieved = ctx.get_field_values(field_name)
        
        # 验证一致性
        assert retrieved == field_values
    
    @given(
        field_names=st.lists(field_name_strategy, min_size=1, max_size=10, unique=True),
    )
    @settings(max_examples=20, deadline=None)
    def test_multiple_field_values_persist(self, field_names: List[str]):
        """多个字段值都能持久化（PBT）"""
        ctx = WorkflowContext(
            datasource_luid="ds_multi_field",
        )
        
        # 设置多个字段的值
        expected = {}
        for i, field_name in enumerate(field_names):
            values = [f"value_{j}" for j in range(i + 1)]
            ctx.set_field_values(field_name, values)
            expected[field_name] = values
        
        # 验证所有字段值都能正确读取
        for field_name, expected_values in expected.items():
            assert ctx.get_field_values(field_name) == expected_values
    
    @pytest.mark.asyncio
    async def test_real_current_time_update_creates_new_context(self):
        """update_current_time 创建新上下文但保留真实数据模型状态"""
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            original_ctx = WorkflowContext(
                datasource_luid=datasource_luid,
                data_model=data_model,
                platform_adapter=adapter,
                timezone="Asia/Shanghai",
                fiscal_year_start_month=4,
            )
            
            # 设置一些状态
            if len(data_model.dimensions) > 0:
                field_name = data_model.dimensions[0].name
                original_ctx.set_field_values(field_name, ["北京", "上海"])
            
            # 更新时间
            new_ctx = original_ctx.update_current_time()
            
            # 验证是新对象
            assert new_ctx is not original_ctx
            
            # 验证状态被保留
            assert new_ctx.datasource_luid == original_ctx.datasource_luid
            assert new_ctx.timezone == original_ctx.timezone
            assert new_ctx.fiscal_year_start_month == original_ctx.fiscal_year_start_month
            
            # 验证数据模型被保留
            assert new_ctx.data_model is data_model
            
            # 验证字段值缓存被保留
            if len(data_model.dimensions) > 0:
                field_name = data_model.dimensions[0].name
                assert new_ctx.get_field_values(field_name) == ["北京", "上海"]
            
            # 验证时间被更新
            assert new_ctx.current_time is not None
        finally:
            if client:
                await client.close()
    
    @pytest.mark.asyncio
    async def test_real_platform_adapter_persists(self):
        """真实平台适配器在上下文中持久化"""
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if adapter is None:
            pytest.skip("无法连接 Tableau 服务")
        
        try:
            ctx = WorkflowContext(
                datasource_luid=datasource_luid,
                data_model=data_model,
                platform_adapter=adapter,
            )
            
            config = create_workflow_config("thread_adapter", ctx)
            
            # 多次访问
            for _ in range(5):
                retrieved_ctx = get_context(config)
                assert retrieved_ctx.platform_adapter is adapter
        finally:
            if client:
                await client.close()
    
    @pytest.mark.asyncio
    async def test_real_dimension_hierarchy_persists(self):
        """维度层级在上下文中持久化（使用真实数据模型字段）"""
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            # 使用真实字段名构建层级
            dimension_names = [f.name for f in data_model.dimensions[:3]]
            
            if len(dimension_names) < 2:
                pytest.skip("数据模型维度字段不足")
            
            hierarchy = {
                dimension_names[0]: {
                    "children": [dimension_names[1]] if len(dimension_names) > 1 else [],
                    "parent": None,
                },
            }
            if len(dimension_names) > 1:
                hierarchy[dimension_names[1]] = {
                    "children": [],
                    "parent": dimension_names[0],
                }
            
            ctx = WorkflowContext(
                datasource_luid=datasource_luid,
                data_model=data_model,
                dimension_hierarchy=hierarchy,
                platform_adapter=adapter,
            )
            
            config = create_workflow_config("thread_hierarchy", ctx)
            
            # 验证层级信息持久化
            retrieved_ctx = get_context(config)
            assert retrieved_ctx.dimension_hierarchy == hierarchy
        finally:
            if client:
                await client.close()


# ═══════════════════════════════════════════════════════════════════════════
# 辅助测试：WorkflowContext 基本功能
# ═══════════════════════════════════════════════════════════════════════════

class TestWorkflowContextBasicFunctionality:
    """WorkflowContext 基本功能测试"""
    
    def test_create_workflow_config(self):
        """创建工作流配置"""
        ctx = WorkflowContext(datasource_luid="ds_123")
        config = create_workflow_config("thread_1", ctx)
        
        assert "configurable" in config
        assert config["configurable"]["thread_id"] == "thread_1"
        assert config["configurable"]["workflow_context"] is ctx
    
    def test_create_workflow_config_with_extra(self):
        """创建工作流配置（带额外参数）"""
        ctx = WorkflowContext(datasource_luid="ds_123")
        config = create_workflow_config(
            "thread_1", 
            ctx, 
            custom_key="custom_value",
        )
        
        assert config["configurable"]["custom_key"] == "custom_value"
    
    def test_get_context_returns_none_for_none_config(self):
        """config 为 None 时返回 None"""
        result = get_context(None)
        assert result is None
    
    def test_get_context_returns_none_for_missing_context(self):
        """config 中没有 workflow_context 时返回 None"""
        config = {"configurable": {"thread_id": "thread_1"}}
        result = get_context(config)
        assert result is None
    
    def test_get_context_or_raise_raises_for_none_config(self):
        """config 为 None 时抛出异常"""
        with pytest.raises(ValueError, match="config is None"):
            get_context_or_raise(None)
    
    def test_get_context_or_raise_raises_for_missing_context(self):
        """config 中没有 workflow_context 时抛出异常"""
        config = {"configurable": {"thread_id": "thread_1"}}
        with pytest.raises(ValueError, match="WorkflowContext not found"):
            get_context_or_raise(config)
    
    @given(
        datasource_luid=datasource_luid_strategy,
        timezone=timezone_strategy,
        fiscal_year_start_month=fiscal_year_start_month_strategy,
    )
    @settings(max_examples=20, deadline=None)
    def test_workflow_context_creation(
        self,
        datasource_luid: str,
        timezone: str,
        fiscal_year_start_month: int,
    ):
        """WorkflowContext 创建测试（PBT）"""
        ctx = WorkflowContext(
            datasource_luid=datasource_luid,
            timezone=timezone,
            fiscal_year_start_month=fiscal_year_start_month,
        )
        
        assert ctx.datasource_luid == datasource_luid
        assert ctx.timezone == timezone
        assert ctx.fiscal_year_start_month == fiscal_year_start_month
        assert ctx.data_model is None
        assert ctx.platform_adapter is None
        assert ctx.field_values_cache == {}


# ═══════════════════════════════════════════════════════════════════════════
# 运行测试
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
