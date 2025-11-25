"""DeepAgent 上下文模型

定义运行时上下文，用于在 DeepAgent 和子代理间传递配置信息。

注意：
- 这是用于 DeepAgent 框架的上下文模型
- 与现有的 VizQLContext (context.py) 是并行的两套系统
- 用于渐进式迁移：先搭建 DeepAgent 框架，再逐步迁移功能
- 详见 README_MODELS.md
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass(frozen=True)  # 不可变
class DeepAgentContext:
    """运行时上下文（不可变配置）
    
    这个上下文在整个 Agent 生命周期中保持不变，包含所有配置信息。
    使用 frozen=True 确保线程安全和不可变性。
    """
    
    # === 必需配置 ===
    datasource_luid: str
    user_id: str
    thread_id: str
    tableau_token: str
    
    # === 可选配置 ===
    max_replan: int = 3
    enable_boost: bool = False
    enable_cache: bool = True
    model_config: Optional[Dict[str, Any]] = None
    
    # === 性能配置 ===
    timeout: int = 300  # 5分钟总超时
    max_tokens_per_call: int = 4000
    temperature: float = 0.0
    
    # === 缓存配置 ===
    cache_ttl: int = 3600  # 1小时
    enable_prompt_cache: bool = True
    enable_query_cache: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'datasource_luid': self.datasource_luid,
            'user_id': self.user_id,
            'thread_id': self.thread_id,
            'tableau_token': self.tableau_token,
            'max_replan': self.max_replan,
            'enable_boost': self.enable_boost,
            'enable_cache': self.enable_cache,
            'model_config': self.model_config,
            'timeout': self.timeout,
            'max_tokens_per_call': self.max_tokens_per_call,
            'temperature': self.temperature,
            'cache_ttl': self.cache_ttl,
            'enable_prompt_cache': self.enable_prompt_cache,
            'enable_query_cache': self.enable_query_cache,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DeepAgentContext':
        """从字典创建"""
        return cls(**data)
