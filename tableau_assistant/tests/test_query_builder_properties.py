"""
Property-based tests for QueryBuilder table calculation conversion.

**Feature: vizql-api-migration, Property 3: TableCalcIntent to TableCalcField conversion correctness**

This test validates that for any TableCalcIntent, QueryBuilder generates a TableCalcField
with the correct tableCalculation specification.
"""

import pytest
from hypothesis import given, strategies as st, settings
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


# ============= Hypothesis Strategies =============

@st.composite
def table_calc_config_strategy(draw, calc_type):
    """Generate random table_calc_config based on calc_type."""
    # Base config with dimensions
    # Generate non-empty strings without leading/trailing whitespace
    config = {
        "dimensions": draw(st.lists(
            st.text(min_size=1, max_size=30, alphabet=st.characters(
                whitelist_categories=('Lu', 'Ll', 'Nd'),
                whitelist_characters='_-'
            )).filter(lambda x: len(x.strip()) > 0).map(lambda x: x.strip()),
            min_size=1,
            max_size=3
        ))
    }
    
    # Add type-specific fields
    if calc_type == "RUNNING_TOTAL":
        if draw(st.booleans()):
            config["aggregation"] = draw(st.sampled_from(["SUM", "AVG", "MIN", "MAX"]))
        if draw(st.booleans()):
            config["restartEvery"] = draw(st.text(min_size=1, max_size=30))
    
    elif calc_type == "MOVING_CALCULATION":
        if draw(st.booleans()):
            config["aggregation"] = draw(st.sampled_from(["SUM", "AVG", "MIN", "MAX"]))
        config["previous"] = draw(st.integers(min_value=0, max_value=10))
        config["next"] = draw(st.integers(min_value=0, max_value=10))
        config["includeCurrent"] = draw(st.booleans())
        if draw(st.booleans()):
            config["fillInNull"] = draw(st.booleans())
    
    elif calc_type == "RANK":
        config["rankType"] = draw(st.sampled_from(["COMPETITION", "DENSE", "UNIQUE"]))
        if draw(st.booleans()):
            config["direction"] = draw(st.sampled_from(["ASC", "DESC"]))
    
    elif calc_type == "PERCENTILE":
        if draw(st.booleans()):
            config["direction"] = draw(st.sampled_from(["ASC", "DESC"]))
    
    elif calc_type in ["PERCENT_FROM", "PERCENT_DIFFERENCE_FROM", "DIFFERENCE_FROM"]:
        if draw(st.booleans()):
            config["relativeTo"] = draw(st.sampled_from(["PREVIOUS", "NEXT", "FIRST", "LAST"]))
    
    elif calc_type == "NESTED":
        config["fieldCaption"] = draw(st.text(min_size=1, max_size=50))
    
    return config


@st.composite
def table_calc_intent_strategy(draw):
    """Generate random TableCalcIntent."""
    # Generate non-empty strings without leading/trailing whitespace
    business_term = draw(st.text(min_size=1, max_size=100, alphabet=st.characters(
        whitelist_categories=('Lu', 'Ll', 'Nd'),
        whitelist_characters='_-'
    )).filter(lambda x: len(x.strip()) > 0).map(lambda x: x.strip()))
    
    technical_field = "Sales"  # Use fixed field name that exists in metadata
    
    table_calc_type = draw(st.sampled_from([
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
    ]))
    
    table_calc_config = draw(table_calc_config_strategy(table_calc_type))
    
    # Optional sorting fields
    sort_direction = draw(st.one_of(
        st.none(),
        st.sampled_from(["ASC", "DESC"])
    ))
    
    sort_priority = draw(st.one_of(
        st.none(),
        st.integers(min_value=0, max_value=10)
    ))
    
    return TableCalcIntent(
        business_term=business_term,
        technical_field=technical_field,
        table_calc_type=table_calc_type,
        table_calc_config=table_calc_config,
        sort_direction=sort_direction,
        sort_priority=sort_priority
    )


@pytest.fixture
def query_builder():
    """Create QueryBuilder instance with test metadata."""
    metadata = Metadata(
        datasource_name="Test Datasource",
        datasource_luid="test-luid-123",
        field_count=3,
        fields=[
            FieldMetadata(
                name="Sales",
                fieldCaption="Sales",
                dataType="REAL",
                role="measure"
            ),
            FieldMetadata(
                name="Order Date",
                fieldCaption="Order Date",
                dataType="DATE",
                role="dimension"
            ),
            FieldMetadata(
                name="Category",
                fieldCaption="Category",
                dataType="STRING",
                role="dimension"
            ),
        ]
    )
    
    return QueryBuilder(
        metadata=metadata,
        anchor_date=datetime(2024, 12, 31),
        week_start_day=0
    )


# ============= Property-Based Tests =============

@given(table_calc_intent_strategy())
@settings(max_examples=100, deadline=None)
def test_table_calc_intent_to_field_conversion_property(intent):
    """
    **Property 3: TableCalcIntent to TableCalcField conversion correctness**
    
    For any TableCalcIntent, QueryBuilder should generate a TableCalcField
    with the correct tableCalculation specification.
    
    **Validates: Requirements 3.4, 3.5, 15.9**
    """
    # Create QueryBuilder
    metadata = Metadata(
        datasource_name="Test Datasource",
        datasource_luid="test-luid-123",
        field_count=3,
        fields=[
            FieldMetadata(
                name="Sales",
                fieldCaption="Sales",
                dataType="REAL",
                role="measure"
            ),
            FieldMetadata(
                name="Order Date",
                fieldCaption="Order Date",
                dataType="DATE",
                role="dimension"
            ),
            FieldMetadata(
                name="Category",
                fieldCaption="Category",
                dataType="STRING",
                role="dimension"
            ),
        ]
    )
    query_builder = QueryBuilder(
        metadata=metadata,
        anchor_date=datetime(2024, 12, 31),
        week_start_day=0
    )
    
    # Build TableCalcField from Intent
    field = query_builder.build_table_calc_field(intent)
    
    # Verify field type
    assert isinstance(field, TableCalcField)
    
    # Verify field caption
    assert field.fieldCaption == intent.business_term
    
    # Verify table calculation type
    assert field.tableCalculation.tableCalcType == intent.table_calc_type
    
    # Verify dimensions
    assert len(field.tableCalculation.dimensions) == len(intent.table_calc_config["dimensions"])
    for i, dim in enumerate(field.tableCalculation.dimensions):
        assert dim.fieldCaption == intent.table_calc_config["dimensions"][i]
    
    # Verify type-specific fields
    if intent.table_calc_type == "RUNNING_TOTAL":
        assert isinstance(field.tableCalculation, RunningTotalTableCalcSpecification)
        if "aggregation" in intent.table_calc_config:
            assert field.tableCalculation.aggregation == TableCalcComputedAggregation[intent.table_calc_config["aggregation"]]
        if "restartEvery" in intent.table_calc_config:
            assert field.tableCalculation.restartEvery is not None
            assert field.tableCalculation.restartEvery.fieldCaption == intent.table_calc_config["restartEvery"]
    
    elif intent.table_calc_type == "MOVING_CALCULATION":
        assert isinstance(field.tableCalculation, MovingTableCalcSpecification)
        assert field.tableCalculation.previous == intent.table_calc_config.get("previous", 0)
        assert field.tableCalculation.next == intent.table_calc_config.get("next", 0)
        assert field.tableCalculation.includeCurrent == intent.table_calc_config.get("includeCurrent", True)
        if "aggregation" in intent.table_calc_config:
            assert field.tableCalculation.aggregation == TableCalcComputedAggregation[intent.table_calc_config["aggregation"]]
    
    elif intent.table_calc_type == "RANK":
        assert isinstance(field.tableCalculation, RankTableCalcSpecification)
        assert field.tableCalculation.rankType == intent.table_calc_config.get("rankType", "COMPETITION")
    
    # Verify sorting
    if intent.sort_direction:
        from tableau_assistant.src.models.vizql_types import SortDirection
        assert field.sortDirection == SortDirection[intent.sort_direction]
    else:
        assert field.sortDirection is None
    
    assert field.sortPriority == intent.sort_priority


@given(
    st.sampled_from([
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
    ])
)
@settings(max_examples=100, deadline=None)
def test_all_table_calc_types_conversion_property(calc_type):
    """
    **Property 4: Table calculation type completeness**
    
    For any of the 10 table calculation types, the system should be able to
    correctly create the corresponding TableCalcSpecification.
    
    **Validates: Requirements 15.3**
    """
    # Create QueryBuilder
    metadata = Metadata(
        datasource_name="Test Datasource",
        datasource_luid="test-luid-123",
        field_count=3,
        fields=[
            FieldMetadata(
                name="Sales",
                fieldCaption="Sales",
                dataType="REAL",
                role="measure"
            ),
            FieldMetadata(
                name="Order Date",
                fieldCaption="Order Date",
                dataType="DATE",
                role="dimension"
            ),
            FieldMetadata(
                name="Category",
                fieldCaption="Category",
                dataType="STRING",
                role="dimension"
            ),
        ]
    )
    query_builder = QueryBuilder(
        metadata=metadata,
        anchor_date=datetime(2024, 12, 31),
        week_start_day=0
    )
    
    # Create minimal valid config for each type
    config = {"dimensions": ["Category"]}
    
    if calc_type == "MOVING_CALCULATION":
        config["previous"] = 1
        config["next"] = 0
        config["includeCurrent"] = True
    elif calc_type == "RANK":
        config["rankType"] = "DENSE"
    elif calc_type == "NESTED":
        config["fieldCaption"] = "Nested Calc"
    
    intent = TableCalcIntent(
        business_term=f"test {calc_type}",
        technical_field="Sales",
        table_calc_type=calc_type,
        table_calc_config=config
    )
    
    # Build field
    field = query_builder.build_table_calc_field(intent)
    
    # Verify
    assert isinstance(field, TableCalcField)
    assert field.tableCalculation.tableCalcType == calc_type
    assert field.fieldCaption == f"test {calc_type}"
    
    # Verify dimensions are correctly converted
    assert len(field.tableCalculation.dimensions) == 1
    assert field.tableCalculation.dimensions[0].fieldCaption == "Category"


if __name__ == "__main__":
    # Run property tests
    pytest.main([__file__, "-v", "--hypothesis-show-statistics"])
