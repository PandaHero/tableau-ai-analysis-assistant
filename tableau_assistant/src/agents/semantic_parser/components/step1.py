"""Step 1 Component - Semantic understanding and question restatement.

Step 1 is the "Intuition" phase of the LLM combination architecture.

使用 call_llm_with_tools 模式：
- call_llm_with_tools(): 支持工具调用 + 中间件 + 流式输出
- parse_json_response(): 解析 JSON 响应
- 不使用 with_structured_output（对某些模型不可靠）

关键：
- 使用 call_llm_with_tools(streaming=True) 支持 token 流式输出
- 传入中间件（从 config 获取）支持重试、摘要等功能
- 当前不需要工具（元数据通过 state 传递）
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ....core.models import Step1Output
from ..prompts.step1 import STEP1_PROMPT
from tableau_assistant.src.agents.base import (
    get_llm,
    call_llm_with_tools,
    parse_json_response,
)

logger = logging.getLogger(__name__)


class Step1Component:
    """Step 1: Semantic understanding and question restatement.
    
    Responsibilities:
    - Understand user question
    - Merge with conversation history
    - Extract What/Where/How structure
    - Classify intent
    - Generate complete restatement
    """
    
    def __init__(self, llm=None):
        """Initialize Step 1 component.
        
        Args:
            llm: LangChain LLM instance (lazy loaded if None)
        """
        self._llm = llm
    
    def _get_llm(self):
        """Get or create LLM instance."""
        if self._llm is None:
            self._llm = get_llm(agent_name="semantic_parser")
        return self._llm
    
    async def execute(
        self,
        question: str,
        history: list[dict[str, str]] | None = None,
        metadata: dict[str, Any] | None = None,
        state: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Step1Output:
        """Execute Step 1: Semantic understanding and question restatement.
        
        Args:
            question: Current user question
            history: Conversation history (list of {"role": "user/assistant", "content": "..."})
            metadata: Data source metadata (available fields, etc.)
            state: Current workflow state (for middleware)
            config: LangGraph RunnableConfig (contains middleware)
            
        Returns:
            Step1Output with restated_question, what, where, how_type, intent
        """
        # Format history for prompt
        history_str = self._format_history(history)
        
        # Format metadata for prompt
        metadata_str = self._format_metadata(metadata)
        
        # Get current time for date-related questions
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Use STEP1_PROMPT to format messages (auto-injects JSON Schema)
        messages = STEP1_PROMPT.format_messages(
            question=question,
            history=history_str,
            metadata=metadata_str,
            current_time=current_time,
        )
        
        # Get middleware from config
        middleware = None
        if config and "configurable" in config:
            middleware = config["configurable"].get("middleware")
        
        # Call LLM using call_llm_with_tools (supports middleware + streaming)
        # - tools=[]: No tools needed, metadata is passed via state
        # - streaming=True: Enable token streaming for frontend
        # - middleware: Apply retry, summarization, etc.
        llm = self._get_llm()
        response = await call_llm_with_tools(
            llm=llm,
            messages=messages,
            tools=[],  # No tools needed
            streaming=True,
            middleware=middleware,
            state=state or {},
            config=config,
        )
        
        # Parse JSON response
        result = parse_json_response(response, Step1Output)
        return result
    
    def _format_history(self, history: list[dict[str, str]] | None) -> str:
        """Format conversation history for prompt.
        
        注意：不在这里限制历史消息数量。
        历史消息的管理由 SummarizationMiddleware 负责：
        - 当 token 超过阈值时自动摘要
        - 保留最近 N 条消息（由 messages_to_keep 配置）
        """
        if not history:
            return "(No previous conversation)"
        
        formatted = []
        for msg in history:  # 不限制数量，由 SummarizationMiddleware 管理
            role = msg.get("role", "user")
            content = msg.get("content", "")
            formatted.append(f"[{role}]: {content}")
        
        return "\n".join(formatted)
    
    def _format_metadata(self, metadata: Any | None) -> str:
        """Format metadata for prompt.
        
        支持两种格式：
        1. Metadata Pydantic 对象（推荐）
        2. dict 格式（向后兼容）
        """
        if not metadata:
            return "(No metadata available)"
        
        # 处理 Pydantic Metadata 对象
        if hasattr(metadata, 'fields') and hasattr(metadata, 'get_dimensions'):
            # Metadata Pydantic 对象
            fields = metadata.fields
            if not fields:
                return "(No fields available)"
            
            dimensions = [
                f.fieldCaption or f.name
                for f in fields 
                if f.role == "dimension"
            ]
            measures = [
                f.fieldCaption or f.name
                for f in fields 
                if f.role == "measure"
            ]
        else:
            # dict 格式（向后兼容）
            fields = metadata.get("fields", []) if isinstance(metadata, dict) else []
            if not fields:
                return "(No fields available)"
            
            # Format as simple list - check both 'role' and 'type' for compatibility
            dimensions = [
                f.get("name") or f.get("fieldCaption", "")
                for f in fields 
                if (f.get("role", "").upper() == "DIMENSION" or f.get("type") == "dimension")
            ]
            measures = [
                f.get("name") or f.get("fieldCaption", "")
                for f in fields 
                if (f.get("role", "").upper() == "MEASURE" or f.get("type") == "measure")
            ]
        
        result = []
        if dimensions:
            # 不硬编码限制字段数量
            # 如果字段过多导致 prompt 过长，由 SummarizationMiddleware 处理
            # 或者在 settings 中配置 max_fields_in_prompt
            result.append(f"维度字段: {', '.join(dimensions)}")
        if measures:
            result.append(f"度量字段: {', '.join(measures)}")
        
        return "\n".join(result) if result else "(No fields available)"
