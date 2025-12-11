"""
字段映射相关数据模型

这些模型用于 FieldMapper Agent 的 LLM 结构化输出。
"""

from typing import List, Optional
from pydantic import BaseModel, Field


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


class BatchSelectionResult(BaseModel):
    """
    批量字段选择结果
    
    用于 LLM 批量处理多个业务术语到技术字段的映射。
    """
    mappings: List[SingleSelectionResult] = Field(
        description="每个业务术语的映射结果"
    )
