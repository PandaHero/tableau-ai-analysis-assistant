# -*- coding: utf-8 -*-
"""
测试 LangGraph 的 callbacks 传递机制
"""
import asyncio
import warnings
warnings.filterwarnings("ignore")

from typing import Dict, Any, TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage, SystemMessage
from tableau_assistant.src.infra.ai import get_llm


class SimpleState(TypedDict):
    question: str
    answer: str


async def llm_node(state: Dict[str, Any], config: Dict[str, Any] = None) -> Dict[str, Any]:
    """简单的 LLM 节点"""
    print(f"\n[llm_node] config keys: {config.keys() if config else 'None'}")
    if config:
        print(f"[llm_node] callbacks: {config.get('callbacks', 'NOT FOUND')}")
    
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
            print(chunk.content, end="", flush=True)
    
    return {"answer": "".join(collected)}


async def test_langgraph_stream():
    """测试 LangGraph 流式输出"""
    print("=" * 60)
    print("测试 LangGraph astream_events 捕获嵌套 LLM 调用")
    print("=" * 60)
    
    # 创建简单的图
    graph = StateGraph(SimpleState)
    graph.add_node("llm", llm_node)
    graph.add_edge(START, "llm")
    graph.add_edge("llm", END)
    
    workflow = graph.compile()
    
    # 使用 astream_events
    state = {"question": "1+1=?", "answer": ""}
    config = {"configurable": {"thread_id": "test"}}
    
    print("\n[Main] 开始 astream_events...")
    token_count = 0
    
    async for event in workflow.astream_events(state, config, version="v2"):
        event_type = event.get("event")
        event_name = event.get("name", "")
        
        if event_type == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content") and chunk.content:
                # 这里应该能捕获到 token
                print(f"[EVENT] token: {chunk.content}")
                token_count += 1
        
        elif event_type == "on_chain_start":
            print(f"[EVENT] chain_start: {event_name}")
        
        elif event_type == "on_chain_end":
            print(f"[EVENT] chain_end: {event_name}")
    
    print(f"\n\n共捕获 {token_count} 个 on_chat_model_stream 事件")


async def main():
    await test_langgraph_stream()
    print("\n✅ 测试完成!")


if __name__ == "__main__":
    asyncio.run(main())
