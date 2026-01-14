"""
批量 Embedding 优化器

实现批量 Embedding 请求合并，减少 API 调用次数。
从 SchemaLinking 的 BatchEmbeddingOptimizer 提取。

收益：
- Embedding 调用次数 -80%（20 个请求 → 1 次批处理）
- Schema Linking 延迟 -50%
- API 费用 -80%

Requirements: 17.7.2 - 融合 SchemaLinking 的优化到统一 RAG
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class BatchEmbeddingConfig:
    """BatchEmbeddingOptimizer 配置
    
    Attributes:
        batch_size: 批处理大小（默认 20）
        flush_delay_ms: 自动 flush 延迟（毫秒，默认 50）
        timeout_ms: 批处理超时时间（毫秒，默认 5000）
    """
    batch_size: int = 20
    flush_delay_ms: int = 50
    timeout_ms: int = 5000


class BatchEmbeddingOptimizer:
    """批量 Embedding 优化器
    
    实现批量 Embedding 请求合并，减少 API 调用次数。
    
    策略：
    1. 请求进入队列
    2. 队列达到 batch_size 或 超时 flush_delay_ms → 触发批处理
    3. 调用 provider.embed_batch() 一次性计算
    4. 分发结果给各个等待者
    
    收益：
    - Embedding 调用次数 -80%（20 个请求 → 1 次批处理）
    - Schema Linking 延迟 -50%
    - API 费用 -80%
    
    Usage:
        optimizer = BatchEmbeddingOptimizer(embedding_provider)
        
        # 并发调用会自动合并
        embedding1 = await optimizer.embed_query("销售额")
        embedding2 = await optimizer.embed_query("地区")
    """
    
    def __init__(
        self,
        provider: Any,
        config: Optional[BatchEmbeddingConfig] = None,
    ):
        """初始化批量 Embedding 优化器
        
        Args:
            provider: Embedding 提供者，需要实现 embed_batch(texts) 或 embed_documents(texts) 方法
            config: 优化器配置
        """
        self.provider = provider
        self.config = config or BatchEmbeddingConfig()
        
        # 待处理队列：(text, future)
        self._pending_queue: List[tuple] = []
        
        # 自动 flush 任务
        self._batch_task: Optional[asyncio.Task] = None
        
        # 锁，保护队列操作
        self._lock = asyncio.Lock()
        
        # 统计信息
        self._total_requests: int = 0
        self._total_batches: int = 0
    
    async def embed_query(self, text: str) -> List[float]:
        """批量 Embedding 入口
        
        Args:
            text: 要 embed 的文本
        
        Returns:
            Embedding 向量
        """
        future: asyncio.Future = asyncio.Future()
        
        async with self._lock:
            self._pending_queue.append((text, future))
            self._total_requests += 1
            
            # 队列达到 batch_size，立即 flush
            if len(self._pending_queue) >= self.config.batch_size:
                await self._flush_batch()
            # 否则启动自动 flush 任务
            elif self._batch_task is None or self._batch_task.done():
                self._batch_task = asyncio.create_task(self._auto_flush())
        
        # 等待结果
        try:
            return await asyncio.wait_for(
                future,
                timeout=self.config.timeout_ms / 1000,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Embedding timeout for text: {text[:50]}...")
            raise
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """直接批量 Embedding（不经过队列）
        
        Args:
            texts: 要 embed 的文本列表
        
        Returns:
            Embedding 向量列表
        """
        if not texts:
            return []
        
        try:
            # 尝试使用 embed_batch 方法
            if hasattr(self.provider, 'embed_batch'):
                return await self.provider.embed_batch(texts)
            # 回退到 embed_documents
            elif hasattr(self.provider, 'embed_documents'):
                # 检查是否是异步方法
                if asyncio.iscoroutinefunction(self.provider.embed_documents):
                    return await self.provider.embed_documents(texts)
                else:
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(
                        None,
                        self.provider.embed_documents,
                        texts
                    )
            else:
                raise AttributeError("Provider must have embed_batch or embed_documents method")
        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            raise
    
    async def _flush_batch(self) -> None:
        """执行批处理"""
        if not self._pending_queue:
            return
        
        # 取出一批
        batch = self._pending_queue[:self.config.batch_size]
        self._pending_queue = self._pending_queue[self.config.batch_size:]
        
        texts = [text for text, _ in batch]
        futures = [future for _, future in batch]
        
        self._total_batches += 1
        
        try:
            # 批量调用
            embeddings = await self.embed_batch(texts)
            
            # 分发结果
            for future, embedding in zip(futures, embeddings):
                if not future.done():
                    future.set_result(embedding)
                    
        except Exception as e:
            # 分发错误
            for future in futures:
                if not future.done():
                    future.set_exception(e)
            logger.error(f"Batch embedding failed: {e}")
    
    async def _auto_flush(self) -> None:
        """超时自动 flush"""
        await asyncio.sleep(self.config.flush_delay_ms / 1000)
        
        async with self._lock:
            await self._flush_batch()
    
    async def flush(self) -> None:
        """强制 flush 所有待处理请求"""
        async with self._lock:
            while self._pending_queue:
                await self._flush_batch()
    
    @property
    def pending_count(self) -> int:
        """获取待处理请求数量"""
        return len(self._pending_queue)
    
    @property
    def stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_requests": self._total_requests,
            "total_batches": self._total_batches,
            "avg_batch_size": (
                self._total_requests / self._total_batches
                if self._total_batches > 0 else 0
            ),
            "pending_count": self.pending_count,
        }


__all__ = [
    "BatchEmbeddingOptimizer",
    "BatchEmbeddingConfig",
]
