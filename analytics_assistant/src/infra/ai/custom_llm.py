# -*- coding: utf-8 -*-
"""
自定义 LLM 实现

用于支持非标准 OpenAI 兼容 API（如自定义 endpoint）。

设计说明：
- ChatOpenAI 会自动在 base_url 后追加 /chat/completions
- 对于使用非标准端点的 API（如 /api/v1/offline/deep/think），需要自定义实现
- 本类继承 BaseChatModel，实现 _generate、_stream 和 _astream 方法
- 必须实现原生 _astream 以支持真正的 token 级别异步流式输出；
  若只有同步 _stream，LangChain 会通过线程池包装，导致 on_token 回调无法
  在流式过程中被触发（all tokens arrive at once）。
"""
import json
import logging
from typing import Any, AsyncIterator, Iterator, Optional

import httpx
from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

logger = logging.getLogger(__name__)

class CustomChatLLM(BaseChatModel):
    """
    自定义 Chat LLM
    
    支持非标准 OpenAI 兼容 API，如：
    - 自定义 endpoint（不追加 /chat/completions）
    - 自定义认证 header
    
    使用场景：
    - 公司内部部署的模型（如 DeepSeek R1）
    - 使用非标准端点的 API
    
    注意：
    - 只需实现 _generate 和 _stream 方法
    - LangChain 会自动基于这些方法提供 ainvoke、astream 等异步方法
    """
    
    # 必需参数
    api_base: str
    """API 完整 URL（直接调用，不会追加任何路径）"""
    
    model_name: str
    """模型名称"""
    
    api_key: str = ""
    """API Key"""
    
    auth_header: str = "apikey"
    """认证 header 名称（默认 apikey）"""
    
    # 可选参数
    temperature: float = 0.7
    """温度参数"""
    
    max_tokens: int = 4096
    """最大 token 数"""
    
    timeout: float = 120.0
    """请求超时时间（秒）"""
    
    verify_ssl: bool = True
    """是否验证 SSL 证书（默认启用，与 ModelConfig.verify_ssl 一致）"""
    
    is_reasoning_model: bool = False
    """是否是推理模型（输出包含思考过程）"""
    
    streaming: bool = True
    """是否启用流式输出（默认 True）"""
    
    response_format: Optional[dict[str, Any]] = None
    """响应格式配置（如 {"type": "json_object"} 或 {"type": "json_schema", "json_schema": {...}}）"""
    
    @property
    def _llm_type(self) -> str:
        return "custom_chat_llm"
    
    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "api_base": self.api_base,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
    
    def bind_tools(
        self,
        tools: list[Any],
        **kwargs: Any,
    ) -> "CustomChatLLM":
        """绑定工具（占位实现）
        
        CustomChatLLM 当前不支持原生工具调用（function calling）。
        返回自身以避免 NotImplementedError，上层代码会通过 Prompt 方式模拟工具调用。
        
        Args:
            tools: 工具列表
            **kwargs: 其他参数
            
        Returns:
            返回自身实例
        """
        logger.warning(
            f"CustomChatLLM 不支持原生工具调用，将通过 Prompt 方式模拟。"
            f"model={self.model_name}, tools_count={len(tools)}"
        )
        return self
    
    def _convert_messages(self, messages: list[BaseMessage]) -> list[dict[str, str]]:
        """将 LangChain 消息转换为 API 格式"""
        result = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                result.append({"role": "system", "content": msg.content})
            elif isinstance(msg, HumanMessage):
                result.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                result.append({"role": "assistant", "content": msg.content})
            else:
                result.append({"role": "user", "content": str(msg.content)})
        return result
    
    def _build_request(
        self,
        messages: list[BaseMessage],
        stream: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """构建请求体"""
        request = {
            "model": self.model_name,
            "messages": self._convert_messages(messages),
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "stream": stream,
        }
        
        # 添加 response_format（如果配置了）
        if self.response_format:
            request["response_format"] = self.response_format
        
        return request
    
    def _get_headers(self) -> dict[str, str]:
        """获取请求头"""
        return {
            "Content-Type": "application/json",
            self.auth_header: self.api_key,
        }
    
    def _parse_sse_line(self, line: str) -> Optional[dict[str, Any]]:
        """解析 SSE 行"""
        line = line.strip()
        if not line or line == "data: [DONE]":
            return None
        if line.startswith("data: "):
            try:
                return json.loads(line[6:])
            except json.JSONDecodeError:
                return None
        return None

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        同步生成（非流式）
        
        注意：此 API 总是返回流式响应，即使 stream=False。
        因此这里使用流式请求并收集所有内容。
        """
        # 使用流式请求收集完整响应
        content_parts = []
        for chunk in self._stream(messages, stop, run_manager, **kwargs):
            if chunk.message.content:
                content_parts.append(chunk.message.content)
        
        full_content = "".join(content_parts)
        message = AIMessage(content=full_content)
        generation = ChatGeneration(message=message)
        
        return ChatResult(generations=[generation])
    
    def _stream(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """
        同步流式生成
        
        LangChain 会基于此方法自动提供 astream() 异步版本。
        
        对于推理模型（R1）：
        - thinking 内容通过 additional_kwargs["thinking"] 实时传递
        - 上层 stream_llm_structured 负责累积完整的 thinking
        """
        payload = self._build_request(messages, stream=True, **kwargs)
        headers = self._get_headers()
        
        logger.debug(f"CustomChatLLM 流式请求: url={self.api_base}, model={self.model_name}")
        
        # 使用 httpx 进行流式请求
        with httpx.Client(verify=self.verify_ssl, timeout=self.timeout) as client:
            with client.stream(
                "POST",
                self.api_base,
                headers=headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                
                for line in response.iter_lines():
                    if not line:
                        continue
                    
                    data = self._parse_sse_line(line)
                    if not data:
                        continue
                    
                    # 解析 delta
                    try:
                        delta = data["choices"][0].get("delta", {})
                        delta_type = delta.get("type", "")
                        content = delta.get("content", "")
                        
                        # thinking 类型（推理过程）- 实时传递
                        if delta_type == "thinking":
                            if content:
                                chunk = ChatGenerationChunk(
                                    message=AIMessageChunk(
                                        content="",
                                        additional_kwargs={"thinking": content}
                                    )
                                )
                                yield chunk
                            continue
                        
                        # text 类型（正常内容）
                        if content:
                            chunk = ChatGenerationChunk(
                                message=AIMessageChunk(content=content)
                            )
                            if run_manager:
                                run_manager.on_llm_new_token(content)
                            yield chunk
                            
                    except (KeyError, IndexError):
                        continue

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """
        原生异步流式生成

        必须实现此方法以支持真正的 token 级别异步流：
        - 若只有同步 _stream，LangChain 会在线程池中运行它，
          导致 on_token（协程）无法在流式过程中被 await，
          所有 token 只能在 LLM 完成后一次性到达前端。
        - 本方法使用 httpx.AsyncClient 进行真正的异步 HTTP 流，
          每个 token 到达时立即 yield，on_token 回调可实时触发。

        对于推理模型（R1）：
        - thinking 内容通过 additional_kwargs["thinking"] 实时传递
        """
        payload = self._build_request(messages, stream=True, **kwargs)
        headers = self._get_headers()

        logger.debug(
            f"CustomChatLLM 异步流式请求: url={self.api_base}, model={self.model_name}"
        )

        async with httpx.AsyncClient(
            verify=self.verify_ssl, timeout=self.timeout
        ) as client:
            async with client.stream(
                "POST",
                self.api_base,
                headers=headers,
                json=payload,
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    data = self._parse_sse_line(line)
                    if not data:
                        continue

                    try:
                        delta = data["choices"][0].get("delta", {})
                        delta_type = delta.get("type", "")
                        content = delta.get("content", "")

                        # thinking 类型（推理过程）- 实时传递
                        if delta_type == "thinking":
                            if content:
                                chunk = ChatGenerationChunk(
                                    message=AIMessageChunk(
                                        content="",
                                        additional_kwargs={"thinking": content},
                                    )
                                )
                                yield chunk
                            continue

                        # text 类型（正常内容）
                        if content:
                            chunk = ChatGenerationChunk(
                                message=AIMessageChunk(content=content)
                            )
                            if run_manager:
                                await run_manager.on_llm_new_token(content)
                            yield chunk

                    except (KeyError, IndexError):
                        continue

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        原生异步非流式生成（通过 _astream 收集完整响应）
        """
        content_parts: list[str] = []
        async for chunk in self._astream(messages, stop, run_manager, **kwargs):
            if chunk.message.content:
                content_parts.append(str(chunk.message.content))

        full_content = "".join(content_parts)
        message = AIMessage(content=full_content)
        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])


__all__ = ["CustomChatLLM"]
