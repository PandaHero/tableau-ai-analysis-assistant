#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
日期 Intent 类型选择测试

专门测试 DateFieldIntent vs DimensionIntent 的正确选择
"""
import os
import sys
from pathlib import Path
import asyncio

# 设置输出编码为 UTF-8
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

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
    # {
    #     "id": "date_dimension_and_filter",
    #     "question": "2025年每个月的销售额",  # 改变问题以绕过缓存
    #     "expected": {
    #         "has_date_field_intent": True,
    #         "date_function": "MONTH",
    #         "no_date_function_in_dimension": True
    #     }
    # },
    # {
    #     "id": "date_with_multi_dimensions",
    #     "question": "各省份各类别每个月的销售额",  # 改变问题以绕过缓存
    #     "expected": {
    #         "has_date_field_intent": True,
    #         "date_function": "MONTH",
    #         "no_date_function_in_dimension": True
    #     }
    # },
    {
        "id": "complex_multi_measure_date",
        "question": "2023年一季度各省份每月的销售额和利润",
        "expected": {
            "has_date_field_intent": True,
            "date_function": "MONTH",
            "no_date_function_in_dimension": True
        }
    }
]


async def test_date_intent_case(test_case: dict, env, metadata, dimension_hierarchy):
    """测试单个日期 Intent 用例"""
    
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
    planning_result = await task_planner_agent.execute(
        state=state,
        runtime=env.get_runtime()
    )
    state.update(planning_result)
    
    print(f"✓ 任务规划完成")
    
    # 验证结果
    query_subtasks = [st for st in state['query_plan'].subtasks if st.task_type == "query"]
    
    if not query_subtasks:
        print(f"✗ 没有查询子任务")
        return False
    
    subtask = query_subtasks[0]
    
    # 检查是否有 DateFieldIntent
    has_date_field_intent = len(subtask.date_field_intents or []) > 0
    
    if test_case["expected"]["has_date_field_intent"]:
        if has_date_field_intent:
            print(f"✓ 生成了 DateFieldIntent")
            
            # 检查 date_function
            for dfi in subtask.date_field_intents:
                if dfi.date_function == test_case["expected"]["date_function"]:
                    print(f"  ✓ date_function = {dfi.date_function}")
                else:
                    print(f"  ✗ date_function = {dfi.date_function}, 期望 {test_case['expected']['date_function']}")
                    return False
        else:
            print(f"✗ 没有生成 DateFieldIntent")
            return False
    
    # 检查 DimensionIntent 中不应有 date_function
    if test_case["expected"]["no_date_function_in_dimension"]:
        has_error = False
        for dim in (subtask.dimension_intents or []):
            if hasattr(dim, 'date_function') and dim.date_function is not None:
                print(f"✗ DimensionIntent 中发现 date_function: {dim.technical_field} has date_function={dim.date_function}")
                has_error = True
        
        if not has_error:
            print(f"✓ DimensionIntent 中没有 date_function")
        else:
            return False
    
    print(f"✓ 测试通过")
    return True


async def main():
    """主测试函数"""
    
    print("="*80)
    print("日期 Intent 类型选择测试")
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
        result = await test_date_intent_case(test_case, env, metadata, dimension_hierarchy)
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
