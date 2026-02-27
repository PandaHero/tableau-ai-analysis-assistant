"""EmbeddingService - 统一的 Embedding 服务

封装 ModelManager 的 Embedding 能力，提供统一的缓存统计信息。

缓存策略：
- 复用 ModelManager.embed_documents_batch_with_stats() 内置的缓存
- ModelManager 返回缓存命中信息，EmbeddingService 统计

与 ModelManager 的关系：
- ModelManager 负责模型配置、API 调用、缓存
- EmbeddingService 负责业务层的统一入口和统计
"""

import logging
from dataclasses import dataclass
from typing import Optional

from analytics_assistant.src.infra.ai import get_model_manager, EmbeddingResult

logger = logging.getLogger(__name__)

@dataclass
class EmbeddingStats:
    """Embedding 统计（累计）"""
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    
    @property
    def hit_rate(self) -> float:
        """缓存命中率"""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total

class EmbeddingService:
    """统一的 Embedding 服务
    
    封装 ModelManager 的 Embedding 能力，提供统一的缓存统计信息。
    
    缓存策略：
    - 复用 ModelManager.embed_documents_batch_with_stats() 内置的缓存
    - ModelManager 返回缓存命中信息，EmbeddingService 统计
    
    与 ModelManager 的关系：
    - ModelManager 负责模型配置、API 调用、缓存
    - EmbeddingService 负责业务层的统一入口和统计
    """
    
    def __init__(self, model_id: Optional[str] = None):
        """初始化 EmbeddingService
        
        Args:
            model_id: 指定使用的 Embedding 模型 ID（可选）
        """
        self._model_manager = get_model_manager()
        self._model_id = model_id
        self._stats = EmbeddingStats()
    
    def embed_query(self, text: str) -> list[float]:
        """单文本向量化
        
        委托给 ModelManager，利用其内置缓存。
        
        Args:
            text: 要向量化的文本
            
        Returns:
            向量列表
        """
        self._stats.total_requests += 1
        result = self._model_manager.embed_documents_batch_with_stats(
            texts=[text],
            model_id=self._model_id,
            use_cache=True,
        )
        self._stats.cache_hits += result.cache_hits
        self._stats.cache_misses += result.cache_misses
        return result.vectors[0] if result.vectors else []
    
    def embed_documents(
        self,
        texts: list[str],
        batch_size: int = 20,
        max_concurrency: int = 5,
    ) -> list[list[float]]:
        """批量文本向量化
        
        委托给 ModelManager.embed_documents_batch_with_stats()。
        
        Args:
            texts: 文本列表
            batch_size: 每批文本数量
            max_concurrency: 最大并发数
            
        Returns:
            向量列表，与输入文本一一对应
        """
        self._stats.total_requests += len(texts)
        result = self._model_manager.embed_documents_batch_with_stats(
            texts=texts,
            model_id=self._model_id,
            batch_size=batch_size,
            max_concurrency=max_concurrency,
            use_cache=True,
        )
        self._stats.cache_hits += result.cache_hits
        self._stats.cache_misses += result.cache_misses
        return result.vectors
    
    async def embed_documents_async(
        self,
        texts: list[str],
        batch_size: int = 20,
        max_concurrency: int = 5,
    ) -> list[list[float]]:
        """异步批量文本向量化
        
        委托给 ModelManager.embed_documents_batch_with_stats_async()。
        
        Args:
            texts: 文本列表
            batch_size: 每批文本数量
            max_concurrency: 最大并发数
            
        Returns:
            向量列表，与输入文本一一对应
        """
        self._stats.total_requests += len(texts)
        result = await self._model_manager.embed_documents_batch_with_stats_async(
            texts=texts,
            model_id=self._model_id,
            batch_size=batch_size,
            max_concurrency=max_concurrency,
            use_cache=True,
        )
        self._stats.cache_hits += result.cache_hits
        self._stats.cache_misses += result.cache_misses
        return result.vectors
    
    def get_stats(self) -> EmbeddingStats:
        """获取统计信息
        
        Returns:
            累计的 Embedding 统计信息
        """
        return self._stats
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        self._stats = EmbeddingStats()
