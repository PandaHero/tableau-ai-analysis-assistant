# -*- coding: utf-8 -*-
"""
字段语义推断工具函数

从 inference.py 提取的模块级工具函数，供各 mixin 和主类使用。
"""
import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

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
    aliases: list[str],
    role: str,
    data_type: str,
    category: Optional[str] = None,
    measure_category: Optional[str] = None,
    sample_values: Optional[list[Any]] = None,
) -> str:
    """
    构建增强的索引文本

    将字段的所有语义信息编码到索引文本中，使向量检索能够利用完整的语义信息。
    索引文本直接决定 embedding 向量的质量，因此需要包含尽可能多的语义线索。

    格式：{caption}: {business_description}。别名: {aliases}。类别: {category}。类型: {role}, {data_type}。样例: {sample_values}
    """
    desc = business_description if business_description else caption

    parts = [f"{caption}: {desc}"]

    if aliases:
        parts.append(f"别名: {', '.join(aliases)}")

    # 写入语义类别，帮助向量检索区分不同类型的字段
    if role == "measure" and measure_category and measure_category != "other":
        # 将英文类别映射为中文，提升中文查询的匹配度
        _MEASURE_CATEGORY_CN = {
            "revenue": "收入类（销售额、营收）",
            "cost": "成本类（成本、费用）",
            "profit": "利润类（利润、毛利）",
            "quantity": "数量类（数量、销量）",
            "ratio": "比率类（占比、增长率）",
            "count": "计数类（人数、次数）",
            "average": "平均类（均价、平均值）",
        }
        cat_text = _MEASURE_CATEGORY_CN.get(measure_category, measure_category)
        parts.append(f"度量类别: {cat_text}")
    elif role == "dimension" and category and category != "other":
        _DIMENSION_CATEGORY_CN = {
            "time": "时间维度",
            "geography": "地理维度（地区、省市）",
            "product": "产品维度（品类、商品）",
            "customer": "客户维度",
            "organization": "组织维度（部门、公司）",
            "channel": "渠道维度",
            "financial": "财务维度",
        }
        cat_text = _DIMENSION_CATEGORY_CN.get(category, category)
        parts.append(f"维度类别: {cat_text}")

    parts.append(f"类型: {role}, {data_type}")

    # 写入样例值，帮助向量检索理解字段的实际内容
    if sample_values:
        samples_str = ", ".join(str(v) for v in sample_values[:5])
        parts.append(f"样例: {samples_str}")

    return "。".join(parts)

# ══════════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════════

def _get_config() -> dict[str, Any]:
    """从 YAML 读取 field_semantic 配置"""
    config = get_config()
    return config.get("field_semantic", {})

def _get_rag_threshold_seed() -> float:
    """获取 RAG seed/verified 数据阈值"""
    return get_config().get_rag_threshold_seed()

def _get_rag_threshold_unverified() -> float:
    """获取 RAG llm/unverified 数据阈值"""
    return get_config().get_rag_threshold_unverified()

def compute_fields_hash(fields: list[Field]) -> str:
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
    new_fields: set[str]
    changed_fields: set[str]
    deleted_fields: set[str]
    unchanged_fields: set[str]

    @property
    def needs_inference(self) -> bool:
        return len(self.new_fields) > 0 or len(self.changed_fields) > 0

    @property
    def fields_to_infer(self) -> set[str]:
        return self.new_fields | self.changed_fields

def compute_incremental_fields(
    fields: list[Field],
    cached_hashes: Optional[dict[str, str]],
    cached_names: Optional[set[str]],
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
