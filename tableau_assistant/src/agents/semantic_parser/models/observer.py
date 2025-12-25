"""Observer models - Consistency checking (Metacognition).

Observer is the "Metacognition" phase of the LLM combination architecture.
It handles two scenarios:
1. Step 1 validation failed - correct filter issues (missing dates, etc.)
2. Step 2 validation failed - check consistency between Step 1 and Step 2

Triggered when:
- step1.validation.all_valid == False (Step 1 filter issues)
- step2.validation.all_valid == False (Step 1/2 consistency issues)
"""

from pydantic import BaseModel, ConfigDict, Field

from tableau_assistant.src.core.models.computations import Computation
from tableau_assistant.src.core.models.enums import ObserverDecision
from tableau_assistant.src.core.models.filters import Filter

from .step1 import Step1Output
from .step2 import Step2Output


class Conflict(BaseModel):
    """Conflict found during validation.
    
    <what>Describes a specific inconsistency or issue</what>
    """
    model_config = ConfigDict(extra="forbid")
    
    aspect: str = Field(
        description="""<what>Aspect of the conflict</what>
<when>ALWAYS required</when>
<examples>filter_completeness, step1_step2_consistency, computation_mismatch</examples>"""
    )
    
    description: str = Field(
        description="""<what>Description of the conflict</what>
<when>ALWAYS required</when>"""
    )
    
    step1_value: str = Field(
        default="",
        description="""<what>Value from Step 1</what>
<when>For consistency checks</when>"""
    )
    
    step2_value: str = Field(
        default="",
        description="""<what>Value from Step 2</what>
<when>For consistency checks</when>"""
    )


class Correction(BaseModel):
    """Correction made by Observer.
    
    <what>Details of how to fix a conflict</what>
    """
    model_config = ConfigDict(extra="forbid")
    
    field: str = Field(
        description="""<what>Field being corrected</what>
<when>ALWAYS required</when>"""
    )
    
    original_value: str | int | None = Field(
        default=None,
        description="""<what>Original value (as string)</what>
<when>ALWAYS required</when>
<rule>Convert to string if needed, use "null" for None</rule>"""
    )
    
    corrected_value: str | int | None = Field(
        description="""<what>Corrected value (as string)</what>
<when>ALWAYS required</when>
<rule>Convert to string if needed</rule>"""
    )
    
    reason: str = Field(
        description="""<what>Reason for correction</what>
<when>ALWAYS required</when>"""
    )


class Step1Correction(BaseModel):
    """Correction for Step 1 output (filter issues).
    
    <what>Corrected filters when Step 1 validation fails</what>
    """
    model_config = ConfigDict(extra="forbid")
    
    corrected_filters: list[Filter] = Field(
        description="""<what>Complete list of corrected filters</what>
<when>ALWAYS required when correcting Step 1</when>
<rule>Include ALL filters, not just the corrected ones</rule>"""
    )
    
    corrections_made: list[Correction] = Field(
        default_factory=list,
        description="""<what>List of corrections applied</what>
<when>ALWAYS required</when>"""
    )


class ObserverInput(BaseModel):
    """Input to Observer.
    
    <what>All information needed for consistency checking</what>
    """
    model_config = ConfigDict(extra="forbid")
    
    original_question: str = Field(
        description="""<what>Original user question</what>
<when>ALWAYS required</when>"""
    )
    
    step1: Step1Output = Field(
        description="""<what>Step 1 output</what>
<when>ALWAYS required</when>"""
    )
    
    step2: Step2Output | None = Field(
        default=None,
        description="""<what>Step 2 output</what>
<when>Only for Step 2 validation failures</when>"""
    )


class ObserverOutput(BaseModel):
    """Observer output: Validation check result.
    
    <what>Validation check + decision + correction</what>
    
    <fill_order>
    1. is_consistent (ALWAYS first)
    2. conflicts (ALWAYS, can be empty)
    3. decision (ALWAYS)
    4. step1_correction (if correcting Step 1 filters)
    5. correction (if correcting Step 2 computation)
    6. final_result (if decision=ACCEPT or CORRECT for Step 2)
    </fill_order>
    
    <examples>
    Step1 filter fix: {"is_consistent": false, "conflicts": [{"aspect": "filter_completeness", ...}], "decision": "CORRECT", "step1_correction": {"corrected_filters": [...]}}
    Step2 consistent: {"is_consistent": true, "conflicts": [], "decision": "ACCEPT", "final_result": {...}}
    Step2 correctable: {"is_consistent": false, "conflicts": [...], "decision": "CORRECT", "correction": {...}, "final_result": {...}}
    </examples>
    
    <anti_patterns>
    X ACCEPT when any validation check failed
    X RETRY for minor fixable issues (use CORRECT instead)
    X CLARIFY when the answer is determinable
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    is_consistent: bool = Field(
        description="""<what>Whether validation passed</what>
<when>ALWAYS required</when>"""
    )
    
    conflicts: list[Conflict] = Field(
        default_factory=list,
        description="""<what>Issues found</what>
<when>ALWAYS fill (empty list if consistent)</when>"""
    )
    
    decision: ObserverDecision = Field(
        description="""<what>Action to take</what>
<when>ALWAYS required</when>"""
    )
    
    # For Step 1 filter corrections
    step1_correction: Step1Correction | None = Field(
        default=None,
        description="""<what>Corrected Step 1 filters</what>
<when>ONLY when correcting Step 1 filter issues</when>
<dependency>decision == CORRECT and step1 validation failed</dependency>"""
    )
    
    # For Step 2 computation corrections (existing)
    correction: Correction | None = Field(
        default=None,
        description="""<what>Correction details for Step 2</what>
<when>ONLY when decision=CORRECT for Step 2</when>
<dependency>decision == CORRECT and step2 validation failed</dependency>"""
    )
    
    final_result: Computation | None = Field(
        default=None,
        description="""<what>Final computation after correction</what>
<when>ONLY when decision=ACCEPT or CORRECT for Step 2</when>
<dependency>decision in [ACCEPT, CORRECT] and step2 exists</dependency>"""
    )


__all__ = [
    "Conflict",
    "Correction",
    "Step1Correction",
    "ObserverInput",
    "ObserverOutput",
]
