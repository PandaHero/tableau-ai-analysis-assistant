"""
Property-based tests for TableCalcField serialization round-trip consistency.

**Feature: vizql-api-migration, Property 2: TableCalcField serialization round-trip consistency**

This test validates that for any TableCalcField instance, serializing and then 
deserializing produces an equivalent object.
"""

import pytest
from hypothesis import given, strategies as st, settings
from tableau_assistant.src.models.vizql_types import (
    TableCalcField,
    TableCalcFieldReference,
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
    TableCalcComputedAggregation,
    SortDirection,
    FunctionEnum,
)


# ============= Hypothesis Strategies =============

@st.composite
def table_calc_field_reference_strategy(draw):
    """Generate random TableCalcFieldReference."""
    field_caption = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('Lu', 'Ll', 'Nd'),
        whitelist_characters=' _-'
    )))
    
    # Optional function
    function = draw(st.one_of(
        st.none(),
        st.sampled_from([
            FunctionEnum.SUM, FunctionEnum.AVG, FunctionEnum.MIN, 
            FunctionEnum.MAX, FunctionEnum.COUNT, FunctionEnum.COUNTD
        ])
    ))
    
    return TableCalcFieldReference(
        fieldCaption=field_caption,
        function=function
    )


@st.composite
def running_total_spec_strategy(draw):
    """Generate random RunningTotalTableCalcSpecification."""
    dimensions = draw(st.lists(
        table_calc_field_reference_strategy(),
        min_size=1,
        max_size=3
    ))
    
    aggregation = draw(st.one_of(
        st.none(),
        st.sampled_from([
            TableCalcComputedAggregation.SUM,
            TableCalcComputedAggregation.AVG,
            TableCalcComputedAggregation.MIN,
            TableCalcComputedAggregation.MAX
        ])
    ))
    
    restart_every = draw(st.one_of(
        st.none(),
        table_calc_field_reference_strategy()
    ))
    
    return RunningTotalTableCalcSpecification(
        dimensions=dimensions,
        aggregation=aggregation,
        restartEvery=restart_every
    )


@st.composite
def moving_calc_spec_strategy(draw):
    """Generate random MovingTableCalcSpecification."""
    dimensions = draw(st.lists(
        table_calc_field_reference_strategy(),
        min_size=1,
        max_size=3
    ))
    
    aggregation = draw(st.one_of(
        st.none(),
        st.sampled_from([
            TableCalcComputedAggregation.SUM,
            TableCalcComputedAggregation.AVG,
            TableCalcComputedAggregation.MIN,
            TableCalcComputedAggregation.MAX
        ])
    ))
    
    previous = draw(st.integers(min_value=0, max_value=10))
    next_val = draw(st.integers(min_value=0, max_value=10))
    include_current = draw(st.booleans())
    fill_in_null = draw(st.one_of(st.none(), st.booleans()))
    
    return MovingTableCalcSpecification(
        dimensions=dimensions,
        aggregation=aggregation,
        previous=previous,
        next=next_val,
        includeCurrent=include_current,
        fillInNull=fill_in_null
    )


@st.composite
def rank_spec_strategy(draw):
    """Generate random RankTableCalcSpecification."""
    dimensions = draw(st.lists(
        table_calc_field_reference_strategy(),
        min_size=1,
        max_size=3
    ))
    
    rank_type = draw(st.sampled_from(["COMPETITION", "DENSE", "UNIQUE"]))
    direction = draw(st.one_of(
        st.none(),
        st.sampled_from([SortDirection.ASC, SortDirection.DESC])
    ))
    
    return RankTableCalcSpecification(
        dimensions=dimensions,
        rankType=rank_type,
        direction=direction
    )


@st.composite
def percentile_spec_strategy(draw):
    """Generate random PercentileTableCalcSpecification."""
    dimensions = draw(st.lists(
        table_calc_field_reference_strategy(),
        min_size=1,
        max_size=3
    ))
    
    direction = draw(st.one_of(
        st.none(),
        st.sampled_from([SortDirection.ASC, SortDirection.DESC])
    ))
    
    return PercentileTableCalcSpecification(
        dimensions=dimensions,
        direction=direction
    )


@st.composite
def percent_of_total_spec_strategy(draw):
    """Generate random PercentOfTotalTableCalcSpecification."""
    dimensions = draw(st.lists(
        table_calc_field_reference_strategy(),
        min_size=1,
        max_size=3
    ))
    
    return PercentOfTotalTableCalcSpecification(dimensions=dimensions)


@st.composite
def percent_from_spec_strategy(draw):
    """Generate random PercentFromTableCalcSpecification."""
    dimensions = draw(st.lists(
        table_calc_field_reference_strategy(),
        min_size=1,
        max_size=3
    ))
    
    relative_to = draw(st.one_of(
        st.none(),
        st.sampled_from(["PREVIOUS", "NEXT", "FIRST", "LAST"])
    ))
    
    return PercentFromTableCalcSpecification(
        dimensions=dimensions,
        relativeTo=relative_to
    )


@st.composite
def percent_difference_from_spec_strategy(draw):
    """Generate random PercentDifferenceFromTableCalcSpecification."""
    dimensions = draw(st.lists(
        table_calc_field_reference_strategy(),
        min_size=1,
        max_size=3
    ))
    
    relative_to = draw(st.one_of(
        st.none(),
        st.sampled_from(["PREVIOUS", "NEXT", "FIRST", "LAST"])
    ))
    
    return PercentDifferenceFromTableCalcSpecification(
        dimensions=dimensions,
        relativeTo=relative_to
    )


@st.composite
def difference_from_spec_strategy(draw):
    """Generate random DifferenceFromTableCalcSpecification."""
    dimensions = draw(st.lists(
        table_calc_field_reference_strategy(),
        min_size=1,
        max_size=3
    ))
    
    relative_to = draw(st.one_of(
        st.none(),
        st.sampled_from(["PREVIOUS", "NEXT", "FIRST", "LAST"])
    ))
    
    return DifferenceFromTableCalcSpecification(
        dimensions=dimensions,
        relativeTo=relative_to
    )


@st.composite
def custom_spec_strategy(draw):
    """Generate random CustomTableCalcSpecification."""
    dimensions = draw(st.lists(
        table_calc_field_reference_strategy(),
        min_size=1,
        max_size=3
    ))
    
    return CustomTableCalcSpecification(dimensions=dimensions)


@st.composite
def nested_spec_strategy(draw):
    """Generate random NestedTableCalcSpecification."""
    dimensions = draw(st.lists(
        table_calc_field_reference_strategy(),
        min_size=1,
        max_size=3
    ))
    
    field_caption = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('Lu', 'Ll', 'Nd'),
        whitelist_characters=' _-'
    )))
    
    return NestedTableCalcSpecification(
        dimensions=dimensions,
        fieldCaption=field_caption
    )


@st.composite
def table_calc_specification_strategy(draw):
    """Generate random TableCalcSpecification (any type)."""
    spec_type = draw(st.sampled_from([
        'running_total',
        'moving_calc',
        'rank',
        'percentile',
        'percent_of_total',
        'percent_from',
        'percent_difference_from',
        'difference_from',
        'custom',
        'nested'
    ]))
    
    if spec_type == 'running_total':
        return draw(running_total_spec_strategy())
    elif spec_type == 'moving_calc':
        return draw(moving_calc_spec_strategy())
    elif spec_type == 'rank':
        return draw(rank_spec_strategy())
    elif spec_type == 'percentile':
        return draw(percentile_spec_strategy())
    elif spec_type == 'percent_of_total':
        return draw(percent_of_total_spec_strategy())
    elif spec_type == 'percent_from':
        return draw(percent_from_spec_strategy())
    elif spec_type == 'percent_difference_from':
        return draw(percent_difference_from_spec_strategy())
    elif spec_type == 'difference_from':
        return draw(difference_from_spec_strategy())
    elif spec_type == 'custom':
        return draw(custom_spec_strategy())
    else:  # nested
        return draw(nested_spec_strategy())


@st.composite
def table_calc_field_strategy(draw):
    """Generate random TableCalcField."""
    field_caption = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('Lu', 'Ll', 'Nd'),
        whitelist_characters=' _-'
    )))
    
    # Optional function
    function = draw(st.one_of(
        st.none(),
        st.sampled_from([
            FunctionEnum.SUM, FunctionEnum.AVG, FunctionEnum.MIN,
            FunctionEnum.MAX, FunctionEnum.COUNT
        ])
    ))
    
    # Optional calculation
    calculation = draw(st.one_of(
        st.none(),
        st.text(min_size=1, max_size=100, alphabet=st.characters(
            whitelist_categories=('Lu', 'Ll', 'Nd'),
            whitelist_characters=' []+-*/()'
        ))
    ))
    
    # Required table calculation
    table_calculation = draw(table_calc_specification_strategy())
    
    # Optional nested table calculations (keep it simple, max 2)
    nested_table_calculations = draw(st.one_of(
        st.none(),
        st.lists(
            table_calc_specification_strategy(),
            min_size=0,
            max_size=2
        )
    ))
    
    # Convert empty list to None
    if nested_table_calculations is not None and len(nested_table_calculations) == 0:
        nested_table_calculations = None
    
    return TableCalcField(
        fieldCaption=field_caption,
        function=function,
        calculation=calculation,
        tableCalculation=table_calculation,
        nestedTableCalculations=nested_table_calculations
    )


# ============= Property-Based Tests =============

@given(table_calc_field_strategy())
@settings(max_examples=100, deadline=None)
def test_table_calc_field_round_trip_property(field):
    """
    **Property 2: TableCalcField serialization round-trip consistency**
    
    For any TableCalcField instance, serializing and then deserializing 
    should produce an equivalent object.
    
    **Validates: Requirements 9.5**
    """
    # Serialize
    serialized = field.model_dump(exclude_none=True)
    
    # Deserialize
    deserialized = TableCalcField(**serialized)
    
    # Verify equivalence
    assert deserialized.fieldCaption == field.fieldCaption
    assert deserialized.function == field.function
    assert deserialized.calculation == field.calculation
    assert deserialized.tableCalculation.tableCalcType == field.tableCalculation.tableCalcType
    
    # Verify nested calculations if present
    if field.nestedTableCalculations is not None:
        assert deserialized.nestedTableCalculations is not None
        assert len(deserialized.nestedTableCalculations) == len(field.nestedTableCalculations)
        for orig, deser in zip(field.nestedTableCalculations, deserialized.nestedTableCalculations):
            assert deser.tableCalcType == orig.tableCalcType
    else:
        assert deserialized.nestedTableCalculations is None
    
    # Verify re-serialization produces same result
    # Note: We need to normalize the comparison because Pydantic may handle
    # None vs default values differently on round-trip
    reserialized = deserialized.model_dump(exclude_none=True)
    
    # For deep comparison, we serialize both to JSON and compare
    # This handles cases where None becomes a default value
    import json
    serialized_json = json.dumps(serialized, sort_keys=True, default=str)
    reserialized_json = json.dumps(reserialized, sort_keys=True, default=str)
    assert serialized_json == reserialized_json


@given(running_total_spec_strategy())
@settings(max_examples=100, deadline=None)
def test_running_total_spec_round_trip(spec):
    """Test RunningTotalTableCalcSpecification round-trip."""
    serialized = spec.model_dump(exclude_none=True)
    deserialized = RunningTotalTableCalcSpecification(**serialized)
    
    assert deserialized.tableCalcType == spec.tableCalcType
    assert deserialized.aggregation == spec.aggregation
    assert len(deserialized.dimensions) == len(spec.dimensions)


@given(moving_calc_spec_strategy())
@settings(max_examples=100, deadline=None)
def test_moving_calc_spec_round_trip(spec):
    """Test MovingTableCalcSpecification round-trip."""
    serialized = spec.model_dump(exclude_none=True)
    deserialized = MovingTableCalcSpecification(**serialized)
    
    assert deserialized.tableCalcType == spec.tableCalcType
    assert deserialized.previous == spec.previous
    assert deserialized.next == spec.next
    assert deserialized.includeCurrent == spec.includeCurrent


@given(rank_spec_strategy())
@settings(max_examples=100, deadline=None)
def test_rank_spec_round_trip(spec):
    """Test RankTableCalcSpecification round-trip."""
    serialized = spec.model_dump(exclude_none=True)
    deserialized = RankTableCalcSpecification(**serialized)
    
    assert deserialized.tableCalcType == spec.tableCalcType
    assert deserialized.rankType == spec.rankType
    assert deserialized.direction == spec.direction


@given(table_calc_field_reference_strategy())
@settings(max_examples=100, deadline=None)
def test_field_reference_round_trip(ref):
    """Test TableCalcFieldReference round-trip."""
    serialized = ref.model_dump(exclude_none=True)
    deserialized = TableCalcFieldReference(**serialized)
    
    assert deserialized.fieldCaption == ref.fieldCaption
    assert deserialized.function == ref.function


# ============= Edge Cases =============

def test_table_calc_field_with_all_none_optionals():
    """Test TableCalcField with all optional fields as None."""
    spec = RunningTotalTableCalcSpecification(
        dimensions=[TableCalcFieldReference(fieldCaption="Date")]
    )
    field = TableCalcField(
        fieldCaption="Test",
        tableCalculation=spec
    )
    
    serialized = field.model_dump(exclude_none=True)
    deserialized = TableCalcField(**serialized)
    
    assert deserialized.fieldCaption == field.fieldCaption
    assert deserialized.function is None
    assert deserialized.calculation is None
    assert deserialized.nestedTableCalculations is None


def test_table_calc_field_with_complex_nested():
    """Test TableCalcField with multiple nested calculations."""
    primary = RunningTotalTableCalcSpecification(
        dimensions=[TableCalcFieldReference(fieldCaption="Date")],
        aggregation=TableCalcComputedAggregation.SUM
    )
    
    nested1 = PercentOfTotalTableCalcSpecification(
        dimensions=[TableCalcFieldReference(fieldCaption="Category")]
    )
    
    nested2 = RankTableCalcSpecification(
        dimensions=[TableCalcFieldReference(fieldCaption="Region")],
        rankType="DENSE"
    )
    
    field = TableCalcField(
        fieldCaption="Complex Calc",
        tableCalculation=primary,
        nestedTableCalculations=[nested1, nested2]
    )
    
    serialized = field.model_dump(exclude_none=True)
    deserialized = TableCalcField(**serialized)
    
    assert len(deserialized.nestedTableCalculations) == 2
    assert deserialized.nestedTableCalculations[0].tableCalcType == "PERCENT_OF_TOTAL"
    assert deserialized.nestedTableCalculations[1].tableCalcType == "RANK"


if __name__ == "__main__":
    # Run property tests
    pytest.main([__file__, "-v", "--hypothesis-show-statistics"])
