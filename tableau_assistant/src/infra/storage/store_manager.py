"""
统一存储管理器

提供业务数据的持久化存储，基于 SQLite 实现。

生产级特性：
- 线程安全：使用线程锁保护并发访问
- 连接池：每个线程独立连接
- 事务支持：自动提交或回滚
- TTL 过期机制：自动清理过期数据
- 性能优化：WAL模式、索引、批量操作
- 错误处理：完善的异常处理和日志记录

支持的命名空间：
- metadata: 元数据缓存（默认1小时）
- dimension_hierarchy: 维度层级缓存（默认24小时）
- data_model: 数据模型缓存（默认24小时）
- user_preferences: 用户偏好（永久）
- question_history: 问题历史（永久）
- anomaly_knowledge: 异常知识库（永久）
"""
import sqlite3
import json
import time
import logging
import threading
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Union
from contextlib import contextmanager
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class StoreItem:
    """存储项，兼容 LangGraph Store 的 Item 接口"""
    namespace: Tuple[str, ...]
    key: str
    value: Dict[str, Any]
    created_at: float
    updated_at: float = 0.0
    expires_at: Optional[float] = None


class StoreManager:
    """
    统一存储管理器
    
    将 PersistentStore 的 SQLite 实现与高级业务接口合并，
    提供单一的存储管理入口。
    
    使用示例：
        # 创建管理器
        store = StoreManager()
        
        # 业务操作
        store.put_metadata("ds_123", metadata_obj)
        metadata = store.get_metadata("ds_123")
        
        # 低级操作
        store.put(("custom",), "key1", {"data": "value"}, ttl=3600)
        item = store.get(("custom",), "key1")
    """
    
    # 缓存过期时间（秒）- 默认值，可通过 .env 配置
    # 注意：这些是类变量默认值，实际值在 __init__ 中从 settings 读取
    METADATA_TTL = 86400  # 24小时
    DIMENSION_HIERARCHY_TTL = 86400  # 24小时
    DATA_MODEL_TTL = 86400  # 24小时
    
    # 默认搜索限制
    DEFAULT_SEARCH_LIMIT = 1000
    
    def __init__(
        self,
        db_path: str = "data/business_cache.db",
        enable_wal: bool = True,
        cache_size: int = -64000,  # 64MB
        timeout: float = 30.0,
        max_search_limit: Optional[int] = None
    ):
        """
        初始化存储管理器
        
        Args:
            db_path: SQLite 数据库文件路径
            enable_wal: 是否启用WAL模式（提高并发性能）
            cache_size: SQLite 缓存大小（负数表示KB）
            timeout: 数据库锁超时时间（秒）
            max_search_limit: 最大搜索限制
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.enable_wal = enable_wal
        self.cache_size = cache_size
        self.timeout = timeout
        
        # 从 settings 读取配置
        try:
            from tableau_assistant.src.infra.config.settings import settings
            self.max_search_limit = max_search_limit or settings.store_max_search_limit
            # 更新 TTL 配置
            self.METADATA_TTL = settings.metadata_cache_ttl
            self.DIMENSION_HIERARCHY_TTL = settings.dimension_hierarchy_cache_ttl
            self.DATA_MODEL_TTL = settings.data_model_cache_ttl
        except Exception:
            self.max_search_limit = max_search_limit or self.DEFAULT_SEARCH_LIMIT
        
        # 线程锁
        self._lock = threading.RLock()
        
        # 线程本地存储（每个线程独立连接）
        self._local = threading.local()
        
        # 初始化数据库
        self._init_db()
        
        logger.info(f"StoreManager initialized: {self.db_path}")

    # ========== 数据库连接管理 ==========
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                timeout=self.timeout,
                check_same_thread=False,
                isolation_level=None  # 自动提交模式
            )
            
            cursor = self._local.conn.cursor()
            
            # WAL模式（提高并发性能）
            if self.enable_wal:
                cursor.execute("PRAGMA journal_mode=WAL")
            
            # 性能优化
            cursor.execute(f"PRAGMA cache_size={self.cache_size}")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA temp_store=MEMORY")
            
            logger.debug(f"Created DB connection for thread {threading.current_thread().name}")
        
        return self._local.conn
    
    @contextmanager
    def _transaction(self):
        """事务上下文管理器"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("BEGIN")
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Transaction failed: {e}")
            raise
        finally:
            cursor.close()
    
    def _init_db(self):
        """初始化数据库表和索引"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            try:
                # 主存储表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS store (
                        namespace TEXT NOT NULL,
                        key TEXT NOT NULL,
                        value TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        expires_at REAL,
                        PRIMARY KEY (namespace, key)
                    )
                """)
                
                # 索引
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_namespace ON store(namespace)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_expires_at ON store(expires_at)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_updated_at ON store(updated_at)")
                
                # 版本表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS schema_version (
                        version INTEGER PRIMARY KEY,
                        applied_at REAL NOT NULL
                    )
                """)
                cursor.execute("INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (1, ?)", (time.time(),))
                
                conn.commit()
                logger.info("Database initialized successfully")
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to initialize database: {e}")
                raise
    
    # ========== 低级存储操作 ==========
    
    def put(
        self,
        namespace: Tuple[str, ...],
        key: str,
        value: Dict[str, Any],
        ttl: Optional[float] = None
    ) -> None:
        """
        保存数据
        
        Args:
            namespace: 命名空间元组，如 ("metadata",) 或 ("question_history", "user_123")
            key: 键
            value: 值（字典）
            ttl: 生存时间（秒），None 表示永不过期
        """
        with self._lock:
            try:
                namespace_str = ":".join(namespace)
                value_json = json.dumps(value, ensure_ascii=False)
                now = time.time()
                expires_at = now + ttl if ttl else None
                
                with self._transaction() as cursor:
                    cursor.execute("""
                        INSERT OR REPLACE INTO store (namespace, key, value, created_at, updated_at, expires_at)
                        VALUES (?, ?, ?, 
                            COALESCE((SELECT created_at FROM store WHERE namespace = ? AND key = ?), ?),
                            ?, ?)
                    """, (namespace_str, key, value_json, namespace_str, key, now, now, expires_at))
                
                logger.debug(f"Put: {namespace_str}:{key} (ttl={ttl})")
                
            except Exception as e:
                logger.error(f"Failed to put data: {e}")
                raise
    
    def get(
        self,
        namespace: Tuple[str, ...],
        key: str
    ) -> Optional[StoreItem]:
        """
        获取数据
        
        Args:
            namespace: 命名空间元组
            key: 键
        
        Returns:
            StoreItem 或 None（如果不存在或已过期）
        """
        with self._lock:
            try:
                namespace_str = ":".join(namespace)
                now = time.time()
                
                conn = self._get_connection()
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT value, created_at, updated_at, expires_at FROM store 
                    WHERE namespace = ? AND key = ?
                """, (namespace_str, key))
                
                row = cursor.fetchone()
                if row:
                    expires_at = row[3]
                    if expires_at and expires_at < now:
                        logger.debug(f"Data expired: {namespace_str}:{key}")
                        self.delete(namespace, key)
                        return None
                    
                    return StoreItem(
                        namespace=namespace,
                        key=key,
                        value=json.loads(row[0]),
                        created_at=row[1],
                        updated_at=row[2],
                        expires_at=expires_at
                    )
                
                return None
                
            except Exception as e:
                logger.error(f"Failed to get data: {e}")
                raise
    
    def delete(self, namespace: Tuple[str, ...], key: str) -> None:
        """删除数据"""
        with self._lock:
            try:
                namespace_str = ":".join(namespace)
                
                with self._transaction() as cursor:
                    cursor.execute("DELETE FROM store WHERE namespace = ? AND key = ?", (namespace_str, key))
                
                logger.debug(f"Delete: {namespace_str}:{key}")
                
            except Exception as e:
                logger.error(f"Failed to delete data: {e}")
                raise
    
    def search(
        self,
        namespace_prefix: Tuple[str, ...],
        query: Optional[str] = None,
        limit: int = 100
    ) -> List[StoreItem]:
        """
        搜索数据
        
        Args:
            namespace_prefix: 命名空间前缀
            query: 查询字符串（简单文本匹配）
            limit: 返回结果数量限制
        
        Returns:
            StoreItem 列表
        """
        with self._lock:
            try:
                namespace_str = ":".join(namespace_prefix)
                now = time.time()
                
                conn = self._get_connection()
                cursor = conn.cursor()
                
                if query:
                    cursor.execute("""
                        SELECT namespace, key, value, created_at, updated_at, expires_at FROM store 
                        WHERE namespace LIKE ? AND value LIKE ?
                        AND (expires_at IS NULL OR expires_at > ?)
                        ORDER BY updated_at DESC
                        LIMIT ?
                    """, (f"{namespace_str}%", f"%{query}%", now, limit))
                else:
                    cursor.execute("""
                        SELECT namespace, key, value, created_at, updated_at, expires_at FROM store 
                        WHERE namespace LIKE ?
                        AND (expires_at IS NULL OR expires_at > ?)
                        ORDER BY updated_at DESC
                        LIMIT ?
                    """, (f"{namespace_str}%", now, limit))
                
                items = []
                for row in cursor.fetchall():
                    items.append(StoreItem(
                        namespace=tuple(row[0].split(":")),
                        key=row[1],
                        value=json.loads(row[2]),
                        created_at=row[3],
                        updated_at=row[4],
                        expires_at=row[5]
                    ))
                
                logger.debug(f"Search: {namespace_str} - found {len(items)} items")
                return items
                
            except Exception as e:
                logger.error(f"Failed to search: {e}")
                raise
    
    def clear_namespace(self, namespace: Tuple[str, ...]) -> int:
        """
        清空指定命名空间的所有数据
        
        Returns:
            删除的记录数
        """
        with self._lock:
            try:
                namespace_str = ":".join(namespace)
                
                with self._transaction() as cursor:
                    cursor.execute("DELETE FROM store WHERE namespace LIKE ?", (f"{namespace_str}%",))
                    deleted = cursor.rowcount
                
                logger.info(f"Cleared namespace {namespace_str}: {deleted} records")
                return deleted
                
            except Exception as e:
                logger.error(f"Failed to clear namespace: {e}")
                raise

    # ========== 元数据缓存 ==========
    
    def get_metadata(self, datasource_luid: str, datasource_updated_at: str = None):
        """
        获取元数据缓存
        
        Args:
            datasource_luid: 数据源LUID
            datasource_updated_at: 数据源最后更新时间（用于版本检测）
        
        Returns:
            Metadata对象，如果不存在或已过期返回None
        """
        try:
            from tableau_assistant.src.core.models import Metadata
            
            item = self.get(namespace=("metadata",), key=datasource_luid)
            
            if item and self._check_ttl(item.value, self.METADATA_TTL):
                metadata_dict = item.value
                
                # 版本检测
                if datasource_updated_at:
                    cached_version = metadata_dict.get("_datasource_updated_at")
                    if cached_version and cached_version != datasource_updated_at:
                        logger.info(f"数据源已更新，缓存失效: {datasource_luid}")
                        return None
                
                # 移除内部字段，反序列化
                clean_dict = {k: v for k, v in metadata_dict.items() if not k.startswith("_")}
                return Metadata.model_validate(clean_dict)
            
            return None
        except Exception as e:
            logger.error(f"获取元数据失败: {e}")
            return None
    
    def put_metadata(
        self,
        datasource_luid: str,
        metadata,
        datasource_updated_at: str = None
    ) -> bool:
        """保存元数据到缓存"""
        try:
            from tableau_assistant.src.core.models import Metadata
            
            if isinstance(metadata, Metadata):
                metadata_dict = metadata.model_dump()
            else:
                metadata_dict = metadata
            
            data = {
                **metadata_dict,
                "_cached_at": time.time(),
            }
            if datasource_updated_at:
                data["_datasource_updated_at"] = datasource_updated_at
            
            self.put(namespace=("metadata",), key=datasource_luid, value=data, ttl=self.METADATA_TTL)
            logger.info(f"元数据已缓存: {datasource_luid}")
            return True
        except Exception as e:
            logger.error(f"保存元数据失败: {e}")
            return False
    
    def clear_metadata_cache(self, datasource_luid: str) -> bool:
        """清除指定数据源的元数据缓存"""
        try:
            self.delete(namespace=("metadata",), key=datasource_luid)
            self.delete(namespace=("dimension_hierarchy",), key=datasource_luid)
            logger.info(f"已清除数据源缓存: {datasource_luid}")
            return True
        except Exception as e:
            logger.error(f"清除缓存失败: {e}")
            return False
    
    # ========== 维度层级缓存 ==========
    
    def get_dimension_hierarchy(self, datasource_luid: str) -> Optional[Dict[str, Any]]:
        """获取维度层级缓存"""
        try:
            item = self.get(namespace=("dimension_hierarchy",), key=datasource_luid)
            
            if item and self._check_ttl(item.value, self.DIMENSION_HIERARCHY_TTL):
                return item.value
            
            return None
        except Exception as e:
            logger.error(f"获取维度层级失败: {e}")
            return None
    
    def put_dimension_hierarchy(self, datasource_luid: str, hierarchy: Dict[str, Any]) -> bool:
        """保存维度层级到缓存"""
        try:
            data = {**hierarchy, "_cached_at": time.time()}
            self.put(namespace=("dimension_hierarchy",), key=datasource_luid, value=data, ttl=self.DIMENSION_HIERARCHY_TTL)
            logger.info(f"维度层级已缓存: {datasource_luid}")
            return True
        except Exception as e:
            logger.error(f"保存维度层级失败: {e}")
            return False
    
    def clear_dimension_hierarchy_cache(self, datasource_luid: str) -> bool:
        """清除维度层级缓存"""
        try:
            self.delete(namespace=("dimension_hierarchy",), key=datasource_luid)
            logger.info(f"已清除维度层级缓存: {datasource_luid}")
            return True
        except Exception as e:
            logger.error(f"清除维度层级缓存失败: {e}")
            return False
    
    # ========== 数据模型缓存 ==========
    
    def get_data_model(self, datasource_luid: str) -> Optional[Any]:
        """获取数据模型缓存"""
        try:
            from tableau_assistant.src.core.models import DataModel, LogicalTable, LogicalTableRelationship
            
            item = self.get(namespace=("data_model",), key=datasource_luid)
            
            if item and self._check_ttl(item.value, self.DATA_MODEL_TTL):
                data = item.value
                
                logical_tables = [
                    LogicalTable(
                        logicalTableId=t.get("logicalTableId", ""),
                        caption=t.get("caption", "")
                    )
                    for t in data.get("logicalTables", [])
                ]
                relationships = [
                    LogicalTableRelationship(
                        fromLogicalTableId=r.get("fromLogicalTableId", ""),
                        toLogicalTableId=r.get("toLogicalTableId", "")
                    )
                    for r in data.get("logicalTableRelationships", [])
                ]
                
                return DataModel(
                    logicalTables=logical_tables,
                    logicalTableRelationships=relationships
                )
            
            return None
        except Exception as e:
            logger.error(f"获取数据模型失败: {e}")
            return None
    
    def put_data_model(self, datasource_luid: str, data_model: Any) -> bool:
        """保存数据模型到缓存"""
        try:
            from tableau_assistant.src.core.models import DataModel
            
            if isinstance(data_model, DataModel):
                data = {
                    "logicalTables": [
                        {"logicalTableId": t.logicalTableId, "caption": t.caption}
                        for t in data_model.logicalTables
                    ],
                    "logicalTableRelationships": [
                        {"fromLogicalTableId": r.fromLogicalTableId, "toLogicalTableId": r.toLogicalTableId}
                        for r in data_model.logicalTableRelationships
                    ],
                    "_cached_at": time.time()
                }
            else:
                data = {**data_model, "_cached_at": time.time()}
            
            self.put(namespace=("data_model",), key=datasource_luid, value=data, ttl=self.DATA_MODEL_TTL)
            logger.info(f"数据模型已缓存: {datasource_luid}")
            return True
        except Exception as e:
            logger.error(f"保存数据模型失败: {e}")
            return False
    
    def clear_data_model_cache(self, datasource_luid: str) -> bool:
        """清除数据模型缓存"""
        try:
            self.delete(namespace=("data_model",), key=datasource_luid)
            logger.info(f"已清除数据模型缓存: {datasource_luid}")
            return True
        except Exception as e:
            logger.error(f"清除数据模型缓存失败: {e}")
            return False

    # ========== 用户偏好 ==========
    
    def get_user_preferences(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户偏好"""
        try:
            item = self.get(namespace=("user_preferences",), key=user_id)
            return item.value if item else None
        except Exception as e:
            logger.error(f"获取用户偏好失败: {e}")
            return None
    
    def put_user_preferences(self, user_id: str, preferences: Dict[str, Any]) -> bool:
        """保存用户偏好（永久存储）"""
        try:
            self.put(namespace=("user_preferences",), key=user_id, value=preferences, ttl=None)
            return True
        except Exception as e:
            logger.error(f"保存用户偏好失败: {e}")
            return False
    
    def update_user_preferences(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """更新用户偏好（增量更新）"""
        try:
            current = self.get_user_preferences(user_id) or {}
            updated = {**current, **updates}
            return self.put_user_preferences(user_id, updated)
        except Exception as e:
            logger.error(f"更新用户偏好失败: {e}")
            return False
    
    # ========== 问题历史 ==========
    
    def add_question_history(
        self,
        user_id: str,
        question: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """添加问题到历史记录"""
        try:
            key = f"q_{int(time.time() * 1000)}"
            data = {
                "question": question,
                "timestamp": time.time(),
                **(metadata or {})
            }
            self.put(namespace=("question_history", user_id), key=key, value=data, ttl=None)
            return True
        except Exception as e:
            logger.error(f"添加问题历史失败: {e}")
            return False
    
    def search_question_history(
        self,
        user_id: str,
        query: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """搜索历史问题（简单文本匹配）"""
        try:
            results = self.search(
                namespace_prefix=("question_history", user_id),
                query=query,
                limit=limit
            )
            return [item.value for item in results]
        except Exception as e:
            logger.error(f"搜索问题历史失败: {e}")
            return []
    
    def get_recent_questions(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的问题（按时间倒序）"""
        try:
            items = self.search(
                namespace_prefix=("question_history", user_id),
                query=None,
                limit=self.max_search_limit
            )
            
            sorted_items = sorted(
                items,
                key=lambda x: x.value.get("timestamp", 0),
                reverse=True
            )
            
            return [item.value for item in sorted_items[:limit]]
        except Exception as e:
            logger.error(f"获取最近问题失败: {e}")
            return []
    
    # ========== 异常知识库 ==========
    
    def get_anomaly_explanation(self, anomaly_key: str) -> Optional[Dict[str, Any]]:
        """获取异常解释"""
        try:
            item = self.get(namespace=("anomaly_knowledge",), key=anomaly_key)
            return item.value if item else None
        except Exception as e:
            logger.error(f"获取异常解释失败: {e}")
            return None
    
    def put_anomaly_explanation(self, anomaly_key: str, explanation: Dict[str, Any]) -> bool:
        """保存异常解释"""
        try:
            data = {**explanation, "_created_at": time.time()}
            self.put(namespace=("anomaly_knowledge",), key=anomaly_key, value=data, ttl=None)
            return True
        except Exception as e:
            logger.error(f"保存异常解释失败: {e}")
            return False
    
    def search_anomaly_knowledge(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """搜索异常知识库"""
        try:
            results = self.search(
                namespace_prefix=("anomaly_knowledge",),
                query=query,
                limit=limit
            )
            return [item.value for item in results]
        except Exception as e:
            logger.error(f"搜索异常知识库失败: {e}")
            return []
    
    # ========== 工具方法 ==========
    
    def _check_ttl(self, value: Dict[str, Any], ttl: int) -> bool:
        """检查缓存是否在 TTL 内有效"""
        cached_at = value.get("_cached_at", 0)
        if cached_at == 0:
            return True  # 没有时间戳，认为永久有效
        return (time.time() - cached_at) < ttl
    
    def cleanup_expired(self) -> int:
        """清理所有过期数据"""
        with self._lock:
            try:
                now = time.time()
                
                with self._transaction() as cursor:
                    cursor.execute(
                        "DELETE FROM store WHERE expires_at IS NOT NULL AND expires_at < ?",
                        (now,)
                    )
                    deleted = cursor.rowcount
                
                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} expired records")
                
                return deleted
                
            except Exception as e:
                logger.error(f"Failed to cleanup expired data: {e}")
                raise
    
    def get_stats(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                
                # 总记录数
                cursor.execute("SELECT COUNT(*) FROM store")
                total_count = cursor.fetchone()[0]
                
                # 按命名空间统计
                cursor.execute("""
                    SELECT 
                        CASE 
                            WHEN namespace LIKE 'metadata%' THEN 'metadata'
                            WHEN namespace LIKE 'dimension_hierarchy%' THEN 'dimension_hierarchy'
                            WHEN namespace LIKE 'data_model%' THEN 'data_model'
                            WHEN namespace LIKE 'user_preferences%' THEN 'user_preferences'
                            WHEN namespace LIKE 'question_history%' THEN 'question_history'
                            WHEN namespace LIKE 'anomaly_knowledge%' THEN 'anomaly_knowledge'
                            ELSE 'other'
                        END as ns_group,
                        COUNT(*) as count 
                    FROM store 
                    GROUP BY ns_group
                """)
                namespace_stats = {row[0]: row[1] for row in cursor.fetchall()}
                
                # 数据库大小
                db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
                
                return {
                    "total_count": total_count,
                    "namespace_stats": namespace_stats,
                    "db_size_bytes": db_size,
                    "db_size_mb": round(db_size / (1024 * 1024), 2),
                    "db_path": str(self.db_path)
                }
                
            except Exception as e:
                logger.error(f"Failed to get stats: {e}")
                return {}
    
    def vacuum(self):
        """优化数据库（回收空间、重建索引）"""
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                
                logger.info("Starting database vacuum...")
                cursor.execute("VACUUM")
                logger.info("Database vacuum completed")
                
            except Exception as e:
                logger.error(f"Failed to vacuum database: {e}")
                raise
    
    def backup(self, backup_path: str):
        """备份数据库"""
        with self._lock:
            try:
                import shutil
                
                backup_file = Path(backup_path)
                backup_file.parent.mkdir(parents=True, exist_ok=True)
                
                self.close()
                shutil.copy2(self.db_path, backup_file)
                
                logger.info(f"Database backed up to: {backup_file}")
                
                # 重新初始化
                self._init_db()
                
            except Exception as e:
                logger.error(f"Failed to backup database: {e}")
                raise
    
    def close(self):
        """关闭数据库连接"""
        with self._lock:
            try:
                if hasattr(self._local, 'conn') and self._local.conn:
                    self._local.conn.close()
                    self._local.conn = None
                    logger.debug("Database connection closed")
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
    
    def __del__(self):
        try:
            self.close()
        except:
            pass


# ========== 全局实例管理 ==========

_global_store_manager: Optional[StoreManager] = None


def get_store_manager(db_path: str = None) -> StoreManager:
    """
    获取全局 StoreManager 实例
    
    Args:
        db_path: 数据库路径，如果为 None 则使用默认路径
    
    Returns:
        StoreManager 实例
    """
    global _global_store_manager
    
    if _global_store_manager is None:
        _global_store_manager = StoreManager(db_path=db_path or "data/business_cache.db")
    
    return _global_store_manager


def reset_store_manager():
    """重置全局实例（主要用于测试）"""
    global _global_store_manager
    if _global_store_manager:
        _global_store_manager.close()
        _global_store_manager = None


# ========== 测试代码 ==========

if __name__ == "__main__":
    import tempfile
    
    print("=" * 60)
    print("测试统一存储管理器")
    print("=" * 60)
    
    # 使用临时数据库
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    manager = StoreManager(db_path=db_path)
    
    # 测试低级 API
    print("\n1. 测试低级存储 API...")
    manager.put(("test",), "key1", {"name": "测试数据", "value": 123})
    item = manager.get(("test",), "key1")
    print(f"   ✓ 低级 API: {item.value if item else None}")
    
    # 测试维度层级
    print("\n2. 测试维度层级缓存...")
    hierarchy = {"地区": {"level": 1, "category": "地理"}}
    manager.put_dimension_hierarchy("ds_123", hierarchy)
    cached = manager.get_dimension_hierarchy("ds_123")
    print(f"   ✓ 维度层级: {list(cached.keys()) if cached else None}")
    
    # 测试用户偏好
    print("\n3. 测试用户偏好...")
    manager.put_user_preferences("user_456", {"theme": "dark"})
    manager.update_user_preferences("user_456", {"language": "zh"})
    prefs = manager.get_user_preferences("user_456")
    print(f"   ✓ 用户偏好: {prefs}")
    
    # 测试问题历史
    print("\n4. 测试问题历史...")
    manager.add_question_history("user_456", "2024年销售额是多少？")
    manager.add_question_history("user_456", "各地区利润对比")
    recent = manager.get_recent_questions("user_456", limit=2)
    print(f"   ✓ 最近问题: {len(recent)} 条")
    
    # 测试 TTL 过期
    print("\n5. 测试 TTL 过期...")
    manager.put(("ttl_test",), "expire_soon", {"data": "will expire"}, ttl=1)
    item_before = manager.get(("ttl_test",), "expire_soon")
    print(f"   过期前: {item_before.value if item_before else None}")
    import time as t
    t.sleep(1.5)
    item_after = manager.get(("ttl_test",), "expire_soon")
    print(f"   过期后: {item_after}")
    
    # 测试统计
    print("\n6. 存储统计...")
    stats = manager.get_stats()
    print(f"   总记录数: {stats['total_count']}")
    print(f"   数据库大小: {stats['db_size_mb']} MB")
    print(f"   命名空间: {stats['namespace_stats']}")
    
    # 清理
    manager.close()
    Path(db_path).unlink(missing_ok=True)
    
    print("\n✓ 测试完成")
