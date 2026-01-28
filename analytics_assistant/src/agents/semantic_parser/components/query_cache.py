# -*- coding: utf-8 -*-
"""
QueryCache 组件 - 查询缓存管理

功能：
- 精确匹配缓存：基于问题 hash 的快速查找
- 语义相似缓存：基于向量相似度的模糊匹配
- Schema Hash 失效：数据模型变更时自动失效缓存
- TTL 过期：默认 24 小时

存储后端：复用 CacheManager（基于 LangGraph SqliteStore）

配置来源：analytics_assistant/config/app.yaml -> semantic_parser.query_cache

Requirements: 2.1-2.5 - QueryCache 查询缓存
"""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.storage import CacheManager, get_kv_store
from analytics_assistant.src.infra.ai import get_embeddings

from ..schemas.cache import CachedQuery

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════════════════

def _get_config() -> Dict[str, Any]:
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
    """计算数据模型的 schema hash。
    
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
    """计算问题的 hash。"""
    content = f"{datasource_luid}:{question.strip().lower()}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# QueryCache 组件（基于 CacheManager 构建）
# ═══════════════════════════════════════════════════════════════════════════

class QueryCache:
    """查询缓存管理器。
    
    基于 infra 层的 CacheManager 构建，增加：
    - Schema Hash 验证：数据模型变更时自动失效
    - 语义相似匹配：基于向量相似度的模糊匹配
    
    存储结构：
    - 使用 CacheManager，namespace 为 "query_cache_{datasource_luid}"
    - key: question_hash
    - value: CachedQuery.model_dump()
    
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
        """初始化 QueryCache。
        
        Args:
            store: 直接传入的 store 实例（用于测试），None 则使用 CacheManager
            embedding_model: Embedding 模型，用于语义相似匹配
            default_ttl: 默认 TTL（秒），None 从配置读取
            similarity_threshold: 语义相似匹配阈值，None 从配置读取
        """
        self._direct_store = store  # 直接传入的 store（用于测试兼容）
        self._cache_managers: Dict[str, Any] = {}  # datasource_luid -> CacheManager
        self._embedding = embedding_model
        
        # 从配置加载参数
        self._load_config(default_ttl, similarity_threshold)
        
        # 直接初始化 embedding（如果未传入）
        if self._embedding is None:
            try:
                self._embedding = get_embeddings()
            except Exception as e:
                logger.warning(f"无法初始化 embedding 模型: {e}")
    
    def _load_config(
        self,
        default_ttl: Optional[int],
        similarity_threshold: Optional[float],
    ) -> None:
        """从配置加载参数。"""
        config = _get_config()
        
        self.default_ttl = (
            default_ttl
            if default_ttl is not None
            else config.get("default_ttl", self._DEFAULT_TTL)
        )
        self.similarity_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else config.get("similarity_threshold", self._DEFAULT_SIMILARITY_THRESHOLD)
        )
    
    def _get_cache_manager(self, datasource_luid: str) -> Optional[Any]:
        """获取指定数据源的 CacheManager（直接初始化）。
        
        Args:
            datasource_luid: 数据源 ID
            
        Returns:
            CacheManager 实例，如果使用直接传入的 store 则返回 None
        """
        # 如果直接传入了 store（测试场景），使用它
        if self._direct_store is not None:
            return None  # 返回 None 表示使用 _direct_store
        
        if datasource_luid not in self._cache_managers:
            namespace = f"{self.NAMESPACE_PREFIX}_{datasource_luid}"
            self._cache_managers[datasource_luid] = CacheManager(
                namespace=namespace,
                default_ttl=self.default_ttl,
            )
        return self._cache_managers[datasource_luid]
    
    def _get_store(self):
        """获取底层 store（兼容测试场景）。"""
        if self._direct_store is not None:
            return self._direct_store
        return get_kv_store()
    
    def _make_namespace(self, datasource_luid: str) -> tuple:
        """生成存储命名空间（兼容直接 store 场景）。"""
        return ("semantic_parser", "query_cache", datasource_luid)
    
    def get(
        self,
        question: str,
        datasource_luid: str,
        current_schema_hash: str,
    ) -> Optional[CachedQuery]:
        """精确匹配查询缓存。
        
        流程：
        1. 计算 question hash
        2. 从缓存中查找
        3. 检查 TTL 是否过期
        4. 检查 schema_hash 是否匹配当前数据模型
        """
        question_hash = compute_question_hash(question, datasource_luid)
        
        try:
            # 获取缓存值
            cache_manager = self._get_cache_manager(datasource_luid)
            if cache_manager is not None:
                # 使用 CacheManager
                value = cache_manager.get(question_hash)
            else:
                # 使用直接传入的 store（测试场景）
                namespace = self._make_namespace(datasource_luid)
                item = self._direct_store.get(namespace, question_hash)
                value = item.value if item else None
            
            if value is None:
                logger.debug(f"QueryCache 未命中: question_hash={question_hash[:8]}...")
                return None
            
            cached = CachedQuery.model_validate(value)
            
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
        """存储缓存值。"""
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
        """语义相似匹配。
        
        流程：
        1. 计算 question embedding
        2. 在该数据源的缓存中进行向量相似度搜索
        3. 返回相似度 > threshold 的最佳匹配
        4. 同样检查 schema_hash 是否匹配
        """
        if self._embedding is None:
            logger.debug("QueryCache 语义相似匹配不可用：未配置 embedding 模型")
            return None
        
        threshold = threshold or self.similarity_threshold
        
        try:
            # 计算问题的 embedding
            question_embedding = self._embedding.embed_query(question)
            
            # 获取该数据源的所有缓存
            store = self._get_store()
            namespace = self._make_namespace(datasource_luid)
            items = store.search(namespace, limit=100)
            
            best_match = None
            best_similarity = 0.0
            
            for item in items:
                if item.value is None:
                    continue
                
                cached = CachedQuery.model_validate(item.value)
                
                # 跳过过期和 schema 不匹配的缓存
                if datetime.now() > cached.expires_at:
                    continue
                if cached.schema_hash != current_schema_hash:
                    continue
                
                # 计算相似度
                if cached.question_embedding:
                    similarity = self._cosine_similarity(
                        question_embedding, 
                        cached.question_embedding
                    )
                    if similarity > threshold and similarity > best_similarity:
                        best_similarity = similarity
                        best_match = cached
            
            if best_match:
                logger.info(
                    f"QueryCache 语义相似命中: similarity={best_similarity:.3f}, "
                    f"cached_question='{best_match.question[:20]}...'"
                )
                # 更新命中计数
                best_match.hit_count += 1
                question_hash = compute_question_hash(best_match.question, datasource_luid)
                self._put_cached(datasource_luid, question_hash, best_match)
            
            return best_match
            
        except Exception as e:
            logger.error(f"QueryCache get_similar 失败: {e}")
            return None
    
    def set(
        self,
        question: str,
        datasource_luid: str,
        schema_hash: str,
        semantic_output: Dict[str, Any],
        query: str,
        ttl: Optional[int] = None,
    ) -> bool:
        """设置缓存。"""
        ttl = ttl or self.default_ttl
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
                    # 记录未知错误但不中断缓存写入
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
            
            logger.info(f"QueryCache 已缓存: question='{question[:20]}...', ttl={ttl}s")
            return True
            
        except Exception as e:
            logger.error(f"QueryCache set 失败: {e}")
            return False
    
    def invalidate_by_datasource(self, datasource_luid: str) -> int:
        """失效指定数据源的所有缓存。"""
        try:
            cache_manager = self._get_cache_manager(datasource_luid)
            if cache_manager is not None:
                cache_manager.clear()
                # CacheManager.clear() 不返回数量，返回 -1 表示已清空
                logger.info(f"QueryCache 已失效缓存: datasource={datasource_luid}")
                return -1
            else:
                store = self._direct_store
                namespace = self._make_namespace(datasource_luid)
                items = store.search(namespace, limit=10000)
                count = 0
                for item in items:
                    store.delete(namespace, item.key)
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
        """当数据模型变更时，主动失效旧版本的缓存。"""
        try:
            store = self._get_store()
            namespace = self._make_namespace(datasource_luid)
            items = store.search(namespace, limit=10000)
            count = 0
            for item in items:
                if item.value is None:
                    continue
                cached = CachedQuery.model_validate(item.value)
                if cached.schema_hash != new_schema_hash:
                    store.delete(namespace, item.key)
                    count += 1
            
            logger.info(
                f"QueryCache schema 变更失效 {count} 条缓存: "
                f"datasource={datasource_luid}, new_hash={new_schema_hash[:8]}..."
            )
            return count
            
        except Exception as e:
            logger.error(f"QueryCache invalidate_by_schema_change 失败: {e}")
            return 0
    
    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度。"""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)


__all__ = [
    "CachedQuery",
    "QueryCache",
    "compute_schema_hash",
    "compute_question_hash",
]
