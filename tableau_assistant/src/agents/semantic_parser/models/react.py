"""ReAct models - ReAct 错误处理相关模型。

定义 ReAct 错误处理流程中使用的数据模型：
- ReActThought: 思考过程
- ReActAction: 动作决策
- ReActObservation: 观察结果
- ReActOutput: 完整输出
"""

from typing import Any, Dict, List, Optional
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class ReActActionType(str, Enum):
    """ReAct 动作类型"""
    RETRY = "retry"           # 使用修正参数重试工具
    CLARIFY = "clarify"       # 返回澄清问题给用户
    ABORT = "abort"           # 放弃并返回友好错误信息


class ReActThought(BaseModel):
    """ReAct 思考过程
    
    分析错误原因并决定下一步动作。
    """
    model_config = ConfigDict(extra="forbid")
    
    error_analysis: str = Field(
        description="错误原因分析"
    )
    
    possible_causes: List[str] = Field(
        default_factory=list,
        description="可能的原因列表"
    )
    
    can_fix: bool = Field(
        description="是否可以通过修正参数修复"
    )
    
    fix_strategy: Optional[str] = Field(
        default=None,
        description="修复策略（如果 can_fix=True）"
    )
    
    reasoning: str = Field(
        description="决策推理过程"
    )


class ReActAction(BaseModel):
    """ReAct 动作决策
    
    基于思考结果决定执行的动作。
    """
    model_config = ConfigDict(extra="forbid")
    
    action_type: ReActActionType = Field(
        description="动作类型"
    )
    
    # RETRY 动作的参数
    retry_tool: Optional[str] = Field(
        default=None,
        description="要重试的工具名称 (map_fields, build_query, execute_query)"
    )
    
    retry_params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="修正后的工具参数"
    )
    
    # CLARIFY 动作的参数
    clarification_question: Optional[str] = Field(
        default=None,
        description="要问用户的澄清问题"
    )
    
    clarification_options: Optional[List[str]] = Field(
        default=None,
        description="澄清问题的选项"
    )
    
    # ABORT 动作的参数
    abort_message: Optional[str] = Field(
        default=None,
        description="友好的错误信息"
    )
    
    abort_suggestion: Optional[str] = Field(
        default=None,
        description="给用户的建议"
    )


class ReActObservation(BaseModel):
    """ReAct 观察结果
    
    工具执行后的观察结果。
    """
    model_config = ConfigDict(extra="forbid")
    
    tool_name: str = Field(
        description="执行的工具名称"
    )
    
    success: bool = Field(
        description="工具是否执行成功"
    )
    
    result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="工具返回结果（成功时）"
    )
    
    error_type: Optional[str] = Field(
        default=None,
        description="错误类型（失败时）"
    )
    
    error_message: Optional[str] = Field(
        default=None,
        description="错误信息（失败时）"
    )
    
    retry_count: int = Field(
        default=0,
        description="当前重试次数"
    )


class ReActOutput(BaseModel):
    """ReAct 完整输出
    
    包含思考、动作和最终结果。
    """
    model_config = ConfigDict(extra="forbid")
    
    thought: ReActThought = Field(
        description="思考过程"
    )
    
    action: ReActAction = Field(
        description="动作决策"
    )
    
    # 执行结果
    final_success: bool = Field(
        default=False,
        description="最终是否成功"
    )
    
    final_result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="最终结果（成功时）"
    )
    
    # 历史记录（用于多轮 ReAct）
    observation_history: List[ReActObservation] = Field(
        default_factory=list,
        description="观察历史记录"
    )
    
    total_retries: int = Field(
        default=0,
        description="总重试次数"
    )


__all__ = [
    "ReActThought",
    "ReActAction",
    "ReActActionType",
    "ReActObservation",
    "ReActOutput",
]
