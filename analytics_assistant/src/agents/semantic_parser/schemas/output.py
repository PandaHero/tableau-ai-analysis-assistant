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
import json as json_module
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from datetime import datetime

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

# Filter Union 类型（不使用 discriminator，让 Pydantic 按顺序尝试匹配）
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
    # 简单计算（多个基础度量间的公式）
    RATIO = "RATIO"                              # 比率: A/B
    SUM = "SUM"                                  # 求和: A+B
    DIFFERENCE = "DIFFERENCE"                    # 差值: A-B
    PRODUCT = "PRODUCT"                          # 乘积: A*B
    FORMULA = "FORMULA"                          # 自定义公式
    
    # 子查询/聚合粒度控制
    SUBQUERY = "SUBQUERY"                        # 子查询
    
    # 表计算
    TABLE_CALC_RANK = "TABLE_CALC_RANK"          # 排名
    TABLE_CALC_PERCENTILE = "TABLE_CALC_PERCENTILE"  # 百分位
    TABLE_CALC_DIFFERENCE = "TABLE_CALC_DIFFERENCE"  # 差异（绝对值）
    TABLE_CALC_PERCENT_DIFF = "TABLE_CALC_PERCENT_DIFF"  # 百分比差异
    TABLE_CALC_PERCENT_OF_TOTAL = "TABLE_CALC_PERCENT_OF_TOTAL"  # 占比
    TABLE_CALC_RUNNING = "TABLE_CALC_RUNNING"    # 累计
    TABLE_CALC_MOVING = "TABLE_CALC_MOVING"      # 移动计算


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
    base_measures: List[str] = Field(
        default_factory=list,
        description="基础度量列表"
    )
    subquery_dimensions: Optional[List[str]] = Field(
        default=None,
        description="子查询聚合维度（仅 SUBQUERY 类型）"
    )
    subquery_aggregation: Optional[str] = Field(
        default=None,
        description="子查询聚合函数（仅 SUBQUERY 类型）"
    )
    partition_by: Optional[List[str]] = Field(
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
    potential_issues: List[str] = Field(
        default_factory=list,
        description="潜在问题列表"
    )


# ═══════════════════════════════════════════════════════════════════════════
# What/Where 模型
# ═══════════════════════════════════════════════════════════════════════════

class What(BaseModel):
    """目标度量"""
    model_config = ConfigDict(extra="forbid")
    
    measures: List[MeasureField] = Field(
        default_factory=list,
        description="度量列表"
    )
    
    @model_validator(mode='before')
    @classmethod
    def convert_string_measures(cls, data: Any) -> Any:
        """自动将字符串格式的度量转换为 MeasureField 对象
        
        LLM 有时会返回简化格式：["销售额", "利润"]
        而不是完整格式：[{"field_name": "销售额", "aggregation": "SUM"}, ...]
        
        此验证器自动处理这种情况。
        """
        if isinstance(data, dict) and 'measures' in data:
            measures = data['measures']
            if isinstance(measures, list):
                converted = []
                for m in measures:
                    if isinstance(m, str):
                        # 字符串 -> MeasureField 对象
                        converted.append({'field_name': m, 'aggregation': 'SUM'})
                    elif isinstance(m, dict):
                        # 已经是字典，保持不变
                        converted.append(m)
                    else:
                        # 其他类型（如 MeasureField 实例），保持不变
                        converted.append(m)
                data['measures'] = converted
        return data


class Where(BaseModel):
    """维度和筛选器"""
    model_config = ConfigDict(extra="forbid")
    
    dimensions: List[DimensionField] = Field(
        default_factory=list,
        description="维度列表"
    )
    filters: List[FilterUnion] = Field(
        default_factory=list,
        description="筛选条件列表"
    )
    
    @model_validator(mode='before')
    @classmethod
    def convert_string_dimensions(cls, data: Any) -> Any:
        """自动将字符串格式的维度转换为 DimensionField 对象
        
        LLM 有时会返回简化格式：["日期", "产品"]
        而不是完整格式：[{"field_name": "日期"}, ...]
        
        此验证器自动处理这种情况。
        """
        if isinstance(data, dict) and 'dimensions' in data:
            dimensions = data['dimensions']
            if isinstance(dimensions, list):
                converted = []
                for d in dimensions:
                    if isinstance(d, str):
                        # 字符串 -> DimensionField 对象
                        converted.append({'field_name': d})
                    elif isinstance(d, dict):
                        # 已经是字典，保持不变
                        converted.append(d)
                    else:
                        # 其他类型（如 DimensionField 实例），保持不变
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
    computations: List[DerivedComputation] = Field(
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
    clarification_options: Optional[List[str]] = Field(
        default=None,
        description="澄清选项"
    )
    
    # ========== 自检结果 ==========
    self_check: SelfCheck = Field(
        description="自检结果"
    )
    
    # ========== 系统字段（由代码自动生成，不需要 LLM 填写）==========
    query_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
    )
    parent_query_id: Optional[str] = Field(default=None)
    clarification_source: Optional[ClarificationSource] = Field(default=None)
    parsing_warnings: List[str] = Field(default_factory=list)
    
    @field_validator("restated_question")
    @classmethod
    def restated_question_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("restated_question 不能为空")
        return v.strip()
    
    @classmethod
    def llm_json_schema(cls) -> dict:
        """生成用于 LLM 的 JSON Schema（排除系统字段）
        
        系统字段（query_id, parent_query_id 等）由代码自动生成，
        不需要 LLM 填写，因此从 Schema 中排除以节省 token。
        
        Returns:
            不含系统字段的 JSON Schema
        """
        # 系统字段列表
        system_fields = {"query_id", "parent_query_id", "clarification_source", "parsing_warnings"}
        
        schema = cls.model_json_schema()
        
        # 从 properties 中移除系统字段
        if "properties" in schema:
            for field in system_fields:
                schema["properties"].pop(field, None)
        
        # 从 required 中移除系统字段
        if "required" in schema:
            schema["required"] = [
                f for f in schema["required"] 
                if f not in system_fields
            ]
        
        # 从 $defs 中移除不再使用的定义（如 ClarificationSource）
        if "$defs" in schema:
            # 将 schema 转为字符串，检查哪些 $defs 被引用
            schema_str = json_module.dumps(schema)
            unused_defs = []
            
            for def_name in list(schema["$defs"].keys()):
                # 检查是否在 schema 中被引用（排除自身定义）
                ref_pattern = f'"$ref": "#/$defs/{def_name}"'
                if ref_pattern not in schema_str:
                    unused_defs.append(def_name)
            
            for def_name in unused_defs:
                schema["$defs"].pop(def_name, None)
        
        return schema


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
