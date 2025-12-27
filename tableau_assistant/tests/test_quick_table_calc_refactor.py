# -*- coding: utf-8 -*-
"""Quick Table Calc Refactor - Validation Tests.

Tests for Task 7: 检查点 - 完整功能验证

Updated for new Computation model structure:
- Computation is now a Union type, not a
from pydantic import ValidationError

from tableau_assistant.src.core.models import (
    # Enums
    HowType,
    CalcType,
    RankStyle,
    RelativeTo,
    CalcAggregation,
    AggregationType,
    SortDirection,
    # Models
    CalcParams,
    Computation,
)
from tableau_assistant.src.agents.semantic_parser.models import (
    Step2Output,
    Step2Validation,
    ValidationCheck,
)


class TestHowTypeEnum:
    """Test HowType enum - binary classification."""
    
    def test_only_two_values(self):
        """HowType should only have SIMPLE and COMPLEX."""
        assert len(HowType) == 2
        assert HowType.SIMPLE.value == "SIMPLE"
        assert HowType.COMPLEX.value == "COMPLEX"
    
    def test_serialization(self):
        """HowType should serialize to string."""
        assert str(HowType.SIMPLE) == "HowType.SIMPLE"
        assert HowType.SIMPLE.value == "SIMPLE"


class TestCalcTypeEnum:
    """Test CalcType enum - calculation types."""
    
    def test_table_calc_types(self):
        """CalcType should have all table calculation types."""
        table_calc_types = [
            CalcType.RANK,
            CalcType.DENSE_RANK,
            CalcType.PERCENTILE,
            CalcType.RUNNING_TOTAL,
            CalcType.MOVING_CALC,
            CalcType.PERCENT_OF_TOTAL,
            CalcType.DIFFERENCE,
            CalcType.PERCENT_DIFFERENCE,
        ]
        for calc_type in table_calc_types:
            assert calc_type in CalcType
    
    def test_lod_types(self):
        """CalcType should have all LOD types."""
        lod_types = [
            CalcType.LOD_FIXED,
            CalcType.LOD_INCLUDE,
            CalcType.LOD_EXCLUDE,
        ]
        for lod_type in lod_types:
            assert lod_type in CalcType
    
    def test_total_count(self):
        """CalcType should have 11 values."""
        assert len(CalcType) == 11


class TestCalcParams:
    """Test CalcParams model - calculation parameters."""
    
    def test_empty_params(self):
        """CalcParams should allow empty initialization."""
        params = CalcParams()
        assert params.direction is None
        assert params.rank_style is None
        assert params.lod_dimensions is None
    
    def test_rank_params(self):
        """CalcParams should accept rank parameters."""
        params = CalcParams(
            direction=SortDirection.DESC,
            rank_style=RankStyle.COMPETITION
        )
        assert params.direction == SortDirection.DESC
        assert params.rank_style == RankStyle.COMPETITION
    
    def test_lod_params(self):
        """CalcParams should accept LOD parameters."""
        params = CalcParams(
            lod_dimensions=["CustomerID"],
            lod_aggregation=AggregationType.MIN
        )
        assert params.lod_dimensions == ["CustomerID"]
        assert params.lod_aggregation == AggregationType.MIN
    
    def test_running_total_params(self):
        """CalcParams should accept running total parameters."""
        params = CalcParams(
            aggregation=CalcAggregation.SUM,
            restart_every="Year"
        )
        assert params.aggregation == CalcAggregation.SUM
        assert params.restart_every == "Year"
    
    def test_moving_calc_params(self):
        """CalcParams should accept moving calculation parameters."""
        params = CalcParams(
            aggregation=CalcAggregation.AVG,
            window_previous=2,
            window_next=0,
            include_current=True
        )
        assert params.window_previous == 2
        assert params.window_next == 0
        assert params.include_current is True
    
    def test_extra_fields_forbidden(self):
        """CalcParams should reject extra fields."""
        with pytest.raises(ValidationError):
            CalcParams(unknown_field="value")


class TestComputation:
    """Test Computation model - core abstraction."""
    
    def test_rank_computation(self):
        """Computation should work for RANK type."""
        comp = Computation(
            target="Sales",
            calc_type=CalcType.RANK,
            partition_by=["Month"],
            params=CalcParams(direction=SortDirection.DESC)
        )
        assert comp.target == "Sales"
        assert comp.calc_type == CalcType.RANK
        assert comp.partition_by == ["Month"]
        assert comp.params.direction == SortDirection.DESC
    
    def test_lod_computation(self):
        """Computation should work for LOD_FIXED type."""
        comp = Computation(
            target="OrderDate",
            calc_type=CalcType.LOD_FIXED,
            partition_by=[],
            params=CalcParams(
                lod_dimensions=["CustomerID"],
                lod_aggregation=AggregationType.MIN
            ),
            alias="FirstPurchase"
        )
        assert comp.calc_type == CalcType.LOD_FIXED
        assert comp.alias == "FirstPurchase"
        assert comp.params.lod_dimensions == ["CustomerID"]
    
    def test_global_computation(self):
        """Computation should work with empty partition_by."""
        comp = Computation(
            target="Sales",
            calc_type=CalcType.PERCENT_OF_TOTAL,
            partition_by=[]
        )
        assert comp.partition_by == []
    
    def test_target_required(self):
        """Computation should require target field."""
        with pytest.raises(ValidationError):
            Computation(
                calc_type=CalcType.RANK,
                partition_by=[]
            )
    
    def test_target_not_empty(self):
        """Computation should reject empty target."""
        with pytest.raises(ValidationError):
            Computation(
                target="",
                calc_type=CalcType.RANK,
                partition_by=[]
            )
    
    def test_whitespace_target_stripped(self):
        """Computation should strip whitespace from target."""
        comp = Computation(
            target="  Sales  ",
            calc_type=CalcType.RANK,
            partition_by=[]
        )
        assert comp.target == "Sales"


class TestValidationCheck:
    """Test ValidationCheck model - LLM self-validation."""
    
    def test_match_check(self):
        """ValidationCheck should work for matching values."""
        check = ValidationCheck(
            inferred_value="Sales",
            reference_value="Sales",
            is_match=True,
            note="Exact match"
        )
        assert check.is_match is True
    
    def test_mismatch_check(self):
        """ValidationCheck should work for mismatching values."""
        check = ValidationCheck(
            inferred_value="Revenue",
            reference_value="Sales",
            is_match=False,
            note="Different field names"
        )
        assert check.is_match is False


class TestStep2Validation:
    """Test Step2Validation model - self-validation result."""
    
    def test_all_valid(self):
        """Step2Validation should work when all checks pass."""
        validation = Step2Validation(
            target_check=ValidationCheck(
                inferred_value="Sales",
                reference_value="Sales",
                is_match=True
            ),
            partition_by_check=ValidationCheck(
                inferred_value=["Month"],
                reference_value=["Month", "Region"],
                is_match=True,
                note="Subset check passed"
            ),
            calc_type_check=ValidationCheck(
                inferred_value="RANK",
                reference_value="COMPLEX",
                is_match=True,
                note="RANK is valid for COMPLEX"
            ),
            all_valid=True
        )
        assert validation.all_valid is True
        assert len(validation.inconsistencies) == 0
    
    def test_with_inconsistencies(self):
        """Step2Validation should capture inconsistencies."""
        validation = Step2Validation(
            target_check=ValidationCheck(
                inferred_value="Revenue",
                reference_value="Sales",
                is_match=False
            ),
            partition_by_check=ValidationCheck(
                inferred_value=["Month"],
                reference_value=["Month"],
                is_match=True
            ),
            calc_type_check=ValidationCheck(
                inferred_value="RANK",
                reference_value="COMPLEX",
                is_match=True
            ),
            all_valid=False,
            inconsistencies=["target 'Revenue' not in measures"]
        )
        assert validation.all_valid is False
        assert len(validation.inconsistencies) == 1


class TestStep2Output:
    """Test Step2Output model - complete output."""
    
    def test_single_computation(self):
        """Step2Output should work with single computation."""
        output = Step2Output(
            reasoning="User wants sales ranking by month",
            computations=[
                Computation(
                    target="Sales",
                    calc_type=CalcType.RANK,
                    partition_by=["Month"],
                    params=CalcParams(direction=SortDirection.DESC)
                )
            ],
            validation=Step2Validation(
                target_check=ValidationCheck(
                    inferred_value="Sales",
                    reference_value="Sales",
                    is_match=True
                ),
                partition_by_check=ValidationCheck(
                    inferred_value=["Month"],
                    reference_value=["Month"],
                    is_match=True
                ),
                calc_type_check=ValidationCheck(
                    inferred_value="RANK",
                    reference_value="COMPLEX",
                    is_match=True
                ),
                all_valid=True
            )
        )
        assert len(output.computations) == 1
        assert output.validation.all_valid is True
    
    def test_combination_lod_and_table_calc(self):
        """Step2Output should work with LOD + Table Calc combination."""
        output = Step2Output(
            reasoning="User wants to rank customers by first purchase date",
            computations=[
                # LOD first
                Computation(
                    target="OrderDate",
                    calc_type=CalcType.LOD_FIXED,
                    partition_by=[],
                    params=CalcParams(
                        lod_dimensions=["CustomerID"],
                        lod_aggregation=AggregationType.MIN
                    ),
                    alias="FirstPurchase"
                ),
                # Table Calc second
                Computation(
                    target="FirstPurchase",
                    calc_type=CalcType.RANK,
                    partition_by=[],
                    params=CalcParams(direction=SortDirection.ASC)
                )
            ],
            validation=Step2Validation(
                target_check=ValidationCheck(
                    inferred_value="OrderDate",
                    reference_value="OrderDate",
                    is_match=True
                ),
                partition_by_check=ValidationCheck(
                    inferred_value=[],
                    reference_value=["CustomerID"],
                    is_match=True
                ),
                calc_type_check=ValidationCheck(
                    inferred_value="LOD_FIXED + RANK",
                    reference_value="COMPLEX",
                    is_match=True
                ),
                all_valid=True
            )
        )
        assert len(output.computations) == 2
        assert output.computations[0].calc_type == CalcType.LOD_FIXED
        assert output.computations[1].calc_type == CalcType.RANK


class TestJsonSerialization:
    """Test JSON serialization for all models."""
    
    def test_computation_to_json(self):
        """Computation should serialize to JSON correctly."""
        comp = Computation(
            target="Sales",
            calc_type=CalcType.RANK,
            partition_by=["Month"],
            params=CalcParams(direction=SortDirection.DESC)
        )
        json_data = comp.model_dump()
        assert json_data["target"] == "Sales"
        assert json_data["calc_type"] == "RANK"
        assert json_data["partition_by"] == ["Month"]
        assert json_data["params"]["direction"] == "DESC"
    
    def test_computation_from_json(self):
        """Computation should deserialize from JSON correctly."""
        json_data = {
            "target": "Sales",
            "calc_type": "RANK",
            "partition_by": ["Month"],
            "params": {"direction": "DESC"}
        }
        comp = Computation.model_validate(json_data)
        assert comp.target == "Sales"
        assert comp.calc_type == CalcType.RANK
        assert comp.params.direction == SortDirection.DESC


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
