"""
Model Configuration for Different Agents

Defines optimal temperature and sampling settings for each agent type.
Based on Google Prompt Engineering best practices.

Temperature Strategy:
- 0.0: Deterministic (greedy decoding) - for tasks with single correct answer
- 0.1: Consistent - for tasks needing stable interpretation with flexibility
- 0.2: Balanced - for general purpose tasks with some flexibility
- 0.3: Balanced+ - for tasks needing understanding + moderate creativity
- 0.7: Creative - for tasks requiring diverse perspectives and insights

Agent Type Mapping:
- FIELD_MAPPING (0.0): Exact field matching, no creativity needed
- TASK_PLANNER (0.0): Deterministic task decomposition, avoid random planning
- UNDERSTANDING (0.1): Consistent question interpretation, allow minor variations
- BOOST (0.3): Question enhancement, balance original intent + expansion
- REPLANNER (0.2): Error analysis and replanning, stable with flexibility
- INSIGHT (0.7): Creative analysis, diverse perspectives, novel connections
"""
from typing import Dict, Any, Optional
from enum import Enum


class AgentType(str, Enum):
    """Agent types with different model configuration needs"""
    
    # Deterministic tasks (need consistency)
    FIELD_MAPPING = "field_mapping"
    UNDERSTANDING = "understanding"
    TASK_PLANNER = "task_planner"
    
    # Creative tasks (need diversity)
    INSIGHT = "insight"
    BOOST = "boost"
    
    # Balanced tasks
    REPLANNER = "replanner"


class ModelConfig:
    """
    Model configuration presets for different agent types
    
    Based on Google Prompt Engineering whitepaper recommendations:
    - Deterministic tasks: temperature=0.0 (greedy decoding)
    - Consistent tasks: temperature=0.1-0.3
    - Creative tasks: temperature=0.7-0.9
    """
    
    # Deterministic configuration (for tasks with single correct answer)
    DETERMINISTIC = {
        "temperature": 0.0,
        "top_p": 0.9,
        "top_k": 20,
        "max_output_tokens": 1024
    }
    
    # Deterministic Large configuration (for complex planning tasks)
    DETERMINISTIC_LARGE = {
        "temperature": 0.0,
        "top_p": 0.9,
        "top_k": 20,
        "max_output_tokens": 3000  # Larger output for complex query plans
    }
    
    # Consistent configuration (for tasks needing consistency but some flexibility)
    CONSISTENT = {
        "temperature": 0.1,
        "top_p": 0.95,
        "top_k": 30,
        "max_output_tokens": 2048
    }
    
    # Balanced configuration (for general tasks)
    BALANCED = {
        "temperature": 0.2,
        "top_p": 0.95,
        "top_k": 30,
        "max_output_tokens": 2048
    }
    
    # Balanced+ configuration (for tasks needing balance with slight creativity)
    BALANCED_PLUS = {
        "temperature": 0.3,
        "top_p": 0.95,
        "top_k": 35,
        "max_output_tokens": 2048
    }
    
    # Creative configuration (for tasks needing diversity and creativity)
    CREATIVE = {
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 3072
    }
    
    @classmethod
    def get_config_for_agent(cls, agent_type: AgentType) -> Dict[str, Any]:
        """
        Get optimal model configuration for specific agent type
        
        Args:
            agent_type: Type of agent
        
        Returns:
            Model configuration dictionary
        
        Examples:
            >>> config = ModelConfig.get_config_for_agent(AgentType.FIELD_MAPPING)
            >>> config["temperature"]
            0.0
        """
        config_map = {
            # Deterministic agents (need exact, consistent answers)
            # - temperature=0.0 for greedy decoding
            # - Used for tasks with single correct answer
            AgentType.FIELD_MAPPING: cls.DETERMINISTIC,
            AgentType.TASK_PLANNER: cls.DETERMINISTIC_LARGE,  # Needs larger output for complex plans
            
            # Consistent agents (need consistency but some interpretation)
            # - temperature=0.1 for stable but flexible interpretation
            # - Used for tasks needing consistent understanding
            AgentType.UNDERSTANDING: cls.CONSISTENT,
            
            # Creative agents (need diversity and insights)
            # - temperature=0.7 for diverse and creative outputs
            # - Used for tasks requiring novel perspectives
            AgentType.INSIGHT: cls.CREATIVE,
            
            # Balanced+ agents (need balance with creativity)
            # - temperature=0.3 for understanding + moderate expansion
            # - Used for tasks like question enhancement
            AgentType.BOOST: cls.BALANCED_PLUS,  # Changed from BALANCED to BALANCED_PLUS
            
            # Balanced agents (general purpose)
            # - temperature=0.2 for stable analysis with some flexibility
            # - Used for tasks like error analysis and replanning
            AgentType.REPLANNER: cls.BALANCED,
        }
        
        return config_map.get(agent_type, cls.BALANCED).copy()
    
    @classmethod
    def get_config_for_field_mapping(cls) -> Dict[str, Any]:
        """
        Get configuration for field mapping (deterministic)
        
        Field mapping requires:
        - Exact matches (temperature=0.0)
        - Consistent results
        - No creativity needed
        
        Returns:
            Deterministic configuration
        """
        return cls.DETERMINISTIC.copy()
    
    @classmethod
    def get_config_for_insight_generation(cls) -> Dict[str, Any]:
        """
        Get configuration for insight generation (creative)
        
        Insight generation requires:
        - Creative analysis (temperature=0.7)
        - Diverse perspectives
        - Novel connections
        
        Returns:
            Creative configuration
        """
        return cls.CREATIVE.copy()
    
    @classmethod
    def get_config_for_understanding(cls) -> Dict[str, Any]:
        """
        Get configuration for question understanding (consistent)
        
        Question understanding requires:
        - Consistent interpretation (temperature=0.1)
        - Some flexibility for ambiguous questions
        - Structured output
        
        Returns:
            Consistent configuration
        """
        return cls.CONSISTENT.copy()
    
    @classmethod
    def merge_with_user_config(
        cls,
        base_config: Dict[str, Any],
        user_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Merge base configuration with user-provided overrides
        
        Args:
            base_config: Base configuration from presets
            user_config: User-provided configuration overrides
        
        Returns:
            Merged configuration
        
        Examples:
            >>> base = ModelConfig.DETERMINISTIC
            >>> user = {"temperature": 0.1}
            >>> merged = ModelConfig.merge_with_user_config(base, user)
            >>> merged["temperature"]
            0.1
        """
        if user_config is None:
            return base_config
        
        merged = base_config.copy()
        merged.update(user_config)
        return merged


# ============= 导出 =============

__all__ = [
    "AgentType",
    "ModelConfig",
]
