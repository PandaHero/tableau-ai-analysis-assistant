"""
Agent 基础工具模块（重构版）

提供所有 Agent 节点共用的基础能力：
1. LLM 获取和配置（通过 ModelManager）
2. 工具调用处理（Tool Calls）
3. JSON 解析和清理
4. 流式输出支持

设计原则：
- 提供工具函数，不强制继承
- 每个 Agent 自己定义 Prompt 和处理逻辑
- 通过 ModelManager 统一管理 LLM

重构说明：
- get_llm() 现在调用 ModelManager.create_llm()
- 保持 Agent 层的便捷接口（agent_name 自动选择 temperature）
- 支持任务类型路由（task_type 参数）

使用示例：

    from analytics_assistant.src.agents.base import (
        get_llm,
        get_agent_temperature,
        call_llm_with_tools,
        parse_json_response,
        stream_llm_call,
    )
    
    # 在 Agent 节点中使用
    async def my_agent_node(state, config):
        # 方式 1：使用 agent_name 自动选择 temperature
        llm = get_llm(agent_name="semantic_parser")  # temperature=0.1
        
        # 方式 2：使用任务类型路由（自动选择最优模型）
        llm = get_llm(task_type=TaskType.SEMANTIC_PARSING)
        
        # 方式 3：直接指定 temperature
        llm = get_llm(temperature=0.1)
        
        tools = [my_tool_1, my_tool_2]
        messages = MY_PROMPT.format_messages(...)
        
        # 带工具调用
        response = await call_llm_with_tools(llm, messages, tools)
        result = parse_json_response(response, MyOutputModel)
        
        # 流式输出（无工具）
        response = await stream_llm_call(llm, messages)
        result = parse_json_response(response, MyOutputModel)
"""
import logging
from typing import Optional

from langchain_core.language_models import BaseChatModel

# 导入 ModelManager（使用相对导入）
from ...infra.ai import get_model_manager, TaskType

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Agent Temperature 配置（Agent 层配置，不放在 model_manager）
# ═══════════════════════════════════════════════════════════════════════════

AGENT_TEMPERATURE_CONFIG = {
    "semantic_parser": 0.1,     # 需要精确理解用户意图
    "dimension_hierarchy": 0.1, # 需要精确推断层级关系
    "field_mapper": 0.1,        # 需要精确的字段映射
    "insight": 0.4,             # 需要创造性发现洞察
    "replanner": 0.2,           # 需要判断是否重规划
    "default": 0.2,
}


def get_agent_temperature(agent_name: str) -> float:
    """获取指定 Agent 的默认 temperature"""
    return AGENT_TEMPERATURE_CONFIG.get(
        agent_name.lower(),
        AGENT_TEMPERATURE_CONFIG["default"]
    )


def get_llm(
    agent_name: Optional[str] = None,
    temperature: Optional[float] = None,
    enable_json_mode: bool = False,
    task_type: Optional[TaskType] = None,
    model_id: Optional[str] = None,
    **kwargs
) -> BaseChatModel:
    """
    获取 LLM 实例（Agent 层封装）
    
    这是 Agent 层的便捷函数，支持通过 agent_name 自动选择 temperature。
    底层调用 ModelManager.create_llm()。
    
    Args:
        agent_name: Agent 名称（可选，用于自动选择 temperature）
        temperature: 温度参数（可选，覆盖 agent_name 配置）
        enable_json_mode: 是否启用 JSON Mode
        task_type: 任务类型（可选，用于智能路由）
        model_id: 模型 ID（可选，显式指定模型）
        **kwargs: 传递给 ModelManager.create_llm() 的其他参数
    
    Returns:
        配置好的 LLM 实例
    
    Examples:
        # 使用 agent 对应的 temperature
        llm = get_llm(agent_name="semantic_parser")  # temperature=0.1
        
        # 启用 JSON Mode
        llm = get_llm(agent_name="semantic_parser", enable_json_mode=True)
        
        # 显式指定 temperature（覆盖 agent_name）
        llm = get_llm(agent_name="semantic_parser", temperature=0.3)
        
        # 使用任务类型路由（自动选择最优模型）
        llm = get_llm(task_type=TaskType.SEMANTIC_PARSING)
        
        # 显式指定模型
        llm = get_llm(model_id="deepseek-reasoner", temperature=0.7)
    """
    # Temperature 优先级：显式参数 > agent_name 配置
    if temperature is not None:
        _temperature = temperature
    elif agent_name:
        _temperature = get_agent_temperature(agent_name)
    else:
        _temperature = None  # 使用 ModelManager 的默认值
    
    # 获取 ModelManager 实例
    manager = get_model_manager()
    
    # 调用 ModelManager.create_llm()
    return manager.create_llm(
        model_id=model_id,
        task_type=task_type,
        temperature=_temperature,
        enable_json_mode=enable_json_mode,
        **kwargs
    )


# ═══════════════════════════════════════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════════════════════════════════════

__all__ = [
    # LLM 获取
    "get_llm",
    "get_agent_temperature",
    "AGENT_TEMPERATURE_CONFIG",
    "TaskType",  # 导出 TaskType 供 Agent 使用
]
