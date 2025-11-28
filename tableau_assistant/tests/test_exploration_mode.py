#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
探索模式专项测试

专门测试 needs_exploration=true 的场景，验证:
1. Understanding 阶段正确识别探索意图
2. Task Planning 阶段自动选择合适的起始字段
3. 查询执行成功返回数据
"""
import os
import sys
from pathlib import Path
import asyncio
import json

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
from tableau_assistant.src.components.query_executor import QueryExecutor


# ============================================================================
# 探索模式测试用例
# ============================================================================

EXPLORATION_TEST_CASES = [
    {
        "id": "exploration_open",
        "name": "开放式探索 - 销售数据洞察",
        "question": "销售数据有什么洞察？",
        "expected": {
            "needs_exploration": True,
            "min_dimensions": 1,
            "min_measures": 1,
            "max_dimensions": 3,
            "max_measures": 3
        }
    },
    {
        "id": "exploration_trend",
        "name": "趋势探索 - 销售趋势分析",
        "question": "分析销售额的趋势",
        "expected": {
            "needs_exploration": True,
            "min_dimensions": 1,
            "min_measures": 1
        }
    },
    {
        "id": "exploration_compare",
        "name": "对比探索 - 省份表现对比",
        "question": "比较各省份的表现",
        "expected": {
            "needs_exploration": True,
            "min_dimensions": 1,
            "min_measures": 1
        }
    },
    {
        "id": "exploration_why",
        "name": "原因探索 - 为什么销售下降",
        "question": "为什么销售额下降了？",
        "expected": {
            "needs_exploration": True,
            "min_dimensions": 1,
            "min_measures": 1
        }
    },
    {
        "id": "exploration_pattern",
        "name": "模式探索 - 发现销售模式",
        "question": "销售数据中有什么模式？",
        "expected": {
            "needs_exploration": True,
            "min_dimensions": 1,
            "min_measures": 1
        }
    }
]


# ============================================================================
# 辅助函数
# ============================================================================

def print_header(text: str):
    """打印标题"""
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80)


def print_section(text: str):
    """打印章节"""
    print("\n" + "─" * 80)
    print(f"  {text}")
    print("─" * 80)


def print_success(text: str, indent: int = 0):
    """打印成功消息"""
    prefix = "  " * indent
    print(f"{prefix}✓ {text}")


def print_error(text: str, indent: int = 0):
    """打印错误消息"""
    prefix = "  " * indent
    print(f"{prefix}✗ {text}")


def print_info(text: str, indent: int = 0):
    """打印信息"""
    prefix = "  " * indent
    print(f"{prefix}{text}")


# ============================================================================
# 测试函数
# ============================================================================

async def test_exploration_case(test_case: dict, env: TestEnvironment, metadata, dimension_hierarchy, executor):
    """测试单个探索模式用例"""
    
    test_id = test_case["id"]
    test_name = test_case["name"]
    question = test_case["question"]
    expected = test_case["expected"]
    
    print_header(f"测试用例: {test_name}")
    print_info(f"ID: {test_id}")
    print_info(f"问题: {question}")
    
    results = {
        "id": test_id,
        "name": test_name,
        "question": question,
        "understanding": {"passed": False},
        "planning": {"passed": False},
        "execution": {"passed": False},
        "overall": False
    }
    
    try:
        # ====================================================================
        # 阶段 1: 问题理解
        # ====================================================================
        print_section("阶段 1: 问题理解")
        
        state = {
            "original_question": question,
            "question": question,
            "metadata": metadata,
            "dimension_hierarchy": dimension_hierarchy
        }
        
        understanding_result = await understanding_agent.execute(
            state=state,
            runtime=env.get_runtime()
        )
        state.update(understanding_result)
        
        print_success(f"问题理解完成")
        
        # 验证 needs_exploration 标志
        needs_exploration = False
        if state['understanding'].sub_questions:
            sq = state['understanding'].sub_questions[0]
            needs_exploration = getattr(sq, 'needs_exploration', False)
        
        exploration_check = needs_exploration == expected["needs_exploration"]
        
        if exploration_check:
            print_success(f"探索模式标志: {needs_exploration}", indent=1)
            results["understanding"]["passed"] = True
        else:
            print_error(f"探索模式标志错误: 期望 {expected['needs_exploration']}, 实际 {needs_exploration}", indent=1)
            return results
        
        # ====================================================================
        # 阶段 2: 任务规划
        # ====================================================================
        print_section("阶段 2: 任务规划")
        
        planning_result = await task_planner_agent.execute(
            state=state,
            runtime=env.get_runtime()
        )
        state.update(planning_result)
        
        print_success(f"任务规划完成")
        
        # 获取查询子任务
        query_subtasks = [st for st in state['query_plan'].subtasks if st.task_type == "query"]
        
        if not query_subtasks:
            print_error("没有生成查询子任务", indent=1)
            return results
        
        subtask = query_subtasks[0]
        
        # 验证字段选择
        dim_count = len(subtask.dimension_intents or [])
        measure_count = len(subtask.measure_intents or [])
        
        print_info(f"选择的维度数量: {dim_count}", indent=1)
        print_info(f"选择的度量数量: {measure_count}", indent=1)
        
        # 检查维度
        dim_check = dim_count >= expected["min_dimensions"]
        if "max_dimensions" in expected:
            dim_check = dim_check and dim_count <= expected["max_dimensions"]
        
        if dim_check:
            print_success(f"维度数量符合预期", indent=1)
        else:
            print_error(f"维度数量不符合预期: 期望 {expected['min_dimensions']}-{expected.get('max_dimensions', '∞')}, 实际 {dim_count}", indent=1)
            return results
        
        # 检查度量
        measure_check = measure_count >= expected["min_measures"]
        if "max_measures" in expected:
            measure_check = measure_check and measure_count <= expected["max_measures"]
        
        if measure_check:
            print_success(f"度量数量符合预期", indent=1)
            results["planning"]["passed"] = True
        else:
            print_error(f"度量数量不符合预期: 期望 {expected['min_measures']}-{expected.get('max_measures', '∞')}, 实际 {measure_count}", indent=1)
            return results
        
        # 显示选择的字段
        print_info("选择的维度:", indent=1)
        for dim in (subtask.dimension_intents or []):
            print_info(f"  - {dim.business_term} → {dim.technical_field}", indent=2)
        
        print_info("选择的度量:", indent=1)
        for measure in (subtask.measure_intents or []):
            print_info(f"  - {measure.business_term} → {measure.technical_field} ({measure.aggregation})", indent=2)
        
        # ====================================================================
        # 阶段 3: 查询执行
        # ====================================================================
        print_section("阶段 3: 查询执行")
        
        # 构建并执行查询
        from tableau_assistant.src.components.query_builder import QueryBuilder
        
        query_builder = QueryBuilder(metadata=metadata)
        vizql_query = query_builder.build_query(subtask)
        
        print_info(f"执行查询...", indent=1)
        
        exec_result = await executor.execute_query(vizql_query)
        
        if exec_result['success']:
            row_count = exec_result['row_count']
            col_count = len(exec_result['columns'])
            
            print_success(f"查询执行成功", indent=1)
            print_info(f"返回: {row_count} 行 x {col_count} 列", indent=2)
            
            # 显示数据样例
            if exec_result['data']:
                print_info("数据样例 (前3行):", indent=2)
                for i, row in enumerate(exec_result['data'][:3], 1):
                    print_info(f"{i}. {row}", indent=3)
            
            results["execution"]["passed"] = True
            results["overall"] = True
            
            print_success(f"✓ 测试用例 {test_id} 完全通过")
        else:
            print_error(f"查询执行失败: {exec_result.get('error', '未知错误')}", indent=1)
            return results
        
    except Exception as e:
        print_error(f"测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return results
    
    return results


async def run_exploration_tests():
    """运行所有探索模式测试"""
    
    print_header("探索模式专项测试")
    print_info(f"测试用例数量: {len(EXPLORATION_TEST_CASES)}")
    
    # 初始化测试环境
    print_section("初始化测试环境")
    env = TestEnvironment()
    await env.setup()
    print_success("测试环境初始化完成")
    
    # 获取必要的环境信息
    metadata = await env.get_metadata_manager().get_metadata_async()
    dimension_hierarchy = metadata.dimension_hierarchy or {}
    
    print_success(f"数据源: {env.get_datasource_luid()}")
    print_success(f"字段数量: {len(metadata.fields)}")
    
    # 创建查询执行器
    executor = QueryExecutor(metadata=metadata)
    
    # 运行测试
    all_results = []
    passed_count = 0
    
    for i, test_case in enumerate(EXPLORATION_TEST_CASES, 1):
        print(f"\n{'='*80}")
        print(f"  进度: {i}/{len(EXPLORATION_TEST_CASES)}")
        print(f"{'='*80}")
        
        result = await test_exploration_case(test_case, env, metadata, dimension_hierarchy, executor)
        all_results.append(result)
        
        if result["overall"]:
            passed_count += 1
    
    # 清理环境
    print_section("清理测试环境")
    await env.teardown()
    print_success("测试环境清理完成")
    
    # 打印总结
    print_header("测试总结")
    print_info(f"总测试数: {len(EXPLORATION_TEST_CASES)}")
    print_info(f"通过数: {passed_count}/{len(EXPLORATION_TEST_CASES)} ({passed_count/len(EXPLORATION_TEST_CASES)*100:.1f}%)")
    
    print("\n详细结果:")
    for result in all_results:
        status = "✓" if result["overall"] else "✗"
        print(f"  {status} {result['id']}: {result['name']}")
        print(f"     - 问题理解: {'✓' if result['understanding']['passed'] else '✗'}")
        print(f"     - 任务规划: {'✓' if result['planning']['passed'] else '✗'}")
        print(f"     - 查询执行: {'✓' if result['execution']['passed'] else '✗'}")
    
    # 保存结果
    output_file = "test_exploration_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存到: {output_file}")
    
    return passed_count == len(EXPLORATION_TEST_CASES)


# ============================================================================
# 主入口
# ============================================================================

if __name__ == "__main__":
    success = asyncio.run(run_exploration_tests())
    sys.exit(0 if success else 1)
