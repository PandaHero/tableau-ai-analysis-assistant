# -*- coding: utf-8 -*-
"""
测试 DeepSeek R1 集成

call_llm_with_tools 返回完整的 AIMessage：
- response.content: 最终答案（不含思考过程）
- response.additional_kwargs.get("thinking"): R1 模型的思考过程

注意：call_llm_with_tools 内部使用流式调用，但返回完整结果。
要看到实时流式输出，需要通过 LangGraph 的 astream_events 订阅。
"""
import asyncio
from tableau_assistant.src.infra.ai import get_llm
from tableau_assistant.src.agents.base import call_llm_with_tools
from langchain_core.messages import HumanMessage, SystemMessage


async def test_r1_integration():
    print("=" * 60)
    print("测试 DeepSeek R1 集成")
    print("=" * 60)
    
    # 获取 LLM
    llm = get_llm()
    print(f"LLM 类型: {type(llm).__name__}")
    
    messages = [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "1+1=? 简短回答"}
    ]
    
    # 测试: call_llm_with_tools 返回 AIMessage
    print("\n测试 call_llm_with_tools（返回 AIMessage）...")
    print("（内部使用流式调用，但等待完整结果）")
    response = await call_llm_with_tools(
        llm=llm,
        messages=messages,
        tools=[],
        streaming=True,
    )
    
    print(f"   类型: {type(response).__name__}")
    print(f"   内容: {response.content[:100]}")
    
    # 检查思考过程（R1 模型特有）
    thinking = response.additional_kwargs.get("thinking", "")
    if thinking:
        print(f"   ✅ 思考过程: {thinking[:200]}...")
    else:
        print("   ⚠️ 没有思考过程（可能不是 R1 模型）")
    
    print("\n✅ 测试完成!")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    asyncio.run(test_r1_integration())
