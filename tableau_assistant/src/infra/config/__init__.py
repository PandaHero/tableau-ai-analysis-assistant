"""
配置管理

提供应用配置的统一管理。

主要组件：
- settings: 应用配置（从 .env 读取）
- model_config: AI 模型配置
- feature_flags: vNext 灰度开关（Requirements 0.14）

使用示例：
    from tableau_assistant.src.infra.config import settings, feature_flags
    
    # 访问配置
    api_base = settings.llm_api_base
    temperature = settings.llm_temperature
    
    # 检查灰度开关
    if feature_flags.semantic_parser_vnext_enabled:
        # 使用 vNext 链路
        pass
"""

from tableau_assistant.src.infra.config.settings import settings, Settings, PROJECT_ROOT
from tableau_assistant.src.infra.config.feature_flags import (
    feature_flags,
    feature_flag_manager,
    FeatureFlags,
    SemanticParserVersion,
    FeatureFlagChangeLog,
    FeatureFlagManager,
)

__all__ = [
    "settings",
    "Settings",
    "PROJECT_ROOT",
    "feature_flags",
    "feature_flag_manager",
    "FeatureFlags",
    "SemanticParserVersion",
    "FeatureFlagChangeLog",
    "FeatureFlagManager",
]
