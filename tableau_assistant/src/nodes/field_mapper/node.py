"""
FieldMapper Node - RAG + LLM Hybrid Node

Maps business terms from SemanticQuery to technical field names.

Strategy:
1. RAG retrieval: SemanticMapper.search()
2. Fast path: confidence >= 0.9, return directly (no LLM)
3. LLM fallback: confidence < 0.9, use LLM to select from top-k candidates

Input: SemanticQuery (business terms)
Output: MappedQuery (technical fields)

Requirements:
- R4.1: Receive SemanticQuery, output MappedQuery
- R4.2: Use SemanticMapper for vector retrieval
- R4.3: Skip LLM when confidence >= 0.9 (fast path)
- R4.4: Use LLM for low confidence selections
- R4.5: Return top-3 alternatives when confidence < 0.7
- R4.6: Cache results with 1 hour TTL
- R4.7: Concurrent processing (max 5 terms)
- R4.8, R4.9: Include dimension hierarchy info
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field

from tableau_assistant.src.nodes.field_mapper.cache import FieldMappingCache, CachedMapping
from tableau_assistant.src.nodes.field_mapper.llm_selector import (
    LLMCandidateSelector,
    FieldCandidate,
    SingleSelectionResult,
)

logger = logging.getLogger(__name__)


# Configuration constants
HIGH_CONFIDENCE_THRESHOLD = 0.9  # Fast path threshold
LOW_CONFIDENCE_THRESHOLD = 0.7   # Below this, return alternatives
MAX_CONCURRENCY = 5              # Max concurrent mapping operations
CACHE_TTL = 3600                 # 1 hour cache TTL
TOP_K_CANDIDATES = 5             # Number of candidates for LLM selection
MAX_ALTERNATIVES = 3             # Max alternatives for low confidence


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
class MappingResult:
    """Result of mapping a single business term"""
    business_term: str
    technical_field: Optional[str]
    confidence: float
    mapping_source: str  # "rag_direct", "rag_llm_fallback", "cache"
    reasoning: Optional[str] = None
    alternatives: List[Dict[str, Any]] = field(default_factory=list)
    category: Optional[str] = None
    level: Optional[int] = None
    granularity: Optional[str] = None
    latency_ms: int = 0


class FieldMapperNode:
    """
    FieldMapper Node - RAG + LLM Hybrid
    
    Maps business terms to technical field names using:
    1. Cache lookup (fastest)
    2. RAG retrieval with high confidence fast path
    3. LLM fallback for low confidence cases
    
    Attributes:
        semantic_mapper: SemanticMapper instance for RAG retrieval
        llm_selector: LLMCandidateSelector for low confidence cases
        cache: FieldMappingCache for caching results
        config: FieldMappingConfig for configuration
    """
    
    def __init__(
        self,
        semantic_mapper: Optional[Any] = None,
        llm_selector: Optional[LLMCandidateSelector] = None,
        cache: Optional[FieldMappingCache] = None,
        config: Optional[FieldMappingConfig] = None,
        store_manager: Optional[Any] = None
    ):
        """
        Initialize FieldMapper Node.
        
        Args:
            semantic_mapper: SemanticMapper instance (lazy loaded if None)
            llm_selector: LLMCandidateSelector instance (lazy loaded if None)
            cache: FieldMappingCache instance (created if None)
            config: FieldMappingConfig (uses defaults if None)
            store_manager: StoreManager for cache persistence
        """
        self._semantic_mapper = semantic_mapper
        self._llm_selector = llm_selector
        self.config = config or FieldMappingConfig()
        self.cache = cache or FieldMappingCache(
            ttl=self.config.cache_ttl,
            store_manager=store_manager
        )
        
        # Statistics
        self._total_mappings = 0
        self._cache_hits = 0
        self._fast_path_hits = 0
        self._llm_fallback_count = 0
    
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
            cached = self.cache.get(term, datasource_luid)
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
            # RAG 失败时回退到 LLM
            logger.info(f"RAG 失败，回退到 LLM 匹配: {term}")
            return await self._map_field_with_llm_only(
                term=term,
                datasource_luid=datasource_luid,
                context=context,
                role_filter=role_filter,
                start_time=start_time
            )
        
        # 5. Check high confidence fast path
        if rag_result.confidence >= self.config.high_confidence_threshold:
            self._fast_path_hits += 1
            latency = int((time.time() - start_time) * 1000)
            
            # Extract dimension hierarchy info from retrieval results
            category, level, granularity = self._extract_hierarchy_info(rag_result)
            
            # Cache the result
            if self.config.enable_cache and rag_result.matched_field:
                self.cache.set(
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
                latency_ms=latency
            )
        
        # 4. LLM fallback for low confidence
        if self.config.enable_llm_fallback and rag_result.retrieval_results:
            self._llm_fallback_count += 1
            
            # Convert retrieval results to FieldCandidate
            candidates = self._convert_to_candidates(rag_result.retrieval_results)
            
            # Use LLM to select best match
            try:
                selection = await self.llm_selector.select(
                    term=term,
                    candidates=candidates,
                    context=context
                )
                
                latency = int((time.time() - start_time) * 1000)
                
                # Find selected candidate for hierarchy info
                selected_candidate = next(
                    (c for c in candidates if c.field_name == selection.selected_field),
                    None
                )
                
                category = selected_candidate.category if selected_candidate else None
                level = selected_candidate.level if selected_candidate else None
                granularity = selected_candidate.granularity if selected_candidate else None
                
                # Build alternatives for low confidence
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
                
                # Cache the result
                if self.config.enable_cache and selection.selected_field:
                    self.cache.set(
                        term=term,
                        datasource_luid=datasource_luid,
                        technical_field=selection.selected_field,
                        confidence=selection.confidence,
                        category=category,
                        level=level,
                        granularity=granularity
                    )
                
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
                    latency_ms=latency
                )
            except Exception as e:
                logger.error(f"LLM selection failed for '{term}': {e}")
                # Fall through to use RAG result
        
        # 5. Use RAG result as fallback
        latency = int((time.time() - start_time) * 1000)
        category, level, granularity = self._extract_hierarchy_info(rag_result)
        
        # Build alternatives for low confidence
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
        
        # Create semaphore for concurrency control
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
        
        # Run all mappings concurrently
        tasks = [map_with_semaphore(term) for term in terms]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Build result dict
        mapping_results = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Mapping task failed: {result}")
                continue
            term, mapping = result
            mapping_results[term] = mapping
        
        return mapping_results
    
    async def _map_field_with_llm_only(
        self,
        term: str,
        datasource_luid: str,
        context: Optional[str] = None,
        role_filter: Optional[str] = None,
        start_time: Optional[float] = None
    ) -> MappingResult:
        """
        使用 LLM 直接进行字段匹配（当 RAG 不可用时）
        
        从 FieldIndexer 获取所有字段元数据，构建候选列表，
        然后使用 LLM 选择最佳匹配。
        
        Args:
            term: 业务术语
            datasource_luid: 数据源标识
            context: 上下文信息
            role_filter: 角色过滤
            start_time: 开始时间（用于计算延迟）
        
        Returns:
            MappingResult
        """
        if start_time is None:
            start_time = time.time()
        
        # 从 FieldIndexer 获取所有字段元数据
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
        
        # 根据 role_filter 过滤字段
        filtered_chunks = all_chunks
        if role_filter:
            filtered_chunks = [
                c for c in all_chunks 
                if c.role and c.role.lower() == role_filter.lower()
            ]
            # 如果过滤后没有结果，使用全部字段
            if not filtered_chunks:
                filtered_chunks = all_chunks
        
        # 构建候选列表（限制数量避免 prompt 过长）
        max_candidates = min(len(filtered_chunks), 20)  # 最多 20 个候选
        candidates = []
        for chunk in filtered_chunks[:max_candidates]:
            candidates.append(FieldCandidate(
                field_name=chunk.field_name,
                field_caption=chunk.field_caption,
                role=chunk.role,
                data_type=chunk.data_type,
                score=0.5,  # 默认分数
                category=chunk.category,
                level=chunk.metadata.get("level") if chunk.metadata else None,
                granularity=chunk.metadata.get("granularity") if chunk.metadata else None,
                sample_values=chunk.sample_values
            ))
        
        # 使用 LLM 选择
        try:
            self._llm_fallback_count += 1
            selection = await self.llm_selector.select(
                term=term,
                candidates=candidates,
                context=context
            )
            
            latency = int((time.time() - start_time) * 1000)
            
            # 查找选中的候选以获取层级信息
            selected_candidate = next(
                (c for c in candidates if c.field_name == selection.selected_field),
                None
            )
            
            category = selected_candidate.category if selected_candidate else None
            level = selected_candidate.level if selected_candidate else None
            granularity = selected_candidate.granularity if selected_candidate else None
            
            # 构建备选列表
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
            
            # 缓存结果
            if self.config.enable_cache and selection.selected_field:
                self.cache.set(
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
    
    def get_stats(self) -> Dict[str, Any]:
        """Get mapping statistics"""
        return {
            "total_mappings": self._total_mappings,
            "cache_hits": self._cache_hits,
            "fast_path_hits": self._fast_path_hits,
            "llm_fallback_count": self._llm_fallback_count,
            "cache_stats": self.cache.get_stats(),
        }


async def field_mapper_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    FieldMapper Node function for StateGraph.
    
    Extracts business terms from SemanticQuery and maps them to technical fields.
    
    Args:
        state: VizQLState containing semantic_query
    
    Returns:
        State update with mapped_query
    """
    import time
    start_time = time.time()
    
    # Get semantic query from state
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
    
    # Get datasource info
    datasource_luid = state.get("datasource") or "default"
    question = state.get("question", "")
    
    # Extract business terms from semantic query
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
    
    # Get or create FieldMapper instance
    # In production, this would be injected via dependency injection
    mapper = _get_field_mapper(state)
    
    # Map all terms
    try:
        mapping_results = await mapper.map_fields_batch(
            terms=list(terms_to_map.keys()),
            datasource_luid=datasource_luid,
            context=question,
            role_filters=terms_to_map  # term -> expected role
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
    
    # Build MappedQuery
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
    
    # Calculate overall confidence
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
    """
    Extract business terms from SemanticQuery.
    
    Returns dict of term -> expected role (dimension/measure/None)
    """
    terms = {}
    
    # Extract from measures
    for measure in semantic_query.get("measures", []):
        name = measure.get("name")
        if name:
            terms[name] = "measure"
    
    # Extract from dimensions
    for dimension in semantic_query.get("dimensions", []):
        name = dimension.get("name")
        if name:
            terms[name] = "dimension"
    
    # Extract from filters
    for filter_spec in semantic_query.get("filters", []):
        field = filter_spec.get("field")
        if field and field not in terms:
            terms[field] = None  # Could be either
    
    # Extract from analyses
    for analysis in semantic_query.get("analyses", []):
        target = analysis.get("target_measure")
        if target and target not in terms:
            terms[target] = "measure"
    
    return terms


def _get_field_mapper(state: Dict[str, Any]) -> FieldMapperNode:
    """
    Get or create FieldMapper instance.
    
    In production, this would use dependency injection.
    """
    # Check if mapper is in state (injected)
    if "_field_mapper" in state:
        return state["_field_mapper"]
    
    # Create new instance with lazy-loaded dependencies
    # SemanticMapper will be loaded when first used
    mapper = FieldMapperNode()
    
    # Try to get SemanticMapper from metadata
    metadata = state.get("metadata")
    if metadata:
        try:
            from tableau_assistant.src.capabilities.rag.semantic_mapper import SemanticMapper
            from tableau_assistant.src.capabilities.rag.field_indexer import FieldIndexer
            
            # Create field indexer from metadata
            field_indexer = FieldIndexer()
            field_indexer.index_metadata(metadata)
            
            # Create semantic mapper
            semantic_mapper = SemanticMapper(field_indexer=field_indexer)
            mapper.set_semantic_mapper(semantic_mapper)
        except Exception as e:
            logger.warning(f"Failed to create SemanticMapper: {e}")
    
    return mapper
