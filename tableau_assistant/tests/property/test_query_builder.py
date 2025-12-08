"""
Property Tests for QueryBuilder Node

Tests:
- Property 21: ImplementationResolver LOD judgment
- Property 22: ExpressionGenerator syntax correctness
- Property 14: Query building correctness

Requirements:
- R7.2.8-14: Implementation resolution and expression generation
"""

import pytest
from hypothesis import given, strategies as st, settings, assume
from typing import List, Dict, Any

from tableau_assistant.src.nodes.query_builder import (
    ImplementationResolver,
    ExpressionGenerator,
    QueryBuilderNode,
)
from tableau_assistant.src.nodes.query_builder.implementation_resolver import (
    ImplementationType,
    ImplementationDecision,
)
from tableau_assistant.src.nodes.query_builder.expression_generator import (
    GeneratedExpression,
)
from tableau_assistant.src.models.semantic.query import (
    SemanticQuery,
    MappedQuery,
    MeasureSpec,
    DimensionSpec,
    AnalysisSpec,
    FieldMapping,
)
from tableau_assistant.src.models.semantic.enums import (
    AnalysisType,
    ComputationScope,
    AggregationType,
    TimeGranularity,
    MappingSource,
)


# ============= Strategies =============

@st.composite
def dimension_spec_strategy(draw):
    """Generate valid DimensionSpec."""
    name = draw(st.sampled_from(["省份", "城市", "产品", "类别", "日期", "月份"]))
    is_time = name in ["日期", "月份"]
    
    time_granularity = None
    if is_time:
        time_granularity = draw(st.sampled_from([
            TimeGranularity.YEAR,
            TimeGranularity.QUARTER,
            TimeGranularity.MONTH,
            TimeGranularity.DAY,
            None,
        ]))
    
    return DimensionSpec(
        name=name,
        time_granularity=time_granularity,
    )


@st.composite
def analysis_spec_strategy(draw, dim_count: int = 1):
    """Generate valid AnalysisSpec."""
    analysis_type = draw(st.sampled_from([
        AnalysisType.CUMULATIVE,
        AnalysisType.RANKING,
        AnalysisType.PERCENTAGE,
        AnalysisType.MOVING,
    ]))
    
    target_measure = draw(st.sampled_from(["销售额", "利润", "数量"]))
    
    # computation_scope only when dim_count > 1
    computation_scope = None
    if dim_count > 1:
        computation_scope = draw(st.sampled_from([
            ComputationScope.PER_GROUP,
            ComputationScope.ACROSS_ALL,
            None,
        ]))
    
    # Type-specific fields
    window_size = None
    order = None  # 新字段名（原 rank_direction）
    
    if analysis_type == AnalysisType.MOVING:
        window_size = draw(st.integers(min_value=2, max_value=10))
    elif analysis_type == AnalysisType.RANKING:
        order = draw(st.sampled_from(["asc", "desc"]))
    
    return AnalysisSpec(
        type=analysis_type,
        target_measure=target_measure,
        computation_scope=computation_scope,
        window_size=window_size,
        order=order,
    )


# ============= Property Tests =============

class TestImplementationResolver:
    """Tests for ImplementationResolver."""
    
    def test_single_dimension_cumulative_uses_table_calc(self):
        """
        Property 21: Single dimension cumulative should use table calc.
        
        When there's only one dimension, cumulative analysis should
        use table calculation with that dimension as addressing.
        """
        resolver = ImplementationResolver()
        
        analysis = AnalysisSpec(
            type=AnalysisType.CUMULATIVE,
            target_measure="销售额",
        )
        
        dimensions = [DimensionSpec(name="日期", is_time=True, time_granularity=TimeGranularity.MONTH)]
        field_mappings = {"日期": "Order_Date"}
        
        decision = resolver.resolve(analysis, dimensions, field_mappings)
        
        assert decision.impl_type == ImplementationType.TABLE_CALC
        assert "Order_Date" in decision.addressing
    
    def test_multi_dimension_per_group_partitions_correctly(self):
        """
        Property 21: Multi-dimension per_group should partition by non-time dimensions.
        
        When computation_scope is per_group with multiple dimensions,
        time dimension should be addressing, others should be partitioning.
        """
        resolver = ImplementationResolver()
        
        analysis = AnalysisSpec(
            type=AnalysisType.CUMULATIVE,
            target_measure="销售额",
            computation_scope=ComputationScope.PER_GROUP,
        )
        
        dimensions = [
            DimensionSpec(name="省份", is_time=False),
            DimensionSpec(name="日期", is_time=True, time_granularity=TimeGranularity.MONTH),
        ]
        field_mappings = {"省份": "State", "日期": "Order_Date"}
        
        decision = resolver.resolve(analysis, dimensions, field_mappings)
        
        assert decision.impl_type == ImplementationType.TABLE_CALC
        # Time dimension should be in addressing
        assert "Order_Date" in decision.addressing
        # Non-time dimension should be in partitioning
        assert "State" in decision.partitioning
    
    def test_multi_dimension_across_all_addresses_all(self):
        """
        Property 21: Multi-dimension across_all should address all dimensions.
        
        When computation_scope is across_all, all dimensions should be
        in addressing (no partitioning).
        """
        resolver = ImplementationResolver()
        
        analysis = AnalysisSpec(
            type=AnalysisType.CUMULATIVE,
            target_measure="销售额",
            computation_scope=ComputationScope.ACROSS_ALL,
        )
        
        dimensions = [
            DimensionSpec(name="省份", is_time=False),
            DimensionSpec(name="日期", is_time=True, time_granularity=TimeGranularity.MONTH),
        ]
        field_mappings = {"省份": "State", "日期": "Order_Date"}
        
        decision = resolver.resolve(analysis, dimensions, field_mappings)
        
        assert decision.impl_type == ImplementationType.TABLE_CALC
        # All dimensions should be in addressing
        assert len(decision.addressing) == 2
        assert "State" in decision.addressing
        assert "Order_Date" in decision.addressing
    
    def test_no_dimensions_uses_simple_agg(self):
        """
        Property 21: No dimensions should use simple aggregation.
        """
        resolver = ImplementationResolver()
        
        analysis = AnalysisSpec(
            type=AnalysisType.CUMULATIVE,
            target_measure="销售额",
        )
        
        dimensions = []
        field_mappings = {}
        
        decision = resolver.resolve(analysis, dimensions, field_mappings)
        
        assert decision.impl_type == ImplementationType.SIMPLE_AGG
    
    @given(st.sampled_from([
        AnalysisType.CUMULATIVE,
        AnalysisType.RANKING,
        AnalysisType.PERCENTAGE,
        AnalysisType.MOVING,
    ]))
    @settings(max_examples=20)
    def test_all_analysis_types_return_valid_decision(self, analysis_type):
        """
        Property: All analysis types should return a valid decision.
        """
        resolver = ImplementationResolver()
        
        analysis = AnalysisSpec(
            type=analysis_type,
            target_measure="销售额",
            window_size=3 if analysis_type == AnalysisType.MOVING else None,
        )
        
        dimensions = [DimensionSpec(name="日期", is_time=True, time_granularity=TimeGranularity.MONTH)]
        field_mappings = {"日期": "Order_Date"}
        
        decision = resolver.resolve(analysis, dimensions, field_mappings)
        
        assert isinstance(decision, ImplementationDecision)
        assert decision.impl_type in ImplementationType


class TestExpressionGenerator:
    """Tests for ExpressionGenerator."""
    
    def test_running_total_generates_valid_spec(self):
        """
        Property 22: Running total should generate valid table calc spec.
        """
        generator = ExpressionGenerator()
        
        decision = ImplementationDecision(
            impl_type=ImplementationType.TABLE_CALC,
            addressing=["Order_Date"],
        )
        
        expression = generator.generate(
            AnalysisType.CUMULATIVE,
            decision,
            "Sales",
            AggregationType.SUM,
        )
        
        assert expression.table_calc_spec is not None
        assert expression.table_calc_spec.tableCalcType == "RUNNING_TOTAL"
        assert len(expression.table_calc_spec.dimensions) == 1
        assert expression.table_calc_spec.dimensions[0].fieldCaption == "Order_Date"
    
    def test_rank_generates_valid_spec(self):
        """
        Property 22: Rank should generate valid table calc spec.
        """
        generator = ExpressionGenerator()
        
        decision = ImplementationDecision(
            impl_type=ImplementationType.TABLE_CALC,
            addressing=["Category"],
        )
        
        expression = generator.generate(
            AnalysisType.RANKING,
            decision,
            "Sales",
            AggregationType.SUM,
            order="desc",
        )
        
        assert expression.table_calc_spec is not None
        assert expression.table_calc_spec.tableCalcType == "RANK"
        assert expression.table_calc_spec.rankType == "COMPETITION"
    
    def test_moving_generates_valid_spec(self):
        """
        Property 22: Moving calculation should generate valid table calc spec.
        """
        generator = ExpressionGenerator()
        
        decision = ImplementationDecision(
            impl_type=ImplementationType.TABLE_CALC,
            addressing=["Order_Date"],
        )
        
        expression = generator.generate(
            AnalysisType.MOVING,
            decision,
            "Sales",
            AggregationType.AVG,
            window_size=3,
        )
        
        assert expression.table_calc_spec is not None
        assert expression.table_calc_spec.tableCalcType == "MOVING_CALCULATION"
        assert expression.table_calc_spec.previous == 2  # window_size - 1
        assert expression.table_calc_spec.next == 0
        assert expression.table_calc_spec.includeCurrent is True
    
    def test_percent_of_total_generates_valid_spec(self):
        """
        Property 22: Percent of total should generate valid table calc spec.
        """
        generator = ExpressionGenerator()
        
        decision = ImplementationDecision(
            impl_type=ImplementationType.TABLE_CALC,
            addressing=["Category"],
        )
        
        expression = generator.generate(
            AnalysisType.PERCENTAGE,
            decision,
            "Sales",
            AggregationType.SUM,
        )
        
        assert expression.table_calc_spec is not None
        assert expression.table_calc_spec.tableCalcType == "PERCENT_OF_TOTAL"
    
    def test_lod_fixed_generates_valid_calculation(self):
        """
        Property 22: LOD FIXED should generate valid calculation string.
        """
        generator = ExpressionGenerator()
        
        decision = ImplementationDecision(
            impl_type=ImplementationType.LOD_FIXED,
            lod_dimensions=["Category"],
        )
        
        expression = generator.generate(
            AnalysisType.CUMULATIVE,
            decision,
            "Sales",
            AggregationType.SUM,
        )
        
        assert expression.calculation is not None
        assert "{FIXED" in expression.calculation
        assert "[Category]" in expression.calculation
        assert "SUM([Sales])" in expression.calculation
    
    def test_simple_agg_returns_function_only(self):
        """
        Property 22: Simple aggregation should return function only.
        """
        generator = ExpressionGenerator()
        
        decision = ImplementationDecision(
            impl_type=ImplementationType.SIMPLE_AGG,
        )
        
        expression = generator.generate(
            AnalysisType.CUMULATIVE,
            decision,
            "Sales",
            AggregationType.SUM,
        )
        
        assert expression.table_calc_spec is None
        assert expression.calculation is None
        assert expression.function is not None
    
    @given(st.sampled_from([
        AggregationType.SUM,
        AggregationType.AVG,
        AggregationType.COUNT,
        AggregationType.MIN,
        AggregationType.MAX,
    ]))
    @settings(max_examples=10)
    def test_all_aggregation_types_work(self, agg_type):
        """
        Property: All aggregation types should generate valid expressions.
        """
        generator = ExpressionGenerator()
        
        decision = ImplementationDecision(
            impl_type=ImplementationType.TABLE_CALC,
            addressing=["Order_Date"],
        )
        
        expression = generator.generate(
            AnalysisType.CUMULATIVE,
            decision,
            "Sales",
            agg_type,
        )
        
        assert isinstance(expression, GeneratedExpression)
        # Should have either table_calc_spec or function
        assert expression.table_calc_spec is not None or expression.function is not None


class TestQueryBuilderNode:
    """Tests for QueryBuilder Node integration."""
    
    @pytest.mark.asyncio
    async def test_build_simple_query(self):
        """
        Property 14: Simple query should build correctly.
        """
        builder = QueryBuilderNode()
        
        semantic_query = SemanticQuery(
            measures=[MeasureSpec(name="销售额", aggregation=AggregationType.SUM)],
            dimensions=[DimensionSpec(name="省份")],
        )
        
        mapped_query = MappedQuery(
            semantic_query=semantic_query,
            field_mappings={
                "销售额": FieldMapping(
                    business_term="销售额",
                    technical_field="Sales",
                    confidence=0.95,
                    mapping_source=MappingSource.RAG_HIGH_CONFIDENCE,
                ),
                "省份": FieldMapping(
                    business_term="省份",
                    technical_field="State",
                    confidence=0.92,
                    mapping_source=MappingSource.RAG_HIGH_CONFIDENCE,
                ),
            },
            overall_confidence=0.92,
        )
        
        vizql_query = await builder.build(mapped_query)
        
        assert vizql_query is not None
        assert len(vizql_query.fields) == 2  # 1 dimension + 1 measure
    
    @pytest.mark.asyncio
    async def test_build_query_with_analysis(self):
        """
        Property 14: Query with analysis should include table calc field.
        """
        builder = QueryBuilderNode()
        
        semantic_query = SemanticQuery(
            measures=[MeasureSpec(name="销售额", aggregation=AggregationType.SUM)],
            dimensions=[
                DimensionSpec(name="日期", is_time=True, time_granularity=TimeGranularity.MONTH),
            ],
            analyses=[
                AnalysisSpec(
                    type=AnalysisType.CUMULATIVE,
                    target_measure="销售额",
                ),
            ],
        )
        
        mapped_query = MappedQuery(
            semantic_query=semantic_query,
            field_mappings={
                "销售额": FieldMapping(
                    business_term="销售额",
                    technical_field="Sales",
                    confidence=0.95,
                    mapping_source=MappingSource.RAG_HIGH_CONFIDENCE,
                ),
                "日期": FieldMapping(
                    business_term="日期",
                    technical_field="Order_Date",
                    confidence=0.92,
                    mapping_source=MappingSource.RAG_HIGH_CONFIDENCE,
                ),
            },
            overall_confidence=0.92,
        )
        
        vizql_query = await builder.build(mapped_query)
        
        assert vizql_query is not None
        # Should have: 1 dimension + 1 measure + 1 analysis field
        assert len(vizql_query.fields) == 3
    
    @pytest.mark.asyncio
    async def test_build_query_with_time_granularity(self):
        """
        Property 14: Time dimension should have correct function.
        """
        builder = QueryBuilderNode()
        
        semantic_query = SemanticQuery(
            measures=[MeasureSpec(name="销售额")],
            dimensions=[
                DimensionSpec(name="日期", is_time=True, time_granularity=TimeGranularity.MONTH),
            ],
        )
        
        mapped_query = MappedQuery(
            semantic_query=semantic_query,
            field_mappings={
                "销售额": FieldMapping(
                    business_term="销售额",
                    technical_field="Sales",
                    confidence=0.95,
                    mapping_source=MappingSource.RAG_HIGH_CONFIDENCE,
                ),
                "日期": FieldMapping(
                    business_term="日期",
                    technical_field="Order_Date",
                    confidence=0.92,
                    mapping_source=MappingSource.RAG_HIGH_CONFIDENCE,
                ),
            },
            overall_confidence=0.92,
        )
        
        vizql_query = await builder.build(mapped_query)
        
        # Check that time dimension has MONTH function
        query_dict = vizql_query.to_dict()
        time_field = query_dict["fields"][0]
        assert time_field.get("function") == "MONTH"
