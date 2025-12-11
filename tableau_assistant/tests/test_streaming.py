"""
测试 Token 级别流式输出

验证 LLM 调用是否能产生 on_chat_model_stream 事件
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(project_root / ".env")


async def test_llm_streaming_direct():
    """直接测试 LLM 流式调用"""
    print("\n=== 测试 1: 直接 LLM 流式调用 ===\n")
    
    from tableau_assistant.src.agents.base import get_llm
    
    llm = get_llm(agent_name="understanding")
    messages = [{"role": "user", "content": "用一句话介绍自己"}]
    
    # 转换消息格式
    from tableau_assistant.src.agents.base.node import convert_messages
    langchain_messages = convert_messages(messages)
    
    print("Token 输出: ", end="", flush=True)
    token_count = 0
    
    async for event in llm.astream_events(langchain_messages, version="v2"):
        if event.get("event") == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content") and chunk.content:
                print(chunk.content, end="", flush=True)
                token_count += 1
    
    print(f"\n\n✓ 共收到 {token_count} 个 token")


async def test_call_llm_with_tools_streaming():
    """测试 call_llm_with_tools 的流式输出"""
    print("\n=== 测试 2: call_llm_with_tools 流式调用 ===\n")
    
    from tableau_assistant.src.agents.base import get_llm, call_llm_with_tools
    
    llm = get_llm(agent_name="understanding")
    messages = [
        {"role": "system", "content": "你是一个助手，请简短回答问题。"},
        {"role": "user", "content": "1+1等于几？"}
    ]
    
    # 无工具调用
    print("调用 call_llm_with_tools (streaming=True)...")
    result = await call_llm_with_tools(llm, messages, tools=[], streaming=True)
    print(f"结果: {result}")
    print("✓ call_llm_with_tools 完成")


async def test_workflow_streaming():
    """测试工作流流式输出"""
    print("\n=== 测试 3: WorkflowExecutor 流式输出 ===\n")
    
    from tableau_assistant.src.workflow.executor import WorkflowExecutor, EventType
    
    executor = WorkflowExecutor()
    
    question = "各产品类别的销售额是多少"
    print(f"问题: {question}\n")
    
    token_count = 0
    node_events = []
    
    try:
        async for event in executor.stream(question):
            if event.type == EventType.NODE_START:
                print(f"\n[{event.node_name}] 开始...")
                node_events.append(f"start:{event.node_name}")
            
            elif event.type == EventType.TOKEN:
                print(event.content, end="", flush=True)
                token_count += 1
            
            elif event.type == EventType.NODE_COMPLETE:
                print(f"\n[{event.node_name}] 完成")
                node_events.append(f"complete:{event.node_name}")
            
            elif event.type == EventType.ERROR:
                print(f"\n❌ 错误: {event.content}")
                break
            
            elif event.type == EventType.COMPLETE:
                print("\n\n✓ 工作流完成")
                break
    
    except Exception as e:
        print(f"\n❌ 异常: {e}")
    
    print(f"\n统计:")
    print(f"  - Token 数量: {token_count}")
    print(f"  - 节点事件: {node_events}")


async def main():
    print("=" * 60)
    print("Token 级别流式输出测试")
    print("=" * 60)
    
    # 测试 1: 直接 LLM 流式
    await test_llm_streaming_direct()
    
    # 测试 2: call_llm_with_tools
    await test_call_llm_with_tools_streaming()
    
    # 测试 3: 工作流流式
    await test_workflow_streaming()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
