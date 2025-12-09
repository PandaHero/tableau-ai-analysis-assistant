"""
FieldMapper Node - RAG + LLM Hybrid Node

Maps business terms from SemanticQuery to technical field names.

Strategy:
1. RAG retrieval: SemanticMapper.search()
2. Fast path: confidence >= 0.9, return directly (no LLM)
3. LLM fallback: confidence < 0.9, use LLM to select from top-k candidates

Input: SemanticQuery (business terms)
Output: MappedQuery (technical fields)
"""

import asyncio
import hashlib
import logging
import time
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field

from .llm_selector import (
    LLMCandidateSelector,
    FieldCandidate,
    SingleSelectionResult,
)

from tableau_assistant.src.capabilities.rag.assembler import (
    KnowledgeAssembler,
    AssemblerConfig,
    ChunkStrategy,
)
from tableau_assistant.src.capabilities.rag.reranker import LLMReranker

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
    1. Cache lookup (fastest) - using StoreManager
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
            store_manager: StoreManager for cache persistence
            assembler: KnowledgeAssembler for metadata loading
            reranker: LLMReranker for second-stage reranking
        """
        self._semantic_mapper = semantic_mapper
        self._llm_selector = llm_selector
        self.config = config or FieldMappingConfig()
        
        self._assembler = assembler
        self._reranker = reranker
        
        # Get StoreManager
        if store_manager is not None:
            self._store_manager = store_manager
        else:
            try:
                from tableau_assistant.src.capabilities.storage.store_manager import get_store_manager
                self._store_manager = get_store_manager()
            except Exception as e:
                logger.warning(f"无法获取 StoreManager，缓存将不可用: {e}")
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
        """Get cached mapping from StoreManager"""
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
        """Save mapping to StoreManager cache"""
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
                include_sample_values=True,
                max_sample_values=5,
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
        role_filter: Optional[str] = None
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
                    mapping_source="cache",
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
                start_time=start_time
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
                start_time=start_time
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
                start_time=start_time
            )
        
        # 7. Use RAG result as fallback
        latency = int((time.time() - start_time) * 1000)
        category, level, granularity = self._extract_hierarchy_info(rag_result)
        latency_breakdown = self._extract_latency_breakdown(rag_result, latency)
        
        alternatives = []
        if rag_result.confidence < self.config.low_confidence_threshold:
            alternatives = [
                {"field": alt, "confidence": 0.0}
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
        start_time: float
    ) -> MappingResult:
        """LLM fallback when RAG confidence is low"""
        self._llm_fallback_count += 1
        
        candidates = self._convert_to_candidates(rag_result.retrieval_results)
        
        try:
            selection = await self.llm_selector.select(
                term=term,
                candidates=candidates,
                context=context
            )
            
            latency = int((time.time() - start_time) * 1000)
            
            selected_candidate = next(
                (c for c in candidates if c.field_name == selection.selected_field),
                None
            )
            
            category = selected_candidate.category if selected_candidate else None
            level = selected_candidate.level if selected_candidate else None
            granularity = selected_candidate.granularity if selected_candidate else None
            
            alternatives = []
            if selection.confidence < self.config.low_confidence_threshold:
                alternatives = [
                    {
                        "field": c.field_name,
                        "confidence": c.score,
                        "caption": c.field_caption
                    }
                    for c in candidates[:self.config.max_alternatives]
                    if c.field_name != selection.selected_field
                ]
            
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
                alternatives=alternatives,
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
        start_time: Optional[float] = None
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
        
        try:
            self._llm_fallback_count += 1
            selection = await self.llm_selector.select(
                term=term,
                candidates=candidates,
                context=context
            )
            
            latency = int((time.time() - start_time) * 1000)
            
            selected_candidate = next(
                (c for c in candidates if c.field_name == selection.selected_field),
                None
            )
            
            category = selected_candidate.category if selected_candidate else None
            level = selected_candidate.level if selected_candidate else None
            granularity = selected_candidate.granularity if selected_candidate else None
            
            alternatives = []
            if selection.confidence < self.config.low_confidence_threshold:
                alternatives = [
                    {
                        "field": c.field_name,
                        "confidence": c.score,
                        "caption": c.field_caption
                    }
                    for c in candidates[:self.config.max_alternatives]
                    if c.field_name != selection.selected_field
                ]
            
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
        role_filters: Optional[Dict[str, str]] = None
    ) -> Dict[str, MappingResult]:
        """
        Map multiple business terms concurrently.
        
        Args:
            terms: List of business terms to map
            datasource_luid: Datasource identifier
            context: Optional question context
            role_filters: Optional dict of term -> role filter
        
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
                    role_filter=role_filters.get(term)
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

async def field_mapper_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    FieldMapper Node function for StateGraph.
    
    Extracts business terms from SemanticQuery and maps them to technical fields.
    
    Args:
        state: VizQLState containing semantic_query
    
    Returns:
        State update with mapped_query
    """
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
        return {
            "current_stage": "field_mapper",
            "field_mapper_complete": True,
            "mapped_query": {
                "semantic_query": semantic_query,
                "field_mappings": {},
                "overall_confidence": 1.0,
                "datasource_luid": datasource_luid
            },
            "execution_path": ["field_mapper"]
        }
    
    mapper = _get_field_mapper(state)
    
    try:
        mapping_results = await mapper.map_fields_batch(
            terms=list(terms_to_map.keys()),
            datasource_luid=datasource_luid,
            context=question,
            role_filters=terms_to_map
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
    
    field_mappings = {}
    confidences = []
    low_confidence_alternatives = {}
    
    for term, result in mapping_results.items():
        field_mappings[term] = {
            "business_term": result.business_term,
            "technical_field": result.technical_field,
            "confidence": result.confidence,
            "mapping_source": result.mapping_source,
            "category": result.category,
            "level": result.level,
            "granularity": result.granularity,
        }
        
        if result.technical_field:
            confidences.append(result.confidence)
        
        if result.alternatives:
            low_confidence_alternatives[term] = result.alternatives
    
    overall_confidence = min(confidences) if confidences else 0.0
    
    mapped_query = {
        "semantic_query": semantic_query,
        "field_mappings": field_mappings,
        "overall_confidence": overall_confidence,
        "datasource_luid": datasource_luid,
        "low_confidence_alternatives": low_confidence_alternatives if low_confidence_alternatives else None,
    }
    
    latency_ms = int((time.time() - start_time) * 1000)
    logger.info(
        f"Field mapping complete: {len(field_mappings)} terms mapped, "
        f"overall_confidence={overall_confidence:.2f}, latency={latency_ms}ms"
    )
    
    return {
        "current_stage": "field_mapper",
        "field_mapper_complete": True,
        "mapped_query": mapped_query,
        "execution_path": ["field_mapper"]
    }


def _extract_terms_from_semantic_query(
    semantic_query: Dict[str, Any]
) -> Dict[str, Optional[str]]:
    """Extract business terms from SemanticQuery."""
    terms = {}
    
    for measure in semantic_query.get("measures", []):
        name = measure.get("name")
        if name:
            terms[name] = "measure"
    
    for dimension in semantic_query.get("dimensions", []):
        name = dimension.get("name")
        if name:
            terms[name] = "dimension"
    
    for filter_spec in semantic_query.get("filters", []):
        field = filter_spec.get("field")
        if field and field not in terms:
            terms[field] = None
    
    for analysis in semantic_query.get("analyses", []):
        target = analysis.get("target_measure")
        if target and target not in terms:
            terms[target] = "measure"
    
    return terms


def _get_field_mapper(state: Dict[str, Any]) -> FieldMapperNode:
    """Get or create FieldMapper instance."""
    if "_field_mapper" in state:
        return state["_field_mapper"]
    
    mapper = FieldMapperNode()
    
    metadata = state.get("metadata")
    datasource_luid = state.get("datasource") or "default"
    
    if metadata:
        try:
            if hasattr(metadata, 'fields') and metadata.fields:
                mapper.load_metadata(
                    fields=metadata.fields,
                    datasource_luid=datasource_luid
                )
                logger.info(f"两阶段架构已启用: {len(metadata.fields)} 个字段已索引")
            
            from tableau_assistant.src.capabilities.rag.semantic_mapper import SemanticMapper
            from tableau_assistant.src.capabilities.rag.field_indexer import FieldIndexer
            
            field_indexer = FieldIndexer(datasource_luid=datasource_luid)
            if hasattr(metadata, 'fields'):
                field_indexer.index_fields(metadata.fields)
            
            semantic_mapper = SemanticMapper(field_indexer=field_indexer)
            mapper.set_semantic_mapper(semantic_mapper)
            
        except Exception as e:
            logger.warning(f"Failed to set up two-stage architecture: {e}")
            try:
                from tableau_assistant.src.capabilities.rag.semantic_mapper import SemanticMapper
                from tableau_assistant.src.capabilities.rag.field_indexer import FieldIndexer
                
                field_indexer = FieldIndexer(datasource_luid=datasource_luid)
                if hasattr(metadata, 'fields'):
                    field_indexer.index_fields(metadata.fields)
                
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
