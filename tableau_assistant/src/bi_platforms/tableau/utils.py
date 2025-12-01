"""
Tableau HTTP 工具函数

提供异步 HTTP 请求功能
"""
import aiohttp
from typing import Dict, Any, Optional


async def http_post(
    endpoint: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    timeout: int = 30
) -> Dict[str, Any]:
    """
    异步 HTTP POST 请求
    
    Args:
        endpoint: 请求 URL
        headers: 请求头
        payload: 请求体
        timeout: 超时时间（秒）
    
    Returns:
        包含 status 和 data 的字典
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as response:
            data = await response.json()
            return {
                "status": response.status,
                "data": data
            }


async def http_get(
    endpoint: str,
    headers: Dict[str, str],
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    异步 HTTP GET 请求
    
    Args:
        endpoint: 请求 URL
        headers: 请求头
        params: 查询参数
        timeout: 超时时间（秒）
    
    Returns:
        包含 status 和 data 的字典
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(
            endpoint,
            headers=headers,
            params=params,
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as response:
            data = await response.json()
            return {
                "status": response.status,
                "data": data
            }


__all__ = ["http_post", "http_get"]
