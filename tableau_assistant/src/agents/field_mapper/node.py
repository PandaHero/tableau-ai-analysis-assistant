"""
FieldMapper Node - RAG + LLM Hybrid Node

Maps business terms from SemanticQuery to technical field names.

Strategy:
1. RAG retrieval: SemanticMapper.search()
2. Fast path: confidence >= 0.9, return directly (no LLM)
3. LLM fallback: confidence < 0.9, use LLM to select from top-k candidates

Middleware 集成：
- 从 config 获取 middleware 栈
- LLM fallback 时传递 middleware
- 支持历史消息上下文

Input: SemanticQuery (business terms)
Output: MappedQuery (technical fields)
"""

import asyncio
import hashlib
import logging
import time
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field

from langgraph.types import RunnableConfig

from .llm_selector import (
    LLMCandidateSelector,
    FieldCandidate,
    SingleSelectionResult,
)

from tableau_assistant.src.infra.ai.rag.assembler import (
    KnowledgeAssembler,
    AssemblerConfig,
    ChunkStrategy,
)
from tableau_assistant.src.infra.ai.rag.reranker import LLMReranker

logger = logging.getLogger(__name__)


# Configuration constants
HIGH_CONFIDENCE_THRESHOLD = 0.9
LOW_CONFIDENCE_THRESHOLD = 0.7
MAX_CONCURRENCY = 5
CACHE_TTL = 24 * 60 * 60  # 24 hours
TOP_K_CANDIDATES = 10
MAX_ALTERNATIVES = 3


@dataclass
class CachedMapping:
    """Cached field mapping entry"""
    business_term: str
    technical_field: str
    confidence: float
    timestamp: float
    datasource_luid: str
    category: Optional[str] = None
    level: Optional[int] = None
    granularity: Optional[str] = None


@dataclass
class FieldMappingConfig:
    """Configuration for FieldMapper Node"""
    high_confidence_threshold: float = HIGH_CONFIDENCE_THRESHOLD
    low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD
    max_concurrency: int = MAX_CONCURRENCY
    cache_ttl: int = CACHE_TTL
    top_k_candidates: int = TOP_K_CANDIDATES
    max_alternatives: int = MAX_ALTERNATIVES
    enable_cache: bool = True
    enable_llm_fallback: bool = True


@dataclass
class LatencyBreakdown:
    """延迟分解"""
    embedding_ms: int = 0
    retrieval_ms: int = 0
    rerank_ms: int = 0
    total_ms: int = 0


@dataclass
class MappingResult:
    """Result of mapping a single business term"""
    business_term: str
    technical_field: Optional[str]
    confidence: float
    mapping_source: str  # "rag_direct", "rag_llm_fallback", "cache", "llm_only"
    reasoning: Optional[str] = None
    alternatives: List[Dict[str, Any]] = field(default_factory=list)
    category: Optional[str] = None
    level: Optional[int] = None
    granularity: Optional[str] = None
    latency_ms: int = 0
    latency_breakdown: Optional[LatencyBreakdown] = None


class FieldMapperNode:
    """
    FieldMapper Node - RAG + LLM Hybrid
    
    Maps business terms to technical field names using:
    1. Cache lookup (fastest) - using LangGraph SqliteStore
    2. RAG retrieval with high confidence fast path
    3. LLM fallback for low confidence cases
    """
    
    def __init__(
        self,
        semantic_mapper: Optional[Any] = None,
        llm_selector: Optional[LLMCandidateSelector] = None,
        config: Optional[FieldMappingConfig] = None,
        store_manager: Optional[Any] = None,
        assembler: Optional[KnowledgeAssembler] = None,
        reranker: Optional[LLMReranker] = None
    ):
        """
        Initialize FieldMapper Node.
        
        Args:
            semantic_mapper: SemanticMapper instance (lazy loaded if None)
            llm_selector: LLMCandidateSelector instance (lazy loaded if None)
            config: FieldMappingConfig (uses defaults if None)
            store_manager: LangGraph SqliteStore for cache persistence
            assembler: KnowledgeAssembler for metadata loading
            reranker: LLMReranker for second-stage reranking
        """
        self._semantic_mapper = semantic_mapper
        self._llm_selector = llm_selector
        self.config = config or FieldMappingConfig()
        
        self._assembler = assembler
        self._reranker = reranker
        
        # Get LangGraph SqliteStore
        if store_manager is not None:
            self._store_manager = store_manager
        else:
            try:
                from tableau_assistant.src.infra.storage import get_langgraph_store
                self._store_manager = get_langgraph_store()
            except Exception as e:
                logger.warning(f"无法获取 LangGraph Store，缓存将不可用: {e}")
                self._store_manager = None
        
        # Statistics
        self._total_mappings = 0
        self._cache_hits = 0
        self._fast_path_hits = 0
        self._llm_fallback_count = 0
        self._rerank_count = 0
    
    # ========== Cache Methods ==========
    
    def _make_cache_key(self, term: str, datasource_luid: str) -> str:
        """Create cache key from term and datasource"""
        key_str = f"{datasource_luid}:{term.lower().strip()}"
        return hashlib.md5(key_str.encode('utf-8')).hexdigest()
    
    def _get_cache_namespace(self, datasource_luid: str) -> Tuple[str, ...]:
        """Get cache namespace for field mapping"""
        return ("field_mapping", datasource_luid)
    
    def _get_from_cache(self, term: str, datasource_luid: str) -> Optional[CachedMapping]:
        """Get cached mapping from LangGraph SqliteStore"""
        if self._store_manager is None or not self.config.enable_cache:
            return None
        
        try:
            key = self._make_cache_key(term, datasource_luid)
            item = self._store_manager.get(
                namespace=self._get_cache_namespace(datasource_luid),
                key=key
            )
            if item:
                data = item.value
                return CachedMapping(
                    business_term=data.get("business_term", term),
                    technical_field=data.get("technical_field"),
                    confidence=data.get("confidence", 0.0),
                    timestamp=data.get("timestamp", 0.0),
                    datasource_luid=data.get("datasource_luid", datasource_luid),
                    category=data.get("category"),
                    level=data.get("level"),
                    granularity=data.get("granularity"),
                )
            return None
        except Exception as e:
            logger.warning(f"从缓存获取映射失败: {e}")
            return None
    
    def _put_to_cache(
        self,
        term: str,
        datasource_luid: str,
        technical_field: str,
        confidence: float,
        category: Optional[str] = None,
        level: Optional[int] = None,
        granularity: Optional[str] = None
    ) -> bool:
        """Save mapping to LangGraph SqliteStore cache"""
        if self._store_manager is None or not self.config.enable_cache:
            return False
        
        try:
            key = self._make_cache_key(term, datasource_luid)
            self._store_manager.put(
                namespace=self._get_cache_namespace(datasource_luid),
                key=key,
                value={
                    "business_term": term,
                    "technical_field": technical_field,
                    "confidence": confidence,
                    "timestamp": time.time(),
                    "datasource_luid": datasource_luid,
                    "category": category,
                    "level": level,
                    "granularity": granularity,
                },
                ttl=self.config.cache_ttl
            )
            logger.debug(f"缓存映射: {term} -> {technical_field}")
            return True
        except Exception as e:
            logger.warning(f"保存映射到缓存失败: {e}")
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total = self._cache_hits + (self._total_mappings - self._cache_hits)
        hit_rate = self._cache_hits / total if total > 0 else 0.0
        return {
            "hits": self._cache_hits,
            "total_mappings": self._total_mappings,
            "hit_rate": hit_rate,
            "ttl_hours": self.config.cache_ttl / 3600,
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get mapping statistics"""
        return {
            "total_mappings": self._total_mappings,
            "cache_hits": self._cache_hits,
            "fast_path_hits": self._fast_path_hits,
            "llm_fallback_count": self._llm_fallback_count,
            "rerank_count": self._rerank_count,
            "cache_stats": self.get_cache_stats(),
            "has_assembler": self._assembler is not None,
            "has_reranker": self._reranker is not None,
        }

    
    # ========== Metadata Loading ==========
    
    def load_metadata(
        self,
        fields: List[Any],
        datasource_luid: str,
        embedding_provider: Optional[Any] = None
    ) -> int:
        """
        加载元数据并构建索引
        
        Args:
            fields: 字段元数据列表
            datasource_luid: 数据源标识
            embedding_provider: Embedding 提供者（可选）
        
        Returns:
            索引的字段数量
        """
        try:
            assembler_config = AssemblerConfig(
                chunk_strategy=ChunkStrategy.BY_FIELD,
                max_samples=5,
            )
            
            self._assembler = KnowledgeAssembler(
                datasource_luid=datasource_luid,
                config=assembler_config,
                embedding_provider=embedding_provider,
            )
            
            count = self._assembler.load_metadata(fields)
            logger.info(f"已加载 {count} 个字段到索引 (datasource={datasource_luid})")
            return count
        except Exception as e:
            logger.error(f"加载元数据失败: {e}")
            raise
    
    def set_reranker(self, reranker: LLMReranker) -> None:
        """设置 LLMReranker"""
        self._reranker = reranker
        logger.debug(f"已设置 LLMReranker: {type(reranker).__name__}")
    
    @property
    def assembler(self) -> Optional[KnowledgeAssembler]:
        return self._assembler
    
    @property
    def reranker(self) -> Optional[LLMReranker]:
        return self._reranker
    
    @property
    def semantic_mapper(self):
        """Lazy load SemanticMapper"""
        if self._semantic_mapper is None:
            raise ValueError(
                "SemanticMapper not initialized. "
                "Please provide semantic_mapper in constructor or call set_semantic_mapper()."
            )
        return self._semantic_mapper
    
    def set_semantic_mapper(self, semantic_mapper: Any) -> None:
        """Set SemanticMapper instance"""
        self._semantic_mapper = semantic_mapper
    
    @property
    def llm_selector(self) -> LLMCandidateSelector:
        """Lazy load LLMCandidateSelector"""
        if self._llm_selector is None:
            self._llm_selector = LLMCandidateSelector(
                confidence_threshold=self.config.low_confidence_threshold
            )
        return self._llm_selector
    
    # ========== Core Mapping Methods ==========
    
    async def map_field(
        self,
        term: str,
        datasource_luid: str,
        context: Optional[str] = None,
        role_filter: Optional[str] = None,
        state: Optional[Dict[str, Any]] = None,
        config: Optional[Any] = None,
    ) -> MappingResult:
        """
        Map a single business term to technical field.
        
        Args:
            term: Business term to map
            datasource_luid: Datasource identifier
            context: Optional question context for disambiguation
            role_filter: Optional role filter ("dimension" or "measure")
        
        Returns:
            MappingResult with mapped field and metadata
        """
        start_time = time.time()
        self._total_mappings += 1
        
        if not term or not term.strip():
            return MappingResult(
                business_term=term,
                technical_field=None,
                confidence=0.0,
                mapping_source="error",
                reasoning="Empty term provided"
            )
        
        term = term.strip()
        
        # 1. Check cache
        if self.config.enable_cache:
            cached = self._get_from_cache(term, datasource_luid)
            if cached:
                self._cache_hits += 1
                latency = int((time.time() - start_time) * 1000)
                logger.debug(f"Cache hit: {term} -> {cached.technical_field}")
                return MappingResult(
                    business_term=term,
                    technical_field=cached.technical_field,
                    confidence=cached.confidence,
                    mapping_source="cache_hit",
                    category=cached.category,
                    level=cached.level,
                    granularity=cached.granularity,
                    latency_ms=latency
                )
        
        # 2. Check if RAG is available
        rag_available = (
            self._semantic_mapper is not None and 
            hasattr(self._semantic_mapper, 'rag_available') and 
            self._semantic_mapper.rag_available
        )
        
        # 3. If RAG not available, use LLM directly
        if not rag_available:
            logger.info(f"RAG 不可用，使用 LLM 直接匹配: {term}")
            return await self._map_field_with_llm_only(
                term=term,
                datasource_luid=datasource_luid,
                context=context,
                role_filter=role_filter,
                start_time=start_time,
                state=state,
                config=config,
            )
        
        # 4. RAG retrieval
        try:
            rag_result = self.semantic_mapper.map_field(
                term=term,
                context=context,
                role_filter=role_filter
            )
        except Exception as e:
            logger.error(f"RAG retrieval failed for '{term}': {e}")
            return await self._map_field_with_llm_only(
                term=term,
                datasource_luid=datasource_luid,
                context=context,
                role_filter=role_filter,
                start_time=start_time,
                state=state,
                config=config,
            )
        
        # 5. High confidence fast path
        if rag_result.confidence >= self.config.high_confidence_threshold:
            self._fast_path_hits += 1
            latency = int((time.time() - start_time) * 1000)
            
            category, level, granularity = self._extract_hierarchy_info(rag_result)
            latency_breakdown = self._extract_latency_breakdown(rag_result, latency)
            
            if self.config.enable_cache and rag_result.matched_field:
                self._put_to_cache(
                    term=term,
                    datasource_luid=datasource_luid,
                    technical_field=rag_result.matched_field,
                    confidence=rag_result.confidence,
                    category=category,
                    level=level,
                    granularity=granularity
                )
            
            logger.debug(
                f"Fast path: {term} -> {rag_result.matched_field} "
                f"(confidence={rag_result.confidence:.2f})"
            )
            
            return MappingResult(
                business_term=term,
                technical_field=rag_result.matched_field,
                confidence=rag_result.confidence,
                mapping_source="rag_direct",
                category=category,
                level=level,
                granularity=granularity,
                latency_ms=latency,
                latency_breakdown=latency_breakdown
            )
        
        # 6. LLM fallback for low confidence
        if self.config.enable_llm_fallback and rag_result.retrieval_results:
            return await self._map_field_with_llm_fallback(
                term=term,
                datasource_luid=datasource_luid,
                context=context,
                rag_result=rag_result,
                start_time=start_time,
                state=state,
                config=config,
            )
        
        # 7. Use RAG result as fallback
        latency = int((time.time() - start_time) * 1000)
        category, level, granularity = self._extract_hierarchy_info(rag_result)
        latency_breakdown = self._extract_latency_breakdown(rag_result, latency)
        
        alternatives = []
        if rag_result.confidence < self.config.low_confidence_threshold:
            alternatives = [
                {"technical_field": alt, "confidence": 0.0}
                for alt in rag_result.alternatives[:self.config.max_alternatives]
            ]
        
        return MappingResult(
            business_term=term,
            technical_field=rag_result.matched_field,
            confidence=rag_result.confidence,
            mapping_source="rag_direct",
            alternatives=alternatives,
            category=category,
            level=level,
            granularity=granularity,
            latency_ms=latency,
            latency_breakdown=latency_breakdown
        )

    
    async def _map_field_with_llm_fallback(
        self,
        term: str,
        datasource_luid: str,
        context: Optional[str],
        rag_result: Any,
        start_time: float,
        state: Optional[Dict[str, Any]] = None,
        config: Optional[Any] = None,
    ) -> MappingResult:
        """LLM fallback when RAG confidence is low"""
        self._llm_fallback_count += 1
        
        candidates = self._convert_to_candidates(rag_result.retrieval_results)
        
        # 从 config 获取 middleware 并设置到 llm_selector
        middleware = None
        if config and "configurable" in config:
            middleware = config["configurable"].get("middleware")
        if middleware:
            self.llm_selector.set_middleware(middleware)
        
        try:
            selection = await self.llm_selector.select(
                term=term,
                candidates=candidates,
                context=context,
                state=state,
                config=config,
            )
            
            latency = int((time.time() - start_time) * 1000)
            
            selected_candidate = next(
                (c for c in candidates if c.field_name == selection.selected_field),
                None
            )
            
            category = selected_candidate.category if selected_candidate else None
            level = selected_candidate.level if selected_candidate else None
            granularity = selected_candidate.granularity if selected_candidate else None
            
            if self.config.enable_cache and selection.selected_field:
                self._put_to_cache(
                    term=term,
                    datasource_luid=datasource_luid,
                    technical_field=selection.selected_field,
                    confidence=selection.confidence,
                    category=category,
                    level=level,
                    granularity=granularity
                )
            
            latency_breakdown = self._extract_latency_breakdown(rag_result, latency)
            
            # 转换 alternatives 格式以匹配 AlternativeMapping
            formatted_alternatives = [
                {
                    "technical_field": c.field_name,
                    "confidence": c.score,
                    "reason": c.field_caption or ""
                }
                for c in candidates[:self.config.max_alternatives]
                if c.field_name != selection.selected_field
            ] if selection.confidence < self.config.low_confidence_threshold else []
            
            logger.debug(
                f"LLM fallback: {term} -> {selection.selected_field} "
                f"(confidence={selection.confidence:.2f})"
            )
            
            return MappingResult(
                business_term=term,
                technical_field=selection.selected_field,
                confidence=selection.confidence,
                mapping_source="rag_llm_fallback",
                reasoning=selection.reasoning,
                alternatives=formatted_alternatives,
                category=category,
                level=level,
                granularity=granularity,
                latency_ms=latency,
                latency_breakdown=latency_breakdown
            )
        except Exception as e:
            logger.error(f"LLM selection failed for '{term}': {e}")
            # Fall through to use RAG result
            latency = int((time.time() - start_time) * 1000)
            category, level, granularity = self._extract_hierarchy_info(rag_result)
            
            return MappingResult(
                business_term=term,
                technical_field=rag_result.matched_field,
                confidence=rag_result.confidence,
                mapping_source="rag_direct",
                reasoning=f"LLM fallback failed: {e}",
                category=category,
                level=level,
                granularity=granularity,
                latency_ms=latency
            )
    
    async def _map_field_with_llm_only(
        self,
        term: str,
        datasource_luid: str,
        context: Optional[str] = None,
        role_filter: Optional[str] = None,
        start_time: Optional[float] = None,
        state: Optional[Dict[str, Any]] = None,
        config: Optional[Any] = None,
    ) -> MappingResult:
        """使用 LLM 直接进行字段匹配（当 RAG 不可用时）"""
        if start_time is None:
            start_time = time.time()
        
        all_chunks = []
        if self._semantic_mapper is not None:
            all_chunks = self._semantic_mapper.field_indexer.get_all_chunks()
        
        if not all_chunks:
            latency = int((time.time() - start_time) * 1000)
            return MappingResult(
                business_term=term,
                technical_field=None,
                confidence=0.0,
                mapping_source="llm_only",
                reasoning="No field metadata available",
                latency_ms=latency
            )
        
        # Filter by role
        filtered_chunks = all_chunks
        if role_filter:
            filtered_chunks = [
                c for c in all_chunks 
                if c.role and c.role.lower() == role_filter.lower()
            ]
            if not filtered_chunks:
                filtered_chunks = all_chunks
        
        # Build candidates (limit to avoid long prompts)
        max_candidates = min(len(filtered_chunks), 20)
        candidates = []
        for chunk in filtered_chunks[:max_candidates]:
            candidates.append(FieldCandidate(
                field_name=chunk.field_name,
                field_caption=chunk.field_caption,
                role=chunk.role,
                data_type=chunk.data_type,
                score=0.5,
                category=chunk.category,
                level=chunk.metadata.get("level") if chunk.metadata else None,
                granularity=chunk.metadata.get("granularity") if chunk.metadata else None,
                sample_values=chunk.sample_values
            ))
        
        # 从 config 获取 middleware 并设置到 llm_selector
        middleware = None
        if config and "configurable" in config:
            middleware = config["configurable"].get("middleware")
        if middleware:
            self.llm_selector.set_middleware(middleware)
        
        try:
            self._llm_fallback_count += 1
            selection = await self.llm_selector.select(
                term=term,
                candidates=candidates,
                context=context,
                state=state,
                config=config,
            )
            
            latency = int((time.time() - start_time) * 1000)
            
            selected_candidate = next(
                (c for c in candidates if c.field_name == selection.selected_field),
                None
            )
            
            category = selected_candidate.category if selected_candidate else None
            level = selected_candidate.level if selected_candidate else None
            granularity = selected_candidate.granularity if selected_candidate else None
            
            # 转换 alternatives 格式以匹配 AlternativeMapping
            alternatives = [
                {
                    "technical_field": c.field_name,
                    "confidence": c.score,
                    "reason": c.field_caption or ""
                }
                for c in candidates[:self.config.max_alternatives]
                if c.field_name != selection.selected_field
            ] if selection.confidence < self.config.low_confidence_threshold else []
            
            if self.config.enable_cache and selection.selected_field:
                self._put_to_cache(
                    term=term,
                    datasource_luid=datasource_luid,
                    technical_field=selection.selected_field,
                    confidence=selection.confidence,
                    category=category,
                    level=level,
                    granularity=granularity
                )
            
            logger.debug(
                f"LLM only: {term} -> {selection.selected_field} "
                f"(confidence={selection.confidence:.2f})"
            )
            
            return MappingResult(
                business_term=term,
                technical_field=selection.selected_field,
                confidence=selection.confidence,
                mapping_source="llm_only",
                reasoning=selection.reasoning,
                alternatives=alternatives,
                category=category,
                level=level,
                granularity=granularity,
                latency_ms=latency
            )
            
        except Exception as e:
            logger.error(f"LLM selection failed for '{term}': {e}")
            latency = int((time.time() - start_time) * 1000)
            return MappingResult(
                business_term=term,
                technical_field=None,
                confidence=0.0,
                mapping_source="error",
                reasoning=f"LLM selection failed: {e}",
                latency_ms=latency
            )

    
    async def map_fields_batch(
        self,
        terms: List[str],
        datasource_luid: str,
        context: Optional[str] = None,
        role_filters: Optional[Dict[str, str]] = None,
        state: Optional[Dict[str, Any]] = None,
        config: Optional[Any] = None,
    ) -> Dict[str, MappingResult]:
        """
        Map multiple business terms concurrently.
        
        Args:
            terms: List of business terms to map
            datasource_luid: Datasource identifier
            context: Optional question context
            role_filters: Optional dict of term -> role filter
            state: Optional workflow state (for middleware)
            config: Optional LangGraph config (for middleware)
        
        Returns:
            Dict mapping term -> MappingResult
        """
        if not terms:
            return {}
        
        role_filters = role_filters or {}
        semaphore = asyncio.Semaphore(self.config.max_concurrency)
        
        async def map_with_semaphore(term: str) -> Tuple[str, MappingResult]:
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
                logger.error(f"Mapping task failed: {result}")
                continue
            term, mapping = result
            mapping_results[term] = mapping
        
        return mapping_results
    
    # ========== Helper Methods ==========
    
    def _convert_to_candidates(
        self,
        retrieval_results: List[Any]
    ) -> List[FieldCandidate]:
        """Convert RAG retrieval results to FieldCandidate list"""
        candidates = []
        for r in retrieval_results[:self.config.top_k_candidates]:
            chunk = r.field_chunk
            candidates.append(FieldCandidate(
                field_name=chunk.field_name,
                field_caption=chunk.field_caption,
                role=chunk.role,
                data_type=chunk.data_type,
                score=r.score,
                category=chunk.category,
                level=chunk.metadata.get("level") if chunk.metadata else None,
                granularity=chunk.metadata.get("granularity") if chunk.metadata else None,
                sample_values=chunk.sample_values
            ))
        return candidates
    
    def _extract_hierarchy_info(
        self,
        rag_result: Any
    ) -> Tuple[Optional[str], Optional[int], Optional[str]]:
        """Extract dimension hierarchy info from RAG result"""
        if not rag_result.retrieval_results:
            return None, None, None
        
        top_result = rag_result.retrieval_results[0]
        chunk = top_result.field_chunk
        
        category = chunk.category
        level = chunk.metadata.get("level") if chunk.metadata else None
        granularity = chunk.metadata.get("granularity") if chunk.metadata else None
        
        return category, level, granularity
    
    def _extract_latency_breakdown(
        self,
        rag_result: Any,
        total_latency: int
    ) -> Optional[LatencyBreakdown]:
        """Extract latency breakdown from RAG result"""
        if hasattr(rag_result, 'latency_breakdown') and rag_result.latency_breakdown:
            lb = rag_result.latency_breakdown
            return LatencyBreakdown(
                embedding_ms=lb.embedding_ms,
                retrieval_ms=lb.retrieval_ms,
                rerank_ms=lb.rerank_ms,
                total_ms=total_latency
            )
        return None


# ========== Node Function ==========

async def field_mapper_node(
    state: Dict[str, Any],
    config: Optional[RunnableConfig] = None,
) -> Dict[str, Any]:
    """
    FieldMapper Node function for StateGraph.
    
    Extracts business terms from SemanticQuery and maps them to technical fields.
    
    Middleware 集成：
    - 从 config 获取 middleware 栈
    - LLM fallback 时传递 middleware
    - 使用 state.messages 作为历史上下文
    
    Args:
        state: VizQLState containing semantic_query (SemanticQuery Pydantic object)
        config: 运行时配置（包含 middleware）
    
    Returns:
        State update with mapped_query (MappedQuery Pydantic object)
    
    **Validates: Requirements 9.3**
    """
    from tableau_assistant.src.core.models.field_mapping import MappedQuery, FieldMapping
    from tableau_assistant.src.agents.base.middleware_runner import get_middleware_from_config
    
    start_time = time.time()
    
    semantic_query = state.get("semantic_query")
    if not semantic_query:
        logger.warning("No semantic_query in state, skipping field mapping")
        return {
            "current_stage": "field_mapper",
            "field_mapper_complete": True,
            "mapped_query": None,
            "errors": [{
                "stage": "field_mapper",
                "error": "No semantic_query provided",
                "timestamp": time.time()
            }]
        }
    
    datasource_luid = state.get("datasource") or "default"
    question = state.get("question", "")
    
    terms_to_map = _extract_terms_from_semantic_query(semantic_query)
    
    if not terms_to_map:
        logger.info("No terms to map in semantic query")
        # 返回 MappedQuery Pydantic 对象
        mapped_query = MappedQuery(
            semantic_query=semantic_query,
            field_mappings={},
            overall_confidence=1.0,
        )
        return {
            "current_stage": "field_mapper",
            "field_mapper_complete": True,
            "mapped_query": mapped_query,
            "execution_path": ["field_mapper"]
        }
    
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
        logger.error(f"Field mapping failed: {e}")
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
    
    # 构建 FieldMapping Pydantic 对象
    field_mappings: Dict[str, FieldMapping] = {}
    
    for term, result in mapping_results.items():
        field_mappings[term] = FieldMapping(
            business_term=result.business_term,
            technical_field=result.technical_field or term,  # fallback to term if no mapping
            confidence=result.confidence,
            mapping_source=result.mapping_source,
            category=result.category,
            level=result.level,
            granularity=result.granularity,
            alternatives=result.alternatives,
        )
    
    # 构建 MappedQuery Pydantic 对象
    mapped_query = MappedQuery(
        semantic_query=semantic_query,
        field_mappings=field_mappings,
    )
    
    latency_ms = int((time.time() - start_time) * 1000)
    logger.info(
        f"Field mapping complete: {len(field_mappings)} terms mapped, "
        f"overall_confidence={mapped_query.overall_confidence:.2f}, latency={latency_ms}ms"
    )
    
    return {
        "current_stage": "field_mapper",
        "field_mapper_complete": True,
        "mapped_query": mapped_query,
        "execution_path": ["field_mapper"]
    }


def _extract_terms_from_semantic_query(
    semantic_query: "SemanticQuery"
) -> Dict[str, Optional[str]]:
    """Extract business terms from SemanticQuery Pydantic object.
    
    注意：不再基于 Step1 的语义分类（measure/dimension）来限制字段搜索范围。
    因为：
    1. 对维度字段使用 COUNT/COUNTD 是完全合法的（如 COUNT(Order ID)）
    2. 用户语义上的"度量"可能在数据源中是维度字段
    3. VizQL 和 SQL 都支持对维度字段进行聚合计算
    
    所以字段映射时应该在整个元数据中搜索最匹配的字段，而不是限制在特定角色中。
    
    Args:
        semantic_query: SemanticQuery Pydantic object
        
    Returns:
        Dict mapping business term to None (no role filter)
    """
    terms = {}
    
    # 提取 measures - 不限制角色
    for measure in semantic_query.measures or []:
        if measure.field_name:
            terms[measure.field_name] = None  # 不限制角色，在整个元数据中搜索
    
    # 提取 dimensions - 不限制角色
    for dimension in semantic_query.dimensions or []:
        if dimension.field_name:
            terms[dimension.field_name] = None  # 不限制角色，在整个元数据中搜索
    
    # 提取 filters - 不限制角色
    for filter_spec in semantic_query.filters or []:
        if filter_spec.field_name and filter_spec.field_name not in terms:
            terms[filter_spec.field_name] = None
    
    # 提取 computations 中的字段 - 不限制角色
    for computation in semantic_query.computations or []:
        if computation.target and computation.target not in terms:
            terms[computation.target] = None
        # partition_by 中的字段
        for partition_field in computation.partition_by or []:
            if partition_field and partition_field not in terms:
                terms[partition_field] = None
    
    return terms


def _get_field_mapper(state: Dict[str, Any], config: Optional[RunnableConfig] = None) -> FieldMapperNode:
    """Get or create FieldMapper instance."""
    if "_field_mapper" in state:
        return state["_field_mapper"]
    
    mapper = FieldMapperNode()
    
    # 优先从 config 的 WorkflowContext 获取 data_model
    data_model = state.get("data_model")
    datasource_luid = state.get("datasource") or "default"
    
    if config and not data_model:
        try:
            from tableau_assistant.src.orchestration.workflow.context import get_context
            ctx = get_context(config)
            if ctx:
                data_model = ctx.data_model
                datasource_luid = ctx.datasource_luid or datasource_luid
                logger.debug(f"从 WorkflowContext 获取 data_model: {data_model is not None}")
        except Exception as e:
            logger.warning(f"从 config 获取 WorkflowContext 失败: {e}")
    
    if data_model:
        try:
            if hasattr(data_model, 'fields') and data_model.fields:
                mapper.load_metadata(
                    fields=data_model.fields,
                    datasource_luid=datasource_luid
                )
                logger.info(f"两阶段架构已启用: {len(data_model.fields)} 个字段已索引")
            
            from tableau_assistant.src.infra.ai.rag.semantic_mapper import SemanticMapper
            from tableau_assistant.src.infra.ai.rag.field_indexer import FieldIndexer
            
            field_indexer = FieldIndexer(datasource_luid=datasource_luid)
            if hasattr(data_model, 'fields'):
                field_indexer.index_fields(data_model.fields)
            
            semantic_mapper = SemanticMapper(field_indexer=field_indexer)
            mapper.set_semantic_mapper(semantic_mapper)
            
        except Exception as e:
            logger.warning(f"Failed to set up two-stage architecture: {e}")
            try:
                from tableau_assistant.src.infra.ai.rag.semantic_mapper import SemanticMapper
                from tableau_assistant.src.infra.ai.rag.field_indexer import FieldIndexer
                
                field_indexer = FieldIndexer(datasource_luid=datasource_luid)
                if hasattr(data_model, 'fields'):
                    field_indexer.index_fields(data_model.fields)
                
                semantic_mapper = SemanticMapper(field_indexer=field_indexer)
                mapper.set_semantic_mapper(semantic_mapper)
                logger.info("降级到简单模式")
            except Exception as e2:
                logger.error(f"Failed to create SemanticMapper: {e2}")
    
    return mapper


__all__ = [
    "FieldMapperNode",
    "FieldMappingConfig",
    "MappingResult",
    "CachedMapping",
    "LatencyBreakdown",
    "field_mapper_node",
]
