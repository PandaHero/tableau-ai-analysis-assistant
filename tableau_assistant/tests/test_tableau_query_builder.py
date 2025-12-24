# -*- coding: utf-8 -*-
"""TableauQueryBuilder Unit Tests.

Tests for Task 8: Unit tests for TableauQueryBuilder conversion logic.
Covers all CalcType conversions, default value application, and LOD + Table Calc ordering.
"""

import pytest

from tableau_assistant.src.core.models import (
    # Enums
    AggregationType,
    CalcAggregation,
    CalcType,
    RankStyle,
    RelativeTo,
    SortDirection,
    # Models
    CalcParams,
    Computation,
    DimensionField,
    MeasureField,
    SemanticQuery,
)
from tableau_assistant.src.platforms.tableau.query_builder import TableauQueryBuilder


@pytest.fixture
def builder() -> TableauQueryBuilder:
    """Create a TableauQueryBuilder instance."""
    return TableauQueryBuilder()


@pytest.fixture
def base_query() -> SemanticQuery:
    """Create a base SemanticQuery with dimensions and measures."""
    return SemanticQuery(
        dimensions=[
            DimensionField(field_name="Month"),
            DimensionField(field_name="Region"),
        ],
        measures=[
            MeasureField(field_name="Sales", aggregation=AggregationType.SUM),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════
# RANK / DENSE_RANK Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRankSpec:
    """Test _build_rank_spec method."""
    
    def test_rank_with_defaults(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """RANK with no params should use Tableau defaults."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.RANK,
                partition_by=["Month"],
                params=CalcParams(),
            )
        ]
        result = builder.build(base_query)
        
        table_calc = result["fields"][-1]["tableCalculation"]
        assert table_calc["tableCalcType"] == "RANK"
        assert table_calc["rankType"] == "COMPETITION"  # DEFAULT_RANK_STYLE
        assert table_calc["direction"] == "DESC"  # DEFAULT_DIRECTION
        assert table_calc["dimensions"] == [{"fieldCaption": "Month"}]
    
    def test_rank_with_custom_params(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """RANK with custom params should override defaults."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.RANK,
                partition_by=["Region"],
                params=CalcParams(
                    direction=SortDirection.ASC,
                    rank_style=RankStyle.UNIQUE,
                ),
            )
        ]
        result = builder.build(base_query)
        
        table_calc = result["fields"][-1]["tableCalculation"]
        assert table_calc["rankType"] == "UNIQUE"
        assert table_calc["direction"] == "ASC"
    
    def test_dense_rank(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """DENSE_RANK should always use DENSE rank type."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.DENSE_RANK,
                partition_by=["Month"],
                params=CalcParams(rank_style=RankStyle.COMPETITION),  # Should be ignored
            )
        ]
        result = builder.build(base_query)
        
        table_calc = result["fields"][-1]["tableCalculation"]
        assert table_calc["tableCalcType"] == "RANK"
        assert table_calc["rankType"] == "DENSE"  # Always DENSE for DENSE_RANK


# ═══════════════════════════════════════════════════════════════════════════
# PERCENTILE Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPercentileSpec:
    """Test _build_percentile_spec method."""
    
    def test_percentile_with_defaults(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """PERCENTILE with no params should use default direction."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.PERCENTILE,
                partition_by=["Month"],
                params=CalcParams(),
            )
        ]
        result = builder.build(base_query)
        
        table_calc = result["fields"][-1]["tableCalculation"]
        assert table_calc["tableCalcType"] == "PERCENTILE"
        assert table_calc["direction"] == "DESC"
    
    def test_percentile_ascending(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """PERCENTILE with ASC direction."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.PERCENTILE,
                partition_by=[],
                params=CalcParams(direction=SortDirection.ASC),
            )
        ]
        result = builder.build(base_query)
        
        table_calc = result["fields"][-1]["tableCalculation"]
        assert table_calc["direction"] == "ASC"


# ═══════════════════════════════════════════════════════════════════════════
# RUNNING_TOTAL Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRunningTotalSpec:
    """Test _build_running_total_spec method."""
    
    def test_running_total_with_defaults(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """RUNNING_TOTAL with no params should use default aggregation."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.RUNNING_TOTAL,
                partition_by=["Region"],
                params=CalcParams(),
            )
        ]
        result = builder.build(base_query)
        
        table_calc = result["fields"][-1]["tableCalculation"]
        assert table_calc["tableCalcType"] == "RUNNING_TOTAL"
        assert table_calc["aggregation"] == "SUM"  # DEFAULT_AGGREGATION
        assert "restartEvery" not in table_calc
    
    def test_running_total_with_restart(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """RUNNING_TOTAL with restart_every (YTD pattern)."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.RUNNING_TOTAL,
                partition_by=["Region"],
                params=CalcParams(
                    aggregation=CalcAggregation.SUM,
                    restart_every="Year",
                ),
            )
        ]
        result = builder.build(base_query)
        
        table_calc = result["fields"][-1]["tableCalculation"]
        assert table_calc["restartEvery"] == {"fieldCaption": "Year"}
    
    def test_running_total_avg(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """RUNNING_TOTAL with AVG aggregation."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.RUNNING_TOTAL,
                partition_by=[],
                params=CalcParams(aggregation=CalcAggregation.AVG),
            )
        ]
        result = builder.build(base_query)
        
        table_calc = result["fields"][-1]["tableCalculation"]
        assert table_calc["aggregation"] == "AVG"


# ═══════════════════════════════════════════════════════════════════════════
# MOVING_CALC Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestMovingCalcSpec:
    """Test _build_moving_calc_spec method."""
    
    def test_moving_calc_with_defaults(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """MOVING_CALC with no params should use all defaults."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.MOVING_CALC,
                partition_by=["Region"],
                params=CalcParams(),
            )
        ]
        result = builder.build(base_query)
        
        table_calc = result["fields"][-1]["tableCalculation"]
        assert table_calc["tableCalcType"] == "MOVING_CALCULATION"
        assert table_calc["aggregation"] == "SUM"  # DEFAULT_AGGREGATION
        assert table_calc["previous"] == 2  # DEFAULT_WINDOW_PREVIOUS
        assert table_calc["next"] == 0  # DEFAULT_WINDOW_NEXT
        assert table_calc["includeCurrent"] is True  # DEFAULT_INCLUDE_CURRENT
    
    def test_moving_calc_custom_window(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """MOVING_CALC with custom window parameters."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.MOVING_CALC,
                partition_by=["Month"],
                params=CalcParams(
                    aggregation=CalcAggregation.AVG,
                    window_previous=3,
                    window_next=1,
                    include_current=False,
                ),
            )
        ]
        result = builder.build(base_query)
        
        table_calc = result["fields"][-1]["tableCalculation"]
        assert table_calc["aggregation"] == "AVG"
        assert table_calc["previous"] == 3
        assert table_calc["next"] == 1
        assert table_calc["includeCurrent"] is False


# ═══════════════════════════════════════════════════════════════════════════
# PERCENT_OF_TOTAL Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPercentOfTotalSpec:
    """Test _build_percent_of_total_spec method."""
    
    def test_percent_of_total_global(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """PERCENT_OF_TOTAL with empty partition (global)."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.PERCENT_OF_TOTAL,
                partition_by=[],
                params=CalcParams(),
            )
        ]
        result = builder.build(base_query)
        
        table_calc = result["fields"][-1]["tableCalculation"]
        assert table_calc["tableCalcType"] == "PERCENT_OF_TOTAL"
        assert table_calc["dimensions"] == []
        assert "levelAddress" not in table_calc
    
    def test_percent_of_total_with_level(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """PERCENT_OF_TOTAL with level_of parameter."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.PERCENT_OF_TOTAL,
                partition_by=["Region"],
                params=CalcParams(level_of="Region"),
            )
        ]
        result = builder.build(base_query)
        
        table_calc = result["fields"][-1]["tableCalculation"]
        assert table_calc["levelAddress"] == {"fieldCaption": "Region"}


# ═══════════════════════════════════════════════════════════════════════════
# DIFFERENCE / PERCENT_DIFFERENCE Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestDifferenceSpec:
    """Test _build_difference_spec and _build_percent_difference_spec methods."""
    
    def test_difference_with_defaults(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """DIFFERENCE with no params should use PREVIOUS."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.DIFFERENCE,
                partition_by=["Region"],
                params=CalcParams(),
            )
        ]
        result = builder.build(base_query)
        
        table_calc = result["fields"][-1]["tableCalculation"]
        assert table_calc["tableCalcType"] == "DIFFERENCE_FROM"
        assert table_calc["relativeTo"] == "PREVIOUS"  # DEFAULT_RELATIVE_TO
    
    def test_difference_from_first(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """DIFFERENCE relative to FIRST."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.DIFFERENCE,
                partition_by=["Month"],
                params=CalcParams(relative_to=RelativeTo.FIRST),
            )
        ]
        result = builder.build(base_query)
        
        table_calc = result["fields"][-1]["tableCalculation"]
        assert table_calc["relativeTo"] == "FIRST"
    
    def test_percent_difference_with_defaults(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """PERCENT_DIFFERENCE with no params should use PREVIOUS."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.PERCENT_DIFFERENCE,
                partition_by=["Month"],
                params=CalcParams(),
            )
        ]
        result = builder.build(base_query)
        
        table_calc = result["fields"][-1]["tableCalculation"]
        assert table_calc["tableCalcType"] == "PERCENT_DIFFERENCE_FROM"
        assert table_calc["relativeTo"] == "PREVIOUS"
    
    def test_percent_difference_mom(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """PERCENT_DIFFERENCE for MoM growth rate."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.PERCENT_DIFFERENCE,
                partition_by=["Region"],
                params=CalcParams(relative_to=RelativeTo.PREVIOUS),
            )
        ]
        result = builder.build(base_query)
        
        table_calc = result["fields"][-1]["tableCalculation"]
        assert table_calc["tableCalcType"] == "PERCENT_DIFFERENCE_FROM"
        assert table_calc["relativeTo"] == "PREVIOUS"


# ═══════════════════════════════════════════════════════════════════════════
# LOD Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestLODField:
    """Test _build_lod_field method."""
    
    def test_lod_fixed(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """LOD_FIXED should generate correct expression."""
        base_query.computations = [
            Computation(
                target="OrderDate",
                calc_type=CalcType.LOD_FIXED,
                partition_by=[],
                params=CalcParams(
                    lod_dimensions=["CustomerID"],
                    lod_aggregation=AggregationType.MIN,
                ),
                alias="FirstPurchase",
            )
        ]
        result = builder.build(base_query)
        
        lod_field = result["fields"][-1]
        assert lod_field["fieldCaption"] == "FirstPurchase"
        assert lod_field["calculation"] == "{FIXED [CustomerID] : MIN([OrderDate])}"
    
    def test_lod_include(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """LOD_INCLUDE should generate correct expression."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.LOD_INCLUDE,
                partition_by=[],
                params=CalcParams(
                    lod_dimensions=["ProductID"],
                    lod_aggregation=AggregationType.SUM,
                ),
            )
        ]
        result = builder.build(base_query)
        
        lod_field = result["fields"][-1]
        assert lod_field["calculation"] == "{INCLUDE [ProductID] : SUM([Sales])}"
    
    def test_lod_exclude(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """LOD_EXCLUDE should generate correct expression."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.LOD_EXCLUDE,
                partition_by=[],
                params=CalcParams(
                    lod_dimensions=["Month"],
                    lod_aggregation=AggregationType.AVG,
                ),
            )
        ]
        result = builder.build(base_query)
        
        lod_field = result["fields"][-1]
        assert lod_field["calculation"] == "{EXCLUDE [Month] : AVG([Sales])}"
    
    def test_lod_multiple_dimensions(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """LOD with multiple dimensions."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.LOD_FIXED,
                partition_by=[],
                params=CalcParams(
                    lod_dimensions=["CustomerID", "ProductID"],
                    lod_aggregation=AggregationType.SUM,
                ),
            )
        ]
        result = builder.build(base_query)
        
        lod_field = result["fields"][-1]
        assert lod_field["calculation"] == "{FIXED [CustomerID], [ProductID] : SUM([Sales])}"
    
    def test_lod_default_alias(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """LOD without alias should use default naming."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.LOD_FIXED,
                partition_by=[],
                params=CalcParams(
                    lod_dimensions=["CustomerID"],
                    lod_aggregation=AggregationType.SUM,
                ),
            )
        ]
        result = builder.build(base_query)
        
        lod_field = result["fields"][-1]
        assert lod_field["fieldCaption"] == "LOD_Sales"


# ═══════════════════════════════════════════════════════════════════════════
# LOD + Table Calc Combination Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestLODTableCalcCombination:
    """Test LOD + Table Calc combination ordering."""
    
    def test_lod_before_table_calc(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """LOD fields should come before table calc fields."""
        base_query.computations = [
            # Table calc first in input
            Computation(
                target="FirstPurchase",
                calc_type=CalcType.RANK,
                partition_by=[],
                params=CalcParams(direction=SortDirection.ASC),
            ),
            # LOD second in input
            Computation(
                target="OrderDate",
                calc_type=CalcType.LOD_FIXED,
                partition_by=[],
                params=CalcParams(
                    lod_dimensions=["CustomerID"],
                    lod_aggregation=AggregationType.MIN,
                ),
                alias="FirstPurchase",
            ),
        ]
        result = builder.build(base_query)
        
        # Find computation fields (after dimensions and measures)
        comp_fields = result["fields"][3:]  # 2 dims + 1 measure = 3
        
        # LOD should be first, table calc second
        assert "calculation" in comp_fields[0]  # LOD field has calculation
        assert "tableCalculation" in comp_fields[1]  # Table calc field
    
    def test_multiple_lod_and_table_calcs(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """Multiple LODs should all come before multiple table calcs."""
        base_query.computations = [
            # Mixed order in input
            Computation(
                target="Sales",
                calc_type=CalcType.RANK,
                partition_by=["Month"],
                params=CalcParams(),
            ),
            Computation(
                target="OrderDate",
                calc_type=CalcType.LOD_FIXED,
                partition_by=[],
                params=CalcParams(
                    lod_dimensions=["CustomerID"],
                    lod_aggregation=AggregationType.MIN,
                ),
                alias="FirstPurchase",
            ),
            Computation(
                target="Sales",
                calc_type=CalcType.PERCENT_OF_TOTAL,
                partition_by=[],
                params=CalcParams(),
            ),
            Computation(
                target="Sales",
                calc_type=CalcType.LOD_INCLUDE,
                partition_by=[],
                params=CalcParams(
                    lod_dimensions=["ProductID"],
                    lod_aggregation=AggregationType.SUM,
                ),
            ),
        ]
        result = builder.build(base_query)
        
        comp_fields = result["fields"][3:]  # After dims and measures
        
        # First 2 should be LOD (have calculation)
        assert "calculation" in comp_fields[0]
        assert "calculation" in comp_fields[1]
        # Last 2 should be table calcs
        assert "tableCalculation" in comp_fields[2]
        assert "tableCalculation" in comp_fields[3]


# ═══════════════════════════════════════════════════════════════════════════
# Validation Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestValidation:
    """Test validate method."""
    
    def test_valid_query(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """Valid query should pass validation."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.RANK,
                partition_by=["Month"],
                params=CalcParams(),
            )
        ]
        result = builder.validate(base_query)
        
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    def test_invalid_target_reference(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """Invalid target should fail validation."""
        base_query.computations = [
            Computation(
                target="NonExistentMeasure",
                calc_type=CalcType.RANK,
                partition_by=["Month"],
                params=CalcParams(),
            )
        ]
        result = builder.validate(base_query)
        
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert "NonExistentMeasure" in result.errors[0].message
    
    def test_invalid_partition_reference(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """Invalid partition_by should fail validation."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.RANK,
                partition_by=["NonExistentDimension"],
                params=CalcParams(),
            )
        ]
        result = builder.validate(base_query)
        
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert "NonExistentDimension" in result.errors[0].message
    
    def test_empty_query_fails(self, builder: TableauQueryBuilder):
        """Empty query (no dimensions or measures) should fail validation."""
        query = SemanticQuery(
            dimensions=[],
            measures=[],
        )
        result = builder.validate(query)
        
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert "at least one dimension or measure" in result.errors[0].message


# ═══════════════════════════════════════════════════════════════════════════
# Field Alias Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestFieldAlias:
    """Test field alias handling."""
    
    def test_table_calc_with_alias(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """Table calc with alias should include fieldAlias."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.RANK,
                partition_by=["Month"],
                params=CalcParams(),
                alias="SalesRank",
            )
        ]
        result = builder.build(base_query)
        
        table_calc_field = result["fields"][-1]
        assert table_calc_field["fieldAlias"] == "SalesRank"
    
    def test_table_calc_without_alias(self, builder: TableauQueryBuilder, base_query: SemanticQuery):
        """Table calc without alias should not include fieldAlias."""
        base_query.computations = [
            Computation(
                target="Sales",
                calc_type=CalcType.RANK,
                partition_by=["Month"],
                params=CalcParams(),
            )
        ]
        result = builder.build(base_query)
        
        table_calc_field = result["fields"][-1]
        assert "fieldAlias" not in table_calc_field


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
