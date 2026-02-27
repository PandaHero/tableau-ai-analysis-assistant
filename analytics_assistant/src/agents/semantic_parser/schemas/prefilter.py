# -*- coding: utf-8 -*-
"""
规则预处理相关数据模型

定义 RulePrefilter、FeatureExtractor、OutputValidator 等组件的数据结构。

模型分类：
1. 枚举类型：ComplexityType, ValidationErrorType
2. RulePrefilter：RuleTimeHint, MatchedComputation, PrefilterResult
3. FeatureExtractor：FeatureExtractionOutput
4. FieldRetriever：FieldRAGResult（使用 core 的 FieldCandidate）
5. OutputValidator：OutputValidationError, ValidationResult
"""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# 从 core 导入共享的 FieldCandidate
from analytics_assistant.src.core.schemas.field_candidate import FieldCandidate

# =============================================================================
# 枚举类型
# =============================================================================

class ComplexityType(str, Enum):
    """复杂度类型。
    
    用于标识查询的复杂度级别，影响 Schema 和 Prompt 的构建。
    """
    SIMPLE = "simple"           # 简单聚合
    RATIO = "ratio"             # 比率计算
    TIME_COMPARE = "time_compare"  # 同比/环比
    RANK = "rank"               # 排名
    SHARE = "share"             # 占比
    CUMULATIVE = "cumulative"   # 累计
    SUBQUERY = "subquery"       # 子查询

class ValidationErrorType(str, Enum):
    """验证错误类型。"""
    INVALID_FIELD = "invalid_field"           # 无效字段引用
    SYNTAX_ERROR = "syntax_error"             # 语法错误
    MISSING_REQUIRED = "missing_required"     # 缺少必需字段
    TYPE_MISMATCH = "type_mismatch"           # 类型不匹配

# =============================================================================
# RulePrefilter 相关模型
# =============================================================================

class RuleTimeHint(BaseModel):
    """规则时间提示。
    
    由 RulePrefilter 使用 TimeHintGenerator 生成，用于辅助 LLM 解析时间表达式。
    
    注意：与 intermediate.py 中的 TimeHint（dataclass）不同：
    - TimeHint: 简单的时间范围 (expression, start, end)
    - RuleTimeHint: 带置信度的时间提示，用于规则预处理
    """
    model_config = ConfigDict(extra="forbid")
    
    original_expression: str = Field(description="原始表达式（如 '上个月'）")
    hint_type: str = Field(description="提示类型（relative/absolute/range）")
    parsed_hint: str = Field(description="解析提示（如 '2024-01 到 2024-01'）")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="解析置信度")

class MatchedComputation(BaseModel):
    """匹配的计算种子。
    
    由 RulePrefilter 从 computation_seeds.py 中匹配得到。
    """
    model_config = ConfigDict(extra="forbid")
    
    seed_name: str = Field(description="种子名称（如 profit_rate）")
    display_name: str = Field(description="显示名称（如 利润率）")
    calc_type: str = Field(description="计算类型（如 RATIO）")
    formula: Optional[str] = Field(default=None, description="公式模板")
    keywords_matched: list[str] = Field(default_factory=list, description="匹配的关键词")

class PrefilterResult(BaseModel):
    """规则预处理结果。
    
    RulePrefilter 的输出，包含时间提示、计算种子、复杂度类型等。
    """
    model_config = ConfigDict(extra="forbid")
    
    time_hints: list[RuleTimeHint] = Field(
        default_factory=list, description="时间表达式解析提示"
    )
    matched_computations: list[MatchedComputation] = Field(
        default_factory=list, description="匹配的计算种子"
    )
    detected_complexity: list[ComplexityType] = Field(
        default_factory=list, description="检测到的复杂度类型"
    )
    detected_language: str = Field(default="zh", description="检测到的语言")
    match_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="规则匹配置信度 (0-1)"
    )
    low_confidence: bool = Field(default=False, description="是否低置信度")

# =============================================================================
# FeatureExtractor 相关模型
# =============================================================================

class FeatureExtractionOutput(BaseModel):
    """特征提取输出。
    
    FeatureExtractor 的输出，包含 LLM 验证后的字段需求。
    """
    model_config = ConfigDict(extra="forbid")
    
    required_measures: list[str] = Field(
        default_factory=list,
        description="需要的度量字段（业务术语，如 '利润', '销售额'）"
    )
    required_dimensions: list[str] = Field(
        default_factory=list,
        description="需要的维度字段（业务术语，如 '城市', '地区'）"
    )
    confirmed_time_hints: list[str] = Field(
        default_factory=list,
        description="确认后的时间提示"
    )
    confirmed_computations: list[str] = Field(
        default_factory=list,
        description="确认后的计算种子名称"
    )
    confirmation_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="LLM 确认置信度 (0-1)"
    )
    is_degraded: bool = Field(
        default=False,
        description="是否为降级模式（超时后使用规则结果）"
    )

# =============================================================================
# FieldRetriever 相关模型
# =============================================================================

# 注意：FieldCandidate 从 core/schemas/field_candidate.py 导入
# 不再重复定义，直接复用

class FieldRAGResult(BaseModel):
    """字段检索结果。
    
    包含 Top-K 候选字段及置信度分数，由主 LLM 从候选中选择正确字段。
    使用 core/schemas/field_candidate.py 中的 FieldCandidate。
    """
    model_config = ConfigDict(extra="forbid")
    
    measures: list[FieldCandidate] = Field(
        default_factory=list,
        description="度量字段候选列表，按置信度降序"
    )
    dimensions: list[FieldCandidate] = Field(
        default_factory=list,
        description="维度字段候选列表，按置信度降序"
    )
    time_fields: list[FieldCandidate] = Field(
        default_factory=list,
        description="时间字段候选列表，按置信度降序"
    )

# =============================================================================
# OutputValidator 相关模型
# =============================================================================

class OutputValidationError(BaseModel):
    """输出验证错误。"""
    model_config = ConfigDict(extra="forbid")
    
    error_type: ValidationErrorType = Field(description="错误类型")
    field_name: Optional[str] = Field(default=None, description="相关字段名")
    message: str = Field(description="错误消息")
    auto_correctable: bool = Field(default=False, description="是否可自动修正")
    suggested_correction: Optional[str] = Field(default=None, description="建议的修正")

class ValidationResult(BaseModel):
    """验证结果。
    
    OutputValidator 的输出，包含验证结果和可能的修正。
    """
    model_config = ConfigDict(extra="forbid")
    
    is_valid: bool = Field(description="是否验证通过")
    errors: list[OutputValidationError] = Field(
        default_factory=list, description="验证错误列表"
    )
    corrected_output: Optional[dict] = Field(
        default=None, description="自动修正后的输出"
    )
    needs_clarification: bool = Field(default=False, description="是否需要澄清")
    clarification_message: Optional[str] = Field(default=None, description="澄清消息")

__all__ = [
    # 枚举
    "ComplexityType",
    "ValidationErrorType",
    # RulePrefilter
    "RuleTimeHint",
    "MatchedComputation",
    "PrefilterResult",
    # FeatureExtractor
    "FeatureExtractionOutput",
    # FieldRetriever（FieldCandidate 从 core 导入）
    "FieldCandidate",
    "FieldRAGResult",
    # OutputValidator
    "OutputValidationError",
    "ValidationResult",
]
