# -*- coding: utf-8 -*-
"""
测试 SSE 流式输出接口

直接调用 generate_sse_events 函数，验证 token 是否实时输出
"""
import asyncio
import time
import warnings
warnings.filterwarnings("ignore")

import sys
sys.path.insert(0, ".")


async def test_sse_stream():
    """测试 SSE 流式输出"""
    print("=" * 60)
    print("测试 SSE 流式输出")
    print("=" * 60)
    
    from tableau_assistant.src.api.chat import generate_sse_events
    
    question = "各产品类别的销售额是多少？"
    session_id = f"test_{int(time.time())}"
    datasource_luid = "e99f1815-b3b8-4660-9624-946ea028338f"
    
    print(f"\n问题: {question}")
    print(f"数据源: {datasource_luid}")
    print("\n开始 SSE 流式输出...")
    print("-" * 60)
    
    start_time = time.time()
    token_count = 0
    token_times = []
    current_node = None
    
    async for sse_data in generate_sse_events(question, session_id, datasource_luid):
        current_time = time.time() - start_time
        
        # 解析 SSE 数据
        if sse_data.startswith("data: "):
            import json
            try:
                event = json.loads(sse_data[6:].strip())
                event_type = event.get("event_type")
                data = event.get("data", {})
                
                if event_type == "node_start":
                    current_node = data.get("node")
                    print(f"\n[{current_time:.2f}s] 🚀 节点开始: {current_node}")
                
                elif event_type == "token":
                    token_count += 1
                    token_times.append(current_time)
                    content = data.get("content", "")
                    # 实时打印 token
                    print(content, end="", flush=True)
                
                elif event_type == "node_complete":
                    node = data.get("node")
                    print(f"\n[{current_time:.2f}s] ✅ 节点完成: {node}")
                
                elif event_type == "complete":
                    print(f"\n[{current_time:.2f}s] 🎉 工作流完成")
                
                elif event_type == "error":
                    print(f"\n[{current_time:.2f}s] ❌ 错误: {data.get('message')}")
                    
            except json.JSONDecodeError:
                pass
    
    total_time = time.time() - start_time
    
    print("\n" + "-" * 60)
    print(f"\n统计:")
    print(f"  - 总 token 数: {token_count}")
    print(f"  - 总耗时: {total_time:.2f}s")
    
    if len(token_times) > 1:
        intervals = [token_times[i] - token_times[i-1] for i in range(1, len(token_times))]
        avg_interval = sum(intervals) / len(intervals)
        print(f"  - 平均 token 间隔: {avg_interval*1000:.1f}ms")
        print(f"  - 第一个 token 时间: {token_times[0]:.2f}s")
        print(f"  - 最后一个 token 时间: {token_times[-1]:.2f}s")
        
        if avg_interval < 0.1:  # 小于 100ms
            print("\n✅ SSE 流式输出正常工作！")
        else:
            print("\n⚠️ token 间隔较大，可能有缓冲问题")


async def main():
    await test_sse_stream()


if __name__ == "__main__":
    asyncio.run(main())
