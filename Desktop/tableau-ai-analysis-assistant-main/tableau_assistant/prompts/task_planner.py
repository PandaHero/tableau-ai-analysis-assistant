"""
Task Planner Prompt (Structured Template)

Uses the structured template system for better consistency and maintainability.
"""
from typing import Type
from pydantic import BaseModel
from tableau_assistant.prompts.base import VizQLPrompt
from tableau_assistant.src.models.query_plan import QueryPlanningResult


class TaskPlannerPrompt(VizQLPrompt):
    """Optimized prompt for field mapping and query intent generation using 4-section structure"""
    
    def get_role(self) -> str:
        return "Field mapper who converts business terms to technical fields."
    
    def get_task(self) -> str:
        return """Map business terms to fields, generate Intents.

Process: Match category → Match name → Generate Intent → Add filters"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """Resources: {original_question}, {sub_questions}, {metadata}, {dimension_hierarchy}

**Think step by step:**

Step 0: Check if this is an exploratory question
- Review sub-question: Does it have needs_exploration=true?
- If yes, select starting fields for exploration:
  * Choose 1-2 dimensions from metadata (prefer Level 1-2 coarse-grained fields)
  * Choose 1-2 measures from metadata (prefer core business metrics)
  * Generate dimension_intents and measure_intents with these fields
- If no, proceed to Step 1 for normal field mapping

Step 1: For each business term, find technical field from metadata
- Review available fields: Examine metadata.fields list carefully
- Identify semantic match: Find field with matching business meaning
  * Match category first: Which category does this term belong to?
  * Then match name: Search for fields within that category by name similarity
- Verify field existence: CRITICAL - technical_field MUST be exact name from metadata.fields
  * Check: Does this exact field name appear in metadata.fields?
  * If no exact match: Choose semantically closest field from metadata
- Double-check: Confirm selected field appears in metadata.fields list
  * Never use business term directly as technical_field
  * Never invent field names

Step 2: Determine Intent type for each entity
- For EACH entity, follow this decision tree:
  
  Question 1: Does this entity need time granularity function?
  - Check sub-question's date_field_functions dict
  - If entity appears in date_field_functions → Answer is YES
  - If entity does NOT appear in date_field_functions → Answer is NO
  
  If YES (needs time function):
    → Add to date_field_intents array
    → Include date_function field (YEAR/MONTH/QUARTER/WEEK/DAY)
    → DO NOT add to dimension_intents
    → STOP here for this entity
  
  If NO (does not need time function):
    → Continue to Question 2
  
  Question 2: Is this a numeric field needing aggregation?
  - Check metadata: Is field_data_type REAL or INTEGER?
  - Check sub-question: Is there aggregation specified?
  
  If YES (numeric with aggregation):
    → Add to measure_intents array
    → Include aggregation field (SUM/AVG/MIN/MAX/etc)
    → STOP here for this entity
  
  If NO (not numeric or no aggregation):
    → Add to dimension_intents array
    → Include aggregation ONLY if counting (COUNTD)
    → NEVER include date_function (this field does not exist in DimensionIntent)
    → STOP here for this entity

CRITICAL RULE: An entity can ONLY appear in ONE of these arrays:
- date_field_intents (if needs time function)
- measure_intents (if numeric with aggregation)
- dimension_intents (all other cases)

NEVER put date_function in dimension_intents - this field does not exist there!

Mapping rules:
1. **CRITICAL: technical_field MUST be exact field name from metadata.fields**
   - Verify field exists before using it
   - Use semantic understanding to find matching field
   - Never use business term directly as technical_field
   - Never invent field names not in metadata
2. **Match category first**: Identify the semantic category (geographic/temporal/product/customer/organizational/financial) of the business term
3. **Then match name**: Search for fields within that category by name similarity
4. **For COUNTD aggregation, prefer fine-grained fields**: When counting distinct values, choose fields with higher level values (more detailed granularity)
5. Prefer coarse level (1-2) for grouping dimensions unless fine detail needed"""
    
    def get_constraints(self) -> str:
        return """MUST NOT: use non-existent fields (verify field exists in metadata), modify TimeRange, add TopN without keywords
MUST: one subtask per sub-question, match category first, use exact field names from metadata"""
    
    def get_user_template(self) -> str:
        return """Original Question: {original_question}

Sub-Questions ({num_sub_questions} total):
{sub_questions}

Metadata Fields Available:
{metadata}

Dimension Hierarchy:
{dimension_hierarchy}

**CRITICAL**: Generate EXACTLY {num_sub_questions} subtask(s) - ONE for EACH sub-question.

For each subtask:
1. Use sub-question's "text" as question_text
2. Map business terms to technical fields:
   - Search metadata.fields for exact or similar field names
   - Use dimension_hierarchy to find category matches
   - technical_field MUST be exact field name from metadata
3. Generate Intents based on sub-question information
4. DO NOT invent fields or add filters not in sub-question"""
    
    def get_output_model(self) -> Type[BaseModel]:
        return QueryPlanningResult


class ProcessingTaskPrompt(VizQLPrompt):
    """Structured prompt for generating ProcessingSubTask"""
    
    def get_role(self) -> str:
        return """You are a data processing instruction generator who converts calculation requirements into structured processing instructions."""
    
    def get_task(self) -> str:
        return """Generate a ProcessingSubTask for the given sub-question with:

1. **processing_type**: Use the processing_type from sub-question
2. **source_tasks**: Convert depends_on_indices to task IDs (e.g., [0,1] → ["q1","q2"])
3. **calculation_formula**: Only for custom type (describe the calculation logic)

Note: Output field names will be automatically generated by DataProcessor based on processing_type and actual data.

Expected outcome: A complete ProcessingSubTask specification."""
    
    def get_specific_context(self) -> str:
        return """## Available Resources
- Sub-question: {sub_question}
- Processing type: {processing_type}
- Dependencies: {depends_on_indices}

## Processing Types
- yoy: Year-over-year comparison
- mom: Month-over-month comparison  
- growth_rate: Growth rate calculation
- percentage: Percentage/ratio calculation
- custom: Custom calculation (requires formula)"""
    
    def get_principles(self) -> str:
        return """## Generation Principles
1. **Source Tasks**: Convert indices to IDs (index 0 → "q1", index 1 → "q2")
2. **Formula**: Only provide for custom type (describe calculation logic in natural language)
3. **Metadata**: Leave empty unless specific needs
4. **Output Fields**: Not needed - DataProcessor will generate field names automatically"""
    
    def get_constraints(self) -> str:
        return """## Must NOT
- Reference invalid task IDs
- Provide formula for non-custom types
- Use empty source_tasks

## Requirements
- source_tasks must reference earlier sub-questions
- calculation_formula required only for custom type"""
    
    def get_output_requirements(self) -> str:
        return """## Quality Standards
- [ ] processing_type matches sub-question
- [ ] source_tasks correctly converted from indices
- [ ] calculation_formula provided if custom type
- [ ] No output_fields needed (auto-generated by DataProcessor)"""
    
    def get_user_template(self) -> str:
        return """Sub-question: {sub_question_text}
Processing Type: {processing_type}
Depends On Indices: {depends_on_indices}

Generate ProcessingSubTask specification."""
    
    def get_output_model(self) -> Type[BaseModel]:
        from tableau_assistant.src.models.query_plan import ProcessingSubTask
        return ProcessingSubTask


# Create prompt instances for easy import
TASK_PLANNER_PROMPT = TaskPlannerPrompt()
PROCESSING_TASK_PROMPT = ProcessingTaskPrompt()


# ============= 导出 =============

__all__ = [
    "TaskPlannerPrompt",
    "ProcessingTaskPrompt",
    "TASK_PLANNER_PROMPT",
    "PROCESSING_TASK_PROMPT",
]
