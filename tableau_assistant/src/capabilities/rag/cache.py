"""
RAG 缓存管理器

提供向量缓存和查询结果缓存功能。
使用 SQLite 作为持久化存储。
"""
import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CachedVector:
    """
    缓存的向量
    
    Attributes:
        text_hash: 文本哈希值
        vector: 向量
        model: 模型名称
        created_at: 创建时间戳
    """
    text_hash: str
    vector: List[float]
    model: str
    created_at: float


class VectorCache:
    """
    向量缓存
    
    使用 SQLite 缓存 embedding 向量，以文本哈希为 key。
    
    Attributes:
        db_path: SQLite 数据库路径
        ttl: 缓存过期时间（秒），默认 7 天
    """
    
    DEFAULT_TTL = 7 * 24 * 60 * 60  # 7 天
    
    def __init__(
        self,
        db_path: Optional[str] = None,
        ttl: int = DEFAULT_TTL
    ):
        """
        初始化向量缓存
        
        Args:
            db_path: SQLite 数据库路径（默认 data/vector_cache.db）
            ttl: 缓存过期时间（秒）
        """
        if db_path is None:
            db_path = "data/vector_cache.db"
        
        self.db_path = Path(db_path)
        self.ttl = ttl
        
        # 确保目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化数据库
        self._init_db()
    
    def _init_db(self) -> None:
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            # 使用 (text_hash, model) 作为复合主键
            # 这样同一文本在不同模型下可以有不同的缓存
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vector_cache (
                    text_hash TEXT NOT NULL,
                    model TEXT NOT NULL,
                    vector TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (text_hash, model)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vector_cache_model 
                ON vector_cache(model)
            """)
            conn.commit()
    
    @staticmethod
    def compute_hash(text: str) -> str:
        """
        计算文本哈希值
        
        Args:
            text: 文本
        
        Returns:
            MD5 哈希值
        """
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def get(
        self,
        text: str,
        model: str
    ) -> Optional[List[float]]:
        """
        获取缓存的向量
        
        Args:
            text: 原始文本
            model: 模型名称
        
        Returns:
            向量，如果不存在或已过期返回 None
        """
        text_hash = self.compute_hash(text)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT vector, created_at FROM vector_cache
                    WHERE text_hash = ? AND model = ?
                    """,
                    (text_hash, model)
                )
                row = cursor.fetchone()
                
                if row:
                    vector_json, created_at = row
                    
                    # 检查是否过期
                    if time.time() - created_at > self.ttl:
                        logger.debug(f"向量缓存已过期: {text_hash[:8]}...")
                        return None
                    
                    return json.loads(vector_json)
                
                return None
                
        except Exception as e:
            logger.error(f"获取向量缓存失败: {e}")
            return None
    
    def put(
        self,
        text: str,
        vector: List[float],
        model: str
    ) -> bool:
        """
        保存向量到缓存
        
        Args:
            text: 原始文本
            vector: 向量
            model: 模型名称
        
        Returns:
            是否保存成功
        """
        text_hash = self.compute_hash(text)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO vector_cache 
                    (text_hash, vector, model, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (text_hash, json.dumps(vector), model, time.time())
                )
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"保存向量缓存失败: {e}")
            return False
    
    def get_batch(
        self,
        texts: List[str],
        model: str
    ) -> Tuple[Dict[str, List[float]], List[str]]:
        """
        批量获取缓存的向量
        
        Args:
            texts: 文本列表
            model: 模型名称
        
        Returns:
            (缓存命中的向量字典, 未命中的文本列表)
        """
        cached = {}
        missed = []
        
        for text in texts:
            vector = self.get(text, model)
            if vector is not None:
                cached[text] = vector
            else:
                missed.append(text)
        
        logger.debug(f"向量缓存: 命中 {len(cached)}, 未命中 {len(missed)}")
        return cached, missed
    
    def put_batch(
        self,
        text_vectors: Dict[str, List[float]],
        model: str
    ) -> int:
        """
        批量保存向量到缓存
        
        Args:
            text_vectors: 文本到向量的映射
            model: 模型名称
        
        Returns:
            成功保存的数量
        """
        success_count = 0
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                for text, vector in text_vectors.items():
                    text_hash = self.compute_hash(text)
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO vector_cache 
                        (text_hash, vector, model, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (text_hash, json.dumps(vector), model, time.time())
                    )
                    success_count += 1
                conn.commit()
                
        except Exception as e:
            logger.error(f"批量保存向量缓存失败: {e}")
        
        return success_count
    
    def clear(self, model: Optional[str] = None) -> int:
        """
        清除缓存
        
        Args:
            model: 模型名称（可选，不指定则清除所有）
        
        Returns:
            清除的记录数
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                if model:
                    cursor = conn.execute(
                        "DELETE FROM vector_cache WHERE model = ?",
                        (model,)
                    )
                else:
                    cursor = conn.execute("DELETE FROM vector_cache")
                
                conn.commit()
                return cursor.rowcount
                
        except Exception as e:
            logger.error(f"清除向量缓存失败: {e}")
            return 0
    
    def cleanup_expired(self) -> int:
        """
        清理过期的缓存
        
        Returns:
            清理的记录数
        """
        try:
            cutoff_time = time.time() - self.ttl
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "DELETE FROM vector_cache WHERE created_at < ?",
                    (cutoff_time,)
                )
                conn.commit()
                
                count = cursor.rowcount
                if count > 0:
                    logger.info(f"清理了 {count} 条过期向量缓存")
                return count
                
        except Exception as e:
            logger.error(f"清理过期缓存失败: {e}")
            return 0
    
    def stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            统计信息字典
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                # 总数
                total = conn.execute(
                    "SELECT COUNT(*) FROM vector_cache"
                ).fetchone()[0]
                
                # 按模型统计
                by_model = {}
                cursor = conn.execute(
                    "SELECT model, COUNT(*) FROM vector_cache GROUP BY model"
                )
                for row in cursor:
                    by_model[row[0]] = row[1]
                
                # 过期数量
                cutoff_time = time.time() - self.ttl
                expired = conn.execute(
                    "SELECT COUNT(*) FROM vector_cache WHERE created_at < ?",
                    (cutoff_time,)
                ).fetchone()[0]
                
                return {
                    "total": total,
                    "by_model": by_model,
                    "expired": expired,
                    "ttl_days": self.ttl / (24 * 60 * 60)
                }
                
        except Exception as e:
            logger.error(f"获取缓存统计失败: {e}")
            return {}


class CachedEmbeddingProvider:
    """
    带缓存的 Embedding 提供者包装器
    
    包装任意 EmbeddingProvider，添加缓存功能。
    """
    
    def __init__(
        self,
        provider: Any,  # EmbeddingProvider
        cache: Optional[VectorCache] = None
    ):
        """
        初始化带缓存的提供者
        
        Args:
            provider: 原始 EmbeddingProvider
            cache: 向量缓存（可选，默认创建新的）
        """
        self.provider = provider
        self.cache = cache or VectorCache()
        
        # 统计信息
        self._cache_hits = 0
        self._cache_misses = 0
    
    @property
    def model_name(self) -> str:
        return self.provider.model_name
    
    @property
    def dimensions(self) -> int:
        return self.provider.dimensions
    
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
        cached, missed = self.cache.get_batch(texts, self.model_name)
        
        self._cache_hits += len(cached)
        self._cache_misses += len(missed)
        
        # 对未命中的文本调用原始提供者
        if missed:
            new_vectors = self.provider.embed_documents(missed)
            
            # 保存到缓存
            text_vectors = dict(zip(missed, new_vectors))
            self.cache.put_batch(text_vectors, self.model_name)
            
            # 合并结果
            cached.update(text_vectors)
        
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
        vector = self.cache.get(text, self.model_name)
        
        if vector is not None:
            self._cache_hits += 1
            return vector
        
        self._cache_misses += 1
        
        # 调用原始提供者
        vector = self.provider.embed_query(text)
        
        # 保存到缓存
        self.cache.put(text, vector, self.model_name)
        
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


__all__ = [
    "CachedVector",
    "VectorCache",
    "CachedEmbeddingProvider",
]
