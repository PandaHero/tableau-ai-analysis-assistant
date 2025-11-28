"""
Property-based tests for TableCalcIntent serialization round-trip consistency.

**Feature: vizql-api-migration, Property 1: TableCalcIntent serialization round-trip consistency**

This test validates that for any TableCalcIntent instance, serializing and then 
deserializing produces an equivalent object.
"""

import pytest
from hypothesis import given, strategies as st, settings
from tableau_assistant.src.models.intent import TableCalcIntent


# ============= Hypothesis Strategies =============

@st.composite
def table_calc_config_strategy(draw, calc_type):
    """Generate random table_calc_config based on calc_type."""
    # Base config with dimensions
    config = {
        "dimensions": draw(st.lists(
            st.text(min_size=1, max_size=30, alphabet=st.characters(
                whitelist_categories=('Lu', 'Ll', 'Nd'),
                whitelist_characters=' _-'
            )),
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
    
    # Add optional common fields
    if draw(st.booleans()):
        config["levelAddress"] = draw(st.text(min_size=1, max_size=30))
    
    return config


@st.composite
def table_calc_intent_strategy(draw):
    """Generate random TableCalcIntent."""
    business_term = draw(st.text(min_size=1, max_size=100, alphabet=st.characters(
        whitelist_categories=('Lu', 'Ll', 'Nd'),
        whitelist_characters=' _-'
    )))
    
    technical_field = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('Lu', 'Ll', 'Nd'),
        whitelist_characters=' _-'
    )))
    
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


# ============= Property-Based Tests =============

@given(table_calc_intent_strategy())
@settings(max_examples=100, deadline=None)
def test_table_calc_intent_round_trip_property(intent):
    """
    **Property 1: TableCalcIntent serialization round-trip consistency**
    
    For any TableCalcIntent instance, serializing and then deserializing 
    should produce an equivalent object.
    
    **Validates: Requirements 7.2**
    """
    # Serialize
    serialized = intent.model_dump(exclude_none=True)
    
    # Deserialize
    deserialized = TableCalcIntent(**serialized)
    
    # Verify equivalence
    assert deserialized.business_term == intent.business_term
    assert deserialized.technical_field == intent.technical_field
    assert deserialized.table_calc_type == intent.table_calc_type
    assert deserialized.table_calc_config == intent.table_calc_config
    assert deserialized.sort_direction == intent.sort_direction
    assert deserialized.sort_priority == intent.sort_priority
    
    # Verify re-serialization produces same result
    reserialized = deserialized.model_dump(exclude_none=True)
    
    # Deep comparison using JSON
    import json
    serialized_json = json.dumps(serialized, sort_keys=True, default=str)
    reserialized_json = json.dumps(reserialized, sort_keys=True, default=str)
    assert serialized_json == reserialized_json


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
def test_all_table_calc_types_round_trip(calc_type):
    """Test round-trip for all table calculation types."""
    config = {"dimensions": ["Category"]}
    
    # Add type-specific required fields
    if calc_type == "MOVING_CALCULATION":
        config["previous"] = 1
        config["next"] = 0
        config["includeCurrent"] = True
    elif calc_type == "RANK":
        config["rankType"] = "DENSE"
    elif calc_type == "NESTED":
        config["fieldCaption"] = "Nested Calc"
    
    intent = TableCalcIntent(
        business_term="test",
        technical_field="Sales",
        table_calc_type=calc_type,
        table_calc_config=config
    )
    
    # Serialize and deserialize
    serialized = intent.model_dump(exclude_none=True)
    deserialized = TableCalcIntent(**serialized)
    
    # Verify
    assert deserialized.table_calc_type == calc_type
    assert deserialized.business_term == "test"
    assert deserialized.technical_field == "Sales"


# ============= Edge Cases =============

def test_table_calc_intent_minimal_config():
    """Test TableCalcIntent with minimal config."""
    intent = TableCalcIntent(
        business_term="simple",
        technical_field="Sales",
        table_calc_type="CUSTOM",
        table_calc_config={}
    )
    
    serialized = intent.model_dump(exclude_none=True)
    deserialized = TableCalcIntent(**serialized)
    
    assert deserialized.business_term == intent.business_term
    assert deserialized.table_calc_config == {}


def test_table_calc_intent_complex_config():
    """Test TableCalcIntent with complex config."""
    intent = TableCalcIntent(
        business_term="complex moving average",
        technical_field="Sales",
        table_calc_type="MOVING_CALCULATION",
        table_calc_config={
            "aggregation": "AVG",
            "dimensions": ["Order Date", "Category"],
            "previous": 3,
            "next": 1,
            "includeCurrent": True,
            "fillInNull": False,
            "levelAddress": "Region"
        },
        sort_direction="DESC",
        sort_priority=0
    )
    
    serialized = intent.model_dump(exclude_none=True)
    deserialized = TableCalcIntent(**serialized)
    
    assert deserialized.table_calc_config["aggregation"] == "AVG"
    assert len(deserialized.table_calc_config["dimensions"]) == 2
    assert deserialized.table_calc_config["previous"] == 3
    assert deserialized.sort_direction == "DESC"


def test_table_calc_intent_with_all_none_optionals():
    """Test TableCalcIntent with all optional fields as None."""
    intent = TableCalcIntent(
        business_term="simple",
        technical_field="Sales",
        table_calc_type="PERCENT_OF_TOTAL",
        table_calc_config={"dimensions": ["Category"]}
    )
    
    serialized = intent.model_dump(exclude_none=True)
    deserialized = TableCalcIntent(**serialized)
    
    assert deserialized.sort_direction is None
    assert deserialized.sort_priority is None


def test_table_calc_intent_running_total_with_restart():
    """Test running total intent with restart field."""
    intent = TableCalcIntent(
        business_term="cumulative sales by category",
        technical_field="Sales",
        table_calc_type="RUNNING_TOTAL",
        table_calc_config={
            "aggregation": "SUM",
            "dimensions": ["Order Date"],
            "restartEvery": "Category"
        }
    )
    
    serialized = intent.model_dump(exclude_none=True)
    deserialized = TableCalcIntent(**serialized)
    
    assert deserialized.table_calc_config["restartEvery"] == "Category"


def test_table_calc_intent_rank_all_types():
    """Test rank intent with all rank types."""
    rank_types = ["COMPETITION", "DENSE", "UNIQUE"]
    
    for rank_type in rank_types:
        intent = TableCalcIntent(
            business_term=f"{rank_type} rank",
            technical_field="Sales",
            table_calc_type="RANK",
            table_calc_config={
                "dimensions": ["Category"],
                "rankType": rank_type,
                "direction": "DESC"
            }
        )
        
        serialized = intent.model_dump(exclude_none=True)
        deserialized = TableCalcIntent(**serialized)
        
        assert deserialized.table_calc_config["rankType"] == rank_type


def test_table_calc_intent_percent_from_relative_to():
    """Test percent from intent with relativeTo options."""
    relative_to_options = ["PREVIOUS", "NEXT", "FIRST", "LAST"]
    
    for relative_to in relative_to_options:
        intent = TableCalcIntent(
            business_term=f"percent from {relative_to}",
            technical_field="Sales",
            table_calc_type="PERCENT_FROM",
            table_calc_config={
                "dimensions": ["Order Date"],
                "relativeTo": relative_to
            }
        )
        
        serialized = intent.model_dump(exclude_none=True)
        deserialized = TableCalcIntent(**serialized)
        
        assert deserialized.table_calc_config["relativeTo"] == relative_to


if __name__ == "__main__":
    # Run property tests
    pytest.main([__file__, "-v", "--hypothesis-show-statistics"])
