# -*- coding: utf-8 -*-
"""
存储工厂模块

基于 LangGraph BaseStore 框架，根据配置创建不同后端的存储实例。
支持的后端：
- sqlite: LangGraph SqliteStore（默认）
- memory: LangGraph InMemoryStore
- postgres: LangGraph AsyncPostgresStore（需安装 langgraph-checkpoint-postgres）
- redis: LangGraph RedisStore（需安装 langgraph-checkpoint-redis）

所有后端继承 BaseStore，API 完全一致，切换只需修改 app.yaml 配置。
"""

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from langgraph.store.base import BaseStore, TTLConfig
from langgraph.store.memory import InMemoryStore
from langgraph.store.sqlite import SqliteStore

from ..config import get_config

logger = logging.getLogger(__name__)

# 可选后端
try:
    from langgraph.store.postgres import AsyncPostgresStore
    _POSTGRES_AVAILABLE = True
except ImportError:
    _POSTGRES_AVAILABLE = False
    logger.info("langgraph-checkpoint-postgres 未安装，PostgreSQL 后端不可用")

try:
    from langgraph.store.redis import RedisStore
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False
    logger.info("langgraph-checkpoint-redis 未安装，Redis 后端不可用")

# 默认配置常量
_DEFAULT_BACKEND = "sqlite"
_DEFAULT_CONNECTION_STRING = "analytics_assistant/data/storage.db"
_DEFAULT_TTL_MINUTES = 1440  # 24 小时
_DEFAULT_SWEEP_INTERVAL_MINUTES = 60

class StoreFactory:
    """存储工厂

    根据配置创建 LangGraph BaseStore 实例。
    所有后端共享相同的 BaseStore API，切换后端只需修改 app.yaml。

    Examples:
        # 使用全局默认配置创建
        store = StoreFactory.get_default_store()

        # 为特定命名空间创建（可能使用不同后端）
        store = StoreFactory.create_namespace_store("auth")
    """

    # 默认存储单例
    _default_store: Optional[BaseStore] = None
    _default_store_lock = threading.Lock()

    # 命名空间存储缓存
    _namespace_stores: dict[str, BaseStore] = {}
    _namespace_stores_lock = threading.Lock()

    @classmethod
    def create_store(
        cls,
        backend: str = _DEFAULT_BACKEND,
        connection_string: Optional[str] = None,
        ttl_minutes: Optional[int] = None,
    ) -> BaseStore:
        """根据参数创建 BaseStore 实例。

        Args:
            backend: 后端类型（sqlite/memory/postgres/redis）
            connection_string: 连接字符串（sqlite 为文件路径，postgres/redis 为 URI）
            ttl_minutes: 默认 TTL（分钟），None 表示不设置

        Returns:
            BaseStore 实例

        Raises:
            ImportError: 所需后端未安装
            ValueError: 不支持的后端类型
        """
        backend = backend.lower()

        if backend == "sqlite":
            return cls._create_sqlite_store(connection_string, ttl_minutes)
        elif backend == "memory":
            return cls._create_memory_store()
        elif backend == "postgres":
            return cls._create_postgres_store(connection_string, ttl_minutes)
        elif backend == "redis":
            return cls._create_redis_store(connection_string, ttl_minutes)
        else:
            raise ValueError(
                f"不支持的存储后端: {backend}，"
                f"支持的后端: sqlite, memory, postgres, redis"
            )

    @classmethod
    def get_default_store(cls) -> BaseStore:
        """获取全局默认存储实例（单例）。

        从 app.yaml 的 storage 配置节读取后端类型和连接参数。

        Returns:
            全局默认 BaseStore 实例
        """
        if cls._default_store is None:
            with cls._default_store_lock:
                if cls._default_store is None:
                    storage_config = cls._get_storage_config()
                    backend = storage_config.get("backend", _DEFAULT_BACKEND)
                    connection_string = storage_config.get(
                        "connection_string", _DEFAULT_CONNECTION_STRING
                    )
                    ttl_minutes = storage_config.get("ttl", _DEFAULT_TTL_MINUTES)

                    cls._default_store = cls.create_store(
                        backend=backend,
                        connection_string=connection_string,
                        ttl_minutes=ttl_minutes,
                    )
                    logger.info(
                        f"默认存储已初始化: backend={backend}, "
                        f"connection={connection_string}"
                    )
        return cls._default_store

    @classmethod
    def create_namespace_store(cls, namespace: str) -> BaseStore:
        """为特定命名空间创建存储实例。

        如果 app.yaml 中为该命名空间配置了独立后端，则使用独立配置；
        否则使用全局默认存储。

        Args:
            namespace: 命名空间名称（对应 app.yaml storage.namespaces 下的键）

        Returns:
            BaseStore 实例
        """
        if namespace in cls._namespace_stores:
            return cls._namespace_stores[namespace]

        with cls._namespace_stores_lock:
            if namespace in cls._namespace_stores:
                return cls._namespace_stores[namespace]

            storage_config = cls._get_storage_config()
            namespaces_config = storage_config.get("namespaces", {})
            ns_config = namespaces_config.get(namespace)

            if ns_config is None:
                # 无独立配置，使用默认存储
                store = cls.get_default_store()
            else:
                ns_backend = ns_config.get(
                    "backend",
                    storage_config.get("backend", _DEFAULT_BACKEND),
                )
                ns_connection = ns_config.get(
                    "connection_string",
                    storage_config.get("connection_string", _DEFAULT_CONNECTION_STRING),
                )
                ns_ttl = ns_config.get("ttl")

                store = cls.create_store(
                    backend=ns_backend,
                    connection_string=ns_connection,
                    ttl_minutes=ns_ttl,
                )
                logger.info(
                    f"命名空间存储已初始化: namespace={namespace}, "
                    f"backend={ns_backend}"
                )

            cls._namespace_stores[namespace] = store
            return store

    @classmethod
    def reset(cls) -> None:
        """重置所有存储实例（主要用于测试）。"""
        with cls._default_store_lock:
            if cls._default_store is not None:
                cls._close_store(cls._default_store)
                cls._default_store = None

        with cls._namespace_stores_lock:
            for ns, store in cls._namespace_stores.items():
                cls._close_store(store)
            cls._namespace_stores.clear()

        logger.info("所有存储实例已重置")

    # ========================================
    # 私有方法
    # ========================================

    @classmethod
    def _get_storage_config(cls) -> dict[str, Any]:
        """从 app.yaml 获取存储配置。"""
        try:
            config = get_config()
            return config.get_storage_config()
        except Exception as e:
            logger.warning(f"获取存储配置失败，使用默认值: {e}")
            return {}

    @classmethod
    def _get_sweep_interval(cls) -> int:
        """从 app.yaml 获取 sweep_interval_minutes 配置。"""
        try:
            config = get_config()
            sqlite_config = config.get("storage", {}).get("sqlite", {})
            return sqlite_config.get(
                "sweep_interval_minutes", _DEFAULT_SWEEP_INTERVAL_MINUTES
            )
        except Exception:
            return _DEFAULT_SWEEP_INTERVAL_MINUTES

    @classmethod
    def _create_sqlite_store(
        cls,
        connection_string: Optional[str],
        ttl_minutes: Optional[int],
    ) -> SqliteStore:
        """创建 SqliteStore 实例。"""
        db_path = connection_string or _DEFAULT_CONNECTION_STRING
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)

        ttl_config: Optional[TTLConfig] = None
        if ttl_minutes is not None:
            sweep_interval = cls._get_sweep_interval()
            ttl_config = {
                "default_ttl": ttl_minutes,
                "refresh_on_read": True,
                "sweep_interval_minutes": sweep_interval,
            }

        store = SqliteStore(conn, ttl=ttl_config)
        store.setup()

        logger.debug(f"SqliteStore 已创建: path={db_path}, ttl={ttl_minutes}min")
        return store

    @classmethod
    def _create_memory_store(cls) -> InMemoryStore:
        """创建 InMemoryStore 实例。"""
        store = InMemoryStore()
        logger.debug("InMemoryStore 已创建")
        return store

    @classmethod
    def _create_postgres_store(
        cls,
        connection_string: Optional[str],
        ttl_minutes: Optional[int],
    ) -> "AsyncPostgresStore":
        """创建 AsyncPostgresStore 实例。"""
        if not _POSTGRES_AVAILABLE:
            raise ImportError(
                "PostgreSQL 后端需要 langgraph-checkpoint-postgres，"
                "请安装: pip install langgraph-checkpoint-postgres"
            )

        if not connection_string:
            raise ValueError("PostgreSQL 后端需要提供 connection_string")

        ttl_config: Optional[TTLConfig] = None
        if ttl_minutes is not None:
            sweep_interval = cls._get_sweep_interval()
            ttl_config = {
                "default_ttl": ttl_minutes,
                "refresh_on_read": True,
                "sweep_interval_minutes": sweep_interval,
            }

        store = AsyncPostgresStore(conn_string=connection_string, ttl=ttl_config)
        logger.debug(f"AsyncPostgresStore 已创建: ttl={ttl_minutes}min")
        return store

    @classmethod
    def _create_redis_store(
        cls,
        connection_string: Optional[str],
        ttl_minutes: Optional[int],
    ) -> "RedisStore":
        """创建 RedisStore 实例。"""
        if not _REDIS_AVAILABLE:
            raise ImportError(
                "Redis 后端需要 langgraph-checkpoint-redis，"
                "请安装: pip install langgraph-checkpoint-redis"
            )

        if not connection_string:
            raise ValueError("Redis 后端需要提供 connection_string")

        ttl_config: Optional[TTLConfig] = None
        if ttl_minutes is not None:
            sweep_interval = cls._get_sweep_interval()
            ttl_config = {
                "default_ttl": ttl_minutes,
                "refresh_on_read": True,
                "sweep_interval_minutes": sweep_interval,
            }

        store = RedisStore(url=connection_string, ttl=ttl_config)
        logger.debug(f"RedisStore 已创建: ttl={ttl_minutes}min")
        return store

    @classmethod
    def _close_store(cls, store: BaseStore) -> None:
        """安全关闭存储实例。"""
        try:
            if isinstance(store, SqliteStore) and hasattr(store, "_conn"):
                store._conn.close()
        except Exception as e:
            logger.warning(f"关闭存储时出错: {e}")
