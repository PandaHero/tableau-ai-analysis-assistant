# -*- coding: utf-8 -*-
"""
维度模式种子数据

预置 44 个常见维度模式，覆盖 6 个主要类别（不含 OTHER）：
- time: 时间维度（年、季度、月、周、日、时分秒等）
- geography: 地理维度（国家、省份、城市、区县等）
- product: 产品维度（类别、子类、品牌、SKU 等）
- customer: 客户维度（客户类型、客户名称、客户 ID 等）
- organization: 组织维度（部门、团队、员工等）
- financial: 财务维度（科目、成本中心等）

支持中英文字段名，用于 RAG 检索的 few-shot 示例。

Requirements: 3.1, 3.2, 3.3
"""
from typing import List, Dict, Any
import logging

from tableau_assistant.src.agents.dimension_hierarchy.rag_retriever import DimensionRAGRetriever



logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# 种子数据定义（44 个模式，6 个类别）
# ═══════════════════════════════════════════════════════════

SEED_PATTERNS: List[Dict[str, Any]] = [
    # ─────────────────────────────────────────────────────────
    # TIME 时间维度（10 个）
    # ─────────────────────────────────────────────────────────
    {
        "field_caption": "年",
        "data_type": "integer",
        "category": "time",
        "category_detail": "time-year",
        "level": 1,
        "granularity": "coarsest",
        "reasoning": "时间维度最粗粒度，表示年份",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "Year",
        "data_type": "integer",
        "category": "time",
        "category_detail": "time-year",
        "level": 1,
        "granularity": "coarsest",
        "reasoning": "Time dimension coarsest level, represents year",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "季度",
        "data_type": "string",
        "category": "time",
        "category_detail": "time-quarter",
        "level": 2,
        "granularity": "coarse",
        "reasoning": "时间维度粗粒度，表示季度",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "Quarter",
        "data_type": "string",
        "category": "time",
        "category_detail": "time-quarter",
        "level": 2,
        "granularity": "coarse",
        "reasoning": "Time dimension coarse level, represents quarter",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "月",
        "data_type": "integer",
        "category": "time",
        "category_detail": "time-month",
        "level": 3,
        "granularity": "medium",
        "reasoning": "时间维度中等粒度，表示月份",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "Month",
        "data_type": "integer",
        "category": "time",
        "category_detail": "time-month",
        "level": 3,
        "granularity": "medium",
        "reasoning": "Time dimension medium level, represents month",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "周",
        "data_type": "integer",
        "category": "time",
        "category_detail": "time-week",
        "level": 4,
        "granularity": "fine",
        "reasoning": "时间维度细粒度，表示周",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "日期",
        "data_type": "date",
        "category": "time",
        "category_detail": "time-date",
        "level": 5,
        "granularity": "finest",
        "reasoning": "时间维度最细粒度，表示日期",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "Date",
        "data_type": "date",
        "category": "time",
        "category_detail": "time-date",
        "level": 5,
        "granularity": "finest",
        "reasoning": "Time dimension finest level, represents date",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "订单日期",
        "data_type": "date",
        "category": "time",
        "category_detail": "time-date",
        "level": 5,
        "granularity": "finest",
        "reasoning": "订单时间维度，表示订单日期",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },

    # ─────────────────────────────────────────────────────────
    # GEOGRAPHY 地理维度（8 个）
    # ─────────────────────────────────────────────────────────
    {
        "field_caption": "国家",
        "data_type": "string",
        "category": "geography",
        "category_detail": "geography-country",
        "level": 1,
        "granularity": "coarsest",
        "reasoning": "地理维度最粗粒度，表示国家",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "Country",
        "data_type": "string",
        "category": "geography",
        "category_detail": "geography-country",
        "level": 1,
        "granularity": "coarsest",
        "reasoning": "Geography dimension coarsest level, represents country",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "省份",
        "data_type": "string",
        "category": "geography",
        "category_detail": "geography-province",
        "level": 2,
        "granularity": "coarse",
        "reasoning": "地理维度粗粒度，表示省份/州",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "State",
        "data_type": "string",
        "category": "geography",
        "category_detail": "geography-state",
        "level": 2,
        "granularity": "coarse",
        "reasoning": "Geography dimension coarse level, represents state/province",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "城市",
        "data_type": "string",
        "category": "geography",
        "category_detail": "geography-city",
        "level": 3,
        "granularity": "medium",
        "reasoning": "地理维度中等粒度，表示城市",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "City",
        "data_type": "string",
        "category": "geography",
        "category_detail": "geography-city",
        "level": 3,
        "granularity": "medium",
        "reasoning": "Geography dimension medium level, represents city",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "区县",
        "data_type": "string",
        "category": "geography",
        "category_detail": "geography-district",
        "level": 4,
        "granularity": "fine",
        "reasoning": "地理维度细粒度，表示区县",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "邮编",
        "data_type": "string",
        "category": "geography",
        "category_detail": "geography-postal",
        "level": 5,
        "granularity": "finest",
        "reasoning": "地理维度最细粒度，表示邮政编码",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },

    # ─────────────────────────────────────────────────────────
    # PRODUCT 产品维度（8 个）
    # ─────────────────────────────────────────────────────────
    {
        "field_caption": "产品类别",
        "data_type": "string",
        "category": "product",
        "category_detail": "product-category",
        "level": 1,
        "granularity": "coarsest",
        "reasoning": "产品维度最粗粒度，表示产品大类",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "Category",
        "data_type": "string",
        "category": "product",
        "category_detail": "product-category",
        "level": 1,
        "granularity": "coarsest",
        "reasoning": "Product dimension coarsest level, represents product category",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "产品子类",
        "data_type": "string",
        "category": "product",
        "category_detail": "product-subcategory",
        "level": 2,
        "granularity": "coarse",
        "reasoning": "产品维度粗粒度，表示产品子类",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "Sub-Category",
        "data_type": "string",
        "category": "product",
        "category_detail": "product-subcategory",
        "level": 2,
        "granularity": "coarse",
        "reasoning": "Product dimension coarse level, represents product sub-category",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "品牌",
        "data_type": "string",
        "category": "product",
        "category_detail": "product-brand",
        "level": 3,
        "granularity": "medium",
        "reasoning": "产品维度中等粒度，表示品牌",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "Brand",
        "data_type": "string",
        "category": "product",
        "category_detail": "product-brand",
        "level": 3,
        "granularity": "medium",
        "reasoning": "Product dimension medium level, represents brand",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "产品名称",
        "data_type": "string",
        "category": "product",
        "category_detail": "product-name",
        "level": 4,
        "granularity": "fine",
        "reasoning": "产品维度细粒度，表示产品名称",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "Product Name",
        "data_type": "string",
        "category": "product",
        "category_detail": "product-name",
        "level": 4,
        "granularity": "fine",
        "reasoning": "Product dimension fine level, represents product name",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },

    # ─────────────────────────────────────────────────────────
    # CUSTOMER 客户维度（6 个）
    # ─────────────────────────────────────────────────────────
    {
        "field_caption": "客户类型",
        "data_type": "string",
        "category": "customer",
        "category_detail": "customer-type",
        "level": 1,
        "granularity": "coarsest",
        "reasoning": "客户维度最粗粒度，表示客户类型/细分",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "Customer Segment",
        "data_type": "string",
        "category": "customer",
        "category_detail": "customer-segment",
        "level": 1,
        "granularity": "coarsest",
        "reasoning": "Customer dimension coarsest level, represents customer segment",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "客户名称",
        "data_type": "string",
        "category": "customer",
        "category_detail": "customer-name",
        "level": 2,
        "granularity": "fine",
        "reasoning": "客户维度细粒度，表示客户名称",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "Customer Name",
        "data_type": "string",
        "category": "customer",
        "category_detail": "customer-name",
        "level": 2,
        "granularity": "fine",
        "reasoning": "Customer dimension fine level, represents customer name",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "客户ID",
        "data_type": "string",
        "category": "customer",
        "category_detail": "customer-id",
        "level": 3,
        "granularity": "finest",
        "reasoning": "客户维度最细粒度，表示客户唯一标识",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "Customer ID",
        "data_type": "string",
        "category": "customer",
        "category_detail": "customer-id",
        "level": 3,
        "granularity": "finest",
        "reasoning": "Customer dimension finest level, represents customer unique identifier",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },

    # ─────────────────────────────────────────────────────────
    # ORGANIZATION 组织维度（6 个）
    # ─────────────────────────────────────────────────────────
    {
        "field_caption": "部门",
        "data_type": "string",
        "category": "organization",
        "category_detail": "organization-department",
        "level": 1,
        "granularity": "coarsest",
        "reasoning": "组织维度最粗粒度，表示部门",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "Department",
        "data_type": "string",
        "category": "organization",
        "category_detail": "organization-department",
        "level": 1,
        "granularity": "coarsest",
        "reasoning": "Organization dimension coarsest level, represents department",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "团队",
        "data_type": "string",
        "category": "organization",
        "category_detail": "organization-team",
        "level": 2,
        "granularity": "medium",
        "reasoning": "组织维度中等粒度，表示团队",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "Team",
        "data_type": "string",
        "category": "organization",
        "category_detail": "organization-team",
        "level": 2,
        "granularity": "medium",
        "reasoning": "Organization dimension medium level, represents team",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "员工",
        "data_type": "string",
        "category": "organization",
        "category_detail": "organization-employee",
        "level": 3,
        "granularity": "finest",
        "reasoning": "组织维度最细粒度，表示员工",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "Employee",
        "data_type": "string",
        "category": "organization",
        "category_detail": "organization-employee",
        "level": 3,
        "granularity": "finest",
        "reasoning": "Organization dimension finest level, represents employee",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },

    # ─────────────────────────────────────────────────────────
    # FINANCIAL 财务维度（6 个）
    # ─────────────────────────────────────────────────────────
    {
        "field_caption": "科目类别",
        "data_type": "string",
        "category": "financial",
        "category_detail": "financial-account-type",
        "level": 1,
        "granularity": "coarsest",
        "reasoning": "财务维度最粗粒度，表示科目大类",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "Account Type",
        "data_type": "string",
        "category": "financial",
        "category_detail": "financial-account-type",
        "level": 1,
        "granularity": "coarsest",
        "reasoning": "Financial dimension coarsest level, represents account type",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "成本中心",
        "data_type": "string",
        "category": "financial",
        "category_detail": "financial-cost-center",
        "level": 2,
        "granularity": "medium",
        "reasoning": "财务维度中等粒度，表示成本中心",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "Cost Center",
        "data_type": "string",
        "category": "financial",
        "category_detail": "financial-cost-center",
        "level": 2,
        "granularity": "medium",
        "reasoning": "Financial dimension medium level, represents cost center",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "科目",
        "data_type": "string",
        "category": "financial",
        "category_detail": "financial-account",
        "level": 3,
        "granularity": "finest",
        "reasoning": "财务维度最细粒度，表示具体科目",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
    {
        "field_caption": "Account",
        "data_type": "string",
        "category": "financial",
        "category_detail": "financial-account",
        "level": 3,
        "granularity": "finest",
        "reasoning": "Financial dimension finest level, represents specific account",
        "confidence": 1.0,
        "source": "seed",
        "verified": True,
    },
]

# 验证种子数据数量
assert len(SEED_PATTERNS) == 44, f"Expected 44 seed patterns, got {len(SEED_PATTERNS)}"


# ═══════════════════════════════════════════════════════════
# Few-shot 示例获取
# ═══════════════════════════════════════════════════════════

def get_seed_few_shot_examples(
    categories: List[str] = None,
    max_per_category: int = 2,
) -> List[Dict[str, Any]]:
    """
    获取种子数据作为 few-shot 示例
    
    Args:
        categories: 要获取的类别列表，None 表示所有类别
        max_per_category: 每个类别最多返回的示例数
    
    Returns:
        few-shot 示例列表
    """
    if categories is None:
        categories = ["time", "geography", "product", "customer", "organization", "financial"]
    
    examples = []
    category_counts = {cat: 0 for cat in categories}
    
    for pattern in SEED_PATTERNS:
        cat = pattern["category"]
        if cat in categories and category_counts[cat] < max_per_category:
            examples.append({
                "field_caption": pattern["field_caption"],
                "data_type": pattern["data_type"],
                "category": pattern["category"],
                "category_detail": pattern["category_detail"],
                "level": pattern["level"],
                "granularity": pattern["granularity"],
            })
            category_counts[cat] += 1
    
    return examples


# ═══════════════════════════════════════════════════════════
# 种子数据初始化
# ═══════════════════════════════════════════════════════════

def initialize_seed_patterns(
    rag_retriever: DimensionRAGRetriever,
) -> int:
    """
    初始化种子数据到 RAG（向量索引 + LangGraph Store）


    流程：
    1. 批量添加所有种子模式到 RAG
    2. 统一保存一次 FAISS 索引（减少磁盘 IO）

    Args:
        rag_retriever: RAG 检索器实例

    Returns:
        metadata 写入成功的数量（包含已存在跳过的，保持幂等调用时的返回值稳定）
    """
    logger.info(f"开始初始化种子数据: {len(SEED_PATTERNS)} 个模式")

    store_result = rag_retriever.batch_store_patterns(
        patterns=SEED_PATTERNS,
        save_after_all=True,
    )

    metadata_written = store_result.get("metadata_written", 0)
    faiss_written = store_result.get("faiss_written", 0)
    skipped_existing = store_result.get("skipped_existing", 0)

    logger.info(
        f"种子数据初始化完成: metadata={metadata_written}/{len(SEED_PATTERNS)}, "
        f"faiss_new={faiss_written}, skipped={skipped_existing}"
    )
    return metadata_written


__all__ = [
    "SEED_PATTERNS",
    "get_seed_few_shot_examples",
    "initialize_seed_patterns",
]
