# -*- coding: utf-8 -*-
"""工作流模块。

包级导出只保留轻量工具，避免在导入 `context` 时递归拉起 `executor`
并形成 `semantic_parser -> orchestration -> workflow -> executor -> semantic_parser`
的循环依赖。
"""

from .callbacks import SSECallbacks, get_processing_stage, get_stage_display_name
from .context import (
    WorkflowContext,
    create_workflow_config,
    get_context,
    get_context_or_raise,
)
__all__ = [
    "WorkflowContext",
    "create_workflow_config",
    "get_context",
    "get_context_or_raise",
    "SSECallbacks",
    "get_processing_stage",
    "get_stage_display_name",
]
