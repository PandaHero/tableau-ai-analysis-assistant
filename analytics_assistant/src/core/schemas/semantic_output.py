# -*- coding: utf-8 -*-
"""
语义解析核心输出模型

从 agents/semantic_parser/schemas/output.py 迁移到 core/schemas/，
修正依赖方向：platform/ 和 api/ 应从 core/ 导入，而非从 agents/ 导入。

核心输出模型定义：
- SemanticOutput: LLM 语义理解的完整输出
- SelfCheck: 自检结果（4 个置信度字段）
- What: 目标度量
- Where: 维度和筛选器
- DerivedComputation: 派生度量计算逻辑
"""
import json as json_module
import uuid
from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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

# Filter Union 类型
FilterUnion = SetFilter | DateRangeFilter | NumericRangeFilter | TextMatchFilter | TopNFilter | Filter

# ═══════════════════════════════════════════════════════════════════════════
# 枚举定义
# ═══════════════════════════════════════════════════════════════════════════

class CalcType(str, Enum):
    """派生度量计算类型

    分为两大类：
    1. 简单计算：RATIO/SUM/DIFFERENCE/PRODUCT/FORMULA
    2. 复杂计算：SUBQUERY/TABLE_CALC_*
    """
    RATIO = "RATIO"
    SUM = "SUM"
    DIFFERENCE = "DIFFERENCE"
    PRODUCT = "PRODUCT"
    FORMULA = "FORMULA"
    SUBQUERY = "SUBQUERY"
    TABLE_CALC_RANK = "TABLE_CALC_RANK"
    TABLE_CALC_PERCENTILE = "TABLE_CALC_PERCENTILE"
    TABLE_CALC_DIFFERENCE = "TABLE_CALC_DIFFERENCE"
    TABLE_CALC_PERCENT_DIFF = "TABLE_CALC_PERCENT_DIFF"
    TABLE_CALC_PERCENT_OF_TOTAL = "TABLE_CALC_PERCENT_OF_TOTAL"
    TABLE_CALC_RUNNING = "TABLE_CALC_RUNNING"
    TABLE_CALC_MOVING = "TABLE_CALC_MOVING"

class ClarificationSource(str, Enum):
    """澄清请求来源"""
    SEMANTIC_UNDERSTANDING = "semantic_understanding"
    FILTER_VALIDATOR = "filter_validator"

# ═══════════════════════════════════════════════════════════════════════════
# 派生度量计算模型
# ═══════════════════════════════════════════════════════════════════════════

class DerivedComputation(BaseModel):
    """派生度量计算定义"""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="计算名称（英文标识符）")
    display_name: str = Field(description="显示名称（用户可见）")
    formula: Optional[str] = Field(
        default=None,
        description="计算公式，使用 [字段名] 引用字段"
    )
    calc_type: CalcType = Field(description="计算类型")
    base_measures: list[str] = Field(
        default_factory=list,
        description="基础度量列表"
    )
    subquery_dimensions: Optional[list[str]] = Field(
        default=None,
        description="子查询聚合维度（仅 SUBQUERY 类型）"
    )
    subquery_aggregation: Optional[str] = Field(
        default=None,
        description="子查询聚合函数（仅 SUBQUERY 类型）"
    )
    partition_by: Optional[list[str]] = Field(
        default=None,
        description="表计算分区维度（仅 TABLE_CALC_* 类型）"
    )
    relative_to: Optional[str] = Field(
        default=None,
        description="差异计算参考点：PREVIOUS/NEXT/FIRST/LAST"
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
    """LLM 自检结果，包含 4 个置信度字段"""
    model_config = ConfigDict(extra="forbid")

    field_mapping_confidence: float = Field(
        ge=0.0, le=1.0,
        description="字段映射置信度"
    )
    time_range_confidence: float = Field(
        ge=0.0, le=1.0,
        description="时间范围置信度"
    )
    computation_confidence: float = Field(
        ge=0.0, le=1.0,
        description="计算逻辑置信度"
    )
    overall_confidence: float = Field(
        ge=0.0, le=1.0,
        description="整体置信度"
    )
    potential_issues: list[str] = Field(
        default_factory=list,
        description="潜在问题列表"
    )

# ═══════════════════════════════════════════════════════════════════════════
# What/Where 模型
# ═══════════════════════════════════════════════════════════════════════════

class What(BaseModel):
    """目标度量"""
    model_config = ConfigDict(extra="forbid")

    measures: list[MeasureField] = Field(
        default_factory=list,
        description="度量列表"
    )

    @model_validator(mode='before')
    @classmethod
    def convert_string_measures(cls, data: Any) -> Any:
        """自动将字符串格式的度量转换为 MeasureField 对象"""
        if isinstance(data, dict) and 'measures' in data:
            measures = data['measures']
            if isinstance(measures, list):
                converted = []
                for m in measures:
                    if isinstance(m, str):
                        converted.append({'field_name': m, 'aggregation': 'SUM'})
                    elif isinstance(m, dict):
                        converted.append(m)
                    else:
                        converted.append(m)
                data['measures'] = converted
        return data

class Where(BaseModel):
    """维度和筛选器"""
    model_config = ConfigDict(extra="forbid")

    dimensions: list[DimensionField] = Field(
        default_factory=list,
        description="维度列表"
    )
    filters: list[FilterUnion] = Field(
        default_factory=list,
        description="筛选条件列表"
    )

    @model_validator(mode='before')
    @classmethod
    def convert_string_dimensions(cls, data: Any) -> Any:
        """自动将字符串格式的维度转换为 DimensionField 对象"""
        if isinstance(data, dict) and 'dimensions' in data:
            dimensions = data['dimensions']
            if isinstance(dimensions, list):
                converted = []
                for d in dimensions:
                    if isinstance(d, str):
                        converted.append({'field_name': d})
                    elif isinstance(d, dict):
                        converted.append(d)
                    else:
                        converted.append(d)
                data['dimensions'] = converted
        return data

# ═══════════════════════════════════════════════════════════════════════════
# 核心输出模型
# ═══════════════════════════════════════════════════════════════════════════

class SemanticOutput(BaseModel):
    """LLM 语义理解输出"""
    model_config = ConfigDict(extra="forbid")

    # ========== 核心输出字段（LLM 必须填写）==========
    restated_question: str = Field(
        description="结合对话历史后的完整问题"
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
        description="计算复杂度"
    )
    computations: list[DerivedComputation] = Field(
        default_factory=list,
        description="派生计算列表（简单查询为空）"
    )

    # ========== 流程控制字段 ==========
    needs_clarification: bool = Field(
        default=False,
        description="是否需要澄清"
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="澄清问题"
    )
    clarification_options: Optional[list[str]] = Field(
        default=None,
        description="澄清选项"
    )

    # ========== 自检结果 ==========
    self_check: SelfCheck = Field(
        description="自检结果"
    )

    # ========== 系统字段（由代码自动生成）==========
    query_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
    )
    parent_query_id: Optional[str] = Field(default=None)
    clarification_source: Optional[ClarificationSource] = Field(default=None)
    parsing_warnings: list[str] = Field(default_factory=list)

    @field_validator("restated_question")
    @classmethod
    def restated_question_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("restated_question 不能为空")
        return v.strip()

    @classmethod
    def llm_json_schema(cls) -> dict:
        """生成用于 LLM 的 JSON Schema（排除系统字段）"""
        system_fields = {"query_id", "parent_query_id", "clarification_source", "parsing_warnings"}
        schema = cls.model_json_schema()
        if "properties" in schema:
            for field in system_fields:
                schema["properties"].pop(field, None)
        if "required" in schema:
            schema["required"] = [
                f for f in schema["required"]
                if f not in system_fields
            ]
        if "$defs" in schema:
            schema_str = json_module.dumps(schema)
            unused_defs = []
            for def_name in list(schema["$defs"].keys()):
                ref_pattern = f'"$ref": "#/$defs/{def_name}"'
                if ref_pattern not in schema_str:
                    unused_defs.append(def_name)
            for def_name in unused_defs:
                schema["$defs"].pop(def_name, None)
        return schema

# ═══════════════════════════════════════════════════════════════════════════
# 复杂查询扩展输出模型
# ═══════════════════════════════════════════════════════════════════════════

class AnalysisModeEnum(str, Enum):
    """全局分析模式（与 planner.AnalysisMode 保持同步）"""
    SINGLE_QUERY = "single_query"
    COMPLEX_SINGLE_QUERY = "complex_single_query"
    MULTI_STEP_ANALYSIS = "multi_step_analysis"
    WHY_ANALYSIS = "why_analysis"


class ComplexSemanticOutput(SemanticOutput):
    """复杂查询的扩展输出模型。

    继承 SemanticOutput 的全部字段，额外增加全局理解判断字段。
    用于复杂查询场景下，让 LLM 在一次调用中同时完成：
    1. 全局结构理解（analysis_mode / single_query_feasible）
    2. 结构化语义解析（what / where / computations）

    LLM 只需给出轻量判断字段，详细的 AnalysisPlan 由规则 planner 根据
    analysis_mode 生成。
    """
    model_config = ConfigDict(extra="forbid")

    analysis_mode: AnalysisModeEnum = Field(
        default=AnalysisModeEnum.SINGLE_QUERY,
        description=(
            "分析模式判断: "
            "single_query=简单直接单查; "
            "complex_single_query=语义复杂但仍可由单条查询完成; "
            "multi_step_analysis=需要多步拆解,下一步依赖前一步结果; "
            "why_analysis=原因/归因分析"
        ),
    )
    single_query_feasible: bool = Field(
        default=True,
        description="在当前系统能力下，是否可以通过单条查询表达",
    )
    decomposition_reason: Optional[str] = Field(
        default=None,
        description="为什么需要拆解或可以保留单查的原因说明",
    )
    risk_flags: list[str] = Field(
        default_factory=list,
        description="分析中发现的风险点，如口径不清、基线缺失等",
    )



__all__ = [
    "CalcType",
    "ClarificationSource",
    "DerivedComputation",
    "SelfCheck",
    "What",
    "Where",
    "SemanticOutput",
    "ComplexSemanticOutput",
    "AnalysisModeEnum",
    "FilterUnion",
]
