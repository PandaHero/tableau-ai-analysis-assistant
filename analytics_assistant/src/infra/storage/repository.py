# -*- coding: utf-8 -*-
"""
BaseRepository - 基于 LangGraph BaseStore 的 CRUD 抽象

为 API 层数据（会话、用户设置、反馈）提供统一的 CRUD 操作。
底层使用 BaseStore.put/get/search/delete，无需 SQLAlchemy ORM。

使用示例:
    from analytics_assistant.src.infra.storage import BaseRepository

    repo = BaseRepository("sessions")

    # 同步 CRUD
    repo.save("session-id-1", {"title": "新对话", "messages": []})
    item = repo.find_by_id("session-id-1")
    items = repo.find_all(filter_dict={"tableau_username": "admin"})
    repo.remove("session-id-1")

    # 异步 CRUD
    await repo.asave("session-id-1", {"title": "新对话"})
    item = await repo.afind_by_id("session-id-1")
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from langgraph.store.base import BaseStore

from .store_factory import StoreFactory

logger = logging.getLogger(__name__)

class BaseRepository:
    """基于 BaseStore 的 CRUD 抽象层。

    将 BaseStore 的 namespace + key/value 模型映射为类似 ORM 的 CRUD 操作。
    支持同步和异步两套 API。

    数据存储结构：
    - namespace: (repository_name,)  例如 ("sessions",)
    - key: 实体 ID（如 session_id）
    - value: 实体数据字典

    Examples:
        repo = BaseRepository("sessions")
        repo.save("id-1", {"title": "对话", "user": "admin"})
        item = repo.find_by_id("id-1")
    """

    def __init__(
        self,
        namespace: str,
        store: Optional[BaseStore] = None,
        default_ttl_minutes: Optional[int] = None,
    ):
        """初始化 Repository。

        Args:
            namespace: 命名空间（如 "sessions"、"user_settings"、"user_feedback"）
            store: 自定义 BaseStore 实例（可选，默认使用全局单例）
            default_ttl_minutes: 默认 TTL（分钟），None 使用 store 默认值
        """
        self.namespace = namespace
        self._namespace_tuple: tuple[str, ...] = (namespace,)
        self._default_ttl_minutes = default_ttl_minutes

        if store is not None:
            self._store = store
        else:
            # 根据 namespace 查找 app.yaml 中的独立配置，无配置则使用默认存储
            self._store = StoreFactory.create_namespace_store(namespace)

        logger.info(f"Repository 已初始化: namespace={namespace}")

    # ========================================
    # 同步 CRUD
    # ========================================

    def save(self, entity_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """保存实体（创建或更新）。

        自动添加 updated_at 时间戳。如果是新建，同时添加 created_at。

        Args:
            entity_id: 实体 ID
            data: 实体数据字典

        Returns:
            保存后的完整数据
        """
        now = datetime.now(timezone.utc).isoformat()

        # 检查是否已存在（用于设置 created_at）
        existing = self._store.get(self._namespace_tuple, entity_id)
        if existing and existing.value is not None:
            # 更新：保留 created_at
            data["created_at"] = existing.value.get("created_at", now)
        else:
            # 新建：设置 created_at
            data.setdefault("created_at", now)

        data["updated_at"] = now

        if self._default_ttl_minutes is not None:
            self._store.put(
                self._namespace_tuple, entity_id, data,
                ttl=self._default_ttl_minutes,
            )
        else:
            self._store.put(self._namespace_tuple, entity_id, data)

        return data

    def find_by_id(self, entity_id: str) -> Optional[dict[str, Any]]:
        """根据 ID 查找实体。

        Args:
            entity_id: 实体 ID

        Returns:
            实体数据字典，不存在返回 None
        """
        try:
            item = self._store.get(self._namespace_tuple, entity_id)
            if item and item.value is not None:
                return item.value
            return None
        except Exception as e:
            logger.error(
                f"查找实体失败: namespace={self.namespace}, "
                f"id={entity_id}, error={e}"
            )
            return None

    def find_all(
        self,
        filter_dict: Optional[dict[str, Any]] = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """查找所有匹配的实体。

        Args:
            filter_dict: 过滤条件（键值对匹配）
            limit: 最大返回数量

        Returns:
            匹配的实体列表
        """
        try:
            items = self._store.search(self._namespace_tuple, limit=limit)
            results = []
            for item in items:
                if item.value is None:
                    continue
                if filter_dict:
                    match = all(
                        item.value.get(k) == v
                        for k, v in filter_dict.items()
                    )
                    if not match:
                        continue
                # 附加 key 作为 id
                data = dict(item.value)
                data.setdefault("id", item.key)
                results.append(data)
            return results
        except Exception as e:
            logger.error(
                f"查找实体列表失败: namespace={self.namespace}, "
                f"filter={filter_dict}, error={e}"
            )
            return []

    def remove(self, entity_id: str) -> bool:
        """删除实体。

        Args:
            entity_id: 实体 ID

        Returns:
            是否成功
        """
        try:
            self._store.delete(self._namespace_tuple, entity_id)
            return True
        except Exception as e:
            logger.error(
                f"删除实体失败: namespace={self.namespace}, "
                f"id={entity_id}, error={e}"
            )
            return False

    # ========================================
    # 异步 CRUD
    # ========================================

    async def asave(self, entity_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """异步保存实体（创建或更新）。

        Args:
            entity_id: 实体 ID
            data: 实体数据字典

        Returns:
            保存后的完整数据
        """
        now = datetime.now(timezone.utc).isoformat()

        existing = await self._store.aget(self._namespace_tuple, entity_id)
        if existing and existing.value is not None:
            data["created_at"] = existing.value.get("created_at", now)
        else:
            data.setdefault("created_at", now)

        data["updated_at"] = now

        if self._default_ttl_minutes is not None:
            await self._store.aput(
                self._namespace_tuple, entity_id, data,
                ttl=self._default_ttl_minutes,
            )
        else:
            await self._store.aput(self._namespace_tuple, entity_id, data)

        return data

    async def afind_by_id(self, entity_id: str) -> Optional[dict[str, Any]]:
        """异步根据 ID 查找实体。

        Args:
            entity_id: 实体 ID

        Returns:
            实体数据字典，不存在返回 None
        """
        try:
            item = await self._store.aget(self._namespace_tuple, entity_id)
            if item and item.value is not None:
                return item.value
            return None
        except Exception as e:
            logger.error(
                f"异步查找实体失败: namespace={self.namespace}, "
                f"id={entity_id}, error={e}"
            )
            return None

    async def afind_all(
        self,
        filter_dict: Optional[dict[str, Any]] = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """异步查找所有匹配的实体。

        Args:
            filter_dict: 过滤条件
            limit: 最大返回数量

        Returns:
            匹配的实体列表
        """
        try:
            items = await self._store.asearch(self._namespace_tuple, limit=limit)
            results = []
            for item in items:
                if item.value is None:
                    continue
                if filter_dict:
                    match = all(
                        item.value.get(k) == v
                        for k, v in filter_dict.items()
                    )
                    if not match:
                        continue
                data = dict(item.value)
                data.setdefault("id", item.key)
                results.append(data)
            return results
        except Exception as e:
            logger.error(
                f"异步查找实体列表失败: namespace={self.namespace}, "
                f"filter={filter_dict}, error={e}"
            )
            return []

    async def aremove(self, entity_id: str) -> bool:
        """异步删除实体。

        Args:
            entity_id: 实体 ID

        Returns:
            是否成功
        """
        try:
            await self._store.adelete(self._namespace_tuple, entity_id)
            return True
        except Exception as e:
            logger.error(
                f"异步删除实体失败: namespace={self.namespace}, "
                f"id={entity_id}, error={e}"
            )
            return False

__all__ = [
    "BaseRepository",
]
