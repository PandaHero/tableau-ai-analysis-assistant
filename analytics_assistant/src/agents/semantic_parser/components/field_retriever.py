# -*- coding: utf-8 -*-
"""
FieldRetriever 组件 - 智能字段检索

功能：
- 三层检索策略：L0 全量 → L1 规则匹配 → L2 Embedding 兜底
- 利用维度层级推断结果（DimensionHierarchyResult）优化字段筛选
- 度量字段始终全量返回
- 支持层级扩展（父/子维度）

设计原则（参考 NeurIPS 2024 "The Death of Schema Linking"）：
- 强推理模型（如 DeepSeek）不需要复杂的 Schema Linking
- 当字段数量较少时，直接传递全部字段给 LLM
- 当字段数量较多时，使用规则+Embedding筛选相关字段

配置来源：
- 常量配置：analytics_assistant/config/app.yaml -> field_retriever
- 类别关键词：从 SEED_PATTERNS 动态提取，支持自学习扩展

Requirements: 3.1-3.3 - FieldRetriever 字段检索
"""

import logging
from typing import Any, Dict, List, Optional, Set

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.agents.dimension_hierarchy.seed_data import SEED_PATTERNS

from ..schemas.intermediate import FieldCandidate

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════════════════

def _get_config() -> Dict[str, Any]:
    """获取 field_retriever 配置。
    
    从 app.yaml 读取配置，如果不存在则使用默认值。
    """
    try:
        config = get_config()
        return config.config.get("field_retriever", {})
    except Exception as e:
        logger.warning(f"无法加载配置，使用默认值: {e}")
        return {}


def _get_confidence_config() -> Dict[str, float]:
    """获取置信度配置。"""
    config = _get_config()
    return config.get("confidence", {})


def get_full_schema_threshold() -> int:
    """获取 L0 全量返回阈值。"""
    return _get_config().get("full_schema_threshold", 20)


def get_min_rule_match_dimensions() -> int:
    """获取 L2 触发阈值。"""
    return _get_config().get("min_rule_match_dimensions", 3)


def get_default_top_k() -> int:
    """获取默认 Top-K。"""
    return _get_config().get("top_k", 10)


def get_full_schema_confidence() -> float:
    """获取 L0 全量返回置信度。"""
    return _get_confidence_config().get("full_schema", 0.8)


def get_rule_match_confidence() -> float:
    """获取 L1 规则匹配置信度。"""
    return _get_confidence_config().get("rule_match", 0.9)


def get_hierarchy_expand_confidence() -> float:
    """获取层级扩展置信度。"""
    return _get_confidence_config().get("hierarchy_expand", 0.85)


def get_embedding_confidence_base() -> float:
    """获取 L2 Embedding 检索基础置信度。"""
    return _get_confidence_config().get("embedding_base", 0.7)


# ═══════════════════════════════════════════════════════════════════════════
# 类别关键词（从 SEED_PATTERNS 动态提取 + 扩展关键词）
# ═══════════════════════════════════════════════════════════════════════════

def _build_category_keywords() -> Dict[str, Set[str]]:
    """从 SEED_PATTERNS 动态构建类别关键词映射。
    
    优先从 seed_data 提取，然后补充常用的查询关键词。
    这样当 seed_data 自学习扩展时，关键词也会自动扩展。
    """
    keywords: Dict[str, Set[str]] = {
        "time": set(),
        "geography": set(),
        "product": set(),
        "customer": set(),
        "organization": set(),
        "financial": set(),
        "channel": set(),
        "measure": set(),  # 度量类别
    }
    
    # 从 SEED_PATTERNS 提取 field_caption 作为关键词
    try:
        for pattern in SEED_PATTERNS:
            category = pattern.get("category", "").lower()
            caption = pattern.get("field_caption", "")
            if category in keywords and caption:
                keywords[category].add(caption.lower())
                # 也添加 category_detail 中的子类型
                detail = pattern.get("category_detail", "")
                if "-" in detail:
                    sub_type = detail.split("-")[-1]
                    keywords[category].add(sub_type.lower())
    except Exception as e:
        logger.warning(f"从 SEED_PATTERNS 提取关键词失败: {e}")
    
    # 补充常用查询关键词（用户问题中常见的表达）
    _extend_query_keywords(keywords)
    
    return keywords


def _extend_query_keywords(keywords: Dict[str, Set[str]]) -> None:
    """补充用户查询中常见的关键词表达。"""
    
    # 时间相关
    keywords["time"].update([
        "时间", "日期", "年", "月", "季度", "周", "天", "日",
        "今天", "昨天", "本周", "上周", "本月", "上个月", "今年", "去年",
        "最近", "过去", "同期", "环比", "同比", "财年", "fy", "q1", "q2", "q3", "q4",
    ])
    
    # 地理相关
    keywords["geography"].update([
        "地区", "区域", "省", "省份", "市", "城市", "县", "区",
        "门店", "店铺", "网点", "分公司", "大区", "片区",
        "华东", "华南", "华北", "华中", "西南", "西北", "东北",
    ])
    
    # 产品相关
    keywords["product"].update([
        "产品", "商品", "品类", "品牌", "sku", "型号", "规格",
        "系列", "产品线", "子品类", "大类", "中类", "小类",
    ])
    
    # 客户相关
    keywords["customer"].update([
        "客户", "顾客", "会员", "用户", "消费者", "买家",
        "vip", "新客", "老客", "回头客",
    ])
    
    # 组织相关
    keywords["organization"].update([
        "部门", "组织", "团队", "员工", "经理", "主管",
        "销售员", "业务员", "店长",
    ])
    
    # 财务相关
    keywords["financial"].update([
        "科目", "成本中心", "费用", "预算", "账户",
    ])
    
    # 渠道相关
    keywords["channel"].update([
        "渠道", "线上", "线下", "电商", "实体店",
        "天猫", "京东", "拼多多", "抖音",
    ])
    
    # 度量相关（用于识别问题中涉及的度量类型）
    keywords["measure"].update([
        "销售额", "销售", "营收", "收入", "金额", "总额",
        "利润", "毛利", "净利", "利润率", "毛利率",
        "成本", "费用", "支出", "开销",
        "数量", "件数", "订单数", "单量", "笔数",
        "均价", "单价", "平均", "客单价",
        "占比", "比例", "份额", "比重",
        "增长", "增长率", "同比", "环比", "yoy", "mom",
        "预算", "实际", "达成率", "完成率",
        "库存", "周转", "周转率",
    ])


# 延迟初始化的类别关键词
_CATEGORY_KEYWORDS: Optional[Dict[str, Set[str]]] = None


def get_category_keywords() -> Dict[str, Set[str]]:
    """获取类别关键词映射（延迟初始化）。"""
    global _CATEGORY_KEYWORDS
    if _CATEGORY_KEYWORDS is None:
        _CATEGORY_KEYWORDS = _build_category_keywords()
    return _CATEGORY_KEYWORDS


# ═══════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════

def _get_field_attr(obj: Any, *names, default=None) -> Any:
    """从对象或字典中获取属性。"""
    for name in names:
        if isinstance(obj, dict):
            if name in obj:
                return obj[name]
        else:
            if hasattr(obj, name):
                return getattr(obj, name)
    return default


def extract_categories_by_rules(question: str) -> Set[str]:
    """从问题中提取匹配的类别。
    
    使用关键词匹配识别问题涉及的维度类别。
    关键词来自 SEED_PATTERNS + 扩展查询词。
    
    Args:
        question: 用户问题
    
    Returns:
        匹配的类别集合（如 {"geography", "time"}）
    """
    matched_categories: Set[str] = set()
    question_lower = question.lower()
    
    category_keywords = get_category_keywords()
    
    for category, keywords in category_keywords.items():
        for keyword in keywords:
            if keyword in question_lower:
                matched_categories.add(category)
                break  # 一个类别只需匹配一个关键词
    
    return matched_categories


def match_field_name_or_caption(
    question: str,
    fields: List[Any],
) -> Set[str]:
    """匹配问题中直接提到的字段名或标题。
    
    Args:
        question: 用户问题
        fields: 字段列表
    
    Returns:
        匹配的字段名集合
    """
    matched_fields: Set[str] = set()
    question_lower = question.lower()
    
    for field in fields:
        field_name = _get_field_attr(field, 'name', 'field_name', default='')
        field_caption = _get_field_attr(field, 'fieldCaption', 'field_caption', 'caption', default='')
        
        # 检查字段名或标题是否出现在问题中
        if field_name and field_name.lower() in question_lower:
            matched_fields.add(field_name)
        elif field_caption and len(field_caption) >= 2 and field_caption.lower() in question_lower:
            # caption 至少 2 个字符才匹配，避免单字误匹配
            matched_fields.add(field_name)
    
    return matched_fields


# ═══════════════════════════════════════════════════════════════════════════
# FieldRetriever 组件
# ═══════════════════════════════════════════════════════════════════════════

class FieldRetriever:
    """字段检索器 - 三层智能策略。
    
    检索策略：
    - L0: 字段数 <= full_schema_threshold → 全量返回（信任 LLM 推理能力）
    - L1: 规则匹配 → 根据类别关键词筛选维度 + 全量度量
    - L2: Embedding 兜底 → 当规则匹配维度 < min_rule_match_dimensions 时触发
    
    核心原则：
    - 度量字段始终全量返回（不筛选）
    - 维度字段根据问题相关性筛选
    - 利用维度层级信息扩展相关字段（父/子维度）
    
    配置来源：
    - app.yaml -> field_retriever 配置节
    
    Examples:
        >>> retriever = FieldRetriever(cascade_retriever)
        >>> candidates = await retriever.retrieve(
        ...     question="上个月各地区的销售额",
        ...     data_model=data_model,
        ...     dimension_hierarchy=hierarchy_result,
        ... )
        >>> for c in candidates:
        ...     print(f"{c.field_name}: {c.source}, category={c.hierarchy_category}")
    """
    
    def __init__(
        self,
        cascade_retriever: Optional[Any] = None,
        default_top_k: Optional[int] = None,
        full_schema_threshold: Optional[int] = None,
        min_rule_match_dimensions: Optional[int] = None,
    ):
        """初始化 FieldRetriever。
        
        Args:
            cascade_retriever: CascadeRetriever 实例，用于 Embedding 检索
            default_top_k: 默认返回数量（None 从配置读取）
            full_schema_threshold: L0 全量返回阈值（None 从配置读取）
            min_rule_match_dimensions: L2 触发阈值（None 从配置读取）
        """
        self._retriever = cascade_retriever
        self.default_top_k = default_top_k or get_default_top_k()
        self.full_schema_threshold = full_schema_threshold or get_full_schema_threshold()
        self.min_rule_match_dimensions = min_rule_match_dimensions or get_min_rule_match_dimensions()
        
        # 从配置加载置信度参数
        self._full_schema_confidence = get_full_schema_confidence()
        self._rule_match_confidence = get_rule_match_confidence()
        self._hierarchy_expand_confidence = get_hierarchy_expand_confidence()
        self._embedding_confidence_base = get_embedding_confidence_base()
    
    async def retrieve(
        self,
        question: str,
        data_model: Optional[Any] = None,
        dimension_hierarchy: Optional[Dict[str, Any]] = None,
        top_k: Optional[int] = None,
        force_vector_search: bool = False,
    ) -> List[FieldCandidate]:
        """检索相关字段。
        
        三层策略：
        - L0: 字段数 <= threshold → 全量返回
        - L1: 规则匹配 → 类别筛选 + 层级扩展
        - L2: Embedding 兜底 → 规则匹配维度 < 3 时触发
        
        Args:
            question: 用户问题
            data_model: 数据模型（包含字段列表）
            dimension_hierarchy: 维度层级推断结果
            top_k: 返回数量限制（仅用于 Embedding 检索）
            force_vector_search: 强制使用向量检索（跳过 L0/L1）
        
        Returns:
            FieldCandidate 列表
        """
        if not question or not question.strip():
            return []
        
        # 获取字段列表
        fields = self._get_fields(data_model)
        if not fields:
            logger.warning("FieldRetriever: 无可用字段")
            return []
        
        field_count = len(fields)
        k = top_k or self.default_top_k
        
        # 分离维度和度量
        dimensions, measures = self._split_fields(fields)
        
        logger.info(
            f"FieldRetriever: 开始检索, question='{question[:30]}...', "
            f"fields={field_count}, dimensions={len(dimensions)}, measures={len(measures)}"
        )
        
        # 强制向量检索
        if force_vector_search:
            return await self._retrieve_with_embedding(
                question, data_model, dimension_hierarchy, k
            )
        
        # L0: 全量模式
        if field_count <= self.full_schema_threshold:
            logger.info(f"FieldRetriever: L0 全量模式 (fields={field_count} <= {self.full_schema_threshold})")
            return self._convert_all_fields(fields, dimension_hierarchy, "full_schema")
        
        # L1: 规则匹配模式
        logger.info(f"FieldRetriever: L1 规则匹配模式 (fields={field_count} > {self.full_schema_threshold})")
        
        # 维度使用规则匹配
        dimension_candidates = self._retrieve_dimensions_by_rules(
            question, dimensions, dimension_hierarchy
        )
        
        # 度量也使用规则匹配
        measure_candidates = self._retrieve_measures_by_rules(question, measures)
        
        # L2: 如果规则匹配结果太少，触发 Embedding 兜底
        need_embedding_for_dims = len(dimension_candidates) < self.min_rule_match_dimensions
        need_embedding_for_measures = len(measure_candidates) < self.min_rule_match_dimensions
        
        if need_embedding_for_dims or need_embedding_for_measures:
            logger.info(
                f"FieldRetriever: L2 Embedding 兜底 "
                f"(dims_matched={len(dimension_candidates)}, measures_matched={len(measure_candidates)}, "
                f"threshold={self.min_rule_match_dimensions})"
            )
            
            # 批量 embedding 检索（一次调用，同时检索维度和度量）
            embedding_results = await self._retrieve_with_embedding_batch(
                question, fields, dimension_hierarchy, k
            )
            
            # 分离 embedding 结果
            embedding_dims = [r for r in embedding_results if r.field_type == "dimension"]
            embedding_measures = [r for r in embedding_results if r.field_type == "measure"]
            
            # 合并去重
            if need_embedding_for_dims:
                dimension_candidates = self._merge_candidates(dimension_candidates, embedding_dims)
            if need_embedding_for_measures:
                measure_candidates = self._merge_candidates(measure_candidates, embedding_measures)
        
        # 合并维度和度量
        all_candidates = dimension_candidates + measure_candidates
        
        # 更新排名
        for i, c in enumerate(all_candidates, 1):
            c.rank = i
        
        logger.info(
            f"FieldRetriever: 检索完成, "
            f"dimensions={len(dimension_candidates)}, measures={len(measure_candidates)}, "
            f"total={len(all_candidates)}"
        )
        
        return all_candidates

    
    def _get_fields(self, data_model: Optional[Any]) -> List[Any]:
        """从数据模型获取字段列表。"""
        if data_model is None:
            return []
        
        if hasattr(data_model, 'fields'):
            return data_model.fields or []
        if hasattr(data_model, 'get_fields'):
            return data_model.get_fields() or []
        if isinstance(data_model, dict):
            return data_model.get('fields', [])
        
        return []
    
    def _split_fields(self, fields: List[Any]) -> tuple:
        """将字段分为维度和度量。
        
        Returns:
            (dimensions, measures) 元组
        """
        dimensions = []
        measures = []
        
        for field in fields:
            role = _get_field_attr(field, 'role', default='dimension')
            if isinstance(role, str):
                role = role.lower()
            
            if role == 'measure':
                measures.append(field)
            else:
                dimensions.append(field)
        
        return dimensions, measures
    
    def _retrieve_dimensions_by_rules(
        self,
        question: str,
        dimensions: List[Any],
        dimension_hierarchy: Optional[Dict[str, Any]],
    ) -> List[FieldCandidate]:
        """使用规则匹配检索维度。
        
        规则匹配策略：
        1. 字段名/标题直接匹配
        2. 类别关键词匹配 → 返回该类别所有维度
        3. 层级扩展 → 包含父/子维度
        """
        matched_field_names: Set[str] = set()
        expanded_field_names: Set[str] = set()
        
        # Step 1: 字段名/标题直接匹配
        direct_matches = match_field_name_or_caption(question, dimensions)
        matched_field_names.update(direct_matches)
        
        # Step 2: 类别关键词匹配
        matched_categories = extract_categories_by_rules(question)
        
        if matched_categories and dimension_hierarchy:
            # 从维度层级中找出匹配类别的所有维度
            for field_name, attrs in dimension_hierarchy.items():
                category = _get_field_attr(attrs, 'category', default=None)
                if category:
                    # category 可能是枚举或字符串
                    category_str = category.value if hasattr(category, 'value') else str(category)
                    if category_str.lower() in matched_categories:
                        matched_field_names.add(field_name)
        
        # Step 3: 层级扩展（父/子维度）
        if dimension_hierarchy:
            for field_name in list(matched_field_names):
                if field_name in dimension_hierarchy:
                    attrs = dimension_hierarchy[field_name]
                    parent = _get_field_attr(attrs, 'parent_dimension', default=None)
                    child = _get_field_attr(attrs, 'child_dimension', default=None)
                    if parent and parent not in matched_field_names:
                        expanded_field_names.add(parent)
                    if child and child not in matched_field_names:
                        expanded_field_names.add(child)
        
        # 转换为 FieldCandidate
        candidates = []
        all_matched = matched_field_names | expanded_field_names
        
        for field in dimensions:
            field_name = _get_field_attr(field, 'name', 'field_name', default='')
            if field_name in all_matched:
                # 判断来源和置信度
                if field_name in direct_matches:
                    source = "rule_match"
                    confidence = self._rule_match_confidence
                elif field_name in expanded_field_names:
                    source = "hierarchy_expand"
                    confidence = self._hierarchy_expand_confidence
                else:
                    source = "rule_match"
                    confidence = self._rule_match_confidence
                
                candidate = self._field_to_candidate(field, source, confidence)
                
                # 增强层级信息
                if dimension_hierarchy and field_name in dimension_hierarchy:
                    self._apply_hierarchy_attrs(candidate, dimension_hierarchy[field_name])
                
                candidates.append(candidate)
        
        return candidates
    
    def _retrieve_measures_by_rules(
        self,
        question: str,
        measures: List[Any],
    ) -> List[FieldCandidate]:
        """使用规则匹配检索度量。
        
        规则匹配策略：
        1. 字段名/标题直接匹配
        2. 度量类别关键词匹配（销售额、利润、成本等）
        """
        matched_field_names: Set[str] = set()
        
        # Step 1: 字段名/标题直接匹配
        direct_matches = match_field_name_or_caption(question, measures)
        matched_field_names.update(direct_matches)
        
        # Step 2: 度量关键词匹配
        category_keywords = get_category_keywords()
        measure_keywords = category_keywords.get("measure", set())
        question_lower = question.lower()
        
        for measure in measures:
            field_name = _get_field_attr(measure, 'name', 'field_name', default='')
            field_caption = _get_field_attr(measure, 'fieldCaption', 'field_caption', 'caption', default='')
            
            # 检查度量名称是否包含关键词
            caption_lower = field_caption.lower() if field_caption else ''
            for keyword in measure_keywords:
                # 关键词在问题中 且 关键词在字段名中
                if keyword in question_lower and keyword in caption_lower:
                    matched_field_names.add(field_name)
                    break
        
        # 转换为 FieldCandidate
        candidates = []
        for measure in measures:
            field_name = _get_field_attr(measure, 'name', 'field_name', default='')
            if field_name in matched_field_names:
                source = "rule_match" if field_name in direct_matches else "rule_match"
                confidence = self._rule_match_confidence
                
                candidate = self._field_to_candidate(measure, source, confidence)
                candidates.append(candidate)
        
        return candidates
    
    async def _retrieve_with_embedding_batch(
        self,
        question: str,
        fields: List[Any],
        dimension_hierarchy: Optional[Dict[str, Any]],
        top_k: int,
    ) -> List[FieldCandidate]:
        """批量使用 Embedding 检索所有字段（维度+度量）。
        
        只调用一次 embedding，同时检索维度和度量。
        """
        if not self._retriever:
            logger.warning("FieldRetriever: 无 Embedding 检索器，跳过批量检索")
            return []
        
        try:
            # 一次调用检索所有字段类型
            if hasattr(self._retriever, 'aretrieve'):
                results = await self._retriever.aretrieve(query=question, top_k=top_k * 2)
            else:
                results = self._retriever.retrieve(query=question, top_k=top_k * 2)
            
            candidates = []
            matched_categories: Set[str] = set()
            
            for result in results:
                chunk = result.field_chunk
                role = chunk.role.lower() if chunk.role else "dimension"
                
                confidence = min(result.score * self._embedding_confidence_base + 0.3, 1.0)
                
                candidate = FieldCandidate(
                    field_name=chunk.field_name,
                    field_caption=chunk.field_caption,
                    field_type=role,
                    data_type=chunk.data_type or "string",
                    description=chunk.metadata.get("description") if chunk.metadata else None,
                    sample_values=chunk.sample_values,
                    confidence=confidence,
                    source="embedding",
                    rank=result.rank,
                    category=chunk.category,
                    formula=chunk.formula,
                    logical_table_caption=chunk.logical_table_caption,
                )
                
                # 增强层级信息（仅维度）
                if role == "dimension" and dimension_hierarchy and chunk.field_name in dimension_hierarchy:
                    attrs = dimension_hierarchy[chunk.field_name]
                    self._apply_hierarchy_attrs(candidate, attrs)
                    if candidate.hierarchy_category:
                        matched_categories.add(candidate.hierarchy_category)
                
                candidates.append(candidate)
            
            # 按类别扩展维度（仅维度）
            if matched_categories and dimension_hierarchy:
                existing_names = {c.field_name for c in candidates}
                for field in fields:
                    field_name = _get_field_attr(field, 'name', 'field_name', default='')
                    role = _get_field_attr(field, 'role', default='dimension')
                    if isinstance(role, str):
                        role = role.lower()
                    
                    if role != 'dimension' or field_name in existing_names:
                        continue
                    
                    if field_name in dimension_hierarchy:
                        attrs = dimension_hierarchy[field_name]
                        category = _get_field_attr(attrs, 'category', default=None)
                        if category:
                            category_str = category.value if hasattr(category, 'value') else str(category)
                            if category_str.lower() in matched_categories:
                                candidate = self._field_to_candidate(
                                    field, "hierarchy_expand", self._hierarchy_expand_confidence
                                )
                                self._apply_hierarchy_attrs(candidate, attrs)
                                candidates.append(candidate)
            
            return candidates
            
        except Exception as e:
            logger.error(f"FieldRetriever: 批量 Embedding 检索失败: {e}")
            return []

    
    async def _retrieve_dimensions_with_embedding(
        self,
        question: str,
        dimensions: List[Any],
        dimension_hierarchy: Optional[Dict[str, Any]],
        top_k: int,
    ) -> List[FieldCandidate]:
        """使用 Embedding 检索维度（L2 兜底）。"""
        if not self._retriever:
            logger.warning("FieldRetriever: 无 Embedding 检索器，跳过 L2")
            return []
        
        try:
            # 使用 CascadeRetriever 检索
            if hasattr(self._retriever, 'aretrieve'):
                results = await self._retriever.aretrieve(query=question, top_k=top_k)
            else:
                results = self._retriever.retrieve(query=question, top_k=top_k)
            
            candidates = []
            matched_categories: Set[str] = set()
            
            for result in results:
                chunk = result.field_chunk
                # 只处理维度
                if chunk.role and chunk.role.lower() == 'measure':
                    continue
                
                confidence = min(result.score * self._embedding_confidence_base + 0.3, 1.0)
                
                candidate = FieldCandidate(
                    field_name=chunk.field_name,
                    field_caption=chunk.field_caption,
                    field_type="dimension",
                    data_type=chunk.data_type or "string",
                    description=chunk.metadata.get("description") if chunk.metadata else None,
                    sample_values=chunk.sample_values,
                    confidence=confidence,
                    source="embedding",
                    rank=result.rank,
                    category=chunk.category,
                    formula=chunk.formula,
                    logical_table_caption=chunk.logical_table_caption,
                )
                
                # 增强层级信息
                if dimension_hierarchy and chunk.field_name in dimension_hierarchy:
                    attrs = dimension_hierarchy[chunk.field_name]
                    self._apply_hierarchy_attrs(candidate, attrs)
                    # 记录类别用于扩展
                    if candidate.hierarchy_category:
                        matched_categories.add(candidate.hierarchy_category)
                
                candidates.append(candidate)
            
            # 按类别扩展：将同类别的其他维度也加入
            if matched_categories and dimension_hierarchy:
                existing_names = {c.field_name for c in candidates}
                for field in dimensions:
                    field_name = _get_field_attr(field, 'name', 'field_name', default='')
                    if field_name in existing_names:
                        continue
                    if field_name in dimension_hierarchy:
                        attrs = dimension_hierarchy[field_name]
                        category = _get_field_attr(attrs, 'category', default=None)
                        if category:
                            category_str = category.value if hasattr(category, 'value') else str(category)
                            if category_str.lower() in matched_categories:
                                candidate = self._field_to_candidate(
                                    field, "hierarchy_expand", self._hierarchy_expand_confidence
                                )
                                self._apply_hierarchy_attrs(candidate, attrs)
                                candidates.append(candidate)
            
            return candidates
            
        except Exception as e:
            logger.error(f"FieldRetriever: Embedding 检索失败: {e}")
            return []
    
    async def _retrieve_with_embedding(
        self,
        question: str,
        data_model: Optional[Any],
        dimension_hierarchy: Optional[Dict[str, Any]],
        top_k: int,
    ) -> List[FieldCandidate]:
        """强制使用 Embedding 检索所有字段。"""
        if not self._retriever:
            logger.warning("FieldRetriever: 无 Embedding 检索器，回退到全量模式")
            fields = self._get_fields(data_model)
            return self._convert_all_fields(fields, dimension_hierarchy, "full_schema")[:top_k]
        
        try:
            if hasattr(self._retriever, 'aretrieve'):
                results = await self._retriever.aretrieve(query=question, top_k=top_k)
            else:
                results = self._retriever.retrieve(query=question, top_k=top_k)
            
            candidates = []
            for result in results:
                chunk = result.field_chunk
                
                # 精确匹配置信度更高
                source = result.source.value if hasattr(result.source, 'value') else str(result.source)
                if source == "exact":
                    confidence = 1.0
                else:
                    confidence = min(result.score, 1.0)
                
                candidate = FieldCandidate(
                    field_name=chunk.field_name,
                    field_caption=chunk.field_caption,
                    field_type=chunk.role.lower() if chunk.role else "dimension",
                    data_type=chunk.data_type or "string",
                    description=chunk.metadata.get("description") if chunk.metadata else None,
                    sample_values=chunk.sample_values,
                    confidence=confidence,
                    source=source,
                    rank=result.rank,
                    category=chunk.category,
                    formula=chunk.formula,
                    logical_table_caption=chunk.logical_table_caption,
                )
                
                # 增强层级信息
                if dimension_hierarchy and chunk.field_name in dimension_hierarchy:
                    self._apply_hierarchy_attrs(candidate, dimension_hierarchy[chunk.field_name])
                
                candidates.append(candidate)
            
            # 按置信度排序
            candidates.sort(key=lambda x: x.confidence, reverse=True)
            
            return candidates
            
        except Exception as e:
            logger.error(f"FieldRetriever: Embedding 检索失败: {e}")
            return []

    
    def _convert_all_fields(
        self,
        fields: List[Any],
        dimension_hierarchy: Optional[Dict[str, Any]],
        source: str,
    ) -> List[FieldCandidate]:
        """将所有字段转换为 FieldCandidate。"""
        candidates = []
        
        for i, field in enumerate(fields, 1):
            candidate = self._field_to_candidate(field, source, self._full_schema_confidence)
            candidate.rank = i
            
            # 增强层级信息
            if dimension_hierarchy and candidate.field_name in dimension_hierarchy:
                self._apply_hierarchy_attrs(candidate, dimension_hierarchy[candidate.field_name])
            
            candidates.append(candidate)
        
        return candidates
    
    def _field_to_candidate(
        self,
        field: Any,
        source: str,
        confidence: float,
    ) -> FieldCandidate:
        """将字段转换为 FieldCandidate。"""
        field_name = _get_field_attr(field, 'name', 'field_name', default='')
        field_caption = _get_field_attr(field, 'fieldCaption', 'field_caption', 'caption', default=field_name)
        role = _get_field_attr(field, 'role', default='dimension')
        data_type = _get_field_attr(field, 'dataType', 'data_type', default='string')
        description = _get_field_attr(field, 'description', default=None)
        sample_values = _get_field_attr(field, 'sample_values', 'sampleValues', default=None)
        category = _get_field_attr(field, 'category', default=None)
        formula = _get_field_attr(field, 'formula', default=None)
        logical_table_caption = _get_field_attr(field, 'logicalTableCaption', 'logical_table_caption', default=None)
        
        # 处理 role
        if isinstance(role, str):
            field_type = role.lower()
        else:
            field_type = 'dimension'
        
        return FieldCandidate(
            field_name=field_name,
            field_caption=field_caption,
            field_type=field_type,
            data_type=data_type or 'string',
            description=description,
            sample_values=sample_values[:10] if sample_values else None,
            confidence=confidence,
            source=source,
            rank=1,
            category=category,
            formula=formula,
            logical_table_caption=logical_table_caption,
        )
    
    def _apply_hierarchy_attrs(
        self,
        candidate: FieldCandidate,
        attrs: Any,
    ) -> None:
        """将维度层级属性应用到候选字段。"""
        candidate.hierarchy_level = _get_field_attr(attrs, 'level', default=None)
        
        category = _get_field_attr(attrs, 'category', default=None)
        if category is not None:
            candidate.hierarchy_category = category.value if hasattr(category, 'value') else str(category)
        
        candidate.parent_dimension = _get_field_attr(attrs, 'parent_dimension', default=None)
        candidate.child_dimension = _get_field_attr(attrs, 'child_dimension', default=None)
    
    def _merge_candidates(
        self,
        primary: List[FieldCandidate],
        secondary: List[FieldCandidate],
    ) -> List[FieldCandidate]:
        """合并两个候选列表，去重。"""
        seen = {c.field_name for c in primary}
        merged = list(primary)
        
        for c in secondary:
            if c.field_name not in seen:
                merged.append(c)
                seen.add(c.field_name)
        
        return merged
    
    def set_retriever(self, retriever: Any) -> None:
        """设置检索器实例。"""
        self._retriever = retriever


__all__ = [
    "FieldCandidate",
    "FieldRetriever",
    "get_full_schema_threshold",
    "get_min_rule_match_dimensions",
    "get_default_top_k",
    "get_category_keywords",
    "extract_categories_by_rules",
    "match_field_name_or_caption",
]
