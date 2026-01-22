# -*- coding: utf-8 -*-
"""
Platform 层 - 平台特定实现

本模块包含各 BI 平台的适配器实现：
- tableau/ - Tableau 平台适配器
- (未来) powerbi/ - Power BI 平台适配器
- (未来) superset/ - Superset 平台适配器
"""

from analytics_assistant.src.platform.base import (
    PlatformRegistry,
    register_adapter,
    get_adapter,
)

__all__ = [
    "PlatformRegistry",
    "register_adapter",
    "get_adapter",
]
