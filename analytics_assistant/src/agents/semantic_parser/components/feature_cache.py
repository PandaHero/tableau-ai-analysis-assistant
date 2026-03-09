# -*- coding: utf-8 -*-
"""
FeatureCache - 特征缓存

缓存 FeatureExtractor 的输出，支持：
- 精确匹配：hash(question + datasource_luid)
- 语义匹配：embedding 相似度 > 0.95

基于 SemanticCache 基类构建，与 QueryCache 共享相同的缓存基础设施。

与 QueryCache 的区别：
- QueryCache: 缓存最终查询结果，TTL 24 小时，需要 schema_hash 验证
- FeatureCache: 缓存中间特征提取结果，TTL 1 小时，无 schema_hash 验证

配置来源：analytics_assistant/config/app.yaml -> semantic_parser.optimization

用法：
    from analytics_assistant.src.agents.semantic_parser.components.feature_cache import (
        FeatureCache,
    )
    
    cache = FeatureCache()
    
    # 精确匹配获取
    cached = cache.get(question, datasource_luid)
    
    # 语义相似匹配获取
    cached = cache.get_similar(question, datasource_luid)
    
    # 设置缓存
    cache.set(question, datasource_luid, feature_output)
"""
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.storage import get_kv_store

from ..schemas.cache import CachedFeature
from ..schemas.prefilter import FeatureExtractionOutput
from .semantic_cache import SemanticCache

logger = logging.getLogger(__name__)

_feature_cache_singleton: Optional["FeatureCache"] = None
_FEATURE_CACHE_VERSION = "semantic-v4-step-intent"

# ═══════════════════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════════════════

def _get_config() -> dict[str, Any]:
    """获取 feature_cache 配置。"""
    try:
        config = get_config()
        return config.get_semantic_parser_optimization_config()
    except Exception as e:
        logger.warning(f"无法加载配置，使用默认值: {e}")
        return {}

def compute_feature_hash(question: str, datasource_luid: str) -> str:
    """计算特征缓存的 hash。"""
    content = f"{datasource_luid}:{question.strip().lower()}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()

# ═══════════════════════════════════════════════════════════════════════════
# FeatureCache 组件（继承 SemanticCache）
# ═══════════════════════════════════════════════════════════════════════════

class FeatureCache(SemanticCache[CachedFeature]):
    """特征缓存管理器
    
    继承 SemanticCache 基类，提供：
    - 精确匹配缓存
    - 语义相似匹配（FAISS 索引优化）
    - TTL 1 小时
    
    配置来源：app.yaml -> semantic_parser.optimization
    """
    
    # 命名空间前缀（固定值）
    NAMESPACE_PREFIX = "feature_cache"
    
    # 默认配置（作为 fallback）
    _DEFAULT_TTL = 3600  # 1 小时
    _DEFAULT_SIMILARITY_THRESHOLD = 0.95
    _DEFAULT_MAX_CACHE_SIZE = 1000
    
    def __init__(
        self,
        store: Optional[Any] = None,
        embedding_model: Optional[Any] = None,
        default_ttl: Optional[int] = None,
        similarity_threshold: Optional[float] = None,
    ):
        """初始化 FeatureCache
        
        Args:
            store: 直接传入的 store 实例（用于测试）
            embedding_model: Embedding 模型
            default_ttl: 默认 TTL（秒）
            similarity_threshold: 语义相似匹配阈值
        """
        # 从配置加载参数
        config = _get_config()
        
        actual_ttl = (
            default_ttl
            if default_ttl is not None
            else config.get("feature_cache_ttl_seconds", self._DEFAULT_TTL)
        )
        actual_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else config.get("feature_cache_similarity_threshold", self._DEFAULT_SIMILARITY_THRESHOLD)
        )
        max_cache_size = config.get("feature_cache_max_size", self._DEFAULT_MAX_CACHE_SIZE)
        
        # 调用父类初始化
        super().__init__(
            namespace_prefix=self.NAMESPACE_PREFIX,
            default_ttl=actual_ttl,
            similarity_threshold=actual_threshold,
            max_cache_size=max_cache_size,
        )
        
        # 测试场景：直接传入 store
        self._direct_store = store
        
        # 覆盖 embedding（如果传入）
        if embedding_model is not None:
            self._embedding = embedding_model
        
        logger.info(
            f"FeatureCache 已初始化: ttl={self._default_ttl}s, "
            f"similarity_threshold={self._similarity_threshold}, "
            f"faiss_available={self._faiss_available}"
        )
    
    # ═══════════════════════════════════════════════════════════════════════
    # 实现抽象方法
    # ═══════════════════════════════════════════════════════════════════════
    
    def _make_namespace(self, datasource_luid: str) -> tuple:
        """生成存储命名空间"""
        return ("semantic_parser", "feature_cache", datasource_luid)
    
    def _validate_cached(self, cached: CachedFeature, **kwargs) -> bool:
        """验证缓存条目是否有效
        
        FeatureCache 不需要 schema_hash 验证，只检查 TTL。
        """
        return (
            datetime.now() <= cached.expires_at
            and cached.parser_version == _FEATURE_CACHE_VERSION
        )
    
    def _parse_cached(self, value: dict[str, Any]) -> Optional[CachedFeature]:
        """解析缓存值"""
        try:
            return CachedFeature.model_validate(value)
        except Exception as e:
            logger.debug(f"解析 FeatureCache 缓存值失败: {e}")
            return None
    
    def _get_cached_embedding(self, cached: CachedFeature) -> Optional[list[float]]:
        """获取缓存条目的 embedding"""
        return cached.question_embedding if cached.question_embedding else None
    
    def _get_cached_expires_at(self, cached: CachedFeature) -> datetime:
        """获取缓存条目的过期时间"""
        return cached.expires_at
    
    # ═══════════════════════════════════════════════════════════════════════
    # 公共方法
    # ═══════════════════════════════════════════════════════════════════════
    
    def get(
        self,
        question: str,
        datasource_luid: str,
    ) -> Optional[CachedFeature]:
        """精确匹配获取缓存
        
        流程：
        1. 计算 question hash
        2. 从缓存中查找
        3. 检查 TTL 是否过期
        """
        question_hash = compute_feature_hash(question, datasource_luid)
        
        try:
            cached = self._get_by_key(question_hash, datasource_luid)
            
            if cached is None:
                logger.debug(f"FeatureCache 未命中: question_hash={question_hash[:8]}...")
                return None
            
            # TTL 检查
            if datetime.now() > cached.expires_at:
                logger.debug(f"FeatureCache TTL 过期: question_hash={question_hash[:8]}...")
                return None

            if cached.parser_version != _FEATURE_CACHE_VERSION:
                logger.info(
                    "FeatureCache 版本不匹配，缓存失效: cached=%s, current=%s",
                    cached.parser_version,
                    _FEATURE_CACHE_VERSION,
                )
                return None
            
            # 更新命中计数
            cached.hit_count += 1
            self._put_cached(datasource_luid, question_hash, cached)
            
            logger.info(f"FeatureCache 命中: question='{question[:20]}...', hit_count={cached.hit_count}")
            return cached
            
        except Exception as e:
            logger.error(f"FeatureCache get 失败: {e}")
            return None
    
    def _put_cached(self, datasource_luid: str, key: str, cached: CachedFeature) -> None:
        """存储缓存值"""
        cache_manager = self._get_cache_manager(datasource_luid)
        if cache_manager is not None:
            cache_manager.set(key, cached.model_dump())
        else:
            namespace = self._make_namespace(datasource_luid)
            self._direct_store.put(namespace, key, cached.model_dump())
    
    def set(
        self,
        question: str,
        datasource_luid: str,
        feature_output: FeatureExtractionOutput,
        ttl: Optional[int] = None,
        include_embedding: bool = True,
    ) -> bool:
        """设置缓存"""
        ttl = ttl or self._default_ttl
        question_hash = compute_feature_hash(question, datasource_luid)
        
        try:
            # 计算 embedding（如果可用）
            question_embedding = []
            if include_embedding and self._embedding:
                try:
                    question_embedding = self._embedding.embed_query(question)
                except (ConnectionError, TimeoutError) as e:
                    logger.warning(f"计算 question embedding 网络错误: {e}")
                except ValueError as e:
                    logger.warning(f"计算 question embedding 参数错误: {e}")
                except Exception as e:
                    logger.error(f"计算 question embedding 未知错误: {type(e).__name__}: {e}")
            
            cached = CachedFeature(
                question=question,
                question_hash=question_hash,
                question_embedding=question_embedding,
                datasource_luid=datasource_luid,
                parser_version=_FEATURE_CACHE_VERSION,
                feature_output=feature_output.model_dump(),
                created_at=datetime.now(),
                expires_at=datetime.now() + timedelta(seconds=ttl),
                hit_count=0,
            )
            
            # 存储
            cache_manager = self._get_cache_manager(datasource_luid)
            if cache_manager is not None:
                cache_manager.set(question_hash, cached.model_dump(), ttl=ttl)
            else:
                namespace = self._make_namespace(datasource_luid)
                ttl_minutes = ttl // 60
                self._direct_store.put(namespace, question_hash, cached.model_dump(), ttl=ttl_minutes)
            
            # 添加到 FAISS 索引
            if question_embedding:
                self._add_to_faiss(question_hash, question_embedding)
            
            logger.info(f"FeatureCache 已缓存: question='{question[:20]}...', ttl={ttl}s")
            return True
            
        except Exception as e:
            logger.error(f"FeatureCache set 失败: {e}")
            return False
    
    def invalidate_by_datasource(self, datasource_luid: str) -> int:
        """失效指定数据源的所有缓存"""
        try:
            cache_manager = self._get_cache_manager(datasource_luid)
            if cache_manager is not None:
                # 使用批量删除：删除所有条目
                deleted = cache_manager.delete_by_filter(lambda _: True)
                # 重置 FAISS 索引
                self._init_faiss()
                self._key_to_id.clear()
                self._id_to_key.clear()
                self._next_id = 0
                logger.info(f"FeatureCache 已失效 {deleted} 条缓存: datasource={datasource_luid}")
                return deleted
            else:
                store = self._direct_store
                namespace = self._make_namespace(datasource_luid)
                items = store.search(namespace, limit=10000)
                count = 0
                for item in items:
                    store.delete(namespace, item.key)
                    self._remove_from_faiss(item.key)
                    count += 1
                logger.info(f"FeatureCache 已失效 {count} 条缓存: datasource={datasource_luid}")
                return count
                
        except Exception as e:
            logger.error(f"FeatureCache invalidate_by_datasource 失败: {e}")
            return 0
    
    def get_stats(self, datasource_luid: Optional[str] = None) -> dict[str, Any]:
        """获取缓存统计信息"""
        try:
            store = self._get_store()
            
            if datasource_luid:
                namespace = self._make_namespace(datasource_luid)
                items = list(store.search(namespace, limit=self._max_cache_size))
            else:
                items = list(store.search(
                    ("semantic_parser", "feature_cache"), 
                    limit=self._max_cache_size * 10
                ))
            
            total_count = len(items)
            total_hits = 0
            expired_count = 0
            now = datetime.now()
            
            for item in items:
                if item.value is None:
                    continue
                try:
                    cached = CachedFeature.model_validate(item.value)
                    total_hits += cached.hit_count
                    if now > cached.expires_at:
                        expired_count += 1
                except Exception as e:
                    logger.debug(f"解析 FeatureCache 缓存条目失败: {e}")
                    pass
            
            return {
                "total_count": total_count,
                "active_count": total_count - expired_count,
                "expired_count": expired_count,
                "total_hits": total_hits,
                "ttl_seconds": self._default_ttl,
                "similarity_threshold": self._similarity_threshold,
                "faiss_available": self._faiss_available,
                "faiss_index_size": self._faiss_index.ntotal if self._faiss_index else 0,
            }
            
        except Exception as e:
            logger.error(f"获取 FeatureCache 统计失败: {e}")
            return {"error": str(e)}

__all__ = [
    "FeatureCache",
    "get_feature_cache",
    "compute_feature_hash",
]

def get_feature_cache() -> FeatureCache:
    """获取进程级 FeatureCache 单例。"""
    global _feature_cache_singleton
    if _feature_cache_singleton is None:
        _feature_cache_singleton = FeatureCache()
    return _feature_cache_singleton
