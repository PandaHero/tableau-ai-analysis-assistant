# -*- coding: utf-8 -*-
"""
Semantic Parser Output Models

核心输出模型定义：
- SemanticOutput: LLM 语义理解的完整输出
- SelfCheck: 自检结果（4 个置信度字段）
- What: 目标度量
- Where: 维度和筛选器
- DerivedComputation: 派生度量计算逻辑
"""
import uuid
from enum import Enum
from typing import List, Optional, Union
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from analytics_assistant.src.core.schemas.enums import HowType
from analytics_assistant.src.core.schemas.fields import MeasureField, DimensionField
from analytics_assistant.src.core.schemas.filters import (
    Filter,
    SetFilter,
    DateRangeFilter,
    NumericRangeFilter,
    TextMatchFilter,
    TopNFilter,
)

# Filter Union 类型（不使用 discriminator，让 Pydantic 按顺序尝试匹配）
FilterUnion = SetFilter | DateRangeFilter | NumericRangeFilter | TextMatchFilter | TopNFilter | Filter


# ═══════════════════════════════════════════════════════════════════════════
# 枚举定义
# ═══════════════════════════════════════════════════════════════════════════

class CalcType(str, Enum):
    """派生度量计算类型
    
    语义解析器输出的计算类型分类，用于指导 QueryAdapter 生成正确的查询。
    
    **何时需要派生计算**：
    - 查询基础度量（如"各地区销售额"）→ 不需要派生计算，直接用 what.measures
    - 多个度量间的公式计算（如"利润率"）→ 简单计算
    - 单个度量 + 维度上下文（如"销售额增长率"）→ 表计算或子查询
    
    分为两大类：
    1. 简单计算（多个基础度量间的公式计算）：
       - RATIO: 比率计算 (A/B)，如利润率 = 利润/销售额
       - SUM: 求和计算 (A+B)，如总成本 = 固定成本 + 可变成本
       - DIFFERENCE: 差值计算 (A-B)，如净利润 = 收入 - 成本
       - PRODUCT: 乘积计算 (A*B)，如总价 = 单价 * 数量
       - FORMULA: 自定义公式，如毛利率 = (销售额-成本)/销售额
    
    2. 复杂计算（单个度量 + 维度上下文，需要子查询或表计算）：
       - SUBQUERY: 子查询/聚合粒度控制（平台无关）
         - 语义：在不同于视图粒度的维度上进行聚合
         - 示例：客户首购日期、每个产品的平均订单金额
         - 适配器转换：
           - Tableau → LOD 表达式 (FIXED/INCLUDE/EXCLUDE，根据上下文决定)
           - SQL → 子查询 (SELECT ... FROM (SELECT ...))
       - TABLE_CALC_RANK: 排名计算
       - TABLE_CALC_PERCENTILE: 百分位计算
       - TABLE_CALC_DIFFERENCE: 差异计算（同比/环比绝对值）
       - TABLE_CALC_PERCENT_DIFF: 百分比差异（同比/环比增长率）
       - TABLE_CALC_PERCENT_OF_TOTAL: 占比计算（市场份额等）
       - TABLE_CALC_RUNNING: 累计计算（YTD等）
       - TABLE_CALC_MOVING: 移动计算（移动平均等）
    
    示例：
    - "各地区销售额" → 无派生计算，what.measures: [销售额]
    - "利润率" → RATIO，formula: "[利润]/[销售额]"
    - "总成本" → SUM，formula: "[固定成本]+[可变成本]"
    - "销售额增长率" → TABLE_CALC_PERCENT_DIFF（单个度量 + 时间维度）
    - "市场份额" → TABLE_CALC_PERCENT_OF_TOTAL（单个度量 + 分区维度）
    - "每个客户的首次购买日期" → SUBQUERY（适配器决定具体实现）
    
    **SUBQUERY 与平台适配**：
    语义解析器只输出 SUBQUERY 类型，不指定具体的 LOD 类型。
    QueryAdapter 根据以下规则决定具体实现：
    
    Tableau LOD 类型选择规则：
    - subquery_dimensions 与视图维度无关 → FIXED
    - subquery_dimensions 是视图维度的超集 → INCLUDE  
    - subquery_dimensions 是视图维度的子集 → EXCLUDE
    """
    # 简单计算（多个基础度量间的公式）
    RATIO = "RATIO"                              # 比率: A/B
    SUM = "SUM"                                  # 求和: A+B
    DIFFERENCE = "DIFFERENCE"                    # 差值: A-B
    PRODUCT = "PRODUCT"                          # 乘积: A*B
    FORMULA = "FORMULA"                          # 自定义公式: 复合计算
    
    # 子查询/聚合粒度控制（平台无关，适配器决定具体实现）
    SUBQUERY = "SUBQUERY"                        # 子查询（Tableau: LOD, SQL: 子查询）
    
    # 表计算（单个度量 + 维度上下文）
    TABLE_CALC_RANK = "TABLE_CALC_RANK"          # 排名
    TABLE_CALC_PERCENTILE = "TABLE_CALC_PERCENTILE"  # 百分位
    TABLE_CALC_DIFFERENCE = "TABLE_CALC_DIFFERENCE"  # 差异（绝对值）
    TABLE_CALC_PERCENT_DIFF = "TABLE_CALC_PERCENT_DIFF"  # 百分比差异（增长率）
    TABLE_CALC_PERCENT_OF_TOTAL = "TABLE_CALC_PERCENT_OF_TOTAL"  # 占比
    TABLE_CALC_RUNNING = "TABLE_CALC_RUNNING"    # 累计
    TABLE_CALC_MOVING = "TABLE_CALC_MOVING"      # 移动计算


class ClarificationSource(str, Enum):
    """澄清请求来源
    
    用于追踪澄清请求的发起组件：
    - SEMANTIC_UNDERSTANDING: 语义理解阶段（问题信息不完整）
    - FILTER_VALIDATOR: 筛选值验证阶段（筛选值不匹配）
    """
    SEMANTIC_UNDERSTANDING = "semantic_understanding"
    FILTER_VALIDATOR = "filter_validator"


# ═══════════════════════════════════════════════════════════════════════════
# 派生度量计算模型
# ═══════════════════════════════════════════════════════════════════════════

class DerivedComputation(BaseModel):
    """派生度量计算定义
    
    描述如何从基础度量计算派生指标。这是语义解析器的中间表示，
    QueryAdapter 会将其转换为具体的 VizQL 计算字段。
    
    **判断逻辑**：
    - 多个度量间的计算 → RATIO（简单计算）
    - 单个度量 + 维度上下文 → 表计算或子查询
    
    示例：
    - 利润率: name="profit_rate", formula="[利润]/[销售额]", calc_type=RATIO
      （两个度量：利润、销售额）
    - 销售额增长率: name="sales_growth", calc_type=TABLE_CALC_PERCENT_DIFF
      （单个度量：销售额，需要时间维度）
    - 市场份额: name="market_share", calc_type=TABLE_CALC_PERCENT_OF_TOTAL
      （单个度量：销售额，需要分区维度）
    - 客户首购: name="first_purchase", calc_type=SUBQUERY
      （单个度量：订单日期，固定到客户维度）
      
    **SUBQUERY 类型说明**：
    当 calc_type=SUBQUERY 时，语义解析器只指定：
    - subquery_dimensions: 子查询的聚合维度
    - subquery_aggregation: 聚合函数（MIN/MAX/SUM/AVG/COUNT）
    
    QueryAdapter 根据 subquery_dimensions 与视图维度的关系，
    决定具体的实现方式（Tableau: FIXED/INCLUDE/EXCLUDE, SQL: 子查询）
    """
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(
        description="计算名称（英文标识符），如 profit_rate"
    )
    display_name: str = Field(
        description="显示名称（用户可见），如 利润率"
    )
    formula: Optional[str] = Field(
        default=None,
        description="计算公式（仅 RATIO/GROWTH 类型需要），使用 [字段名] 引用字段"
    )
    calc_type: CalcType = Field(
        description="计算类型"
    )
    base_measures: List[str] = Field(
        default_factory=list,
        description="基础度量列表，如 ['利润', '销售额']"
    )
    # 子查询特有字段（平台无关）
    subquery_dimensions: Optional[List[str]] = Field(
        default=None,
        description="子查询聚合维度（仅 SUBQUERY 类型需要），如 ['客户ID']"
    )
    subquery_aggregation: Optional[str] = Field(
        default=None,
        description="子查询聚合函数（仅 SUBQUERY 类型需要）：MIN/MAX/SUM/AVG/COUNT"
    )
    # 表计算特有字段
    partition_by: Optional[List[str]] = Field(
        default=None,
        description="表计算分区维度（仅 TABLE_CALC_* 类型需要）"
    )
    relative_to: Optional[str] = Field(
        default=None,
        description="差异计算参考点：PREVIOUS/NEXT/FIRST/LAST（仅差异类型需要）"
    )
    
    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name 不能为空")
        return v.strip()


# ═══════════════════════════════════════════════════════════════════════════
# 自检模型
# ═══════════════════════════════════════════════════════════════════════════

class SelfCheck(BaseModel):
    """LLM 自检结果
    
    包含 4 个置信度字段，用于评估语义理解的可靠性。
    当任一置信度低于阈值（0.7）时，potential_issues 应非空。
    """
    model_config = ConfigDict(extra="forbid")
    
    field_mapping_confidence: float = Field(
        ge=0.0, le=1.0,
        description="字段映射置信度：字段名是否正确匹配到数据模型"
    )
    time_range_confidence: float = Field(
        ge=0.0, le=1.0,
        description="时间范围置信度：时间表达式是否正确解析"
    )
    computation_confidence: float = Field(
        ge=0.0, le=1.0,
        description="计算逻辑置信度：派生度量公式是否正确"
    )
    overall_confidence: float = Field(
        ge=0.0, le=1.0,
        description="整体置信度：综合评估"
    )
    potential_issues: List[str] = Field(
        default_factory=list,
        description="潜在问题列表，当任一置信度 < 0.7 时应非空"
    )


# ═══════════════════════════════════════════════════════════════════════════
# What/Where 模型
# ═══════════════════════════════════════════════════════════════════════════

class What(BaseModel):
    """目标度量（What to measure）
    
    描述用户想要查询的度量指标。
    """
    model_config = ConfigDict(extra="forbid")
    
    measures: List[MeasureField] = Field(
        default_factory=list,
        description="基础度量列表"
    )


class Where(BaseModel):
    """维度和筛选器（Where to slice）
    
    描述数据的切分维度和筛选条件。
    """
    model_config = ConfigDict(extra="forbid")
    
    dimensions: List[DimensionField] = Field(
        default_factory=list,
        description="分组维度列表"
    )
    filters: List[FilterUnion] = Field(
        default_factory=list,
        description="筛选条件列表"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 核心输出模型
# ═══════════════════════════════════════════════════════════════════════════

class SemanticOutput(BaseModel):
    """LLM 语义理解输出
    
    语义解析器的核心输出模型，包含：
    - 追踪字段：query_id, parent_query_id（用于调试和错误修正追踪）
    - 核心输出：restated_question, what, where, computations
    - 流程控制：needs_clarification, clarification_question
    - 自检结果：self_check
    
    示例：
    用户问题："上个月各地区的利润率是多少？"
    输出：
    - restated_question: "查询上个月（2024年12月）各地区的利润率"
    - what.measures: [利润, 销售额]
    - where.dimensions: [地区]
    - where.filters: [日期 IN 上个月]
    - computations: [{name: "profit_rate", formula: "[利润]/[销售额]", calc_type: RATIO}]
    """
    model_config = ConfigDict(extra="forbid")
    
    # ========== 追踪字段 ==========
    query_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="查询唯一标识，用于追踪和调试"
    )
    parent_query_id: Optional[str] = Field(
        default=None,
        description="如果是错误修正，指向原查询的 query_id"
    )
    
    # ========== 核心输出字段 ==========
    restated_question: str = Field(
        description="完整独立的问题描述，不依赖对话历史即可理解"
    )
    what: What = Field(
        default_factory=What,
        description="目标度量"
    )
    where: Where = Field(
        default_factory=Where,
        description="维度和筛选器"
    )
    how_type: HowType = Field(
        default=HowType.SIMPLE,
        description="计算复杂度：SIMPLE=简单聚合/比率, COMPLEX=需要子查询或表计算"
    )
    computations: List[DerivedComputation] = Field(
        default_factory=list,
        description="派生度量计算逻辑列表"
    )
    
    # ========== 流程控制字段 ==========
    needs_clarification: bool = Field(
        default=False,
        description="是否需要用户澄清"
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="澄清问题（当 needs_clarification=True 时）"
    )
    clarification_options: Optional[List[str]] = Field(
        default=None,
        description="澄清选项列表（供用户选择）"
    )
    clarification_source: Optional[ClarificationSource] = Field(
        default=None,
        description="澄清请求来源（用于追踪）"
    )
    
    # ========== 自检结果 ==========
    self_check: SelfCheck = Field(
        description="LLM 自检结果"
    )
    
    # ========== 调试字段 ==========
    parsing_warnings: List[str] = Field(
        default_factory=list,
        description="解析过程中的警告信息，用于调试"
    )
    
    @field_validator("restated_question")
    @classmethod
    def restated_question_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("restated_question 不能为空")
        return v.strip()


__all__ = [
    # Enums
    "CalcType",
    "ClarificationSource",
    # Models
    "DerivedComputation",
    "SelfCheck",
    "What",
    "Where",
    "SemanticOutput",
]
