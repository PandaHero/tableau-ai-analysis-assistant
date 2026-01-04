# -*- coding: utf-8 -*-
"""
自定义 LLM 客户端

支持公司内部部署的各种大模型，包括但不限于：
- DeepSeek R1 推理模型
- 其他自建/私有化部署的模型

特点：
- 支持自定义 API 端点和认证方式
- 支持思考过程提取（<think>...</think> 标签）
- 支持流式输出
- 支持动态配置（从数据库/配置文件加载）
"""
import re
import json
import logging
from enum import Enum
from typing import Any, List, Optional, Iterator, AsyncIterator, Dict

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage, AIMessageChunk
from langchain_core.outputs import ChatResult, ChatGeneration, ChatGenerationChunk
from langchain_core.callbacks import CallbackManagerForLLMRun, AsyncCallbackManagerForLLMRun
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AuthType(str, Enum):
    """认证类型"""
    BEARER = "bearer"           # Authorization: Bearer <token>
    API_KEY_HEADER = "apikey"   # Apikey: <token>
    CUSTOM_HEADER = "custom"    # 自定义 header
    NONE = "none"               # 无认证


class CustomLLMConfig(BaseModel):
    """自定义 LLM 配置模型
    
    用于存储和传递自定义模型的配置信息。
    可以从数据库、配置文件或 API 请求中加载。
    """
    # 基本信息
    name: str = Field(..., description="模型名称（唯一标识）")
    display_name: str = Field(default="", description="显示名称")
    description: str = Field(default="", description="模型描述")
    
    # API 配置
    api_base: str = Field(..., description="API 基础 URL")
    api_endpoint: str = Field(default="/v1/chat/completions", description="API 端点路径")
    model_name: str = Field(..., description="模型名称（API 参数）")
    
    # 认证配置
    auth_type: AuthType = Field(default=AuthType.BEARER, description="认证类型")
    auth_header: str = Field(default="Authorization", description="认证 header 名称")
    api_key: str = Field(default="", description="API Key")
    
    # 模型参数
    temperature: float = Field(default=0.2, description="温度参数")
    max_tokens: int = Field(default=4096, description="最大 token 数")
    timeout: float = Field(default=120.0, description="请求超时时间")
    
    # 特性配置
    supports_streaming: bool = Field(default=True, description="是否支持流式输出")
    supports_thinking: bool = Field(default=False, description="是否支持思考过程提取")
    thinking_tag: str = Field(default="think", description="思考过程标签名")
    
    # SSL 配置
    verify_ssl: bool = Field(default=False, description="是否验证 SSL 证书")
    
    # 额外配置
    extra_headers: Dict[str, str] = Field(default_factory=dict, description="额外请求头")
    extra_body: Dict[str, Any] = Field(default_factory=dict, description="额外请求体参数")


class CustomLLMChat(BaseChatModel):
    """通用自定义 LLM 客户端
    
    支持各种自定义 API 格式的大模型，包括：
    - 公司内部部署的模型
    - 私有化部署的开源模型
    - 自定义 API 格式的模型
    
    特点：
    - 灵活的认证方式（Bearer、API Key Header、自定义）
    - 可选的思考过程提取
    - 支持流式输出
    """
    
    # 配置
    config: CustomLLMConfig = Field(...)
    
    # 运行时覆盖（可选）
    temperature_override: Optional[float] = Field(default=None)
    
    model_config = {"arbitrary_types_allowed": True}
    
    @property
    def _llm_type(self) -> str:
        return f"custom-llm-{self.config.name}"
    
    @property
    def _effective_temperature(self) -> float:
        """获取有效温度"""
        return self.temperature_override if self.temperature_override is not None else self.config.temperature
    
    def _convert_messages(self, messages: List[BaseMessage]) -> List[dict]:
        """转换 LangChain 消息为 API 格式"""
        result = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                result.append({"role": "system", "content": msg.content})
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
        """
        thinking = ""
        answer = content
        
        if self.config.supports_thinking:
            tag = self.config.thinking_tag
            # 提取 <tag>...</tag> 标签内容
            pattern = rf'<{tag}>(.*?)</{tag}>'
            think_match = re.search(pattern, content, re.DOTALL)
            if think_match:
                thinking = think_match.group(1).strip()
                answer = re.sub(rf'<{tag}>.*?</{tag}>\s*', '', content, flags=re.DOTALL).strip()
            elif is_streaming:
                # 流式模式：尝试用空行分隔
                parts = content.strip().split('\n\n')
                if len(parts) >= 2:
                    thinking = '\n\n'.join(parts[:-1]).strip()
                    answer = parts[-1].strip()
        
        return AIMessage(
            content=answer,
            additional_kwargs={
                "thinking": thinking,
                "raw_content": content,
                "answer": answer,
            }
        )
    
    def _get_headers(self) -> dict:
        """获取请求头"""
        headers = {
            "Content-Type": "application/json",
            **self.config.extra_headers,
        }
        
        # 添加认证头
        if self.config.api_key:
            if self.config.auth_type == AuthType.BEARER:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            elif self.config.auth_type == AuthType.API_KEY_HEADER:
                headers["Apikey"] = self.config.api_key
            elif self.config.auth_type == AuthType.CUSTOM_HEADER:
                headers[self.config.auth_header] = self.config.api_key
        
        return headers
    
    def _get_payload(self, messages: List[BaseMessage], stream: bool = False) -> dict:
        """构建请求体"""
        payload = {
            "model": self.config.model_name,
            "max_tokens": self.config.max_tokens,
            "temperature": self._effective_temperature,
            "messages": self._convert_messages(messages),
            "stream": stream,
            **self.config.extra_body,
        }
        return payload
    
    def _get_url(self) -> str:
        """获取完整 API URL"""
        base = self.config.api_base.rstrip('/')
        endpoint = self.config.api_endpoint
        if not endpoint.startswith('/'):
            endpoint = '/' + endpoint
        return f"{base}{endpoint}"
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """同步生成"""
        payload = self._get_payload(messages, stream=False)
        url = self._get_url()
        
        logger.debug(f"Custom LLM [{self.config.name}] 请求: {url}")
        
        with httpx.Client(verify=self.config.verify_ssl, timeout=self.config.timeout) as client:
            resp = client.post(url, json=payload, headers=self._get_headers())
            resp.raise_for_status()
            data = resp.json()
        
        content = data["choices"][0]["message"]["content"]
        ai_message = self._parse_response(content)
        
        logger.debug(f"Custom LLM [{self.config.name}] 响应: {ai_message.content[:100]}...")
        
        return ChatResult(generations=[ChatGeneration(message=ai_message)])
    
    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """异步生成"""
        payload = self._get_payload(messages, stream=False)
        url = self._get_url()
        
        logger.debug(f"Custom LLM [{self.config.name}] 异步请求: {url}")
        
        async with httpx.AsyncClient(verify=self.config.verify_ssl, timeout=self.config.timeout) as client:
            resp = await client.post(url, json=payload, headers=self._get_headers())
            resp.raise_for_status()
            data = resp.json()
        
        content = data["choices"][0]["message"]["content"]
        ai_message = self._parse_response(content)
        
        logger.debug(f"Custom LLM [{self.config.name}] 异步响应: {ai_message.content[:100]}...")
        
        return ChatResult(generations=[ChatGeneration(message=ai_message)])

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """同步流式生成"""
        if not self.config.supports_streaming:
            # 不支持流式，回退到普通生成
            result = self._generate(messages, stop, run_manager, **kwargs)
            yield ChatGenerationChunk(message=AIMessageChunk(content=result.generations[0].message.content))
            return
        
        payload = self._get_payload(messages, stream=True)
        url = self._get_url()
        
        logger.debug(f"Custom LLM [{self.config.name}] 流式请求: {url}")
        
        full_content = ""
        
        with httpx.Client(verify=self.config.verify_ssl, timeout=self.config.timeout) as client:
            with client.stream("POST", url, json=payload, headers=self._get_headers()) as resp:
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
        if not self.config.supports_streaming:
            # 不支持流式，回退到普通生成
            result = await self._agenerate(messages, stop, run_manager, **kwargs)
            yield ChatGenerationChunk(message=AIMessageChunk(content=result.generations[0].message.content))
            return
        
        payload = self._get_payload(messages, stream=True)
        url = self._get_url()
        
        logger.debug(f"Custom LLM [{self.config.name}] 异步流式请求: {url}")
        
        full_content = ""
        
        async with httpx.AsyncClient(verify=self.config.verify_ssl, timeout=self.config.timeout) as client:
            async with client.stream("POST", url, json=payload, headers=self._get_headers()) as resp:
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


__all__ = [
    # 核心类
    "CustomLLMChat",
    "CustomLLMConfig",
    "AuthType",
]
