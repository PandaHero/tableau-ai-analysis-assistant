# -*- coding: utf-8 -*-
"""
FieldRetriever 组件 - 基于特征的字段检索

功能：
- 基于 FeatureExtractionOutput 进行批量 Top-K 检索
- 返回 FieldRAGResult（measures、dimensions、time_fields）
- 支持降级模式（terms 为空时返回全量字段）

检索策略（两阶段）：
1. 粗召回（Recall）：RAG 向量检索，多取候选（top_k * rerank_candidate_multiplier）
2. 精排序（Rerank）：LLMReranker 对候选做语义重排序，返回 top_k 个最相关字段
3. 精确匹配：字段名或标题包含术语（作为补充）
4. 降级模式：terms 为空时返回全量字段

注意：
- 字段语义信息（aliases、business_description）在索引构建时已写入索引文本
- 检索时通过向量相似度自动匹配，无需额外的别名匹配逻辑
- 索引构建流程：data_loader.py -> FieldSemanticInference.infer() -> build_enhanced_index_text()
- Rerank 使用 LLMReranker，利用默认 LLM 理解中文语义做精排

配置来源：
- analytics_assistant/config/app.yaml -> semantic_parser.optimization.field_retriever
- analytics_assistant/config/app.yaml -> rag.retrieval（检索策略）
- analytics_assistant/config/app.yaml -> rag.reranking（重排序配置）

RAG 服务集成：
- 使用 RAGService.retrieval.search_async() 进行检索
- 使用 LLMReranker 进行重排序
- 索引由 IndexManager 管理，需要预先创建
- 检索策略由 app.yaml 配置决定，不硬编码

Requirements: 5.1-5.6 - FieldRetriever 字段检索
"""

import asyncio
import logging
import re
import threading
from typing import Any, Optional

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.ai import get_model_manager
from analytics_assistant.src.infra.rag import get_rag_service
from analytics_assistant.src.infra.rag.exceptions import IndexNotFoundError
from analytics_assistant.src.infra.rag.models import FieldChunk, RetrievalResult, RetrievalSource
from analytics_assistant.src.infra.rag.reranker import LLMReranker
from analytics_assistant.src.platform.tableau.artifact_keys import build_field_index_name
from analytics_assistant.src.core.schemas.field_candidate import FieldCandidate

from ..schemas.prefilter import FeatureExtractionOutput, FieldRAGResult

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════════════════

def _get_field_retriever_config() -> dict[str, Any]:
    """获取 FieldRetriever 配置。"""
    try:
        config = get_config()
        return config.get_field_retriever_config()
    except Exception as e:
        logger.warning(f"无法加载 field_retriever 配置，使用默认值: {e}")
        return {}

def _get_rerank_config() -> dict[str, Any]:
    """获取重排序配置（rag.reranking 节）。"""
    try:
        return get_config().get_nested_config("rag", "reranking")
    except Exception as e:
        logger.warning(f"无法加载 rerank 配置，使用默认值: {e}")
        return {}

# ═══════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════

def _get_field_attr(obj: Any, *names, default=None) -> Any:
    """从对象或字典中获取属性。"""
    if isinstance(obj, dict):
        for name in names:
            if name in obj:
                return obj[name]
    else:
        for name in names:
            val = getattr(obj, name, None)
            if val is not None:
                return val
    return default

_reranker_cache: dict[int, Optional[LLMReranker]] = {}
_reranker_lock = threading.Lock()


def _create_llm_reranker(top_k: int) -> Optional[LLMReranker]:
    """获取或创建 LLMReranker 实例（进程级缓存，避免每次请求创建新 LLM）。

    使用 ModelManager 获取默认 LLM，同时提供：
    - allm_call_fn：异步调用（arerank 优先使用，不阻塞 event loop）
    - llm_call_fn：同步调用（作为 fallback）
    失败时返回 None（降级为无 rerank）。

    Args:
        top_k: 重排序返回的结果数量

    Returns:
        LLMReranker 实例，或 None（创建失败时）
    """
    with _reranker_lock:
        if top_k in _reranker_cache:
            return _reranker_cache[top_k]

    try:
        manager = get_model_manager()
        llm = manager.create_llm()

        def llm_call_fn(prompt: str) -> str:
            response = llm.invoke(prompt)
            return response.content if hasattr(response, 'content') else str(response)

        async def allm_call_fn(prompt: str) -> str:
            response = await llm.ainvoke(prompt)
            return response.content if hasattr(response, 'content') else str(response)

        reranker = LLMReranker(top_k=top_k, llm_call_fn=llm_call_fn, allm_call_fn=allm_call_fn)
    except Exception as e:
        logger.warning(f"创建 LLMReranker 失败，将跳过重排序: {e}")
        reranker = None

    with _reranker_lock:
        _reranker_cache[top_k] = reranker
    return reranker

# ═══════════════════════════════════════════════════════════════════════════
# FieldRetriever 组件
# ═══════════════════════════════════════════════════════════════════════════

class FieldRetriever:
    """字段检索器 - 两阶段检索：粗召回 + LLM 精排。

    使用 RAGService 进行粗召回，LLMReranker 进行精排。
    索引在构建时已包含语义增强信息（aliases、business_description），
    粗召回通过向量相似度匹配，精排通过 LLM 理解语义相关性。

    配置来源：
    - field_retriever.top_k: 每类字段返回的候选数
    - field_retriever.fallback_multiplier: 降级时的倍数
    - rag.reranking.enabled: 是否启用重排序
    - rag.reranking.reranker_type: 重排序器类型
    - rag.reranking.rerank_top_k: 粗召回候选数量

    Examples:
        >>> retriever = FieldRetriever()
        >>> result = await retriever.retrieve(
        ...     feature_output=feature_output,
        ...     data_model=data_model,
        ... )
        >>> print(f"度量: {len(result.measures)}, 维度: {len(result.dimensions)}")
    """

    # 默认配置
    _DEFAULT_TOP_K = 5
    _DEFAULT_FALLBACK_MULTIPLIER = 2.0
    _DEFAULT_RERANK_CANDIDATE_MULTIPLIER = 3

    def __init__(
        self,
        top_k: Optional[int] = None,
        fallback_multiplier: Optional[float] = None,
        enable_rerank: Optional[bool] = None,
    ):
        """初始化 FieldRetriever。

        Args:
            top_k: 每类字段返回的候选数（None 从配置读取）
            fallback_multiplier: 降级时的倍数（None 从配置读取）
            enable_rerank: 是否启用 LLM rerank（None 从配置读取）
        """
        self._load_config()

        # 允许构造时覆盖配置
        if top_k is not None:
            self.top_k = top_k
        if fallback_multiplier is not None:
            self.fallback_multiplier = fallback_multiplier
        if enable_rerank is not None:
            self._rerank_enabled = enable_rerank

        # 延迟初始化：获取 RAGService 单例
        # 注意：在 __init__ 中获取全局单例，避免模块加载时初始化
        self._rag_service = get_rag_service()

        # 初始化 LLMReranker（如果配置启用）
        self._reranker: Optional[LLMReranker] = None
        if self._rerank_enabled:
            self._reranker = _create_llm_reranker(self.top_k)
            if self._reranker:
                logger.info("FieldRetriever: LLMReranker 已启用")
            else:
                logger.warning("FieldRetriever: LLMReranker 创建失败，将跳过重排序")
        else:
            logger.info("FieldRetriever: 当前请求跳过 LLMReranker")

    def _load_config(self) -> None:
        """从配置文件加载参数。"""
        fr_config = _get_field_retriever_config()
        self.top_k = fr_config.get("top_k", self._DEFAULT_TOP_K)
        self.fallback_multiplier = float(
            fr_config.get("fallback_multiplier", self._DEFAULT_FALLBACK_MULTIPLIER)
        )

        # 加载 rerank 配置
        rerank_config = _get_rerank_config()
        self._rerank_enabled = rerank_config.get("enabled", False)
        self._rerank_candidate_multiplier = self._DEFAULT_RERANK_CANDIDATE_MULTIPLIER

        # rerank_top_k 从配置读取，作为粗召回的候选数量上限
        self._rerank_top_k = rerank_config.get("rerank_top_k", 30)

        logger.debug(
            f"FieldRetriever 配置: top_k={self.top_k}, "
            f"fallback_multiplier={self.fallback_multiplier}, "
            f"rerank_enabled={self._rerank_enabled}, "
            f"rerank_top_k={self._rerank_top_k}"
        )

    async def retrieve(
        self,
        feature_output: FeatureExtractionOutput,
        data_model: Optional[Any] = None,
        datasource_luid: Optional[str] = None,
        tenant_site: Optional[str] = None,
        schema_hash: Optional[str] = None,
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
        index_name = self._get_index_name(
            datasource_luid,
            tenant_site=tenant_site,
            schema_hash=schema_hash,
        )

        # 检查索引是否存在
        index_exists = self._check_index_exists(index_name)

        # 1+2. 并行检索度量和维度字段（含 RAG 粗召回 + LLM 精排）
        measure_candidates, dimension_candidates = await asyncio.gather(
            self._retrieve_by_terms(
                terms=feature_output.required_measures,
                fields=measures,
                role="measure",
                index_name=index_name if index_exists else None,
            ),
            self._retrieve_by_terms(
                terms=feature_output.required_dimensions,
                fields=dimensions,
                role="dimension",
                index_name=index_name if index_exists else None,
            ),
        )

        # 3. 检索时间字段（纯本地逻辑，无需异步）
        time_candidates = self._retrieve_time_fields(dimensions)

        logger.info(
            f"FieldRetriever: 检索完成, "
            f"measures={len(measure_candidates)}, "
            f"dimensions={len(dimension_candidates)}, "
            f"time_fields={len(time_candidates)}"
        )

        field_samples = getattr(data_model, "_field_samples_cache", None)
        if field_samples:
            measure_candidates = self._attach_cached_sample_values(
                measure_candidates,
                field_samples,
            )
            dimension_candidates = self._attach_cached_sample_values(
                dimension_candidates,
                field_samples,
            )
            time_candidates = self._attach_cached_sample_values(
                time_candidates,
                field_samples,
            )

        return FieldRAGResult(
            measures=measure_candidates,
            dimensions=dimension_candidates,
            time_fields=time_candidates,
        )

    def _get_index_name(
        self,
        datasource_luid: Optional[str],
        *,
        tenant_site: Optional[str] = None,
        schema_hash: Optional[str] = None,
    ) -> Optional[str]:
        """获取索引名称。"""
        # 读取路径必须和写入路径使用同一份 schema 版本键，避免命中旧索引。
        if not datasource_luid or not schema_hash:
            return None
        return build_field_index_name(
            datasource_id=datasource_luid,
            site=tenant_site,
            schema_hash=schema_hash,
        )

    def _check_index_exists(self, index_name: Optional[str]) -> bool:
        """检查索引是否存在。"""
        if not index_name:
            return False
        try:
            retriever = self._rag_service.index.get_index(index_name)
            return retriever is not None
        except Exception as e:
            logger.warning(f"检查索引是否存在失败: index={index_name}, error={e}")
            return False

    def _attach_cached_sample_values(
        self,
        candidates: list[FieldCandidate],
        field_samples: dict[str, Any],
    ) -> list[FieldCandidate]:
        """用 values artifact 恢复字段样例，避免依赖语义索引中的旧样例。"""
        if not candidates or not field_samples:
            return candidates

        for candidate in candidates:
            if candidate.sample_values:
                continue
            sample_info = (
                field_samples.get(candidate.field_caption)
                or field_samples.get(candidate.field_name)
                or {}
            )
            sample_values = list(sample_info.get("sample_values") or [])
            if sample_values:
                candidate.sample_values = sample_values[:5]
        return candidates

    async def _retrieve_by_terms(
        self,
        terms: list[str],
        fields: list[Any],
        role: str,
        index_name: Optional[str] = None,
    ) -> list[FieldCandidate]:
        """根据术语检索字段（两阶段：粗召回 + LLM 精排）。

        检索策略（优先级从高到低）：
        1. RAG 粗召回：向量检索，多取候选（top_k * multiplier）
        2. LLM 精排：对粗召回结果做语义重排序，返回 top_k 个最相关字段
        3. 精确匹配：字段名或标题包含术语（作为补充）
        4. 降级模式：terms 为空时返回全量字段

        Args:
            terms: 检索术语列表（如 ["利润", "销售额"]）
            fields: 候选字段列表
            role: 字段角色（measure/dimension）
            index_name: 索引名称

        Returns:
            FieldCandidate 列表，按置信度降序
        """
        # 降级模式：terms 为空时返回全量字段（过滤不可查询的幽灵字段）
        if not terms:
            queryable_fields = [
                f for f in fields
                if _get_field_attr(f, 'queryable', default=True)
            ]
            fallback_count = int(self.top_k * self.fallback_multiplier)
            logger.info(f"FieldRetriever: 降级模式, 返回 {fallback_count} 个 {role} 字段")
            return self._convert_fields_to_candidates(
                queryable_fields[:fallback_count],
                confidence=0.5,
                source="fallback",
            )

        # 构建字段名到字段对象的映射
        field_map = {
            _get_field_attr(f, 'name', 'field_name', default=''): f
            for f in fields
        }
        field_caption_map = {
            _get_field_attr(f, 'fieldCaption', 'field_caption', 'caption', default=''): f
            for f in fields
        }

        candidates: list[FieldCandidate] = []
        matched_names: set = set()

        # 1. RAG 粗召回（多取候选，供 rerank 精排）
        # 如果启用 rerank，多取 rerank_candidate_multiplier 倍候选
        if self._reranker:
            recall_k = min(
                self.top_k * self._rerank_candidate_multiplier,
                self._rerank_top_k,
            )
        else:
            recall_k = self.top_k

        rag_results = []  # 保存原始 SearchResult，用于 rerank

        if index_name:
            try:
                query = " ".join(terms)
                results = await self._rag_service.retrieval.search_async(
                    index_name=index_name,
                    query=query,
                    top_k=recall_k,
                    filters={"role": role},
                )

                if results:
                    rag_results = results
                    logger.info(
                        f"FieldRetriever: RAG 粗召回 {len(results)} 个 {role} 字段 "
                        f"(recall_k={recall_k})"
                    )

            except IndexNotFoundError:
                logger.warning(f"FieldRetriever: 索引 {index_name} 不存在，使用精确匹配")
            except Exception as e:
                logger.warning(f"FieldRetriever: RAG 检索失败: {e}，使用精确匹配")

        # 2. LLM 精排（如果有 reranker 且有足够候选）
        if self._reranker and len(rag_results) > 1:
            rag_results = await self._rerank_results(
                terms=terms,
                results=rag_results,
            )

        # 3. 将 RAG 结果转换为 FieldCandidate
        if rag_results:
            # 归一化分数到 [0.5, 0.95]
            raw_scores = [r.score for r in rag_results]
            max_score = max(raw_scores) if raw_scores else 1.0
            min_score = min(raw_scores) if raw_scores else 0.0
            score_range = max_score - min_score

            for result in rag_results:
                field_name = result.doc_id
                if field_name in matched_names:
                    continue

                metadata = result.metadata or {}

                # 跳过不可查询的幽灵字段
                if metadata.get("queryable") is False:
                    logger.debug(f"FieldRetriever: 跳过幽灵字段 '{field_name}'（不可查询）")
                    continue

                matched_names.add(field_name)

                # 归一化分数：映射到 [0.5, 0.95]
                # 当所有分数相同时，使用原始分数的绝对值（clamp 到 [0, 1]）
                if score_range > 0:
                    normalized = (result.score - min_score) / score_range
                else:
                    normalized = min(max(result.score, 0.0), 1.0)
                confidence = 0.5 + normalized * 0.45

                candidates.append(FieldCandidate(
                    field_name=field_name,
                    field_caption=metadata.get("field_caption", field_name),
                    role=role,
                    data_type=metadata.get("data_type", "string"),
                    confidence=confidence,
                    source="rag+rerank" if self._reranker else "rag",
                    rank=result.rank,
                    category=metadata.get("category"),
                    level=metadata.get("level"),
                    granularity=metadata.get("granularity"),
                    formula=metadata.get("formula"),
                    logical_table_caption=metadata.get("logical_table_caption"),
                    business_description=metadata.get("business_description"),
                    aliases=metadata.get("aliases"),
                    measure_category=metadata.get("measure_category"),
                    sample_values=metadata.get("sample_values"),
                ))

        # 4. 精确匹配补充（当结果不足时）
        if len(candidates) < self.top_k:
            for term in terms:
                exact_matches = self._exact_match_by_term(term, fields)
                for field in exact_matches:
                    # 跳过不可查询的幽灵字段
                    if not _get_field_attr(field, 'queryable', default=True):
                        continue
                    field_name = _get_field_attr(field, 'name', 'field_name', default='')
                    if field_name and field_name not in matched_names:
                        matched_names.add(field_name)
                        candidates.append(self._field_to_candidate(
                            field, confidence=0.8, source="exact_match"
                        ))
                        if len(candidates) >= self.top_k:
                            break
                if len(candidates) >= self.top_k:
                    break

        # 5. 如果仍不足，补充更多字段
        if len(candidates) < self.top_k:
            for field in fields:
                # 跳过不可查询的幽灵字段
                if not _get_field_attr(field, 'queryable', default=True):
                    continue
                field_name = _get_field_attr(field, 'name', 'field_name', default='')
                if field_name and field_name not in matched_names:
                    matched_names.add(field_name)
                    candidates.append(self._field_to_candidate(
                        field, confidence=0.5, source="fallback"
                    ))
                    if len(candidates) >= self.top_k:
                        break

        return candidates[:self.top_k]

    async def _rerank_results(
        self,
        terms: list[str],
        results: list[Any],
    ) -> list[Any]:
        """使用 LLMReranker 对 RAG 结果做精排。

        将 SearchResult 转换为 RetrievalResult，调用 LLMReranker.arerank()，
        然后将排序后的结果映射回 SearchResult 顺序。

        Args:
            terms: 用户查询术语
            results: RAG 粗召回的 SearchResult 列表

        Returns:
            重排序后的 SearchResult 列表
        """
        if not self._reranker or len(results) <= 1:
            return results

        query = " ".join(terms)

        # SearchResult → RetrievalResult（LLMReranker 需要的格式）
        retrieval_results: list[RetrievalResult] = []
        result_map: dict[str, Any] = {}  # field_name → SearchResult

        for r in results:
            field_name = r.doc_id
            metadata = r.metadata or {}
            result_map[field_name] = r

            # 提取 sample_values（可能是列表或字符串）
            raw_samples = metadata.get("sample_values")
            sample_values = None
            if isinstance(raw_samples, list):
                sample_values = raw_samples[:5]

            chunk = FieldChunk(
                field_name=field_name,
                field_caption=metadata.get("field_caption", field_name),
                role=metadata.get("role", "dimension"),
                data_type=metadata.get("data_type", "string"),
                index_text=r.content or "",
                category=metadata.get("category"),
                formula=metadata.get("formula"),
                sample_values=sample_values,
                logical_table_caption=metadata.get("logical_table_caption"),
                metadata={
                    k: v for k, v in metadata.items()
                    if k not in {
                        "field_caption", "role", "data_type",
                        "category", "sample_values", "formula",
                        "logical_table_caption",
                    }
                },
            )
            retrieval_results.append(RetrievalResult(
                field_chunk=chunk,
                score=r.score,
                source=RetrievalSource.HYBRID,
                rank=r.rank,
            ))

        try:
            reranked = await self._reranker.arerank(
                query=query,
                candidates=retrieval_results,
                top_k=self.top_k,
            )

            # RetrievalResult → SearchResult 顺序
            reranked_results = []
            for rr in reranked:
                field_name = rr.field_chunk.field_name
                if field_name in result_map:
                    original = result_map[field_name]
                    # 更新分数为 rerank 后的分数
                    original.score = rr.score
                    original.rank = rr.rank
                    reranked_results.append(original)

            logger.info(
                f"FieldRetriever: LLM 精排完成, "
                f"输入 {len(retrieval_results)} → 输出 {len(reranked_results)} 个候选"
            )

            if reranked_results:
                for i, r in enumerate(reranked_results[:3]):
                    logger.info(
                        f"  Rerank[{i+1}]: {r.doc_id} "
                        f"(score={r.score:.3f})"
                    )

            return reranked_results

        except Exception as e:
            logger.warning(
                f"FieldRetriever: LLM 精排失败，使用原始 RAG 排序: {e}"
            )
            return results

    def _exact_match_by_term(self, term: str, fields: list[Any]) -> list[Any]:
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

    # 时间字段关键词：长度 ≥ 3 的可安全做子串匹配，短关键词需拆分匹配以防误判
    _TIME_SUBSTR_KEYWORDS = {
        "date", "time", "year", "month", "day", "week", "quarter",
        "日期", "时间", "季度", "yyyymm", "yyyymmdd",
    }
    # 短关键词：必须作为独立分段出现（按 _/- 拆分后精确匹配）
    _TIME_SEGMENT_KEYWORDS = {"dt", "yyyy", "mm", "dd", "年", "月", "日", "周"}

    def _retrieve_time_fields(self, dimensions: list[Any]) -> list[FieldCandidate]:
        """检索时间字段。

        根据数据类型和字段名识别时间字段。
        跳过不可查询的幽灵字段（queryable=False）。
        """
        time_candidates = []
        time_data_types = {"date", "datetime", "timestamp"}

        for field in dimensions:
            # 跳过不可查询的幽灵字段
            queryable = _get_field_attr(field, 'queryable', default=True)
            if not queryable:
                continue

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
            # 检查字段名/标题（长关键词用子串匹配）
            elif self._has_time_keyword(field_name, field_caption):
                is_time_field = True
                confidence = 0.85

            if is_time_field:
                time_candidates.append(self._field_to_candidate(
                    field, confidence=confidence, source="time_detection"
                ))

        # 按置信度排序
        time_candidates.sort(key=lambda c: c.confidence, reverse=True)

        return time_candidates[:self.top_k]

    @classmethod
    def _has_time_keyword(cls, field_name: str, field_caption: str) -> bool:
        """判断字段名/标题是否包含时间关键词。

        长关键词（≥3 字符）使用子串匹配；短关键词（dd/mm/dt 等）按 _/- 拆分后
        做精确段匹配，避免 "added" 误匹配 "dd"、"summary" 误匹配 "mm"。
        """
        name_lower = field_name.lower()
        caption_lower = field_caption.lower()

        # 长关键词：安全子串匹配
        for kw in cls._TIME_SUBSTR_KEYWORDS:
            if kw in name_lower or kw in caption_lower:
                return True

        # 短关键词：按 _ / - 拆分后精确段匹配
        name_segments = set(re.split(r"[_\-]", name_lower))
        caption_segments = set(re.split(r"[_\-]", caption_lower))
        all_segments = name_segments | caption_segments

        return bool(all_segments & cls._TIME_SEGMENT_KEYWORDS)

    # ═══════════════════════════════════════════════════════════════════════
    # 辅助方法
    # ═══════════════════════════════════════════════════════════════════════

    def _get_fields(self, data_model: Optional[Any]) -> list[Any]:
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

    def _split_fields(self, fields: list[Any]) -> tuple:
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
            role=role.lower() if isinstance(role, str) else str(role).lower(),
            data_type=data_type.lower() if isinstance(data_type, str) else str(data_type).lower(),
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
        fields: list[Any],
        confidence: float,
        source: str,
    ) -> list[FieldCandidate]:
        """批量将字段转换为 FieldCandidate。"""
        return [
            self._field_to_candidate(field, confidence, source)
            for field in fields
        ]

__all__ = [
    "FieldRetriever",
]
