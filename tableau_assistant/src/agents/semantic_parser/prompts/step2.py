# -*- coding: utf-8 -*-
"""Step 2 Prompt - Computation reasoning and LLM self-validation.

Step 2 is the "Reasoning" phase of the LLM combination architecture.
It infers computation from restated_question and validates against Step 1 output.

IMPORTANT: Validation is done by LLM itself, NOT by code.

Design principles (from prompt_and_models规范文档.md):
- Prompt teaches LLM HOW to think (domain concepts, analysis methods)
- Schema tells LLM WHAT to output (field meanings, fill rules, decision rules)
- Examples belong in Schema <examples> tags, NOT in Prompt
- Enum selection rules only in Enum docstring <rule> tag
"""

from typing import Type
from pydantic import BaseModel

from tableau_assistant.src.agents.base.prompt import VizQLPrompt
from tableau_assistant.src.agents.semantic_parser.models import Step2Output


class Step2Prompt(VizQLPrompt):
    """Step 2: Computation reasoning and LLM self-validation.
    
    Uses 4-section structure per spec section 3.3:
    - ROLE: 2-3 sentences defining expertise
    - TASK: 1 sentence + Process flow
    - DOMAIN KNOWLEDGE: Domain concepts + abstract thinking steps (NO field-specific rules)
    - CONSTRAINTS: MUST/MUST NOT format
    """
    
    def get_role(self) -> str:
        return """Computation reasoning expert for data analysis.

Expertise: LOD vs Table Calc decision, Partition inference, Self-validation"""

    def get_task(self) -> str:
        return """Infer computation from restated_question, then validate against Step 1 output.

Process: Infer target → Decide LOD vs Table Calc → Infer partition/dimensions → Fill params → Validate"""

    def get_specific_domain_knowledge(self) -> str:
        return """**Computation Model**
Computation = Target × CalcType × Partition × Params

**Think step by step:**
Step 1: Infer target from restated_question (must be in what.measures)
Step 2: Decide LOD vs Table Calc based on question semantics
Step 3: Select specific calc_type (see computation class docstrings)
Step 4: Infer partition from scope keywords (must be subset of where.dimensions)
Step 5: Fill remaining fields per class fill_order
Step 6: Check if computation covers derived measures in Step1
Step 7: Validate all three checks

**LOD vs Table Calc - Core Distinction**
- LOD = Question needs metric at DIFFERENT granularity than query dimensions
- Table Calc = Question needs to TRANSFORM query results

**Partition Keywords**
- global/total/no scope word → empty partition
- per month/within month → time dimension from where.dimensions
- per province/per region → corresponding dimension from where.dimensions

**Measure Coverage**
When Step1 has duplicate measures with aliases, check if your computation can derive the aliased measure. If yes, only keep base measure as target.

**Combination Scenarios**
When question needs BOTH different granularity AND transformation:
→ Output order: [LOD first, then Table Calc]"""

    def get_constraints(self) -> str:
        return """MUST: Infer from restated_question, Validate against Step 1, Report inconsistencies
MUST NOT: Infer partition_by not in dimensions, Skip validation, Mark valid when check fails"""

    def get_user_template(self) -> str:
        return """**Restated Question:** {restated_question}

**Step 1 Output (for validation):**
- what.measures: {measures}
- where.dimensions: {dimensions}
- how_type: {how_type}

Please infer computation and self-validate, then output Step2Output JSON."""

    def get_output_model(self) -> Type[BaseModel]:
        return Step2Output


# Create prompt instance
STEP2_PROMPT = Step2Prompt()

__all__ = ["Step2Prompt", "STEP2_PROMPT"]
