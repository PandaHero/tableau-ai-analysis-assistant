# -*- coding: utf-8 -*-
"""
Semantic Parser Prompts Module

包含 Prompt 构建相关组件：
- TimeHintGenerator: 时间提示生成器
- DynamicPromptBuilder: 动态 Prompt 构建器
- error_correction_prompt: 错误修正 Prompt
"""

from .time_hint_generator import TimeHintGenerator, TimeHint
from .prompt_builder import DynamicPromptBuilder
from .error_correction_prompt import (
    SYSTEM_PROMPT as ERROR_CORRECTION_SYSTEM_PROMPT,
    ERROR_TYPE_GUIDANCE,
    build_user_prompt as build_error_correction_prompt,
    get_system_prompt as get_error_correction_system_prompt,
)

# 关键词函数从 keywords_data.py 导入
from ..keywords_data import (
    get_derived_metric_keywords,
    get_time_calc_keywords,
    get_subquery_keywords,
    get_table_calc_keywords,
)

# 从 schemas 导入（保持向后兼容的导入路径）
from ..schemas.enums import PromptComplexity
from ..schemas.intermediate import FieldCandidate, FewShotExample
from ..schemas.config import SemanticConfig

__all__ = [
    # TimeHintGenerator
    "TimeHintGenerator",
    "TimeHint",
    # DynamicPromptBuilder
    "DynamicPromptBuilder",
    "get_derived_metric_keywords",
    "get_time_calc_keywords",
    "get_subquery_keywords",
    "get_table_calc_keywords",
    # Schemas (re-exported for convenience)
    "PromptComplexity",
    "FieldCandidate",
    "FewShotExample",
    "SemanticConfig",
    # ErrorCorrectionPrompt
    "ERROR_CORRECTION_SYSTEM_PROMPT",
    "ERROR_TYPE_GUIDANCE",
    "build_error_correction_prompt",
    "get_error_correction_system_prompt",
]
