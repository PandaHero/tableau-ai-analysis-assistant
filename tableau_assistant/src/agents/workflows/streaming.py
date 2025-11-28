"""
流式输出处理器

使用LangGraph 1.0的astream_events实现详细进度反馈
"""
from typing import AsyncIterator, Dict, Any, Optional
from enum import Enum
import json
import time


class EventType(str, Enum):
    """事件类型枚举"""
    # Token级流式输出
    TOKEN = "token"
    
    # Agent进度
    AGENT_START = "agent_start"
    AGENT_COMPLETE = "agent_complete"
    AGENT_ERROR = "agent_error"
    
    # 工具调用进度
    TOOL_START = "tool_start"
    TOOL_COMPLETE = "tool_complete"
    TOOL_ERROR = "tool_error"
    
    # 查询执行进度
    QUERY_START = "query_start"
    QUERY_COMPLETE = "query_complete"
    QUERY_ERROR = "query_error"
    
    # 整体进度
    WORKFLOW_START = "workflow_start"
    WORKFLOW_COMPLETE = "workflow_complete"
    WORKFLOW_ERROR = "workflow_error"
    
    # 其他
    PROGRESS = "progress"
    LOG = "log"


class StreamingEventHandler:
    """
    流式事件处理器
    
    将LangGraph的astream_events转换为前端友好的事件格式
    """
    
    def __init__(self):
        """初始化事件处理器"""
        self.start_time = time.time()
        self.agent_stack = []  # Agent调用栈
        self.tool_stack = []  # 工具调用栈
    
    async def process_events(
        self,
        event_stream: AsyncIterator[Dict[str, Any]]
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        处理astream_events并转换为前端事件
        
        为什么是异步的？
        - event_stream 是异步生成器，需要使用 async for 遍历
        - 每个事件的到达时间不确定，需要异步等待
        - 使用异步可以在等待事件时不阻塞其他操作
        
        Args:
            event_stream: LangGraph的astream_events生成器
        
        Yields:
            前端事件字典
        """
        try:
            # 处理astream_events
            async for event in event_stream:
                # 转换事件
                frontend_event = await self._convert_event(event)
                if frontend_event:
                    yield frontend_event
        
        except Exception as e:
            # 发送错误事件
            yield self._create_event(
                EventType.WORKFLOW_ERROR,
                {
                    "error": str(e),
                    "timestamp": time.time()
                }
            )
    
    async def _convert_event(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        转换LangGraph事件为前端事件
        
        Args:
            event: LangGraph事件
        
        Returns:
            前端事件字典，如果不需要转换返回None
        """
        event_type = event.get("event")
        event_name = event.get("name", "")
        event_data = event.get("data", {})
        
        # ========== Token级流式输出 ==========
        if event_type == "on_chat_model_stream":
            chunk = event_data.get("chunk")
            if chunk and hasattr(chunk, "content"):
                token = chunk.content
                if token:
                    return self._create_event(
                        EventType.TOKEN,
                        {
                            "token": token,
                            "agent": self.agent_stack[-1] if self.agent_stack else None
                        }
                    )
        
        # ========== Agent进度 ==========
        elif event_type == "on_chain_start":
            # 判断是否是Agent节点
            if self._is_agent_node(event_name):
                self.agent_stack.append(event_name)
                return self._create_event(
                    EventType.AGENT_START,
                    {
                        "agent": event_name,
                        "run_id": event.get("run_id"),
                        "timestamp": time.time()
                    }
                )
        
        elif event_type == "on_chain_end":
            if self._is_agent_node(event_name):
                if self.agent_stack and self.agent_stack[-1] == event_name:
                    self.agent_stack.pop()
                
                return self._create_event(
                    EventType.AGENT_COMPLETE,
                    {
                        "agent": event_name,
                        "run_id": event.get("run_id"),
                        "output": event_data.get("output"),
                        "timestamp": time.time()
                    }
                )
        
        elif event_type == "on_chain_error":
            if self._is_agent_node(event_name):
                if self.agent_stack and self.agent_stack[-1] == event_name:
                    self.agent_stack.pop()
                
                return self._create_event(
                    EventType.AGENT_ERROR,
                    {
                        "agent": event_name,
                        "error": str(event_data.get("error")),
                        "timestamp": time.time()
                    }
                )
        
        # ========== 工具调用进度 ==========
        elif event_type == "on_tool_start":
            self.tool_stack.append(event_name)
            return self._create_event(
                EventType.TOOL_START,
                {
                    "tool": event_name,
                    "input": event_data.get("input"),
                    "timestamp": time.time()
                }
            )
        
        elif event_type == "on_tool_end":
            if self.tool_stack and self.tool_stack[-1] == event_name:
                self.tool_stack.pop()
            
            return self._create_event(
                EventType.TOOL_COMPLETE,
                {
                    "tool": event_name,
                    "output": event_data.get("output"),
                    "timestamp": time.time()
                }
            )
        
        elif event_type == "on_tool_error":
            if self.tool_stack and self.tool_stack[-1] == event_name:
                self.tool_stack.pop()
            
            return self._create_event(
                EventType.TOOL_ERROR,
                {
                    "tool": event_name,
                    "error": str(event_data.get("error")),
                    "timestamp": time.time()
                }
            )
        
        return None
    
    def _is_agent_node(self, name: str) -> bool:
        """
        判断是否是Agent节点
        
        Args:
            name: 节点名称
        
        Returns:
            是否是Agent节点
        """
        # Agent节点通常包含"agent"关键字
        agent_keywords = ["agent", "understanding", "planner", "insight", "replanner", "summarizer"]
        name_lower = name.lower()
        return any(keyword in name_lower for keyword in agent_keywords)
    
    def _create_event(
        self,
        event_type: EventType,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        创建前端事件
        
        Args:
            event_type: 事件类型
            data: 事件数据
        
        Returns:
            前端事件字典
        """
        return {
            "type": event_type.value,
            "data": data,
            "timestamp": time.time()
        }


def format_sse_event(event: Dict[str, Any]) -> str:
    """
    格式化为SSE事件
    
    Args:
        event: 事件字典
    
    Returns:
        SSE格式的字符串
    """
    # SSE格式: data: {json}\n\n
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def stream_workflow_events(
    input_data: Dict[str, Any],
    datasource_luid: str,
    user_id: str = "default_user",
    session_id: str = "default_session",
    store = None
) -> AsyncIterator[str]:
    """
    流式输出工作流事件（SSE格式）
    
    这是推荐的使用方式，结合了 workflow 和 event handler
    
    为什么是异步的？
    - 需要等待 LLM 生成每个 token（I/O 密集型）
    - 使用异步可以高效处理多个并发请求
    - SSE 本身就是异步流式协议
    
    Args:
        input_data: 输入数据
        datasource_luid: 数据源LUID
        user_id: 用户ID
        session_id: 会话ID
        store: 可选的Store实例
    
    Yields:
        SSE格式的事件字符串
    """
    from tableau_assistant.src.agents.workflows.vizql_workflow import run_vizql_workflow_stream
    
    handler = StreamingEventHandler()
    
    # 发送工作流开始事件
    yield format_sse_event(handler._create_event(
        EventType.WORKFLOW_START,
        {
            "question": input_data.get("question"),
            "timestamp": time.time()
        }
    ))
    
    try:
        # 获取 workflow 的事件流
        event_stream = run_vizql_workflow_stream(
            input_data=input_data,
            datasource_luid=datasource_luid,
            user_id=user_id,
            session_id=session_id,
            store=store
        )
        
        # 处理并转换事件
        async for event in handler.process_events(event_stream):
            yield format_sse_event(event)
        
        # 发送工作流完成事件
        yield format_sse_event(handler._create_event(
            EventType.WORKFLOW_COMPLETE,
            {
                "duration": time.time() - handler.start_time,
                "timestamp": time.time()
            }
        ))
    
    except Exception as e:
        # 发送错误事件
        yield format_sse_event(handler._create_event(
            EventType.WORKFLOW_ERROR,
            {
                "error": str(e),
                "timestamp": time.time()
            }
        ))


# 示例用法
if __name__ == "__main__":
    import asyncio
    from tableau_assistant.src.workflows.example_workflow import create_example_workflow
    
    async def test_streaming():
        """测试流式输出"""
        # 创建工作流
        app = create_example_workflow()
        
        # 准备输入
        input_data = {
            "question": "2016年各地区的销售额",
            "boost_question": False
        }
        
        config = {
            "configurable": {
                "thread_id": "test_session",
                "datasource_luid": "test_ds",
                "user_id": "test_user",
                "session_id": "test_session",
                "max_replan_rounds": 2,
                "parallel_upper_limit": 3,
                "max_retry_times": 2,
                "max_subtasks_per_round": 10
            }
        }
        
        # 流式输出
        print("=" * 60)
        print("测试流式输出")
        print("=" * 60)
        
        async for sse_event in stream_workflow_events(app, input_data, config):
            print(sse_event, end="")
    
    # 运行测试
    asyncio.run(test_streaming())
