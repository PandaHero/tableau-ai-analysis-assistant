# -*- coding: utf-8 -*-
"""
测试 DeepSeek R1 流式输出和思考过程提取
"""
import asyncio
from tableau_assistant.src.infra.ai import get_llm


async def test_r1_stream():
    print("=" * 60)
    print("测试 DeepSeek R1 流式输出")
    print("=" * 60)
    
    llm = get_llm()
    print(f"LLM 类型: {type(llm).__name__}")
    
    from langchain_core.messages import HumanMessage, SystemMessage
    messages = [
        SystemMessage(content="你是助手"),
        HumanMessage(content="1+1=? 简短回答")
    ]
    
    print("\n流式输出:")
    collected_content = []
    additional_kwargs = {}
    
    async for chunk in llm.astream(messages):
        print(f"  chunk 类型: {type(chunk).__name__}")
        
        if hasattr(chunk, "content") and chunk.content:
            print(f"  content: {chunk.content[:50]}...")
            collected_content.append(chunk.content)
        
        if hasattr(chunk, "additional_kwargs") and chunk.additional_kwargs:
            print(f"  additional_kwargs: {list(chunk.additional_kwargs.keys())}")
            additional_kwargs.update(chunk.additional_kwargs)
    
    print(f"\n完整内容: {''.join(collected_content)[:200]}...")
    print(f"additional_kwargs: {list(additional_kwargs.keys())}")
    
    if "thinking" in additional_kwargs:
        print(f"✅ 思考过程: {additional_kwargs['thinking'][:200]}...")
    else:
        print("⚠️ 没有思考过程")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    asyncio.run(test_r1_stream())
