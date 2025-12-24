"""Step 2 models - Computation reasoning and LLM self-validation.

Step 2 is the "Reasoning" phase of the LLM combination architecture.
It infers computation from restated_question and validates against Step 1 output.

IMPORTANT: validation is LLM self-validation, NOT code validation.
The LLM fills in the validation fields based on the rules in field descriptions.
"""

from pydantic import BaseModel, ConfigDict, Field

from .computations import Computation


class ValidationCheck(BaseModel):
    """Single validation check result (filled by LLM).
    
    <what>LLM compares its inferred value against Step 1's reference value</what>
    """
    model_config = ConfigDict(extra="forbid")
    
    inferred_value: str | list[str] = Field(
        description="""<what>Value inferred from restated_question</what>
<when>ALWAYS required</when>
<rule>Extract what you inferred in Step 2</rule>"""
    )
    
    reference_value: str | list[str] = Field(
        description="""<what>Value from Step 1 structured output</what>
<when>ALWAYS required</when>
<rule>Extract what Step 1 extracted</rule>"""
    )
    
    is_match: bool = Field(
        description="""<what>Whether inferred matches reference</what>
<when>ALWAYS required</when>
<rule>True if semantically equivalent, False otherwise</rule>
<must_not>Mark as True when values are clearly different</must_not>"""
    )
    
    note: str = Field(
        default="",
        description="""<what>Explanation of the check result</what>
<when>Recommended, especially when is_match=False</when>
<rule>Explain why match or mismatch</rule>"""
    )


class Step2Validation(BaseModel):
    """Step 2 self-validation (LLM validates against Step 1).
    
    <fill_order>
    1. target_check
    2. partition_by_check
    3. calc_type_check
    4. all_valid
    5. inconsistencies (if any)
    </fill_order>
    """
    model_config = ConfigDict(extra="forbid")
    
    target_check: ValidationCheck = Field(
        description="""<what>Check target in what.measures</what>
<when>ALWAYS</when>"""
    )
    
    partition_by_check: ValidationCheck = Field(
        description="""<what>Check partition_by subset of where.dimensions</what>
<when>ALWAYS</when>"""
    )
    
    calc_type_check: ValidationCheck = Field(
        description="""<what>Check calc_type matches question intent</what>
<when>ALWAYS</when>"""
    )
    
    all_valid: bool = Field(
        description="""<what>All checks passed</what>
<when>ALWAYS</when>
<rule>True only if all is_match=True</rule>"""
    )
    
    inconsistencies: list[str] = Field(
        default_factory=list,
        description="""<what>List of mismatches</what>
<when>If all_valid=False</when>"""
    )


class Step2Output(BaseModel):
    """Step 2 output: Computation reasoning + self-validation.
    
    <fill_order>
    1. reasoning (ALWAYS)
    2. computations (ALWAYS, can be multiple)
    3. validation (ALWAYS)
    </fill_order>
    
    <examples>
    Single: {"computations": [{"target": "Sales", "calc_type": "RANK", "partition_by": ["Month"]}]}
    Combination: {"computations": [{"calc_type": "LOD_FIXED", ...}, {"calc_type": "RANK", ...}]}
    </examples>
    
    <anti_patterns>
    X Combination outputs only one Computation
    X LOD after table calc (should be LOD first)
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    reasoning: str = Field(
        description="""<what>Inference process</what>
<when>ALWAYS</when>"""
    )
    
    computations: list[Computation] = Field(
        description="""<what>Computation definitions</what>
<when>ALWAYS</when>
<rule>Combination: LOD first, then table calc</rule>"""
    )
    
    validation: Step2Validation = Field(
        description="""<what>Self-validation result</what>
<when>ALWAYS</when>"""
    )
