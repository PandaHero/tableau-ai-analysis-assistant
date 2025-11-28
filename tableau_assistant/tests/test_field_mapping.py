#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
字段映射验证测试

专门测试 technical_field 是否正确映射到 metadata.fields 中的字段
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
        "id": "aggregation",
        "question": "总销售额是多少？",
        "expected": {
            "has_valid_fields": True,
            "expected_fields": ["netplamt", "收入", "销售额"]  # 任意一个都可以
        }
    },
    {
        "id": "date_filter_last_quarter",
        "question": "上个季度的销售额",
        "expected": {
            "has_valid_fields": True,
            "has_date_filter": True
        }
    },
    {
        "id": "edge_empty_result",
        "question": "2030年的销售额",
        "expected": {
            "has_valid_fields": True,
            "has_date_filter": True
        }
    }
]


async def test_field_mapping_case(test_case: dict, env, metadata, dimension_hierarchy):
    """测试单个字段映射用例"""
    
    print(f"\n{'='*80}")
    print(f"测试: {test_case['id']}")
    print(f"问题: {test_case['question']}")
    print(f"{'='*80}")
    
    # 获取所有有效字段名
    valid_fields = set(field.name for field in metadata.fields)
    print(f"元数据中的字段数量: {len(valid_fields)}")
    
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
    
    # 验证字段映射
    query_subtasks = [st for st in state['query_plan'].subtasks if st.task_type == "query"]
    
    if not query_subtasks:
        print(f"✗ 没有查询子任务")
        return False
    
    subtask = query_subtasks[0]
    
    # 收集所有使用的 technical_field
    all_fields = []
    
    for dim in (subtask.dimension_intents or []):
        all_fields.append(dim.technical_field)
    
    for measure in (subtask.measure_intents or []):
        all_fields.append(measure.technical_field)
    
    for date_field in (subtask.date_field_intents or []):
        all_fields.append(date_field.technical_field)
    
    if subtask.date_filter_intent:
        all_fields.append(subtask.date_filter_intent.technical_field)
    
    print(f"\n使用的字段:")
    for field in all_fields:
        print(f"  - {field}")
    
    # 验证所有字段都在 metadata 中
    invalid_fields = []
    for field in all_fields:
        if field not in valid_fields:
            invalid_fields.append(field)
            print(f"  ✗ 字段 '{field}' 不存在于元数据中")
    
    if invalid_fields:
        print(f"\n✗ 发现 {len(invalid_fields)} 个无效字段")
        print(f"有效字段示例: {list(valid_fields)[:10]}")
        return False
    
    print(f"\n✓ 所有字段都有效")
    
    # 检查特定期望
    if "expected_fields" in test_case["expected"]:
        expected = test_case["expected"]["expected_fields"]
        found = any(field in all_fields for field in expected)
        if found:
            print(f"✓ 找到了期望的字段之一: {[f for f in expected if f in all_fields]}")
        else:
            print(f"✗ 没有找到期望的字段: {expected}")
            print(f"实际使用的字段: {all_fields}")
            return False
    
    if test_case["expected"].get("has_date_filter"):
        if subtask.date_filter_intent:
            print(f"✓ 有日期筛选")
        else:
            print(f"✗ 缺少日期筛选")
            return False
    
    print(f"✓ 测试通过")
    return True


async def main():
    """主测试函数"""
    
    print("="*80)
    print("字段映射验证测试")
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
        result = await test_field_mapping_case(test_case, env, metadata, dimension_hierarchy)
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
