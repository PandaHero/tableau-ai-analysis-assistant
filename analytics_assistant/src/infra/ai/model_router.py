# -*- coding: utf-8 -*-
"""
TaskRouter - 任务路由器

职责：根据任务类型选择最优模型

从 ModelManager 拆分出来，专注于任务路由逻辑。
"""
import logging
from typing import Optional

from .models import ModelConfig, ModelType, ModelStatus, TaskType
from .model_registry import ModelRegistry

logger = logging.getLogger(__name__)


class TaskRouter:
    """任务路由器
    
    职责：根据任务类型选择最优模型
    
    路由策略：
    1. 查找适合该任务的活跃模型
    2. 按优先级排序
    3. 返回优先级最高的模型
    4. 如果没有适合的模型，降级到默认模型
    """
    
    def __init__(self, registry: ModelRegistry):
        """初始化路由器
        
        Args:
            registry: 模型注册表
        """
        self._registry = registry
    
    def route(
        self,
        task_type: TaskType,
        model_type: ModelType = ModelType.LLM,
    ) -> Optional[ModelConfig]:
        """根据任务类型路由到最优模型
        
        Args:
            task_type: 任务类型
            model_type: 模型类型（默认 LLM）
        
        Returns:
            最优模型配置，没有可用模型返回 None
        """
        # 获取适合该任务的活跃模型
        suitable_models = []
        for config in self._registry.list(
            model_type=model_type, 
            status=ModelStatus.ACTIVE
        ):
            if task_type in config.suitable_tasks:
                suitable_models.append(config)
        
        if not suitable_models:
            # 降级到默认模型
            logger.debug(f"没有适合任务 {task_type.value} 的模型，使用默认模型")
            return self._registry.get_default(model_type)
        
        # 按优先级排序（优先级越大越优先）
        suitable_models.sort(key=lambda m: m.priority, reverse=True)
        
        selected = suitable_models[0]
        logger.debug(f"任务 {task_type.value} 路由到模型: {selected.id}")
        return selected
    
    def get_suitable_models(
        self,
        task_type: TaskType,
        model_type: ModelType = ModelType.LLM,
    ) -> list[ModelConfig]:
        """获取适合指定任务的所有模型
        
        Args:
            task_type: 任务类型
            model_type: 模型类型
        
        Returns:
            适合的模型列表（按优先级排序）
        """
        suitable_models = []
        for config in self._registry.list(
            model_type=model_type, 
            status=ModelStatus.ACTIVE
        ):
            if task_type in config.suitable_tasks:
                suitable_models.append(config)
        
        suitable_models.sort(key=lambda m: m.priority, reverse=True)
        return suitable_models


__all__ = ["TaskRouter"]
