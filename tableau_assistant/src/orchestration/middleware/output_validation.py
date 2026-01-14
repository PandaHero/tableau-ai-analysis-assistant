"""
OutputValidationMiddleware - LLM 输出校验中间件

在 after_model 钩子中校验 LLM 输出是否符合预期的 Pydantic Schema。
在 after_agent 钩子中校验最终状态是否包含必需字段。

Features:
- JSON 格式校验
- Pydantic Schema 校验
- 错误记录和报告
- 可配置的校验策略（strict/lenient）

Design Principle (Requirements 0.6):
- This middleware is a FINAL QUALITY GATE, not a retry trigger
- Format errors (JSON parse, Pydantic validation) are handled by component-level retry
- Semantic errors are handled by ReAct
- This middleware only logs and alerts, does NOT trigger retries by default

Error Classification:
| Error Type | Handler | Retry Location |
|------------|---------|----------------|
| Format error (JSON/Pydantic) | Component | Step1/Step2 internal |
| Semantic error (field not found) | ReAct | Agent level |
| Final validation (fallback) | This middleware | Log + Alert only |

Requirements:
- R15.1: 校验输出是否为有效 JSON
- R15.2: 使用 Pydantic Schema 校验
- R15.3: strict=True 时抛出异常
- R15.4: strict=False 时记录警告（默认行为）
- R15.5: retry_on_failure=True 时抛出异常触发重试（非默认）
- R15.6: 校验必需状态字段
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, ValidationError
from langchain.agents.middleware.types import ModelResponse, ModelRequest, AgentState
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


class OutputValidationError(Exception):
    """
    输出校验错误
    
    当 retry_on_failure=True 且校验失败时抛出，
    用于触发 ModelRetryMiddleware 重试。
    """
    
    def __init__(self, message: str, validation_errors: Optional[List[Dict[str, Any]]] = None):
        self.validation_errors = validation_errors or []
        super().__init__(message)


# 尝试导入 LangChain AgentMiddleware
try:
    from langchain.agents.middleware import AgentMiddleware
    LANGCHAIN_MIDDLEWARE_AVAILABLE = True
except ImportError:
    # 如果 LangChain middleware 不可用，创建一个基类
    class AgentMiddleware:
        """AgentMiddleware 基类（本地定义）"""
        pass
    LANGCHAIN_MIDDLEWARE_AVAILABLE = False


class OutputValidationMiddleware(AgentMiddleware):
    """
    输出校验中间件 - 最终质量闸门
    
    在 after_model 钩子中校验 LLM 输出是否符合预期的 Pydantic Schema。
    在 after_agent 钩子中校验最终状态是否包含必需字段。
    
    Design Principle (Requirements 0.6):
    - This is a FINAL QUALITY GATE, not a retry trigger
    - Format errors should be handled by component-level retry (Step1/Step2)
    - Semantic errors should be handled by ReAct
    - This middleware only logs and alerts by default
    
    Attributes:
        expected_schema: 期望的输出 Pydantic 模型
        required_state_fields: 必需的状态字段列表
        strict: 严格模式，校验失败时抛出异常
        retry_on_failure: 校验失败时是否触发重试（默认 False，作为质量闸门）
    
    Example:
        >>> # Default: quality gate mode (log + alert only)
        >>> middleware = OutputValidationMiddleware(
        ...     expected_schema=SemanticQuery,
        ...     required_state_fields=["semantic_query", "is_analysis_question"],
        ... )
        >>> 
        >>> # Legacy: retry mode (not recommended, use component-level retry instead)
        >>> middleware = OutputValidationMiddleware(
        ...     expected_schema=SemanticQuery,
        ...     retry_on_failure=True,  # Explicitly enable retry
        ... )
    """
    
    def __init__(
        self,
        expected_schema: Optional[Type[BaseModel]] = None,
        required_state_fields: Optional[List[str]] = None,
        strict: bool = False,
        retry_on_failure: bool = False,  # Changed: default False (quality gate mode)
    ):
        """
        初始化 OutputValidationMiddleware
        
        Args:
            expected_schema: 期望的输出 Pydantic 模型（用于 after_model）
            required_state_fields: 必需的状态字段列表（用于 after_agent）
            strict: 严格模式，校验失败时抛出 ValueError
            retry_on_failure: 校验失败时是否抛出 OutputValidationError 触发重试
                             默认 False（质量闸门模式，只记录不重试）
                             设为 True 可与 ModelRetryMiddleware 配合使用（不推荐）
                             
        Note (Requirements 0.6):
            Format retry should be handled at component level (Step1/Step2).
            This middleware serves as a final quality gate for monitoring.
        """
        self.expected_schema = expected_schema
        self.required_state_fields = required_state_fields or []
        self.strict = strict
        self.retry_on_failure = retry_on_failure
    
    async def aafter_model(
        self,
        response: ModelResponse,
        request: ModelRequest,
        state: AgentState,
        runtime: Runtime,
    ) -> Optional[Dict[str, Any]]:
        """
        校验 LLM 输出
        
        检查：
        1. 输出是否为有效 JSON
        2. JSON 是否符合 expected_schema
        
        Args:
            response: LLM 响应
            request: 原始请求
            state: 当前状态
            runtime: 运行时上下文
        
        Returns:
            状态更新字典，包含 validated_output 或 validation_errors
        """
        if not self.expected_schema:
            return None
        
        # 检查响应是否为空
        if not response or not hasattr(response, 'result') or not response.result:
            logger.warning("OutputValidation: Empty response from LLM")
            return self._handle_error("Empty response", state)
        
        # 获取响应内容
        content = ""
        if isinstance(response.result, list) and len(response.result) > 0:
            first_result = response.result[0]
            if hasattr(first_result, 'content'):
                content = first_result.content
            elif isinstance(first_result, str):
                content = first_result
        elif hasattr(response.result, 'content'):
            content = response.result.content
        
        if not content:
            logger.warning("OutputValidation: No content in response")
            return self._handle_error("No content in response", state)
        
        # Step 1: 提取 JSON
        try:
            json_str = self._extract_json(content)
            parsed = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"OutputValidation: Invalid JSON - {e}")
            return self._handle_error(f"Invalid JSON: {e}", state)
        
        # Step 2: Pydantic 校验
        try:
            validated = self.expected_schema.model_validate(parsed)
            logger.debug(
                f"OutputValidation: Schema validation passed for "
                f"{self.expected_schema.__name__}"
            )
            return {"validated_output": validated}
        except ValidationError as e:
            logger.warning(f"OutputValidation: Schema validation failed - {e}")
            return self._handle_error(f"Schema validation failed: {e}", state)
    
    async def aafter_agent(
        self,
        state: AgentState,
        runtime: Runtime,
    ) -> Optional[Dict[str, Any]]:
        """
        校验最终状态
        
        检查：
        1. 必需字段是否存在
        2. 必需字段是否为 None
        
        Args:
            state: 当前状态
            runtime: 运行时上下文
        
        Returns:
            状态更新字典，如果有错误则包含 validation_errors
        """
        if not self.required_state_fields:
            return None
        
        missing_fields = []
        for field in self.required_state_fields:
            if field not in state or state.get(field) is None:
                missing_fields.append(field)
        
        if missing_fields:
            error_msg = f"Missing required fields: {missing_fields}"
            logger.warning(f"OutputValidation: {error_msg}")
            # after_agent 不触发重试，只记录错误
            return self._handle_error(error_msg, state, allow_retry=False)
        
        logger.debug("OutputValidation: All required state fields present")
        return None
    
    def _extract_json(self, content: str) -> str:
        """
        从内容中提取 JSON 字符串
        
        支持：
        - Markdown 代码块 ```json ... ```
        - 纯 JSON 对象 { ... }
        - 纯 JSON 数组 [ ... ]
        
        Args:
            content: LLM 输出内容
        
        Returns:
            提取的 JSON 字符串
        """
        # 尝试从 ```json ... ``` 中提取
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
        if match:
            return match.group(1).strip()
        
        # 尝试找到 { ... } 或 [ ... ]
        start_brace = content.find('{')
        start_bracket = content.find('[')
        
        if start_brace == -1 and start_bracket == -1:
            return content  # 返回原内容，让 json.loads 报错
        
        if start_brace == -1:
            start = start_bracket
        elif start_bracket == -1:
            start = start_brace
        else:
            start = min(start_brace, start_bracket)
        
        # 找到对应的结束符
        if content[start] == '{':
            end = content.rfind('}')
        else:
            end = content.rfind(']')
        
        if end == -1:
            return content[start:]
        
        return content[start:end + 1]
    
    def _handle_error(
        self,
        error_msg: str,
        state: AgentState,
        allow_retry: bool = True,
    ) -> Dict[str, Any]:
        """
        处理校验错误
        
        Args:
            error_msg: 错误消息
            state: 当前状态
            allow_retry: 是否允许触发重试
        
        Returns:
            状态更新字典
        
        Raises:
            ValueError: 如果 strict=True
            OutputValidationError: 如果 retry_on_failure=True 且 allow_retry=True
        """
        error_record = {
            "middleware": "OutputValidationMiddleware",
            "error": error_msg,
        }
        
        # 严格模式：直接抛出异常
        if self.strict:
            raise ValueError(f"OutputValidation failed: {error_msg}")
        
        # 重试模式：抛出 OutputValidationError 触发 ModelRetryMiddleware
        if self.retry_on_failure and allow_retry:
            raise OutputValidationError(
                f"OutputValidation failed: {error_msg}",
                validation_errors=[error_record],
            )
        
        # 宽松模式：记录错误到 state
        existing_errors = state.get("validation_errors", [])
        return {
            "validation_errors": existing_errors + [error_record]
        }


__all__ = [
    "OutputValidationMiddleware",
    "OutputValidationError",
]
