# -*- coding: utf-8 -*-
"""缓存相关方法。依赖主类初始化 self._cache 和 self.config。"""
import hashlib
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

class CacheMixin:
    """缓存相关方法 Mixin"""

    def _make_cache_key(self, term: str, datasource_luid: str, role_filter: Optional[str] = None) -> str:
        """创建缓存键

        包含 role_filter，因为同一 term 在不同角色过滤下可能映射到不同字段。
        """
        role_part = role_filter.lower() if role_filter else "any"
        key_str = f"{datasource_luid}:{term.lower().strip()}:{role_part}"
        return hashlib.md5(key_str.encode('utf-8')).hexdigest()

    def _get_from_cache(self, term: str, datasource_luid: str, role_filter: Optional[str] = None) -> Optional[dict[str, Any]]:
        """从缓存获取映射"""
        if self._cache is None:
            return None
        try:
            key = self._make_cache_key(term, datasource_luid, role_filter)
            return self._cache.get(key)
        except Exception as e:
            logger.warning(f"从缓存获取映射失败: {e}")
            return None

    def _put_to_cache(
        self,
        term: str,
        datasource_luid: str,
        technical_field: str,
        confidence: float,
        role_filter: Optional[str] = None,
        **kwargs
    ) -> bool:
        """保存映射到缓存"""
        if self._cache is None:
            return False
        try:
            key = self._make_cache_key(term, datasource_luid, role_filter)
            self._cache.set(key, {
                "business_term": term,
                "technical_field": technical_field,
                "confidence": confidence,
                "timestamp": time.time(),
                "datasource_luid": datasource_luid,
                "role_filter": role_filter,
                **kwargs
            })
            logger.debug(f"缓存映射: {term} -> {technical_field}")
            return True
        except Exception as e:
            logger.warning(f"保存映射到缓存失败: {e}")
            return False
