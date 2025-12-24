# -*- coding: utf-8 -*-
"""
测试 DeepSeek R1 实时流式输出
"""
import asyncio
from tableau_assistant.src.infra.ai import get_llm
from langchain_core.messages import HumanMessage, SystemMessage


async def test_r1_stream_live():
    print("=" * 60)
    print("测试 DeepSeek R1 实时流式输出")
    print("=" * 60)
    
    llm = get_llm()
    print(f"LLM 类型: {type(llm).__name__}")
    
    messages = [
        SystemMessage(content="你是助手"),
        HumanMessage(content="1+1=? 简短回答")
    ]
    
    print("\n实时流式输出:")
    print("-" * 40)
    
    collected_content = []
    additional_kwargs = {}
    
    # 使用 astream 进行流式调用，实时打印每个 token
    async for chunk in llm.astream(messages):
        if hasattr(chunk, "content") and chunk.content:
            print(chunk.content, end="", flush=True)  # 实时打印
            collected_content.append(chunk.content)
        
        if hasattr(chunk, "additional_kwargs") and chunk.additional_kwargs:
            additional_kwargs.update(chunk.additional_kwargs)
    
    print("\n" + "-" * 40)
    
    # 显示解析结果
    full_content = "".join(collected_content)
    print(f"\n完整内容长度: {len(full_content)} 字符")
    
    if "thinking" in additional_kwargs:
        thinking = additional_kwargs["thinking"]
        print(f"思考过程长度: {len(thinking)} 字符")
        print(f"思考过程预览: {thinking[:100]}...")
    
    if "answer" in additional_kwargs:
        answer = additional_kwargs["answer"]
        print(f"最终答案: {answer}")
    
    print("\n✅ 测试完成!")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    asyncio.run(test_r1_stream_live())
