# -*- coding: utf-8 -*-
"""
字段语义推断工具函数

从 inference.py 提取的模块级工具函数，供各 mixin 和主类使用。
"""
import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from analytics_assistant.src.core.schemas.data_model import Field
from analytics_assistant.src.core.schemas.enums import DimensionCategory, MeasureCategory
from analytics_assistant.src.agents.field_semantic.schemas import (
    FieldSemanticAttributes,
)
from analytics_assistant.src.infra.config import get_config


# 字段语义模式索引名称
FIELD_SEMANTIC_PATTERNS_INDEX = "field_semantic_patterns"


class PatternSource(str, Enum):
    """RAG 模式来源"""
    SEED = "seed"
    LLM = "llm"
    MANUAL = "manual"


# ══════════════════════════════════════════════════════════════
# 并发控制常量
# ══════════════════════════════════════════════════════════════

MAX_LOCKS = 100
LOCK_EXPIRE_SECONDS = 300


# ══════════════════════════════════════════════════════════════
# 索引文本增强
# ══════════════════════════════════════════════════════════════

def build_enhanced_index_text(
    caption: str,
    business_description: str,
    aliases: List[str],
    role: str,
    data_type: str,
) -> str:
    """
    构建增强的索引文本

    格式：{caption}: {business_description}。别名: {aliases}。类型: {role}, {data_type}
    """
    desc = business_description if business_description else caption

    parts = [f"{caption}: {desc}"]

    if aliases:
        parts.append(f"别名: {', '.join(aliases)}")

    parts.append(f"类型: {role}, {data_type}")

    return "。".join(parts)


# ══════════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════════

def _get_config() -> Dict[str, Any]:
    """从 YAML 读取 field_semantic 配置"""
    config = get_config()
    return config.get("field_semantic", {})


def _get_rag_threshold_seed() -> float:
    """获取 RAG seed/verified 数据阈值"""
    return get_config().get_rag_threshold_seed()


def _get_rag_threshold_unverified() -> float:
    """获取 RAG llm/unverified 数据阈值"""
    return get_config().get_rag_threshold_unverified()


def compute_fields_hash(fields: List[Field]) -> str:
    """计算字段列表的整体哈希值"""
    field_info = []
    for f in sorted(fields, key=lambda x: x.caption or x.name):
        field_info.append({
            "caption": f.caption or f.name,
            "data_type": f.data_type,
            "role": f.role,
        })
    return hashlib.md5(json.dumps(field_info, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def compute_single_field_hash(field: Field) -> str:
    """计算单个字段的哈希值"""
    info = {
        "caption": field.caption or field.name,
        "data_type": field.data_type,
        "role": field.role,
    }
    return hashlib.md5(json.dumps(info, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def generate_pattern_id(caption: str, data_type: str, scope: Optional[str] = None) -> str:
    """生成模式 ID"""
    key = f"{caption}|{data_type}|{scope or 'global'}"
    return hashlib.md5(key.encode()).hexdigest()[:16]


def build_cache_key(datasource_luid: str, table_id: Optional[str] = None) -> str:
    """构建缓存 key"""
    return f"{datasource_luid}:{table_id}" if table_id else datasource_luid


# ══════════════════════════════════════════════════════════════
# 增量字段计算
# ══════════════════════════════════════════════════════════════

@dataclass
class IncrementalFieldsResult:
    """增量字段计算结果"""
    new_fields: Set[str]
    changed_fields: Set[str]
    deleted_fields: Set[str]
    unchanged_fields: Set[str]

    @property
    def needs_inference(self) -> bool:
        return len(self.new_fields) > 0 or len(self.changed_fields) > 0

    @property
    def fields_to_infer(self) -> Set[str]:
        return self.new_fields | self.changed_fields


def compute_incremental_fields(
    fields: List[Field],
    cached_hashes: Optional[Dict[str, str]],
    cached_names: Optional[Set[str]],
) -> IncrementalFieldsResult:
    """计算增量字段"""
    current_names = {f.caption or f.name for f in fields}

    if cached_hashes is None or cached_names is None:
        return IncrementalFieldsResult(current_names, set(), set(), set())

    current_hashes = {f.caption or f.name: compute_single_field_hash(f) for f in fields}
    new_fields = current_names - cached_names
    deleted_fields = cached_names - current_names
    changed_fields = set()
    unchanged_fields = set()

    for name in current_names & cached_names:
        if current_hashes.get(name) != cached_hashes.get(name):
            changed_fields.add(name)
        else:
            unchanged_fields.add(name)

    return IncrementalFieldsResult(new_fields, changed_fields, deleted_fields, unchanged_fields)


# ══════════════════════════════════════════════════════════════
# 默认属性
# ══════════════════════════════════════════════════════════════

def _default_dimension_attrs(name: str) -> FieldSemanticAttributes:
    """维度字段默认属性"""
    return FieldSemanticAttributes(
        role="dimension",
        category=DimensionCategory.OTHER,
        category_detail="other-unknown",
        level=3,
        granularity="medium",
        business_description=name,
        aliases=[],
        confidence=0.0,
        reasoning=f"推断失败: {name}",
    )


def _default_measure_attrs(name: str) -> FieldSemanticAttributes:
    """度量字段默认属性"""
    return FieldSemanticAttributes(
        role="measure",
        measure_category=MeasureCategory.OTHER,
        business_description=name,
        aliases=[],
        confidence=0.0,
        reasoning=f"推断失败: {name}",
    )


def _default_attrs(name: str, role: str) -> FieldSemanticAttributes:
    """根据角色返回默认属性"""
    if role == "measure":
        return _default_measure_attrs(name)
    return _default_dimension_attrs(name)
