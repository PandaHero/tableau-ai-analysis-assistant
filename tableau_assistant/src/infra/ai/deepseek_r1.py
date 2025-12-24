# -*- coding: utf-8 -*-
"""
DeepSeek R1 推理模型客户端

公司内部部署的 DeepSeek R1 模型，支持思考过程输出。

特点：
- 自定义端点: /api/v1/offline/deep/think
- 使用 Apikey header 认证
- 思考过程在 <think>...</think> 标签内，自动提取到 additional_kwargs["thinking"]
- 支持流式输出
"""
import re
import json
import logging
from typing import Any, List, Optional, Iterator, AsyncIterator

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage, AIMessageChunk
from langchain_core.outputs import ChatResult, ChatGeneration, ChatGenerationChunk
from langchain_core.callbacks import CallbackManagerForLLMRun, AsyncCallbackManagerForLLMRun
from pydantic import Field

logger = logging.getLogger(__name__)


class DeepSeekR1Chat(BaseChatModel):
    """公司内部 DeepSeek R1 推理模型
    
    特点：
    - 自定义端点: /api/v1/offline/deep/think
    - 使用 Apikey header 认证
    - 思考过程在 <think>...</think> 标签内
    - 自动提取思考过程到 additional_kwargs["thinking"]
    - 支持流式输出
    """
    
    # 必需参数，无默认值
    api_base: str = Field(...)
    api_key: str = Field(...)
    model_name: str = Field(...)
    
    # 可选参数
    api_endpoint: str = Field(default="/api/v1/offline/deep/think")
    temperature: float = Field(default=0.2)
    max_tokens: int = Field(default=4096)
    timeout: float = Field(default=120.0)
    streaming: bool = Field(default=False)
    
    @property
    def _llm_type(self) -> str:
        return "deepseek-r1"
    
    def _convert_messages(self, messages: List[BaseMessage]) -> List[dict]:
        """转换 LangChain 消息为 API 格式"""
        result = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                result.append({
                    "role": "system",
                    "content": msg.content,
                    "model_name": "deepseek-r1"
                })
            elif isinstance(msg, HumanMessage):
                result.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                result.append({"role": "assistant", "content": msg.content})
        return result
    
    def _parse_response(self, content: str, is_streaming: bool = False) -> AIMessage:
        """解析响应，提取思考过程和最终回答
        
        Args:
            content: 原始响应内容
            is_streaming: 是否来自流式响应
            
        Returns:
            AIMessage with thinking in additional_kwargs
            - content: 最终答案（不含思考过程）
            - additional_kwargs["thinking"]: 思考过程
            - additional_kwargs["raw_content"]: 原始完整内容
        """
        thinking = ""
        answer = content
        
        # 非流式模式：提取 <think>...</think> 标签内容
        think_match = re.search(r'<think>(.*?)</think>', content, re.DOTALL)
        if think_match:
            thinking = think_match.group(1).strip()
            answer = re.sub(r'<think>.*?</think>\s*', '', content, flags=re.DOTALL).strip()
        elif is_streaming:
            # 流式模式：R1 API 不使用 <think> 标签
            # 尝试用空行分隔思考过程和最终答案
            parts = content.strip().split('\n\n')
            if len(parts) >= 2:
                # 最后一部分是答案，之前的是思考过程
                thinking = '\n\n'.join(parts[:-1]).strip()
                answer = parts[-1].strip()
            # 如果只有一部分，整个内容就是答案，没有思考过程
        
        return AIMessage(
            content=answer,
            additional_kwargs={
                "thinking": thinking,
                "raw_content": content,
                "answer": answer,  # 添加 answer 字段，方便 _stream_llm_call_internal 使用
            }
        )
    
    def _get_headers(self) -> dict:
        """获取请求头"""
        return {
            "Content-Type": "application/json",
            "Apikey": self.api_key,
        }
    
    def _get_payload(self, messages: List[BaseMessage], stream: bool = False) -> dict:
        """构建请求体"""
        return {
            "model": self.model_name,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": self._convert_messages(messages),
            "files_id": [],
            "stream": stream
        }
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """同步生成"""
        payload = self._get_payload(messages, stream=False)
        
        logger.debug(f"DeepSeek R1 请求: {self.api_base}{self.api_endpoint}")
        
        with httpx.Client(verify=False, timeout=self.timeout) as client:
            resp = client.post(
                f"{self.api_base}{self.api_endpoint}",
                json=payload,
                headers=self._get_headers()
            )
            resp.raise_for_status()
            data = resp.json()
        
        content = data["choices"][0]["message"]["content"]
        ai_message = self._parse_response(content)
        
        logger.debug(f"DeepSeek R1 响应: {ai_message.content[:100]}...")
        
        return ChatResult(
            generations=[ChatGeneration(message=ai_message)]
        )
    
    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """异步生成"""
        payload = self._get_payload(messages, stream=False)
        
        logger.debug(f"DeepSeek R1 异步请求: {self.api_base}{self.api_endpoint}")
        
        async with httpx.AsyncClient(verify=False, timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.api_base}{self.api_endpoint}",
                json=payload,
                headers=self._get_headers()
            )
            resp.raise_for_status()
            data = resp.json()
        
        content = data["choices"][0]["message"]["content"]
        ai_message = self._parse_response(content)
        
        logger.debug(f"DeepSeek R1 异步响应: {ai_message.content[:100]}...")
        
        return ChatResult(
            generations=[ChatGeneration(message=ai_message)]
        )
    
    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """同步流式生成"""
        payload = self._get_payload(messages, stream=True)
        
        logger.debug(f"DeepSeek R1 流式请求: {self.api_base}{self.api_endpoint}")
        
        full_content = ""
        
        with httpx.Client(verify=False, timeout=self.timeout) as client:
            with client.stream(
                "POST",
                f"{self.api_base}{self.api_endpoint}",
                json=payload,
                headers=self._get_headers()
            ) as resp:
                resp.raise_for_status()
                
                for line in resp.iter_lines():
                    if not line:
                        continue
                    
                    # SSE 格式: data: {...}
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        
                        try:
                            data = json.loads(data_str)
                            if "choices" in data and data["choices"]:
                                delta = data["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                
                                if content:
                                    full_content += content
                                    chunk = ChatGenerationChunk(
                                        message=AIMessageChunk(content=content)
                                    )
                                    if run_manager:
                                        run_manager.on_llm_new_token(content)
                                    yield chunk
                        except json.JSONDecodeError:
                            continue
        
        # 最后一个 chunk 包含完整的 additional_kwargs
        if full_content:
            ai_message = self._parse_response(full_content, is_streaming=True)
            final_chunk = ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    additional_kwargs=ai_message.additional_kwargs
                )
            )
            yield final_chunk
    
    async def _astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """异步流式生成"""
        payload = self._get_payload(messages, stream=True)
        
        logger.debug(f"DeepSeek R1 异步流式请求: {self.api_base}{self.api_endpoint}")
        
        full_content = ""
        
        async with httpx.AsyncClient(verify=False, timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.api_base}{self.api_endpoint}",
                json=payload,
                headers=self._get_headers()
            ) as resp:
                resp.raise_for_status()
                
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    
                    # SSE 格式: data: {...}
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        
                        try:
                            data = json.loads(data_str)
                            if "choices" in data and data["choices"]:
                                delta = data["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                
                                if content:
                                    full_content += content
                                    chunk = ChatGenerationChunk(
                                        message=AIMessageChunk(content=content)
                                    )
                                    if run_manager:
                                        await run_manager.on_llm_new_token(content)
                                    yield chunk
                        except json.JSONDecodeError:
                            continue
        
        # 最后一个 chunk 包含完整的 additional_kwargs
        if full_content:
            ai_message = self._parse_response(full_content, is_streaming=True)
            final_chunk = ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    additional_kwargs=ai_message.additional_kwargs
                )
            )
            yield final_chunk


__all__ = ["DeepSeekR1Chat"]
