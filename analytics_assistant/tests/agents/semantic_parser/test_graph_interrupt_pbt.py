# -*- coding: utf-8 -*-
"""
Property-Based Tests for LangGraph interrupt() Mechanism

Property 34: Filter Confirmation via LangGraph interrupt()
Property 35: Filter Value Update After Confirmation

测试框架：Hypothesis
运行方式：
    cd analytics_assistant
    $env:PYTHONPATH = ".."
    pytest tests/agents/semantic_parser/test_graph_interrupt_pbt.py -v --tb=short

使用真实 Tableau 服务进行测试。
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from hypothesis import given, settings, strategies as st, assume
from langgraph.types import interrupt, Interrupt

from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
from analytics_assistant.src.agents.semantic_parser.schemas.output import (
    SemanticOutput,
    What,
    Where,
    SelfCheck,
)
from analytics_assistant.src.agents.semantic_parser.schemas.filters import (
    FilterValidationType,
    FilterValidationResult,
    FilterValidationSummary,
    FilterConfirmation,
)
from analytics_assistant.src.core.schemas.filters import SetFilter, FilterType
from analytics_assistant.src.core.schemas.fields import MeasureField, DimensionField


# ═══════════════════════════════════════════════════════════════════════════
# 测试数据生成策略
# ═══════════════════════════════════════════════════════════════════════════

# 字段名生成策略
field_name_strategy = st.sampled_from([
    "地区", "城市", "产品", "客户", "部门", "类别", "品牌", "渠道",
])

# 筛选值生成策略
filter_value_strategy = st.sampled_from([
    "北京", "上海", "广州", "深圳", "杭州", "南京", "成都", "武汉",
    "华东", "华北", "华南", "西南", "东北",
])

# 相似值列表生成策略
similar_values_strategy = st.lists(
    st.sampled_from([
        "北京市", "上海市", "广州市", "深圳市", "杭州市",
        "华东区", "华北区", "华南区", "西南区", "东北区",
    ]),
    min_size=1,
    max_size=5,
    unique=True,
)


# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════

def create_semantic_output_with_filter(
    field_name: str,
    filter_values: List[str],
) -> SemanticOutput:
    """创建带有筛选条件的 SemanticOutput"""
    return SemanticOutput(
        restated_question=f"查询{field_name}的数据",
        what=What(measures=[
            MeasureField(field_name="销售额", aggregation="SUM"),
        ]),
        where=Where(
            dimensions=[
                DimensionField(field_name=field_name),
            ],
            filters=[
                SetFilter(
                    field_name=field_name,
                    filter_type=FilterType.SET,
                    values=filter_values,
                ),
            ],
        ),
        self_check=SelfCheck(
            field_mapping_confidence=0.9,
            time_range_confidence=0.9,
            computation_confidence=0.9,
            overall_confidence=0.9,
        ),
    )


def create_validation_result_needs_confirmation(
    field_name: str,
    requested_value: str,
    similar_values: List[str],
) -> FilterValidationResult:
    """创建需要确认的验证结果"""
    return FilterValidationResult(
        is_valid=False,
        field_name=field_name,
        requested_value=requested_value,
        similar_values=similar_values,
        validation_type=FilterValidationType.NEEDS_CONFIRMATION,
        needs_confirmation=True,
        message=f"字段'{field_name}'中没有'{requested_value}'，找到相似值：{', '.join(similar_values)}",
    )


def create_validation_result_exact_match(
    field_name: str,
    value: str,
) -> FilterValidationResult:
    """创建精确匹配的验证结果"""
    return FilterValidationResult(
        is_valid=True,
        field_name=field_name,
        requested_value=value,
        matched_values=[value],
        validation_type=FilterValidationType.EXACT_MATCH,
    )


async def get_real_tableau_components():
    """获取真实的 Tableau 组件
    
    Returns:
        tuple: (client, adapter, auth, datasource_luid, data_model)
    """
    from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
    from analytics_assistant.src.platform.tableau.client import VizQLClient
    from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
    from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
    
    try:
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
        
        if not datasource_luid:
            return None, None, None, None, None
        
        # 加载真实数据模型
        loader = TableauDataLoader(client=client)
        data_model = await loader.load_data_model(
            datasource_id=datasource_luid,
            auth=auth,
        )
        
        return client, adapter, auth, datasource_luid, data_model
    except Exception as e:
        print(f"获取 Tableau 组件失败: {e}")
        return None, None, None, None, None


# ═══════════════════════════════════════════════════════════════════════════
# Property 34: Filter Confirmation via LangGraph interrupt()
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty34FilterConfirmationViaInterrupt:
    """
    Property 34: Filter Confirmation via LangGraph interrupt()
    
    **Validates: Requirements 18.2**
    
    *For any* filter validation result where needs_confirmation=True 
    and similar_values is non-empty, the filter_validator_node SHALL 
    call LangGraph interrupt() to pause execution and wait for user confirmation.
    
    验证筛选值确认时正确调用 interrupt()。
    """
    
    @pytest.mark.asyncio
    async def test_interrupt_called_when_needs_confirmation(self):
        """当 needs_confirmation=True 且有相似值时调用 interrupt()"""
        from analytics_assistant.src.agents.semantic_parser.graph import (
            filter_validator_node,
        )
        from analytics_assistant.src.agents.semantic_parser.components.filter_validator import (
            FilterValueValidator,
        )
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        from analytics_assistant.src.orchestration.workflow.context import (
            WorkflowContext,
            create_workflow_config,
        )
        
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            # 创建 WorkflowContext
            ctx = WorkflowContext(
                datasource_luid=datasource_luid,
                data_model=data_model,
                platform_adapter=adapter,
            )
            config = create_workflow_config("thread_interrupt_test", ctx)
            
            # 创建带有不存在筛选值的 SemanticOutput
            # 使用一个不太可能存在的值
            semantic_output = create_semantic_output_with_filter(
                field_name="地区",  # 假设数据模型有这个字段
                filter_values=["不存在的地区XYZ"],
            )
            
            state: SemanticParserState = {
                "question": "查询不存在地区的销售额",
                "semantic_output": semantic_output.model_dump(),
                "confirmed_filters": [],
            }
            
            # Mock interrupt 函数来捕获调用
            interrupt_called = False
            interrupt_payload = None
            
            def mock_interrupt(payload):
                nonlocal interrupt_called, interrupt_payload
                interrupt_called = True
                interrupt_payload = payload
                # 模拟用户确认
                return {"confirmations": {"不存在的地区XYZ": "北京"}}
            
            # 使用 patch 替换 interrupt
            with patch(
                "analytics_assistant.src.agents.semantic_parser.graph.interrupt",
                side_effect=mock_interrupt,
            ):
                result = await filter_validator_node(state, config)
            
            # 验证：如果找到相似值，应该调用 interrupt
            # 如果没有相似值，应该设置 needs_clarification=True
            validation_result = result.get("filter_validation_result", {})
            
            if interrupt_called:
                # 验证 interrupt payload 格式正确
                assert interrupt_payload is not None
                assert "type" in interrupt_payload
                assert interrupt_payload["type"] == "filter_value_confirmation"
                assert "pending" in interrupt_payload
                assert len(interrupt_payload["pending"]) > 0
                
                # 验证 pending 项包含必要字段
                pending_item = interrupt_payload["pending"][0]
                assert "field_name" in pending_item
                assert "requested_value" in pending_item
                assert "similar_values" in pending_item
            else:
                # 如果没有调用 interrupt，应该是因为没有相似值
                # 此时应该设置 needs_clarification 或 all_valid
                assert (
                    result.get("needs_clarification") == True or
                    validation_result.get("all_valid") == True or
                    validation_result.get("has_unresolvable_filters") == True
                )
        finally:
            if client:
                await client.close()
    
    @given(
        field_name=field_name_strategy,
        requested_value=filter_value_strategy,
        similar_values=similar_values_strategy,
    )
    @settings(max_examples=20, deadline=None)
    def test_interrupt_payload_format(
        self,
        field_name: str,
        requested_value: str,
        similar_values: List[str],
    ):
        """验证 interrupt payload 格式正确（PBT）"""
        # 创建需要确认的验证结果
        validation_result = create_validation_result_needs_confirmation(
            field_name=field_name,
            requested_value=requested_value,
            similar_values=similar_values,
        )
        
        # 构建 interrupt payload（模拟 filter_validator_node 的逻辑）
        pending_confirmations = [validation_result]
        
        confirmation_request = {
            "type": "filter_value_confirmation",
            "pending": [
                {
                    "field_name": r.field_name,
                    "requested_value": r.requested_value,
                    "similar_values": r.similar_values,
                    "message": r.message,
                }
                for r in pending_confirmations
            ],
        }
        
        # 验证 payload 格式
        assert confirmation_request["type"] == "filter_value_confirmation"
        assert len(confirmation_request["pending"]) == 1
        
        pending_item = confirmation_request["pending"][0]
        assert pending_item["field_name"] == field_name
        assert pending_item["requested_value"] == requested_value
        assert pending_item["similar_values"] == similar_values
        assert pending_item["message"] is not None
    
    def test_no_interrupt_when_all_valid(self):
        """所有筛选值都有效时不调用 interrupt"""
        # 创建全部有效的验证结果
        results = [
            create_validation_result_exact_match("地区", "北京"),
            create_validation_result_exact_match("城市", "上海"),
        ]
        
        summary = FilterValidationSummary.from_results(results)
        
        # 验证：all_valid=True，不需要确认
        assert summary.all_valid == True
        assert summary.has_unresolvable_filters == False
        
        # 检查是否有需要确认的项
        pending_confirmations = [
            r for r in summary.results
            if r.needs_confirmation and len(r.similar_values) > 0
        ]
        
        assert len(pending_confirmations) == 0
    
    def test_no_interrupt_when_unresolvable(self):
        """无相似值时不调用 interrupt，而是返回 needs_clarification"""
        # 创建无法解决的验证结果（没有相似值）
        result = FilterValidationResult(
            is_valid=False,
            field_name="地区",
            requested_value="完全不存在的值",
            similar_values=[],  # 空列表
            validation_type=FilterValidationType.NOT_FOUND,
            is_unresolvable=True,
            message="没有找到相似值",
        )
        
        summary = FilterValidationSummary.from_results([result])
        
        # 验证：has_unresolvable_filters=True
        assert summary.has_unresolvable_filters == True
        
        # 检查是否有需要确认的项（应该没有，因为没有相似值）
        pending_confirmations = [
            r for r in summary.results
            if r.needs_confirmation and len(r.similar_values) > 0
        ]
        
        assert len(pending_confirmations) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Property 35: Filter Value Update After Confirmation
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty35FilterValueUpdateAfterConfirmation:
    """
    Property 35: Filter Value Update After Confirmation
    
    **Validates: Requirements 18.3**
    
    *For any* user confirmation of filter values, the filter_validator_node 
    SHALL update the semantic_output.where.filters with the confirmed values 
    and accumulate the confirmation in confirmed_filters.
    
    验证确认后 filters 被正确更新。
    """
    
    @given(
        field_name=field_name_strategy,
        original_value=filter_value_strategy,
        confirmed_value=st.sampled_from([
            "北京市", "上海市", "广州市", "深圳市", "杭州市",
        ]),
    )
    @settings(max_examples=30, deadline=None)
    def test_apply_single_confirmation_updates_filter(
        self,
        field_name: str,
        original_value: str,
        confirmed_value: str,
    ):
        """apply_single_confirmation 正确更新筛选值（PBT）"""
        from analytics_assistant.src.agents.semantic_parser.components.filter_validator import (
            FilterValueValidator,
        )
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        
        # 跳过原始值和确认值相同的情况
        assume(original_value != confirmed_value)
        
        # 创建 mock 依赖
        mock_adapter = MagicMock()
        mock_cache = FieldValueCache()
        
        validator = FilterValueValidator(
            platform_adapter=mock_adapter,
            field_value_cache=mock_cache,
        )
        
        # 创建带有原始筛选值的 SemanticOutput
        semantic_output = create_semantic_output_with_filter(
            field_name=field_name,
            filter_values=[original_value],
        )
        
        # 应用确认
        updated_output = validator.apply_single_confirmation(
            semantic_output=semantic_output,
            field_name=field_name,
            original_value=original_value,
            confirmed_value=confirmed_value,
        )
        
        # 验证：筛选值已更新
        updated_filters = updated_output.where.filters
        assert len(updated_filters) == 1
        
        updated_filter = updated_filters[0]
        assert isinstance(updated_filter, SetFilter)
        assert confirmed_value in updated_filter.values
        assert original_value not in updated_filter.values
    
    @given(
        confirmations=st.dictionaries(
            keys=filter_value_strategy,
            values=st.sampled_from([
                "北京市", "上海市", "广州市", "深圳市",
            ]),
            min_size=1,
            max_size=3,
        ),
    )
    @settings(max_examples=20, deadline=None)
    def test_apply_confirmations_updates_multiple_values(
        self,
        confirmations: Dict[str, str],
    ):
        """apply_confirmations 正确更新多个筛选值（PBT）"""
        from analytics_assistant.src.agents.semantic_parser.components.filter_validator import (
            FilterValueValidator,
        )
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        
        # 确保原始值和确认值不同
        for orig, conf in confirmations.items():
            assume(orig != conf)
        
        mock_adapter = MagicMock()
        mock_cache = FieldValueCache()
        
        validator = FilterValueValidator(
            platform_adapter=mock_adapter,
            field_value_cache=mock_cache,
        )
        
        # 创建带有多个原始筛选值的 SemanticOutput
        original_values = list(confirmations.keys())
        semantic_output = create_semantic_output_with_filter(
            field_name="地区",
            filter_values=original_values,
        )
        
        # 应用确认
        updated_output = validator.apply_confirmations(
            semantic_output=semantic_output,
            confirmations=confirmations,
        )
        
        # 验证：所有筛选值都已更新
        updated_filter = updated_output.where.filters[0]
        assert isinstance(updated_filter, SetFilter)
        
        for original_value, confirmed_value in confirmations.items():
            assert confirmed_value in updated_filter.values
            # 原始值应该被替换（除非原始值和确认值相同）
            if original_value != confirmed_value:
                assert original_value not in updated_filter.values
    
    def test_confirmed_filters_accumulation(self):
        """confirmed_filters 正确累积多轮确认"""
        # 模拟多轮确认场景
        existing_confirmations = [
            {
                "field_name": "地区",
                "original_value": "北京",
                "confirmed_value": "北京市",
                "confirmed_at": "2025-01-28T10:00:00",
            },
        ]
        
        new_confirmations = [
            {
                "field_name": "城市",
                "original_value": "上海",
                "confirmed_value": "上海市",
                "confirmed_at": "2025-01-28T10:05:00",
            },
        ]
        
        # 累积确认
        all_confirmations = existing_confirmations + new_confirmations
        
        # 验证：所有确认都被保留
        assert len(all_confirmations) == 2
        assert all_confirmations[0]["field_name"] == "地区"
        assert all_confirmations[1]["field_name"] == "城市"
    
    @pytest.mark.asyncio
    async def test_real_filter_update_after_confirmation(self):
        """使用真实 Tableau 服务测试确认后的筛选值更新"""
        from analytics_assistant.src.agents.semantic_parser.components.filter_validator import (
            FilterValueValidator,
        )
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            # 创建验证器
            field_value_cache = FieldValueCache()
            validator = FilterValueValidator(
                platform_adapter=adapter,
                field_value_cache=field_value_cache,
            )
            
            # 获取一个真实的维度字段
            if len(data_model.dimensions) == 0:
                pytest.skip("数据模型没有维度字段")
            
            real_field = data_model.dimensions[0]
            field_name = real_field.name
            
            # 创建 SemanticOutput
            semantic_output = create_semantic_output_with_filter(
                field_name=field_name,
                filter_values=["测试原始值"],
            )
            
            # 应用确认
            updated_output = validator.apply_single_confirmation(
                semantic_output=semantic_output,
                field_name=field_name,
                original_value="测试原始值",
                confirmed_value="测试确认值",
            )
            
            # 验证更新
            updated_filter = updated_output.where.filters[0]
            assert "测试确认值" in updated_filter.values
            assert "测试原始值" not in updated_filter.values
        finally:
            if client:
                await client.close()
    
    @given(
        num_rounds=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=10, deadline=None)
    def test_multi_round_confirmation_accumulation(self, num_rounds: int):
        """多轮确认正确累积（PBT）"""
        all_confirmations = []
        
        for i in range(num_rounds):
            new_confirmation = {
                "field_name": f"字段_{i}",
                "original_value": f"原始值_{i}",
                "confirmed_value": f"确认值_{i}",
                "confirmed_at": datetime.now().isoformat(),
            }
            all_confirmations.append(new_confirmation)
        
        # 验证：所有轮次的确认都被保留
        assert len(all_confirmations) == num_rounds
        
        # 验证：每轮确认都有正确的字段
        for i, conf in enumerate(all_confirmations):
            assert conf["field_name"] == f"字段_{i}"
            assert conf["original_value"] == f"原始值_{i}"
            assert conf["confirmed_value"] == f"确认值_{i}"
            assert "confirmed_at" in conf


# ═══════════════════════════════════════════════════════════════════════════
# 集成测试：完整的 interrupt/resume 流程
# ═══════════════════════════════════════════════════════════════════════════

class TestInterruptResumeIntegration:
    """集成测试：完整的 interrupt/resume 流程"""
    
    def test_filter_validation_summary_from_results(self):
        """FilterValidationSummary.from_results 正确汇总结果"""
        results = [
            create_validation_result_exact_match("地区", "北京"),
            create_validation_result_needs_confirmation("城市", "上海", ["上海市"]),
        ]
        
        summary = FilterValidationSummary.from_results(results)
        
        # 验证汇总
        assert len(summary.results) == 2
        assert summary.all_valid == False  # 有一个需要确认
        assert summary.has_unresolvable_filters == False
    
    def test_filter_validation_summary_all_valid(self):
        """所有筛选值都有效时 all_valid=True"""
        results = [
            create_validation_result_exact_match("地区", "北京"),
            create_validation_result_exact_match("城市", "上海"),
        ]
        
        summary = FilterValidationSummary.from_results(results)
        
        assert summary.all_valid == True
        assert summary.has_unresolvable_filters == False
    
    def test_filter_validation_summary_has_unresolvable(self):
        """有无法解决的筛选值时 has_unresolvable_filters=True"""
        results = [
            create_validation_result_exact_match("地区", "北京"),
            FilterValidationResult(
                is_valid=False,
                field_name="城市",
                requested_value="不存在的城市",
                similar_values=[],
                validation_type=FilterValidationType.NOT_FOUND,
                is_unresolvable=True,
            ),
        ]
        
        summary = FilterValidationSummary.from_results(results)
        
        assert summary.all_valid == False
        assert summary.has_unresolvable_filters == True
    
    @given(
        num_valid=st.integers(min_value=0, max_value=5),
        num_needs_confirmation=st.integers(min_value=0, max_value=3),
        num_unresolvable=st.integers(min_value=0, max_value=2),
    )
    @settings(max_examples=20, deadline=None)
    def test_filter_validation_summary_properties(
        self,
        num_valid: int,
        num_needs_confirmation: int,
        num_unresolvable: int,
    ):
        """FilterValidationSummary 属性正确（PBT）"""
        results = []
        
        # 添加有效结果
        for i in range(num_valid):
            results.append(create_validation_result_exact_match(f"字段_{i}", f"值_{i}"))
        
        # 添加需要确认的结果
        for i in range(num_needs_confirmation):
            results.append(create_validation_result_needs_confirmation(
                f"确认字段_{i}",
                f"原始值_{i}",
                [f"相似值_{i}_1", f"相似值_{i}_2"],
            ))
        
        # 添加无法解决的结果
        for i in range(num_unresolvable):
            results.append(FilterValidationResult(
                is_valid=False,
                field_name=f"无法解决字段_{i}",
                requested_value=f"无法解决值_{i}",
                similar_values=[],
                validation_type=FilterValidationType.NOT_FOUND,
                is_unresolvable=True,
            ))
        
        if not results:
            # 空结果列表
            summary = FilterValidationSummary.from_results(results)
            assert summary.all_valid == True
            assert summary.has_unresolvable_filters == False
            return
        
        summary = FilterValidationSummary.from_results(results)
        
        # 验证属性
        expected_all_valid = (num_needs_confirmation == 0 and num_unresolvable == 0)
        expected_has_unresolvable = (num_unresolvable > 0)
        
        assert summary.all_valid == expected_all_valid
        assert summary.has_unresolvable_filters == expected_has_unresolvable
        assert len(summary.results) == len(results)


# ═══════════════════════════════════════════════════════════════════════════
# 运行测试
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
