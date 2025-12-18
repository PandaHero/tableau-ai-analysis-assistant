# -*- coding: utf-8 -*-
"""
Insight Agent Prompts

按照 PROMPT_AND_MODEL_GUIDE.md 规范实现的 Prompt 模板。

核心原则：
- Prompt 告诉 LLM 如何思考（Role, Task, Domain Knowledge, Constraints）
- Schema（数据模型）告诉 LLM 输出什么（字段定义、XML 标签）
- 使用 VizQLPrompt 基类的 4 段式结构
- Output Model 自动注入 JSON Schema

双 LLM 协作模式（来自 insight-design.md）：
- 主持人 LLM：选择分块策略、决定分析顺序、累积洞察、决定早停
- 分析师 LLM：分析单个数据块、生成结构化洞察
"""

from typing import Type, List
from pydantic import BaseModel, Field, ConfigDict

from tableau_assistant.src.agents.base.prompt import VizQLPrompt
from tableau_assistant.src.core.models import (
    Insight,
    NextBiteDecision,
    InsightQuality,
)


# ============================================================================
# Output Models（输出模型）
# ============================================================================

class InsightListOutput(BaseModel):
    """
    洞察列表输出 - 分析师 LLM 输出
    
    <what>分析师 LLM 生成的洞察列表</what>
    """
    model_config = ConfigDict(extra="forbid")
    
    insights: List[Insight] = Field(
        description="""<what>洞察列表</what>
<when>ALWAYS required</when>
<how>2-5 个洞察，按重要性排序</how>"""
    )


class CoordinatorDecisionOutput(BaseModel):
    """
    主持人决策输出 - 主持人 LLM 输出
    
    <what>主持人 LLM 的决策，包含下一口决策和质量评估</what>
    
    <fill_order>
    1. next_bite_decision - 决定下一步
    2. insights_quality - 评估当前洞察质量
    </fill_order>
    """
    model_config = ConfigDict(extra="forbid")
    
    next_bite_decision: NextBiteDecision = Field(
        description="""<what>下一口决策</what>
<when>ALWAYS required</when>"""
    )
    
    insights_quality: InsightQuality = Field(
        description="""<what>洞察质量评估</what>
<when>ALWAYS required</when>"""
    )


# ============================================================================
# Prompt Classes（Prompt 类）
# ============================================================================

class CoordinatorPrompt(VizQLPrompt):
    """
    主持人 LLM Prompt
    
    职责（来自 insight-design.md）：
    1. 基于整体画像选择分块策略（已由 StatisticalAnalyzer 推荐）
    2. 决定分析顺序（优先级）
    3. 累积洞察，判断完成度
    4. 决定是否早停
    
    输出：NextBiteDecision + InsightQuality
    """
    
    def get_role(self) -> str:
        return "Analysis coordinator who orchestrates progressive data analysis, deciding what to analyze next and when to stop."
    
    def get_task(self) -> str:
        return """Evaluate current analysis progress and decide next steps.

Process:
1. Review accumulated insights -> Assess completeness
2. Evaluate remaining chunks -> Identify high-value targets
3. Decide: Continue or Stop -> If continue, which chunk next"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """**Think step by step:**

Step 1: Assess current insights completeness
- Does the accumulated insights answer the core question?
- What aspects are still missing?
- How confident are we in current findings?

Step 2: Evaluate remaining data chunks
- Which chunks have high potential value?
- Which chunks might fill the missing aspects?
- Are there anomaly chunks that need investigation?

Step 3: Make decision
- If completeness >= 0.8 and core question answered -> Stop
- If remaining chunks have low value -> Stop
- If important aspects missing -> Continue with highest value chunk

**Chunk Type Priority (for reference):**
- anomalies: Highest priority (unexpected patterns)
- cluster_*: High priority (natural groupings)
- pareto_top_20: High priority (key contributors)
- segment_*: Medium priority (time-based patterns)
- tail_data: Low priority (but may contain hidden gems)"""
    
    def get_constraints(self) -> str:
        return """MUST: Give clear decision with reasoning, estimate completeness accurately
MUST NOT: Analyze data directly (that's the analyst's job), continue indefinitely"""
    
    def get_user_template(self) -> str:
        return """## 原始问题
{question}

## 整体数据画像（Phase 1 统计分析结果）
- 分布类型：{distribution_type}
- 帕累托比率：{pareto_ratio}（Top 20% 贡献比例）
- 异常比例：{anomaly_ratio}
- 聚类数：{cluster_count}
- 推荐分块策略：{chunking_strategy}

## 已累积洞察
{accumulated_insights}

## 剩余数据块
{remaining_chunks}

## 已分析块数
{analyzed_count}"""
    
    def get_output_model(self) -> Type[BaseModel]:
        return CoordinatorDecisionOutput


class AnalystPrompt(VizQLPrompt):
    """
    分析师 LLM Prompt
    
    职责（来自 insight-design.md）：
    1. 分析单个数据块
    2. 结合整体画像和 top_n_summary 解读局部数据
    3. 生成结构化洞察
    
    输出：List[Insight]
    """
    
    def get_role(self) -> str:
        return "Data analyst who extracts insights from a single data chunk, using overall profile for context."
    
    def get_task(self) -> str:
        return """Analyze the current data chunk and extract meaningful insights.

**IMPORTANT: Focus primarily on the actual data sample provided below. The data profile is supplementary context only.**

Process:
1. **Analyze data sample first** -> Examine actual values, patterns, and relationships in the data
2. Understand chunk context -> What type of data is this?
3. Use profile as reference -> Compare findings with overall statistics
4. Extract insights -> Generate 2-5 structured insights based on data evidence"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """**Think step by step:**

Step 1: **Analyze the actual data sample (PRIMARY FOCUS)**
- Read through the data rows carefully
- Identify specific values, entities, and their relationships
- Look for patterns, outliers, and notable data points
- **Your insights MUST cite specific values from the data sample**

Step 2: Understand chunk context
- What type of data chunk is this? (anomalies, top_data, cluster, etc.)
- What is the business meaning of this data?

Step 3: Use profile as reference (SECONDARY)
- How does this chunk differ from overall statistics?
- Use max, q75, median from statistics as comparison baseline
- Calculate ratios: value / median, value / q75

Step 4: Compare with Top N data
- How does this data compare to top performers?
- Calculate ranking gaps (e.g., "5x of second place")
- Use pareto_ratio to explain concentration

Step 5: Extract insights
- Identify patterns: trend, anomaly, comparison, pattern
- **Each insight MUST reference specific data points from the sample**
- Avoid repeating existing insights

**Insight Quality Criteria:**
- **Data-driven: Insights must come from actual data sample, not just profile statistics**
- Specific: Include actual numbers and entity names from the data
- Evidenced: Every claim backed by data rows you can point to
- Actionable: Provide business-relevant findings
- Non-redundant: Check existing insights before adding"""
    
    def get_constraints(self) -> str:
        return """MUST: Write insights in Chinese, cite specific data points from the sample, provide evidence with actual values from data rows
MUST NOT: Repeat existing insights, invent data not in sample, rely solely on profile statistics without referencing actual data"""
    
    def get_user_template(self) -> str:
        return """## 原始问题
{question}

## 整体数据画像（用于对比）
- 分布类型：{distribution_type}
- 统计信息：{statistics}
- 帕累托比率：{pareto_ratio}

## Top N 数据摘要（用于排名对比）
{top_n_summary}

## 当前数据块
- 类型：{chunk_type}
- 行数：{row_count}
- 描述：{chunk_description}

数据样本：
{data_sample}

## 已有洞察（避免重复）
{existing_insights}"""
    
    def get_output_model(self) -> Type[BaseModel]:
        return InsightListOutput


class DirectAnalysisPrompt(VizQLPrompt):
    """
    直接分析 Prompt（用于小数据集 < 100 行）
    
    当数据量小时，不需要分块，直接分析全部数据。
    """
    
    def get_role(self) -> str:
        return "Data analysis expert who extracts business insights from structured data."
    
    def get_task(self) -> str:
        return """Analyze data and extract key insights.

Process: Understand context -> Profile data -> Identify patterns -> Generate insights"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """**Think step by step:**

Step 1: Understand the business context
- What question is the user trying to answer?
- What dimensions (categorical fields) are involved?
- What measures (numeric fields) are involved?

Step 2: Profile the data
- What is the data distribution? (normal, long-tail, bimodal)
- Are there any obvious patterns or outliers?
- What is the concentration? (top N contribution)

Step 3: Identify insight opportunities
- Time-based change? -> trend insight
- Outliers/unexpected values? -> anomaly insight
- Group comparisons? -> comparison insight
- Distribution characteristics? -> pattern insight

Step 4: Evaluate importance
- Business impact: How significant is this finding?
- Actionability: Can user act on this insight?
- Confidence: How certain are we based on data?

**Insight Quality Criteria:**
- Each insight must have concrete evidence with numbers
- Write insights in Chinese
- Generate 2-5 insights, prioritized by importance"""
    
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


# ============================================================================
# Prompt Instances（Prompt 实例）
# ============================================================================

COORDINATOR_PROMPT = CoordinatorPrompt()
ANALYST_PROMPT = AnalystPrompt()
DIRECT_ANALYSIS_PROMPT = DirectAnalysisPrompt()


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    # Output Models
    "InsightListOutput",
    "CoordinatorDecisionOutput",
    # Prompt Classes
    "CoordinatorPrompt",
    "AnalystPrompt",
    "DirectAnalysisPrompt",
    # Prompt Instances
    "COORDINATOR_PROMPT",
    "ANALYST_PROMPT",
    "DIRECT_ANALYSIS_PROMPT",
]
