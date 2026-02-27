# -*- coding: utf-8 -*-
"""
QueryCache 组件 - 查询缓存管理

功能：
- 精确匹配缓存：基于问题 hash 的快速查找
- 语义相似缓存：基于向量相似度的模糊匹配（FAISS 优化）
- Schema Hash 失效：数据模型变更时自动失效缓存
- TTL 过期：默认 24 小时

继承 SemanticCache 基类，复用 FAISS 索引和线性扫描回退逻辑。

配置来源：analytics_assistant/config/app.yaml -> semantic_parser.query_cache

Requirements: 2.1-2.5 - QueryCache 查询缓存
"""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.storage import get_kv_store

from ..schemas.cache import CachedQuery
from .semantic_cache import SemanticCache

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════════════════

def _get_config() -> dict[str, Any]:
    """获取 query_cache 配置。"""
    try:
        config = get_config()
        return config.config.get("semantic_parser", {}).get("query_cache", {})
    except Exception as e:
        logger.warning(f"无法加载配置，使用默认值: {e}")
        return {}

# ═══════════════════════════════════════════════════════════════════════════
# Schema Hash 计算
# ═══════════════════════════════════════════════════════════════════════════

def compute_schema_hash(data_model: Any) -> str:
    """计算数据模型的 schema hash
    
    只包含影响查询生成的字段属性：
    - field.name: 字段名
    - field.data_type: 数据类型
    - field.role: 字段角色 (DIMENSION/MEASURE)
    
    不包含：
    - field.description: 描述变更不影响查询
    - field.caption: 显示名变更不影响查询
    """
    if not hasattr(data_model, 'fields') or not data_model.fields:
        return hashlib.md5(b"empty").hexdigest()
    
    field_signatures = []
    for field in data_model.fields:
        name = getattr(field, 'name', '') or getattr(field, 'field_name', '')
        data_type = getattr(field, 'data_type', '') or getattr(field, 'dataType', '')
        role = getattr(field, 'role', '') or getattr(field, 'field_role', '')
        field_signatures.append(f"{name}:{data_type}:{role}")
    
    field_signatures.sort()
    content = "|".join(field_signatures)
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def compute_question_hash(question: str, datasource_luid: str) -> str:
    """计算问题的 hash"""
    content = f"{datasource_luid}:{question.strip().lower()}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()

# ═══════════════════════════════════════════════════════════════════════════
# QueryCache 组件（继承 SemanticCache）
# ═══════════════════════════════════════════════════════════════════════════

class QueryCache(SemanticCache[CachedQuery]):
    """查询缓存管理器
    
    继承 SemanticCache 基类，提供：
    - 精确匹配缓存
    - 语义相似匹配（FAISS 索引优化）
    - Schema Hash 验证
    - TTL 24 小时
    
    配置来源：app.yaml -> semantic_parser.query_cache
    """
    
    # 命名空间前缀（固定值）
    NAMESPACE_PREFIX = "query_cache"
    
    # 默认配置（作为 fallback）
    _DEFAULT_TTL = 86400  # 24 小时
    _DEFAULT_SIMILARITY_THRESHOLD = 0.95
    _DEFAULT_MAX_CACHE_SIZE = 1000
    
    def __init__(
        self,
        store: Optional[Any] = None,
        embedding_model: Optional[Any] = None,
        default_ttl: Optional[int] = None,
        similarity_threshold: Optional[float] = None,
    ):
        """初始化 QueryCache
        
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
            else config.get("default_ttl", self._DEFAULT_TTL)
        )
        actual_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else config.get("similarity_threshold", self._DEFAULT_SIMILARITY_THRESHOLD)
        )
        max_cache_size = config.get("max_cache_size", self._DEFAULT_MAX_CACHE_SIZE)
        
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
            f"QueryCache 已初始化: ttl={self._default_ttl}s, "
            f"similarity_threshold={self._similarity_threshold}, "
            f"faiss_available={self._faiss_available}"
        )
    
    # ═══════════════════════════════════════════════════════════════════════
    # 实现抽象方法
    # ═══════════════════════════════════════════════════════════════════════
    
    def _make_namespace(self, datasource_luid: str) -> tuple:
        """生成存储命名空间"""
        return ("semantic_parser", "query_cache", datasource_luid)
    
    def _validate_cached(self, cached: CachedQuery, **kwargs) -> bool:
        """验证缓存条目是否有效
        
        QueryCache 需要检查：
        1. TTL 是否过期
        2. schema_hash 是否匹配
        """
        # TTL 检查
        if datetime.now() > cached.expires_at:
            return False
        
        # Schema hash 检查
        current_schema_hash = kwargs.get("current_schema_hash")
        if current_schema_hash and cached.schema_hash != current_schema_hash:
            return False
        
        return True
    
    def _parse_cached(self, value: dict[str, Any]) -> Optional[CachedQuery]:
        """解析缓存值"""
        try:
            return CachedQuery.model_validate(value)
        except Exception as e:
            logger.debug(f"解析 QueryCache 缓存值失败: {e}")
            return None
    
    def _get_cached_embedding(self, cached: CachedQuery) -> Optional[list[float]]:
        """获取缓存条目的 embedding"""
        return cached.question_embedding if cached.question_embedding else None
    
    def _get_cached_expires_at(self, cached: CachedQuery) -> datetime:
        """获取缓存条目的过期时间"""
        return cached.expires_at
    
    # ═══════════════════════════════════════════════════════════════════════
    # 公共方法
    # ═══════════════════════════════════════════════════════════════════════
    
    def get(
        self,
        question: str,
        datasource_luid: str,
        current_schema_hash: str,
    ) -> Optional[CachedQuery]:
        """精确匹配查询缓存
        
        流程：
        1. 计算 question hash
        2. 从缓存中查找
        3. 检查 TTL 是否过期
        4. 检查 schema_hash 是否匹配当前数据模型
        """
        question_hash = compute_question_hash(question, datasource_luid)
        
        try:
            cached = self._get_by_key(question_hash, datasource_luid)
            
            if cached is None:
                logger.debug(f"QueryCache 未命中: question_hash={question_hash[:8]}...")
                return None
            
            # TTL 检查
            if datetime.now() > cached.expires_at:
                logger.debug(f"QueryCache TTL 过期: question_hash={question_hash[:8]}...")
                return None
            
            # Schema hash 检查（核心失效机制）
            if cached.schema_hash != current_schema_hash:
                logger.info(
                    f"QueryCache schema_hash 不匹配，缓存失效: "
                    f"cached={cached.schema_hash[:8]}..., current={current_schema_hash[:8]}..."
                )
                return None
            
            # 更新命中计数
            cached.hit_count += 1
            self._put_cached(datasource_luid, question_hash, cached)
            
            logger.info(f"QueryCache 命中: question='{question[:20]}...', hit_count={cached.hit_count}")
            return cached
            
        except Exception as e:
            logger.error(f"QueryCache get 失败: {e}")
            return None
    
    def _put_cached(self, datasource_luid: str, key: str, cached: CachedQuery) -> None:
        """存储缓存值"""
        cache_manager = self._get_cache_manager(datasource_luid)
        if cache_manager is not None:
            cache_manager.set(key, cached.model_dump())
        else:
            namespace = self._make_namespace(datasource_luid)
            self._direct_store.put(namespace, key, cached.model_dump())
    
    def get_similar(
        self,
        question: str,
        datasource_luid: str,
        current_schema_hash: str,
        threshold: Optional[float] = None,
    ) -> Optional[CachedQuery]:
        """语义相似匹配
        
        重写父类方法，添加 schema_hash 验证。
        """
        return super().get_similar(
            question=question,
            datasource_luid=datasource_luid,
            threshold=threshold,
            current_schema_hash=current_schema_hash,
        )
    
    def set(
        self,
        question: str,
        datasource_luid: str,
        schema_hash: str,
        semantic_output: dict[str, Any],
        query: str,
        ttl: Optional[int] = None,
    ) -> bool:
        """设置缓存"""
        ttl = ttl or self._default_ttl
        question_hash = compute_question_hash(question, datasource_luid)
        
        try:
            # 计算 embedding（如果可用）
            question_embedding = None
            if self._embedding:
                try:
                    question_embedding = self._embedding.embed_query(question)
                except (ConnectionError, TimeoutError) as e:
                    logger.warning(f"计算 question embedding 网络错误: {e}")
                except ValueError as e:
                    logger.warning(f"计算 question embedding 参数错误: {e}")
                except Exception as e:
                    logger.error(f"计算 question embedding 未知错误: {type(e).__name__}: {e}")
            
            cached = CachedQuery(
                question=question,
                question_hash=question_hash,
                question_embedding=question_embedding,
                datasource_luid=datasource_luid,
                schema_hash=schema_hash,
                semantic_output=semantic_output,
                query=query,
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
            
            logger.info(f"QueryCache 已缓存: question='{question[:20]}...', ttl={ttl}s")
            return True
            
        except Exception as e:
            logger.error(f"QueryCache set 失败: {e}")
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
                logger.info(f"QueryCache 已失效 {deleted} 条缓存: datasource={datasource_luid}")
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
                logger.info(f"QueryCache 已失效 {count} 条缓存: datasource={datasource_luid}")
                return count
                
        except Exception as e:
            logger.error(f"QueryCache invalidate_by_datasource 失败: {e}")
            return 0
    
    def invalidate_by_schema_change(
        self,
        datasource_luid: str,
        new_schema_hash: str,
    ) -> int:
        """当数据模型变更时，主动失效旧版本的缓存"""
        try:
            cache_manager = self._get_cache_manager(datasource_luid)
            if cache_manager is not None:
                # 使用批量删除：仅删除 schema_hash 不匹配的条目
                def _schema_mismatch(value: dict) -> bool:
                    return value.get("schema_hash") != new_schema_hash

                deleted = cache_manager.delete_by_filter(_schema_mismatch)
                # 重置 FAISS 索引（部分删除后索引不一致，需重建）
                self._init_faiss()
                self._key_to_id.clear()
                self._id_to_key.clear()
                self._next_id = 0
                logger.info(
                    f"QueryCache schema 变更失效 {deleted} 条缓存: "
                    f"datasource={datasource_luid}, new_hash={new_schema_hash[:8]}..."
                )
                return deleted
            else:
                store = self._get_store()
                namespace = self._make_namespace(datasource_luid)
                items = store.search(namespace, limit=10000)
                count = 0
                for item in items:
                    if item.value is None:
                        continue
                    try:
                        cached = CachedQuery.model_validate(item.value)
                    except Exception as e:
                        logger.debug(f"解析 QueryCache 缓存条目失败（schema 变更检查）: {e}")
                        continue
                    if cached.schema_hash != new_schema_hash:
                        store.delete(namespace, item.key)
                        self._remove_from_faiss(item.key)
                        count += 1
                
                logger.info(
                    f"QueryCache schema 变更失效 {count} 条缓存: "
                    f"datasource={datasource_luid}, new_hash={new_schema_hash[:8]}..."
                )
                return count
            
        except Exception as e:
            logger.error(f"QueryCache invalidate_by_schema_change 失败: {e}")
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
                    ("semantic_parser", "query_cache"), 
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
                    cached = CachedQuery.model_validate(item.value)
                    total_hits += cached.hit_count
                    if now > cached.expires_at:
                        expired_count += 1
                except Exception as e:
                    logger.debug(f"解析 QueryCache 缓存条目失败: {e}")
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
            logger.error(f"获取 QueryCache 统计失败: {e}")
            return {"error": str(e)}

__all__ = [
    "CachedQuery",
    "QueryCache",
    "compute_schema_hash",
    "compute_question_hash",
]
