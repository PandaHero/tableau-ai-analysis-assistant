"""Observer models - Consistency checking (Metacognition).

Observer is the "Metacognition" phase of the LLM combination architecture.
It checks consistency between Step 1 and Step 2 outputs when validation fails.
Only triggered when step2.validation.all_valid == False.
"""

from pydantic import BaseModel, ConfigDict, Field

from .computations import Computation
from .enums import ObserverDecision
from .step1 import Step1Output
from .step2 import Step2Output


class Conflict(BaseModel):
    """Conflict found between Step 1 and Step 2."""
    model_config = ConfigDict(extra="forbid")
    
    aspect: str = Field(
        description="""<what>Aspect of the conflict</what>
<when>ALWAYS required</when>
<rule>e.g., "target", "partition_by", "operation"</rule>"""
    )
    
    description: str = Field(
        description="""<what>Description of the conflict</what>
<when>ALWAYS required</when>
<rule>Explain what is inconsistent</rule>"""
    )
    
    step1_value: str = Field(
        description="""<what>Value from Step 1</what>
<when>ALWAYS required</when>"""
    )
    
    step2_value: str = Field(
        description="""<what>Value from Step 2</what>
<when>ALWAYS required</when>"""
    )


class Correction(BaseModel):
    """Correction made by Observer."""
    model_config = ConfigDict(extra="forbid")
    
    field: str = Field(
        description="""<what>Field being corrected</what>
<when>ALWAYS required</when>
<rule>e.g., "partition_by", "operation.type"</rule>"""
    )
    
    original_value: str = Field(
        description="""<what>Original value from Step 2</what>
<when>ALWAYS required</when>"""
    )
    
    corrected_value: str = Field(
        description="""<what>Corrected value</what>
<when>ALWAYS required</when>"""
    )
    
    reason: str = Field(
        description="""<what>Reason for correction</what>
<when>ALWAYS required</when>
<rule>Explain why this correction is made</rule>"""
    )


class ObserverInput(BaseModel):
    """Input to Observer."""
    model_config = ConfigDict(extra="forbid")
    
    original_question: str = Field(
        description="""<what>Original user question</what>
<when>ALWAYS required</when>
<rule>Used to check if restated_question preserved key info</rule>"""
    )
    
    step1: Step1Output = Field(
        description="""<what>Step 1 output</what>
<when>ALWAYS required</when>"""
    )
    
    step2: Step2Output = Field(
        description="""<what>Step 2 output</what>
<when>ALWAYS required</when>"""
    )


class ObserverOutput(BaseModel):
    """Observer output: Consistency check result.
    
    <what>Consistency check + decision + correction</what>
    
    Observer checks:
    1. Restatement completeness: Did restated_question preserve key info from original?
    2. Structure consistency: Review Step 2's validation results
    3. Semantic consistency: Does computation match the intent?
    
    <fill_order>
    1. is_consistent (ALWAYS first)
    2. conflicts (ALWAYS, can be empty)
    3. decision (ALWAYS)
    4. correction (if decision=CORRECT)
    5. final_result (if decision=ACCEPT or CORRECT)
    </fill_order>
    
    <examples>
    Consistent: {"is_consistent": true, "conflicts": [], "decision": "ACCEPT", "final_result": {...}}
    Correctable: {"is_consistent": false, "conflicts": [...], "decision": "CORRECT", "correction": {...}, "final_result": {...}}
    </examples>
    
    <anti_patterns>
    ❌ ACCEPT when validation failed
    ❌ RETRY for minor fixable issues
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    is_consistent: bool = Field(
        description="""<what>Whether Step 1 and Step 2 are consistent</what>
<when>ALWAYS required</when>
<rule>Check restatement, structure, semantics</rule>"""
    )
    
    conflicts: list[Conflict] = Field(
        default_factory=list,
        description="""<what>Inconsistencies found</what>
<when>ALWAYS fill (empty if consistent)</when>"""
    )
    
    decision: ObserverDecision = Field(
        description="""<what>Action to take</what>
<when>ALWAYS required</when>
<rule>All pass→ACCEPT, Small conflict→CORRECT, Large conflict→RETRY, Unclear→CLARIFY</rule>"""
    )
    
    correction: Correction | None = Field(
        default=None,
        description="""<what>Correction details</what>
<when>ONLY when decision=CORRECT</when>
<dependency>decision == "CORRECT"</dependency>"""
    )
    
    final_result: Computation | None = Field(
        default=None,
        description="""<what>Final computation after correction</what>
<when>ONLY when decision=ACCEPT or CORRECT</when>
<dependency>decision in ["ACCEPT", "CORRECT"]</dependency>"""
    )
