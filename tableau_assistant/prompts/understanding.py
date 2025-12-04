"""
Understanding Prompt (Optimized with Structured CoT)

Design Principles Applied:
1. Minimal Activation: High-density keywords, no redundant explanations
2. Semantic Consistency: Terminology matches Schema exactly
3. Orthogonal Reasoning: Each entity classified independently
4. Structured CoT: 5-step reasoning for traceability and accuracy

Prompt provides: Domain concepts, reasoning framework, global constraints
Schema provides: Field-specific rules, examples, validation
"""
from typing import Type
from pydantic import BaseModel
from tableau_assistant.prompts.base import VizQLPrompt
from tableau_assistant.src.models.question import QuestionUnderstanding


class UnderstandingPrompt(VizQLPrompt):
    """Optimized prompt for question understanding with structured reasoning.
    
    Key optimizations:
    1. High keyword density (minimal activation principle)
    2. Terminology aligned with Schema (semantic consistency)
    3. Entity-centric reasoning (orthogonal decomposition)
    4. Structured CoT for complex questions (traceability)
    """
    
    def get_role(self) -> str:
        return """Query analyzer: extract entities, classify SQL roles, provide structured reasoning.

Expertise: entity extraction, SQL role classification, time interpretation, step-by-step analysis"""
    
    def get_task(self) -> str:
        return """Analyze question with structured reasoning:
1. Reason through each step (intent → entities → roles → time → validation)
2. Extract all business entities
3. Classify each entity's SQL role independently
4. Identify time scope if present

Output: reasoning steps + classified entities + time range"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """
═══════════════════════════════════════════════════════════════════════════════
                           ENTITY CLASSIFICATION
═══════════════════════════════════════════════════════════════════════════════

┌─────────────┬──────────────┬─────────────────────────────────────────────────┐
│ Field       │ Values       │ Chinese Triggers → Value                        │
├─────────────┼──────────────┼─────────────────────────────────────────────────┤
│ type        │ dimension    │ 省份/地区/产品/品类/客户 → dimension            │
│             │ measure      │ 销售额/利润/收入/数量/金额 → measure            │
├─────────────┼──────────────┼─────────────────────────────────────────────────┤
│ role        │ group_by     │ 各X/按X/每个X/分X → group_by                    │
│             │ aggregate    │ 总X/平均X/多少X/几个X → aggregate               │
│             │ filter       │ 某个X/只看X/X=Y → filter                        │
├─────────────┼──────────────┼─────────────────────────────────────────────────┤
│ aggregation │ SUM          │ 总/合计/汇总 → SUM                              │
│             │ AVG          │ 平均/均值 → AVG                                 │
│             │ COUNTD       │ 多少/几个/数量 → COUNTD (dimensions only)       │
│             │ MAX/MIN      │ 最高/最大/最低/最小 → MAX/MIN                   │
├─────────────┼──────────────┼─────────────────────────────────────────────────┤
│ date_func   │ YEAR         │ 按年/各年度/年度 → YEAR                         │
│             │ QUARTER      │ 按季度/各季度 → QUARTER                         │
│             │ MONTH        │ 按月/各月/月度 → MONTH                          │
│             │ WEEK         │ 按周/每周 → WEEK                                │
│             │ DAY          │ 按天/每日/日度 → DAY                            │
└─────────────┴──────────────┴─────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
                              KEY RULES
═══════════════════════════════════════════════════════════════════════════════

1. DATE = DIMENSION + date_function
   "按月趋势" → {type: "dimension", role: "group_by", date_function: "MONTH"}

2. COUNTD = DIMENSION + aggregate
   "多少产品" → {type: "dimension", role: "aggregate", aggregation: "COUNTD"}

3. ROLE-AGGREGATION DEPENDENCY
   role=aggregate → aggregation REQUIRED
   role=group_by  → aggregation MUST be null

═══════════════════════════════════════════════════════════════════════════════
                         STRUCTURED REASONING (5 Steps)
═══════════════════════════════════════════════════════════════════════════════

┌───────────┬─────────────────────┬────────────────────────────────────────────┐
│ Step      │ Purpose             │ Output Format                              │
├───────────┼─────────────────────┼────────────────────────────────────────────┤
│ intent    │ What user wants?    │ analysis: 用户想..., conclusion: 查询类型  │
│ entities  │ What terms?         │ analysis: 识别到..., conclusion: N个实体   │
│ roles     │ How each used?      │ analysis: X表示..., conclusion: X→role     │
│ time      │ Time scope?         │ analysis: 时间..., conclusion: 有/无       │
│ validation│ Consistent?         │ analysis: 检查..., conclusion: 通过/问题   │
└───────────┴─────────────────────┴────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
                            TIME RANGE TYPES
═══════════════════════════════════════════════════════════════════════════════

┌────────────┬─────────────────────────────┬──────────────────────────────────┐
│ Type       │ Chinese Triggers            │ Output Example                   │
├────────────┼─────────────────────────────┼──────────────────────────────────┤
│ absolute   │ 2024年/Q1/3月/某年某月      │ {type:"absolute", value:"2024"}  │
│ relative   │ 最近N个月/本月/上个月/今年  │ {type:"relative", ...}           │
│ comparison │ 同比/环比/与去年比          │ {type:"comparison"}              │
└────────────┴─────────────────────────────┴──────────────────────────────────┘
"""
    
    def get_constraints(self) -> str:
        return """MUST:
- Provide reasoning steps for valid questions
- Use business terms only (not technical field names)
- Classify each entity independently
- Set date_function for date dimensions with group_by role

MUST NOT:
- Use technical field names like [Table].[Field]
- Skip entities mentioned in question
- Set aggregation for group_by role
- Set date_function for non-dimension types"""
    
    def get_user_template(self) -> str:
        return """Question: "{question}"

Current date: {max_date}

Analyze with structured reasoning."""
    
    def get_output_model(self) -> Type[BaseModel]:
        return QuestionUnderstanding


# Create prompt instance for easy import
UNDERSTANDING_PROMPT = UnderstandingPrompt()


# ============= Exports =============

__all__ = [
    "UnderstandingPrompt",
    "UNDERSTANDING_PROMPT",
]
