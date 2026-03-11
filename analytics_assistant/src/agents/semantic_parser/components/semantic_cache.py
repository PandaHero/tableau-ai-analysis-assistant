# -*- coding: utf-8 -*-
"""
SemanticCache - 语义缓存抽象基类

提供 FeatureCache 和 QueryCache 的公共实现：
- LRU 淘汰
- 语义相似搜索（FAISS 索引）
- Embedding 缓存

配置来源：analytics_assistant/config/app.yaml -> rag_service.retrieval.score_type
"""
import logging
import threading
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Generic, Optional, TypeVar

import numpy as np

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.storage import CacheManager, get_kv_store
from analytics_assistant.src.infra.ai import get_embeddings
from analytics_assistant.src.infra.rag import cosine_similarity
from analytics_assistant.src.infra.rag.similarity import SimilarityCalculator, inner_product_similarity

# FAISS 可选依赖
try:
    import faiss
    _FAISS_AVAILABLE = True
except ImportError:
    faiss = None
    _FAISS_AVAILABLE = False

logger = logging.getLogger(__name__)

T = TypeVar("T")  # 缓存条目类型

class SemanticCache(ABC, Generic[T]):
    """语义缓存抽象基类
    
    提供公共功能：
    - LRU 淘汰
    - 语义相似搜索（FAISS 索引）
    - Embedding 缓存
    
    子类需要实现：
    - _make_namespace(): 生成存储命名空间
    - _validate_cached(): 验证缓存条目是否有效
    - _get_by_key(): 根据 key 获取缓存条目
    - _parse_cached(): 解析缓存值为类型 T
    """
    
    def __init__(
        self,
        namespace_prefix: str,
        default_ttl: int,
        similarity_threshold: float,
        max_cache_size: int,
        embedding_dim: int = 1024,
    ):
        """初始化语义缓存
        
        Args:
            namespace_prefix: 命名空间前缀
            default_ttl: 默认 TTL（秒）
            similarity_threshold: 相似度阈值
            max_cache_size: 最大缓存大小
            embedding_dim: Embedding 维度
        """
        self._namespace_prefix = namespace_prefix
        self._default_ttl = default_ttl
        self._similarity_threshold = similarity_threshold
        self._max_cache_size = max_cache_size
        self._embedding_dim = embedding_dim
        
        # FAISS 索引相关（按 datasource_luid 隔离）
        self._faiss_available = False
        self._faiss_indices: dict[str, Any] = {}       # datasource_luid -> faiss.Index
        self._id_to_key_maps: dict[str, dict[int, str]] = {}  # datasource_luid -> {FAISS ID -> cache key}
        self._key_to_id_maps: dict[str, dict[str, int]] = {}  # datasource_luid -> {cache key -> FAISS ID}
        self._next_ids: dict[str, int] = {}             # datasource_luid -> next_id
        self._index_rebuilt: set[str] = set()            # 已完成冷启动重建的 datasource
        
        # 线程安全锁
        self._faiss_lock = threading.RLock()
        
        # 缓存统计
        self._stats: dict[str, int] = {
            "exact_hits": 0,
            "semantic_hits": 0,
            "misses": 0,
            "faiss_hits": 0,
            "linear_hits": 0,
            "embedding_computes": 0,
            "ghost_rebuilds": 0,
            "cold_rebuilds": 0,
        }
        
        # 相似度计算器（从配置读取 score_type）
        self._similarity_calc = SimilarityCalculator.from_config()
        
        # Embedding 模型
        self._embedding = None
        self._init_embedding()
        
        # 尝试初始化 FAISS
        self._init_faiss()
        
        # CacheManager 实例缓存
        self._cache_managers: dict[str, CacheManager] = {}
        
        # 直接传入的 store（用于测试）
        self._direct_store = None
    
    def _init_embedding(self) -> None:
        """初始化 Embedding 模型"""
        try:
            self._embedding = get_embeddings()
        except Exception as e:
            logger.warning(f"无法初始化 embedding 模型: {e}")
    
    def _init_faiss(self) -> None:
        """检查 FAISS 是否可用（索引按数据源按需创建）"""
        if not _FAISS_AVAILABLE:
            logger.info("FAISS 不可用，将使用线性扫描进行相似度搜索")
            self._faiss_available = False
            return
        
        try:
            _test_index = faiss.IndexFlatIP(1)
            del _test_index
            self._faiss_available = True
            logger.debug("FAISS 可用")
        except Exception as e:
            logger.warning(f"FAISS 不可用: {e}")
            self._faiss_available = False
    
    # 幽灵向量占比超过此阈值时自动重建索引
    _GHOST_RATIO_REBUILD_THRESHOLD = 0.3
    
    def _get_or_create_faiss_index(self, datasource_luid: str):
        """获取或创建指定数据源的 FAISS 索引（调用方需持有 _faiss_lock）"""
        if datasource_luid not in self._faiss_indices:
            self._faiss_indices[datasource_luid] = faiss.IndexFlatIP(self._embedding_dim)
            self._id_to_key_maps[datasource_luid] = {}
            self._key_to_id_maps[datasource_luid] = {}
            self._next_ids[datasource_luid] = 0
        return self._faiss_indices[datasource_luid]
    
    def _reset_faiss_for_datasource(self, datasource_luid: str) -> None:
        """重置指定数据源的 FAISS 索引及映射"""
        with self._faiss_lock:
            self._faiss_indices.pop(datasource_luid, None)
            self._id_to_key_maps.pop(datasource_luid, None)
            self._key_to_id_maps.pop(datasource_luid, None)
            self._next_ids.pop(datasource_luid, None)
            self._index_rebuilt.discard(datasource_luid)
    
    def _add_to_faiss(self, datasource_luid: str, key: str, embedding: list[float]) -> None:
        """添加向量到 FAISS 索引
        
        Args:
            datasource_luid: 数据源 ID
            key: 缓存 key
            embedding: 向量
        """
        if not self._faiss_available:
            return
        
        if not embedding:
            return
        
        with self._faiss_lock:
            try:
                vec = np.array([embedding], dtype=np.float32)
                
                # 检查维度是否匹配，如果不匹配则重新初始化所有索引
                actual_dim = vec.shape[1]
                if actual_dim != self._embedding_dim:
                    logger.info(
                        f"Embedding 维度变化: {self._embedding_dim} -> {actual_dim}，"
                        f"重新初始化所有 FAISS 索引"
                    )
                    self._embedding_dim = actual_dim
                    self._faiss_indices.clear()
                    self._id_to_key_maps.clear()
                    self._key_to_id_maps.clear()
                    self._next_ids.clear()
                    self._index_rebuilt.clear()
                
                index = self._get_or_create_faiss_index(datasource_luid)
                id_to_key = self._id_to_key_maps[datasource_luid]
                key_to_id = self._key_to_id_maps[datasource_luid]
                
                faiss.normalize_L2(vec)  # 归一化用于余弦相似度
                
                index.add(vec)
                next_id = self._next_ids[datasource_luid]
                id_to_key[next_id] = key
                key_to_id[key] = next_id
                self._next_ids[datasource_luid] = next_id + 1
                
            except Exception as e:
                logger.warning(f"添加向量到 FAISS 失败: {e}")
    
    def _remove_from_faiss(self, datasource_luid: str, key: str) -> None:
        """从 FAISS 索引移除向量
        
        注意：FAISS IndexFlatIP 不支持直接删除，
        这里只是从映射中移除，实际向量仍在索引中。
        完整的删除需要重建索引。
        
        Args:
            datasource_luid: 数据源 ID
            key: 缓存 key
        """
        with self._faiss_lock:
            key_to_id = self._key_to_id_maps.get(datasource_luid)
            if key_to_id is None:
                return
            if key in key_to_id:
                faiss_id = key_to_id.pop(key)
                id_to_key = self._id_to_key_maps.get(datasource_luid)
                if id_to_key is not None:
                    id_to_key.pop(faiss_id, None)
    
    def _search_faiss(
        self,
        datasource_luid: str,
        query_embedding: list[float],
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        """在 FAISS 索引中搜索相似向量（仅搜索指定数据源）
        
        Args:
            datasource_luid: 数据源 ID
            query_embedding: 查询向量
            top_k: 返回数量
            
        Returns:
            [(key, score), ...] 列表
        """
        with self._faiss_lock:
            if not self._faiss_available:
                return []
            
            index = self._faiss_indices.get(datasource_luid)
            if index is None or index.ntotal == 0:
                return []
            
            id_to_key = self._id_to_key_maps.get(datasource_luid, {})
            
            try:
                vec = np.array([query_embedding], dtype=np.float32)
                faiss.normalize_L2(vec)
                
                scores, indices = index.search(
                    vec, min(top_k, index.ntotal)
                )
                
                results = []
                for score, idx in zip(scores[0], indices[0]):
                    if idx >= 0 and idx in id_to_key:
                        results.append((id_to_key[idx], float(score)))
                
                return results
                
            except Exception as e:
                logger.warning(f"FAISS 搜索失败: {e}")
                return []
    
    def _maybe_rebuild_index(self, datasource_luid: str) -> None:
        """当幽灵向量比例过高时自动重建索引
        
        Args:
            datasource_luid: 数据源 ID
        """
        needs_rebuild = False
        with self._faiss_lock:
            index = self._faiss_indices.get(datasource_luid)
            if index is not None and index.ntotal > 0:
                active_count = len(self._id_to_key_maps.get(datasource_luid, {}))
                ghost_ratio = 1.0 - (active_count / index.ntotal)
                if ghost_ratio > self._GHOST_RATIO_REBUILD_THRESHOLD:
                    needs_rebuild = True
                    logger.info(
                        f"幽灵向量比例 {ghost_ratio:.1%} 超过阈值 "
                        f"{self._GHOST_RATIO_REBUILD_THRESHOLD:.0%}，"
                        f"触发自动重建: datasource={datasource_luid}"
                    )
                    self._stats["ghost_rebuilds"] += 1
        if needs_rebuild:
            self.rebuild_faiss_index(datasource_luid)
    
    def _linear_search(
        self,
        query_embedding: list[float],
        datasource_luid: str,
        top_k: int = 10,
    ) -> list[tuple[str, float, Any]]:
        """线性扫描搜索（FAISS 不可用时的回退方案）
        
        Args:
            query_embedding: 查询向量
            datasource_luid: 数据源 ID
            top_k: 返回数量
            
        Returns:
            [(key, score, cached_value), ...] 列表
        """
        store = self._get_store()
        namespace = self._make_namespace(datasource_luid)
        items = store.search(namespace, limit=self._max_cache_size)
        
        scored = []
        for item in items:
            if item.value is None:
                continue
            
            cached = self._parse_cached(item.value)
            if cached is None:
                continue
            
            # 获取缓存的 embedding
            cached_embedding = self._get_cached_embedding(cached)
            if not cached_embedding:
                continue
            
            # 计算相似度
            raw_similarity = cosine_similarity(query_embedding, cached_embedding)
            similarity = inner_product_similarity(raw_similarity)
            scored.append((item.key, similarity, cached))
        
        # 按相似度排序
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
    
    def _get_store(self):
        """获取底层 store"""
        if self._direct_store is not None:
            return self._direct_store
        return get_kv_store()
    
    def _get_cache_manager(self, datasource_luid: str) -> Optional[CacheManager]:
        """获取指定数据源的 CacheManager
        
        Args:
            datasource_luid: 数据源 ID
            
        Returns:
            CacheManager 实例
        """
        if self._direct_store is not None:
            return None
        
        if datasource_luid not in self._cache_managers:
            namespace = f"{self._namespace_prefix}_{datasource_luid}"
            self._cache_managers[datasource_luid] = CacheManager(
                namespace=namespace,
                default_ttl=self._default_ttl,
            )
        return self._cache_managers[datasource_luid]
    
    # ═══════════════════════════════════════════════════════════════════════
    # 抽象方法（子类必须实现）
    # ═══════════════════════════════════════════════════════════════════════
    
    @abstractmethod
    def _make_namespace(self, datasource_luid: str) -> tuple:
        """生成存储命名空间
        
        Args:
            datasource_luid: 数据源 ID
            
        Returns:
            命名空间元组
        """
        pass
    
    @abstractmethod
    def _validate_cached(self, cached: T, **kwargs) -> bool:
        """验证缓存条目是否有效
        
        Args:
            cached: 缓存条目
            **kwargs: 额外验证参数
            
        Returns:
            是否有效
        """
        pass
    
    @abstractmethod
    def _parse_cached(self, value: dict[str, Any]) -> Optional[T]:
        """解析缓存值为类型 T
        
        Args:
            value: 缓存值字典
            
        Returns:
            解析后的缓存条目，失败返回 None
        """
        pass
    
    @abstractmethod
    def _get_cached_embedding(self, cached: T) -> Optional[list[float]]:
        """获取缓存条目的 embedding
        
        Args:
            cached: 缓存条目
            
        Returns:
            embedding 向量，没有则返回 None
        """
        pass
    
    @abstractmethod
    def _get_cached_expires_at(self, cached: T) -> datetime:
        """获取缓存条目的过期时间
        
        Args:
            cached: 缓存条目
            
        Returns:
            过期时间
        """
        pass
    
    # ═══════════════════════════════════════════════════════════════════════
    # 公共方法
    # ═══════════════════════════════════════════════════════════════════════
    
    def get_similar(
        self,
        question: str,
        datasource_luid: str,
        threshold: Optional[float] = None,
        **kwargs,
    ) -> Optional[T]:
        """语义相似匹配
        
        优先使用 FAISS 索引，不可用时回退到线性扫描。
        
        Args:
            question: 查询问题
            datasource_luid: 数据源 ID
            threshold: 相似度阈值
            **kwargs: 额外验证参数
            
        Returns:
            最佳匹配的缓存条目，没有则返回 None
        """
        if self._embedding is None:
            logger.debug("语义相似匹配不可用：未配置 embedding 模型")
            return None
        
        threshold = threshold or self._similarity_threshold
        
        try:
            # 冷启动重建：首次对该数据源做语义搜索时，从存储重建 FAISS 索引
            if self._faiss_available and datasource_luid not in self._index_rebuilt:
                with self._faiss_lock:
                    needs_cold_rebuild = datasource_luid not in self._index_rebuilt
                    if needs_cold_rebuild:
                        self._index_rebuilt.add(datasource_luid)
                if needs_cold_rebuild:
                    rebuilt_count = self.rebuild_faiss_index(datasource_luid)
                    if rebuilt_count > 0:
                        self._stats["cold_rebuilds"] += 1
                        logger.info(
                            f"冷启动重建 FAISS 索引: datasource={datasource_luid}, "
                            f"entries={rebuilt_count}"
                        )
            
            # 幽灵向量检查：比例过高时自动重建
            if self._faiss_available:
                self._maybe_rebuild_index(datasource_luid)
            
            # 快速检查：FAISS 索引是否有条目
            faiss_has_entries = False
            if self._faiss_available:
                with self._faiss_lock:
                    index = self._faiss_indices.get(datasource_luid)
                    faiss_has_entries = index is not None and index.ntotal > 0
            
            # 计算查询 embedding
            query_embedding = self._embedding.embed_query(question)
            self._stats["embedding_computes"] += 1
            
            # 优先使用 FAISS 搜索（按数据源隔离）
            if faiss_has_entries:
                similar_keys = self._search_faiss(datasource_luid, query_embedding, top_k=10)
                
                for key, score in similar_keys:
                    if score < threshold:
                        continue
                    
                    cached = self._get_by_key(key, datasource_luid)
                    if cached is None:
                        continue
                    
                    # FAISS 路径也检查过期（修复双重 TTL 不一致）
                    if datetime.now() > self._get_cached_expires_at(cached):
                        continue
                    
                    if self._validate_cached(cached, **kwargs):
                        self._stats["semantic_hits"] += 1
                        self._stats["faiss_hits"] += 1
                        logger.info(
                            f"FAISS 语义相似命中: score={score:.3f}, "
                            f"datasource={datasource_luid}"
                        )
                        return cached
            
            # FAISS 不可用或未找到，使用线性扫描
            results = self._linear_search(query_embedding, datasource_luid, top_k=10)
            
            for key, score, cached in results:
                if score < threshold:
                    continue
                
                # 检查过期
                if datetime.now() > self._get_cached_expires_at(cached):
                    continue
                
                if self._validate_cached(cached, **kwargs):
                    self._stats["semantic_hits"] += 1
                    self._stats["linear_hits"] += 1
                    logger.info(
                        f"线性扫描语义相似命中: score={score:.3f}"
                    )
                    return cached
            
            self._stats["misses"] += 1
            return None
            
        except Exception as e:
            logger.error(f"语义相似匹配失败: {e}")
            return None
    
    def _get_by_key(self, key: str, datasource_luid: str) -> Optional[T]:
        """根据 key 获取缓存条目
        
        Args:
            key: 缓存 key
            datasource_luid: 数据源 ID
            
        Returns:
            缓存条目，不存在返回 None
        """
        try:
            cache_manager = self._get_cache_manager(datasource_luid)
            if cache_manager is not None:
                value = cache_manager.get(key)
            else:
                namespace = self._make_namespace(datasource_luid)
                item = self._direct_store.get(namespace, key)
                value = item.value if item else None
            
            if value is None:
                return None
            
            return self._parse_cached(value)
            
        except Exception as e:
            logger.error(f"获取缓存失败: {e}")
            return None
    
    def rebuild_faiss_index(self, datasource_luid: str) -> int:
        """重建指定数据源的 FAISS 索引
        
        从存储中加载所有缓存条目，重建 FAISS 索引。
        用于冷启动加载和清理过期条目后的索引重建。
        
        Args:
            datasource_luid: 数据源 ID
            
        Returns:
            索引中的条目数量
        """
        if not self._faiss_available:
            return 0
        
        try:
            # 重置该数据源的索引
            self._reset_faiss_for_datasource(datasource_luid)
            
            # 加载所有缓存
            store = self._get_store()
            namespace = self._make_namespace(datasource_luid)
            items = store.search(namespace, limit=self._max_cache_size)
            
            count = 0
            for item in items:
                if item.value is None:
                    continue
                
                cached = self._parse_cached(item.value)
                if cached is None:
                    continue
                
                # 跳过过期的
                if datetime.now() > self._get_cached_expires_at(cached):
                    continue
                
                embedding = self._get_cached_embedding(cached)
                if embedding:
                    self._add_to_faiss(datasource_luid, item.key, embedding)
                    count += 1
            
            # 标记该数据源已完成重建
            self._index_rebuilt.add(datasource_luid)
            
            logger.info(
                f"FAISS 索引重建完成: datasource={datasource_luid}, entries={count}"
            )
            return count
            
        except Exception as e:
            logger.error(f"重建 FAISS 索引失败: {e}")
            return 0
    
    @property
    def faiss_available(self) -> bool:
        """FAISS 是否可用"""
        return self._faiss_available
    
    @property
    def default_ttl(self) -> int:
        """默认 TTL"""
        return self._default_ttl
    
    @property
    def similarity_threshold(self) -> float:
        """相似度阈值"""
        return self._similarity_threshold
    
    @property
    def cache_stats(self) -> dict[str, Any]:
        """获取缓存统计信息"""
        stats = dict(self._stats)
        with self._faiss_lock:
            stats["faiss_indices_count"] = len(self._faiss_indices)
            stats["faiss_details"] = {}
            for ds_luid, index in self._faiss_indices.items():
                active = len(self._id_to_key_maps.get(ds_luid, {}))
                total = index.ntotal if index else 0
                stats["faiss_details"][ds_luid] = {
                    "total_vectors": total,
                    "active_vectors": active,
                    "ghost_vectors": total - active,
                }
        return stats

__all__ = ["SemanticCache"]
