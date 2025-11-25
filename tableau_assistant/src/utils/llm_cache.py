"""
LLM 响应缓存

基于 PersistentStore 实现 LLM 响应缓存，减少重复调用和成本
"""
import hashlib
import json
import logging
from typing import Optional, Any, Dict
from tableau_assistant.src.components.persistent_store import PersistentStore

logger = logging.getLogger(__name__)


class LLMCache:
    """
    LLM 响应缓存
    
    使用 PersistentStore (SQLite) 缓存 LLM 响应
    """
    
    def __init__(self, store: PersistentStore, ttl: int = 3600):
        """
        初始化 LLM 缓存
        
        Args:
            store: PersistentStore 实例
            ttl: 缓存过期时间（秒），默认1小时
        """
        self.store = store
        self.ttl = ttl
        self.hit_count = 0
        self.miss_count = 0
    
    def _generate_cache_key(
        self,
        messages: list,
        model_name: str,
        temperature: float
    ) -> str:
        """
        生成缓存键
        
        Args:
            messages: 消息列表
            model_name: 模型名称
            temperature: 温度参数
        
        Returns:
            缓存键（MD5 哈希）
        """
        # 构建缓存键的原始字符串
        cache_input = {
            "messages": messages,
            "model": model_name,
            "temperature": temperature
        }
        
        # 序列化为 JSON
        cache_str = json.dumps(cache_input, sort_keys=True, ensure_ascii=False)
        
        # 生成 MD5 哈希
        cache_key = hashlib.md5(cache_str.encode('utf-8')).hexdigest()
        
        return cache_key
    
    def get(
        self,
        messages: list,
        model_name: str,
        temperature: float
    ) -> Optional[str]:
        """
        从缓存获取 LLM 响应
        
        Args:
            messages: 消息列表
            model_name: 模型名称
            temperature: 温度参数
        
        Returns:
            缓存的响应内容，如果不存在返回 None
        """
        try:
            cache_key = self._generate_cache_key(messages, model_name, temperature)
            
            item = self.store.get(
                namespace=("llm_cache",),
                key=cache_key
            )
            
            if item:
                self.hit_count += 1
                logger.info(f"✓ LLM 缓存命中: {cache_key[:8]}...")
                return item.value.get("content")
            else:
                self.miss_count += 1
                logger.debug(f"✗ LLM 缓存未命中: {cache_key[:8]}...")
                return None
        
        except Exception as e:
            logger.error(f"获取 LLM 缓存失败: {e}")
            return None
    
    def set(
        self,
        messages: list,
        model_name: str,
        temperature: float,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        保存 LLM 响应到缓存
        
        Args:
            messages: 消息列表
            model_name: 模型名称
            temperature: 温度参数
            content: LLM 响应内容
            metadata: 额外的元数据（如 token 使用量）
        
        Returns:
            是否保存成功
        """
        try:
            cache_key = self._generate_cache_key(messages, model_name, temperature)
            
            cache_value = {
                "content": content,
                "model": model_name,
                "temperature": temperature,
                "metadata": metadata or {}
            }
            
            self.store.put(
                namespace=("llm_cache",),
                key=cache_key,
                value=cache_value,
                ttl=self.ttl
            )
            
            logger.debug(f"✓ LLM 响应已缓存: {cache_key[:8]}...")
            return True
        
        except Exception as e:
            logger.error(f"保存 LLM 缓存失败: {e}")
            return False
    
    def clear(self) -> bool:
        """
        清空所有 LLM 缓存
        
        Returns:
            是否清空成功
        """
        try:
            self.store.clear_namespace(("llm_cache",))
            logger.info("✓ LLM 缓存已清空")
            return True
        except Exception as e:
            logger.error(f"清空 LLM 缓存失败: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            统计信息字典
        """
        total_requests = self.hit_count + self.miss_count
        hit_rate = (self.hit_count / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "hit_count": self.hit_count,
            "miss_count": self.miss_count,
            "total_requests": total_requests,
            "hit_rate": f"{hit_rate:.2f}%"
        }


# ============= 导出 =============

__all__ = [
    "LLMCache",
]
