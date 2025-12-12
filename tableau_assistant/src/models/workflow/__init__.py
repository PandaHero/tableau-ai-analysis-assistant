"""
Workflow models - LangGraph state and context definitions

Contains:
- state.py: VizQLState, VizQLInput, VizQLOutput
- context.py: VizQLContext runtime context

Note: TableauAuthContext 已移至 bi_platforms.tableau.auth 模块
"""

from .state import (
    VizQLState,
    VizQLInput,
    VizQLOutput,
    create_initial_state,
)

from .context import VizQLContext

# 为了向后兼容，从 bi_platforms.tableau 重新导出认证相关类
from tableau_assistant.src.bi_platforms.tableau import (
    TableauAuthContext,
    TableauAuthError,
    get_tableau_auth,
    get_tableau_auth_async,
    get_auth_from_config,
    create_config_with_auth,
    ensure_valid_auth,
    ensure_valid_auth_async,
)

__all__ = [
    # State
    "VizQLState",
    "VizQLInput",
    "VizQLOutput",
    "create_initial_state",
    # Context
    "VizQLContext",
    # Tableau auth (re-exported from bi_platforms.tableau)
    "TableauAuthContext",
    "TableauAuthError",
    "get_tableau_auth",
    "get_tableau_auth_async",
    "get_auth_from_config",
    "create_config_with_auth",
    "ensure_valid_auth",
    "ensure_valid_auth_async",
]
