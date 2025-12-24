# -*- coding: utf-8 -*-
"""
直接测试 DeepSeekR1Chat._astream() 是否真正逐 chunk yield
"""
import asyncio
import time
import warnings
warnings.filterwarnings("ignore")

from tableau_assistant.src.infra.ai import get_llm
from langchain_core.messages import HumanMessage, SystemMessage


async def test_direct_astream():
    """直接测试 astream，不经过 LangGraph"""
    print("=" * 60)
    print("直接测试 DeepSeekR1Chat.astream() 流式输出")
    print("=" * 60)
    
    llm = get_llm()
    print(f"LLM 类型: {type(llm).__name__}")
    
    messages = [
        SystemMessage(content="你是助手，简短回答"),
        HumanMessage(content="什么是人工智能？用3句话回答。")
    ]
    
    print("\n开始流式调用...")
    start_time = time.time()
    
    chunk_count = 0
    chunk_times = []
    
    async for chunk in llm.astream(messages):
        current_time = time.time() - start_time
        chunk_times.append(current_time)
        
        if hasattr(chunk, "content") and chunk.content:
            chunk_count += 1
            # 打印每个 chunk 的时间和内容
            print(f"[{current_time:.2f}s] chunk {chunk_count}: '{chunk.content[:50]}...' " if len(chunk.content) > 50 else f"[{current_time:.2f}s] chunk {chunk_count}: '{chunk.content}'")
    
    total_time = time.time() - start_time
    
    print(f"\n统计:")
    print(f"  - 总 chunk 数: {chunk_count}")
    print(f"  - 总耗时: {total_time:.2f}s")
    
    if len(chunk_times) > 1:
        # 计算 chunk 之间的时间间隔
        intervals = [chunk_times[i] - chunk_times[i-1] for i in range(1, len(chunk_times))]
        avg_interval = sum(intervals) / len(intervals)
        print(f"  - 平均 chunk 间隔: {avg_interval*1000:.1f}ms")
        print(f"  - 第一个 chunk 时间: {chunk_times[0]:.2f}s")
        print(f"  - 最后一个 chunk 时间: {chunk_times[-1]:.2f}s")
        
        # 判断是否真正流式
        if chunk_times[0] > total_time * 0.8:
            print("\n⚠️ 警告: 第一个 chunk 出现很晚，可能不是真正的流式输出！")
            print("   API 可能是等待完成后一次性返回所有数据")
        else:
            print("\n✅ 看起来是真正的流式输出")


async def main():
    await test_direct_astream()


if __name__ == "__main__":
    asyncio.run(main())
