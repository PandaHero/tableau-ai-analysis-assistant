# -*- coding: utf-8 -*-
"""
FieldRetriever 组件 - 基于特征的字段检索

功能：
- 基于 FeatureExtractionOutput 进行批量 Top-K 检索
- 返回 FieldRAGResult（measures、dimensions、time_fields）
- 支持降级模式（terms 为空时返回全量字段）

检索策略：
1. 数据类型优先：先按 role（measure/dimension）过滤
2. 批量检索：使用批量检索而非逐个检索，提高效率
3. 级联检索：精确匹配 → 向量检索

配置来源：
- analytics_assistant/config/app.yaml -> semantic_parser.optimization.field_retriever
- analytics_assistant/config/app.yaml -> rag.retrieval（检索策略）

RAG 服务集成：
- 使用 RAGService.retrieval.search_async() 进行检索
- 索引由 IndexManager 管理，需要预先创建
- 检索策略由 app.yaml 配置决定，不硬编码

Requirements: 5.1-5.6 - FieldRetriever 字段检索
"""

import logging
from typing import Any, Dict, List, Optional

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.rag import get_rag_service
from analytics_assistant.src.infra.rag.exceptions import IndexNotFoundError
from analytics_assistant.src.core.schemas.field_candidate import FieldCandidate

from ..schemas.prefilter import FeatureExtractionOutput, FieldRAGResult

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════════════════

def _get_field_retriever_config() -> Dict[str, Any]:
    """获取 FieldRetriever 配置。"""
    try:
        config = get_config()
        return config.get_field_retriever_config()
    except Exception as e:
        logger.warning(f"无法加载 field_retriever 配置，使用默认值: {e}")
        return {}


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


# ═══════════════════════════════════════════════════════════════════════════
# FieldRetriever 组件
# ═══════════════════════════════════════════════════════════════════════════

class FieldRetriever:
    """字段检索器 - 基于特征的批量 Top-K 检索。
    
    使用 RAGService 进行检索，索引需要预先创建。
    
    配置来源：
    - field_retriever.top_k: 每类字段返回的候选数
    - field_retriever.fallback_multiplier: 降级时的倍数
    - rag.retrieval.retriever_type: 检索策略（由 RAGService 读取）
    
    Examples:
        >>> retriever = FieldRetriever()
        >>> result = await retriever.retrieve(
        ...     feature_output=feature_output,
        ...     data_model=data_model,
        ... )
        >>> print(f"度量: {len(result.measures)}, 维度: {len(result.dimensions)}")
    """
    
    INDEX_PREFIX = "fields_"
    
    # 默认配置
    _DEFAULT_TOP_K = 5
    _DEFAULT_FALLBACK_MULTIPLIER = 2.0
    
    def __init__(
        self,
        top_k: Optional[int] = None,
        fallback_multiplier: Optional[float] = None,
    ):
        """初始化 FieldRetriever。
        
        Args:
            top_k: 每类字段返回的候选数（None 从配置读取）
            fallback_multiplier: 降级时的倍数（None 从配置读取）
        """
        self._load_config()
        
        # 允许构造时覆盖配置
        if top_k is not None:
            self.top_k = top_k
        if fallback_multiplier is not None:
            self.fallback_multiplier = fallback_multiplier
        
        # 延迟初始化：获取 RAGService 单例
        # 注意：在 __init__ 中获取全局单例，避免模块加载时初始化
        self._rag_service = get_rag_service()
    
    def _load_config(self) -> None:
        """从配置文件加载参数。"""
        fr_config = _get_field_retriever_config()
        self.top_k = fr_config.get("top_k", self._DEFAULT_TOP_K)
        self.fallback_multiplier = float(
            fr_config.get("fallback_multiplier", self._DEFAULT_FALLBACK_MULTIPLIER)
        )
        
        logger.debug(
            f"FieldRetriever 配置: top_k={self.top_k}, "
            f"fallback_multiplier={self.fallback_multiplier}"
        )


    async def retrieve(
        self,
        feature_output: FeatureExtractionOutput,
        data_model: Optional[Any] = None,
        datasource_luid: Optional[str] = None,
    ) -> FieldRAGResult:
        """基于特征提取输出检索字段。
        
        Args:
            feature_output: FeatureExtractor 输出
            data_model: 数据模型（包含字段列表）
            datasource_luid: 数据源 ID（用于索引命名）
        
        Returns:
            FieldRAGResult 包含 measures、dimensions、time_fields
        """
        # 获取字段列表
        fields = self._get_fields(data_model)
        if not fields:
            logger.warning("FieldRetriever: 无可用字段")
            return FieldRAGResult()
        
        # 分离维度和度量
        dimensions, measures = self._split_fields(fields)
        
        logger.info(
            f"FieldRetriever: 开始检索, "
            f"required_measures={feature_output.required_measures}, "
            f"required_dimensions={feature_output.required_dimensions}"
        )
        
        # 获取索引名称
        index_name = self._get_index_name(datasource_luid)
        
        # 检查索引是否存在
        index_exists = self._check_index_exists(index_name)
        
        # 1. 检索度量字段
        measure_candidates = await self._retrieve_by_terms(
            terms=feature_output.required_measures,
            fields=measures,
            role="measure",
            index_name=index_name if index_exists else None,
        )
        
        # 2. 检索维度字段
        dimension_candidates = await self._retrieve_by_terms(
            terms=feature_output.required_dimensions,
            fields=dimensions,
            role="dimension",
            index_name=index_name if index_exists else None,
        )
        
        # 3. 检索时间字段
        time_candidates = self._retrieve_time_fields(dimensions)
        
        logger.info(
            f"FieldRetriever: 检索完成, "
            f"measures={len(measure_candidates)}, "
            f"dimensions={len(dimension_candidates)}, "
            f"time_fields={len(time_candidates)}"
        )
        
        return FieldRAGResult(
            measures=measure_candidates,
            dimensions=dimension_candidates,
            time_fields=time_candidates,
        )
    
    def _get_index_name(self, datasource_luid: Optional[str]) -> Optional[str]:
        """获取索引名称。"""
        if not datasource_luid:
            return None
        return f"{self.INDEX_PREFIX}{datasource_luid}"
    
    def _check_index_exists(self, index_name: Optional[str]) -> bool:
        """检查索引是否存在。"""
        if not index_name:
            return False
        try:
            retriever = self._rag_service.index.get_index(index_name)
            return retriever is not None
        except Exception:
            return False

    async def _retrieve_by_terms(
        self,
        terms: List[str],
        fields: List[Any],
        role: str,
        index_name: Optional[str] = None,
    ) -> List[FieldCandidate]:
        """根据术语检索字段。
        
        检索策略：
        1. 如果 terms 为空 → 降级模式，返回全量字段
        2. 如果索引存在 → 使用 RAGService 进行检索
        3. 如果索引不存在 → 使用精确匹配回退
        
        Args:
            terms: 检索术语列表（如 ["利润", "销售额"]）
            fields: 候选字段列表
            role: 字段角色（measure/dimension）
            index_name: 索引名称
        
        Returns:
            FieldCandidate 列表，按置信度降序
        """
        # 降级模式：terms 为空时返回全量字段
        if not terms:
            fallback_count = int(self.top_k * self.fallback_multiplier)
            logger.info(f"FieldRetriever: 降级模式, 返回 {fallback_count} 个 {role} 字段")
            return self._convert_fields_to_candidates(
                fields[:fallback_count],
                confidence=0.5,
                source="fallback",
            )
        
        # 如果没有索引，使用精确匹配
        if not index_name:
            logger.info(f"FieldRetriever: 无索引，使用精确匹配")
            return self._exact_match_fallback(terms, fields, role)
        
        # 使用 RAGService 进行检索
        try:
            query = " ".join(terms)
            
            # 使用 RAGService.retrieval.search_async()
            # 检索策略由 app.yaml 配置决定
            results = await self._rag_service.retrieval.search_async(
                index_name=index_name,
                query=query,
                top_k=self.top_k,
                filters={"role": role},
            )
            
            if results:
                candidates = []
                for result in results:
                    # 从 metadata 获取字段信息
                    metadata = result.metadata or {}
                    
                    # 将检索分数转换为置信度
                    confidence = min(result.score * 0.8 + 0.15, 0.95)
                    
                    candidates.append(FieldCandidate(
                        field_name=result.doc_id,
                        field_caption=metadata.get("field_caption", result.doc_id),
                        field_type=role,
                        data_type=metadata.get("data_type", "string"),
                        confidence=confidence,
                        source="rag",
                        rank=result.rank,
                        category=metadata.get("category"),
                        level=metadata.get("level"),
                        granularity=metadata.get("granularity"),
                        formula=metadata.get("formula"),
                        logical_table_caption=metadata.get("logical_table_caption"),
                        sample_values=metadata.get("sample_values"),
                    ))
                
                logger.info(f"FieldRetriever: RAG 检索返回 {len(candidates)} 个 {role} 字段")
                return candidates
            
            # RAG 检索无结果，回退到精确匹配
            logger.info(f"FieldRetriever: RAG 检索无结果，回退到精确匹配")
            return self._exact_match_fallback(terms, fields, role)
            
        except IndexNotFoundError:
            logger.warning(f"FieldRetriever: 索引 {index_name} 不存在，回退到精确匹配")
            return self._exact_match_fallback(terms, fields, role)
        except Exception as e:
            logger.warning(f"FieldRetriever: RAG 检索失败: {e}，回退到精确匹配")
            return self._exact_match_fallback(terms, fields, role)


    def _exact_match_fallback(
        self,
        terms: List[str],
        fields: List[Any],
        role: str,
    ) -> List[FieldCandidate]:
        """精确匹配回退方案。"""
        candidates = []
        matched_names = set()
        
        for term in terms:
            exact_matches = self._exact_match_by_term(term, fields)
            for field in exact_matches:
                field_name = _get_field_attr(field, 'name', 'field_name', default='')
                if field_name not in matched_names:
                    matched_names.add(field_name)
                    candidates.append(self._field_to_candidate(
                        field, confidence=0.9, source="exact_match"
                    ))
        
        # 如果精确匹配不足，补充更多字段
        if len(candidates) < self.top_k:
            for field in fields:
                field_name = _get_field_attr(field, 'name', 'field_name', default='')
                if field_name not in matched_names:
                    matched_names.add(field_name)
                    candidates.append(self._field_to_candidate(
                        field, confidence=0.5, source="fallback"
                    ))
                    if len(candidates) >= self.top_k:
                        break
        
        return candidates[:self.top_k]

    def _exact_match_by_term(self, term: str, fields: List[Any]) -> List[Any]:
        """精确匹配：字段名或标题包含术语。"""
        matched = []
        term_lower = term.lower()
        
        for field in fields:
            field_name = _get_field_attr(field, 'name', 'field_name', default='')
            field_caption = _get_field_attr(
                field, 'fieldCaption', 'field_caption', 'caption', default=''
            )
            
            # 检查术语是否在字段名或标题中
            if (term_lower in field_name.lower() or 
                term_lower in field_caption.lower()):
                matched.append(field)
        
        return matched

    def _retrieve_time_fields(self, dimensions: List[Any]) -> List[FieldCandidate]:
        """检索时间字段。
        
        根据数据类型和字段名识别时间字段。
        """
        time_candidates = []
        time_data_types = {"date", "datetime", "timestamp"}
        time_keywords = {"date", "time", "year", "month", "day", "日期", "时间", "年", "月", "日"}
        
        for field in dimensions:
            field_name = _get_field_attr(field, 'name', 'field_name', default='')
            field_caption = _get_field_attr(
                field, 'fieldCaption', 'field_caption', 'caption', default=''
            )
            data_type = _get_field_attr(field, 'dataType', 'data_type', default='')
            
            is_time_field = False
            confidence = 0.7
            
            # 检查数据类型
            if data_type.lower() in time_data_types:
                is_time_field = True
                confidence = 0.95
            # 检查字段名/标题
            elif any(kw in field_name.lower() or kw in field_caption.lower() 
                     for kw in time_keywords):
                is_time_field = True
                confidence = 0.85
            
            if is_time_field:
                time_candidates.append(self._field_to_candidate(
                    field, confidence=confidence, source="time_detection"
                ))
        
        # 按置信度排序
        time_candidates.sort(key=lambda c: c.confidence, reverse=True)
        
        return time_candidates[:self.top_k]

    # ═══════════════════════════════════════════════════════════════════════
    # 辅助方法
    # ═══════════════════════════════════════════════════════════════════════
    
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
    
    def _field_to_candidate(
        self,
        field: Any,
        confidence: float,
        source: str,
    ) -> FieldCandidate:
        """将字段转换为 FieldCandidate。
        
        包含维度层级信息和样例值，用于 Prompt 展示。
        """
        field_name = _get_field_attr(field, 'name', 'field_name', default='')
        field_caption = _get_field_attr(
            field, 'fieldCaption', 'field_caption', 'caption', default=field_name
        )
        role = _get_field_attr(field, 'role', default='dimension')
        data_type = _get_field_attr(field, 'dataType', 'data_type', default='string')
        
        # 获取维度层级信息
        category = _get_field_attr(field, 'category', 'hierarchy_category', default=None)
        level = _get_field_attr(field, 'level', 'hierarchy_level', default=None)
        granularity = _get_field_attr(field, 'granularity', default=None)
        
        # 获取样例值
        sample_values = _get_field_attr(field, 'sample_values', default=None)
        
        # 获取公式和逻辑表
        formula = _get_field_attr(field, 'calculation', 'formula', default=None)
        logical_table_caption = _get_field_attr(
            field, 'logical_table_caption', 'logicalTableCaption', default=None
        )
        
        return FieldCandidate(
            field_name=field_name,
            field_caption=field_caption,
            field_type=role if isinstance(role, str) else str(role),
            data_type=data_type if isinstance(data_type, str) else str(data_type),
            confidence=confidence,
            source=source,
            category=category,
            level=level,
            granularity=granularity,
            sample_values=sample_values,
            formula=formula,
            logical_table_caption=logical_table_caption,
        )
    
    def _convert_fields_to_candidates(
        self,
        fields: List[Any],
        confidence: float,
        source: str,
    ) -> List[FieldCandidate]:
        """批量将字段转换为 FieldCandidate。"""
        return [
            self._field_to_candidate(field, confidence, source)
            for field in fields
        ]


__all__ = [
    "FieldRetriever",
]
