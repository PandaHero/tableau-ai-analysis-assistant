"""
重试机制

使用 tenacity 库实现 LLM 调用的重试逻辑
"""
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    after_log
)
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)


# 定义需要重试的异常类型
RETRIABLE_EXCEPTIONS = (
    # OpenAI 异常
    Exception,  # 暂时捕获所有异常，后续可以细化
)


def create_retry_decorator(
    max_attempts: int = 3,
    min_wait: int = 4,
    max_wait: int = 10,
    multiplier: int = 1
):
    """
    创建重试装饰器
    
    Args:
        max_attempts: 最大重试次数
        min_wait: 最小等待时间（秒）
        max_wait: 最大等待时间（秒）
        multiplier: 指数退避的乘数
    
    Returns:
        重试装饰器
    """
    return retry(
        # 重试条件：特定异常类型
        retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
        
        # 停止条件：最大重试次数
        stop=stop_after_attempt(max_attempts),
        
        # 等待策略：指数退避 + 抖动
        wait=wait_exponential(
            multiplier=multiplier,
            min=min_wait,
            max=max_wait
        ),
        
        # 日志记录
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.INFO),
        
        # 重新抛出异常
        reraise=True
    )


# 默认的重试装饰器
default_retry = create_retry_decorator()


async def retry_async_call(
    func: Callable,
    *args,
    max_attempts: int = 3,
    **kwargs
) -> Any:
    """
    异步函数的重试包装器
    
    Args:
        func: 异步函数
        *args: 位置参数
        max_attempts: 最大重试次数
        **kwargs: 关键字参数
    
    Returns:
        函数返回值
    
    Raises:
        最后一次调用的异常
    """
    retry_decorator = create_retry_decorator(max_attempts=max_attempts)
    
    @retry_decorator
    async def _wrapped():
        return await func(*args, **kwargs)
    
    return await _wrapped()


# ============= 导出 =============

__all__ = [
    "create_retry_decorator",
    "default_retry",
    "retry_async_call",
]
