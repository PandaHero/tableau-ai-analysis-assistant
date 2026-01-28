# -*- coding: utf-8 -*-
"""
手动测试：FilterValueValidator 筛选值验证器

测试完整的筛选值验证流程：
1. 精确匹配
2. 模糊匹配（返回相似值）
3. 无匹配（无法解决）
4. 跳过验证（时间字段）
5. apply_confirmations 应用确认
"""
import asyncio
import sys
sys.path.insert(0, "..")

from analytics_assistant.src.platform.tableau.client import VizQLClient
from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import FieldValueCache
from analytics_assistant.src.agents.semantic_parser.components.filter_validator import FilterValueValidator
from analytics_assistant.src.agents.semantic_parser.schemas.output import (
    SemanticOutput,
    What,
    Where,
    SelfCheck,
)
from analytics_assistant.src.core.schemas.filters import SetFilter, FilterType
from analytics_assistant.src.core.schemas.fields import MeasureField
from analytics_assistant.src.core.schemas.enums import AggregationType


async def test_filter_value_validator():
    """测试 FilterValueValidator"""
    
    # 获取认证
    print("获取 Tableau 认证...")
    auth = await get_tableau_auth_async()
    print(f"认证成功，site: {auth.site}")
    
    # 创建组件
    client = VizQLClient()
    
    # 使用 TableauAdapter 作为平台适配器
    from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
    adapter = TableauAdapter(vizql_client=client)
    
    cache = FieldValueCache(max_fields=100)
    validator = FilterValueValidator(
        platform_adapter=adapter,
        field_value_cache=cache,
    )
    
    # 获取数据源
    datasource_name = "正大益生"
    print(f"\n查找数据源: {datasource_name}")
    datasource_luid = await client.get_datasource_luid_by_name(
        datasource_name=datasource_name,
        api_key=auth.api_key,
    )
    
    if not datasource_luid:
        print(f"未找到数据源: {datasource_name}")
        return
    
    print(f"数据源 LUID: {datasource_luid}")
    
    # 加载数据模型
    print("\n加载数据模型...")
    loader = TableauDataLoader(client=client)
    data_model = await loader.load_data_model(
        datasource_id=datasource_luid,
        auth=auth,
    )
    print(f"数据模型加载完成，字段数: {len(data_model.fields)}")
    
    # 构造测试用的 SemanticOutput
    test_cases = [
        {
            "name": "精确匹配",
            "filters": [
                SetFilter(
                    field_name="公司名称",
                    filter_type=FilterType.SET,
                    values=["正大益生科技发展（北京）有限公司"],
                )
            ],
        },
        {
            "name": "模糊匹配 - 应返回相似值",
            "filters": [
                SetFilter(
                    field_name="公司名称",
                    filter_type=FilterType.SET,
                    values=["正大益生"],
                )
            ],
        },
        {
            "name": "无匹配 - 应返回无法解决",
            "filters": [
                SetFilter(
                    field_name="公司名称",
                    filter_type=FilterType.SET,
                    values=["不存在的公司ABC123"],
                )
            ],
        },
    ]
    
    print("\n" + "=" * 70)
    print("开始测试 FilterValueValidator")
    print("=" * 70)
    
    for test_case in test_cases:
        print(f"\n{'─' * 70}")
        print(f"测试: {test_case['name']}")
        print(f"{'─' * 70}")
        
        # 构造 SemanticOutput
        semantic_output = SemanticOutput(
            restated_question="测试查询",
            what=What(measures=[MeasureField(field_name="销售额", aggregation=AggregationType.SUM)]),
            where=Where(
                dimensions=[],
                filters=test_case["filters"],
            ),
            self_check=SelfCheck(
                field_mapping_confidence=0.9,
                time_range_confidence=0.9,
                computation_confidence=0.9,
                overall_confidence=0.9,
            ),
        )
        
        try:
            summary = await validator.validate(
                semantic_output=semantic_output,
                data_model=data_model,
                datasource_id=datasource_luid,
                api_key=auth.api_key,
                site=auth.site,
            )
            
            print(f"结果:")
            print(f"  all_valid: {summary.all_valid}")
            print(f"  has_unresolvable_filters: {summary.has_unresolvable_filters}")
            print(f"  results count: {len(summary.results)}")
            
            for r in summary.results:
                print(f"\n  筛选条件: {r.field_name} = {r.requested_value}")
                print(f"    is_valid: {r.is_valid}")
                print(f"    validation_type: {r.validation_type}")
                print(f"    needs_confirmation: {r.needs_confirmation}")
                print(f"    is_unresolvable: {r.is_unresolvable}")
                if r.similar_values:
                    print(f"    similar_values: {r.similar_values}")
                if r.message:
                    print(f"    message: {r.message}")
                    
        except Exception as e:
            print(f"错误: {e}")
            import traceback
            traceback.print_exc()
    
    # 测试 apply_confirmations
    print(f"\n{'─' * 70}")
    print("测试: apply_confirmations")
    print(f"{'─' * 70}")
    
    semantic_output = SemanticOutput(
        restated_question="测试查询",
        what=What(measures=[MeasureField(field_name="销售额", aggregation=AggregationType.SUM)]),
        where=Where(
            dimensions=[],
            filters=[
                SetFilter(
                    field_name="公司名称",
                    filter_type=FilterType.SET,
                    values=["正大益生"],
                )
            ],
        ),
        self_check=SelfCheck(
            field_mapping_confidence=0.9,
            time_range_confidence=0.9,
            computation_confidence=0.9,
            overall_confidence=0.9,
        ),
    )
    
    print(f"原始筛选值: {semantic_output.where.filters[0].values}")
    
    updated = validator.apply_confirmations(
        semantic_output=semantic_output,
        confirmations={"正大益生": "正大益生科技发展（北京）有限公司"},
    )
    
    print(f"确认后筛选值: {updated.where.filters[0].values}")
    
    # 关闭客户端
    await client.close()
    
    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_filter_value_validator())
