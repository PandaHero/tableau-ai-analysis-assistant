#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
日期范围测试

测试 TimeRange 模型的 start_date 和 end_date 字段
"""
import os
import sys
from pathlib import Path
import asyncio

# 设置输出编码为 UTF-8
# 注意：在pytest环境下不要重新包装stdout/stderr，会导致pytest捕获机制失败
# if sys.platform == 'win32':
#     import io
#     sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
#     sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from tableau_assistant.tests.test_helpers.test_environment import TestEnvironment
from tableau_assistant.src.agents.understanding_agent import understanding_agent
from tableau_assistant.src.agents.task_planner_agent import task_planner_agent


# 测试用例
TEST_CASES = [
    {
        "id": "edge_date_range",
        "question": "2024年1月到3月的销售额",
        "expected": {
            "has_date_filter": True,
            "has_start_date": True,
            "has_end_date": True,
            "expected_start": "2024-01-01",
            "expected_end": "2024-03-31"
        }
    }
]


async def test_date_range_case(test_case: dict, env, metadata, dimension_hierarchy):
    """测试日期范围用例"""
    
    print(f"\n{'='*80}")
    print(f"测试: {test_case['id']}")
    print(f"问题: {test_case['question']}")
    print(f"{'='*80}")
    
    # 问题理解
    state = {
        "original_question": test_case["question"],
        "question": test_case["question"],
        "metadata": metadata,
        "dimension_hierarchy": dimension_hierarchy
    }
    
    understanding_result = await understanding_agent.execute(
        state=state,
        runtime=env.get_runtime()
    )
    state.update(understanding_result)
    
    print(f"✓ 问题理解完成")
    
    # 任务规划
    try:
        planning_result = await task_planner_agent.execute(
            state=state,
            runtime=env.get_runtime()
        )
        state.update(planning_result)
        
        print(f"✓ 任务规划完成")
    except Exception as e:
        print(f"✗ 任务规划失败: {str(e)}")
        return False
    
    # 验证结果
    query_subtasks = [st for st in state['query_plan'].subtasks if st.task_type == "query"]
    
    if not query_subtasks:
        print(f"✗ 没有查询子任务")
        return False
    
    subtask = query_subtasks[0]
    
    # 检查日期筛选
    if not subtask.date_filter_intent:
        print(f"✗ 没有日期筛选")
        return False
    
    print(f"✓ 有日期筛选")
    
    time_range = subtask.date_filter_intent.time_range
    
    # 检查 start_date
    if test_case["expected"]["has_start_date"]:
        if hasattr(time_range, 'start_date') and time_range.start_date:
            print(f"✓ 有 start_date: {time_range.start_date}")
            
            if "expected_start" in test_case["expected"]:
                if time_range.start_date == test_case["expected"]["expected_start"]:
                    print(f"  ✓ start_date 值正确")
                else:
                    print(f"  ✗ start_date 值错误: 期望 {test_case['expected']['expected_start']}, 实际 {time_range.start_date}")
                    return False
        else:
            print(f"✗ 缺少 start_date")
            return False
    
    # 检查 end_date
    if test_case["expected"]["has_end_date"]:
        if hasattr(time_range, 'end_date') and time_range.end_date:
            print(f"✓ 有 end_date: {time_range.end_date}")
            
            if "expected_end" in test_case["expected"]:
                if time_range.end_date == test_case["expected"]["expected_end"]:
                    print(f"  ✓ end_date 值正确")
                else:
                    print(f"  ✗ end_date 值错误: 期望 {test_case['expected']['expected_end']}, 实际 {time_range.end_date}")
                    return False
        else:
            print(f"✗ 缺少 end_date")
            return False
    
    print(f"✓ 测试通过")
    return True


async def main():
    """主测试函数"""
    
    print("="*80)
    print("日期范围测试")
    print("="*80)
    
    # 初始化环境
    env = TestEnvironment()
    await env.setup()
    
    metadata = await env.get_metadata_manager().get_metadata_async()
    dimension_hierarchy = metadata.dimension_hierarchy or {}
    
    print(f"✓ 环境初始化完成")
    
    # 运行测试
    results = []
    for test_case in TEST_CASES:
        result = await test_date_range_case(test_case, env, metadata, dimension_hierarchy)
        results.append((test_case["id"], result))
    
    # 清理环境
    await env.teardown()
    
    # 打印总结
    print(f"\n{'='*80}")
    print("测试总结")
    print(f"{'='*80}")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    print(f"通过: {passed}/{total}")
    
    for test_id, result in results:
        status = "✓" if result else "✗"
        print(f"  {status} {test_id}")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
