"""
Insight Agent Prompts

按照 PROMPT_AND_MODEL_GUIDE.md 规范实现的 Prompt 模板。

核心原则：
- Prompt 教 LLM 如何思考（Role, Task, Domain Knowledge, Constraints）
- Schema（数据模型）告诉 LLM 输出什么（字段定义用 XML 标签）
- 使用 VizQLPrompt 基类的 4 段式结构
- Output Model 自动注入 JSON Schema

渐进式分析（来自 progressive-insight-analysis/design.md）：
- AI 驱动的洞察累积
- AI 驱动的下一口选择
- 早停机制
"""

from typing import Type, List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict

from tableau_assistant.src.agents.base.prompt import VizQLPrompt


# ============================================================================
# Output Models（输出模型）
# 
# 按照 PROMPT_AND_MODEL_GUIDE.md 规范：
# - 使用 XML 标签描述字段
# - 包含 decision_tree、fill_order、examples、anti_patterns
# ============================================================================

class InsightOutput(BaseModel):
    """
    单个洞察输出
    
    <what>LLM 生成的单个洞察</what>
    
    <decision_tree>
    START
      │
      ├─► type = ? (ALWAYS fill first)
      │   ├─► trend: 数据随时间变化
      │   ├─► anomaly: 发现异常值/离群点
      │   ├─► comparison: 不同组之间对比
      │   └─► pattern: 数据分布/规律
      │
      ├─► title = ? (ALWAYS fill, 中文)
      ├─► description = ? (ALWAYS fill, 中文)
      ├─► importance = ? (ALWAYS fill, 0.0-1.0)
      ├─► evidence = ? (IF supporting data exists)
      └─► related_columns = ? (IF columns are relevant)
    END
    </decision_tree>
    """
    model_config = ConfigDict(extra="forbid")
    
    type: Literal["trend", "anomaly", "comparison", "pattern"] = Field(
        description="""<what>洞察类型</what>
<when>ALWAYS required (fill first)</when>

<decision_rule>
- 数据随时间变化 → trend
- 发现异常值/离群点 → anomaly
- 不同组之间对比 → comparison
- 数据分布/规律 → pattern
</decision_rule>"""
    )
    
    title: str = Field(
        description="""<what>洞察标题（中文）</what>
<when>ALWAYS required</when>
<how>一句话概括发现</how>"""
    )
    
    description: str = Field(
        description="""<what>洞察描述（中文）</what>
<when>ALWAYS required</when>
<how>详细解释发现</how>"""
    )
    
    importance: float = Field(
        ge=0.0, le=1.0,
        description="""<what>重要性评分</what>
<when>ALWAYS required</when>

<values>
- 0.8-1.0: 高重要性（关键发现）
- 0.5-0.8: 中等重要性
- 0.0-0.5: 低重要性
</values>"""
    )
    
    evidence: Optional[Dict[str, Any]] = Field(
        default=None,
        description="""<what>支持证据</what>
<when>IF supporting data exists</when>
<how>Dict with key metrics/values</how>"""
    )
    
    related_columns: List[str] = Field(
        default_factory=list,
        description="""<what>相关列</what>
<when>IF columns are relevant</when>"""
    )


class InsightListOutput(BaseModel):
    """
    洞察列表输出（用于直接分析和块分析）
    
    <what>LLM 生成的洞察列表</what>
    """
    model_config = ConfigDict(extra="forbid")
    
    insights: List[InsightOutput] = Field(
        description="""<what>洞察列表</what>
<when>ALWAYS required</when>
<how>2-5 个洞察，按重要性排序</how>"""
    )


class NextBiteDecisionOutput(BaseModel):
    """
    下一口决策输出
    
    <what>AI 决定下一步分析哪个数据块</what>
    
    <design_note>
    基于"AI 宝宝吃饭"理念：
    - 吃了辣的 → 下一口选择清淡的
    - 发现第一名 → 分析为什么第一
    - 发现异常 → 深入调查
    - 吃饱了 → 早停
    </design_note>
    """
    model_config = ConfigDict(extra="forbid")
    
    should_continue: bool = Field(
        description="""<what>是否继续分析</what>
<when>ALWAYS required</when>

<decision_rule>
- 问题已充分回答 → False
- 洞察质量高且完整 → False
- 还有重要数据未分析 → True
- 发现异常需要深入 → True
</decision_rule>"""
    )
    
    next_chunk_type: Optional[Literal["anomalies", "top_data", "mid_data", "low_data", "tail_data"]] = Field(
        default=None,
        description="""<what>下一个要分析的块类型</what>
<when>IF should_continue is True</when>

<values>
- anomalies: 异常值数据
- top_data: Top 100 行
- mid_data: 101-500 行
- low_data: 501-1000 行
- tail_data: 1000+ 行
</values>"""
    )
    
    reason: str = Field(
        description="""<what>决策原因（中文）</what>
<when>ALWAYS required</when>"""
    )
    
    eating_strategy: str = Field(
        description="""<what>吃饭策略说明（中文）</what>
<when>ALWAYS required</when>

<examples>
- "发现第一名，分析为什么第一"
- "吃了辣的，选择清淡的"
- "发现异常，深入调查"
- "吃饱了，该停了"
</examples>"""
    )
    
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="""<what>决策置信度</what>
<when>ALWAYS required</when>"""
    )


class InsightQualityOutput(BaseModel):
    """
    洞察质量评估输出
    
    <what>评估当前洞察是否足够回答问题</what>
    """
    model_config = ConfigDict(extra="forbid")
    
    completeness: float = Field(
        ge=0.0, le=1.0,
        description="""<what>完整度（是否充分回答了问题）</what>"""
    )
    
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="""<what>置信度</what>"""
    )
    
    need_more_data: bool = Field(
        description="""<what>是否需要更多数据</what>"""
    )
    
    question_answered: bool = Field(
        description="""<what>核心问题是否已回答</what>"""
    )


class AIAnalysisOutput(BaseModel):
    """
    AI 驱动分析的完整输出
    
    <what>包含新洞察、下一口决策、质量评估</what>
    
    <fill_order>
    1. new_insights - 先提取洞察
    2. next_bite_decision - 再决定下一步
    3. insights_quality - 最后评估质量
    </fill_order>
    """
    model_config = ConfigDict(extra="forbid")
    
    new_insights: List[InsightOutput] = Field(
        description="""<what>新发现的洞察</what>
<when>ALWAYS required (may be empty)</when>"""
    )
    
    next_bite_decision: NextBiteDecisionOutput = Field(
        description="""<what>下一口决策</what>
<when>ALWAYS required</when>"""
    )
    
    insights_quality: InsightQualityOutput = Field(
        description="""<what>洞察质量评估</what>
<when>ALWAYS required</when>"""
    )


# ============================================================================
# Prompt Classes（Prompt 类）
# 
# 按照 VizQLPrompt 基类的 4 段式结构：
# - get_role(): 角色定义
# - get_task(): 任务描述
# - get_specific_domain_knowledge(): 领域知识
# - get_constraints(): 约束条件
# - get_user_template(): 用户输入模板
# - get_output_model(): 输出模型
# ============================================================================

class InsightAnalysisPrompt(VizQLPrompt):
    """
    洞察分析 Prompt（用于直接分析小数据集）
    """
    
    def get_role(self) -> str:
        return "Data analysis expert who extracts business insights from structured data."
    
    def get_task(self) -> str:
        return """Analyze data and extract key insights.

Process: Understand context → Profile data → Identify patterns → Generate insights"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """**Think step by step:**

Step 1: Understand the business context
- What question is the user trying to answer?
- What dimensions (categorical fields) are involved?
- What measures (numeric fields) are involved?

Step 2: Profile the data
- What is the data distribution?
- Are there any obvious patterns or outliers?

Step 3: Identify insight opportunities
- Time-based change? → trend
- Outliers/unexpected values? → anomaly
- Group comparisons? → comparison
- Distribution characteristics? → pattern

Step 4: Evaluate importance
- Business impact: How significant?
- Actionability: Can user act on this?
- Confidence: How certain?"""
    
    def get_constraints(self) -> str:
        return """MUST: Generate 2-5 insights, provide evidence, write in Chinese
MUST NOT: Invent data not present, repeat insights"""
    
    def get_user_template(self) -> str:
        return """## Dataset
- Total Rows: {row_count}
- Columns: {columns}

## Data Sample
{data}

## Analysis Context
- Question: {question}
- Dimensions: {dimensions}
- Measures: {measures}"""
    
    def get_output_model(self) -> Type[BaseModel]:
        return InsightListOutput


class ChunkAnalysisPrompt(VizQLPrompt):
    """
    块分析 Prompt（用于渐进式分析中的单块分析）
    """
    
    def get_role(self) -> str:
        return "Data analysis expert for progressive chunk-by-chunk analysis."
    
    def get_task(self) -> str:
        return """Analyze current data chunk and extract insights, avoiding duplicates.

Process: Review previous → Analyze chunk → Extract new insights"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """**Think step by step:**

Step 1: Review previous insights
- What has already been discovered?
- What should NOT be repeated?

Step 2: Analyze current chunk
- What patterns exist in this data?
- Any anomalies or unexpected values?

Step 3: Extract NEW insights only
- Is this information new or duplicate?
- Does it add value beyond existing insights?"""
    
    def get_constraints(self) -> str:
        return """MUST: Generate 2-5 NEW insights, write in Chinese
MUST NOT: Repeat previous insights, invent data"""
    
    def get_user_template(self) -> str:
        return """## Data Chunk
- Name: {chunk_name}
- Rows: {row_count}
- Columns: {columns}

## Data Sample
{data_sample}

## Analysis Context
- Question: {question}
- Dimensions: {dimensions}
- Measures: {measures}

## Already Discovered (avoid duplicates)
{previous_insights}"""
    
    def get_output_model(self) -> Type[BaseModel]:
        return InsightListOutput


class AIAnalysisPrompt(VizQLPrompt):
    """
    AI 驱动分析 Prompt（用于渐进式分析的核心循环）
    
    核心理念（来自设计文档）：
    1. AI 分析当前数据块，提取洞察
    2. AI 累积洞察（理解含义，避免重复）
    3. AI 根据累积的洞察，智能选择下一口吃什么
    """
    
    def get_role(self) -> str:
        return "Data analysis expert for progressive insight extraction using 'AI baby eating' methodology."
    
    def get_task(self) -> str:
        return """Complete three tasks:
1. Analyze current chunk → Extract insights
2. Accumulate smartly → Avoid duplicates
3. Decide next bite → Or early stop

Process: Analyze → Accumulate → Decide next"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """**"AI 宝宝吃饭"理念：**
- 吃了辣的 → 下一口选择清淡的
- 发现第一名 → 分析为什么第一
- 发现异常 → 深入调查
- 吃饱了 → 该停了

**数据块类型：**
- anomalies: 异常值（可能是问题也可能是宝藏）
- top_data: Top 100 行（排名最高）
- mid_data: 101-500 行（中间层）
- low_data: 501-1000 行（较低层）
- tail_data: 1000+ 行（尾部，可能有边缘案例）

**洞察累积规则：**
- 冲突 → 标记为局部洞察，不覆盖全局事实
- 补充 → 合并到相关洞察中
- 重复 → 忽略，不重复记录

**下一口选择场景：**
- 场景 1：发现第一名 → 分析为什么第一
- 场景 2：发现异常 → 深入调查
- 场景 3：吃饱了 → 早停
- 场景 4：剩菜可能有宝藏 → 看看 tail_data"""
    
    def get_constraints(self) -> str:
        return """MUST: Write insights in Chinese, give clear next decision
MUST NOT: Repeat existing insights, invent data not in sample"""
    
    def get_user_template(self) -> str:
        return """## 原始问题
{question}

## 已有洞察（前面吃的菜）
{accumulated_insights}

## 当前数据块（刚吃的这一口）
- 类型：{chunk_type}
- 优先级：{priority}
- 行数：{row_count}
- 描述：{chunk_description}

数据样本：
{data_sample}

## 剩余数据块（还有哪些菜可以吃）
{remaining_chunks}"""
    
    def get_output_model(self) -> Type[BaseModel]:
        return AIAnalysisOutput


# ============================================================================
# Prompt Instances（Prompt 实例）
# ============================================================================

INSIGHT_ANALYSIS_PROMPT = InsightAnalysisPrompt()
CHUNK_ANALYSIS_PROMPT = ChunkAnalysisPrompt()
AI_ANALYSIS_PROMPT = AIAnalysisPrompt()


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    # Output Models
    "InsightOutput",
    "InsightListOutput",
    "NextBiteDecisionOutput",
    "InsightQualityOutput",
    "AIAnalysisOutput",
    # Prompt Classes
    "InsightAnalysisPrompt",
    "ChunkAnalysisPrompt",
    "AIAnalysisPrompt",
    # Prompt Instances
    "INSIGHT_ANALYSIS_PROMPT",
    "CHUNK_ANALYSIS_PROMPT",
    "AI_ANALYSIS_PROMPT",
]
