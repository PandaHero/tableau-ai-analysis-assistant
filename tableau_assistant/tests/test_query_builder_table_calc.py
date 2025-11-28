"""
Unit tests for QueryBuilder table calculation support.

Tests the build_table_calc_field method and integration with build_query.
"""
import pytest
from datetime import datetime
from tableau_assistant.src.capabilities.query.builder.builder import QueryBuilder
from tableau_assistant.src.models.intent import TableCalcIntent
from tableau_assistant.src.models.metadata import Metadata, FieldMetadata
from tableau_assistant.src.models.vizql_types import (
    TableCalcField,
    RunningTotalTableCalcSpecification,
    MovingTableCalcSpecification,
    RankTableCalcSpecification,
    TableCalcComputedAggregation,
)


@pytest.fixture
def metadata():
    """Create test metadata."""
    return Metadata(
        datasource_name="Test Datasource",
        datasource_luid="test-luid-123",
        field_count=3,
        fields=[
            FieldMetadata(
                name="Sales",
                fieldCaption="Sales",
                dataType="REAL",
                role="measure",
                sample_values=["100.0", "200.0", "300.0"]
            ),
            FieldMetadata(
                name="Order Date",
                fieldCaption="Order Date",
                dataType="DATE",
                role="dimension",
                sample_values=["2024-01-01", "2024-01-02", "2024-01-03"]
            ),
            FieldMetadata(
                name="Category",
                fieldCaption="Category",
                dataType="STRING",
                role="dimension",
                sample_values=["Furniture", "Technology", "Office Supplies"]
            ),
        ]
    )


@pytest.fixture
def query_builder(metadata):
    """Create QueryBuilder instance."""
    return QueryBuilder(
        metadata=metadata,
        anchor_date=datetime(2024, 12, 31),
        week_start_day=0
    )


class TestBuildTableCalcFieldRunningTotal:
    """Test building RUNNING_TOTAL table calculations."""
    
    def test_running_total_minimal(self, query_builder):
        """Test running total with minimal config."""
        intent = TableCalcIntent(
            business_term="cumulative sales",
            technical_field="Sales",
            table_calc_type="RUNNING_TOTAL",
            table_calc_config={
                "dimensions": ["Order Date"]
            }
        )
        
        field = query_builder.build_table_calc_field(intent)
        
        assert isinstance(field, TableCalcField)
        assert field.fieldCaption == "cumulative sales"
        assert isinstance(field.tableCalculation, RunningTotalTableCalcSpecification)
        assert field.tableCalculation.tableCalcType == "RUNNING_TOTAL"
        assert len(field.tableCalculation.dimensions) == 1
        assert field.tableCalculation.dimensions[0].fieldCaption == "Order Date"
        assert field.tableCalculation.aggregation is None
    
    def test_running_total_with_aggregation(self, query_builder):
        """Test running total with aggregation."""
        intent = TableCalcIntent(
            business_term="cumulative sales",
            technical_field="Sales",
            table_calc_type="RUNNING_TOTAL",
            table_calc_config={
                "dimensions": ["Order Date"],
                "aggregation": "SUM"
            }
        )
        
        field = query_builder.build_table_calc_field(intent)
        
        assert field.tableCalculation.aggregation == TableCalcComputedAggregation.SUM
    
    def test_running_total_with_restart(self, query_builder):
        """Test running total with restart field."""
        intent = TableCalcIntent(
            business_term="cumulative sales by category",
            technical_field="Sales",
            table_calc_type="RUNNING_TOTAL",
            table_calc_config={
                "dimensions": ["Order Date"],
                "aggregation": "SUM",
                "restartEvery": "Category"
            }
        )
        
        field = query_builder.build_table_calc_field(intent)
        
        assert field.tableCalculation.restartEvery is not None
        assert field.tableCalculation.restartEvery.fieldCaption == "Category"


class TestBuildTableCalcFieldMovingCalculation:
    """Test building MOVING_CALCULATION table calculations."""
    
    def test_moving_calc_minimal(self, query_builder):
        """Test moving calculation with minimal config."""
        intent = TableCalcIntent(
            business_term="3-day moving average",
            technical_field="Sales",
            table_calc_type="MOVING_CALCULATION",
            table_calc_config={
                "dimensions": ["Order Date"],
                "previous": 2,
                "next": 0,
                "includeCurrent": True
            }
        )
        
        field = query_builder.build_table_calc_field(intent)
        
        assert isinstance(field.tableCalculation, MovingTableCalcSpecification)
        assert field.tableCalculation.previous == 2
        assert field.tableCalculation.next == 0
        assert field.tableCalculation.includeCurrent is True
    
    def test_moving_calc_with_aggregation(self, query_builder):
        """Test moving calculation with aggregation."""
        intent = TableCalcIntent(
            business_term="moving average",
            technical_field="Sales",
            table_calc_type="MOVING_CALCULATION",
            table_calc_config={
                "dimensions": ["Order Date"],
                "aggregation": "AVG",
                "previous": 3,
                "next": 0,
                "includeCurrent": True,
                "fillInNull": False
            }
        )
        
        field = query_builder.build_table_calc_field(intent)
        
        assert field.tableCalculation.aggregation == TableCalcComputedAggregation.AVG
        assert field.tableCalculation.fillInNull is False


class TestBuildTableCalcFieldRank:
    """Test building RANK table calculations."""
    
    def test_rank_minimal(self, query_builder):
        """Test rank with minimal config."""
        intent = TableCalcIntent(
            business_term="sales rank",
            technical_field="Sales",
            table_calc_type="RANK",
            table_calc_config={
                "dimensions": ["Category"],
                "rankType": "DENSE"
            }
        )
        
        field = query_builder.build_table_calc_field(intent)
        
        assert isinstance(field.tableCalculation, RankTableCalcSpecification)
        assert field.tableCalculation.rankType == "DENSE"
    
    def test_rank_with_direction(self, query_builder):
        """Test rank with direction."""
        intent = TableCalcIntent(
            business_term="sales rank",
            technical_field="Sales",
            table_calc_type="RANK",
            table_calc_config={
                "dimensions": ["Category"],
                "rankType": "COMPETITION",
                "direction": "DESC"
            }
        )
        
        field = query_builder.build_table_calc_field(intent)
        
        from tableau_assistant.src.models.vizql_types import SortDirection
        assert field.tableCalculation.direction == SortDirection.DESC


class TestBuildTableCalcFieldOtherTypes:
    """Test building other table calculation types."""
    
    def test_percentile(self, query_builder):
        """Test PERCENTILE type."""
        intent = TableCalcIntent(
            business_term="sales percentile",
            technical_field="Sales",
            table_calc_type="PERCENTILE",
            table_calc_config={
                "dimensions": ["Category"],
                "direction": "ASC"
            }
        )
        
        field = query_builder.build_table_calc_field(intent)
        
        assert field.tableCalculation.tableCalcType == "PERCENTILE"
    
    def test_percent_of_total(self, query_builder):
        """Test PERCENT_OF_TOTAL type."""
        intent = TableCalcIntent(
            business_term="percent of total sales",
            technical_field="Sales",
            table_calc_type="PERCENT_OF_TOTAL",
            table_calc_config={
                "dimensions": ["Category"]
            }
        )
        
        field = query_builder.build_table_calc_field(intent)
        
        assert field.tableCalculation.tableCalcType == "PERCENT_OF_TOTAL"
    
    def test_percent_from(self, query_builder):
        """Test PERCENT_FROM type."""
        intent = TableCalcIntent(
            business_term="percent from first",
            technical_field="Sales",
            table_calc_type="PERCENT_FROM",
            table_calc_config={
                "dimensions": ["Order Date"],
                "relativeTo": "FIRST"
            }
        )
        
        field = query_builder.build_table_calc_field(intent)
        
        assert field.tableCalculation.tableCalcType == "PERCENT_FROM"
        assert field.tableCalculation.relativeTo == "FIRST"
    
    def test_custom(self, query_builder):
        """Test CUSTOM type."""
        intent = TableCalcIntent(
            business_term="custom calculation",
            technical_field="Sales",
            table_calc_type="CUSTOM",
            table_calc_config={
                "dimensions": ["Category"]
            }
        )
        
        field = query_builder.build_table_calc_field(intent)
        
        assert field.tableCalculation.tableCalcType == "CUSTOM"
    
    def test_nested(self, query_builder):
        """Test NESTED type."""
        intent = TableCalcIntent(
            business_term="nested calculation",
            technical_field="Sales",
            table_calc_type="NESTED",
            table_calc_config={
                "dimensions": ["Category"],
                "fieldCaption": "Nested Calc"
            }
        )
        
        field = query_builder.build_table_calc_field(intent)
        
        assert field.tableCalculation.tableCalcType == "NESTED"
        assert field.tableCalculation.fieldCaption == "Nested Calc"


class TestBuildTableCalcFieldWithSorting:
    """Test table calculation fields with sorting."""
    
    def test_with_sort_direction(self, query_builder):
        """Test table calc field with sort direction."""
        intent = TableCalcIntent(
            business_term="cumulative sales",
            technical_field="Sales",
            table_calc_type="RUNNING_TOTAL",
            table_calc_config={
                "dimensions": ["Order Date"]
            },
            sort_direction="DESC"
        )
        
        field = query_builder.build_table_calc_field(intent)
        
        from tableau_assistant.src.models.vizql_types import SortDirection
        assert field.sortDirection == SortDirection.DESC
    
    def test_with_sort_priority(self, query_builder):
        """Test table calc field with sort priority."""
        intent = TableCalcIntent(
            business_term="cumulative sales",
            technical_field="Sales",
            table_calc_type="RUNNING_TOTAL",
            table_calc_config={
                "dimensions": ["Order Date"]
            },
            sort_direction="ASC",
            sort_priority=0
        )
        
        field = query_builder.build_table_calc_field(intent)
        
        assert field.sortPriority == 0


class TestBuildTableCalcFieldValidation:
    """Test validation and error handling."""
    
    def test_invalid_table_calc_type(self, query_builder):
        """Test that Pydantic validates table_calc_type at Intent creation."""
        # Note: Pydantic validates table_calc_type when creating the Intent,
        # so invalid types are caught before reaching build_table_calc_field.
        # This is the correct behavior - type safety at the data model layer.
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError, match="table_calc_type"):
            TableCalcIntent(
                business_term="test",
                technical_field="Sales",
                table_calc_type="INVALID_TYPE",
                table_calc_config={"dimensions": ["Date"]}
            )
    
    def test_missing_dimensions(self, query_builder):
        """Test error for missing dimensions."""
        intent = TableCalcIntent(
            business_term="test",
            technical_field="Sales",
            table_calc_type="RUNNING_TOTAL",
            table_calc_config={}
        )
        
        with pytest.raises(ValueError, match="dimensions字段是必需的"):
            query_builder.build_table_calc_field(intent)
    
    def test_nested_missing_field_caption(self, query_builder):
        """Test error for NESTED without fieldCaption."""
        intent = TableCalcIntent(
            business_term="test",
            technical_field="Sales",
            table_calc_type="NESTED",
            table_calc_config={
                "dimensions": ["Category"]
            }
        )
        
        with pytest.raises(ValueError, match="NESTED类型需要fieldCaption字段"):
            query_builder.build_table_calc_field(intent)


class TestAllTableCalcTypes:
    """Test all 10 table calculation types can be built."""
    
    def test_all_types(self, query_builder):
        """Test building all 10 table calculation types."""
        test_cases = [
            ("RUNNING_TOTAL", {"dimensions": ["Date"]}),
            ("MOVING_CALCULATION", {"dimensions": ["Date"], "previous": 1, "next": 0, "includeCurrent": True}),
            ("RANK", {"dimensions": ["Category"], "rankType": "DENSE"}),
            ("PERCENTILE", {"dimensions": ["Category"]}),
            ("PERCENT_OF_TOTAL", {"dimensions": ["Category"]}),
            ("PERCENT_FROM", {"dimensions": ["Date"]}),
            ("PERCENT_DIFFERENCE_FROM", {"dimensions": ["Date"]}),
            ("DIFFERENCE_FROM", {"dimensions": ["Date"]}),
            ("CUSTOM", {"dimensions": ["Category"]}),
            ("NESTED", {"dimensions": ["Category"], "fieldCaption": "Nested"}),
        ]
        
        for calc_type, config in test_cases:
            intent = TableCalcIntent(
                business_term=f"test {calc_type}",
                technical_field="Sales",
                table_calc_type=calc_type,
                table_calc_config=config
            )
            
            field = query_builder.build_table_calc_field(intent)
            
            assert field.tableCalculation.tableCalcType == calc_type
            assert field.fieldCaption == f"test {calc_type}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
