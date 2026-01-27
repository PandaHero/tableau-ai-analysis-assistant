# -*- coding: utf-8 -*-
"""
测试语义解析器 schemas 是否能正常导入和使用
"""
import sys
from datetime import datetime, timedelta

def test_imports():
    """测试所有 schemas 能否正常导入"""
    print("=" * 60)
    print("1. 测试导入")
    print("=" * 60)
    
    try:
        from analytics_assistant.src.agents.semantic_parser.schemas import (
            # Output
            CalcType,
            ClarificationSource,
            DerivedComputation,
            SelfCheck,
            What,
            Where,
            SemanticOutput,
            # Intermediate
            FieldCandidate,
            FewShotExample,
            # Cache
            CachedQuery,
            CachedFieldValues,
            # Filters
            FilterValidationType,
            FilterValidationResult,
            FilterValidationSummary,
            FilterConfirmation,
        )
        print("✓ 所有 schemas 导入成功")
        return True
    except Exception as e:
        print(f"✗ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_calc_type_enum():
    """测试 CalcType 枚举"""
    print("\n" + "=" * 60)
    print("2. 测试 CalcType 枚举")
    print("=" * 60)
    
    from analytics_assistant.src.agents.semantic_parser.schemas import CalcType
    
    print("简单计算类型:")
    simple_types = [CalcType.RATIO, CalcType.SUM, CalcType.DIFFERENCE, 
                    CalcType.PRODUCT, CalcType.FORMULA]
    for t in simple_types:
        print(f"  - {t.value}")
    
    print("\nLOD 类型:")
    lod_types = [CalcType.LOD_FIXED, CalcType.LOD_INCLUDE, CalcType.LOD_EXCLUDE]
    for t in lod_types:
        print(f"  - {t.value}")
    
    print("\n表计算类型:")
    table_calc_types = [
        CalcType.TABLE_CALC_RANK,
        CalcType.TABLE_CALC_PERCENTILE,
        CalcType.TABLE_CALC_DIFFERENCE,
        CalcType.TABLE_CALC_PERCENT_DIFF,
        CalcType.TABLE_CALC_PERCENT_OF_TOTAL,
        CalcType.TABLE_CALC_RUNNING,
        CalcType.TABLE_CALC_MOVING,
    ]
    for t in table_calc_types:
        print(f"  - {t.value}")
    
    print(f"\n✓ CalcType 共 {len(CalcType)} 个枚举值")


def test_derived_computation():
    """测试 DerivedComputation 模型"""
    print("\n" + "=" * 60)
    print("3. 测试 DerivedComputation 模型")
    print("=" * 60)
    
    from analytics_assistant.src.agents.semantic_parser.schemas import (
        DerivedComputation, CalcType
    )
    
    # 测试 RATIO 类型（利润率）
    profit_rate = DerivedComputation(
        name="profit_rate",
        display_name="利润率",
        formula="[利润]/[销售额]",
        calc_type=CalcType.RATIO,
        base_measures=["利润", "销售额"],
    )
    print(f"✓ RATIO 示例: {profit_rate.display_name} = {profit_rate.formula}")
    
    # 测试 TABLE_CALC_PERCENT_DIFF 类型（增长率）
    growth_rate = DerivedComputation(
        name="sales_growth",
        display_name="销售额增长率",
        calc_type=CalcType.TABLE_CALC_PERCENT_DIFF,
        base_measures=["销售额"],
        relative_to="PREVIOUS",
    )
    print(f"✓ TABLE_CALC_PERCENT_DIFF 示例: {growth_rate.display_name}")
    
    # 测试 LOD_FIXED 类型
    first_purchase = DerivedComputation(
        name="first_purchase_date",
        display_name="客户首购日期",
        calc_type=CalcType.LOD_FIXED,
        base_measures=["订单日期"],
        lod_dimensions=["客户ID"],
    )
    print(f"✓ LOD_FIXED 示例: {first_purchase.display_name}")


def test_semantic_output():
    """测试 SemanticOutput 模型"""
    print("\n" + "=" * 60)
    print("4. 测试 SemanticOutput 模型")
    print("=" * 60)
    
    from analytics_assistant.src.agents.semantic_parser.schemas import (
        SemanticOutput, SelfCheck, What, Where, DerivedComputation, CalcType
    )
    from analytics_assistant.src.core.schemas.fields import MeasureField, DimensionField
    from analytics_assistant.src.core.schemas.enums import AggregationType, HowType
    
    # 创建一个完整的 SemanticOutput
    output = SemanticOutput(
        restated_question="查询上个月各地区的利润率",
        what=What(
            measures=[
                MeasureField(field_name="利润", aggregation=AggregationType.SUM),
                MeasureField(field_name="销售额", aggregation=AggregationType.SUM),
            ]
        ),
        where=Where(
            dimensions=[
                DimensionField(field_name="地区"),
            ],
            filters=[],
        ),
        how_type=HowType.SIMPLE,
        computations=[
            DerivedComputation(
                name="profit_rate",
                display_name="利润率",
                formula="[利润]/[销售额]",
                calc_type=CalcType.RATIO,
                base_measures=["利润", "销售额"],
            )
        ],
        self_check=SelfCheck(
            field_mapping_confidence=0.95,
            time_range_confidence=0.90,
            computation_confidence=0.85,
            overall_confidence=0.90,
            potential_issues=[],
        ),
    )
    
    print(f"✓ query_id: {output.query_id}")
    print(f"✓ restated_question: {output.restated_question}")
    print(f"✓ measures: {[m.field_name for m in output.what.measures]}")
    print(f"✓ dimensions: {[d.field_name for d in output.where.dimensions]}")
    print(f"✓ computations: {[c.display_name for c in output.computations]}")
    print(f"✓ overall_confidence: {output.self_check.overall_confidence}")


def test_filter_validation():
    """测试筛选器验证模型"""
    print("\n" + "=" * 60)
    print("5. 测试筛选器验证模型")
    print("=" * 60)
    
    from analytics_assistant.src.agents.semantic_parser.schemas import (
        FilterValidationType,
        FilterValidationResult,
        FilterValidationSummary,
        FilterConfirmation,
    )
    
    # 测试精确匹配
    exact_match = FilterValidationResult(
        is_valid=True,
        field_name="地区",
        requested_value="华东",
        matched_values=["华东"],
        validation_type=FilterValidationType.EXACT_MATCH,
    )
    print(f"✓ 精确匹配: {exact_match.field_name}={exact_match.requested_value}")
    
    # 测试需要确认
    needs_confirm = FilterValidationResult(
        is_valid=False,
        field_name="省份",
        requested_value="上海",
        similar_values=["上海市", "上海浦东"],
        validation_type=FilterValidationType.NEEDS_CONFIRMATION,
        needs_confirmation=True,
        message="找到多个相似值，请选择",
    )
    print(f"✓ 需要确认: {needs_confirm.field_name}={needs_confirm.requested_value}")
    print(f"  相似值: {needs_confirm.similar_values}")
    
    # 测试汇总
    summary = FilterValidationSummary.from_results([exact_match, needs_confirm])
    print(f"✓ 汇总: all_valid={summary.all_valid}")
    
    # 测试确认记录
    confirmation = FilterConfirmation(
        field_name="省份",
        original_value="上海",
        confirmed_value="上海市",
    )
    print(f"✓ 确认记录: {confirmation.original_value} → {confirmation.confirmed_value}")


def test_cache_models():
    """测试缓存模型"""
    print("\n" + "=" * 60)
    print("6. 测试缓存模型")
    print("=" * 60)
    
    from analytics_assistant.src.agents.semantic_parser.schemas import (
        CachedQuery, CachedFieldValues
    )
    
    # 测试 CachedQuery
    cached_query = CachedQuery(
        question="各地区销售额",
        question_hash="abc123",
        question_embedding=[0.1] * 10,  # 简化的 embedding
        datasource_luid="ds-001",
        schema_hash="schema-hash-001",
        semantic_output={"restated_question": "查询各地区的销售额"},
        query="SELECT region, SUM(sales) FROM ...",
        expires_at=datetime.now() + timedelta(hours=24),
    )
    print(f"✓ CachedQuery: {cached_query.question}")
    
    # 测试 CachedFieldValues
    cached_values = CachedFieldValues(
        field_name="地区",
        datasource_luid="ds-001",
        values=["华东", "华南", "华北", "西南", "西北"],
        cardinality=5,
        expires_at=datetime.now() + timedelta(hours=1),
    )
    print(f"✓ CachedFieldValues: {cached_values.field_name} ({cached_values.cardinality} 个值)")


def test_field_candidate():
    """测试 FieldCandidate 模型"""
    print("\n" + "=" * 60)
    print("7. 测试 FieldCandidate 模型")
    print("=" * 60)
    
    from analytics_assistant.src.agents.semantic_parser.schemas import FieldCandidate
    
    candidate = FieldCandidate(
        field_name="Sales",
        field_caption="销售额",
        field_type="measure",
        data_type="number",
        description="产品销售金额",
        sample_values=["1000", "2500", "3800"],
        confidence=0.95,
        match_type="exact",
        category="financial",
        level=3,
    )
    print(f"✓ FieldCandidate: {candidate.field_caption} ({candidate.field_type})")
    print(f"  confidence: {candidate.confidence}, match_type: {candidate.match_type}")


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("语义解析器 Schemas 测试")
    print("=" * 60)
    
    if not test_imports():
        print("\n导入失败，终止测试")
        return
    
    test_calc_type_enum()
    test_derived_computation()
    test_semantic_output()
    test_filter_validation()
    test_cache_models()
    test_field_candidate()
    
    print("\n" + "=" * 60)
    print("✓ 所有测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    main()
