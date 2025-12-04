"""
模型配置（向后兼容）

此模块已迁移到 tableau_assistant.src.model_manager.config
保留此文件以保持向后兼容性。

推荐使用：
    from tableau_assistant.src.model_manager import AgentType, ModelConfig
"""

# 从新位置导入并重新导出
from tableau_assistant.src.model_manager.config import AgentType, ModelConfig

__all__ = [
    "AgentType",
    "ModelConfig",
]
