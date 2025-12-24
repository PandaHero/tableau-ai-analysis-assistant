# -*- coding: utf-8 -*-
"""
测试 Workflow 流式输出

验证 WorkflowExecutor.stream() 是否能正确输出 LLM 的 token 流
"""
import asyncio
import warnings
warnings.filterwarnings("ignore")

from tableau_assistant.src.orchestration.workflow.executor import WorkflowExecutor, EventType


async def test_workflow_stream():
    """测试 workflow 流式输出"""
    print("=" * 60)
    print("测试 Workflow 流式输出")
    print("=" * 60)
    
    # 创建 executor
    executor = WorkflowExecutor()
    
    question = "各产品类别的销售额是多少?"
    print(f"\n问题: {question}\n")
    print("-" * 60)
    
    token_count = 0
    current_node = None
    
    async for event in executor.stream(question):
        if event.type == EventType.NODE_START:
            current_node = event.node_name
            print(f"\n🚀 [{event.node_name}] 开始...")
            
        elif event.type == EventType.TOKEN:
            # 流式输出 token
            print(event.content, end="", flush=True)
            token_count += 1
            
        elif event.type == EventType.NODE_COMPLETE:
            print(f"\n✅ [{event.node_name}] 完成")
            
        elif event.type == EventType.ERROR:
            print(f"\n❌ 错误: {event.content}")
            break
            
        elif event.type == EventType.COMPLETE:
            print(f"\n{'=' * 60}")
            print(f"✅ 工作流完成! 共输出 {token_count} 个 token")
            break
    
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_workflow_stream())
