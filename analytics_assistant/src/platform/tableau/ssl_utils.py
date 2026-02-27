# -*- coding: utf-8 -*-
"""
Tableau SSL 配置工具

提供统一的 SSL 验证参数获取，供 auth.py 和 client.py 共用。
"""
import logging
import ssl
from typing import Any, Union

from analytics_assistant.src.infra.config import get_config

# certifi 可选依赖（标准模式：Rule 19.1）
try:
    import certifi
    _CERTIFI_AVAILABLE = True
except ImportError:
    _CERTIFI_AVAILABLE = False

logger = logging.getLogger(__name__)

def get_ssl_verify() -> Union[ssl.SSLContext, bool]:
    """获取 SSL 验证参数。

    Returns:
        - ssl.SSLContext: 如果配置了 ca_bundle 或 certifi 可用
        - True: 使用系统默认证书
        - False: 禁用 SSL 验证（仅开发环境）
    """
    config = get_config()

    if not config.get_ssl_verify():
        return False

    ca_bundle = config.get_ssl_ca_bundle()
    if ca_bundle:
        ssl_context = ssl.create_default_context(cafile=ca_bundle)
        return ssl_context

    if _CERTIFI_AVAILABLE:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        return ssl_context

    return True
