"""Unit tests for TableCalcIntent model."""

import pytest
from pydantic import ValidationError
from tableau_assistant.src.models.intent import TableCalcIntent


class TestTableCalcIntentCreation:
    """Test TableCalcIntent creation with different table calculation types."""
    
    def test_create_running_total_intent(self):
        """Test creating running total intent."""
        intent = TableCalcIntent(
            business_term="cumulative sales",
            technical_field="Sales",
            table_calc_type="RUNNING_TOTAL",
            table_calc_config={
                "aggregation": "SUM",
                "dimensions": ["Order Date"],
                "restartEvery": "Category"
            }
        )
        assert intent.business_term == "cumulative sales"
        assert intent.technical_field == "Sales"
        assert intent.table_calc_type == "RUNNING_TOTAL"
        assert intent.table_calc_config["aggregation"] == "SUM"
        assert "Order Date" in intent.table_calc_config["dimensions"]
    
    def test_create_moving_calculation_intent(self):
        """Test creating moving calculation intent."""
        intent = TableCalcIntent(
            business_term="3-month moving average",
            technical_field="Sales",
            table_calc_type="MOVING_CALCULATION",
            table_calc_config={
                "aggregation": "AVG",
                "dimensions": ["Order Date"],
                "previous": 2,
                "next": 0,
                "includeCurrent": True
            }
        )
        assert intent.table_calc_type == "MOVING_CALCULATION"
        assert intent.table_calc_config["previous"] == 2
        assert intent.table_calc_config["includeCurrent"] is True
    
    def test_create_rank_intent(self):
        """Test creating rank intent."""
        intent = TableCalcIntent(
            business_term="sales rank",
            technical_field="Sales",
            table_calc_type="RANK",
            table_calc_config={
                "dimensions": ["Category"],
                "rankType": "DENSE",
                "direction": "DESC"
            }
        )
        assert intent.table_calc_type == "RANK"
        assert intent.table_calc_config["rankType"] == "DENSE"
        assert intent.table_calc_config["direction"] == "DESC"
    
    def test_create_percentile_intent(self):
        """Test creating percentile intent."""
        intent = TableCalcIntent(
            business_term="sales percentile",
            technical_field="Sales",
            table_calc_type="PERCENTILE",
            table_calc_config={
                "dimensions": ["Category"],
                "direction": "ASC"
            }
        )
        assert intent.table_calc_type == "PERCENTILE"
    
    def test_create_percent_of_total_intent(self):
        """Test creating percent of total intent."""
        intent = TableCalcIntent(
            business_term="percent of total sales",
            technical_field="Sales",
            table_calc_type="PERCENT_OF_TOTAL",
            table_calc_config={
                "dimensions": ["Category"]
            }
        )
        assert intent.table_calc_type == "PERCENT_OF_TOTAL"
    
    def test_create_percent_from_intent(self):
        """Test creating percent from intent."""
        intent = TableCalcIntent(
            business_term="percent from first",
            technical_field="Sales",
            table_calc_type="PERCENT_FROM",
            table_calc_config={
                "dimensions": ["Order Date"],
                "relativeTo": "FIRST"
            }
        )
        assert intent.table_calc_type == "PERCENT_FROM"
        assert intent.table_calc_config["relativeTo"] == "FIRST"
    
    def test_create_percent_difference_from_intent(self):
        """Test creating percent difference from intent."""
        intent = TableCalcIntent(
            business_term="percent difference from previous",
            technical_field="Sales",
            table_calc_type="PERCENT_DIFFERENCE_FROM",
            table_calc_config={
                "dimensions": ["Order Date"],
                "relativeTo": "PREVIOUS"
            }
        )
        assert intent.table_calc_type == "PERCENT_DIFFERENCE_FROM"
    
    def test_create_difference_from_intent(self):
        """Test creating difference from intent."""
        intent = TableCalcIntent(
            business_term="difference from previous",
            technical_field="Sales",
            table_calc_type="DIFFERENCE_FROM",
            table_calc_config={
                "dimensions": ["Order Date"],
                "relativeTo": "PREVIOUS"
            }
        )
        assert intent.table_calc_type == "DIFFERENCE_FROM"
    
    def test_create_custom_intent(self):
        """Test creating custom calculation intent."""
        intent = TableCalcIntent(
            business_term="custom calculation",
            technical_field="Sales",
            table_calc_type="CUSTOM",
            table_calc_config={
                "dimensions": ["Category"]
            }
        )
        assert intent.table_calc_type == "CUSTOM"
    
    def test_create_nested_intent(self):
        """Test creating nested calculation intent."""
        intent = TableCalcIntent(
            business_term="nested calculation",
            technical_field="Sales",
            table_calc_type="NESTED",
            table_calc_config={
                "dimensions": ["Category"],
                "fieldCaption": "Nested Calc"
            }
        )
        assert intent.table_calc_type == "NESTED"


class TestTableCalcIntentWithSorting:
    """Test TableCalcIntent with sorting options."""
    
    def test_create_intent_with_sort_direction(self):
        """Test creating intent with sort direction."""
        intent = TableCalcIntent(
            business_term="cumulative sales",
            technical_field="Sales",
            table_calc_type="RUNNING_TOTAL",
            table_calc_config={
                "aggregation": "SUM",
                "dimensions": ["Order Date"]
            },
            sort_direction="DESC"
        )
        assert intent.sort_direction == "DESC"
    
    def test_create_intent_with_sort_priority(self):
        """Test creating intent with sort priority."""
        intent = TableCalcIntent(
            business_term="cumulative sales",
            technical_field="Sales",
            table_calc_type="RUNNING_TOTAL",
            table_calc_config={
                "aggregation": "SUM",
                "dimensions": ["Order Date"]
            },
            sort_direction="ASC",
            sort_priority=0
        )
        assert intent.sort_priority == 0
    
    def test_create_intent_without_sorting(self):
        """Test creating intent without sorting."""
        intent = TableCalcIntent(
            business_term="cumulative sales",
            technical_field="Sales",
            table_calc_type="RUNNING_TOTAL",
            table_calc_config={
                "aggregation": "SUM",
                "dimensions": ["Order Date"]
            }
        )
        assert intent.sort_direction is None
        assert intent.sort_priority is None


class TestTableCalcIntentSerialization:
    """Test TableCalcIntent serialization and deserialization."""
    
    def test_serialize_running_total_intent(self):
        """Test serializing running total intent."""
        intent = TableCalcIntent(
            business_term="cumulative sales",
            technical_field="Sales",
            table_calc_type="RUNNING_TOTAL",
            table_calc_config={
                "aggregation": "SUM",
                "dimensions": ["Order Date"]
            }
        )
        data = intent.model_dump(exclude_none=True)
        assert data["business_term"] == "cumulative sales"
        assert data["table_calc_type"] == "RUNNING_TOTAL"
        assert "table_calc_config" in data
    
    def test_deserialize_running_total_intent(self):
        """Test deserializing running total intent."""
        data = {
            "business_term": "cumulative sales",
            "technical_field": "Sales",
            "table_calc_type": "RUNNING_TOTAL",
            "table_calc_config": {
                "aggregation": "SUM",
                "dimensions": ["Order Date"]
            }
        }
        intent = TableCalcIntent(**data)
        assert intent.business_term == "cumulative sales"
        assert intent.table_calc_type == "RUNNING_TOTAL"
    
    def test_round_trip_serialization(self):
        """Test round trip serialization."""
        original = TableCalcIntent(
            business_term="3-month moving average",
            technical_field="Sales",
            table_calc_type="MOVING_CALCULATION",
            table_calc_config={
                "aggregation": "AVG",
                "dimensions": ["Order Date"],
                "previous": 2,
                "next": 0,
                "includeCurrent": True
            },
            sort_direction="ASC",
            sort_priority=0
        )
        
        # Serialize
        data = original.model_dump(exclude_none=True)
        
        # Deserialize
        restored = TableCalcIntent(**data)
        
        # Verify
        assert restored.business_term == original.business_term
        assert restored.technical_field == original.technical_field
        assert restored.table_calc_type == original.table_calc_type
        assert restored.table_calc_config == original.table_calc_config
        assert restored.sort_direction == original.sort_direction
        assert restored.sort_priority == original.sort_priority


class TestTableCalcIntentValidation:
    """Test TableCalcIntent validation."""
    
    def test_requires_business_term(self):
        """Test that business_term is required."""
        with pytest.raises(ValidationError):
            TableCalcIntent(
                technical_field="Sales",
                table_calc_type="RUNNING_TOTAL",
                table_calc_config={"aggregation": "SUM", "dimensions": ["Date"]}
            )
    
    def test_requires_technical_field(self):
        """Test that technical_field is required."""
        with pytest.raises(ValidationError):
            TableCalcIntent(
                business_term="cumulative sales",
                table_calc_type="RUNNING_TOTAL",
                table_calc_config={"aggregation": "SUM", "dimensions": ["Date"]}
            )
    
    def test_requires_table_calc_type(self):
        """Test that table_calc_type is required."""
        with pytest.raises(ValidationError):
            TableCalcIntent(
                business_term="cumulative sales",
                technical_field="Sales",
                table_calc_config={"aggregation": "SUM", "dimensions": ["Date"]}
            )
    
    def test_requires_table_calc_config(self):
        """Test that table_calc_config is required."""
        with pytest.raises(ValidationError):
            TableCalcIntent(
                business_term="cumulative sales",
                technical_field="Sales",
                table_calc_type="RUNNING_TOTAL"
            )
    
    def test_invalid_table_calc_type(self):
        """Test validation fails for invalid table_calc_type."""
        with pytest.raises(ValidationError):
            TableCalcIntent(
                business_term="cumulative sales",
                technical_field="Sales",
                table_calc_type="INVALID_TYPE",
                table_calc_config={"aggregation": "SUM", "dimensions": ["Date"]}
            )
    
    def test_invalid_sort_direction(self):
        """Test validation fails for invalid sort_direction."""
        with pytest.raises(ValidationError):
            TableCalcIntent(
                business_term="cumulative sales",
                technical_field="Sales",
                table_calc_type="RUNNING_TOTAL",
                table_calc_config={"aggregation": "SUM", "dimensions": ["Date"]},
                sort_direction="INVALID"
            )
    
    def test_negative_sort_priority(self):
        """Test validation fails for negative sort_priority."""
        with pytest.raises(ValidationError):
            TableCalcIntent(
                business_term="cumulative sales",
                technical_field="Sales",
                table_calc_type="RUNNING_TOTAL",
                table_calc_config={"aggregation": "SUM", "dimensions": ["Date"]},
                sort_priority=-1
            )
    
    def test_forbids_extra_fields(self):
        """Test that extra fields are forbidden."""
        with pytest.raises(ValidationError):
            TableCalcIntent(
                business_term="cumulative sales",
                technical_field="Sales",
                table_calc_type="RUNNING_TOTAL",
                table_calc_config={"aggregation": "SUM", "dimensions": ["Date"]},
                extra_field="not allowed"
            )


class TestAllTableCalcTypes:
    """Test all 10 table calculation types can be created."""
    
    def test_all_table_calc_types(self):
        """Test creating all 10 table calculation types."""
        types = [
            "RUNNING_TOTAL",
            "MOVING_CALCULATION",
            "RANK",
            "PERCENTILE",
            "PERCENT_OF_TOTAL",
            "PERCENT_FROM",
            "PERCENT_DIFFERENCE_FROM",
            "DIFFERENCE_FROM",
            "CUSTOM",
            "NESTED"
        ]
        
        for calc_type in types:
            intent = TableCalcIntent(
                business_term=f"test {calc_type}",
                technical_field="Sales",
                table_calc_type=calc_type,
                table_calc_config={"dimensions": ["Category"]}
            )
            assert intent.table_calc_type == calc_type


class TestTableCalcConfigVariations:
    """Test various table_calc_config structures."""
    
    def test_running_total_with_restart(self):
        """Test running total config with restartEvery."""
        intent = TableCalcIntent(
            business_term="cumulative sales",
            technical_field="Sales",
            table_calc_type="RUNNING_TOTAL",
            table_calc_config={
                "aggregation": "SUM",
                "dimensions": ["Order Date"],
                "restartEvery": "Category"
            }
        )
        assert "restartEvery" in intent.table_calc_config
    
    def test_moving_calc_with_all_options(self):
        """Test moving calculation config with all options."""
        intent = TableCalcIntent(
            business_term="moving average",
            technical_field="Sales",
            table_calc_type="MOVING_CALCULATION",
            table_calc_config={
                "aggregation": "AVG",
                "dimensions": ["Order Date"],
                "previous": 3,
                "next": 1,
                "includeCurrent": True,
                "fillInNull": False
            }
        )
        assert intent.table_calc_config["previous"] == 3
        assert intent.table_calc_config["next"] == 1
        assert intent.table_calc_config["fillInNull"] is False
    
    def test_rank_with_all_rank_types(self):
        """Test rank config with different rank types."""
        rank_types = ["COMPETITION", "DENSE", "UNIQUE"]
        
        for rank_type in rank_types:
            intent = TableCalcIntent(
                business_term="sales rank",
                technical_field="Sales",
                table_calc_type="RANK",
                table_calc_config={
                    "dimensions": ["Category"],
                    "rankType": rank_type,
                    "direction": "DESC"
                }
            )
            assert intent.table_calc_config["rankType"] == rank_type
    
    def test_percent_from_with_relative_to_options(self):
        """Test percent from config with different relativeTo options."""
        relative_to_options = ["PREVIOUS", "NEXT", "FIRST", "LAST"]
        
        for relative_to in relative_to_options:
            intent = TableCalcIntent(
                business_term="percent from",
                technical_field="Sales",
                table_calc_type="PERCENT_FROM",
                table_calc_config={
                    "dimensions": ["Order Date"],
                    "relativeTo": relative_to
                }
            )
            assert intent.table_calc_config["relativeTo"] == relative_to
    
    def test_empty_config(self):
        """Test with minimal config."""
        intent = TableCalcIntent(
            business_term="simple calc",
            technical_field="Sales",
            table_calc_type="CUSTOM",
            table_calc_config={}
        )
        assert intent.table_calc_config == {}
    
    def test_complex_nested_config(self):
        """Test with complex nested config."""
        intent = TableCalcIntent(
            business_term="complex nested",
            technical_field="Sales",
            table_calc_type="NESTED",
            table_calc_config={
                "dimensions": ["Category", "Region"],
                "fieldCaption": "Complex Calculation",
                "levelAddress": "Category",
                "customSort": {
                    "sortOrder": "ASC"
                }
            }
        )
        assert len(intent.table_calc_config["dimensions"]) == 2
        assert "customSort" in intent.table_calc_config
