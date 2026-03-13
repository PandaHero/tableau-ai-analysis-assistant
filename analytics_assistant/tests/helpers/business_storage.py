# -*- coding: utf-8 -*-
"""业务存储测试辅助函数。"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from analytics_assistant.src.infra.business_storage import BusinessDatabase

_TEST_DB_DIR = Path("analytics_assistant/tests/test_outputs/business_storage")


def create_test_business_database(prefix: str) -> tuple[BusinessDatabase, Path]:
    """在仓库内创建独立测试数据库路径。"""
    _TEST_DB_DIR.mkdir(parents=True, exist_ok=True)
    db_path = _TEST_DB_DIR / f"{prefix}_{uuid4().hex}.db"
    if db_path.exists():
        db_path.unlink()
    return BusinessDatabase(str(db_path)), db_path
