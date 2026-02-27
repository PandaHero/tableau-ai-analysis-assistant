# -*- coding: utf-8 -*-
"""
infra/ai 测试的 conftest

处理缺失的 langgraph.store.sqlite 模块依赖。
"""
import sys
from unittest.mock import MagicMock

# 模拟 langgraph.store.sqlite 模块，避免 ImportError
# 该模块在当前环境中未安装，但被 infra/storage/store_factory.py 导入
if "langgraph.store.sqlite" not in sys.modules:
    _mock_sqlite = MagicMock()
    sys.modules["langgraph.store.sqlite"] = _mock_sqlite
    sys.modules["langgraph.store.sqlite.aio"] = MagicMock()
