"""
FieldMapper Prompt - 字段映射 Agent 的 Prompt 定义

遵循 VizQLPrompt 规范，使用 4 段式结构。
"""
from typing import Type

from pydantic import BaseModel, Field
from typing import Optional, List

from tableau_assistant.src.agents.base.prompt import VizQLPrompt


class SingleSelectionResult(BaseModel):
    """
    LLM 字段选择输出模型
    
    <decision_tree>
    START
      ├─► 分析 business_term 语义
      │   ├─► 找到高匹配候选 → selected_field = 候选名, confidence >= 0.7
      │   └─► 无合适候选 → selected_field = null, confidence < 0.5
      └─► 填写 reasoning 解释选择原因
    END
    </decision_tree>
    
    <fill_order>
    1. business_term (ALWAYS - 复制输入)
    2. selected_field (ALWAYS - 选择或 null)
    3. confidence (ALWAYS - 0.0-1.0)
    4. reasoning (ALWAYS - 解释)
    </fill_order>
    """
    
    business_term: str = Field(
        description="""业务术语

<what>正在映射的业务术语</what>
<how>直接复制输入的业务术语</how>"""
    )
    
    selected_field: Optional[str] = Field(
        default=None,
        description="""选中的字段名

<what>最佳匹配的技术字段名</what>
<when>找到合适匹配时填写，否则为 null</when>
<how>从候选列表中选择语义最匹配的字段名</how>
<decision_rule>
- 语义高度匹配 → 填写字段名
- 无合适匹配 → null
</decision_rule>
<anti_patterns>
❌ 发明不在候选列表中的字段名
❌ 仅因关键词部分匹配就选择
</anti_patterns>"""
    )
    
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="""置信度

<what>选择的置信度分数</what>
<how>基于语义匹配程度评估</how>
<values>
- 0.9-1.0: 完全匹配（字段名/标题与术语相同）
- 0.7-0.9: 高度匹配（语义相近）
- 0.5-0.7: 中等匹配（可能正确）
- 0.0-0.5: 低匹配（不确定或无匹配）
</values>"""
    )
    
    reasoning: str = Field(
        description="""选择理由

<what>解释为什么选择该字段或为什么无匹配</what>
<how>简要说明语义匹配的依据</how>
<examples>
- "字段标题'销售额'与业务术语'销售'语义一致"
- "无候选字段与'客户满意度'语义相关"
</examples>"""
    )


class FieldMapperPrompt(VizQLPrompt):
    """
    字段映射 Agent 的 Prompt
    
    将业务术语映射到技术字段名，使用 RAG 候选 + LLM 精选策略。
    """
    
    def get_role(self) -> str:
        return """Field mapping expert who matches business terms to technical field names.

Expertise: semantic matching, field disambiguation, context-aware selection."""
    
    def get_task(self) -> str:
        return """Select the best matching technical field for the business term.

Process: Analyze term semantics → Compare candidates → Consider context → Select best match or null."""
    
    def get_specific_domain_knowledge(self) -> str:
        return """**Think step by step:**

Step 1: Analyze business term semantics
- What does the term mean in business context?
- Is it likely a dimension (categorical) or measure (numeric)?

Step 2: Compare with candidates
- Match field name and caption semantically
- Consider sample values as evidence
- Check data type compatibility

Step 3: Consider context
- Use question context for disambiguation
- Consider field role (dimension vs measure)

Step 4: Make decision
- High semantic match → select with high confidence
- Partial match → select with medium confidence
- No good match → set selected_field to null"""
    
    def get_constraints(self) -> str:
        return """MUST: Only select from provided candidates
MUST: Set selected_field to null if no candidate is a good match
MUST NOT: Invent field names not in candidates
MUST NOT: Select based only on keyword overlap without semantic understanding"""
    
    def get_user_template(self) -> str:
        return """Select the best matching field for this business term:

## Business Term
"{term}"

## Context
{context}

## Candidate Fields
{candidates}

Output JSON with selected_field, confidence, and reasoning."""
    
    def get_output_model(self) -> Type[BaseModel]:
        return SingleSelectionResult


# 单例 Prompt 实例
FIELD_MAPPER_PROMPT = FieldMapperPrompt()


__all__ = [
    "FieldMapperPrompt",
    "SingleSelectionResult",
    "FIELD_MAPPER_PROMPT",
]
