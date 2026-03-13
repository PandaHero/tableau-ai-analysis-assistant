# -*- coding: utf-8 -*-
"""测试全局钩子。"""

from __future__ import annotations

import os
from pathlib import Path


def pytest_configure() -> None:
    """规避 Windows 环境下 pytest 临时目录清理的权限问题。"""
    import _pytest.pathlib
    import _pytest.tmpdir

    pytest_root = Path(__file__).resolve().parent / "test_outputs" / "pytest_root"
    pytest_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PYTEST_DEBUG_TEMPROOT", str(pytest_root))

    def _skip_cleanup_dead_symlinks(_root) -> None:
        return None

    _pytest.pathlib.cleanup_dead_symlinks = _skip_cleanup_dead_symlinks
    _pytest.tmpdir.cleanup_dead_symlinks = _skip_cleanup_dead_symlinks
