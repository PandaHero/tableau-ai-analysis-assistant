"""vNext 版本化存储。

本模块实现 vNext 功能的版本化存储，支持数据隔离和回滚。

设计原则（Requirements 0.14）：
- 使用版本化 namespace 存储 vNext 缓存
- 与旧版 namespace 隔离，不覆盖旧键
- 支持快速回滚（删除 vNext namespace）
- 数据最小化，不落盘敏感信息

Namespace 格式：
- vNext: ("semantic_parser", "vnext", datasource_luid)
- Legacy: ("semantic_parser", datasource_luid)

敏感字段过滤：
- sample_values: 可能含业务数据
- user_question: 可能含 PII
- raw_input: 可能含 PII

Usage:
    from tableau_assistant.src.infra.storage.vnext_store import VNextStore
    from tableau_assistant.src.infra.storage.langgraph_store import get_store
    
    base_store = get_store()
    vnext_store = VNextStore(base_store)
    
    # 存储数据
    await vnext_store.put(
        datasource_luid="ds-123",
        key="schema_candidates:hash123",
        value={"candidates": [...]},
    )
    
    # 读取数据
    data = await vnext_store.get(
        datasource_luid="ds-123",
        key="schema_candidates:hash123",
    )
    
    # 回滚：删除 vNext 数据
    await vnext_store.delete_vnext_data(datasource_luid="ds-123")
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# 敏感字段列表（不落盘）
SENSITIVE_FIELDS = {
    "sample_values",  # 可能含业务数据
    "user_question",  # 可能含 PII
    "raw_input",  # 可能含 PII
    "original_question",  # 可能含 PII
    "user_input",  # 可能含 PII
}


class VNextStore:
    """vNext 版本化存储。
    
    使用版本化 namespace 存储 vNext 缓存，与旧版隔离。
    
    Attributes:
        base_store: 底层存储（LangGraphStore）
    """
    
    VNEXT_NAMESPACE_PREFIX: Tuple[str, str] = ("semantic_parser", "vnext")
    
    def __init__(self, base_store: Any):
        """初始化 vNext 存储。
        
        Args:
            base_store: 底层存储实例
        """
        self.base_store = base_store
    
    def get_namespace(self, datasource_luid: str) -> Tuple[str, str, str]:
        """获取 vNext namespace。
        
        Args:
            datasource_luid: 数据源 LUID
        
        Returns:
            namespace 元组
        """
        return (*self.VNEXT_NAMESPACE_PREFIX, datasource_luid)
    
    async def put(
        self,
        datasource_luid: str,
        key: str,
        value: Dict[str, Any],
        exclude_sensitive: bool = True,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """存储数据 - 自动过滤敏感字段。
        
        Args:
            datasource_luid: 数据源 LUID
            key: 存储键
            value: 存储值
            exclude_sensitive: 是否过滤敏感字段
            ttl_seconds: TTL 秒数（可选）
        """
        if exclude_sensitive:
            value = self._filter_sensitive_fields(value)
        
        # 添加元数据
        value["_vnext_stored_at"] = datetime.now().isoformat()
        if ttl_seconds:
            value["_vnext_ttl_seconds"] = ttl_seconds
        
        namespace = self.get_namespace(datasource_luid)
        
        try:
            await self.base_store.aput(namespace, key, value)
            logger.debug(
                f"VNextStore: stored key={key} in namespace={namespace}",
                extra={
                    "datasource_luid": datasource_luid,
                    "key": key,
                    "value_keys": list(value.keys()),
                },
            )
        except Exception as e:
            logger.error(
                f"VNextStore: failed to store key={key}: {e}",
                extra={
                    "datasource_luid": datasource_luid,
                    "key": key,
                    "error": str(e),
                },
            )
            raise
    
    async def get(
        self,
        datasource_luid: str,
        key: str,
    ) -> Optional[Dict[str, Any]]:
        """读取数据。
        
        Args:
            datasource_luid: 数据源 LUID
            key: 存储键
        
        Returns:
            存储值，如果不存在返回 None
        """
        namespace = self.get_namespace(datasource_luid)
        
        try:
            result = await self.base_store.aget(namespace, key)
            
            if result is None:
                return None
            
            # 检查 TTL
            if self._is_expired(result):
                logger.debug(f"VNextStore: key={key} expired, returning None")
                return None
            
            return result
            
        except Exception as e:
            logger.error(
                f"VNextStore: failed to get key={key}: {e}",
                extra={
                    "datasource_luid": datasource_luid,
                    "key": key,
                    "error": str(e),
                },
            )
            return None
    
    async def delete(
        self,
        datasource_luid: str,
        key: str,
    ) -> bool:
        """删除单个键。
        
        Args:
            datasource_luid: 数据源 LUID
            key: 存储键
        
        Returns:
            是否删除成功
        """
        namespace = self.get_namespace(datasource_luid)
        
        try:
            await self.base_store.adelete(namespace, key)
            logger.info(
                f"VNextStore: deleted key={key}",
                extra={
                    "datasource_luid": datasource_luid,
                    "key": key,
                },
            )
            return True
        except Exception as e:
            logger.error(
                f"VNextStore: failed to delete key={key}: {e}",
                extra={
                    "datasource_luid": datasource_luid,
                    "key": key,
                    "error": str(e),
                },
            )
            return False
    
    async def delete_vnext_data(
        self,
        datasource_luid: Optional[str] = None,
    ) -> bool:
        """删除 vNext 数据（用于回滚）。
        
        注意：SqliteStore 可能不支持 pattern delete，
        如果不支持，建议使用备份恢复方式回滚。
        
        Args:
            datasource_luid: 数据源 LUID（可选，不指定则删除所有 vNext 数据）
        
        Returns:
            是否删除成功
        """
        try:
            if datasource_luid:
                namespace = self.get_namespace(datasource_luid)
            else:
                namespace = self.VNEXT_NAMESPACE_PREFIX
            
            # 尝试使用 adelete_namespace（如果存储支持）
            if hasattr(self.base_store, "adelete_namespace"):
                await self.base_store.adelete_namespace(namespace)
                logger.info(
                    f"VNextStore: deleted namespace={namespace}",
                    extra={
                        "datasource_luid": datasource_luid,
                        "namespace": namespace,
                    },
                )
                return True
            else:
                # 存储不支持 namespace 删除
                logger.warning(
                    "VNextStore: base_store does not support adelete_namespace, "
                    "please use backup restore for rollback",
                    extra={
                        "datasource_luid": datasource_luid,
                        "namespace": namespace,
                    },
                )
                return False
                
        except Exception as e:
            logger.error(
                f"VNextStore: failed to delete namespace: {e}",
                extra={
                    "datasource_luid": datasource_luid,
                    "error": str(e),
                },
            )
            return False
    
    async def list_keys(
        self,
        datasource_luid: str,
        prefix: Optional[str] = None,
    ) -> List[str]:
        """列出指定 namespace 下的所有键。
        
        Args:
            datasource_luid: 数据源 LUID
            prefix: 键前缀（可选）
        
        Returns:
            键列表
        """
        namespace = self.get_namespace(datasource_luid)
        
        try:
            if hasattr(self.base_store, "alist_keys"):
                keys = await self.base_store.alist_keys(namespace, prefix=prefix)
                return keys
            else:
                logger.warning("VNextStore: base_store does not support alist_keys")
                return []
        except Exception as e:
            logger.error(
                f"VNextStore: failed to list keys: {e}",
                extra={
                    "datasource_luid": datasource_luid,
                    "prefix": prefix,
                    "error": str(e),
                },
            )
            return []
    
    def _filter_sensitive_fields(self, value: Dict[str, Any]) -> Dict[str, Any]:
        """过滤敏感字段。
        
        递归过滤嵌套字典中的敏感字段。
        
        Args:
            value: 原始值
        
        Returns:
            过滤后的值
        """
        if not isinstance(value, dict):
            return value
        
        filtered = {}
        for k, v in value.items():
            if k in SENSITIVE_FIELDS:
                continue
            if isinstance(v, dict):
                filtered[k] = self._filter_sensitive_fields(v)
            elif isinstance(v, list):
                filtered[k] = [
                    self._filter_sensitive_fields(item) if isinstance(item, dict) else item
                    for item in v
                ]
            else:
                filtered[k] = v
        
        return filtered
    
    def _is_expired(self, value: Dict[str, Any]) -> bool:
        """检查数据是否过期。
        
        Args:
            value: 存储值
        
        Returns:
            是否过期
        """
        stored_at_str = value.get("_vnext_stored_at")
        ttl_seconds = value.get("_vnext_ttl_seconds")
        
        if not stored_at_str or not ttl_seconds:
            return False
        
        try:
            stored_at = datetime.fromisoformat(stored_at_str)
            elapsed = (datetime.now() - stored_at).total_seconds()
            return elapsed > ttl_seconds
        except Exception:
            return False


__all__ = [
    "VNextStore",
    "SENSITIVE_FIELDS",
]
