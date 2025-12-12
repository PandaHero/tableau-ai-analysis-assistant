# -*- coding: utf-8 -*-
"""
Shared fixtures for workflow E2E tests.

Provides:
- executor: WorkflowExecutor instance
- printer: WorkflowPrinter instance  
- settings: Settings instance
- check_env: Environment validation fixture

Requirements: 1.1, 14.1
"""

import pytest
import pytest_asyncio
import os
from typing import Generator

from tableau_assistant.src.config.settings import Settings
from tableau_assistant.src.workflow.executor import WorkflowExecutor
from tableau_assistant.src.workflow.printer import WorkflowPrinter


# ============================================================
# Environment Check Fixture
# ============================================================

@pytest.fixture(scope="session")
def settings() -> Settings:
    """
    Load application settings.
    
    Returns:
        Settings instance with configuration from .env
    """
    return Settings()


@pytest.fixture(scope="session")
def check_env(settings: Settings) -> None:
    """
    Validate required environment variables.
    
    Skips tests if required configuration is missing.
    
    Required:
        - TABLEAU_DOMAIN: Tableau server domain
        - LLM_API_KEY: LLM API key
        - DATASOURCE_LUID: Data source LUID
        - TOOLING_LLM_MODEL: LLM model name
    """
    required = {
        "TABLEAU_DOMAIN": settings.tableau_domain,
        "LLM_API_KEY": settings.llm_api_key,
        "DATASOURCE_LUID": settings.datasource_luid,
        "TOOLING_LLM_MODEL": settings.tooling_llm_model,
    }
    
    missing = [k for k, v in required.items() if not v]
    
    if missing:
        pytest.skip(f"缺少环境配置: {', '.join(missing)}")


# ============================================================
# Workflow Executor Fixture
# ============================================================

@pytest.fixture(scope="module")
def executor() -> WorkflowExecutor:
    """
    Create WorkflowExecutor instance.
    
    Uses memory checkpointer for test isolation.
    Max replan rounds set to 3 for testing.
    
    Returns:
        Configured WorkflowExecutor instance
    """
    return WorkflowExecutor(
        max_replan_rounds=3,
        use_memory_checkpointer=True,
    )


@pytest.fixture(scope="function")
def fresh_executor() -> WorkflowExecutor:
    """
    Create a fresh WorkflowExecutor for each test.
    
    Use this when test isolation is critical.
    
    Returns:
        New WorkflowExecutor instance
    """
    return WorkflowExecutor(
        max_replan_rounds=3,
        use_memory_checkpointer=True,
    )


# ============================================================
# Workflow Printer Fixture
# ============================================================

@pytest.fixture(scope="module")
def printer() -> WorkflowPrinter:
    """
    Create WorkflowPrinter instance.
    
    Configured for verbose output with token streaming.
    
    Returns:
        Configured WorkflowPrinter instance
    """
    return WorkflowPrinter(verbose=True, show_tokens=True)


@pytest.fixture(scope="module")
def quiet_printer() -> WorkflowPrinter:
    """
    Create quiet WorkflowPrinter instance.
    
    Minimal output for batch testing.
    
    Returns:
        WorkflowPrinter with verbose=False
    """
    return WorkflowPrinter(verbose=False, show_tokens=False)


# ============================================================
# SQLite Checkpointer Fixture (for persistence tests)
# ============================================================

@pytest.fixture(scope="function")
def sqlite_executor(tmp_path) -> WorkflowExecutor:
    """
    Create WorkflowExecutor with SQLite checkpointer.
    
    Uses temporary directory for test isolation.
    
    Args:
        tmp_path: pytest temporary directory fixture
        
    Returns:
        WorkflowExecutor with SQLite persistence
    """
    from tableau_assistant.src.workflow.factory import create_tableau_workflow
    
    db_path = str(tmp_path / "test_workflow.db")
    
    # Create workflow with SQLite checkpointer
    workflow = create_tableau_workflow(
        use_memory_checkpointer=False,
        use_sqlite_checkpointer=True,
        sqlite_db_path=db_path,
        config={"max_replan_rounds": 3}
    )
    
    # Create executor wrapper
    executor = WorkflowExecutor(
        max_replan_rounds=3,
        use_memory_checkpointer=False,
    )
    executor._workflow = workflow
    
    return executor


# ============================================================
# Test Data Fixtures
# ============================================================

@pytest.fixture(scope="session")
def sample_questions() -> dict:
    """
    Sample questions for testing different scenarios.
    
    Returns:
        Dictionary of question categories with sample questions
    """
    return {
        # Simple aggregation
        "sum": "各地区销售额是多少",
        "avg": "各产品类别的平均利润是多少",
        "count": "各地区有多少订单",
        
        # COUNTD
        "countd_customer": "各地区有多少不同的客户",
        "countd_product": "各类别有多少种不同的产品",
        
        # LOD expressions
        "fixed_lod": "每个客户的首次购买日期是什么",
        "include_lod": "每个地区每个客户的平均订单金额",
        "exclude_lod": "不考虑产品类别的地区平均销售额",
        
        # Table calculations
        "running_sum": "按月份显示累计销售额",
        "rank": "各产品销售额排名",
        "moving_avg": "销售额的3个月移动平均",
        "yoy": "各地区销售额同比增长率",
        "mom": "各月销售额环比增长",
        "percent_total": "各产品类别销售额占比",
        
        # Date filters
        "absolute_year": "2024年各地区销售额",
        "absolute_month": "2024年3月的销售情况",
        "relative_current_month": "本月销售额是多少",
        "relative_last_month": "上个月各地区销售额",
        "relative_ytd": "今年至今的销售总额",
        
        # Multi-dimension
        "two_dim": "各地区各产品类别的销售额",
        "multi_measure": "各地区的销售额和利润",
        
        # Non-analysis
        "greeting": "你好",
        "help": "你能做什么",
        "bye": "再见",
        
        # Drilldown scenarios
        "geo_drilldown": "分析各地区销售情况",
        "time_drilldown": "分析各年度销售趋势",
        "product_drilldown": "分析各产品类别销售情况",
    }


@pytest.fixture(scope="session")
def dimension_hierarchy(settings: Settings) -> dict:
    """
    Get real dimension hierarchy from Tableau datasource cache.
    
    This fixture retrieves the actual dimension hierarchy from the
    StoreManager cache, which is populated by the dimension_hierarchy_agent
    when analyzing the datasource.
    
    Returns:
        Dictionary containing real dimension hierarchy from datasource,
        or empty dict if not available.
    """
    try:
        from tableau_assistant.src.capabilities.storage.store_manager import StoreManager
        
        # Get datasource LUID from settings
        datasource_luid = settings.datasource_luid
        if not datasource_luid:
            print("⚠️ DATASOURCE_LUID 未配置，无法获取真实维度层级")
            return {}
        
        # Get dimension hierarchy from cache
        store_manager = StoreManager()
        hierarchy = store_manager.get_dimension_hierarchy(datasource_luid)
        
        if hierarchy:
            # Filter out metadata fields like _cached_at
            filtered = {k: v for k, v in hierarchy.items() if not k.startswith("_")}
            print(f"✓ 从缓存加载真实维度层级: {len(filtered)} 个维度")
            return filtered
        else:
            print("⚠️ 缓存中没有维度层级，请先运行一次完整工作流以生成缓存")
            return {}
            
    except Exception as e:
        print(f"⚠️ 获取维度层级失败: {e}")
        return {}


@pytest.fixture(scope="session")
def real_metadata(settings: Settings):
    """
    Get real metadata from Tableau datasource cache.
    
    This fixture retrieves the actual field metadata from the
    StoreManager cache, providing real field names, types, and roles.
    
    Returns:
        Metadata object or None if not available.
    """
    try:
        from tableau_assistant.src.capabilities.storage.store_manager import StoreManager
        
        datasource_luid = settings.datasource_luid
        if not datasource_luid:
            print("⚠️ DATASOURCE_LUID 未配置，无法获取真实元数据")
            return None
        
        store_manager = StoreManager()
        metadata = store_manager.get_metadata(datasource_luid)
        
        if metadata:
            print(f"✓ 从缓存加载真实元数据: {len(metadata.get('fields', []))} 个字段")
            return metadata
        else:
            print("⚠️ 缓存中没有元数据")
            return None
            
    except Exception as e:
        print(f"⚠️ 获取元数据失败: {e}")
        return None


@pytest.fixture(scope="session")
def real_field_names(real_metadata) -> dict:
    """
    Extract real field names from metadata, grouped by role.
    
    Returns:
        Dictionary with 'dimensions' and 'measures' lists containing
        real field names from the datasource.
    """
    if not real_metadata:
        return {"dimensions": [], "measures": []}
    
    fields = real_metadata.get("fields", [])
    dimensions = []
    measures = []
    
    for field in fields:
        name = field.get("name", "")
        role = field.get("role", "").upper()
        
        if role == "DIMENSION":
            dimensions.append(name)
        elif role == "MEASURE":
            measures.append(name)
    
    print(f"✓ 真实字段: {len(dimensions)} 个维度, {len(measures)} 个度量")
    return {"dimensions": dimensions, "measures": measures}


# ============================================================
# Performance Timing Fixture
# ============================================================

@pytest.fixture(scope="function")
def timer():
    """
    Simple timer for performance tests.
    
    Returns:
        Timer context manager
    """
    import time
    
    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
            self.duration = None
        
        def __enter__(self):
            self.start_time = time.time()
            return self
        
        def __exit__(self, *args):
            self.end_time = time.time()
            self.duration = self.end_time - self.start_time
    
    return Timer


# ============================================================
# Async Event Loop Configuration
# ============================================================

@pytest.fixture(scope="session")
def event_loop_policy():
    """
    Configure event loop policy for Windows compatibility.
    """
    import sys
    if sys.platform == 'win32':
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
