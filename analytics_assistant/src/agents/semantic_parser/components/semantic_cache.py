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
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar

import numpy as np

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.storage import CacheManager, get_kv_store
from analytics_assistant.src.infra.ai import get_embeddings
from analytics_assistant.src.infra.rag import cosine_similarity
from analytics_assistant.src.infra.rag.similarity import SimilarityCalculator

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
        
        # FAISS 索引相关
        self._faiss_available = False
        self._faiss_index = None
        self._id_to_key: Dict[int, str] = {}  # FAISS ID -> cache key
        self._key_to_id: Dict[str, int] = {}  # cache key -> FAISS ID
        self._next_id = 0
        
        # 相似度计算器（从配置读取 score_type）
        self._similarity_calc = SimilarityCalculator.from_config()
        
        # Embedding 模型
        self._embedding = None
        self._init_embedding()
        
        # 尝试初始化 FAISS
        self._init_faiss()
        
        # CacheManager 实例缓存
        self._cache_managers: Dict[str, CacheManager] = {}
        
        # 直接传入的 store（用于测试）
        self._direct_store = None
    
    def _init_embedding(self) -> None:
        """初始化 Embedding 模型"""
        try:
            self._embedding = get_embeddings()
        except Exception as e:
            logger.warning(f"无法初始化 embedding 模型: {e}")
    
    def _init_faiss(self) -> None:
        """初始化 FAISS 索引"""
        if not _FAISS_AVAILABLE:
            logger.info("FAISS 不可用，将使用线性扫描进行相似度搜索")
            self._faiss_available = False
            return
        
        try:
            self._faiss_index = faiss.IndexFlatIP(self._embedding_dim)
            self._faiss_available = True
            logger.debug("FAISS 索引已初始化")
        except Exception as e:
            logger.warning(f"初始化 FAISS 索引失败: {e}")
            self._faiss_available = False
    
    def _add_to_faiss(self, key: str, embedding: List[float]) -> None:
        """添加向量到 FAISS 索引
        
        Args:
            key: 缓存 key
            embedding: 向量
        """
        if not self._faiss_available or self._faiss_index is None:
            return
        
        if not embedding:
            return
        
        try:
            vec = np.array([embedding], dtype=np.float32)
            
            # 检查维度是否匹配，如果不匹配则重新初始化索引
            actual_dim = vec.shape[1]
            if actual_dim != self._embedding_dim:
                logger.info(
                    f"Embedding 维度变化: {self._embedding_dim} -> {actual_dim}，重新初始化 FAISS 索引"
                )
                self._embedding_dim = actual_dim
                self._faiss_index = faiss.IndexFlatIP(actual_dim)
                self._id_to_key.clear()
                self._key_to_id.clear()
                self._next_id = 0
            
            faiss.normalize_L2(vec)  # 归一化用于余弦相似度
            
            self._faiss_index.add(vec)
            self._id_to_key[self._next_id] = key
            self._key_to_id[key] = self._next_id
            self._next_id += 1
            
        except Exception as e:
            logger.warning(f"添加向量到 FAISS 失败: {e}")
    
    def _remove_from_faiss(self, key: str) -> None:
        """从 FAISS 索引移除向量
        
        注意：FAISS IndexFlatIP 不支持直接删除，
        这里只是从映射中移除，实际向量仍在索引中。
        完整的删除需要重建索引。
        
        Args:
            key: 缓存 key
        """
        if key in self._key_to_id:
            faiss_id = self._key_to_id.pop(key)
            self._id_to_key.pop(faiss_id, None)
    
    def _search_faiss(
        self, 
        query_embedding: List[float], 
        top_k: int = 10
    ) -> List[tuple[str, float]]:
        """在 FAISS 索引中搜索相似向量
        
        Args:
            query_embedding: 查询向量
            top_k: 返回数量
            
        Returns:
            [(key, score), ...] 列表
        """
        if not self._faiss_available or self._faiss_index is None:
            return []
        
        if self._faiss_index.ntotal == 0:
            return []
        
        try:
            vec = np.array([query_embedding], dtype=np.float32)
            faiss.normalize_L2(vec)
            
            scores, indices = self._faiss_index.search(
                vec, min(top_k, self._faiss_index.ntotal)
            )
            
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx >= 0 and idx in self._id_to_key:
                    results.append((self._id_to_key[idx], float(score)))
            
            return results
            
        except Exception as e:
            logger.warning(f"FAISS 搜索失败: {e}")
            return []
    
    def _linear_search(
        self,
        query_embedding: List[float],
        datasource_luid: str,
        top_k: int = 10,
    ) -> List[tuple[str, float, Any]]:
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
            similarity = self._similarity_calc.normalize(raw_similarity)
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
    def _parse_cached(self, value: Dict[str, Any]) -> Optional[T]:
        """解析缓存值为类型 T
        
        Args:
            value: 缓存值字典
            
        Returns:
            解析后的缓存条目，失败返回 None
        """
        pass
    
    @abstractmethod
    def _get_cached_embedding(self, cached: T) -> Optional[List[float]]:
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
            # 计算查询 embedding
            query_embedding = self._embedding.embed_query(question)
            
            # 优先使用 FAISS 搜索
            if self._faiss_available and self._faiss_index is not None:
                similar_keys = self._search_faiss(query_embedding, top_k=10)
                
                for key, score in similar_keys:
                    if score < threshold:
                        continue
                    
                    cached = self._get_by_key(key, datasource_luid)
                    if cached and self._validate_cached(cached, **kwargs):
                        logger.info(
                            f"FAISS 语义相似命中: score={score:.3f}"
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
                    logger.info(
                        f"线性扫描语义相似命中: score={score:.3f}"
                    )
                    return cached
            
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
        """重建 FAISS 索引
        
        从存储中加载所有缓存条目，重建 FAISS 索引。
        用于清理过期条目后的索引重建。
        
        Args:
            datasource_luid: 数据源 ID
            
        Returns:
            索引中的条目数量
        """
        if not self._faiss_available:
            return 0
        
        try:
            # 重置索引
            self._faiss_index = faiss.IndexFlatIP(self._embedding_dim)
            self._id_to_key.clear()
            self._key_to_id.clear()
            self._next_id = 0
            
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
                    self._add_to_faiss(item.key, embedding)
                    count += 1
            
            logger.info(f"FAISS 索引重建完成: {count} 条")
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


__all__ = ["SemanticCache"]
