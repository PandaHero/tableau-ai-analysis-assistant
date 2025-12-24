# -*- coding: utf-8 -*-
"""
测试 WorkflowExecutor.stream() 的流式输出
"""
import asyncio
import time
import warnings
warnings.filterwarnings("ignore")

from tableau_assistant.src.orchestration.workflow.executor import WorkflowExecutor, EventType


async def test_executor_stream():
    """测试 WorkflowExecutor.stream() 的流式输出时序"""
    print("=" * 60)
    print("测试 WorkflowExecutor.stream() 流式输出")
    print("=" * 60)
    
    executor = WorkflowExecutor()
    
    question = "各产品类别的销售额是多少？"
    print(f"\n问题: {question}")
    print("\n开始流式执行...")
    
    start_time = time.time()
    token_count = 0
    token_times = []
    current_node = None
    
    async for event in executor.stream(question):
        current_time = time.time() - start_time
        
        if event.type == EventType.NODE_START:
            current_node = event.node_name
            print(f"\n[{current_time:.2f}s] 🚀 节点开始: {event.node_name}")
        
        elif event.type == EventType.TOKEN:
            token_count += 1
            token_times.append(current_time)
            # 实时打印 token
            print(event.content, end="", flush=True)
        
        elif event.type == EventType.NODE_COMPLETE:
            print(f"\n[{current_time:.2f}s] ✅ 节点完成: {event.node_name}")
        
        elif event.type == EventType.ERROR:
            print(f"\n[{current_time:.2f}s] ❌ 错误: {event.content}")
        
        elif event.type == EventType.COMPLETE:
            print(f"\n[{current_time:.2f}s] 🎉 工作流完成")
    
    total_time = time.time() - start_time
    
    print(f"\n\n统计:")
    print(f"  - 总 token 数: {token_count}")
    print(f"  - 总耗时: {total_time:.2f}s")
    
    if len(token_times) > 1:
        intervals = [token_times[i] - token_times[i-1] for i in range(1, len(token_times))]
        avg_interval = sum(intervals) / len(intervals)
        print(f"  - 平均 token 间隔: {avg_interval*1000:.1f}ms")
        print(f"  - 第一个 token 时间: {token_times[0]:.2f}s")
        print(f"  - 最后一个 token 时间: {token_times[-1]:.2f}s")


async def main():
    await test_executor_stream()


if __name__ == "__main__":
    asyncio.run(main())
