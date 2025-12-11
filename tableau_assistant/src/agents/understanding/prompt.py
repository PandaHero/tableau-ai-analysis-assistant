"""
Understanding Agent Prompt（含原 Boost 功能）

设计原则（遵循 prompt-and-schema-design.md）：
- Prompt 教 LLM 如何思考（领域知识 + 推理步骤）
- Schema 告诉 LLM 输出什么（字段填写规则）
- Prompt 不包含具体字段名和关键词映射（这些在 Schema 中）
- 思考步骤与 Schema 中的 <decision_rule> 对应

架构变更：
- Boost Agent 已移除，功能合并到此 Agent
- 新增：问题分类（is_analysis_question）
- 新增：元数据获取（get_metadata 工具）

参考文档：
- .kiro/specs/agent-refactor-with-rag/design-appendix/prompt-and-schema-design.md
- .kiro/specs/agent-refactor-with-rag/design-appendix/agent-design.md
"""
from typing import Type
from pydantic import BaseModel

from tableau_assistant.src.agents.base.prompt import VizQLPrompt
from tableau_assistant.src.models.semantic.query import SemanticQuery


class UnderstandingPrompt(VizQLPrompt):
    """
    Understanding Agent 的 Prompt 模板（含原 Boost 功能）
    
    设计原则：
    - Prompt 教 LLM 如何思考（领域知识 + 推理步骤）
    - Schema 告诉 LLM 输出什么（字段填写规则）
    - Prompt 不包含具体字段名和关键词映射
    - 思考步骤与 Schema 中的 <decision_rule> 对应
    """
    
    def get_role(self) -> str:
        """
        定义 LLM 的角色（激活知识子空间）
        
        Target: ~20 words
        """
        return """Data analysis expert who classifies questions and extracts structured query intent.

Expertise: question classification, semantic understanding, entity extraction, time parsing, analysis detection"""
    
    def get_task(self) -> str:
        """
        定义任务（聚焦注意力）
        
        Target: ~50 words with implicit CoT
        """
        return """Classify question type and output SemanticQuery (pure semantic, no VizQL concepts).

Process: Classify question → Extract entities → Classify roles → Detect filters → Detect analysis → Output JSON"""
    
    def get_specific_domain_knowledge(self) -> str:
        """
        提供领域知识和思考步骤（HOW to think）
        
        注意：不包含具体字段名和关键词映射，这些在 Schema 的 <decision_rule> 中
        
        Target: ~200 words
        """
        return """**Think step by step:**

Step 1: Classify question type
- Is this a data analysis question or a non-analysis question?
- Analysis: queries about data, trends, comparisons, aggregations
- Non-analysis: greetings, help requests, system questions

Step 2: Extract business entities
- Identify all business terms mentioned in the question
- Use exact terms from question, not technical field names

Step 3: Classify entity roles
- Dimension: categorical field used for grouping
- Measure: numeric field used for aggregation
- Time dimension: date/time field with granularity

Step 4: Detect filters
- Time filters: absolute dates or relative time expressions
  - For absolute time filters, MUST specify both value AND granularity
  - granularity: year/quarter/month/week/day (tells DateParser how to interpret value)
  - Example: "2024年" → value="2024", granularity="year"
  - Example: "2024年3月" → value="2024-03", granularity="month"
- Set filters: specific values to include/exclude
- Quantitative filters: numeric ranges

Step 5: Detect analysis type
- Does the question imply derived calculations?
- Look for keywords indicating cumulative, ranking, percentage, comparison, or moving calculations

Step 6: Determine computation scope (multi-dimension only)
- When multiple dimensions exist, determine if calculation is per-group or across-all
- Single dimension queries do not need computation scope"""
    
    def get_constraints(self) -> str:
        """
        定义约束条件
        
        Target: 3-5 rules, ~10 words each
        """
        return """MUST:
- Use business terms from question (not technical field names)
- Follow <decision_rule> in Schema for each field
- Fill fields in order specified by <fill_order>

MUST NOT:
- Use VizQL concepts (addressing, partitioning, RUNNING_SUM)
- Invent entities not mentioned in question
- Set computation_scope for single dimension queries"""
    
    def get_user_template(self) -> str:
        return """Analyze this question and output SemanticQuery:

Question: {question}
Current date: {current_date}

Available technical fields (for reference only, DO NOT use these names in output):
{metadata_summary}

IMPORTANT: In your output, use the EXACT business terms from the question (e.g., "销售额", "省份"), 
NOT the technical field names from the metadata (e.g., "netamt", "group_nm").
The field mapping will be done in a later stage."""
    
    def get_output_model(self) -> Type[BaseModel]:
        return SemanticQuery


# Create prompt instance for easy import
UNDERSTANDING_PROMPT = UnderstandingPrompt()


__all__ = [
    "UnderstandingPrompt",
    "UNDERSTANDING_PROMPT",
]
