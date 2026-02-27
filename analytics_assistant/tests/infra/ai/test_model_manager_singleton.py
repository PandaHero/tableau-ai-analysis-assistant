# -*- coding: utf-8 -*-
"""
Property 8: ModelManager 单例线程安全

验证并发线程调用 ModelManager() 构造函数时，所有线程获得同一实例。
"""
import threading
from unittest.mock import patch, MagicMock

import pytest
from hypothesis import given, settings, strategies as st

from analytics_assistant.src.infra.ai.model_manager import ModelManager


@pytest.fixture(autouse=True)
def _reset_singleton():
    """每个测试前后重置 ModelManager 单例状态"""
    original_instance = ModelManager._instance
    original_initialized = getattr(ModelManager, '_initialized', None)
    ModelManager._instance = None
    # 清除 _initialized 标记，确保 __init__ 可以重新执行
    if hasattr(ModelManager, '_initialized'):
        del ModelManager._initialized
    yield
    ModelManager._instance = original_instance
    if original_initialized is not None:
        ModelManager._initialized = original_initialized


@given(num_threads=st.integers(min_value=2, max_value=20))
@settings(max_examples=50, deadline=10000)
def test_singleton_thread_safety(num_threads: int):
    """并发线程获得同一 ModelManager 实例（id() 相同）"""
    # 重置单例
    ModelManager._instance = None
    if hasattr(ModelManager, '_initialized'):
        del ModelManager._initialized

    instances = [None] * num_threads
    barrier = threading.Barrier(num_threads)

    def create_instance(index: int) -> None:
        barrier.wait()  # 所有线程同时开始
        with patch.object(ModelManager, '__init__', lambda self: None):
            instances[index] = ModelManager()

    threads = [
        threading.Thread(target=create_instance, args=(i,))
        for i in range(num_threads)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    # 所有实例应为同一对象
    assert all(inst is not None for inst in instances), "部分线程未成功创建实例"
    first_id = id(instances[0])
    assert all(
        id(inst) == first_id for inst in instances
    ), f"并发创建产生了不同实例: {[id(inst) for inst in instances]}"


def test_singleton_returns_same_instance():
    """基本单例验证：连续两次调用返回同一实例"""
    with patch.object(ModelManager, '__init__', lambda self: None):
        a = ModelManager()
        b = ModelManager()
    assert a is b, "连续调用 ModelManager() 应返回同一实例"


def test_double_check_locking_exists():
    """验证 ModelManager 使用了 threading.Lock 双重检查锁定"""
    assert hasattr(ModelManager, '_lock'), "ModelManager 缺少 _lock 类属性"
    assert isinstance(ModelManager._lock, type(threading.Lock())), (
        "_lock 应为 threading.Lock 实例"
    )
