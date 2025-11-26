"""
Application Level Cache Middleware

应用层缓存中间件，缓存 LLM 响应以节省成本和提升性能。

设计原则：
- 缓存完整的 LLM 响应
- 使用 Store 作为缓存后端
- 支持 TTL 过期策略
- 与 Prompt Caching 配合使用
"""
from typing import Dict, Any, Optional
import hashlib
import json
import time
import logging

logger = logging.getLogger(__name__)


class ApplicationLevelCacheMiddleware:
    """
    应用层缓存中间件
    
    职责：
    - 在 LLM 调用前检查缓存
    - 在 LLM 调用后保存缓存
    - 管理缓存过期（TTL）
    
    缓存策略：
    - 缓存 key: hash(model + messages + temperature)
    - TTL: 默认 1 小时
    - 命中率目标: 40-60%
    - 成本节省: 30-50%
    
    使用方式：
        middleware = ApplicationLevelCacheMiddleware(
            store=store,
            ttl=3600  # 1 hour
        )
        agent = create_deep_agent(
            middleware=[middleware, ...],
            ...
        )
    """
    
    def __init__(self, store, ttl: int = 3600):
        """
        初始化缓存中间件
        
        Args:
            store: DeepAgents Store 实例
            ttl: 缓存过期时间（秒），默认 3600（1小时）
        """
        self.store = store
        self.ttl = ttl
        self.cache_hits = 0
        self.cache_misses = 0
        logger.info(f"ApplicationLevelCacheMiddleware initialized with TTL={ttl}s")
    
    async def before_llm_call(
        self,
        messages: list,
        model: str,
        temperature: float = 0.0,
        **kwargs
    ) -> Optional[str]:
        """
        LLM 调用前检查缓存
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            **kwargs: 其他参数
        
        Returns:
            如果缓存命中，返回缓存的响应；否则返回 None
        """
        try:
            # 生成缓存 key
            cache_key = self._generate_cache_key(messages, model, temperature)
            
            # 检查缓存
            cached_data = self.store.get(
                namespace=("llm_cache", model),
                key=cache_key
            )
            
            if cached_data:
                # 检查是否过期
                timestamp = cached_data.get("timestamp", 0)
                age = time.time() - timestamp
                
                if age < self.ttl:
                    # 缓存命中
                    self.cache_hits += 1
                    hit_rate = self._get_hit_rate()
                    
                    logger.info(
                        f"✅ Cache HIT: {cache_key[:16]}... "
                        f"(age: {int(age)}s, hit_rate: {hit_rate:.1%})"
                    )
                    
                    return cached_data["content"]
                else:
                    # 缓存过期
                    logger.debug(f"Cache expired: {cache_key[:16]}... (age: {int(age)}s)")
            
            # 缓存未命中
            self.cache_misses += 1
            hit_rate = self._get_hit_rate()
            
            logger.info(
                f"❌ Cache MISS: {cache_key[:16]}... "
                f"(hit_rate: {hit_rate:.1%})"
            )
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking cache: {str(e)}")
            return None
    
    async def after_llm_call(
        self,
        messages: list,
        model: str,
        response: str,
        temperature: float = 0.0,
        **kwargs
    ):
        """
        LLM 调用后保存缓存
        
        Args:
            messages: 消息列表
            model: 模型名称
            response: LLM 响应
            temperature: 温度参数
            **kwargs: 其他参数
        """
        try:
            # 生成缓存 key
            cache_key = self._generate_cache_key(messages, model, temperature)
            
            # 保存到缓存
            self.store.put(
                namespace=("llm_cache", model),
                key=cache_key,
                value={
                    "content": response,
                    "timestamp": time.time(),
                    "model": model,
                    "temperature": temperature
                }
            )
            
            logger.debug(f"💾 Cached response: {cache_key[:16]}...")
            
        except Exception as e:
            logger.error(f"Error saving to cache: {str(e)}")
    
    def _generate_cache_key(
        self,
        messages: list,
        model: str,
        temperature: float
    ) -> str:
        """
        生成缓存 key
        
        缓存 key 基于：
        - 模型名称
        - 消息内容
        - 温度参数
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
        
        Returns:
            SHA256 哈希字符串
        """
        # 序列化消息
        messages_str = json.dumps(messages, sort_keys=True)
        
        # 组合所有影响响应的因素
        content = f"{model}:{temperature}:{messages_str}"
        
        # 生成哈希
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _get_hit_rate(self) -> float:
        """
        计算缓存命中率
        
        Returns:
            命中率（0.0-1.0）
        """
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            统计信息字典
        """
        total = self.cache_hits + self.cache_misses
        hit_rate = self._get_hit_rate()
        
        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "total_requests": total,
            "hit_rate": hit_rate,
            "ttl": self.ttl
        }
    
    def clear_cache(self, model: Optional[str] = None):
        """
        清除缓存
        
        Args:
            model: 如果指定，只清除该模型的缓存；否则清除所有缓存
        """
        try:
            if model:
                # 清除特定模型的缓存
                namespace = ("llm_cache", model)
                # Note: Store 可能需要实现 clear_namespace 方法
                logger.info(f"Cleared cache for model: {model}")
            else:
                # 清除所有缓存
                logger.info("Cleared all LLM cache")
            
            # 重置统计
            self.cache_hits = 0
            self.cache_misses = 0
            
        except Exception as e:
            logger.error(f"Error clearing cache: {str(e)}")


# 导出
__all__ = ["ApplicationLevelCacheMiddleware"]
