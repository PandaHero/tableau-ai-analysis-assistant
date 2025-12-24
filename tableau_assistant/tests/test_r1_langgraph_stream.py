# -*- coding: utf-8 -*-
"""
测试 LangGraph 是否能捕获 DeepSeek R1 的流式输出
"""
import asyncio
from tableau_assistant.src.infra.ai import get_llm
from tableau_assistant.src.agents.base import call_llm_with_tools
from langchain_core.messages import HumanMessage, SystemMessage


async def test_direct_astream():
    """直接测试 llm.astream() 是否有流式输出"""
    print("=" * 60)
    print("测试 1: 直接调用 llm.astream()")
    print("=" * 60)
    
    llm = get_llm()
    messages = [
        SystemMessage(content="你是助手"),
        HumanMessage(content="1+1=?")
    ]
    
    print("流式输出:")
    async for chunk in llm.astream(messages):
        if hasattr(chunk, "content") and chunk.content:
            print(chunk.content, end="", flush=True)
    print("\n")


async def test_astream_events():
    """测试 llm.astream_events() 是否能捕获事件"""
    print("=" * 60)
    print("测试 2: 调用 llm.astream_events()")
    print("=" * 60)
    
    llm = get_llm()
    messages = [
        SystemMessage(content="你是助手"),
        HumanMessage(content="1+1=?")
    ]
    
    print("流式事件:")
    try:
        async for event in llm.astream_events(messages, version="v2"):
            event_type = event.get("event")
            if event_type == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    print(chunk.content, end="", flush=True)
        print("\n")
    except Exception as e:
        print(f"astream_events 不支持: {e}")


async def main():
    await test_direct_astream()
    await test_astream_events()
    print("✅ 测试完成!")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    asyncio.run(main())
