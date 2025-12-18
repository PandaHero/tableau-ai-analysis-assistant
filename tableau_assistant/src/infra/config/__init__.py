"""
配置管理

提供应用配置的统一管理。

主要组件：
- settings: 应用配置（从 .env 读取）
- model_config: AI 模型配置

使用示例：
    from tableau_assistant.src.infra.config import settings
    
    # 访问配置
    api_base = settings.llm_api_base
    temperature = settings.llm_temperature
"""

from tableau_assistant.src.infra.config.settings import settings, Settings, PROJECT_ROOT

__all__ = [
    "settings",
    "Settings",
    "PROJECT_ROOT",
]
