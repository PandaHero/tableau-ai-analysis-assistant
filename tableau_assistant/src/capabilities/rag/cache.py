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


class MappingCache:
    """
    字段映射结果缓存
    
    缓存 SemanticMapper 的映射结果，减少重复计算。
    使用 SQLite 作为持久化存储。
    
    Attributes:
        db_path: SQLite 数据库路径
        ttl: 缓存过期时间（秒），默认 1 小时
    """
    
    DEFAULT_TTL = 60 * 60  # 1 小时
    
    def __init__(
        self,
        db_path: Optional[str] = None,
        ttl: int = DEFAULT_TTL
    ):
        """
        初始化映射缓存
        
        Args:
            db_path: SQLite 数据库路径（默认 data/mapping_cache.db）
            ttl: 缓存过期时间（秒）
        """
        if db_path is None:
            db_path = "data/mapping_cache.db"
        
        self.db_path = Path(db_path)
        self.ttl = ttl
        
        # 确保目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化数据库
        self._init_db()
    
    def _init_db(self) -> None:
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mapping_cache (
                    cache_key TEXT PRIMARY KEY,
                    term TEXT NOT NULL,
                    datasource_luid TEXT,
                    result_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_mapping_cache_datasource 
                ON mapping_cache(datasource_luid)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_mapping_cache_term 
                ON mapping_cache(term)
            """)
            conn.commit()
    
    @staticmethod
    def _make_key(term: str, datasource_luid: Optional[str] = None) -> str:
        """
        生成缓存键
        
        Args:
            term: 查询术语
            datasource_luid: 数据源 LUID
        
        Returns:
            缓存键
        """
        key_parts = [term.lower().strip()]
        if datasource_luid:
            key_parts.append(datasource_luid)
        key_str = "|".join(key_parts)
        return hashlib.md5(key_str.encode('utf-8')).hexdigest()
    
    def get(
        self,
        term: str,
        datasource_luid: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        获取缓存的映射结果
        
        Args:
            term: 查询术语
            datasource_luid: 数据源 LUID
        
        Returns:
            映射结果字典，如果不存在或已过期返回 None
        """
        cache_key = self._make_key(term, datasource_luid)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT result_json, created_at FROM mapping_cache
                    WHERE cache_key = ?
                    """,
                    (cache_key,)
                )
                row = cursor.fetchone()
                
                if row:
                    result_json, created_at = row
                    
                    # 检查是否过期
                    if time.time() - created_at > self.ttl:
                        logger.debug(f"映射缓存已过期: {term}")
                        return None
                    
                    return json.loads(result_json)
                
                return None
                
        except Exception as e:
            logger.error(f"获取映射缓存失败: {e}")
            return None
    
    def put(
        self,
        term: str,
        result: Dict[str, Any],
        datasource_luid: Optional[str] = None
    ) -> bool:
        """
        保存映射结果到缓存
        
        Args:
            term: 查询术语
            result: 映射结果字典
            datasource_luid: 数据源 LUID
        
        Returns:
            是否保存成功
        """
        cache_key = self._make_key(term, datasource_luid)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO mapping_cache 
                    (cache_key, term, datasource_luid, result_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (cache_key, term, datasource_luid, json.dumps(result), time.time())
                )
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"保存映射缓存失败: {e}")
            return False
    
    def clear(self, datasource_luid: Optional[str] = None) -> int:
        """
        清除缓存
        
        Args:
            datasource_luid: 数据源 LUID（可选，不指定则清除所有）
        
        Returns:
            清除的记录数
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                if datasource_luid:
                    cursor = conn.execute(
                        "DELETE FROM mapping_cache WHERE datasource_luid = ?",
                        (datasource_luid,)
                    )
                else:
                    cursor = conn.execute("DELETE FROM mapping_cache")
                
                conn.commit()
                return cursor.rowcount
                
        except Exception as e:
            logger.error(f"清除映射缓存失败: {e}")
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
                    "DELETE FROM mapping_cache WHERE created_at < ?",
                    (cutoff_time,)
                )
                conn.commit()
                
                count = cursor.rowcount
                if count > 0:
                    logger.info(f"清理了 {count} 条过期映射缓存")
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
                    "SELECT COUNT(*) FROM mapping_cache"
                ).fetchone()[0]
                
                # 按数据源统计
                by_datasource = {}
                cursor = conn.execute(
                    "SELECT datasource_luid, COUNT(*) FROM mapping_cache GROUP BY datasource_luid"
                )
                for row in cursor:
                    ds = row[0] or "unknown"
                    by_datasource[ds] = row[1]
                
                # 过期数量
                cutoff_time = time.time() - self.ttl
                expired = conn.execute(
                    "SELECT COUNT(*) FROM mapping_cache WHERE created_at < ?",
                    (cutoff_time,)
                ).fetchone()[0]
                
                return {
                    "total": total,
                    "by_datasource": by_datasource,
                    "expired": expired,
                    "ttl_hours": self.ttl / 3600
                }
                
        except Exception as e:
            logger.error(f"获取缓存统计失败: {e}")
            return {}


class CacheManager:
    """
    统一缓存管理器
    
    整合向量缓存和映射结果缓存，提供统一的缓存管理接口。
    
    **Validates: Requirements 7.1, 7.2**
    
    Attributes:
        vector_cache: 向量缓存
        mapping_cache: 映射结果缓存
    """
    
    def __init__(
        self,
        db_dir: str = "data",
        vector_ttl: int = VectorCache.DEFAULT_TTL,
        mapping_ttl: int = MappingCache.DEFAULT_TTL
    ):
        """
        初始化缓存管理器
        
        Args:
            db_dir: 数据库目录
            vector_ttl: 向量缓存 TTL（秒）
            mapping_ttl: 映射缓存 TTL（秒），默认 1 小时
        """
        self.db_dir = Path(db_dir)
        self.db_dir.mkdir(parents=True, exist_ok=True)
        
        self.vector_cache = VectorCache(
            db_path=str(self.db_dir / "vector_cache.db"),
            ttl=vector_ttl
        )
        self.mapping_cache = MappingCache(
            db_path=str(self.db_dir / "mapping_cache.db"),
            ttl=mapping_ttl
        )
        
        # 统计信息
        self._vector_hits = 0
        self._vector_misses = 0
        self._mapping_hits = 0
        self._mapping_misses = 0
    
    # ========== 向量缓存接口 ==========
    
    def get_embedding(self, text: str, model: str) -> Optional[List[float]]:
        """
        获取缓存的向量
        
        Args:
            text: 原始文本
            model: 模型名称
        
        Returns:
            向量，如果不存在或已过期返回 None
        """
        result = self.vector_cache.get(text, model)
        if result is not None:
            self._vector_hits += 1
        else:
            self._vector_misses += 1
        return result
    
    def set_embedding(self, text: str, vector: List[float], model: str) -> bool:
        """
        保存向量到缓存
        
        Args:
            text: 原始文本
            vector: 向量
            model: 模型名称
        
        Returns:
            是否保存成功
        """
        return self.vector_cache.put(text, vector, model)
    
    def get_embeddings_batch(
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
        cached, missed = self.vector_cache.get_batch(texts, model)
        self._vector_hits += len(cached)
        self._vector_misses += len(missed)
        return cached, missed
    
    def set_embeddings_batch(
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
        return self.vector_cache.put_batch(text_vectors, model)
    
    # ========== 映射缓存接口 ==========
    
    def get_mapping(
        self,
        term: str,
        datasource_luid: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        获取缓存的映射结果
        
        Args:
            term: 查询术语
            datasource_luid: 数据源 LUID
        
        Returns:
            映射结果字典，如果不存在或已过期返回 None
        """
        result = self.mapping_cache.get(term, datasource_luid)
        if result is not None:
            self._mapping_hits += 1
        else:
            self._mapping_misses += 1
        return result
    
    def set_mapping(
        self,
        term: str,
        result: Dict[str, Any],
        datasource_luid: Optional[str] = None
    ) -> bool:
        """
        保存映射结果到缓存
        
        Args:
            term: 查询术语
            result: 映射结果字典
            datasource_luid: 数据源 LUID
        
        Returns:
            是否保存成功
        """
        return self.mapping_cache.put(term, result, datasource_luid)
    
    # ========== 通用接口 ==========
    
    def get(self, key: str) -> Optional[Any]:
        """
        通用获取接口（兼容旧 API）
        
        Args:
            key: 缓存键（格式：mapping:{term} 或 vector:{text}:{model}）
        
        Returns:
            缓存值
        """
        if key.startswith("mapping:"):
            term = key[8:]  # 去掉 "mapping:" 前缀
            return self.mapping_cache.get(term)
        return None
    
    def put(self, key: str, value: Any) -> bool:
        """
        通用保存接口（兼容旧 API）
        
        Args:
            key: 缓存键
            value: 缓存值
        
        Returns:
            是否保存成功
        """
        if key.startswith("mapping:"):
            term = key[8:]
            # 将 FieldMappingResult 转换为字典
            if hasattr(value, 'to_dict'):
                value = value.to_dict()
            elif hasattr(value, '__dict__'):
                value = value.__dict__
            return self.mapping_cache.put(term, value)
        return False
    
    def clear_all(self) -> Dict[str, int]:
        """
        清除所有缓存
        
        Returns:
            各类缓存清除的记录数
        """
        return {
            "vector": self.vector_cache.clear(),
            "mapping": self.mapping_cache.clear()
        }
    
    def clear_datasource(self, datasource_luid: str) -> Dict[str, int]:
        """
        清除指定数据源的缓存
        
        Args:
            datasource_luid: 数据源 LUID
        
        Returns:
            各类缓存清除的记录数
        """
        return {
            "mapping": self.mapping_cache.clear(datasource_luid)
        }
    
    def cleanup_expired(self) -> Dict[str, int]:
        """
        清理所有过期缓存
        
        Returns:
            各类缓存清理的记录数
        """
        return {
            "vector": self.vector_cache.cleanup_expired(),
            "mapping": self.mapping_cache.cleanup_expired()
        }
    
    def stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            统计信息字典
        """
        vector_total = self._vector_hits + self._vector_misses
        mapping_total = self._mapping_hits + self._mapping_misses
        
        return {
            "vector": {
                **self.vector_cache.stats(),
                "hits": self._vector_hits,
                "misses": self._vector_misses,
                "hit_rate": self._vector_hits / max(1, vector_total)
            },
            "mapping": {
                **self.mapping_cache.stats(),
                "hits": self._mapping_hits,
                "misses": self._mapping_misses,
                "hit_rate": self._mapping_hits / max(1, mapping_total)
            }
        }
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        self._vector_hits = 0
        self._vector_misses = 0
        self._mapping_hits = 0
        self._mapping_misses = 0


__all__ = [
    "CachedVector",
    "VectorCache",
    "CachedEmbeddingProvider",
    "MappingCache",
    "CacheManager",
]
