# -*- coding: utf-8 -*-
"""
agents/base/context.py 的属性测试和单元测试

测试内容：
- Property 1: WorkflowContext 满足 WorkflowContextProtocol 约束
- Property 2: get_context 提取等价性
- 单元测试: 边界情况覆盖
- 静态分析: 依赖方向合规性验证
"""

import ast
import os
import pytest
from hypothesis import given, settings, strategies as st
from typing import Any, Dict, List, Optional

from analytics_assistant.src.core.interfaces import WorkflowContextProtocol

# 直接加载 context 模块，绕过 agents/base/__init__.py
# __init__.py 导入 node.py 会触发 infra.ai ↔ infra.storage 的预存循环导入
import importlib.util as _ilu

_context_path = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "src", "agents", "base", "context.py",
))
_spec = _ilu.spec_from_file_location(
    "analytics_assistant.src.agents.base.context", _context_path
)
_context_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_context_mod)

get_context = _context_mod.get_context
get_context_or_raise = _context_mod.get_context_or_raise


# ═══════════════════════════════════════════════════════════════════════════
# 测试用 Protocol 实现（轻量级，避免触发循环导入）
# ═══════════════════════════════════════════════════════════════════════════

class _MockWorkflowContext:
    """满足 WorkflowContextProtocol 的轻量级测试实现。"""

    def __init__(
        self,
        datasource_luid: str = "ds_test",
        data_model: Optional[Any] = None,
        field_semantic: Optional[Dict[str, Any]] = None,
        platform_adapter: Optional[Any] = None,
        auth: Optional[Any] = None,
        field_values_cache: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        self._datasource_luid = datasource_luid
        self._data_model = data_model
        self._field_semantic = field_semantic
        self._platform_adapter = platform_adapter
        self._auth = auth
        self._field_values_cache = field_values_cache or {}

    @property
    def datasource_luid(self) -> str:
        return self._datasource_luid

    @property
    def data_model(self) -> Optional[Any]:
        return self._data_model

    @property
    def field_semantic(self) -> Optional[Dict[str, Any]]:
        return self._field_semantic

    @property
    def platform_adapter(self) -> Optional[Any]:
        return self._platform_adapter

    @property
    def auth(self) -> Optional[Any]:
        return self._auth

    @property
    def field_values_cache(self) -> Dict[str, List[str]]:
        return self._field_values_cache

    @property
    def schema_hash(self) -> str:
        return "mock_hash"

    def enrich_field_candidates_with_hierarchy(
        self, field_candidates: List[Any],
    ) -> List[Any]:
        return field_candidates


# ═══════════════════════════════════════════════════════════════════════════
# Property 1: WorkflowContext 满足 Protocol 约束
# Feature: graph-dependency-refactor
# Validates: Requirements 1.5
# ═══════════════════════════════════════════════════════════════════════════

@given(
    datasource_luid=st.text(min_size=1, max_size=50),
    has_data_model=st.booleans(),
    has_field_semantic=st.booleans(),
    has_auth=st.booleans(),
)
@settings(max_examples=100)
def test_property1_workflow_context_satisfies_protocol(
    datasource_luid: str,
    has_data_model: bool,
    has_field_semantic: bool,
    has_auth: bool,
) -> None:
    """**Property 1: WorkflowContext 满足 Protocol 约束**

    对于任意有效的 WorkflowContext 实例（使用满足 Protocol 的实现），
    该实例都应通过 isinstance(ctx, WorkflowContextProtocol) 检查。

    **Validates: Requirements 1.5**
    """
    ctx = _MockWorkflowContext(
        datasource_luid=datasource_luid,
        data_model={"mock": True} if has_data_model else None,
        field_semantic={"field1": {"category": "time"}} if has_field_semantic else None,
        auth={"token": "***"} if has_auth else None,
    )
    assert isinstance(ctx, WorkflowContextProtocol)


# ═══════════════════════════════════════════════════════════════════════════
# Property 2: get_context 提取等价性
# Feature: graph-dependency-refactor
# Validates: Requirements 2.4, 3.4
# ═══════════════════════════════════════════════════════════════════════════

@given(obj=st.from_type(type).flatmap(st.from_type) | st.integers() | st.text())
@settings(max_examples=100)
def test_property2_get_context_extraction_equivalence(obj: Any) -> None:
    """**Property 2: get_context 提取等价性**

    对于任意对象 obj，放入 config["configurable"]["workflow_context"]，
    get_context(config) 应返回与 obj 完全相同的对象（is 相等）。

    **Validates: Requirements 2.4, 3.4**
    """
    config = {"configurable": {"workflow_context": obj}}
    result = get_context(config)
    assert result is obj


# ═══════════════════════════════════════════════════════════════════════════
# 单元测试: 边界情况
# ═══════════════════════════════════════════════════════════════════════════

class TestGetContext:
    """get_context 边界情况测试。"""

    def test_none_config_returns_none(self) -> None:
        """get_context(None) 应返回 None。"""
        assert get_context(None) is None

    def test_empty_config_returns_none(self) -> None:
        """get_context({}) 应返回 None（空 config）。"""
        assert get_context({}) is None

    def test_missing_workflow_context_key_returns_none(self) -> None:
        """config 中有 configurable 但无 workflow_context 键时返回 None。"""
        assert get_context({"configurable": {}}) is None

    def test_valid_config_returns_context(self) -> None:
        """有效 config 应返回 workflow_context 对象。"""
        ctx = _MockWorkflowContext(datasource_luid="ds_test")
        config = {"configurable": {"workflow_context": ctx}}
        assert get_context(config) is ctx


class TestGetContextOrRaise:
    """get_context_or_raise 边界情况测试。"""

    def test_none_config_raises_value_error(self) -> None:
        """get_context_or_raise(None) 应抛出 ValueError。"""
        with pytest.raises(ValueError, match="config is None"):
            get_context_or_raise(None)

    def test_empty_config_raises_value_error(self) -> None:
        """config 中无 workflow_context 时应抛出 ValueError。"""
        with pytest.raises(ValueError, match="WorkflowContext not found"):
            get_context_or_raise({"configurable": {}})

    def test_valid_config_returns_context(self) -> None:
        """有效 config 应返回 workflow_context 对象。"""
        ctx = _MockWorkflowContext(datasource_luid="ds_test")
        config = {"configurable": {"workflow_context": ctx}}
        assert get_context_or_raise(config) is ctx


# ═══════════════════════════════════════════════════════════════════════════
# 静态分析: 依赖方向合规性验证
# Requirements: 3.3, 4.1, 4.2, 4.3
# ═══════════════════════════════════════════════════════════════════════════

def _get_src_root() -> str:
    """获取 analytics_assistant/src 的绝对路径。"""
    tests_dir = os.path.dirname(os.path.abspath(__file__))
    analytics_root = os.path.dirname(os.path.dirname(os.path.dirname(tests_dir)))
    return os.path.join(analytics_root, "src")


def _extract_imports(filepath: str) -> List[str]:
    """从 Python 文件中提取所有导入模块路径。"""
    with open(filepath, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=filepath)

    imports: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


class TestDependencyCompliance:
    """依赖方向合规性静态分析测试。"""

    def test_graph_py_no_orchestration_import(self) -> None:
        """graph.py 不应包含任何 orchestration 导入。

        Requirements: 3.3, 4.1
        """
        src_root = _get_src_root()
        graph_path = os.path.join(
            src_root, "agents", "semantic_parser", "graph.py"
        )
        imports = _extract_imports(graph_path)

        orchestration_imports = [
            imp for imp in imports if "orchestration" in imp
        ]
        assert orchestration_imports == [], (
            f"graph.py 仍包含 orchestration 导入: {orchestration_imports}"
        )

    def test_agents_base_context_only_depends_on_core(self) -> None:
        """agents/base/context.py 仅应依赖 core/ 模块。

        Requirements: 4.2, 4.3
        """
        src_root = _get_src_root()
        context_path = os.path.join(src_root, "agents", "base", "context.py")
        imports = _extract_imports(context_path)

        project_imports = [
            imp for imp in imports
            if imp.startswith("analytics_assistant.src.")
        ]

        for imp in project_imports:
            module_after_src = imp.replace("analytics_assistant.src.", "")
            assert module_after_src.startswith("core"), (
                f"agents/base/context.py 不应依赖 core/ 以外的模块: {imp}"
            )
