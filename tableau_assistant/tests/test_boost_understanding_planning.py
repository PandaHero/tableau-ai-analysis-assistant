#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
端到端测试：Question Boost → Understanding → Task Planning

测试完整的问题处理流程：
1. 问题增强（Question Boost）
2. 问题理解（Understanding）
3. 任务规划（Task Planning）
"""
import os
import sys
from pathlib import Path
import asyncio
import json
import time

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
from tableau_assistant.src.agents.question_boost_agent import question_boost_agent
from tableau_assistant.src.agents.understanding_agent import understanding_agent
from tableau_assistant.src.agents.task_planner_agent import task_planner_agent


async def test_end_to_end_pipeline():
    """测试完整的问题处理流程"""
    print("\n" + "=" * 80)
    print("端到端测试：Question Boost → Understanding → Task Planning")
    print("=" * 80)
    
    # 初始化测试环境
    print("\n[1/6] 初始化测试环境...")
    env = TestEnvironment(use_persistent_store=True)
    await env.setup()
    print("✓ 环境初始化完成")
    
    # 获取元数据和维度层级
    print("\n[2/6] 获取元数据和维度层级...")
    step_start = time.time()
    metadata = await env.metadata_manager.get_metadata_async()
    dimension_hierarchy = metadata.dimension_hierarchy or {}
    step_time = time.time() - step_start
    
    print(f"✓ 元数据获取完成 (耗时: {step_time:.2f}秒)")
    print(f"  - 字段总数: {len(metadata.fields)}")
    print(f"  - 维度层级类别: {len(dimension_hierarchy)}")
    
    # 测试问题
    test_questions = [
        # "最近一个月各省份的销售额是多少",
        # "对比今年春节期间每天和去年春节期间每天各门店的销售额",
        "显示各产品类别的销售额和利润，按销售额降序排列",
        "哪个门店的利润最高?为什么?"
    ]
    
    for i, original_question in enumerate(test_questions, 1):
        print("\n" + "=" * 80)
        print(f"测试问题 {i}/{len(test_questions)}: {original_question}")
        print("=" * 80)
        
        # 初始化状态
        state = {
            "original_question": original_question,
            "question": original_question,
            "metadata": metadata,
            "dimension_hierarchy": dimension_hierarchy
        }
        
        # Step 1: Question Boost
        print(f"\n[3/6] 问题增强...")
        step_start = time.time()
        boost_result = await question_boost_agent.execute(state, env.runtime)
        step_time = time.time() - step_start
        
        boost = boost_result.get("boost")
        if boost:
            print(f"✓ 问题增强完成 (耗时: {step_time:.2f}秒)")
            print(f"  - 是否数据分析问题: {boost.is_data_analysis_question}")
            if boost.is_data_analysis_question:
                print(f"  - 原始问题: {boost.original_question}")
                print(f"  - 增强问题: {boost.boosted_question}")
                if boost.changes:
                    print(f"  - 变更数量: {len(boost.changes)}")
                    for change in boost.changes[:2]:
                        print(f"    * {change}")
                
                # 更新状态
                state["boost"] = boost
                state["boosted_question"] = boost.boosted_question
            else:
                print(f"  - 非数据分析问题，跳过后续步骤")
                continue
        else:
            print(f"✗ 问题增强失败")
            continue
        
        # Step 2: Understanding
        print(f"\n[4/6] 问题理解...")
        step_start = time.time()
        understanding_result = await understanding_agent.execute(state, env.runtime)
        step_time = time.time() - step_start
        
        understanding = understanding_result.get("understanding")
        if understanding:
            print(f"✓ 问题理解完成 (耗时: {step_time:.2f}秒)")
            print(f"  - 是否有效问题: {understanding.is_valid_question}")
            
            if understanding.is_valid_question:
                print(f"  - 问题类型: {understanding.question_type}")
                print(f"  - 复杂度: {understanding.complexity}")
                print(f"  - 子问题数量: {len(understanding.sub_questions)}")
                
                for j, sub_q in enumerate(understanding.sub_questions, 1):
                    exec_type = sub_q.execution_type
                    print(f"    {j}. [{exec_type}] {sub_q.text}")
                    if sub_q.depends_on_indices:
                        print(f"       依赖: {sub_q.depends_on_indices}")
                    
                    # 显示子问题的字段信息（仅对 query 类型）
                    if exec_type == "query":
                        if sub_q.mentioned_dimensions:
                            print(f"       维度: {sub_q.mentioned_dimensions}")
                        if sub_q.mentioned_measures:
                            print(f"       度量: {sub_q.mentioned_measures}")
                        if sub_q.mentioned_date_fields:
                            print(f"       日期字段: {sub_q.mentioned_date_fields}")
                        if sub_q.time_range:
                            print(f"       时间范围: {sub_q.time_range.type}")
                    elif exec_type == "post_processing":
                        print(f"       处理类型: {sub_q.processing_type}")
                
                # 更新状态
                state["understanding"] = understanding
            else:
                print(f"  - 无效问题: {understanding.invalid_reason}")
                continue
        else:
            print(f"✗ 问题理解失败")
            continue
        
        # Step 3: Task Planning
        print(f"\n[5/6] 任务规划...")
        step_start = time.time()
        planning_result = await task_planner_agent.execute(state, env.runtime)
        step_time = time.time() - step_start
        
        query_plan = planning_result.get("query_plan")
        if query_plan:
            print(f"✓ 任务规划完成 (耗时: {step_time:.2f}秒)")
            print(f"  - 子任务数量: {len(query_plan.subtasks)}")
            print(f"  - 复杂度: {query_plan.complexity}")
            print(f"  - 预估行数: {query_plan.estimated_rows}")
            
            # 分析每个子任务
            for k, subtask in enumerate(query_plan.subtasks, 1):
                print(f"\n  子任务 {k}: {subtask.question_text}")
                print(f"    - 问题ID: {subtask.question_id}")
                print(f"    - 任务类型: {subtask.task_type}")
                print(f"    - Stage: {subtask.stage}")
                
                # 根据任务类型显示不同的信息
                if subtask.task_type == "query":
                    # QuerySubTask - 显示 Intent 信息
                    if subtask.dimension_intents:
                        print(f"    - Dimension Intents ({len(subtask.dimension_intents)}):")
                        for intent in subtask.dimension_intents:
                            agg = f", agg={intent.aggregation}" if intent.aggregation else ""
                            sort = f", sort={intent.sort_direction}" if intent.sort_direction else ""
                            print(f"      * {intent.business_term} → {intent.technical_field}{agg}{sort}")
                    
                    if subtask.measure_intents:
                        print(f"    - Measure Intents ({len(subtask.measure_intents)}):")
                        for intent in subtask.measure_intents:
                            sort = f", sort={intent.sort_direction}" if intent.sort_direction else ""
                            print(f"      * {intent.business_term} → {intent.technical_field} (agg={intent.aggregation}{sort})")
                    
                    if subtask.date_field_intents:
                        print(f"    - Date Field Intents ({len(subtask.date_field_intents)}):")
                        for intent in subtask.date_field_intents:
                            func = f", func={intent.date_function}" if intent.date_function else ""
                            print(f"      * {intent.business_term} → {intent.technical_field}{func}")
                    
                    if subtask.date_filter_intent:
                        dfi = subtask.date_filter_intent
                        print(f"    - Date Filter Intent:")
                        print(f"      * {dfi.business_term} → {dfi.technical_field}")
                        if dfi.time_range:
                            tr = dfi.time_range
                            print(f"        time_range: {tr.type}, {tr.relative_type}, {tr.period_type}/{tr.range_n}")
                    
                    if subtask.filter_intents:
                        print(f"    - Filter Intents ({len(subtask.filter_intents)}):")
                        for intent in subtask.filter_intents:
                            print(f"      * {intent.business_term} → {intent.technical_field} ({intent.filter_type})")
                    
                    if subtask.topn_intent:
                        ti = subtask.topn_intent
                        print(f"    - TopN Intent:")
                        print(f"      * {ti.business_term} → {ti.technical_field} (n={ti.n}, dir={ti.direction})")
                
                elif subtask.task_type == "post_processing":
                    # ProcessingSubTask - 显示处理指令
                    instruction = subtask.processing_instruction
                    print(f"    - 处理类型: {instruction.processing_type}")
                    print(f"    - 源任务: {instruction.source_tasks}")
                    if instruction.calculation_formula:
                        print(f"    - 计算公式: {instruction.calculation_formula}")
                
                # 依赖关系
                if subtask.depends_on:
                    print(f"    - 依赖: {subtask.depends_on}")
                
                # 推理说明
                if subtask.rationale:
                    print(f"    - 推理: {subtask.rationale[:100]}...")
            
            # 保存完整结果到文件（用于调试）
            output_file = f"test_output_q{i}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                output_data = {
                    "original_question": original_question,
                    "boost": boost.model_dump() if boost else None,
                    "understanding": understanding.model_dump() if understanding else None,
                    "query_plan": query_plan.model_dump() if query_plan else None
                }
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            
            print(f"\n  ✓ 完整结果已保存到: {output_file}")
            
        else:
            print(f"✗ 任务规划失败")
            if "error" in planning_result:
                print(f"  错误: {planning_result['error']}")
    
    # 清理环境
    print("\n" + "=" * 80)
    print("[6/6] 清理测试环境...")
    # await env.teardown()  # 注释掉，保留缓存供下一个测试使用
    print("✓ 测试完成（缓存已保留）")
    print("=" * 80)


async def test_simple_question():
    """测试简单问题（不需要拆分）"""
    print("\n\n" + "=" * 80)
    print("测试简单问题（不需要拆分）")
    print("=" * 80)
    
    env = TestEnvironment(use_persistent_store=True)
    await env.setup()
    
    metadata = await env.metadata_manager.get_metadata_async()
    dimension_hierarchy = metadata.dimension_hierarchy or {}
    
    question = "哪个门店的利润最高?为什么?"
    print(f"\n问题: {question}")
    
    state = {
        "original_question": question,
        "question": question,
        "metadata": metadata,
        "dimension_hierarchy": dimension_hierarchy
    }
    
    # Boost
    print("\n[1/3] 问题增强...")
    boost_result = await question_boost_agent.execute(state, env.runtime)
    boost = boost_result.get("boost")
    if boost and boost.is_data_analysis_question:
        state["boost"] = boost
        state["boosted_question"] = boost.boosted_question
        print(f"✓ 增强问题: {boost.boosted_question}")
    
    # Understanding
    print("\n[2/3] 问题理解...")
    understanding_result = await understanding_agent.execute(state, env.runtime)
    understanding = understanding_result.get("understanding")
    if understanding and understanding.is_valid_question:
        state["understanding"] = understanding
        print(f"✓ 子问题数量: {len(understanding.sub_questions)}")
        print(f"  复杂度: {understanding.complexity}")
    
    # Planning
    print("\n[3/3] 任务规划...")
    planning_result = await task_planner_agent.execute(state, env.runtime)
    query_plan = planning_result.get("query_plan")
    if query_plan:
        print(f"✓ 子任务数量: {len(query_plan.subtasks)}")
        print(f"  复杂度: {query_plan.complexity}")
        
        # 显示第一个子任务的 Intent 信息
        if query_plan.subtasks:
            subtask = query_plan.subtasks[0]
            if subtask.task_type == "query":
                print(f"\n  Intent 列表:")
                if subtask.dimension_intents:
                    for intent in subtask.dimension_intents:
                        print(f"    - [Dimension] {intent.business_term} → {intent.technical_field}")
                if subtask.measure_intents:
                    for intent in subtask.measure_intents:
                        print(f"    - [Measure] {intent.business_term} → {intent.technical_field} (agg={intent.aggregation})")
                if subtask.date_field_intents:
                    for intent in subtask.date_field_intents:
                        print(f"    - [DateField] {intent.business_term} → {intent.technical_field}")
    
    await env.teardown()  # 注释掉，避免清除缓存
    print("\n✓ 测试完成")


if __name__ == "__main__":
    # 运行端到端测试
    asyncio.run(test_end_to_end_pipeline())
    
    # 运行简单问题测试
    asyncio.run(test_simple_question())
