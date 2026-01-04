"""
RAG 缓存管理

提供 Embedding 向量缓存功能
使用 LangGraph SqliteStore 作为统一的持久化存储

注意：VectorCache, MappingCache, CacheManager 已删除，
统一使用 LangGraph SqliteStore (通过 get_langgraph_store())
"""
import hashlib
import json
import logging
import time
from typing import List, Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)


# Embedding 缓存 TTL（7 天）
EMBEDDING_CACHE_TTL = 7 * 24 * 60 * 60


class CachedEmbeddingProvider:
    """
    带缓存的 Embedding 提供者包装器
    
    包装任意 EmbeddingProvider，添加缓存功能。
    使用 LangGraph SqliteStore 进行持久化存储。
    
    缓存命名空间: ("embedding_cache", model_name)
    """
    
    def __init__(
        self,
        provider: Any,  # EmbeddingProvider
        store_manager: Optional[Any] = None
    ):
        """
        初始化带缓存的提供者
        
        Args:
            provider: 原始 EmbeddingProvider
            store_manager: LangGraph SqliteStore 实例（可选，默认使用全局实例）
        """
        self.provider = provider
        
        # 获取 LangGraph SqliteStore
        if store_manager is not None:
            self._store_manager = store_manager
        else:
            try:
                from tableau_assistant.src.infra.storage import get_langgraph_store
                self._store_manager = get_langgraph_store()
            except Exception as e:
                logger.warning(f"无法获取 LangGraph Store，缓存将不可用: {e}")
                self._store_manager = None
        
        # 统计信息
        self._cache_hits = 0
        self._cache_misses = 0
    
    @property
    def model_name(self) -> str:
        return self.provider.model_name
    
    @property
    def dimensions(self) -> int:
        return self.provider.dimensions
    
    @staticmethod
    def _compute_hash(text: str) -> str:
        """计算文本哈希值"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def _get_cache_namespace(self) -> Tuple[str, ...]:
        """获取缓存命名空间"""
        return ("embedding_cache", self.model_name)
    
    def _get_from_cache(self, text: str) -> Optional[List[float]]:
        """从缓存获取向量"""
        if self._store_manager is None:
            return None
        
        try:
            text_hash = self._compute_hash(text)
            item = self._store_manager.get(
                namespace=self._get_cache_namespace(),
                key=text_hash
            )
            if item:
                return item.value.get("vector")
            return None
        except Exception as e:
            logger.warning(f"从缓存获取向量失败: {e}")
            return None
    
    def _put_to_cache(self, text: str, vector: List[float]) -> bool:
        """保存向量到缓存"""
        if self._store_manager is None:
            return False
        
        try:
            text_hash = self._compute_hash(text)
            self._store_manager.put(
                namespace=self._get_cache_namespace(),
                key=text_hash,
                value={"vector": vector, "text_preview": text[:100]},
                ttl=EMBEDDING_CACHE_TTL
            )
            return True
        except Exception as e:
            logger.warning(f"保存向量到缓存失败: {e}")
            return False
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        向量化文档（带缓存）
        
        Args:
            texts: 文档文本列表
        
        Returns:
            向量列表
        """
        if not texts:
            return []
        
        # 批量查询缓存
        cached: Dict[str, List[float]] = {}
        missed: List[str] = []
        
        for text in texts:
            vector = self._get_from_cache(text)
            if vector is not None:
                cached[text] = vector
                self._cache_hits += 1
            else:
                missed.append(text)
                self._cache_misses += 1
        
        logger.debug(f"Embedding 缓存: 命中 {len(cached)}, 未命中 {len(missed)}")
        
        # 对未命中的文本调用原始提供者
        if missed:
            new_vectors = self.provider.embed_documents(missed)
            
            # 保存到缓存
            for text, vector in zip(missed, new_vectors):
                self._put_to_cache(text, vector)
                cached[text] = vector
        
        # 按原始顺序返回
        return [cached[text] for text in texts]
    
    def embed_query(self, text: str) -> List[float]:
        """
        向量化查询（带缓存）
        
        Args:
            text: 查询文本
        
        Returns:
            查询向量
        """
        # 查询缓存
        vector = self._get_from_cache(text)
        
        if vector is not None:
            self._cache_hits += 1
            return vector
        
        self._cache_misses += 1
        
        # 调用原始提供者
        vector = self.provider.embed_query(text)
        
        # 保存到缓存
        self._put_to_cache(text, vector)
        
        return vector
    
    @property
    def cache_hit_rate(self) -> float:
        """缓存命中率"""
        total = self._cache_hits + self._cache_misses
        if total == 0:
            return 0.0
        return self._cache_hits / total
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        self._cache_hits = 0
        self._cache_misses = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total = self._cache_hits + self._cache_misses
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "total": total,
            "hit_rate": self.cache_hit_rate,
            "model_name": self.model_name,
            "ttl_days": EMBEDDING_CACHE_TTL / (24 * 60 * 60)
        }


__all__ = [
    "CachedEmbeddingProvider",
    "EMBEDDING_CACHE_TTL",
]
