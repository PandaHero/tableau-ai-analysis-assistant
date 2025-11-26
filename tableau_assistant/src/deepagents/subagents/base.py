"""
Base SubAgent Class

提供所有子代理的统一基类，集成 ModelConfig 自动配置和 Prompt 系统。

设计原则：
- 统一的执行流程
- 自动的 Temperature 配置
- 复用现有的 Prompt 类系统
- 支持用户配置覆盖
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

from tableau_assistant.src.config.model_config import AgentType, ModelConfig

logger = logging.getLogger(__name__)


class BaseSubAgent(ABC):
    """
    子代理基类
    
    所有子代理都应继承此类并实现抽象方法。
    
    职责：
    - 提供统一的 execute() 方法
    - 自动获取最优 Temperature 配置
    - 集成现有的 Prompt 类系统
    - 支持用户配置覆盖
    
    使用方式：
        class MySubAgent(BaseSubAgent):
            def get_agent_type(self) -> AgentType:
                return AgentType.UNDERSTANDING
            
            def _prepare_input_data(self, **kwargs) -> Dict[str, Any]:
                return {"question": kwargs["question"]}
            
            def _process_result(self, result: Any) -> Dict[str, Any]:
                return {"understanding": result}
        
        agent = MySubAgent()
        result = await agent.execute(
            state=state,
            runtime=runtime,
            question="What is the sales trend?"
        )
    """
    
    def __init__(self):
        """初始化子代理"""
        self.agent_type = self.get_agent_type()
        self.default_config = ModelConfig.get_config_for_agent(self.agent_type)
        logger.info(
            f"{self.__class__.__name__} initialized with "
            f"temperature={self.default_config['temperature']}"
        )
    
    @abstractmethod
    def get_agent_type(self) -> AgentType:
        """
        返回 Agent 类型
        
        用于自动获取最优配置。
        
        Returns:
            AgentType 枚举值
        
        Examples:
            >>> def get_agent_type(self) -> AgentType:
            ...     return AgentType.UNDERSTANDING
        """
        pass
    
    @abstractmethod
    def _prepare_input_data(self, **kwargs) -> Dict[str, Any]:
        """
        准备输入数据
        
        将 execute() 接收的参数转换为 Prompt 所需的格式。
        
        Args:
            **kwargs: execute() 传入的参数
        
        Returns:
            Prompt 所需的输入数据字典
        
        Examples:
            >>> def _prepare_input_data(self, **kwargs) -> Dict[str, Any]:
            ...     return {
            ...         "question": kwargs["question"],
            ...         "metadata": kwargs["metadata"]
            ...     }
        """
        pass
    
    @abstractmethod
    def _process_result(self, result: Any) -> Dict[str, Any]:
        """
        处理 LLM 结果
        
        将 LLM 的原始输出转换为标准格式。
        
        Args:
            result: LLM 的原始输出
        
        Returns:
            处理后的结果字典
        
        Examples:
            >>> def _process_result(self, result: Any) -> Dict[str, Any]:
            ...     return {
            ...         "understanding": result,
            ...         "confidence": 0.95
            ...     }
        """
        pass
    
    async def execute(
        self,
        state: Dict[str, Any],
        runtime: Any,
        user_config: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行子代理
        
        统一的执行流程：
        1. 获取 Agent 默认配置（基于 agent_type）
        2. 合并用户配置（用户配置优先）
        3. 准备输入数据
        4. 执行 LLM 调用（使用最优配置）
        5. 处理结果
        
        Args:
            state: DeepAgent 状态
            runtime: DeepAgent 运行时
            user_config: 用户配置覆盖（可选）
            **kwargs: 子代理特定的参数
        
        Returns:
            处理后的结果字典
        
        Examples:
            >>> result = await agent.execute(
            ...     state=state,
            ...     runtime=runtime,
            ...     question="What is the sales trend?",
            ...     metadata=metadata
            ... )
            >>> print(result["understanding"])
        
        Note:
            - 默认配置基于 agent_type 自动获取
            - user_config 可以覆盖任何配置项
            - Temperature 等参数会自动应用
        """
        try:
            # 1. 获取默认配置
            config = self.default_config.copy()
            
            # 2. 合并用户配置
            if user_config:
                config = ModelConfig.merge_with_user_config(config, user_config)
                logger.debug(
                    f"User config applied: temperature={config['temperature']}"
                )
            
            # 3. 准备输入数据
            input_data = self._prepare_input_data(**kwargs)
            
            logger.info(
                f"Executing {self.__class__.__name__} with "
                f"temperature={config['temperature']}"
            )
            
            # 4. 执行 LLM 调用
            result = await self._execute_with_prompt(
                state=state,
                runtime=runtime,
                input_data=input_data,
                config=config
            )
            
            # 5. 处理结果
            processed_result = self._process_result(result)
            
            logger.info(f"✅ {self.__class__.__name__} completed successfully")
            
            return processed_result
            
        except Exception as e:
            error_msg = f"{self.__class__.__name__} execution failed: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    async def _execute_with_prompt(
        self,
        state: Dict[str, Any],
        runtime: Any,
        input_data: Dict[str, Any],
        config: Dict[str, Any]
    ) -> Any:
        """
        使用 Prompt 执行 LLM 调用
        
        复用现有的 Prompt 类系统。
        
        Args:
            state: DeepAgent 状态
            runtime: DeepAgent 运行时
            input_data: 准备好的输入数据
            config: 模型配置
        
        Returns:
            LLM 的原始输出
        
        Note:
            此方法应该被子类覆盖以使用特定的 Prompt 类。
            默认实现提供基本的 LLM 调用逻辑。
        """
        # 默认实现：直接调用 LLM
        # 子类应该覆盖此方法以使用特定的 Prompt 类
        
        # 这里是一个占位实现
        # 实际的子代理会使用现有的 Prompt 类（如 QuestionBoostPrompt）
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _execute_with_prompt()"
        )
    
    def get_config(self) -> Dict[str, Any]:
        """
        获取当前配置
        
        Returns:
            当前的模型配置
        """
        return self.default_config.copy()
    
    def get_temperature(self) -> float:
        """
        获取当前 Temperature
        
        Returns:
            Temperature 值
        """
        return self.default_config["temperature"]


# 导出
__all__ = ["BaseSubAgent"]
