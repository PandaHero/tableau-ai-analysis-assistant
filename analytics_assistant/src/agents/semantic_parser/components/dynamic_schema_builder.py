# -*- coding: utf-8 -*-
"""
DynamicSchemaBuilder - 动态 Schema 构建器

根据 ComplexityType 精确裁剪 Schema，只传递必要的字段定义给 LLM。

核心优化思路：
1. 传给 LLM 的 Prompt = 系统提示词 + Schema + 字段列表
2. 系统提示词已固定，无法优化
3. 字段列表通过 FieldRetriever 的 Top-K 优化
4. Schema 根据 ComplexityType 精确裁剪

Schema 裁剪策略：
- SIMPLE: 只需要 What + Where（无 computations）
- RATIO: + computations.formula, computations.base_measures
- TIME_COMPARE: + computations.relative_to, computations.partition_by
- RANK: + computations.partition_by
- SHARE: + computations.partition_by（占比计算）
- CUMULATIVE: + computations.partition_by（累计计算）
- SUBQUERY: + computations.subquery_dimensions, computations.subquery_aggregation

配置来源：
- analytics_assistant/config/app.yaml -> semantic_parser.optimization.max_schema_fields

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
"""

import json
import logging
from enum import Enum
from typing import Any, Optional

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.core.schemas.field_candidate import FieldCandidate
from ..schemas.prefilter import ComplexityType
from ..schemas.dynamic_schema import DynamicSchemaResult

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# Schema 模块枚举
# ═══════════════════════════════════════════════════════════════════════════

class SchemaModule(str, Enum):
    """Schema 模块类型"""
    BASE = "base"               # 基础模块（始终包含：What + Where）
    TIME = "time"               # 时间模块（DateRangeFilter 等）
    COMPUTATION = "computation" # 计算模块（DerivedComputation）

# ═══════════════════════════════════════════════════════════════════════════
# DerivedComputation Schema 字段定义
# ═══════════════════════════════════════════════════════════════════════════

# 基础字段（所有计算类型都需要）
COMPUTATION_BASE_FIELDS = ["name", "display_name", "calc_type"]

# 各 ComplexityType 需要的额外字段
COMPLEXITY_SCHEMA_FIELDS: dict[ComplexityType, list[str]] = {
    ComplexityType.SIMPLE: [],  # 不需要 computations
    ComplexityType.RATIO: ["formula", "base_measures"],
    ComplexityType.TIME_COMPARE: ["relative_to", "partition_by", "base_measures"],
    ComplexityType.RANK: ["partition_by", "base_measures"],
    ComplexityType.SHARE: ["partition_by", "base_measures"],
    ComplexityType.CUMULATIVE: ["partition_by", "base_measures"],
    ComplexityType.SUBQUERY: ["subquery_dimensions", "subquery_aggregation", "base_measures"],
}

# 各 ComplexityType 对应的 CalcType 枚举值
COMPLEXITY_CALC_TYPES: dict[ComplexityType, list[str]] = {
    ComplexityType.SIMPLE: [],
    ComplexityType.RATIO: ["RATIO", "DIFFERENCE", "PRODUCT", "SUM", "FORMULA"],
    ComplexityType.TIME_COMPARE: ["TABLE_CALC_PERCENT_DIFF", "TABLE_CALC_DIFFERENCE"],
    ComplexityType.RANK: ["TABLE_CALC_RANK", "TABLE_CALC_PERCENTILE"],
    ComplexityType.SHARE: ["TABLE_CALC_PERCENT_OF_TOTAL"],
    ComplexityType.CUMULATIVE: ["TABLE_CALC_RUNNING", "TABLE_CALC_MOVING"],
    ComplexityType.SUBQUERY: ["SUBQUERY"],
}

# DynamicSchemaResult 已迁移到 schemas/dynamic_schema.py

# ═══════════════════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════════════════

def get_max_schema_fields() -> int:
    """获取最大 Schema 字段数。"""
    try:
        config = get_config()
        return config.get_semantic_parser_optimization_config().get("max_schema_fields", 20)
    except Exception as e:
        logger.warning(f"无法加载配置，使用默认值: {e}")
        return 20

# ═══════════════════════════════════════════════════════════════════════════
# DynamicSchemaBuilder 组件
# ═══════════════════════════════════════════════════════════════════════════

class DynamicSchemaBuilder:
    """动态 Schema 构建器
    
    根据 ComplexityType 精确裁剪 Schema，只传递必要的字段定义给 LLM。
    
    优化原理：
    - 既然 RulePrefilter 已经检测出了具体的 ComplexityType（如 RATIO）
    - 就只需要把 RATIO 相关的 Schema 字段传给 LLM
    - 而不是把所有计算类型的 Schema 都传过去
    
    Examples:
        >>> builder = DynamicSchemaBuilder()
        >>> result = builder.build(
        ...     feature_output=feature_output,
        ...     field_rag_result=field_rag_result,
        ...     prefilter_result=prefilter_result,
        ... )
        >>> # result.computation_schema_fields 包含裁剪后的字段列表
        >>> # result.allowed_calc_types 包含允许的 CalcType
    """
    
    DEFAULT_MAX_FIELDS = 20
    
    def __init__(self, max_fields: Optional[int] = None):
        """初始化 DynamicSchemaBuilder。
        
        Args:
            max_fields: 最大字段数（None 从配置读取）
        """
        self.max_fields = max_fields or get_max_schema_fields()

    def build(
        self,
        feature_output: Any,
        field_rag_result: Any,
        prefilter_result: Optional[Any] = None,
    ) -> DynamicSchemaResult:
        """构建动态 Schema
        
        Args:
            feature_output: FeatureExtractionOutput 特征提取输出
            field_rag_result: FieldRAGResult 字段检索结果
            prefilter_result: PrefilterResult 规则预处理结果（可选）
            
        Returns:
            DynamicSchemaResult 包含裁剪后的 Schema JSON
        """
        # 1. 获取检测到的 ComplexityType
        detected_complexity = self._get_detected_complexity(prefilter_result)
        
        # 2. 选择需要的模块
        modules = self._select_modules(detected_complexity, prefilter_result)
        
        # 3. 收集字段（Top-K 优化）
        field_candidates = self._collect_fields(field_rag_result, modules)
        
        # 4. 根据 ComplexityType 获取允许的 CalcType
        allowed_calc_types = self._get_allowed_calc_types(detected_complexity)
        
        # 5. 生成裁剪后的 Schema JSON
        schema_json = self._build_schema_json(detected_complexity, allowed_calc_types)
        
        # 6. 获取时间表达式类型
        time_expressions = []
        if SchemaModule.TIME in modules:
            time_expressions = ["relative", "absolute", "range", "period"]
        
        logger.info(
            f"DynamicSchemaBuilder: 构建完成, "
            f"complexity={[c.value for c in detected_complexity]}, "
            f"modules={[m.value for m in modules]}, "
            f"schema_json_len={len(schema_json)}, "
            f"field_count={len(field_candidates)}"
        )
        
        return DynamicSchemaResult(
            field_candidates=field_candidates,
            schema_text=schema_json,
            modules={m.value for m in modules},
            detected_complexity=detected_complexity,
            allowed_calc_types=allowed_calc_types,
            time_expressions=time_expressions,
        )
    
    def _get_detected_complexity(
        self,
        prefilter_result: Optional[Any],
    ) -> list[ComplexityType]:
        """获取检测到的 ComplexityType
        
        Args:
            prefilter_result: 规则预处理结果
            
        Returns:
            ComplexityType 列表
        """
        if prefilter_result is None:
            return [ComplexityType.SIMPLE]
        
        detected = getattr(prefilter_result, 'detected_complexity', [])
        if not detected:
            return [ComplexityType.SIMPLE]
        
        # 转换为 ComplexityType 枚举
        result = []
        for c in detected:
            if isinstance(c, ComplexityType):
                result.append(c)
            elif isinstance(c, str):
                try:
                    result.append(ComplexityType(c.lower()))
                except ValueError:
                    logger.warning(f"未知的 ComplexityType: {c}")
            elif hasattr(c, 'value'):
                try:
                    result.append(ComplexityType(c.value.lower()))
                except ValueError:
                    logger.warning(f"未知的 ComplexityType: {c.value}")
        
        return result if result else [ComplexityType.SIMPLE]
    
    def _select_modules(
        self,
        detected_complexity: list[ComplexityType],
        prefilter_result: Optional[Any],
    ) -> set[SchemaModule]:
        """选择需要的 Schema 模块
        
        Args:
            detected_complexity: 检测到的复杂度类型
            prefilter_result: 规则预处理结果
            
        Returns:
            选择的模块集合
        """
        modules = {SchemaModule.BASE}  # 始终包含基础模块
        
        # 检测时间表达式
        if prefilter_result:
            time_hints = getattr(prefilter_result, 'time_hints', [])
            if time_hints:
                modules.add(SchemaModule.TIME)
        
        # 检测是否需要计算模块
        # 只有非 SIMPLE 类型才需要
        for complexity in detected_complexity:
            if complexity != ComplexityType.SIMPLE:
                modules.add(SchemaModule.COMPUTATION)
                break
        
        return modules
    
    def _collect_fields(
        self,
        field_rag_result: Any,
        modules: set[SchemaModule],
    ) -> list[FieldCandidate]:
        """收集字段（Top-K 优化）
        
        Args:
            field_rag_result: 字段检索结果
            modules: 选择的模块集合
            
        Returns:
            FieldCandidate 列表
        """
        candidates: list[FieldCandidate] = []
        seen_names: set[str] = set()
        
        if field_rag_result is None:
            return candidates
        
        def _add_unique(fields: list[FieldCandidate]) -> None:
            for f in fields:
                if f.field_name not in seen_names:
                    seen_names.add(f.field_name)
                    candidates.append(f)
        
        # 添加度量字段
        _add_unique(getattr(field_rag_result, 'measures', []))
        
        # 添加维度字段
        _add_unique(getattr(field_rag_result, 'dimensions', []))
        
        # 添加时间字段（如果需要时间模块；去重避免与 dimensions 重叠）
        if SchemaModule.TIME in modules:
            _add_unique(getattr(field_rag_result, 'time_fields', []))
        
        # 按置信度排序并限制数量
        candidates.sort(key=lambda x: x.confidence, reverse=True)
        return candidates[:self.max_fields]
    
    def _get_allowed_calc_types(
        self,
        detected_complexity: list[ComplexityType],
    ) -> list[str]:
        """根据 ComplexityType 获取允许的 CalcType 枚举值
        
        核心裁剪逻辑：
        - SIMPLE: 不需要 CalcType
        - RATIO: 只允许 RATIO, DIFFERENCE, PRODUCT, SUM, FORMULA
        - TIME_COMPARE: 只允许 TABLE_CALC_PERCENT_DIFF, TABLE_CALC_DIFFERENCE
        - 等等...
        
        Args:
            detected_complexity: 检测到的复杂度类型
            
        Returns:
            允许的 CalcType 列表
        """
        # 如果只有 SIMPLE，不需要 CalcType
        if detected_complexity == [ComplexityType.SIMPLE]:
            return []
        
        # 收集所有允许的 CalcType
        calc_types: set[str] = set()
        
        for complexity in detected_complexity:
            if complexity == ComplexityType.SIMPLE:
                continue
            allowed = COMPLEXITY_CALC_TYPES.get(complexity, [])
            calc_types.update(allowed)
        
        return sorted(list(calc_types))
    
    def _build_schema_json(
        self,
        detected_complexity: list[ComplexityType],
        allowed_calc_types: list[str],
    ) -> str:
        """构建裁剪后的 Schema JSON
        
        根据 ComplexityType 只包含必要的字段定义。
        
        Args:
            detected_complexity: 检测到的复杂度类型
            allowed_calc_types: 允许的 CalcType
            
        Returns:
            Schema JSON 字符串，SIMPLE 类型返回空字符串
        """
        # SIMPLE 类型不需要 computations Schema，但提供精简的结构约束
        if detected_complexity == [ComplexityType.SIMPLE] or not allowed_calc_types:
            return json.dumps({
                "type": "object",
                "description": "简单查询输出结构（无需 computations）",
                "properties": {
                    "what": {
                        "type": "object",
                        "properties": {
                            "measures": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "度量字段列表",
                            },
                        },
                    },
                    "where": {
                        "type": "object",
                        "properties": {
                            "dimensions": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "维度字段列表",
                            },
                            "filters": {
                                "type": "array",
                                "description": "筛选条件列表",
                            },
                        },
                    },
                },
                "required": ["what", "where"],
            }, ensure_ascii=False, indent=2)
        
        # 收集需要的字段
        schema_fields: set[str] = set(COMPUTATION_BASE_FIELDS)
        for complexity in detected_complexity:
            if complexity == ComplexityType.SIMPLE:
                continue
            extra_fields = COMPLEXITY_SCHEMA_FIELDS.get(complexity, [])
            schema_fields.update(extra_fields)
        
        # 字段定义映射
        field_definitions = {
            "name": {"type": "string", "description": "计算名称（英文标识符）"},
            "display_name": {"type": "string", "description": "显示名称"},
            "calc_type": {
                "type": "string",
                "enum": allowed_calc_types,
                "description": "计算类型",
            },
            "formula": {
                "type": "string",
                "description": "计算公式，使用 [字段名] 引用字段",
            },
            "base_measures": {
                "type": "array",
                "items": {"type": "string"},
                "description": "基础度量列表",
            },
            "partition_by": {
                "type": "array",
                "items": {"type": "string"},
                "description": "分区维度列表",
            },
            "relative_to": {
                "type": "string",
                "enum": ["PREVIOUS", "NEXT", "FIRST", "LAST"],
                "description": "对比参考点",
            },
            "subquery_dimensions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "子查询聚合维度",
            },
            "subquery_aggregation": {
                "type": "string",
                "description": "子查询聚合函数",
            },
        }
        
        # 构建 Schema
        schema_def = {
            "type": "object",
            "properties": {},
            "required": ["name", "display_name", "calc_type"],
        }
        
        for field_name in sorted(schema_fields):
            if field_name in field_definitions:
                schema_def["properties"][field_name] = field_definitions[field_name]
        
        return json.dumps(schema_def, ensure_ascii=False, indent=2)

__all__ = [
    "SchemaModule",
    "DynamicSchemaBuilder",
    "get_max_schema_fields",
    "COMPLEXITY_SCHEMA_FIELDS",
    "COMPLEXITY_CALC_TYPES",
]
