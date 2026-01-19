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
from tableau_assistant.src.orchestration.workflow.state import VizQLState
from tableau_assistant.src.agents.semantic_parser.models import Step1Output, Step2Output
from tableau_assistant.src.agents.semantic_parser.models.pipeline import QueryError
from tableau_assistant.src.agents.semantic_parser.models.react import ReActActionType



class SemanticParserState(VizQLState):
    """
    SemanticParser 子图内部状态。
    
    ⚠️ State 序列化原则（支持 checkpoint/持久化/回放）：
    - State 中只存可 JSON 化的基本类型或结构
    - 复杂对象（如 Pydantic BaseModel）在存入 State 前必须调用 .model_dump()
    - 从 State 读取后需要重新构造对象
    
    字段类型约定：
    - 基本类型：str, int, float, bool, None
    - 容器类型：list[基本类型], dict[str, 基本类型]
    - 嵌套结构：dict（已序列化的 Pydantic 对象）
    
    继承 VizQLState，添加子图中间输出：
    - step1_output: dict（Step1Output 序列化后）
    - step2_output: dict（Step2Output 序列化后）
    - pipeline_success: 管道执行是否成功
    - needs_clarification: 是否需要用户澄清
    - pipeline_aborted: 管道是否被中止
    - retry_history: 重试历史记录
    
    LangGraph 节点路由循环字段：
    - retry_from: 从哪个步骤重试（由 react_error_handler_node 设置）
    - error_feedback: 传递给重试步骤的反馈信息
    - react_action: str（ReActActionType.value，非枚举对象）
    - pipeline_error: dict（QueryError 序列化后）
    - retry_count: 已重试次数
    
    扁平化字段（供主工作流路由消费）：
    - intent_type: str（IntentType.value，非枚举对象）
    - is_analysis_question: bool
    
    使用者：
    - step1_node: 写入 step1_output（dict）
    - step2_node: 读取 step1_output，写入 step2_output（dict）
    - pipeline_node: 读取 step1/step2 输出，写入管道结果
    - react_error_handler_node: 分析错误，设置 retry_from/error_feedback
    - _flatten_output: 在子图出口处扁平化字段
    - SemanticParser 子图: 使用完整的 SemanticParserState
    
    注意：
    - VizQLState 包含扁平化字段（intent_type, semantic_query 等）
    - 这些字段仅用于子图内部通信
    """
    
    # SemanticParser 子图中间输出（存储为 dict，非 Pydantic 对象）
    # 写入时：state["step1_output"] = step1_output.model_dump()
    # 读取时：Step1Output.model_validate(state["step1_output"])
    preprocess_result: Optional[Dict[str, Any]]  # Preprocess 输出（规范化问题、时间上下文、记忆槽位）
    intent_router_output: Optional[Dict[str, Any]]  # IntentRouter 输出（意图识别结果）
    schema_candidates: Optional[Dict[str, Any]]  # Schema Linking 输出（候选字段集）
    step1_output: Optional[Dict[str, Any]]  # Step1 输出（意图 + what/where/how）
    step2_output: Optional[Dict[str, Any]]  # Step2 输出（计算逻辑）
    
    # Preprocess 输出的扁平化字段（供后续组件直接使用）
    canonical_question: Optional[str]  # 规范化问题（用于缓存 key）
    time_context: Optional[Dict[str, Any]]  # 时间上下文（TimeContext 序列化后）
    
    # 管道执行状态（基本类型）
    pipeline_success: Optional[bool]  # 管道是否成功
    needs_clarification: Optional[bool]  # 是否需要澄清
    pipeline_aborted: Optional[bool]  # 管道是否被中止
    is_metadata_question: Optional[bool]  # 是否为元数据问答（由 IntentRouter 设置）
    
    # ReAct 错误处理 - LangGraph 节点路由循环（基本类型）
    retry_from: Optional[str]  # 从哪个步骤重试（step1, step2, map_fields, build_query）
    error_feedback: Optional[str]  # 传递给重试步骤的反馈
    react_action: Optional[str]  # ReAct 动作类型值（CORRECT/RETRY/CLARIFY/ABORT）
    pipeline_error: Optional[Dict[str, Any]]  # 管道执行错误（QueryError 序列化后）
    retry_count: Optional[int]  # 已重试次数
    retry_history: Optional[List[Dict[str, Any]]]  # 重试历史记录（RetryRecord 字典列表）
    
    # 错误状态（基本类型）
    step1_parse_error: Optional[str]  # Step1 解析失败错误信息
    step2_parse_error: Optional[str]  # Step2 解析失败错误信息
    
    # 重试计数（基本类型）
    # ⚠️ 命名约定：parse_retry 表示格式解析重试，semantic_retry 表示语义重试
    parse_retry_count: Optional[int]  # 格式解析重试次数
    semantic_retry_count: Optional[int]  # 语义重试次数
    
    # 面向用户的消息（来自 ReAct）（基本类型）
    clarification_question: Optional[str]  # 向用户提问（CLARIFY）
    user_message: Optional[str]  # 显示给用户的消息（ABORT）
    
    # 管道输出（成功时）（基本类型）
    columns: Optional[List[Dict[str, Any]]]  # 列元数据
    row_count: Optional[int]  # 返回的行数
    file_path: Optional[str]  # 大结果文件路径
    is_large_result: Optional[bool]  # 结果是否保存到文件
    mapped_query: Optional[Dict[str, Any]]  # 映射后的查询
    vizql_query: Optional[Dict[str, Any]]  # VizQL 查询
    execution_time_ms: Optional[int]  # 执行时间（毫秒）
    
    # 思考过程（来自 R1 模型）（基本类型）
    thinking: Optional[str]  # R1 模型思考过程
    
    # 上下文字段（从工作流传递）（基本类型）
    datasource_luid: Optional[str]  # 用于查询执行的数据源 LUID


__all__ = ["SemanticParserState"]
