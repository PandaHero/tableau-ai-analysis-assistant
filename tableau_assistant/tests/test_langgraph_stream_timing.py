# -*- coding: utf-8 -*-
"""
测试 LangGraph astream_events 的流式输出时序
"""
import asyncio
import time
import warnings
warnings.filterwarnings("ignore")

from typing import Dict, Any, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import RunnableConfig
from langchain_core.messages import HumanMessage, SystemMessage
from tableau_assistant.src.infra.ai import get_llm


class SimpleState(TypedDict):
    question: str
    answer: str


async def llm_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """LLM 节点，传递 config"""
    llm = get_llm()
    messages = [
        SystemMessage(content="你是助手，简短回答"),
        HumanMessage(content=state["question"])
    ]
    
    # 传递 config 给 astream
    collected = []
    async for chunk in llm.astream(messages, config=config):
        if hasattr(chunk, "content") and chunk.content:
            collected.append(chunk.content)
    
    return {"answer": "".join(collected)}


async def test_langgraph_stream_timing():
    """测试 LangGraph astream_events 的时序"""
    print("=" * 60)
    print("测试 LangGraph astream_events 流式输出时序")
    print("=" * 60)
    
    # 创建图
    graph = StateGraph(SimpleState)
    graph.add_node("llm", llm_node)
    graph.add_edge(START, "llm")
    graph.add_edge("llm", END)
    
    workflow = graph.compile()
    
    state = {"question": "什么是人工智能？用3句话回答。", "answer": ""}
    config = {"configurable": {"thread_id": "test"}}
    
    print("\n开始 astream_events...")
    start_time = time.time()
    
    chunk_count = 0
    chunk_times = []
    
    async for event in workflow.astream_events(state, config, version="v2"):
        event_type = event.get("event")
        
        if event_type == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content") and chunk.content:
                current_time = time.time() - start_time
                chunk_times.append(current_time)
                chunk_count += 1
                
                content = chunk.content
                # 实时打印
                print(f"[{current_time:.2f}s] chunk {chunk_count}: '{content[:30]}...' " if len(content) > 30 else f"[{current_time:.2f}s] chunk {chunk_count}: '{content}'", flush=True)
    
    total_time = time.time() - start_time
    
    print(f"\n统计:")
    print(f"  - 总 chunk 数: {chunk_count}")
    print(f"  - 总耗时: {total_time:.2f}s")
    
    if len(chunk_times) > 1:
        intervals = [chunk_times[i] - chunk_times[i-1] for i in range(1, len(chunk_times))]
        avg_interval = sum(intervals) / len(intervals)
        print(f"  - 平均 chunk 间隔: {avg_interval*1000:.1f}ms")
        print(f"  - 第一个 chunk 时间: {chunk_times[0]:.2f}s")
        print(f"  - 最后一个 chunk 时间: {chunk_times[-1]:.2f}s")
        
        if chunk_times[0] > total_time * 0.8:
            print("\n⚠️ 警告: 第一个 chunk 出现很晚，LangGraph 可能有缓冲问题！")
        else:
            print("\n✅ LangGraph astream_events 正常工作")


async def main():
    await test_langgraph_stream_timing()


if __name__ == "__main__":
    asyncio.run(main())
