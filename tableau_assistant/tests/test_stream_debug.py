# -*- coding: utf-8 -*-
"""
调试流式输出 - 检查 config 传递是否正确
"""
import asyncio
import warnings
warnings.filterwarnings("ignore")

from langchain_core.messages import HumanMessage, SystemMessage
from tableau_assistant.src.infra.ai import get_llm


async def test_astream_with_config():
    """测试 astream 传递 config 时是否触发事件"""
    print("=" * 60)
    print("测试: llm.astream() 传递 config")
    print("=" * 60)
    
    llm = get_llm()
    messages = [
        SystemMessage(content="你是助手"),
        HumanMessage(content="1+1=?")
    ]
    
    # 模拟 LangGraph 的 config
    config = {
        "callbacks": [],  # 空 callbacks
        "configurable": {"thread_id": "test"},
    }
    
    print("\n1. 不传 config:")
    async for chunk in llm.astream(messages):
        if hasattr(chunk, "content") and chunk.content:
            print(chunk.content, end="", flush=True)
    print("\n")
    
    print("2. 传递 config:")
    async for chunk in llm.astream(messages, config=config):
        if hasattr(chunk, "content") and chunk.content:
            print(chunk.content, end="", flush=True)
    print("\n")


async def test_astream_events_direct():
    """直接测试 astream_events"""
    print("=" * 60)
    print("测试: llm.astream_events() 直接调用")
    print("=" * 60)
    
    llm = get_llm()
    messages = [
        SystemMessage(content="你是助手"),
        HumanMessage(content="1+1=?")
    ]
    
    print("\n流式事件:")
    token_count = 0
    async for event in llm.astream_events(messages, version="v2"):
        event_type = event.get("event")
        if event_type == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content") and chunk.content:
                print(chunk.content, end="", flush=True)
                token_count += 1
    print(f"\n\n共 {token_count} 个 token 事件")


async def main():
    await test_astream_with_config()
    await test_astream_events_direct()
    print("\n✅ 测试完成!")


if __name__ == "__main__":
    asyncio.run(main())
