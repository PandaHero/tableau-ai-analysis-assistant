# -*- coding: utf-8 -*-
"""
工作流执行器

封装工作流执行逻辑，提供简洁的对外接口。

使用示例:
    from tableau_assistant.src.workflow.executor import WorkflowExecutor
    
    executor = WorkflowExecutor()
    
    # 简单执行
    result = await executor.run("各产品类别的销售额是多少")
    print(result.semantic_query)
    print(result.query_result)
    
    # 流式执行
    async for event in executor.stream("各产品类别的销售额是多少"):
        if event.type == "token":
            print(event.content, end="", flush=True)
        elif event.type == "node_complete":
            print(f"\\n[{event.node_name}] 完成")
"""

import time
import uuid
import logging
from typing import Dict, Any, Optional, List, AsyncIterator
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field

from tableau_assistant.src.workflow.factory import create_tableau_workflow

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """事件类型"""
    NODE_START = "node_start"
    NODE_COMPLETE = "node_complete"
    TOKEN = "token"
    ERROR = "error"
    COMPLETE = "complete"


class WorkflowEvent(BaseModel):
    """工作流事件"""
    type: EventType
    node_name: Optional[str] = None
    content: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    timestamp: float = Field(default_factory=time.time)


@dataclass
class WorkflowResult:
    """工作流执行结果"""
    question: str
    success: bool
    duration: float
    
    # 各节点输出 (Pydantic 对象)
    semantic_query: Optional[Any] = None
    mapped_query: Optional[Any] = None
    vizql_query: Optional[Any] = None
    query_result: Optional[Any] = None
    insights: List[Any] = field(default_factory=list)
    replan_decision: Optional[Any] = None
    
    # 元信息
    is_analysis_question: bool = True
    replan_count: int = 0
    error: Optional[str] = None
    
    @classmethod
    def from_state(cls, question: str, state: Dict[str, Any], duration: float) -> "WorkflowResult":
        """从工作流状态创建结果"""
        return cls(
            question=question,
            success=state.get("errors") is None or len(state.get("errors", [])) == 0,
            duration=duration,
            semantic_query=state.get("semantic_query"),
            mapped_query=state.get("mapped_query"),
            vizql_query=state.get("vizql_query"),
            query_result=state.get("query_result"),
            insights=state.get("insights", []),
            replan_decision=state.get("replan_decision"),
            is_analysis_question=state.get("is_analysis_question", True),
            replan_count=state.get("replan_count", 0),
            error=state.get("errors", [{}])[0].get("error") if state.get("errors") else None,
        )


class WorkflowExecutor:
    """
    工作流执行器
    
    封装工作流执行逻辑，提供：
    1. run() - 简单执行，返回完整结果
    2. stream() - 流式执行，逐步返回事件
    """
    
    # 工作流节点列表
    NODES = ["understanding", "field_mapper", "query_builder", "execute", "insight", "replanner"]
    
    def __init__(
        self,
        max_replan_rounds: int = 2,
        use_memory_checkpointer: bool = True,
    ):
        """
        初始化执行器
        
        Args:
            max_replan_rounds: 最大重规划轮数
            use_memory_checkpointer: 是否使用内存检查点
        """
        self._workflow = create_tableau_workflow(
            use_memory_checkpointer=use_memory_checkpointer,
            config={"max_replan_rounds": max_replan_rounds}
        )
        self._max_replan_rounds = max_replan_rounds
    
    async def run(
        self,
        question: str,
        thread_id: Optional[str] = None,
    ) -> WorkflowResult:
        """
        执行工作流
        
        Args:
            question: 用户问题
            thread_id: 线程ID（可选，自动生成）
            
        Returns:
            WorkflowResult 包含所有节点输出
        """
        thread_id = thread_id or f"thread_{uuid.uuid4().hex[:8]}"
        
        start_time = time.time()
        
        try:
            state = {"question": question, "messages": []}
            config = {"configurable": {"thread_id": thread_id}}
            
            result = await self._workflow.ainvoke(state, config)
            
            duration = time.time() - start_time
            return WorkflowResult.from_state(question, result, duration)
            
        except Exception as e:
            logger.exception(f"Workflow execution failed: {e}")
            return WorkflowResult(
                question=question,
                success=False,
                duration=time.time() - start_time,
                error=str(e),
            )
    
    async def stream(
        self,
        question: str,
        thread_id: Optional[str] = None,
    ) -> AsyncIterator[WorkflowEvent]:
        """
        流式执行工作流
        
        Args:
            question: 用户问题
            thread_id: 线程ID（可选，自动生成）
            
        Yields:
            WorkflowEvent 事件流
        """
        thread_id = thread_id or f"thread_{uuid.uuid4().hex[:8]}"
        
        try:
            state = {"question": question, "messages": []}
            config = {"configurable": {"thread_id": thread_id}}
            
            current_node = None
            
            async for event in self._workflow.astream_events(state, config, version="v2"):
                event_type = event.get("event")
                event_name = event.get("name", "")
                event_data = event.get("data", {})
                
                # 节点开始
                if event_type == "on_chain_start" and event_name in self.NODES:
                    current_node = event_name
                    yield WorkflowEvent(
                        type=EventType.NODE_START,
                        node_name=event_name,
                    )
                
                # Token 流式输出
                elif event_type == "on_chat_model_stream":
                    chunk = event_data.get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        yield WorkflowEvent(
                            type=EventType.TOKEN,
                            node_name=current_node,
                            content=chunk.content,
                        )
                
                # 节点完成
                elif event_type == "on_chain_end" and event_name in self.NODES:
                    output = event_data.get("output", {})
                    yield WorkflowEvent(
                        type=EventType.NODE_COMPLETE,
                        node_name=event_name,
                        data=output,
                    )
                    current_node = None
                
                # 错误
                elif event_type == "on_chain_error":
                    yield WorkflowEvent(
                        type=EventType.ERROR,
                        node_name=current_node,
                        content=str(event_data.get("error", "未知错误")),
                    )
            
            # 完成
            yield WorkflowEvent(type=EventType.COMPLETE)
            
        except Exception as e:
            logger.exception(f"Workflow streaming failed: {e}")
            yield WorkflowEvent(
                type=EventType.ERROR,
                content=str(e),
            )
