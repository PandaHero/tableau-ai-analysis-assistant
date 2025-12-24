# -*- coding: utf-8 -*-
"""
测试 LangGraph 节点函数的 config 传递
"""
import asyncio
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


async def llm_node_with_config(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """使用正确的类型注解接收 config"""
    print(f"\n[llm_node] config type: {type(config)}")
    print(f"[llm_node] config keys: {config.keys() if config else 'None'}")
    if config:
        print(f"[llm_node] callbacks type: {type(config.get('callbacks', 'NOT FOUND'))}")
    
    llm = get_llm()
    messages = [
        SystemMessage(content="你是助手，用一个词回答"),
        HumanMessage(content=state["question"])
    ]
    
    # 传递 config 给 astream
    collected = []
    async for chunk in llm.astream(messages, config=config):
        if hasattr(chunk, "content") and chunk.content:
            collected.append(chunk.content)
    
    return {"answer": "".join(collected)}


async def test_config_passing():
    """测试 config 传递"""
    print("=" * 60)
    print("测试 LangGraph config 传递到节点函数")
    print("=" * 60)
    
    # 创建简单的图
    graph = StateGraph(SimpleState)
    graph.add_node("llm", llm_node_with_config)
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
        
        if event_type == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content") and chunk.content:
                token_count += 1
    
    print(f"\n共捕获 {token_count} 个 on_chat_model_stream 事件")


async def main():
    await test_config_passing()
    print("\n✅ 测试完成!")


if __name__ == "__main__":
    asyncio.run(main())
