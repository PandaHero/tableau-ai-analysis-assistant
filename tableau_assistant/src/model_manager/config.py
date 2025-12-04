"""
模型配置

定义不同 Agent 类型的最优温度和采样设置。
基于 Google Prompt Engineering 最佳实践。

温度策略：
- 0.0: 确定性（贪婪解码）- 用于有单一正确答案的任务
- 0.1: 一致性 - 用于需要稳定解释但有灵活性的任务
- 0.2: 平衡 - 用于通用任务
- 0.3: 平衡+ - 用于需要理解+适度创造力的任务
- 0.7: 创造性 - 用于需要多样化视角和洞察的任务
"""
from typing import Dict, Any, Optional
from enum import Enum


class AgentType(str, Enum):
    """Agent 类型，对应不同的模型配置需求"""
    
    # 确定性任务（需要一致性）
    FIELD_MAPPING = "field_mapping"
    UNDERSTANDING = "understanding"
    TASK_PLANNER = "task_planner"
    
    # 创造性任务（需要多样性）
    INSIGHT = "insight"
    BOOST = "boost"
    
    # 平衡任务
    REPLANNER = "replanner"


class ModelConfig:
    """
    模型配置预设
    
    基于 Google Prompt Engineering 白皮书建议：
    - 确定性任务: temperature=0.0（贪婪解码）
    - 一致性任务: temperature=0.1-0.3
    - 创造性任务: temperature=0.7-0.9
    """
    
    # 确定性配置（用于有单一正确答案的任务）
    DETERMINISTIC = {
        "temperature": 0.0,
        "top_p": 0.9,
        "top_k": 20,
        "max_output_tokens": 1024
    }
    
    # 确定性大输出配置（用于复杂规划任务）
    DETERMINISTIC_LARGE = {
        "temperature": 0.0,
        "top_p": 0.9,
        "top_k": 20,
        "max_output_tokens": 3000
    }
    
    # 一致性配置（用于需要一致性但有灵活性的任务）
    CONSISTENT = {
        "temperature": 0.1,
        "top_p": 0.95,
        "top_k": 30,
        "max_output_tokens": 2048
    }
    
    # 平衡配置（用于通用任务）
    BALANCED = {
        "temperature": 0.2,
        "top_p": 0.95,
        "top_k": 30,
        "max_output_tokens": 2048
    }
    
    # 平衡+配置（用于需要平衡和轻微创造力的任务）
    BALANCED_PLUS = {
        "temperature": 0.3,
        "top_p": 0.95,
        "top_k": 35,
        "max_output_tokens": 2048
    }
    
    # 创造性配置（用于需要多样性和创造力的任务）
    CREATIVE = {
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 3072
    }
    
    @classmethod
    def get_config_for_agent(cls, agent_type: AgentType) -> Dict[str, Any]:
        """
        获取特定 Agent 类型的最优模型配置
        
        Args:
            agent_type: Agent 类型
        
        Returns:
            模型配置字典
        """
        config_map = {
            AgentType.FIELD_MAPPING: cls.DETERMINISTIC,
            AgentType.TASK_PLANNER: cls.DETERMINISTIC_LARGE,
            AgentType.UNDERSTANDING: cls.CONSISTENT,
            AgentType.INSIGHT: cls.CREATIVE,
            AgentType.BOOST: cls.BALANCED_PLUS,
            AgentType.REPLANNER: cls.BALANCED,
        }
        
        return config_map.get(agent_type, cls.BALANCED).copy()
    
    @classmethod
    def get_config_for_field_mapping(cls) -> Dict[str, Any]:
        """获取字段映射配置（确定性）"""
        return cls.DETERMINISTIC.copy()
    
    @classmethod
    def get_config_for_insight_generation(cls) -> Dict[str, Any]:
        """获取洞察生成配置（创造性）"""
        return cls.CREATIVE.copy()
    
    @classmethod
    def get_config_for_understanding(cls) -> Dict[str, Any]:
        """获取问题理解配置（一致性）"""
        return cls.CONSISTENT.copy()
    
    @classmethod
    def merge_with_user_config(
        cls,
        base_config: Dict[str, Any],
        user_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        合并基础配置和用户配置
        
        Args:
            base_config: 基础配置
            user_config: 用户配置覆盖
        
        Returns:
            合并后的配置
        """
        if user_config is None:
            return base_config
        
        merged = base_config.copy()
        merged.update(user_config)
        return merged


__all__ = [
    "AgentType",
    "ModelConfig",
]
