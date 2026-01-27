# -*- coding: utf-8 -*-
"""
QueryCache 组件 - 查询缓存管理

功能：
- 精确匹配缓存：基于问题 hash 的快速查找
- 语义相似缓存：基于向量相似度的模糊匹配
- Schema Hash 失效：数据模型变更时自动失效缓存
- TTL 过期：默认 24 小时

存储后端：LangGraph SqliteStore（复用现有基础设施）

Requirements: 2.1-2.5 - QueryCache 查询缓存
"""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════════════

class CachedQuery(BaseModel):
    """缓存的查询结果。
    
    Attributes:
        question: 原始问题
        question_hash: 问题的 MD5 hash
        question_embedding: 问题的向量表示（用于语义相似匹配）
        datasource_luid: 数据源 ID
        schema_hash: 数据模型版本 hash（用于失效检测）
        semantic_output: 语义解析输出（SemanticOutput 的字典形式）
        query: 生成的查询语句
        created_at: 创建时间
        expires_at: 过期时间
        hit_count: 命中次数统计
    """
    question: str
    question_hash: str
    question_embedding: Optional[List[float]] = None
    datasource_luid: str
    schema_hash: str
    semantic_output: Dict[str, Any]
    query: str
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: datetime
    hit_count: int = 0


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
    
    Args:
        data_model: 数据模型对象，需要有 fields 属性
    
    Returns:
        MD5 hash 字符串
    
    Examples:
        >>> hash1 = compute_schema_hash(data_model)
        >>> # 添加新字段后
        >>> hash2 = compute_schema_hash(data_model)
        >>> assert hash1 != hash2  # hash 变化，缓存失效
    """
    if not hasattr(data_model, 'fields') or not data_model.fields:
        return hashlib.md5(b"empty").hexdigest()
    
    field_signatures = []
    for field in data_model.fields:
        # 获取字段属性，兼容不同的字段模型
        name = getattr(field, 'name', '') or getattr(field, 'field_name', '')
        data_type = getattr(field, 'data_type', '') or getattr(field, 'dataType', '')
        role = getattr(field, 'role', '') or getattr(field, 'field_role', '')
        
        field_signatures.append(f"{name}:{data_type}:{role}")
    
    # 排序确保顺序一致
    field_signatures.sort()
    content = "|".join(field_signatures)
    
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def compute_question_hash(question: str, datasource_luid: str) -> str:
    """计算问题的 hash。
    
    Args:
        question: 用户问题
        datasource_luid: 数据源 ID
    
    Returns:
        MD5 hash 字符串
    """
    content = f"{datasource_luid}:{question.strip().lower()}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# QueryCache 组件
# ═══════════════════════════════════════════════════════════════════════════

class QueryCache:
    """查询缓存管理器。
    
    功能：
    - 精确匹配：基于问题 hash 的快速查找
    - 语义相似匹配：基于向量相似度的模糊匹配（可选）
    - Schema Hash 失效：数据模型变更时自动失效
    - TTL 过期：默认 24 小时
    
    存储结构：
    - namespace: ("semantic_parser", "query_cache", datasource_luid)
    - key: question_hash
    - value: CachedQuery.model_dump()
    
    Attributes:
        default_ttl: 默认 TTL（秒），默认 86400（24小时）
        similarity_threshold: 语义相似匹配阈值，默认 0.95
    
    Examples:
        >>> cache = QueryCache()
        >>> 
        >>> # 设置缓存
        >>> cache.set(
        ...     question="上个月各地区的销售额",
        ...     datasource_luid="ds_123",
        ...     schema_hash="abc123",
        ...     semantic_output={"what": {...}, "where": {...}},
        ...     query="SELECT ...",
        ... )
        >>> 
        >>> # 获取缓存
        >>> result = cache.get(
        ...     question="上个月各地区的销售额",
        ...     datasource_luid="ds_123",
        ...     current_schema_hash="abc123",
        ... )
    """
    
    # 缓存命名空间前缀
    NAMESPACE_PREFIX = ("semantic_parser", "query_cache")
    
    def __init__(
        self,
        store: Optional[Any] = None,
        embedding_model: Optional[Any] = None,
        default_ttl: int = 86400,  # 24 小时
        similarity_threshold: float = 0.95,
    ):
        """初始化 QueryCache。
        
        Args:
            store: LangGraph SqliteStore 实例，None 则使用全局实例
            embedding_model: Embedding 模型，用于语义相似匹配
            default_ttl: 默认 TTL（秒）
            similarity_threshold: 语义相似匹配阈值
        """
        self._store = store
        self._embedding = embedding_model
        self.default_ttl = default_ttl
        self.similarity_threshold = similarity_threshold
        
        # 延迟初始化 store
        self._store_initialized = False
    
    def _get_store(self):
        """获取存储实例（延迟初始化）"""
        if self._store is None and not self._store_initialized:
            try:
                from analytics_assistant.src.infra.storage import get_kv_store
                self._store = get_kv_store()
            except ImportError:
                logger.warning("无法导入 get_kv_store，缓存功能将不可用")
            self._store_initialized = True
        return self._store
    
    def _make_namespace(self, datasource_luid: str) -> tuple:
        """生成缓存命名空间。
        
        Args:
            datasource_luid: 数据源 ID
        
        Returns:
            命名空间元组
        """
        return (*self.NAMESPACE_PREFIX, datasource_luid)
    
    def get(
        self,
        question: str,
        datasource_luid: str,
        current_schema_hash: str,
    ) -> Optional[CachedQuery]:
        """精确匹配查询缓存。
        
        流程：
        1. 计算 question hash
        2. 从 store 中查找
        3. 检查 TTL 是否过期
        4. 检查 schema_hash 是否匹配当前数据模型
        
        Args:
            question: 用户问题
            datasource_luid: 数据源 ID
            current_schema_hash: 当前数据模型的 schema hash
        
        Returns:
            CachedQuery 或 None（缓存未命中或已失效）
        """
        store = self._get_store()
        if store is None:
            return None
        
        question_hash = compute_question_hash(question, datasource_luid)
        namespace = self._make_namespace(datasource_luid)
        
        try:
            item = store.get(namespace, question_hash)
            if item is None or item.value is None:
                logger.debug(f"QueryCache 未命中: question_hash={question_hash[:8]}...")
                return None
            
            cached = CachedQuery.model_validate(item.value)
            
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
            store.put(namespace, question_hash, cached.model_dump())
            
            logger.info(f"QueryCache 命中: question='{question[:20]}...', hit_count={cached.hit_count}")
            return cached
            
        except Exception as e:
            logger.error(f"QueryCache get 失败: {e}")
            return None
    
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
        
        Args:
            question: 用户问题
            datasource_luid: 数据源 ID
            current_schema_hash: 当前数据模型的 schema hash
            threshold: 相似度阈值，None 使用默认值
        
        Returns:
            CachedQuery 或 None
        """
        if self._embedding is None:
            logger.debug("QueryCache 语义相似匹配不可用：未配置 embedding 模型")
            return None
        
        store = self._get_store()
        if store is None:
            return None
        
        threshold = threshold or self.similarity_threshold
        namespace = self._make_namespace(datasource_luid)
        
        try:
            # 计算问题的 embedding
            question_embedding = self._embedding.embed_query(question)
            
            # 搜索该数据源的所有缓存
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
                store.put(namespace, question_hash, best_match.model_dump())
            
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
        """设置缓存。
        
        Args:
            question: 用户问题
            datasource_luid: 数据源 ID
            schema_hash: 当前数据模型的 schema hash
            semantic_output: 语义解析输出
            query: 生成的查询语句
            ttl: TTL（秒），None 使用默认值
        
        Returns:
            是否成功
        """
        store = self._get_store()
        if store is None:
            return False
        
        ttl = ttl or self.default_ttl
        question_hash = compute_question_hash(question, datasource_luid)
        namespace = self._make_namespace(datasource_luid)
        
        try:
            # 计算 embedding（如果可用）
            question_embedding = None
            if self._embedding:
                try:
                    question_embedding = self._embedding.embed_query(question)
                except Exception as e:
                    logger.warning(f"计算 question embedding 失败: {e}")
            
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
            
            # 存储到 SqliteStore
            # TTL 以分钟为单位
            ttl_minutes = ttl // 60
            store.put(namespace, question_hash, cached.model_dump(), ttl=ttl_minutes)
            
            logger.info(f"QueryCache 已缓存: question='{question[:20]}...', ttl={ttl}s")
            return True
            
        except Exception as e:
            logger.error(f"QueryCache set 失败: {e}")
            return False
    
    def invalidate_by_datasource(self, datasource_luid: str) -> int:
        """失效指定数据源的所有缓存。
        
        Args:
            datasource_luid: 数据源 ID
        
        Returns:
            失效的缓存数量
        """
        store = self._get_store()
        if store is None:
            return 0
        
        namespace = self._make_namespace(datasource_luid)
        
        try:
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
        """当数据模型变更时，主动失效旧版本的缓存。
        
        遍历该数据源的所有缓存，删除 schema_hash 不匹配的条目。
        
        注意：这是可选的主动清理，即使不调用，
        get() 方法也会在读取时检测并跳过失效缓存。
        
        Args:
            datasource_luid: 数据源 ID
            new_schema_hash: 新的 schema hash
        
        Returns:
            失效的缓存数量
        """
        store = self._get_store()
        if store is None:
            return 0
        
        namespace = self._make_namespace(datasource_luid)
        
        try:
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
        """计算余弦相似度。
        
        Args:
            vec1: 向量 1
            vec2: 向量 2
        
        Returns:
            相似度（0-1）
        """
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
