"""
SemanticParser 内部状态定义

定义 SemanticParserState，用于 SemanticParser 子图内部使用。
该状态继承 VizQLState，并添加 SemanticParser 特有的字段。

架构（金字塔结构）：
- VizQLState（编排层）：包含所有节点输出的工作流状态
- SemanticParserState（代理层）：继承 VizQLState，添加子图内部字段：
  - step1_output: Step1Output（意图 + what/where/how）
  - step2_output: Step2Output（计算逻辑）
  - pipeline_success: 管道执行是否成功
  - needs_clarification: 是否需要用户澄清
  - pipeline_aborted: 管道是否被中止
  - retry_history: 重试历史记录

LangGraph 节点路由循环：
- retry_from: 从哪个步骤重试（由 react_error_handler_node 设置）
- error_feedback: 传递给重试步骤的反馈信息
- react_action: ReAct 动作类型（RETRY/CLARIFY/ABORT）
- pipeline_error: 管道执行错误
- retry_count: 已重试次数

为什么要分离？
- VizQLState 包含所有节点可见的最终输出
- SemanticParserState 添加仅在子图内部使用的字段
- 这允许子图节点传递中间数据而不污染主状态
"""
from typing import Any, Dict, List, Optional

# 从编排层导入（正确的依赖方向）
from ...orchestration.workflow.state import VizQLState
from .models import Step1Output, Step2Output
from .models.pipeline import QueryError
from .models.react import ReActActionType


class SemanticParserState(VizQLState):
    """
    SemanticParser 子图内部状态。
    
    继承 VizQLState，添加子图中间输出：
    - step1_output: Step1Output（意图 + what/where/how）
    - step2_output: Step2Output（计算逻辑）
    - pipeline_success: 管道执行是否成功
    - needs_clarification: 是否需要用户澄清
    - pipeline_aborted: 管道是否被中止
    - retry_history: 重试历史记录
    
    LangGraph 节点路由循环字段：
    - retry_from: 从哪个步骤重试（由 react_error_handler_node 设置）
    - error_feedback: 传递给重试步骤的反馈信息
    - react_action: ReAct 动作类型（CORRECT/RETRY/CLARIFY/ABORT）
    - pipeline_error: 管道执行错误
    - retry_count: 已重试次数
    
    使用者：
    - step1_node: 写入 step1_output
    - step2_node: 读取 step1_output，写入 step2_output
    - pipeline_node: 读取 step1/step2 输出，写入管道结果
    - react_error_handler_node: 分析错误，设置 retry_from/error_feedback
    - SemanticParser 子图: 使用完整的 SemanticParserState
    
    注意：
    - VizQLState 包含扁平化字段（intent_type, semantic_query 等）
    - 这些字段仅用于子图内部通信
    """
    
    # SemanticParser 子图中间输出
    step1_output: Optional[Step1Output]  # Step1 输出（意图 + what/where/how）
    step2_output: Optional[Step2Output]  # Step2 输出（计算逻辑）
    
    # 管道执行状态
    pipeline_success: Optional[bool]  # 管道是否成功
    needs_clarification: Optional[bool]  # 是否需要澄清
    pipeline_aborted: Optional[bool]  # 管道是否被中止
    
    # ReAct 错误处理 - LangGraph 节点路由循环
    retry_from: Optional[str]  # 从哪个步骤重试（step1, step2, map_fields, build_query）
    error_feedback: Optional[str]  # 传递给重试步骤的反馈
    react_action: Optional[ReActActionType]  # ReAct 动作类型（CORRECT/RETRY/CLARIFY/ABORT）
    pipeline_error: Optional[QueryError]  # 管道执行错误
    retry_count: Optional[int]  # 已重试次数
    retry_history: Optional[List[Dict[str, Any]]]  # 重试历史记录（RetryRecord 字典列表）
    
    # 面向用户的消息（来自 ReAct）
    clarification_question: Optional[str]  # 向用户提问（CLARIFY）
    user_message: Optional[str]  # 显示给用户的消息（ABORT）
    
    # 管道输出（成功时）
    columns: Optional[List[Dict[str, Any]]]  # 列元数据
    row_count: Optional[int]  # 返回的行数
    file_path: Optional[str]  # 大结果文件路径
    is_large_result: Optional[bool]  # 结果是否保存到文件
    mapped_query: Optional[Dict[str, Any]]  # 映射后的查询
    vizql_query: Optional[Dict[str, Any]]  # VizQL 查询
    execution_time_ms: Optional[int]  # 执行时间（毫秒）
    
    # 思考过程（来自 R1 模型）
    thinking: Optional[str]  # R1 模型思考过程
    
    # 上下文字段（从工作流传递）
    datasource_luid: Optional[str]  # 用于查询执行的数据源 LUID


__all__ = ["SemanticParserState"]
