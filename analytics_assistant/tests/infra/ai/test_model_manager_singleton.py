# -*- coding: utf-8 -*-
"""
Property 8: ModelManager 单例入口线程安全

单例语义只保留在 get_model_manager()：
- 并发调用 get_model_manager() 必须获得同一实例
- 直接调用 ModelManager() 不再复用全局单例
"""
import threading
from unittest.mock import patch

import pytest
from hypothesis import given, settings, strategies as st

from analytics_assistant.src.infra.ai import model_manager as model_manager_module
from analytics_assistant.src.infra.ai.model_manager import ModelManager, get_model_manager


@pytest.fixture(autouse=True)
def _reset_singleton():
    """每个测试前后重置 getter 级别的单例状态。"""
    original_instance = model_manager_module._manager_instance
    model_manager_module._manager_instance = None
    yield
    model_manager_module._manager_instance = original_instance


@given(num_threads=st.integers(min_value=2, max_value=20))
@settings(max_examples=50, deadline=10000)
def test_get_model_manager_thread_safety(num_threads: int):
    """并发线程调用 getter 时应返回同一实例。"""
    model_manager_module._manager_instance = None

    instances = [None] * num_threads
    barrier = threading.Barrier(num_threads)

    def create_instance(index: int) -> None:
        barrier.wait()
        with patch.object(ModelManager, "__init__", lambda self: None):
            instances[index] = get_model_manager()

    threads = [
        threading.Thread(target=create_instance, args=(i,))
        for i in range(num_threads)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(instance is not None for instance in instances), "部分线程未成功获取实例"
    first_id = id(instances[0])
    assert all(
        id(instance) == first_id for instance in instances
    ), f"并发 getter 产生了不同实例: {[id(instance) for instance in instances]}"


def test_get_model_manager_returns_same_instance():
    """连续两次调用 getter 应返回同一实例。"""
    with patch.object(ModelManager, "__init__", lambda self: None):
        first = get_model_manager()
        second = get_model_manager()
    assert first is second, "get_model_manager() 应返回同一实例"


def test_direct_construction_returns_distinct_instances():
    """直接构造 ModelManager 不应再承担全局单例职责。"""
    with patch.object(ModelManager, "__init__", lambda self: None):
        first = ModelManager()
        second = ModelManager()
    assert first is not second, "直接调用 ModelManager() 不应返回全局单例"


def test_module_level_lock_exists():
    """验证 getter 使用模块级线程锁保护单例初始化。"""
    assert hasattr(model_manager_module, "_manager_lock"), "缺少模块级 _manager_lock"
    assert isinstance(model_manager_module._manager_lock, type(threading.Lock())), (
        "_manager_lock 应为 threading.Lock 实例"
    )
