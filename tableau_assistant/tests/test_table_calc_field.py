"""Unit tests for TableCalcField and related table calculation models."""

import pytest
from pydantic import ValidationError
from tableau_assistant.src.models.vizql_types import (
    TableCalcField,
    TableCalcSpecification,
    RunningTotalTableCalcSpecification,
    MovingTableCalcSpecification,
    RankTableCalcSpecification,
    PercentileTableCalcSpecification,
    PercentOfTotalTableCalcSpecification,
    PercentFromTableCalcSpecification,
    PercentDifferenceFromTableCalcSpecification,
    DifferenceFromTableCalcSpecification,
    CustomTableCalcSpecification,
    NestedTableCalcSpecification,
    TableCalcFieldReference,
    TableCalcCustomSort,
    TableCalcComputedAggregation,
)


class TestTableCalcFieldReference:
    """Test TableCalcFieldReference model."""
    
    def test_create_field_reference_minimal(self):
        """Test creating field reference with minimal fields."""
        ref = TableCalcFieldReference(fieldCaption="Sales")
        assert ref.fieldCaption == "Sales"
        assert ref.function is None
    
    def test_create_field_reference_with_function(self):
        """Test creating field reference with aggregation function."""
        ref = TableCalcFieldReference(
            fieldCaption="Sales",
            function="SUM"
        )
        assert ref.fieldCaption == "Sales"
        assert ref.function == "SUM"
    
    def test_field_reference_serialization(self):
        """Test field reference serialization."""
        ref = TableCalcFieldReference(
            fieldCaption="Sales",
            function="AVG"
        )
        data = ref.model_dump(exclude_none=True)
        assert data == {"fieldCaption": "Sales", "function": "AVG"}
    
    def test_field_reference_deserialization(self):
        """Test field reference deserialization."""
        data = {"fieldCaption": "Profit", "function": "MAX"}
        ref = TableCalcFieldReference(**data)
        assert ref.fieldCaption == "Profit"
        assert ref.function == "MAX"


class TestRunningTotalTableCalcSpecification:
    """Test RunningTotalTableCalcSpecification model."""
    
    def test_create_running_total_minimal(self):
        """Test creating running total with minimal fields."""
        spec = RunningTotalTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Date")]
        )
        assert spec.tableCalcType == "RUNNING_TOTAL"
        assert len(spec.dimensions) == 1
        assert spec.aggregation is None
    
    def test_create_running_total_with_aggregation(self):
        """Test creating running total with aggregation."""
        spec = RunningTotalTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Date")],
            aggregation=TableCalcComputedAggregation.SUM
        )
        assert spec.aggregation == TableCalcComputedAggregation.SUM
    
    def test_create_running_total_with_restart(self):
        """Test creating running total with restart field."""
        spec = RunningTotalTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Date")],
            restartEvery=TableCalcFieldReference(fieldCaption="Category")
        )
        assert spec.restartEvery.fieldCaption == "Category"
    
    def test_running_total_serialization(self):
        """Test running total serialization."""
        spec = RunningTotalTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Date")],
            aggregation=TableCalcComputedAggregation.SUM
        )
        data = spec.model_dump(exclude_none=True)
        assert data["tableCalcType"] == "RUNNING_TOTAL"
        assert data["aggregation"] == "SUM"


class TestMovingTableCalcSpecification:
    """Test MovingTableCalcSpecification model."""
    
    def test_create_moving_calc_minimal(self):
        """Test creating moving calculation with minimal fields."""
        spec = MovingTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Date")],
            previous=2,
            next=0
        )
        assert spec.tableCalcType == "MOVING_CALCULATION"
        assert spec.previous == 2
        assert spec.next == 0
    
    def test_create_moving_calc_with_aggregation(self):
        """Test creating moving calculation with aggregation."""
        spec = MovingTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Date")],
            aggregation=TableCalcComputedAggregation.AVG,
            previous=3,
            next=0,
            includeCurrent=True
        )
        assert spec.aggregation == TableCalcComputedAggregation.AVG
        assert spec.includeCurrent is True
    
    def test_moving_calc_validation_negative_previous(self):
        """Test validation fails for negative previous value."""
        with pytest.raises(ValidationError):
            MovingTableCalcSpecification(
                dimensions=[TableCalcFieldReference(fieldCaption="Date")],
                previous=-1,
                next=0
            )
    
    def test_moving_calc_validation_negative_next(self):
        """Test validation fails for negative next value."""
        with pytest.raises(ValidationError):
            MovingTableCalcSpecification(
                dimensions=[TableCalcFieldReference(fieldCaption="Date")],
                previous=0,
                next=-1
            )


class TestRankTableCalcSpecification:
    """Test RankTableCalcSpecification model."""
    
    def test_create_rank_competition(self):
        """Test creating rank with COMPETITION type."""
        spec = RankTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Sales", function="SUM")],
            rankType="COMPETITION"
        )
        assert spec.tableCalcType == "RANK"
        assert spec.rankType == "COMPETITION"
    
    def test_create_rank_dense(self):
        """Test creating rank with DENSE type."""
        spec = RankTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Sales", function="SUM")],
            rankType="DENSE"
        )
        assert spec.rankType == "DENSE"
    
    def test_create_rank_unique(self):
        """Test creating rank with UNIQUE type."""
        spec = RankTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Sales", function="SUM")],
            rankType="UNIQUE"
        )
        assert spec.rankType == "UNIQUE"
    
    def test_create_rank_with_direction(self):
        """Test creating rank with direction."""
        spec = RankTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Sales", function="SUM")],
            rankType="COMPETITION",
            direction="DESC"
        )
        assert spec.direction == "DESC"


class TestOtherTableCalcSpecifications:
    """Test other table calculation specification models."""
    
    def test_create_percentile(self):
        """Test creating percentile calculation."""
        spec = PercentileTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Sales")],
            direction="DESC"
        )
        assert spec.tableCalcType == "PERCENTILE"
        assert spec.direction == "DESC"
    
    def test_create_percent_of_total(self):
        """Test creating percent of total calculation."""
        spec = PercentOfTotalTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Category")]
        )
        assert spec.tableCalcType == "PERCENT_OF_TOTAL"
    
    def test_create_percent_from(self):
        """Test creating percent from calculation."""
        spec = PercentFromTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Date")],
            relativeTo="FIRST"
        )
        assert spec.tableCalcType == "PERCENT_FROM"
        assert spec.relativeTo == "FIRST"
    
    def test_create_percent_difference_from(self):
        """Test creating percent difference from calculation."""
        spec = PercentDifferenceFromTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Date")],
            relativeTo="FIRST"
        )
        assert spec.tableCalcType == "PERCENT_DIFFERENCE_FROM"
        assert spec.relativeTo == "FIRST"
    
    def test_create_difference_from(self):
        """Test creating difference from calculation."""
        spec = DifferenceFromTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Date")],
            relativeTo="PREVIOUS"
        )
        assert spec.tableCalcType == "DIFFERENCE_FROM"
        assert spec.relativeTo == "PREVIOUS"
    
    def test_create_custom(self):
        """Test creating custom calculation."""
        spec = CustomTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Date")],
            levelAddress=TableCalcFieldReference(fieldCaption="Category")
        )
        assert spec.tableCalcType == "CUSTOM"
        assert spec.levelAddress.fieldCaption == "Category"
    
    def test_create_nested(self):
        """Test creating nested calculation."""
        spec = NestedTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Category")],
            fieldCaption="Nested Calculation"
        )
        assert spec.tableCalcType == "NESTED"
        assert spec.fieldCaption == "Nested Calculation"


class TestTableCalcField:
    """Test TableCalcField model."""
    
    def test_create_table_calc_field_running_total(self):
        """Test creating table calc field with running total."""
        table_calc = RunningTotalTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Date")],
            aggregation=TableCalcComputedAggregation.SUM
        )
        field = TableCalcField(
            fieldCaption="Running Total of Sales",
            tableCalculation=table_calc
        )
        assert field.fieldCaption == "Running Total of Sales"
        assert field.tableCalculation.tableCalcType == "RUNNING_TOTAL"
    
    def test_create_table_calc_field_moving_avg(self):
        """Test creating table calc field with moving average."""
        table_calc = MovingTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Date")],
            aggregation=TableCalcComputedAggregation.AVG,
            previous=2,
            next=0,
            includeCurrent=True
        )
        field = TableCalcField(
            fieldCaption="3-Day Moving Average",
            tableCalculation=table_calc
        )
        assert field.tableCalculation.aggregation == TableCalcComputedAggregation.AVG
        assert field.tableCalculation.previous == 2
    
    def test_create_table_calc_field_rank(self):
        """Test creating table calc field with rank."""
        table_calc = RankTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Sales", function="SUM")],
            rankType="DENSE",
            direction="DESC"
        )
        field = TableCalcField(
            fieldCaption="Sales Rank",
            tableCalculation=table_calc
        )
        assert field.tableCalculation.rankType == "DENSE"
    
    def test_create_table_calc_field_with_nested(self):
        """Test creating table calc field with nested calculations."""
        primary = RunningTotalTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Date")]
        )
        secondary = PercentOfTotalTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Category")]
        )
        field = TableCalcField(
            fieldCaption="Complex Calculation",
            tableCalculation=primary,
            nestedTableCalculations=[secondary]
        )
        assert len(field.nestedTableCalculations) == 1
        assert field.nestedTableCalculations[0].tableCalcType == "PERCENT_OF_TOTAL"
    
    def test_table_calc_field_serialization(self):
        """Test table calc field serialization."""
        table_calc = RunningTotalTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Date")],
            aggregation=TableCalcComputedAggregation.SUM
        )
        field = TableCalcField(
            fieldCaption="Running Total",
            tableCalculation=table_calc
        )
        data = field.model_dump(exclude_none=True)
        assert data["fieldCaption"] == "Running Total"
        assert data["tableCalculation"]["tableCalcType"] == "RUNNING_TOTAL"
        assert data["tableCalculation"]["aggregation"] == "SUM"
    
    def test_table_calc_field_deserialization(self):
        """Test table calc field deserialization."""
        data = {
            "fieldCaption": "Running Total",
            "tableCalculation": {
                "tableCalcType": "RUNNING_TOTAL",
                "dimensions": [{"fieldCaption": "Date"}],
                "aggregation": "SUM"
            }
        }
        field = TableCalcField(**data)
        assert field.fieldCaption == "Running Total"
        assert field.tableCalculation.tableCalcType == "RUNNING_TOTAL"
        assert field.tableCalculation.aggregation == TableCalcComputedAggregation.SUM
    
    def test_table_calc_field_round_trip(self):
        """Test table calc field serialization round trip."""
        table_calc = MovingTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Date")],
            aggregation=TableCalcComputedAggregation.AVG,
            previous=3,
            next=0,
            includeCurrent=True,
            fillInNull=False
        )
        field = TableCalcField(
            fieldCaption="Moving Average",
            tableCalculation=table_calc
        )
        
        # Serialize
        data = field.model_dump(exclude_none=True)
        
        # Deserialize
        field2 = TableCalcField(**data)
        
        # Verify
        assert field2.fieldCaption == field.fieldCaption
        assert field2.tableCalculation.tableCalcType == field.tableCalculation.tableCalcType
        assert field2.tableCalculation.aggregation == field.tableCalculation.aggregation
        assert field2.tableCalculation.previous == field.tableCalculation.previous
        assert field2.tableCalculation.includeCurrent == field.tableCalculation.includeCurrent


class TestTableCalcFieldValidation:
    """Test TableCalcField validation."""
    
    def test_table_calc_field_requires_table_calculation(self):
        """Test that tableCalculation field is required."""
        with pytest.raises(ValidationError):
            TableCalcField(fieldCaption="Test")
    
    def test_table_calc_field_forbids_extra_fields(self):
        """Test that extra fields are forbidden."""
        table_calc = RunningTotalTableCalcSpecification(
            dimensions=[TableCalcFieldReference(fieldCaption="Date")]
        )
        with pytest.raises(ValidationError):
            TableCalcField(
                fieldCaption="Test",
                tableCalculation=table_calc,
                extraField="not allowed"
            )


class TestAllTableCalcTypes:
    """Test all 10 table calculation types can be created."""
    
    def test_all_table_calc_types(self):
        """Test creating all 10 table calculation types."""
        types = [
            ("RUNNING_TOTAL", RunningTotalTableCalcSpecification(
                dimensions=[TableCalcFieldReference(fieldCaption="Date")]
            )),
            ("MOVING_CALCULATION", MovingTableCalcSpecification(
                dimensions=[TableCalcFieldReference(fieldCaption="Date")],
                previous=1,
                next=0
            )),
            ("RANK", RankTableCalcSpecification(
                dimensions=[TableCalcFieldReference(fieldCaption="Sales", function="SUM")],
                rankType="COMPETITION"
            )),
            ("PERCENTILE", PercentileTableCalcSpecification(
                dimensions=[TableCalcFieldReference(fieldCaption="Sales")],
                direction="ASC"
            )),
            ("PERCENT_OF_TOTAL", PercentOfTotalTableCalcSpecification(
                dimensions=[TableCalcFieldReference(fieldCaption="Category")]
            )),
            ("PERCENT_FROM", PercentFromTableCalcSpecification(
                dimensions=[TableCalcFieldReference(fieldCaption="Date")],
                relativeTo="FIRST"
            )),
            ("PERCENT_DIFFERENCE_FROM", PercentDifferenceFromTableCalcSpecification(
                dimensions=[TableCalcFieldReference(fieldCaption="Date")],
                relativeTo="PREVIOUS"
            )),
            ("DIFFERENCE_FROM", DifferenceFromTableCalcSpecification(
                dimensions=[TableCalcFieldReference(fieldCaption="Date")],
                relativeTo="PREVIOUS"
            )),
            ("CUSTOM", CustomTableCalcSpecification(
                dimensions=[TableCalcFieldReference(fieldCaption="Date")]
            )),
            ("NESTED", NestedTableCalcSpecification(
                dimensions=[TableCalcFieldReference(fieldCaption="Category")],
                fieldCaption="Nested Calc"
            )),
        ]
        
        for expected_type, spec in types:
            assert spec.tableCalcType == expected_type
            field = TableCalcField(
                fieldCaption=f"Test {expected_type}",
                tableCalculation=spec
            )
            assert field.tableCalculation.tableCalcType == expected_type
