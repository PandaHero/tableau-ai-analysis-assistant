# -*- coding: utf-8 -*-
"""
维度层级推断

推断策略：缓存 → 增量检测 → 种子匹配 → RAG → LLM → 自学习

特性：
- 增量推断：只对新增/变更字段进行推断
- 阈值分层：seed/verified 使用标准阈值，llm/unverified 使用更高阈值
- 并发控制：按 cache_key 粒度加锁，避免同一数据源的并发推断
- 批量检索：使用批量 Embedding 优化 RAG 检索性能
- 自学习：高置信度结果存入 RAG
"""
import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple, Set, Callable, Awaitable

from langchain_core.messages import SystemMessage, HumanMessage

from analytics_assistant.src.core.schemas.data_model import Field
from analytics_assistant.src.agents.dimension_hierarchy.schemas import (
    DimensionCategory,
    DimensionAttributes,
    DimensionHierarchyResult,
    LLMDimensionOutput,
)
from analytics_assistant.src.agents.dimension_hierarchy.prompts import (
    SYSTEM_PROMPT,
    build_user_prompt,
)
from analytics_assistant.src.agents.dimension_hierarchy.seed_data import SEED_PATTERNS
from analytics_assistant.src.agents.base import get_llm, stream_llm_structured
from analytics_assistant.src.infra.storage import CacheManager
from analytics_assistant.src.infra.config import get_config


logger = logging.getLogger(__name__)


class PatternSource(str, Enum):
    """RAG 模式来源"""
    SEED = "seed"
    LLM = "llm"
    MANUAL = "manual"


# ══════════════════════════════════════════════════════════════
# 并发控制常量
# ══════════════════════════════════════════════════════════════

MAX_LOCKS = 100  # 最大锁数量
LOCK_EXPIRE_SECONDS = 300  # 锁过期时间（秒）


# ══════════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════════

def _get_config() -> Dict[str, Any]:
    """从 YAML 读取配置"""
    config = get_config()
    return config.get("dimension_hierarchy", {})


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
        field_info.append({"caption": f.caption or f.name, "data_type": f.data_type})
    return hashlib.md5(json.dumps(field_info, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def compute_single_field_hash(field: Field) -> str:
    """计算单个字段的哈希值"""
    info = {"caption": field.caption or field.name, "data_type": field.data_type}
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
# 主推断类
# ══════════════════════════════════════════════════════════════

class DimensionHierarchyInference:
    """
    维度层级推断
    
    推断策略：缓存 → 增量检测 → 种子匹配 → RAG → LLM → 自学习
    
    特性：
    - 并发控制：按 cache_key 粒度加锁
    - 种子数据一致性检查：自动修复索引与元数据不一致
    - 批量 RAG 检索：使用批量 Embedding 优化性能
    """
    
    def __init__(
        self,
        enable_rag: bool = True,
        enable_cache: bool = True,
        enable_self_learning: bool = True,
    ):
        config = _get_config()
        self._high_confidence = config.get("high_confidence_threshold", 0.85)
        self._max_retry = config.get("max_retry_attempts", 3)
        cache_ns = config.get("cache_namespace", "dimension_hierarchy")
        pattern_ns = config.get("pattern_namespace", "dimension_patterns_metadata")
        self._incremental_enabled = config.get("incremental", {}).get("enabled", True)
        
        self._enable_rag = enable_rag
        self._enable_cache = enable_cache
        self._enable_self_learning = enable_self_learning
        
        # 种子数据索引
        self._seed_index = {p["field_caption"].lower(): p for p in SEED_PATTERNS}
        
        # 缓存
        self._cache = CacheManager(cache_ns) if enable_cache else None
        self._pattern_store = CacheManager(pattern_ns) if enable_self_learning else None
        
        # RAG（延迟初始化）
        self._rag_retriever = None
        self._rag_initialized = False
        self._seed_initialized = False
        
        # 并发控制
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock_times: Dict[str, float] = {}
        self._global_lock = asyncio.Lock()
        
        # 结果
        self._last_result: Optional[DimensionHierarchyResult] = None
    
    # ─────────────────────────────────────────────────────────
    # 并发控制
    # ─────────────────────────────────────────────────────────
    
    async def _get_lock(self, cache_key: str) -> asyncio.Lock:
        """
        获取指定 cache_key 的锁
        
        按 cache_key 粒度加锁，避免同一数据源的并发推断。
        """
        async with self._global_lock:
            self._cleanup_old_locks()
            
            if cache_key not in self._locks:
                self._locks[cache_key] = asyncio.Lock()
            
            self._lock_times[cache_key] = time.time()
            return self._locks[cache_key]
    
    def _cleanup_old_locks(self) -> None:
        """清理过期的锁，防止锁字典无限增长"""
        if len(self._locks) <= MAX_LOCKS:
            return
        
        current_time = time.time()
        expired_keys = [
            key for key, lock_time in self._lock_times.items()
            if current_time - lock_time > LOCK_EXPIRE_SECONDS
        ]
        
        for key in expired_keys:
            if key in self._locks and not self._locks[key].locked():
                del self._locks[key]
                del self._lock_times[key]
        
        if expired_keys:
            logger.debug(f"清理过期锁: {len(expired_keys)} 个")
    
    # ─────────────────────────────────────────────────────────
    # 种子数据一致性检查
    # ─────────────────────────────────────────────────────────
    
    def _ensure_seed_data(self) -> None:
        """
        确保种子数据已初始化
        
        首次调用时自动初始化种子数据到 RAG，并检查一致性。
        
        修复场景：
        1. index=0 & metadata=0: 初始化种子数据
        2. index>0 & metadata 数量不一致: 一致性修复
        """
        if self._seed_initialized:
            return
        
        patterns = self._load_patterns()
        metadata_count = len(patterns)
        
        # 检查向量索引数量
        index_count = self._get_index_count()
        
        logger.debug(f"一致性检查: index={index_count}, metadata={metadata_count}")
        
        if metadata_count == 0:
            logger.info("metadata 为空，初始化种子数据")
            self._init_seed_patterns()
        elif index_count != metadata_count and index_count > 0:
            logger.warning(
                f"索引 ({index_count}) 和 metadata ({metadata_count}) 数量不一致，"
                f"将在 RAG 初始化时重建索引"
            )
            # 标记需要重建索引
            self._rag_initialized = False
        
        self._seed_initialized = True
    
    def _get_index_count(self) -> int:
        """获取向量索引中的模式数量"""
        if not self._rag_retriever:
            return 0
        
        try:
            embedding_retriever = getattr(self._rag_retriever, '_embedding', None)
            if embedding_retriever and hasattr(embedding_retriever, '_chunks'):
                return len(embedding_retriever._chunks)
        except Exception:
            pass
        
        return 0

    
    # ─────────────────────────────────────────────────────────
    # 种子匹配
    # ─────────────────────────────────────────────────────────
    
    def _match_seed(self, caption: str) -> Optional[Dict[str, Any]]:
        """精确匹配种子数据"""
        return self._seed_index.get(caption.lower())
    
    # ─────────────────────────────────────────────────────────
    # 缓存操作
    # ─────────────────────────────────────────────────────────
    
    def _get_cache(self, key: str) -> Optional[Dict[str, Any]]:
        return self._cache.get(key) if self._cache else None
    
    def _put_cache(self, key: str, field_hash: str, field_hashes: Dict[str, str], data: Dict[str, Any]) -> bool:
        if not self._cache:
            return False
        return self._cache.set(key, {"field_hash": field_hash, "field_hashes": field_hashes, "data": data})
    
    # ─────────────────────────────────────────────────────────
    # 序列化
    # ─────────────────────────────────────────────────────────
    
    def _serialize_attrs(self, attrs: DimensionAttributes) -> Dict[str, Any]:
        return {
            "category": attrs.category.value,
            "category_detail": attrs.category_detail,
            "level": attrs.level,
            "granularity": attrs.granularity,
            "level_confidence": attrs.level_confidence,
            "reasoning": attrs.reasoning,
        }
    
    def _deserialize_attrs(self, data: Dict[str, Any]) -> DimensionAttributes:
        return DimensionAttributes(
            category=DimensionCategory(data["category"]),
            category_detail=data["category_detail"],
            level=data["level"],
            granularity=data["granularity"],
            level_confidence=data["level_confidence"],
            reasoning=data.get("reasoning", "缓存命中"),
        )

    
    # ─────────────────────────────────────────────────────────
    # RAG 初始化
    # ─────────────────────────────────────────────────────────
    
    def _init_rag(self) -> None:
        """
        初始化 RAG 检索器
        
        策略：
        1. 先尝试加载已有向量索引（快速）
        2. 索引不存在时才创建新的（慢，需要 embedding）
        3. chunks 从 pattern_store 加载，与向量索引分离
        """
        if self._rag_initialized or not self._enable_rag:
            return
        
        try:
            from analytics_assistant.src.infra.rag import (
                RetrievalConfig, FieldChunk, ExactRetriever, EmbeddingRetriever, CascadeRetriever,
            )
            from analytics_assistant.src.infra.storage import get_vector_store
            from analytics_assistant.src.infra.ai import get_embeddings
            
            app_config = get_config()
            vector_cfg = app_config.config.get("vector_storage", {})
            index_dir = vector_cfg.get("index_dir", "analytics_assistant/data/indexes")
            
            # 1. 加载 patterns（从 KV 存储）
            patterns = self._load_patterns()
            if not patterns:
                patterns = self._init_seed_patterns()
            
            if not patterns:
                self._rag_initialized = True
                return
            
            # 2. 构建 chunks（内存中，用于精确匹配和结果映射）
            chunks: Dict[str, FieldChunk] = {}
            for p in patterns:
                index_text = f"{p['field_caption']} | {p.get('category', '')} | {p.get('category_detail', '')}"
                chunk = FieldChunk(
                    field_name=p["pattern_id"],
                    field_caption=p["field_caption"],
                    role="dimension",
                    data_type=p["data_type"],
                    index_text=index_text,
                    category=p.get("category"),
                    metadata={"source": p.get("source"), "verified": p.get("verified", False)},
                )
                chunks[chunk.field_name] = chunk
            
            # 3. 检查索引是否存在，存在则加载，否则创建
            from pathlib import Path
            index_path = Path(index_dir) / "dimension_patterns"
            embeddings = get_embeddings()
            
            if index_path.exists():
                # 加载已有索引
                logger.info(f"加载已有向量索引: {index_path}")
                vector_store = get_vector_store(
                    backend=vector_cfg.get("backend", "faiss"),
                    embeddings=embeddings,
                    collection_name="dimension_patterns",
                    persist_directory=index_dir,
                )
            else:
                # 创建新索引
                logger.info(f"创建新向量索引: {len(patterns)} 个模式")
                texts, metadatas = [], []
                for p in patterns:
                    index_text = f"{p['field_caption']} | {p.get('category', '')} | {p.get('category_detail', '')}"
                    texts.append(index_text)
                    metadatas.append({"field_name": p["pattern_id"], "field_caption": p["field_caption"]})
                
                vector_store = get_vector_store(
                    backend=vector_cfg.get("backend", "faiss"),
                    embeddings=embeddings,
                    collection_name="dimension_patterns",
                    persist_directory=index_dir,
                    texts=texts,
                    metadatas=metadatas,
                )
                
                # 持久化索引
                if vector_store and hasattr(vector_store, 'save_local'):
                    index_path.parent.mkdir(parents=True, exist_ok=True)
                    vector_store.save_local(str(index_path))
                    logger.info(f"向量索引已保存: {index_path}")
            
            if vector_store is None:
                logger.warning("无法创建向量存储")
                self._rag_initialized = True
                return
            
            # 5. 创建检索器
            rag_threshold = _get_rag_threshold_seed()
            config = RetrievalConfig(top_k=5, score_threshold=rag_threshold)
            self._rag_retriever = CascadeRetriever(
                ExactRetriever(chunks, config),
                EmbeddingRetriever(vector_store, chunks, config),
                config,
            )
            logger.info(f"RAG 初始化完成: {len(patterns)} 个模式，索引已加载")
            
        except Exception as e:
            logger.warning(f"RAG 初始化失败: {e}")
        
        self._rag_initialized = True

    
    def _load_patterns(self) -> List[Dict[str, Any]]:
        """加载已存储的 pattern"""
        if not self._pattern_store:
            return []
        pattern_index = self._pattern_store.get("_pattern_index") or []
        return [p for pid in pattern_index if (p := self._pattern_store.get(pid))]
    
    def _init_seed_patterns(self) -> List[Dict[str, Any]]:
        """初始化种子数据到 pattern store"""
        if not self._pattern_store:
            return []
        
        patterns, pattern_ids = [], []
        for seed in SEED_PATTERNS:
            pid = generate_pattern_id(seed["field_caption"], seed["data_type"])
            pattern = {
                "pattern_id": pid,
                "field_caption": seed["field_caption"],
                "data_type": seed["data_type"],
                "category": seed["category"],
                "category_detail": seed["category_detail"],
                "level": seed["level"],
                "granularity": seed["granularity"],
                "reasoning": seed.get("reasoning", "种子数据"),
                "confidence": 1.0,
                "source": PatternSource.SEED.value,
                "verified": True,
            }
            self._pattern_store.set(pid, pattern)
            patterns.append(pattern)
            pattern_ids.append(pid)
        
        self._pattern_store.set("_pattern_index", pattern_ids)
        logger.info(f"种子数据初始化: {len(patterns)} 个模式")
        return patterns

    
    # ─────────────────────────────────────────────────────────
    # RAG 检索
    # ─────────────────────────────────────────────────────────
    
    async def _rag_search(self, fields: List[Field]) -> Tuple[Dict[str, DimensionAttributes], List[Field]]:
        """
        RAG 检索，返回 (命中结果, 未命中字段)
        
        优化：使用批量 Embedding 减少 API 调用次数
        """
        if not self._rag_retriever:
            return {}, fields
        
        if not fields:
            return {}, []
        
        results: Dict[str, DimensionAttributes] = {}
        misses: List[Field] = []
        
        # 从配置获取阈值
        rag_threshold_seed = _get_rag_threshold_seed()
        rag_threshold_unverified = _get_rag_threshold_unverified()
        
        # 获取 EmbeddingRetriever 的底层 vector_store
        embedding_retriever = getattr(self._rag_retriever, '_embedding', None)
        if not embedding_retriever or not hasattr(embedding_retriever, '_store'):
            # 回退到逐个检索
            return await self._rag_search_sequential(fields, rag_threshold_seed, rag_threshold_unverified)
        
        vector_store = embedding_retriever._store
        if not vector_store or not hasattr(vector_store, 'similarity_search_by_vector'):
            return await self._rag_search_sequential(fields, rag_threshold_seed, rag_threshold_unverified)
        
        # 1. 先尝试精确匹配（O(1)，无需 embedding）
        exact_retriever = getattr(self._rag_retriever, '_exact', None)
        exact_hits: Dict[str, Tuple[Field, Any]] = {}  # name -> (field, result)
        fields_need_embedding: List[Tuple[int, Field]] = []  # (index, field)
        
        if exact_retriever:
            for i, f in enumerate(fields):
                name = f.caption or f.name
                exact_results = exact_retriever.retrieve(query=name, top_k=1)
                if exact_results:
                    exact_hits[name] = (f, exact_results[0])
                else:
                    fields_need_embedding.append((i, f))
        else:
            fields_need_embedding = list(enumerate(fields))
        
        # 处理精确匹配结果
        for name, (f, result) in exact_hits.items():
            pattern = self._pattern_store.get(result.field_chunk.field_name) if self._pattern_store else None
            if pattern:
                results[name] = DimensionAttributes(
                    category=DimensionCategory(pattern["category"]),
                    category_detail=pattern["category_detail"],
                    level=pattern["level"],
                    granularity=pattern["granularity"],
                    level_confidence=1.0,
                    reasoning=f"RAG 精确匹配: {pattern['field_caption']}",
                )
            else:
                misses.append(f)
        
        if not fields_need_embedding:
            return results, misses
        
        # 2. 批量获取 embedding
        try:
            from analytics_assistant.src.infra.ai import get_model_manager
            
            manager = get_model_manager()
            texts_to_embed = [f.caption or f.name for _, f in fields_need_embedding]
            
            logger.debug(f"批量 Embedding: {len(texts_to_embed)} 个查询")
            query_vectors = await manager.embed_documents_batch_async(
                texts=texts_to_embed,
                use_cache=True,
            )
            
            # 3. 使用向量进行批量检索
            for (idx, f), query_vector in zip(fields_need_embedding, query_vectors):
                name = f.caption or f.name
                
                if not query_vector or len(query_vector) == 0:
                    logger.warning(f"Embedding 失败: {name}")
                    misses.append(f)
                    continue
                
                try:
                    # 使用预计算的向量进行检索
                    docs_and_scores = vector_store.similarity_search_by_vector(
                        query_vector, k=3
                    )
                    
                    if not docs_and_scores:
                        misses.append(f)
                        continue
                    
                    # 处理检索结果
                    best_doc, best_score = docs_and_scores[0] if isinstance(docs_and_scores[0], tuple) else (docs_and_scores[0], 0.0)
                    
                    # FAISS 返回的是 L2 距离，需要转换为相似度
                    if isinstance(best_score, (int, float)):
                        similarity = 1.0 / (1.0 + best_score)
                    else:
                        similarity = 0.0
                    
                    field_name = best_doc.metadata.get("field_name") if hasattr(best_doc, 'metadata') else None
                    if not field_name:
                        misses.append(f)
                        continue
                    
                    pattern = self._pattern_store.get(field_name) if self._pattern_store else None
                    if not pattern:
                        misses.append(f)
                        continue
                    
                    # 阈值分层
                    source = pattern.get("source", "llm")
                    verified = pattern.get("verified", False)
                    threshold = rag_threshold_seed if source == PatternSource.SEED.value or verified else rag_threshold_unverified
                    
                    if similarity < threshold:
                        misses.append(f)
                        continue
                    
                    results[name] = DimensionAttributes(
                        category=DimensionCategory(pattern["category"]),
                        category_detail=pattern["category_detail"],
                        level=pattern["level"],
                        granularity=pattern["granularity"],
                        level_confidence=similarity,
                        reasoning=f"RAG 匹配: {pattern['field_caption']} ({similarity:.2f})",
                    )
                    
                except Exception as e:
                    logger.warning(f"向量检索失败({name}): {e}")
                    misses.append(f)
            
        except Exception as e:
            logger.warning(f"批量 Embedding 失败，回退到逐个检索: {e}")
            # 回退到逐个检索
            for _, f in fields_need_embedding:
                name = f.caption or f.name
                try:
                    search_results = await self._rag_retriever.aretrieve(query=name, top_k=3, score_threshold=rag_threshold_seed)
                    if not search_results:
                        misses.append(f)
                        continue
                    
                    best = search_results[0]
                    pattern = self._pattern_store.get(best.field_chunk.field_name) if self._pattern_store else None
                    if not pattern:
                        misses.append(f)
                        continue
                    
                    source = pattern.get("source", "llm")
                    verified = pattern.get("verified", False)
                    threshold = rag_threshold_seed if source == PatternSource.SEED.value or verified else rag_threshold_unverified
                    
                    if best.score < threshold:
                        misses.append(f)
                        continue
                    
                    results[name] = DimensionAttributes(
                        category=DimensionCategory(pattern["category"]),
                        category_detail=pattern["category_detail"],
                        level=pattern["level"],
                        granularity=pattern["granularity"],
                        level_confidence=best.score,
                        reasoning=f"RAG 匹配: {pattern['field_caption']} ({best.score:.2f})",
                    )
                except Exception as e2:
                    logger.warning(f"RAG 检索失败({name}): {e2}")
                    misses.append(f)
        
        return results, misses
    
    async def _rag_search_sequential(
        self,
        fields: List[Field],
        rag_threshold_seed: float,
        rag_threshold_unverified: float,
    ) -> Tuple[Dict[str, DimensionAttributes], List[Field]]:
        """逐个字段进行 RAG 检索（回退方案）"""
        results: Dict[str, DimensionAttributes] = {}
        misses: List[Field] = []
        
        for f in fields:
            name = f.caption or f.name
            try:
                search_results = await self._rag_retriever.aretrieve(query=name, top_k=3, score_threshold=rag_threshold_seed)
                if not search_results:
                    misses.append(f)
                    continue
                
                best = search_results[0]
                pattern = self._pattern_store.get(best.field_chunk.field_name) if self._pattern_store else None
                if not pattern:
                    misses.append(f)
                    continue
                
                # 阈值分层
                source = pattern.get("source", "llm")
                verified = pattern.get("verified", False)
                threshold = rag_threshold_seed if source == PatternSource.SEED.value or verified else rag_threshold_unverified
                
                if best.score < threshold:
                    misses.append(f)
                    continue
                
                results[name] = DimensionAttributes(
                    category=DimensionCategory(pattern["category"]),
                    category_detail=pattern["category_detail"],
                    level=pattern["level"],
                    granularity=pattern["granularity"],
                    level_confidence=best.score,
                    reasoning=f"RAG 匹配: {pattern['field_caption']} ({best.score:.2f})",
                )
            except Exception as e:
                logger.warning(f"RAG 检索失败({name}): {e}")
                misses.append(f)
        
        return results, misses

    
    # ─────────────────────────────────────────────────────────
    # 自学习
    # ─────────────────────────────────────────────────────────
    
    def _store_to_rag(self, results: Dict[str, DimensionAttributes], fields: List[Field], datasource_luid: str) -> int:
        """
        将高置信度结果存入 RAG
        
        同时更新：
        1. KV 存储（pattern 元数据）
        2. 向量索引（增量添加）
        """
        if not self._pattern_store or not self._enable_self_learning:
            return 0
        
        field_map = {f.caption or f.name: f for f in fields}
        pattern_ids = self._pattern_store.get("_pattern_index") or []
        new_patterns = []
        
        for name, attrs in results.items():
            # 只存高置信度、非种子/RAG 匹配的结果
            if attrs.level_confidence < self._high_confidence:
                continue
            if "种子匹配" in attrs.reasoning or "RAG 匹配" in attrs.reasoning:
                continue
            
            f = field_map.get(name)
            if not f:
                continue
            
            pid = generate_pattern_id(name, f.data_type, datasource_luid)
            if self._pattern_store.get(pid):
                continue
            
            pattern = {
                "pattern_id": pid,
                "field_caption": name,
                "data_type": f.data_type,
                "category": attrs.category.value,
                "category_detail": attrs.category_detail,
                "level": attrs.level,
                "granularity": attrs.granularity,
                "reasoning": attrs.reasoning,
                "confidence": attrs.level_confidence,
                "source": PatternSource.LLM.value,
                "verified": False,
                "datasource_luid": datasource_luid,
            }
            self._pattern_store.set(pid, pattern)
            pattern_ids.append(pid)
            new_patterns.append(pattern)
        
        if new_patterns:
            self._pattern_store.set("_pattern_index", pattern_ids)
            
            # 增量更新向量索引
            self._add_patterns_to_vector_index(new_patterns)
            
            logger.info(f"自学习: 存储 {len(new_patterns)} 个新模式")
        
        return len(new_patterns)
    
    def _add_patterns_to_vector_index(self, patterns: List[Dict[str, Any]]) -> None:
        """增量添加 patterns 到向量索引"""
        if not patterns or not self._rag_retriever:
            return
        
        try:
            # CascadeRetriever 使用 _exact 和 _embedding 属性
            embedding_retriever = getattr(self._rag_retriever, '_embedding', None)
            exact_retriever = getattr(self._rag_retriever, '_exact', None)
            
            if not embedding_retriever or not hasattr(embedding_retriever, '_store'):
                return
            
            vector_store = embedding_retriever._store
            if not vector_store or not hasattr(vector_store, 'add_texts'):
                return
            
            # 构建新文档
            texts, metadatas = [], []
            for p in patterns:
                index_text = f"{p['field_caption']} | {p.get('category', '')} | {p.get('category_detail', '')}"
                texts.append(index_text)
                metadatas.append({"field_name": p["pattern_id"], "field_caption": p["field_caption"]})
            
            # 增量添加
            vector_store.add_texts(texts, metadatas=metadatas)
            
            # 同时更新 chunks（用于精确匹配和结果映射）
            from analytics_assistant.src.infra.rag import FieldChunk
            for p in patterns:
                index_text = f"{p['field_caption']} | {p.get('category', '')} | {p.get('category_detail', '')}"
                chunk = FieldChunk(
                    field_name=p["pattern_id"],
                    field_caption=p["field_caption"],
                    role="dimension",
                    data_type=p["data_type"],
                    index_text=index_text,
                    category=p.get("category"),
                    metadata={"source": p.get("source"), "verified": p.get("verified", False)},
                )
                # 更新 ExactRetriever 的 chunks
                if exact_retriever and hasattr(exact_retriever, '_chunks'):
                    exact_retriever._chunks[chunk.field_name] = chunk
                    # 重建索引
                    exact_retriever._build_index()
                # 更新 EmbeddingRetriever 的 chunks
                if hasattr(embedding_retriever, '_chunks'):
                    embedding_retriever._chunks[chunk.field_name] = chunk
            
            # 持久化索引
            if hasattr(vector_store, 'save_local'):
                app_config = get_config()
                vector_cfg = app_config.config.get("vector_storage", {})
                index_dir = vector_cfg.get("index_dir", "analytics_assistant/data/indexes")
                from pathlib import Path
                save_path = Path(index_dir) / "dimension_patterns"
                vector_store.save_local(str(save_path))
            
            logger.debug(f"向量索引已更新: +{len(patterns)} 条")
            
        except Exception as e:
            logger.warning(f"更新向量索引失败: {e}")

    
    # ─────────────────────────────────────────────────────────
    # 主推断方法
    # ─────────────────────────────────────────────────────────
    
    async def infer(
        self,
        datasource_luid: str,
        fields: List[Field],
        table_id: Optional[str] = None,
        skip_cache: bool = False,
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> DimensionHierarchyResult:
        """
        推断维度层级
        
        Args:
            datasource_luid: 数据源 LUID
            fields: Field 模型列表
            table_id: 逻辑表 ID（多表数据源时使用）
            skip_cache: 是否跳过缓存
            on_token: Token 回调（用于流式输出展示）
        
        Returns:
            DimensionHierarchyResult 推断结果
        """
        if not fields:
            self._last_result = DimensionHierarchyResult(dimension_hierarchy={})
            return self._last_result
        
        cache_key = build_cache_key(datasource_luid, table_id)
        
        # 确保种子数据已初始化
        self._ensure_seed_data()
        
        # 获取锁，避免同一数据源的并发推断
        lock = await self._get_lock(cache_key)
        async with lock:
            return await self._infer_with_lock(
                datasource_luid, fields, table_id, cache_key, skip_cache, on_token
            )
    
    async def _infer_with_lock(
        self,
        datasource_luid: str,
        fields: List[Field],
        table_id: Optional[str],
        cache_key: str,
        skip_cache: bool,
        on_token: Optional[Callable[[str], Awaitable[None]]],
    ) -> DimensionHierarchyResult:
        """在锁保护下执行推断"""
        results: Dict[str, DimensionAttributes] = {}
        
        # 1. 缓存检查
        cached_data, cached_hashes, cached_names = None, None, None
        if not skip_cache and self._incremental_enabled:
            cached = self._get_cache(cache_key)
            if cached:
                cached_data = cached.get("data", {})
                cached_hashes = cached.get("field_hashes", {})
                cached_names = set(cached_data.keys())
                
                if compute_fields_hash(fields) == cached.get("field_hash"):
                    logger.info(f"缓存完全命中: {len(cached_data)} 个字段")
                    for name, data in cached_data.items():
                        results[name] = self._deserialize_attrs(data)
                    self._last_result = DimensionHierarchyResult(dimension_hierarchy=results)
                    return self._last_result
        
        # 2. 增量计算
        incremental = compute_incremental_fields(fields, cached_hashes, cached_names)
        
        if cached_data:
            for name in incremental.unchanged_fields:
                if name in cached_data:
                    results[name] = self._deserialize_attrs(cached_data[name])
        
        fields_to_infer = [f for f in fields if (f.caption or f.name) in incremental.fields_to_infer]
        
        if not fields_to_infer:
            logger.info(f"增量检测: 无需推断，复用 {len(results)} 个缓存")
            self._update_cache(cache_key, fields, results)
            self._last_result = DimensionHierarchyResult(dimension_hierarchy=results)
            return self._last_result
        
        logger.info(f"增量推断: 新增={len(incremental.new_fields)}, 变更={len(incremental.changed_fields)}")
        
        # 3. 种子匹配
        fields_after_seed = []
        for f in fields_to_infer:
            name = f.caption or f.name
            seed = self._match_seed(name)
            if seed:
                results[name] = DimensionAttributes(
                    category=DimensionCategory(seed["category"]),
                    category_detail=seed["category_detail"],
                    level=seed["level"],
                    granularity=seed["granularity"],
                    level_confidence=1.0,
                    reasoning=f"种子匹配: {seed.get('reasoning', name)}",
                )
            else:
                fields_after_seed.append(f)
        
        # 4. RAG 检索
        fields_after_rag = fields_after_seed
        if self._enable_rag and fields_after_seed:
            self._init_rag()
            if self._rag_retriever:
                rag_results, fields_after_rag = await self._rag_search(fields_after_seed)
                results.update(rag_results)
        
        # 5. LLM 推断
        if fields_after_rag:
            await self._llm_infer(fields_after_rag, results, on_token)
        
        # 6. 自学习
        if self._enable_self_learning:
            self._store_to_rag(results, fields, datasource_luid)
        
        # 7. 建立父子关系
        self._build_parent_child_relations(results)
        
        # 8. 更新缓存
        self._update_cache(cache_key, fields, results)
        
        seed_count = len(fields_to_infer) - len(fields_after_seed)
        rag_count = len(fields_after_seed) - len(fields_after_rag)
        logger.info(f"推断完成: 种子={seed_count}, RAG={rag_count}, LLM={len(fields_after_rag)}, 总计={len(results)}")
        self._last_result = DimensionHierarchyResult(dimension_hierarchy=results)
        return self._last_result
    
    def _build_parent_child_relations(self, results: Dict[str, DimensionAttributes]) -> None:
        """根据 category + level 建立父子关系
        
        策略：
        1. 按 category（大类）分组
        2. 在同一 category 内，按 level 排序
        3. 相邻 level 建立父子关系
        4. 同一 level 有多个字段时，优先匹配相同 category_detail 前缀的
        """
        # 按 category 分组
        by_category: Dict[str, List[tuple]] = {}
        for name, attrs in results.items():
            cat = attrs.category.value
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append((name, attrs))
        
        # 对每个 category 建立父子关系
        for cat, items in by_category.items():
            if len(items) < 2:
                continue
            
            # 按 level 分组
            by_level: Dict[int, List[tuple]] = {}
            for name, attrs in items:
                level = attrs.level
                if level not in by_level:
                    by_level[level] = []
                by_level[level].append((name, attrs))
            
            # 获取排序后的 level 列表
            levels = sorted(by_level.keys())
            
            # 对相邻 level 建立关系
            for i in range(len(levels) - 1):
                parent_level = levels[i]
                child_level = levels[i + 1]
                
                parent_items = by_level[parent_level]
                child_items = by_level[child_level]
                
                # 匹配父子关系
                self._match_by_level(parent_items, child_items)
    
    def _match_by_level(
        self,
        parent_items: List[tuple],
        child_items: List[tuple],
    ) -> None:
        """在相邻 level 之间匹配父子关系
        
        策略：
        1. 一对一直接匹配
        2. 多对多时，优先匹配 category_detail 前缀相同的
        3. 其次用名称相似度辅助
        """
        # 过滤已有关系的
        available_parents = [(n, a) for n, a in parent_items if not a.child_dimension]
        available_children = [(n, a) for n, a in child_items if not a.parent_dimension]
        
        if not available_parents or not available_children:
            return
        
        # 一对一直接匹配
        if len(available_parents) == 1 and len(available_children) == 1:
            parent_name, parent_attrs = available_parents[0]
            child_name, child_attrs = available_children[0]
            parent_attrs.child_dimension = child_name
            child_attrs.parent_dimension = parent_name
            return
        
        # 多对多：按优先级匹配
        matched_children = set()
        for parent_name, parent_attrs in available_parents:
            if parent_attrs.child_dimension:
                continue
            
            best_match = None
            best_score = -1
            
            for child_name, child_attrs in available_children:
                if child_name in matched_children or child_attrs.parent_dimension:
                    continue
                
                # 计算匹配分数
                score = self._compute_match_score(
                    parent_name, parent_attrs,
                    child_name, child_attrs
                )
                
                if score > best_score:
                    best_score = score
                    best_match = (child_name, child_attrs)
            
            # 建立关系
            if best_match:
                child_name, child_attrs = best_match
                parent_attrs.child_dimension = child_name
                child_attrs.parent_dimension = parent_name
                matched_children.add(child_name)
    
    def _compute_match_score(
        self,
        parent_name: str, parent_attrs: DimensionAttributes,
        child_name: str, child_attrs: DimensionAttributes,
    ) -> float:
        """计算父子匹配分数
        
        优先级：
        1. category_detail 前缀匹配（如 geography-province 和 geography-city 共享 geography）
        2. 名称相似度
        """
        score = 0.0
        
        # 1. category_detail 前缀匹配（基础分）
        # 同一 category 内的字段，category_detail 前缀一定相同
        # 这里主要是为了区分不同子类（如 geography-region vs geography-province）
        parent_detail = parent_attrs.category_detail
        child_detail = child_attrs.category_detail
        
        # 提取 category_detail 的子类部分（如 geography-province -> province）
        parent_sub = parent_detail.split('-')[-1] if '-' in parent_detail else parent_detail
        child_sub = child_detail.split('-')[-1] if '-' in child_detail else child_detail
        
        # 如果子类名称有包含关系，加分（如 province 和 city 都是地理概念）
        # 这里简单处理：同一 category 内默认有基础分
        score = 0.5
        
        # 2. 名称相似度加分
        name_sim = self._compute_name_similarity(parent_name, child_name)
        score += name_sim * 0.5
        
        return score
    
    def _compute_name_similarity(self, parent_name: str, child_name: str) -> float:
        """计算两个字段名的相似度
        
        返回 0-1 之间的分数
        """
        import re
        
        # 提取中文部分
        parent_cn = ''.join(re.findall(r'[\u4e00-\u9fff]+', parent_name))
        child_cn = ''.join(re.findall(r'[\u4e00-\u9fff]+', child_name))
        
        score = 0.0
        
        # 1. 检查中文共同前缀（如 "客户省" 和 "客户市" 共享 "客户"）
        if parent_cn and child_cn:
            common_prefix_len = 0
            for i in range(min(len(parent_cn), len(child_cn))):
                if parent_cn[i] == child_cn[i]:
                    common_prefix_len += 1
                else:
                    break
            
            if common_prefix_len > 0:
                score = common_prefix_len / max(len(parent_cn), len(child_cn))
        
        # 2. 检查英文共同前缀
        parent_en = ''.join(re.findall(r'[a-zA-Z_]+', parent_name.lower()))
        child_en = ''.join(re.findall(r'[a-zA-Z_]+', child_name.lower()))
        
        if parent_en and child_en:
            common_prefix_len = 0
            for i in range(min(len(parent_en), len(child_en))):
                if parent_en[i] == child_en[i]:
                    common_prefix_len += 1
                else:
                    break
            
            if common_prefix_len > 0:
                en_score = common_prefix_len / max(len(parent_en), len(child_en))
                score = max(score, en_score * 0.8)
        
        return score
    
    def _update_cache(self, key: str, fields: List[Field], results: Dict[str, DimensionAttributes]) -> None:
        """更新缓存"""
        if not self._cache:
            return
        field_hash = compute_fields_hash(fields)
        field_hashes = {f.caption or f.name: compute_single_field_hash(f) for f in fields}
        data = {name: self._serialize_attrs(attrs) for name, attrs in results.items()}
        self._put_cache(key, field_hash, field_hashes, data)

    
    # ─────────────────────────────────────────────────────────
    # LLM 推断
    # ─────────────────────────────────────────────────────────
    
    async def _llm_infer(
        self,
        fields: List[Field],
        results: Dict[str, DimensionAttributes],
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> None:
        """LLM 推断"""
        if not fields:
            return
        
        fields_input = [{"field_caption": f.caption or f.name, "data_type": f.data_type} for f in fields]
        user_prompt = build_user_prompt(fields_input, include_few_shot=True)
        messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_prompt)]
        
        llm = get_llm(agent_name="dimension_hierarchy", enable_json_mode=True)
        
        for attempt in range(self._max_retry):
            try:
                # 使用 stream_llm_structured 获取结构化输出
                llm_output: LLMDimensionOutput = await stream_llm_structured(
                    llm, messages, LLMDimensionOutput,
                    on_token=on_token,
                )
                
                # 转换为 DimensionAttributes 并更新 results
                hierarchy_result = llm_output.to_dimension_hierarchy_result()
                for name, attrs in hierarchy_result.dimension_hierarchy.items():
                    results[name] = attrs
                
                # 为未推断的字段设置默认值
                for f in fields:
                    name = f.caption or f.name
                    if name not in results:
                        results[name] = self._default_attrs(name)
                return
                
            except Exception as e:
                logger.warning(f"LLM 推断失败 (尝试 {attempt + 1}/{self._max_retry}): {e}")
        
        logger.error(f"LLM 推断失败，使用默认值: {len(fields)} 个字段")
        for f in fields:
            name = f.caption or f.name
            if name not in results:
                results[name] = self._default_attrs(name)
    
    def _default_attrs(self, name: str) -> DimensionAttributes:
        """默认属性"""
        return DimensionAttributes(
            category=DimensionCategory.OTHER,
            category_detail="other-unknown",
            level=3,
            granularity="medium",
            level_confidence=0.0,
            reasoning=f"推断失败: {name}",
        )

    
    # ─────────────────────────────────────────────────────────
    # 公开接口
    # ─────────────────────────────────────────────────────────
    
    def get_result(self) -> Optional[DimensionHierarchyResult]:
        """获取推断结果"""
        return self._last_result
    
    def enrich_fields(self, fields: List[Field]) -> List[Field]:
        """使用推断结果更新 Field 对象"""
        if not self._last_result:
            return fields
        
        for f in fields:
            name = f.caption or f.name
            attrs = self._last_result.dimension_hierarchy.get(name)
            if attrs:
                f.category = attrs.category.value
                f.category_detail = attrs.category_detail
                f.hierarchy_level = attrs.level
                f.granularity = attrs.granularity
                f.level_confidence = attrs.level_confidence
        
        return fields
    
    def clear_cache(self, cache_key: Optional[str] = None) -> bool:
        """清除缓存"""
        if not self._cache:
            return False
        return self._cache.delete(cache_key) if cache_key else False


# ══════════════════════════════════════════════════════════════
# 便捷函数
# ══════════════════════════════════════════════════════════════

async def infer_dimension_hierarchy(
    datasource_luid: str,
    fields: List[Field],
    table_id: Optional[str] = None,
    on_token: Optional[Callable[[str], Awaitable[None]]] = None,
) -> DimensionHierarchyResult:
    """便捷函数：推断维度层级"""
    inference = DimensionHierarchyInference()
    return await inference.infer(datasource_luid, fields, table_id, on_token=on_token)


__all__ = [
    "DimensionHierarchyInference",
    "DimensionHierarchyResult",
    "DimensionAttributes",
    "DimensionCategory",
    "IncrementalFieldsResult",
    "PatternSource",
    "build_cache_key",
    "compute_fields_hash",
    "compute_incremental_fields",
    "infer_dimension_hierarchy",
]
