# -*- coding: utf-8 -*-
"""
快速测试：create_agent + stream_mode="messages" 流式输出
"""
import asyncio
import json
import os
import sys
import time
import io

# 修复 Windows GBK 编码问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from pydantic import BaseModel, Field
from typing import List
from langchain_core.messages import AIMessageChunk, HumanMessage
from langchain_core.tools import tool
from langchain.agents import create_agent
from analytics_assistant.src.agents.base import get_llm


class SimpleResult(BaseModel):
    """简单结果。"""
    answer: str = Field(description="回答")
    confidence: float = Field(ge=0.0, le=1.0, description="置信度")


@tool
def add_numbers(a: int, b: int) -> str:
    """将两个数字相加。"""
    return json.dumps({"result": a + b})


async def test_custom_llm_streaming():
    """测试 CustomChatLLM（内部 R1）基础流式。"""
    print("\n=== 测试 1: custom-deepseek-r1 基础流式 ===")
    from analytics_assistant.src.infra.ai import TaskType
    llm = get_llm(agent_name="insight", task_type=TaskType.INSIGHT_GENERATION)
    agent = create_agent(model=llm, system_prompt="用中文简短回答，50字以内。")

    token_count = 0
    thinking_count = 0
    start = time.time()

    async for event in agent.astream(
        {"messages": [HumanMessage(content="1+1等于几？")]},
        stream_mode="messages",
    ):
        msg, _ = event
        if isinstance(msg, AIMessageChunk):
            if msg.additional_kwargs.get("thinking"):
                thinking_count += 1
            if msg.content:
                token_count += 1
                print(msg.content, end="", flush=True)

    elapsed = time.time() - start
    print(f"\n  tokens={token_count}, thinking={thinking_count}, elapsed={elapsed:.1f}s")
    print(f"  streaming: {'PASS' if token_count > 1 else 'FAIL'}")
    return token_count > 1


async def test_openai_streaming():
    """测试 OpenAI 兼容模型基础流式。"""
    print("\n=== 测试 2: deepseek-chat 基础流式 ===")
    llm = get_llm(model_id="deepseek-chat")
    agent = create_agent(model=llm, system_prompt="用中文简短回答，50字以内。")

    token_count = 0
    start = time.time()
    first_token = None

    async for event in agent.astream(
        {"messages": [HumanMessage(content="1+1等于几？")]},
        stream_mode="messages",
    ):
        msg, _ = event
        if isinstance(msg, AIMessageChunk) and msg.content:
            if first_token is None:
                first_token = time.time()
            token_count += 1
            print(msg.content, end="", flush=True)

    elapsed = time.time() - start
    ttft = f"{first_token - start:.1f}s" if first_token else "N/A"
    print(f"\n  tokens={token_count}, elapsed={elapsed:.1f}s, TTFT={ttft}")
    print(f"  streaming: {'PASS' if token_count > 1 else 'FAIL'}")
    return token_count > 1


async def test_openai_tools():
    """测试 OpenAI 兼容模型工具调用。"""
    print("\n=== 测试 3: deepseek-chat 工具调用 ===")
    llm = get_llm(model_id="deepseek-chat")
    agent = create_agent(model=llm, tools=[add_numbers], system_prompt="使用工具计算，然后用中文简短回答。")

    token_count = 0
    tool_calls = 0
    start = time.time()

    async for event in agent.astream(
        {"messages": [HumanMessage(content="请计算 42 + 58")]},
        stream_mode="messages",
    ):
        msg, _ = event
        if isinstance(msg, AIMessageChunk):
            if msg.content:
                token_count += 1
                print(msg.content, end="", flush=True)
            if msg.tool_call_chunks:
                tool_calls += 1

    elapsed = time.time() - start
    print(f"\n  tokens={token_count}, tool_calls={tool_calls}, elapsed={elapsed:.1f}s")
    print(f"  tool_calling: {'PASS' if tool_calls > 0 else 'FAIL'}")
    return tool_calls > 0


async def test_openai_structured():
    """测试 OpenAI 兼容模型结构化输出。"""
    print("\n=== 测试 4: deepseek-chat 结构化输出 ===")
    llm = get_llm(model_id="deepseek-chat")
    agent = create_agent(model=llm, system_prompt="用中文回答。", response_format=SimpleResult)

    start = time.time()
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content="1+1等于几？")]},
    )
    elapsed = time.time() - start

    structured = result.get("structured_response")
    if structured:
        print(f"  answer={structured.answer}, confidence={structured.confidence}")
        print(f"  elapsed={elapsed:.1f}s")
        print(f"  structured: PASS")
        return True
    else:
        print(f"  keys={list(result.keys())}")
        print(f"  structured: FAIL")
        return False


async def main():
    results = {}

    for name, test_fn in [
        ("custom_streaming", test_custom_llm_streaming),
        ("openai_streaming", test_openai_streaming),
        ("openai_tools", test_openai_tools),
        ("openai_structured", test_openai_structured),
    ]:
        try:
            results[name] = await test_fn()
        except Exception as e:
            print(f"  FAIL: {e}")
            results[name] = False

    print("\n=== Summary ===")
    for k, v in results.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")


if __name__ == "__main__":
    asyncio.run(main())
