# -*- coding: utf-8 -*-
"""
Semantic Parser Prompts Module

包含 Prompt 构建相关组件：
- TimeHintGenerator: 时间提示生成器
- DynamicPromptBuilder: 动态 Prompt 构建器（含计算种子插入功能）
- error_correction_prompt: 错误修正 Prompt
"""

from .time_hint_generator import TimeHintGenerator, TimeHint
from .prompt_builder import DynamicPromptBuilder, get_low_confidence_threshold
from .feature_extractor_prompt import (
    FEATURE_EXTRACTOR_SYSTEM_PROMPT,
    build_feature_extractor_prompt,
)
from .global_understanding_prompt import (
    GLOBAL_UNDERSTANDING_SYSTEM_PROMPT,
    build_global_understanding_prompt,
)
from .error_correction_prompt import (
    SYSTEM_PROMPT as ERROR_CORRECTION_SYSTEM_PROMPT,
    ERROR_TYPE_GUIDANCE,
    build_user_prompt as build_error_correction_prompt,
    get_system_prompt as get_error_correction_system_prompt,
)

# 关键词从 seeds 包导入
from ..seeds import COMPLEXITY_KEYWORDS

# 从 schemas 导入（保持向后兼容的导入路径）
from analytics_assistant.src.core.schemas.enums import HowType
from ..schemas.intermediate import FieldCandidate, FewShotExample
from ..schemas.config import SemanticConfig

__all__ = [
    # TimeHintGenerator
    "TimeHintGenerator",
    "TimeHint",
    # DynamicPromptBuilder
    "DynamicPromptBuilder",
    "get_low_confidence_threshold",
    # FeatureExtractor Prompt
    "FEATURE_EXTRACTOR_SYSTEM_PROMPT",
    "build_feature_extractor_prompt",
    # GlobalUnderstanding Prompt
    "GLOBAL_UNDERSTANDING_SYSTEM_PROMPT",
    "build_global_understanding_prompt",
    # Complexity keywords
    "COMPLEXITY_KEYWORDS",
    # Schemas (re-exported for convenience)
    "HowType",
    "FieldCandidate",
    "FewShotExample",
    "SemanticConfig",
    # ErrorCorrectionPrompt
    "ERROR_CORRECTION_SYSTEM_PROMPT",
    "ERROR_TYPE_GUIDANCE",
    "build_error_correction_prompt",
    "get_error_correction_system_prompt",
]
