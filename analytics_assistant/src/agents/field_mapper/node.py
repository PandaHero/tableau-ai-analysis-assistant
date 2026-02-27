# -*- coding: utf-8 -*-
"""
FieldMapper Node - RAG + LLM 混合节点

将业务术语从 SemanticOutput 映射到技术字段名。

策略：
1. 缓存查找：检查 CacheManager 缓存
2. RAG 检索：使用 infra/rag 的 CascadeRetriever（内部先精确匹配，再向量检索）
3. 快速路径：置信度 >= 0.9（包括精确匹配返回的 1.0），直接返回（无需 LLM）
4. LLM 回退：置信度 < 0.9，使用 LLM 从 top-k 候选中选择

设计原则：
- 使用 infra/rag 的统一检索器，不重复实现 RAG 逻辑
- 精确匹配由 CascadeRetriever 内部的 ExactRetriever 处理
- 使用 agents/base 的工具函数（get_llm, call_llm, parse_json_response）
- 使用 CacheManager 进行缓存，不直接操作 LangGraph Store
- 保持函数式风格，不强制继承

输入: SemanticOutput (语义解析器输出)
输出: MappedQuery (技术字段)
"""

import asyncio
import logging
import time
from typing import Any, Optional

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.storage import CacheManager
from analytics_assistant.src.core.schemas.semantic_output import SemanticOutput

from .components import CacheMixin, RAGMixin, LLMMixin
from .schemas import (
    FieldMappingConfig,
    FieldMapping,
    MappedQuery,
    FieldCandidate,
)

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# FieldMapperNode 类
# ══════════════════════════════════════════════════════════════════════════════

class FieldMapperNode(CacheMixin, RAGMixin, LLMMixin):
    """
    FieldMapper 节点 - RAG + LLM 混合
    使用以下策略将业务术语映射到技术字段名：
    1. 缓存查找（最快）- 使用 CacheManager
    2. 精确匹配快速路径
    3. RAG 检索 + 高置信度快速路径
    4. LLM 回退处理低置信度情况
    """
    
    def __init__(
        self,
        config: Optional[FieldMappingConfig] = None,
        retriever: Optional[Any] = None,
        field_chunks: Optional[list[Any]] = None,
    ):
        """
        初始化 FieldMapper 节点
        
        Args:
            config: FieldMappingConfig（使用默认值如果为 None）
            retriever: 检索器实例（来自 infra/rag）
            field_chunks: 字段元数据列表（用于精确匹配）
        """
        self.config = config or FieldMappingConfig.from_yaml()
        self._retriever = retriever
        self._field_chunks = field_chunks or []
        
        # 缓存管理器
        self._cache: Optional[CacheManager] = None
        if self.config.enable_cache:
            try:
                self._cache = CacheManager(
                    namespace="field_mapping",
                    default_ttl=self.config.cache_ttl,
                )
            except Exception as e:
                logger.warning(f"无法创建 CacheManager，缓存将不可用: {e}")
        
        # 统计信息
        self._total_mappings = 0
        self._cache_hits = 0
        self._fast_path_hits = 0
        self._llm_fallback_count = 0
    
    def get_stats(self) -> dict[str, Any]:
        """获取映射统计信息"""
        total = self._cache_hits + (self._total_mappings - self._cache_hits)
        hit_rate = self._cache_hits / total if total > 0 else 0.0
        return {
            "total_mappings": self._total_mappings,
            "cache_hits": self._cache_hits,
            "cache_hit_rate": hit_rate,
            "fast_path_hits": self._fast_path_hits,
            "llm_fallback_count": self._llm_fallback_count,
        }
    
    def set_field_chunks(self, field_chunks: list[Any]) -> None:
        """设置字段元数据"""
        self._field_chunks = field_chunks
        logger.debug(f"已设置 {len(field_chunks)} 个字段元数据")
    
    def set_retriever(self, retriever: Any) -> None:
        """设置检索器"""
        self._retriever = retriever
        logger.debug(f"已设置检索器: {type(retriever).__name__}")
    
    @property
    def rag_available(self) -> bool:
        """检查 RAG 是否可用"""
        return self._retriever is not None
    
    @property
    def field_count(self) -> int:
        """获取字段数量"""
        return len(self._field_chunks)

    # ========== 核心映射方法 ==========
    
    async def map_field(
        self,
        term: str,
        datasource_luid: str,
        context: Optional[str] = None,
        role_filter: Optional[str] = None,
        state: Optional[dict[str, Any]] = None,
        config: Optional[Any] = None,
    ) -> FieldMapping:
        """
        映射单个业务术语到技术字段
        
        Args:
            term: 要映射的业务术语
            datasource_luid: 数据源标识
            context: 可选的问题上下文（用于消歧）
            role_filter: 可选的角色过滤（"dimension" 或 "measure"）
            state: 可选的工作流状态
            config: 可选的 LangGraph 配置
        
        Returns:
            FieldMapping 包含映射的字段和元数据
        """
        start_time = time.time()
        self._total_mappings += 1
        
        if not term or not term.strip():
            return FieldMapping(
                business_term=term,
                technical_field=None,
                confidence=0.0,
                mapping_source="error",
                reasoning="提供了空术语"
            )
        
        term = term.strip()
        
        # 1. 检查缓存
        if self.config.enable_cache:
            cached = self._get_from_cache(term, datasource_luid, role_filter)
            if cached:
                self._cache_hits += 1
                latency = int((time.time() - start_time) * 1000)
                logger.debug(f"缓存命中: {term} -> {cached.get('technical_field')}")
                return FieldMapping(
                    business_term=term,
                    technical_field=cached.get("technical_field"),
                    confidence=cached.get("confidence", 0.0),
                    mapping_source="cache_hit",
                    category=cached.get("category"),
                    level=cached.get("level"),
                    granularity=cached.get("granularity"),
                    latency_ms=latency
                )
        
        # 2. RAG 检索（CascadeRetriever 内部会先尝试精确匹配）
        if not self.rag_available:
            logger.info(f"RAG 不可用，使用 LLM 直接匹配: {term}")
            return await self._map_field_with_llm_only(
                term=term,
                datasource_luid=datasource_luid,
                context=context,
                role_filter=role_filter,
                start_time=start_time,
            )
        
        try:
            retrieval_results = await self._retrieve(term, context, role_filter)
        except Exception as e:
            logger.error(f"RAG 检索失败 '{term}': {e}")
            return await self._map_field_with_llm_only(
                term=term,
                datasource_luid=datasource_luid,
                context=context,
                role_filter=role_filter,
                start_time=start_time,
            )
        
        if not retrieval_results:
            return await self._map_field_with_llm_only(
                term=term,
                datasource_luid=datasource_luid,
                context=context,
                role_filter=role_filter,
                start_time=start_time,
            )
        
        # 3. 高置信度快速路径（精确匹配返回 score=1.0）
        top_result = retrieval_results[0]
        top_score = getattr(top_result, 'score', 0.0)
        
        if top_score >= self.config.high_confidence_threshold:
            self._fast_path_hits += 1
            latency = int((time.time() - start_time) * 1000)
            
            chunk = getattr(top_result, 'field_chunk', top_result)
            field_name = getattr(chunk, 'field_name', None) or getattr(chunk, 'name', '')
            category = getattr(chunk, 'category', None)
            metadata = getattr(chunk, 'metadata', {}) or {}
            
            if self.config.enable_cache and field_name:
                self._put_to_cache(
                    term=term,
                    datasource_luid=datasource_luid,
                    technical_field=field_name,
                    confidence=top_score,
                    role_filter=role_filter,
                    category=category,
                    level=metadata.get("level"),
                    granularity=metadata.get("granularity")
                )
            
            logger.debug(f"快速路径: {term} -> {field_name} (confidence={top_score:.2f})")
            
            return FieldMapping(
                business_term=term,
                technical_field=field_name,
                confidence=top_score,
                mapping_source="rag_direct",
                category=category,
                level=metadata.get("level"),
                granularity=metadata.get("granularity"),
                latency_ms=latency
            )
        
        # 4. LLM 回退处理低置信度
        if self.config.enable_llm_fallback:
            return await self._map_field_with_llm_fallback(
                term=term,
                datasource_luid=datasource_luid,
                context=context,
                retrieval_results=retrieval_results,
                start_time=start_time,
                role_filter=role_filter,
            )
        
        # 5. 使用 RAG 结果作为回退（LLM 回退禁用时）
        latency = int((time.time() - start_time) * 1000)
        chunk = getattr(top_result, 'field_chunk', top_result)
        field_name = getattr(chunk, 'field_name', None) or getattr(chunk, 'name', '')
        
        return FieldMapping(
            business_term=term,
            technical_field=field_name,
            confidence=top_score,
            mapping_source="rag_direct",
            latency_ms=latency
        )

    async def _map_field_with_llm_fallback(
        self,
        term: str,
        datasource_luid: str,
        context: Optional[str],
        retrieval_results: list[Any],
        start_time: float,
        role_filter: Optional[str] = None,
    ) -> FieldMapping:
        """RAG 置信度低时使用 LLM 回退

        使用 _llm_select_from_candidates 统一逻辑。
        LLM 失败时回退到 RAG 最佳结果（与 llm_only 不同）。
        """
        candidates = self._convert_to_candidates(retrieval_results)

        result = await self._llm_select_from_candidates(
            term=term,
            candidates=candidates,
            datasource_luid=datasource_luid,
            context=context,
            role_filter=role_filter,
            start_time=start_time,
            mapping_source="rag_llm_fallback",
        )

        # _llm_select_from_candidates 异常时返回 mapping_source="error"
        # 此时回退到 RAG 最佳结果
        if result.mapping_source == "error" and retrieval_results:
            latency = int((time.time() - start_time) * 1000)
            top_result = retrieval_results[0]
            chunk = getattr(top_result, 'field_chunk', top_result)
            field_name = getattr(chunk, 'field_name', None) or getattr(chunk, 'name', '')
            top_score = getattr(top_result, 'score', 0.0)

            return FieldMapping(
                business_term=term,
                technical_field=field_name,
                confidence=top_score,
                mapping_source="rag_direct",
                reasoning=f"LLM 回退失败，使用 RAG 最佳结果: {result.reasoning}",
                latency_ms=latency,
            )

        return result
    
    async def _map_field_with_llm_only(
        self,
        term: str,
        datasource_luid: str,
        context: Optional[str] = None,
        role_filter: Optional[str] = None,
        start_time: Optional[float] = None,
    ) -> FieldMapping:
        """当 RAG 不可用时使用 LLM 直接匹配"""
        if start_time is None:
            start_time = time.time()

        if not self._field_chunks:
            latency = int((time.time() - start_time) * 1000)
            return FieldMapping(
                business_term=term,
                technical_field=None,
                confidence=0.0,
                mapping_source="llm_only",
                reasoning="没有可用的字段元数据",
                latency_ms=latency,
            )

        # 过滤字段
        filtered_chunks = self._field_chunks
        if role_filter:
            filtered_chunks = [
                c for c in self._field_chunks
                if not getattr(c, 'role', None)
                or getattr(c, 'role', '').lower() == role_filter.lower()
            ]
            if not filtered_chunks:
                filtered_chunks = self._field_chunks

        # 构建候选（限制数量避免 prompt 过长）
        max_candidates = min(len(filtered_chunks), 20)
        candidates = [
            FieldCandidate(
                field_name=getattr(chunk, 'field_name', None) or getattr(chunk, 'name', ''),
                field_caption=getattr(chunk, 'field_caption', None) or getattr(chunk, 'fieldCaption', ''),
                role=getattr(chunk, 'role', ''),
                data_type=getattr(chunk, 'data_type', None) or getattr(chunk, 'dataType', ''),
                confidence=0.5,
                category=getattr(chunk, 'category', None),
                level=getattr(chunk, 'metadata', {}).get("level") if hasattr(chunk, 'metadata') else None,
                granularity=getattr(chunk, 'metadata', {}).get("granularity") if hasattr(chunk, 'metadata') else None,
                sample_values=getattr(chunk, 'sample_values', None),
            )
            for chunk in filtered_chunks[:max_candidates]
        ]

        return await self._llm_select_from_candidates(
            term=term,
            candidates=candidates,
            datasource_luid=datasource_luid,
            context=context,
            role_filter=role_filter,
            start_time=start_time,
            mapping_source="llm_only",
        )

    # ========== 批量映射 ==========
    
    async def map_fields_batch(
        self,
        terms: list[str],
        datasource_luid: str,
        context: Optional[str] = None,
        role_filters: Optional[dict[str, str]] = None,
        state: Optional[dict[str, Any]] = None,
        config: Optional[Any] = None,
    ) -> dict[str, FieldMapping]:
        """
        并发映射多个业务术语
        
        Args:
            terms: 要映射的业务术语列表
            datasource_luid: 数据源标识
            context: 可选的问题上下文
            role_filters: 可选的术语 -> 角色过滤字典
            state: 可选的工作流状态
            config: 可选的 LangGraph 配置
        
        Returns:
            术语 -> FieldMapping 的字典
        """
        if not terms:
            return {}
        
        role_filters = role_filters or {}
        semaphore = asyncio.Semaphore(self.config.max_concurrency)
        
        async def map_with_semaphore(term: str) -> tuple[str, FieldMapping]:
            async with semaphore:
                result = await self.map_field(
                    term=term,
                    datasource_luid=datasource_luid,
                    context=context,
                    role_filter=role_filters.get(term),
                    state=state,
                    config=config,
                )
                return (term, result)
        
        tasks = [map_with_semaphore(term) for term in terms]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        mapping_results = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"映射任务失败: {result}")
                continue
            term, mapping = result
            mapping_results[term] = mapping
        
        return mapping_results

# ══════════════════════════════════════════════════════════════════════════════
# 节点函数
# ══════════════════════════════════════════════════════════════════════════════

async def field_mapper_node(
    state: dict[str, Any],
    config: Optional[Any] = None,
) -> dict[str, Any]:
    """
    FieldMapper 节点函数，用于 StateGraph
    
    从 SemanticOutput 提取业务术语并映射到技术字段。
    
    Args:
        state: 包含 semantic_output 的 VizQLState
        config: 运行时配置
    
    Returns:
        包含 mapped_query 的状态更新
    """
    start_time = time.time()
    
    semantic_output = state.get("semantic_output")
    if not semantic_output:
        logger.warning("state 中没有 semantic_output，跳过字段映射")
        return {
            "current_stage": "field_mapper",
            "field_mapper_complete": True,
            "mapped_query": None,
            "errors": [{
                "stage": "field_mapper",
                "error": "没有提供 semantic_output",
                "timestamp": time.time()
            }]
        }
    
    datasource_luid = state.get("datasource") or "default"
    question = state.get("question", "")
    
    # 提取要映射的术语
    terms_to_map = _extract_terms_from_semantic_output(semantic_output)
    
    if not terms_to_map:
        logger.info("语义输出中没有要映射的术语")
        mapped_query = MappedQuery(
            semantic_output=semantic_output,
            field_mappings={},
            overall_confidence=1.0,
        )
        return {
            "current_stage": "field_mapper",
            "field_mapper_complete": True,
            "mapped_query": mapped_query,
            "execution_path": ["field_mapper"]
        }
    
    # 获取或创建 mapper
    mapper = _get_field_mapper(state, config)
    
    try:
        mapping_results = await mapper.map_fields_batch(
            terms=list(terms_to_map.keys()),
            datasource_luid=datasource_luid,
            context=question,
            role_filters=terms_to_map,
            state=dict(state),
            config=config,
        )
    except Exception as e:
        logger.error(f"字段映射失败: {e}")
        return {
            "current_stage": "field_mapper",
            "field_mapper_complete": True,
            "mapped_query": None,
            "errors": [{
                "stage": "field_mapper",
                "error": str(e),
                "timestamp": time.time()
            }]
        }
    
    # 构建 FieldMapping 对象
    field_mappings: dict[str, FieldMapping] = {}
    
    for term, result in mapping_results.items():
        field_mappings[term] = FieldMapping(
            business_term=result.business_term,
            technical_field=result.technical_field or term,  # 无映射时回退到术语本身
            confidence=result.confidence,
            mapping_source=result.mapping_source,
            category=result.category,
            level=result.level,
            granularity=result.granularity,
            alternatives=result.alternatives,
        )
    
    # 构建 MappedQuery
    mapped_query = MappedQuery(
        semantic_output=semantic_output,
        field_mappings=field_mappings,
    )
    
    latency_ms = int((time.time() - start_time) * 1000)
    logger.info(
        f"字段映射完成: {len(field_mappings)} 个术语已映射, "
        f"overall_confidence={mapped_query.overall_confidence:.2f}, latency={latency_ms}ms"
    )
    
    return {
        "current_stage": "field_mapper",
        "field_mapper_complete": True,
        "mapped_query": mapped_query,
        "execution_path": ["field_mapper"]
    }

def _extract_terms_from_semantic_output(semantic_output: Any) -> dict[str, Optional[str]]:
    """
    从 SemanticOutput 提取业务术语
    
    注意：不再基于 Step1 的语义分类（measure/dimension）来限制字段搜索范围。
    因为：
    1. 对维度字段使用 COUNT/COUNTD 是完全合法的
    2. 用户语义上的"度量"可能在数据源中是维度字段
    3. VizQL 和 SQL 都支持对维度字段进行聚合计算
    
    Args:
        semantic_output: SemanticOutput 对象
        
    Returns:
        业务术语 -> None（不限制角色）的字典
    """
    terms = {}
    
    # 提取 what.measures - 不限制角色
    what = getattr(semantic_output, 'what', None)
    if what:
        for measure in getattr(what, 'measures', []) or []:
            field_name = getattr(measure, 'field_name', None)
            if field_name:
                terms[field_name] = None
    
    # 提取 where.dimensions 和 where.filters - 不限制角色
    where = getattr(semantic_output, 'where', None)
    if where:
        for dimension in getattr(where, 'dimensions', []) or []:
            field_name = getattr(dimension, 'field_name', None)
            if field_name:
                terms[field_name] = None
        
        for filter_spec in getattr(where, 'filters', []) or []:
            field_name = getattr(filter_spec, 'field_name', None)
            if field_name and field_name not in terms:
                terms[field_name] = None
    
    # 提取 computations 中的字段 - 不限制角色
    for computation in getattr(semantic_output, 'computations', []) or []:
        # DerivedComputation 使用 base_measures 而不是 target
        for base_measure in getattr(computation, 'base_measures', []) or []:
            if base_measure and base_measure not in terms:
                terms[base_measure] = None
        # partition_by 是字符串列表
        for partition_dim in getattr(computation, 'partition_by', []) or []:
            if partition_dim and partition_dim not in terms:
                terms[partition_dim] = None
        # subquery_dimensions 也是字符串列表
        for subquery_dim in getattr(computation, 'subquery_dimensions', []) or []:
            if subquery_dim and subquery_dim not in terms:
                terms[subquery_dim] = None
    
    return terms

def _get_field_mapper(state: dict[str, Any], config: Optional[Any] = None) -> FieldMapperNode:
    """
    获取或创建 FieldMapper 实例
    
    优先级：
    1. 从 state 获取已存在的 mapper
    2. 从 config 的 WorkflowContext 获取 data_model
    3. 从 state 获取 data_model
    4. 创建空的 mapper（LLM only 模式）
    
    注意：新创建的 mapper 会存入 state["_field_mapper"]
    """
    # 1. 检查 state 中是否已有 mapper
    if "_field_mapper" in state:
        return state["_field_mapper"]
    
    mapper = FieldMapperNode()
    
    # 2. 优先从 config 的 WorkflowContext 获取 data_model
    data_model = None
    datasource_luid = state.get("datasource") or "default"
    
    if config:
        try:
            # 尝试从 config 获取 WorkflowContext
            configurable = config.get("configurable", {}) if isinstance(config, dict) else getattr(config, "configurable", {})
            if configurable:
                ctx = configurable.get("workflow_context")
                if ctx:
                    data_model = getattr(ctx, 'data_model', None)
                    datasource_luid = getattr(ctx, 'datasource_luid', datasource_luid) or datasource_luid
                    logger.debug(f"从 WorkflowContext 获取 data_model: {data_model is not None}")
        except Exception as e:
            logger.warning(f"从 config 获取 WorkflowContext 失败: {e}")
    
    # 3. 从 state 获取 data_model
    if not data_model:
        data_model = state.get("data_model")
    
    # 4. 设置字段元数据并创建检索器
    if data_model:
        try:
            fields = getattr(data_model, 'fields', None)
            if fields:
                # load_metadata 会自动创建级联检索器
                mapper.load_metadata(
                    fields=fields,
                    datasource_luid=datasource_luid,
                )
                logger.info(f"FieldMapper 已初始化: {len(fields)} 个字段, RAG={mapper.rag_available}")
        except Exception as e:
            logger.warning(f"设置字段元数据失败: {e}")
    
    # 5. 存回 state（供后续调用复用）
    state["_field_mapper"] = mapper
    
    return mapper

__all__ = [
    "FieldMapperNode",
    "FieldCandidate",
    "FieldMapping",
    "field_mapper_node",
]
