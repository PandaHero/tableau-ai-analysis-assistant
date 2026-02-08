# -*- coding: utf-8 -*-
"""
Tableau 平台实现

提供 Tableau 特定的适配器和查询构建器。

本模块整合：
- 平台适配器（实现 BasePlatformAdapter）
- 查询构建器（实现 BaseQueryBuilder）
"""

from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
from analytics_assistant.src.platform.tableau.query_builder import TableauQueryBuilder
from analytics_assistant.src.platform.base import register_adapter

import logging

logger = logging.getLogger(__name__)


# 注册 Tableau 适配器到平台注册表
def _register():
    """注册 Tableau 适配器到平台注册表。"""
    try:
        register_adapter("tableau", TableauAdapter)
    except Exception as e:
        logger.warning(f"注册 Tableau 适配器失败: {e}")


_register()

__all__ = [
    "TableauAdapter",
    "TableauQueryBuilder",
]
