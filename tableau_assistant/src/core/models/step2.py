"""Step 2 models - Computation reasoning and LLM self-validation.

Step 2 is the "Reasoning" phase of the LLM combination architecture.
It infers computation from restated_question and validates against Step 1 output.

IMPORTANT: validation is LLM self-validation, NOT code validation.
The LLM fills in the validation fields based on OPERATION_TYPE_MAPPING reference in the prompt.
"""

from pydantic import BaseModel, ConfigDict, Field

from .computations import Computation


class ValidationCheck(BaseModel):
    """Single validation check result (filled by LLM).
    
    LLM compares its inferred value against Step 1's reference value.
    """
    model_config = ConfigDict(extra="forbid")
    
    inferred_value: str | list[str] = Field(
        description="""<what>Value inferred from restated_question</what>
<when>ALWAYS required</when>
<rule>What LLM inferred in Step 2</rule>"""
    )
    
    reference_value: str | list[str] = Field(
        description="""<what>Value from Step 1 structured output</what>
<when>ALWAYS required</when>
<rule>What Step 1 extracted</rule>"""
    )
    
    is_match: bool = Field(
        description="""<what>Whether inferred matches reference</what>
<when>ALWAYS required</when>
<rule>LLM judges if they are semantically equivalent</rule>"""
    )
    
    note: str = Field(
        default="",
        description="""<what>Explanation of the check result</what>
<when>Recommended</when>
<rule>Explain why match or mismatch</rule>"""
    )


class Step2Validation(BaseModel):
    """Step 2 self-validation result (filled by LLM).
    
    LLM validates its own reasoning against Step 1 output.
    This is NOT code validation - LLM fills these fields.
    
    Validation checks:
    - target_check: Is target in what.measures?
    - partition_by_check: Is partition_by subset of where.dimensions?
    - operation_check: Does operation.type match how_type via OPERATION_TYPE_MAPPING?
    """
    model_config = ConfigDict(extra="forbid")
    
    target_check: ValidationCheck = Field(
        description="""<what>Check if target is in what.measures</what>
<when>ALWAYS required</when>
<rule>target ∈ what.measures</rule>"""
    )
    
    partition_by_check: ValidationCheck = Field(
        description="""<what>Check if partition_by is subset of where.dimensions</what>
<when>ALWAYS required</when>
<rule>partition_by ⊆ where.dimensions</rule>"""
    )
    
    operation_check: ValidationCheck = Field(
        description="""<what>Check if operation.type matches how_type</what>
<when>ALWAYS required</when>
<rule>Use OPERATION_TYPE_MAPPING from prompt to verify match</rule>
<must_not>Mark as match if operation.type not in mapping[how_type]</must_not>"""
    )
    
    all_valid: bool = Field(
        description="""<what>Whether all checks passed</what>
<when>ALWAYS required</when>
<rule>True only if all three checks have is_match=True</rule>"""
    )
    
    inconsistencies: list[str] = Field(
        default_factory=list,
        description="""<what>List of inconsistencies found</what>
<when>When all_valid=False</when>
<rule>Describe each mismatch</rule>"""
    )


class Step2Output(BaseModel):
    """Step 2 output: Computation reasoning and LLM self-validation.
    
    <what>Computation definitions + LLM self-validation results</what>
    
    IMPORTANT: validation is filled by LLM, not computed by code.
    LLM uses OPERATION_TYPE_MAPPING reference in prompt to validate.
    
    <fill_order>
    1. reasoning (ALWAYS first)
    2. computations (ALWAYS)
    3. validation (ALWAYS - LLM self-validates)
    </fill_order>
    
    <examples>
    Input: restated_question="按省份分组，在每个月内按销售额降序排名"
    Output: {
        "reasoning": "从重述中推断：target=销售额，partition_by=[订单日期]（每月内），operation=RANK",
        "computations": [{"target": "销售额", "partition_by": ["订单日期"], "operation": {"type": "RANK"}}],
        "validation": {"all_valid": true, ...}
    }
    </examples>
    
    <anti_patterns>
    ❌ partition_by not in dimensions: where.dimensions=["省份"], partition_by=["月份"]
    ❌ operation.type not matching how_type: how_type=RANKING, operation.type=PERCENT
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    reasoning: str = Field(
        description="""<what>Inference process description</what>
<when>ALWAYS required</when>
<rule>Explain how target, partition_by, operation were inferred from restated_question</rule>"""
    )
    
    computations: list[Computation] = Field(
        description="""<what>Computation definitions</what>
<when>ALWAYS required</when>
<rule>Each has target, partition_by, operation</rule>"""
    )
    
    validation: Step2Validation = Field(
        description="""<what>LLM self-validation result</what>
<when>ALWAYS required</when>
<rule>LLM checks its inference against Step 1 output</rule>"""
    )
