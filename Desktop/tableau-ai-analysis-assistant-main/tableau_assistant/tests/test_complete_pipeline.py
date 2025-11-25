#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
完整流程测试套件

测试从问题理解到查询执行的完整流程，覆盖所有可能场景：
1. 问题理解（Understanding）
2. 任务规划（Task Planning）
3. 查询构建（Query Building）
4. 查询执行（Query Execution）

使用真实环境和真实数据，每个节点严格测试。
"""
import os
import sys
from pathlib import Path
import asyncio
import json
import time
from datetime import datetime
from typing import List, Dict, Any

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
from tableau_assistant.src.components.query_executor import QueryExecutor


# ============================================================================
# 测试用例定义
# ============================================================================

TEST_CASES = [
    # Scenario 1: Simple query (1 dimension + 1 measure)
    {
        "id": "simple_1d_1m",
        "name": "Simple Query - Sales by Province",
        "question": "显示各省份的销售额",
        "expected": {
            "question_type": ["排名"],
            "complexity": "Simple",
            "min_dimensions": 1,
            "min_measures": 1,
            "min_rows": 5
        }
    },
    
    # Scenario 2: Multi-dimension query
    {
        "id": "multi_dimension",
        "name": "Multi-Dimension - Sales by Province and Channel",
        "question": "显示各省份各渠道的销售额",
        "expected": {
            "question_type": ["多维分解"],
            "complexity": "Medium",
            "min_dimensions": 2,
            "min_measures": 1,
            "min_rows": 10
        }
    },
    
    # Scenario 3: Multi-measure query
    {
        "id": "multi_measure",
        "name": "Multi-Measure - Sales and Profit by Province",
        "question": "显示各省份的销售额和利润",
        "expected": {
            "question_type": ["对比"],
            "complexity": "Simple",
            "min_dimensions": 1,
            "min_measures": 2,
            "min_rows": 5
        }
    },
    
    # Scenario 4: Sorting query
    {
        "id": "sorting",
        "name": "Sorting - Province with Highest Sales",
        "question": "哪个省份的销售额最高？",
        "expected": {
            "question_type": ["排名"],
            "complexity": "Simple",
            "min_dimensions": 1,
            "min_measures": 1,
            "min_rows": 1
        }
    },
    
    # Scenario 5: Top N query
    {
        "id": "topn",
        "name": "Top N - Top 5 Provinces by Sales",
        "question": "销售额前5的省份是哪些？",
        "expected": {
            "question_type": ["排名"],
            "complexity": "Simple",
            "min_dimensions": 1,
            "min_measures": 1,
            "max_rows": 5
        }
    },
    
    # Scenario 6: Date filter query (relative date)
    {
        "id": "date_filter_relative",
        "name": "Date Filter - Last Month Sales by Province",
        "question": "最近一个月各省份的销售额是多少？",
        "expected": {
            "question_type": ["趋势"],
            "complexity": "Medium",
            "min_dimensions": 1,
            "min_measures": 1,
            "has_date_filter": True
        }
    },
    
    # Scenario 7: Date dimension query
    {
        "id": "date_dimension",
        "name": "Date Dimension - Monthly Sales",
        "question": "显示每月的销售额",
        "expected": {
            "question_type": ["趋势"],
            "complexity": "Simple",
            "min_dimensions": 1,
            "min_measures": 1,
            "has_date_dimension": True
        }
    },
    
    # Scenario 8: Aggregation query
    {
        "id": "aggregation",
        "name": "Aggregation - Total Sales",
        "question": "总销售额是多少？",
        "expected": {
            "question_type": ["汇总"],
            "complexity": "Simple",
            "min_dimensions": 0,
            "min_measures": 1,
            "max_rows": 1
        }
    },
    
    # Scenario 9: Complex multi-dimension multi-measure
    {
        "id": "complex_multi",
        "name": "Complex - Sales and Profit by Province and Store",
        "question": "显示各省份各门店的销售额和利润",
        "expected": {
            "question_type": ["多维分解"],
            "complexity": "Medium",
            "min_dimensions": 2,
            "min_measures": 2,
            "min_rows": 20
        }
    },
    
    # Scenario 10: Diagnostic query
    {
        "id": "diagnostic",
        "name": "Diagnostic - Store with Highest Profit",
        "question": "哪个门店的利润最高？",
        "expected": {
            "question_type": ["排名", "诊断"],
            "complexity": "Simple",
            "min_dimensions": 1,
            "min_measures": 1,
            "min_rows": 1
        }
    },
    
    # ========================================================================
    # 维度聚合逻辑测试用例（针对fix-dimension-aggregation-logic）
    # ========================================================================
    
    # Scenario 11: Grouping dimension (no aggregation)
    {
        "id": "grouping_dimension",
        "name": "Grouping Dimension - Sales by Province (No Aggregation)",
        "question": "各省份的销售额是多少？",
        "expected": {
            "question_type": ["排名"],
            "complexity": "Simple",
            "min_dimensions": 1,
            "min_measures": 1,
            "dimension_aggregations": {},  # 分组维度不应有聚合
            "vizql_check": {
                "grouping_dimensions": ["pro_name"],  # 这些维度不应有function
                "aggregated_measures": ["收入"]  # 这些度量必须有function
            }
        }
    },
    
    # Scenario 12: Counted dimension (with COUNTD aggregation)
    {
        "id": "counted_dimension",
        "name": "Counted Dimension - Store Count by Province",
        "question": "每个省份有多少个门店？",
        "expected": {
            "question_type": ["汇总"],
            "complexity": "Simple",
            "min_dimensions": 2,  # 省份（分组） + 门店（计数）
            "min_measures": 0,
            "dimension_aggregations": {"门店": "COUNTD"},  # 门店应有COUNTD聚合
            "vizql_check": {
                "grouping_dimensions": ["pro_name"],  # 省份不应有function
                "counted_dimensions": ["门店编码"]  # 门店应有COUNTD function
            }
        }
    },
    
    # Scenario 13: Mixed - Grouping and counted dimensions
    {
        "id": "mixed_dimensions",
        "name": "Mixed Dimensions - Product Count by Province and Channel",
        "question": "各省份各渠道有多少个产品？",
        "expected": {
            "question_type": ["多维分解"],
            "complexity": "Medium",
            "min_dimensions": 3,  # 省份（分组） + 渠道（分组） + 产品（计数）
            "min_measures": 0,
            "dimension_aggregations": {"产品": "COUNTD"},
            "vizql_check": {
                "grouping_dimensions": ["pro_name", "渠道"],  # 这些不应有function
                "counted_dimensions": ["产品"]  # 产品应有COUNTD function
            }
        }
    },
    
    # Scenario 14: Multi-dimension grouping (all for GROUP BY)
    {
        "id": "multi_dimension_grouping",
        "name": "Multi-Dimension Grouping - Sales by Province and Store",
        "question": "各省份各门店的销售额",
        "expected": {
            "question_type": ["多维分解"],
            "complexity": "Medium",
            "min_dimensions": 2,
            "min_measures": 1,
            "dimension_aggregations": {},  # 所有维度都是分组，不应有聚合
            "vizql_check": {
                "grouping_dimensions": ["pro_name", "门店编码"],  # 都不应有function
                "aggregated_measures": ["收入"]
            }
        }
    },
    
    # Scenario 15: TopN with grouping dimension
    {
        "id": "topn_grouping",
        "name": "TopN with Grouping - Top 5 Provinces by Sales",
        "question": "销售额前5的省份",
        "expected": {
            "question_type": ["排名"],
            "complexity": "Simple",
            "min_dimensions": 1,
            "min_measures": 1,
            "max_rows": 5,
            "dimension_aggregations": {},  # 省份是分组维度
            "vizql_check": {
                "grouping_dimensions": ["pro_name"],
                "aggregated_measures": ["收入"],
                "has_topn": True
            }
        }
    },
    
    # ========================================================================
    # 日期场景扩展测试（更多日期组合）
    # ========================================================================
    
    # Scenario 16: Date dimension + Date filter (same field)
    {
        "id": "date_dimension_and_filter",
        "name": "Date Dimension + Filter - 2024 Monthly Sales",
        "question": "2024年每月的销售额",
        "expected": {
            "question_type": ["趋势"],
            "complexity": "Medium",
            "min_dimensions": 1,
            "min_measures": 1,
            "has_date_dimension": True,
            "has_date_filter": True
        }
    },
    
    # Scenario 17: Multiple date functions (Year + Month)
    {
        "id": "multi_date_functions",
        "name": "Multiple Date Functions - Sales by Year and Month",
        "question": "显示每年每月的销售额",
        "expected": {
            "question_type": ["趋势"],
            "complexity": "Medium",
            "min_dimensions": 2,  # 年 + 月
            "min_measures": 1,
            "has_date_dimension": True
        }
    },
    
    # Scenario 18: Date filter with absolute date (specific month)
    {
        "id": "date_filter_absolute_month",
        "name": "Date Filter Absolute - September 2024 Sales",
        "question": "2024年9月的销售额",
        "expected": {
            "question_type": ["趋势"],
            "complexity": "Simple",
            "min_measures": 1,
            "has_date_filter": True
        }
    },
    
    # Scenario 19: Date filter with relative date (last quarter)
    {
        "id": "date_filter_last_quarter",
        "name": "Date Filter Relative - Last Quarter Sales",
        "question": "上个季度的销售额",
        "expected": {
            "question_type": ["趋势"],
            "complexity": "Simple",
            "min_measures": 1,
            "has_date_filter": True
        }
    },
    
    # Scenario 20: Date dimension with multiple dimensions
    {
        "id": "date_with_multi_dimensions",
        "name": "Date + Multi Dimensions - Monthly Sales by Province and Channel",
        "question": "各省份各渠道每月的销售额",
        "expected": {
            "question_type": ["趋势", "多维分解"],
            "complexity": "High",
            "min_dimensions": 3,  # 省份 + 渠道 + 月份
            "min_measures": 1,
            "has_date_dimension": True
        }
    },
    
    # Scenario 21: Quarter dimension
    {
        "id": "date_quarter_dimension",
        "name": "Date Quarter - Quarterly Sales",
        "question": "显示每季度的销售额",
        "expected": {
            "question_type": ["趋势"],
            "complexity": "Simple",
            "min_dimensions": 1,
            "min_measures": 1,
            "has_date_dimension": True
        }
    },
    
    # ========================================================================
    # 高复杂度查询测试
    # ========================================================================
    
    # Scenario 22: Complex - TopN with multiple dimensions and date filter
    {
        "id": "complex_topn_date",
        "name": "Complex TopN - Top 10 Stores by Sales in Last Month",
        "question": "最近一个月销售额前10的门店",
        "expected": {
            "question_type": ["排名"],
            "complexity": "High",
            "min_dimensions": 1,
            "min_measures": 1,
            "max_rows": 10,
            "has_date_filter": True
        }
    },
    
    # Scenario 23: Complex - Multiple measures with date dimension and filter
    {
        "id": "complex_multi_measure_date",
        "name": "Complex Multi-Measure - 2024 Monthly Sales and Profit by Province",
        "question": "2024年各省份每月的销售额和利润",
        "expected": {
            "question_type": ["趋势", "对比"],
            "complexity": "High",
            "min_dimensions": 2,  # 省份 + 月份
            "min_measures": 2,  # 销售额 + 利润
            "has_date_dimension": True,
            "has_date_filter": True
        }
    },
    
    # Scenario 24: Complex - Counted dimension with date filter
    {
        "id": "complex_count_date",
        "name": "Complex Count - Product Count by Province in Last Month",
        "question": "最近一个月各省份有多少个产品？",
        "expected": {
            "question_type": ["多维分解"],
            "complexity": "High",
            "min_dimensions": 2,  # 省份 + 产品（计数）
            "has_date_filter": True,
            "dimension_aggregations": {"产品": "COUNTD"}
        }
    },
    
    # Scenario 25: Complex - Multi-dimension with TopN and sorting
    {
        "id": "complex_multi_dim_topn",
        "name": "Complex Multi-Dim TopN - Top 5 Province-Channel by Sales",
        "question": "销售额前5的省份渠道组合",
        "expected": {
            "question_type": ["排名"],
            "complexity": "High",
            "min_dimensions": 2,  # 省份 + 渠道
            "min_measures": 1,
            "max_rows": 5
        }
    },
    
    # Scenario 26: Complex - Aggregation with multiple dimensions
    {
        "id": "complex_agg_multi_dim",
        "name": "Complex Aggregation - Average Sales by Province and Store Type",
        "question": "各省份各渠道的平均销售额",
        "expected": {
            "question_type": ["对比"],
            "complexity": "Medium",
            "min_dimensions": 2,
            "min_measures": 1
        }
    },
    
    # ========================================================================
    # 探索模式测试（needs_exploration）
    # ========================================================================
    
    # Scenario 27: Exploration - Open-ended question
    {
        "id": "exploration_open",
        "name": "Exploration - What insights about sales?",
        "question": "销售数据有什么洞察？",
        "expected": {
            "question_type": ["探索"],
            "complexity": "High",
            "needs_exploration": True
        }
    },
    
    # Scenario 28: Exploration - Trend analysis
    {
        "id": "exploration_trend",
        "name": "Exploration - Sales trend analysis",
        "question": "分析销售额的趋势",
        "expected": {
            "question_type": ["趋势", "探索"],
            "complexity": "High",
            "needs_exploration": True
        }
    },
    
    # Scenario 29: Exploration - Comparison request
    {
        "id": "exploration_compare",
        "name": "Exploration - Compare provinces performance",
        "question": "比较各省份的表现",
        "expected": {
            "question_type": ["对比", "探索"],
            "complexity": "High",
            "needs_exploration": True
        }
    },
    
    # ========================================================================
    # 边界情况和特殊场景
    # ========================================================================
    
    # Scenario 30: Empty result - Filter with no matches
    {
        "id": "edge_empty_result",
        "name": "Edge Case - Query with potentially empty result",
        "question": "2030年的销售额",
        "expected": {
            "question_type": ["趋势"],
            "complexity": "Simple",
            "min_measures": 1,
            "has_date_filter": True,
            "allow_empty": True
        }
    },
    
    # Scenario 31: Very specific filter
    {
        "id": "edge_specific_filter",
        "name": "Edge Case - Very specific province and channel",
        "question": "广东省O2O渠道的销售额",
        "expected": {
            "question_type": ["筛选"],
            "complexity": "Simple",
            "min_dimensions": 2,
            "min_measures": 1
        }
    },
    
    # Scenario 32: Multiple aggregations on same dimension
    {
        "id": "edge_multi_agg",
        "name": "Edge Case - Min and Max sales by province",
        "question": "各省份的最高和最低销售额",
        "expected": {
            "question_type": ["对比"],
            "complexity": "Medium",
            "min_dimensions": 1,
            "min_measures": 2
        }
    },
    
    # Scenario 33: Complex date range
    {
        "id": "edge_date_range",
        "name": "Edge Case - Specific date range",
        "question": "2024年1月到3月的销售额",
        "expected": {
            "question_type": ["趋势"],
            "complexity": "Medium",
            "min_measures": 1,
            "has_date_filter": True
        }
    },
    
    # Scenario 34: Nested grouping with count
    {
        "id": "edge_nested_count",
        "name": "Edge Case - Count stores and products by province",
        "question": "各省份有多少个门店和多少个产品？",
        "expected": {
            "question_type": ["多维分解"],
            "complexity": "High",
            "min_dimensions": 3,  # 省份 + 门店（计数） + 产品（计数）
            "dimension_aggregations": {"门店": "COUNTD", "产品": "COUNTD"}
        }
    },
    
    # Scenario 35: Year-over-year comparison (may need post-processing)
    {
        "id": "edge_yoy",
        "name": "Edge Case - Year over year sales comparison",
        "question": "2024年和2023年的销售额对比",
        "expected": {
            "question_type": ["对比", "趋势"],
            "complexity": "High",
            "min_measures": 1,
            "has_date_filter": True
        }
    },
]


# ============================================================================
# 辅助函数
# ============================================================================

def print_header(text: str, level: int = 1):
    """打印标题"""
    if level == 1:
        print("\n" + "=" * 100)
        print(f"  {text}")
        print("=" * 100)
    elif level == 2:
        print("\n" + "─" * 100)
        print(f"  {text}")
        print("─" * 100)
    else:
        print(f"\n  {text}")
        print("  " + "·" * 80)


def print_success(text: str, indent: int = 0):
    """打印成功消息"""
    prefix = "  " * indent
    print(f"{prefix}✓ {text}")


def print_error(text: str, indent: int = 0):
    """打印错误消息"""
    prefix = "  " * indent
    print(f"{prefix}✗ {text}")


def print_warning(text: str, indent: int = 0):
    """打印警告消息"""
    prefix = "  " * indent
    print(f"{prefix}⚠ {text}")


def print_info(text: str, indent: int = 0):
    """打印信息"""
    prefix = "  " * indent
    print(f"{prefix}{text}")


def validate_understanding(understanding, expected: Dict) -> Dict[str, Any]:
    """验证问题理解结果"""
    results = {
        "passed": True,
        "checks": []
    }
    
    # 检查是否有效问题
    if not understanding.is_valid_question:
        results["passed"] = False
        results["checks"].append({
            "name": "有效问题检查",
            "passed": False,
            "message": "问题被判定为无效"
        })
        return results
    
    results["checks"].append({
        "name": "有效问题检查",
        "passed": True,
        "message": "问题有效"
    })
    
    # 检查问题类型
    if "question_type" in expected:
        expected_types = expected["question_type"]
        actual_types = [qt.value for qt in understanding.question_type]
        type_match = any(et in actual_types for et in expected_types)
        
        results["checks"].append({
            "name": "问题类型检查",
            "passed": type_match,
            "expected": expected_types,
            "actual": actual_types
        })
        
        if not type_match:
            results["passed"] = False
    
    # 检查复杂度
    if "complexity" in expected:
        complexity_match = understanding.complexity.value == expected["complexity"]
        results["checks"].append({
            "name": "复杂度检查",
            "passed": complexity_match,
            "expected": expected["complexity"],
            "actual": understanding.complexity.value
        })
    
    # 检查子问题数量
    sub_question_count = len(understanding.sub_questions)
    results["checks"].append({
        "name": "子问题数量",
        "passed": True,
        "value": sub_question_count
    })
    
    # 检查探索模式
    if "needs_exploration" in expected:
        expected_exploration = expected["needs_exploration"]
        # 检查第一个子问题的needs_exploration标志
        actual_exploration = False
        if understanding.sub_questions:
            sq = understanding.sub_questions[0]
            actual_exploration = getattr(sq, 'needs_exploration', False)
        
        exploration_match = actual_exploration == expected_exploration
        results["checks"].append({
            "name": "探索模式检查",
            "passed": exploration_match,
            "expected": expected_exploration,
            "actual": actual_exploration
        })
        
        if not exploration_match:
            results["passed"] = False
    
    # 检查维度聚合（针对fix-dimension-aggregation-logic）
    if "dimension_aggregations" in expected:
        expected_aggs = expected["dimension_aggregations"]
        
        # 检查第一个query类型的子问题
        for sq in understanding.sub_questions:
            if hasattr(sq, 'dimension_aggregations'):
                actual_aggs = sq.dimension_aggregations or {}
                
                # 检查是否匹配
                aggs_match = actual_aggs == expected_aggs
                
                results["checks"].append({
                    "name": "维度聚合检查",
                    "passed": aggs_match,
                    "expected": expected_aggs,
                    "actual": actual_aggs,
                    "message": f"Expected: {expected_aggs}, Got: {actual_aggs}"
                })
                
                if not aggs_match:
                    results["passed"] = False
                
                break  # 只检查第一个query子问题
    
    return results


def validate_planning(query_plan, expected: Dict) -> Dict[str, Any]:
    """验证任务规划结果"""
    results = {
        "passed": True,
        "checks": []
    }
    
    # 获取查询类型的子任务
    query_subtasks = [st for st in query_plan.subtasks if st.task_type == "query"]
    
    if not query_subtasks:
        results["passed"] = False
        results["checks"].append({
            "name": "查询子任务检查",
            "passed": False,
            "message": "没有查询类型的子任务"
        })
        return results
    
    # 检查第一个查询子任务
    subtask = query_subtasks[0]
    
    # 检查维度数量
    if "min_dimensions" in expected:
        dim_count = len(subtask.dimension_intents or [])
        passed = dim_count >= expected["min_dimensions"]
        results["checks"].append({
            "name": "维度数量检查",
            "passed": passed,
            "expected": f">= {expected['min_dimensions']}",
            "actual": dim_count
        })
        if not passed:
            results["passed"] = False
    
    # 检查度量数量
    if "min_measures" in expected:
        measure_count = len(subtask.measure_intents or [])
        passed = measure_count >= expected["min_measures"]
        results["checks"].append({
            "name": "度量数量检查",
            "passed": passed,
            "expected": f">= {expected['min_measures']}",
            "actual": measure_count
        })
        if not passed:
            results["passed"] = False
    
    # 检查日期筛选
    if expected.get("has_date_filter"):
        has_filter = subtask.date_filter_intent is not None
        results["checks"].append({
            "name": "日期筛选检查",
            "passed": has_filter,
            "expected": "有日期筛选",
            "actual": "有" if has_filter else "无"
        })
        if not has_filter:
            results["passed"] = False
    
    # 检查日期维度
    if expected.get("has_date_dimension"):
        has_date_dim = any(
            d.field_data_type in ["DATE", "DATETIME"] or "日期" in d.technical_field
            for d in (subtask.dimension_intents or [])
        )
        results["checks"].append({
            "name": "日期维度检查",
            "passed": has_date_dim,
            "expected": "有日期维度",
            "actual": "有" if has_date_dim else "无"
        })
        if not has_date_dim:
            results["passed"] = False
    
    # 检查DimensionIntent的aggregation字段（针对fix-dimension-aggregation-logic）
    if "vizql_check" in expected:
        vizql_check = expected["vizql_check"]
        
        # 检查分组维度（不应有aggregation）
        if "grouping_dimensions" in vizql_check:
            expected_grouping = vizql_check["grouping_dimensions"]
            for dim_intent in (subtask.dimension_intents or []):
                if dim_intent.technical_field in expected_grouping:
                    passed = dim_intent.aggregation is None
                    results["checks"].append({
                        "name": f"分组维度检查 - {dim_intent.technical_field}",
                        "passed": passed,
                        "expected": "aggregation=None (无聚合)",
                        "actual": f"aggregation={dim_intent.aggregation}",
                        "message": f"分组维度 {dim_intent.technical_field} 不应有聚合函数"
                    })
                    if not passed:
                        results["passed"] = False
        
        # 检查计数维度（应有COUNTD aggregation）
        if "counted_dimensions" in vizql_check:
            expected_counted = vizql_check["counted_dimensions"]
            for dim_intent in (subtask.dimension_intents or []):
                if dim_intent.technical_field in expected_counted:
                    passed = dim_intent.aggregation == "COUNTD"
                    results["checks"].append({
                        "name": f"计数维度检查 - {dim_intent.technical_field}",
                        "passed": passed,
                        "expected": "aggregation='COUNTD'",
                        "actual": f"aggregation={dim_intent.aggregation}",
                        "message": f"计数维度 {dim_intent.technical_field} 应有COUNTD聚合"
                    })
                    if not passed:
                        results["passed"] = False
        
        # 检查度量（必须有aggregation）
        if "aggregated_measures" in vizql_check:
            expected_measures = vizql_check["aggregated_measures"]
            for measure_intent in (subtask.measure_intents or []):
                if measure_intent.technical_field in expected_measures:
                    passed = measure_intent.aggregation is not None
                    results["checks"].append({
                        "name": f"度量聚合检查 - {measure_intent.technical_field}",
                        "passed": passed,
                        "expected": "aggregation!=None (必须有聚合)",
                        "actual": f"aggregation={measure_intent.aggregation}",
                        "message": f"度量 {measure_intent.technical_field} 必须有聚合函数"
                    })
                    if not passed:
                        results["passed"] = False
        
        # 检查TopN
        if vizql_check.get("has_topn"):
            has_topn = subtask.topn_intent is not None
            results["checks"].append({
                "name": "TopN检查",
                "passed": has_topn,
                "expected": "有TopN",
                "actual": "有" if has_topn else "无"
            })
            if not has_topn:
                results["passed"] = False
    
    return results


def validate_execution(result: Dict, expected: Dict) -> Dict[str, Any]:
    """验证查询执行结果"""
    results = {
        "passed": True,
        "checks": []
    }
    
    # 检查返回行数
    row_count = result['row_count']
    allow_empty = expected.get("allow_empty", False)
    
    if "min_rows" in expected:
        passed = row_count >= expected["min_rows"]
        results["checks"].append({
            "name": "最小行数检查",
            "passed": passed,
            "expected": f">= {expected['min_rows']}",
            "actual": row_count
        })
        if not passed and not allow_empty:
            results["passed"] = False
    
    if "max_rows" in expected:
        passed = row_count <= expected["max_rows"]
        results["checks"].append({
            "name": "最大行数检查",
            "passed": passed,
            "expected": f"<= {expected['max_rows']}",
            "actual": row_count
        })
        if not passed:
            results["passed"] = False
    
    # 检查列数
    column_count = len(result['columns'])
    results["checks"].append({
        "name": "列数检查",
        "passed": column_count > 0,
        "value": column_count
    })
    
    # 检查数据完整性（允许空结果的场景除外）
    has_data = row_count > 0 and len(result['data']) > 0
    data_check_passed = has_data or allow_empty
    results["checks"].append({
        "name": "数据完整性检查",
        "passed": data_check_passed,
        "message": "有数据" if has_data else ("允许空结果" if allow_empty else "无数据")
    })
    if not data_check_passed:
        results["passed"] = False
    
    # 检查性能
    exec_time = result['performance']['execution_time']
    passed = exec_time < 10  # 10秒内完成
    results["checks"].append({
        "name": "性能检查",
        "passed": passed,
        "expected": "< 10秒",
        "actual": f"{exec_time:.3f}秒"
    })
    
    return results


# ============================================================================
# 主测试函数
# ============================================================================

async def run_complete_pipeline_tests():
    """运行完整流程测试"""
    
    print_header("完整流程测试套件", level=1)
    print_info(f"测试用例数量: {len(TEST_CASES)}")
    print_info(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # ========================================
    # 初始化环境
    # ========================================
    print_header("初始化测试环境", level=2)
    env = TestEnvironment(use_persistent_store=True)
    await env.setup()
    print_success("环境初始化完成")
    
    # 获取元数据
    print_info("\n获取元数据...")
    metadata = await env.metadata_manager.get_metadata_async()
    dimension_hierarchy = metadata.dimension_hierarchy or {}
    print_success(f"元数据获取完成 (字段: {len(metadata.fields)}, 维度层级: {len(dimension_hierarchy)})")
    
    # 创建查询执行器
    print_info("\n创建查询执行器...")
    executor = QueryExecutor(metadata=metadata)
    print_success("查询执行器创建完成")
    
    # ========================================
    # 执行测试用例
    # ========================================
    all_results = []
    
    for i, test_case in enumerate(TEST_CASES, 1):
        print_header(f"测试 {i}/{len(TEST_CASES)}: {test_case['name']}", level=1)
        print_info(f"ID: {test_case['id']}")
        print_info(f"问题: {test_case['question']}")
        
        test_result = {
            "id": test_case["id"],
            "name": test_case["name"],
            "question": test_case["question"],
            "timestamp": datetime.now().isoformat(),
            "stages": {}
        }
        
        try:
            # 初始化状态
            state = {
                "original_question": test_case["question"],
                "question": test_case["question"],
                "metadata": metadata,
                "dimension_hierarchy": dimension_hierarchy
            }
            
            # ========================================
            # 阶段1: 问题理解
            # ========================================
            print_header("阶段1: 问题理解", level=3)
            stage_start = time.time()
            
            understanding_result = await understanding_agent.execute(
                state=state,
                runtime=env.runtime
            )
            state.update(understanding_result)
            
            stage_time = time.time() - stage_start
            print_success(f"问题理解完成 (耗时: {stage_time:.2f}秒)")
            
            # 验证理解结果
            understanding_validation = validate_understanding(
                state['understanding'],
                test_case['expected']
            )
            
            test_result["stages"]["understanding"] = {
                "success": True,
                "time": stage_time,
                "validation": understanding_validation,
                "data": {
                    "is_valid": state['understanding'].is_valid_question,
                    "question_type": [qt.value for qt in state['understanding'].question_type],
                    "complexity": state['understanding'].complexity.value,
                    "sub_questions_count": len(state['understanding'].sub_questions)
                }
            }
            
            # 显示验证结果
            for check in understanding_validation["checks"]:
                status = "✓" if check["passed"] else "✗"
                print_info(f"{status} {check['name']}: {check.get('message', check.get('actual', ''))}", indent=1)
            
            if not understanding_validation["passed"]:
                print_warning("问题理解验证未通过，但继续执行")
            
            # ========================================
            # 阶段2: 任务规划
            # ========================================
            print_header("阶段2: 任务规划", level=3)
            stage_start = time.time()
            
            planning_result = await task_planner_agent.execute(
                state=state,
                runtime=env.runtime
            )
            state.update(planning_result)
            
            stage_time = time.time() - stage_start
            print_success(f"任务规划完成 (耗时: {stage_time:.2f}秒)")
            
            # 验证规划结果
            planning_validation = validate_planning(
                state['query_plan'],
                test_case['expected']
            )
            
            query_subtasks = [st for st in state['query_plan'].subtasks if st.task_type == "query"]
            
            test_result["stages"]["planning"] = {
                "success": True,
                "time": stage_time,
                "validation": planning_validation,
                "data": {
                    "total_subtasks": len(state['query_plan'].subtasks),
                    "query_subtasks": len(query_subtasks),
                    "complexity": state['query_plan'].complexity,
                    "estimated_rows": state['query_plan'].estimated_rows
                }
            }
            
            # 显示验证结果
            for check in planning_validation["checks"]:
                status = "✓" if check["passed"] else "✗"
                msg = f"{check.get('expected', '')} vs {check.get('actual', '')}" if 'expected' in check else check.get('message', check.get('value', ''))
                print_info(f"{status} {check['name']}: {msg}", indent=1)
            
            if not planning_validation["passed"]:
                print_warning("任务规划验证未通过，但继续执行")
            
            # 显示子任务详情
            print_info(f"\n查询子任务详情:", indent=1)
            for idx, subtask in enumerate(query_subtasks, 1):
                print_info(f"子任务 {idx}: {subtask.question_text}", indent=2)
                print_info(f"- 维度: {len(subtask.dimension_intents or [])} 个", indent=2)
                print_info(f"- 度量: {len(subtask.measure_intents or [])} 个", indent=2)
                if subtask.date_filter_intent:
                    print_info(f"- 日期筛选: 有", indent=2)
            
            # ========================================
            # 阶段3: 查询执行
            # ========================================
            print_header("阶段3: 查询执行", level=3)
            
            execution_results = []
            
            for idx, subtask in enumerate(query_subtasks, 1):
                print_info(f"\n执行子任务 {idx}/{len(query_subtasks)}: {subtask.question_id}", indent=1)
                
                try:
                    exec_start = time.time()
                    
                    result = executor.execute_subtask(
                        subtask=subtask,
                        datasource_luid=env.datasource_luid,
                        tableau_config=env.tableau_config,
                        enable_retry=True
                    )
                    
                    exec_time = time.time() - exec_start
                    
                    # 验证执行结果
                    execution_validation = validate_execution(result, test_case['expected'])
                    
                    print_success(f"查询执行成功 (耗时: {exec_time:.2f}秒)", indent=2)
                    print_info(f"返回: {result['row_count']} 行 x {len(result['columns'])} 列", indent=2)
                    
                    # 显示验证结果
                    for check in execution_validation["checks"]:
                        status = "✓" if check["passed"] else "✗"
                        msg = f"{check.get('expected', '')} vs {check.get('actual', '')}" if 'expected' in check else check.get('message', check.get('value', ''))
                        print_info(f"{status} {check['name']}: {msg}", indent=3)
                    
                    # 显示数据样例
                    if result['data'] and len(result['data']) > 0:
                        print_info(f"\n数据样例 (前3行):", indent=2)
                        for row_idx, row in enumerate(result['data'][:3], 1):
                            print_info(f"{row_idx}. {row}", indent=3)
                    
                    execution_results.append({
                        "subtask_id": subtask.question_id,
                        "success": True,
                        "validation": execution_validation,
                        "result": {
                            "row_count": result['row_count'],
                            "column_count": len(result['columns']),
                            "columns": result['columns'],
                            "execution_time": result['performance']['execution_time'],
                            "build_time": result['performance']['build_time'],
                            "total_time": result['performance']['total_time']
                        }
                    })
                    
                except Exception as e:
                    print_error(f"查询执行失败: {e}", indent=2)
                    execution_results.append({
                        "subtask_id": subtask.question_id,
                        "success": False,
                        "error": str(e)
                    })
            
            test_result["stages"]["execution"] = {
                "success": all(r["success"] for r in execution_results),
                "results": execution_results
            }
            
            # ========================================
            # 测试用例总结
            # ========================================
            all_stages_passed = all(
                test_result["stages"][stage].get("success", False)
                for stage in ["understanding", "planning", "execution"]
            )
            
            all_validations_passed = (
                understanding_validation["passed"] and
                planning_validation["passed"] and
                all(r.get("validation", {}).get("passed", False) for r in execution_results if r["success"])
            )
            
            test_result["overall_success"] = all_stages_passed
            test_result["validation_passed"] = all_validations_passed
            
            if all_stages_passed and all_validations_passed:
                print_success(f"\n✓ 测试用例 {test_case['id']} 完全通过")
            elif all_stages_passed:
                print_warning(f"\n⚠ 测试用例 {test_case['id']} 执行成功但验证部分未通过")
            else:
                print_error(f"\n✗ 测试用例 {test_case['id']} 执行失败")
            
        except Exception as e:
            print_error(f"\n✗ 测试用例执行异常: {e}")
            import traceback
            traceback.print_exc()
            
            test_result["overall_success"] = False
            test_result["error"] = str(e)
        
        all_results.append(test_result)
    
    # ========================================
    # 总体测试报告
    # ========================================
    print_header("测试总结报告", level=1)
    
    total_tests = len(all_results)
    successful_tests = sum(1 for r in all_results if r.get("overall_success", False))
    validated_tests = sum(1 for r in all_results if r.get("validation_passed", False))
    
    print_info(f"\n总测试数: {total_tests}")
    print_info(f"执行成功: {successful_tests}/{total_tests} ({successful_tests/total_tests*100:.1f}%)")
    print_info(f"验证通过: {validated_tests}/{total_tests} ({validated_tests/total_tests*100:.1f}%)")
    
    print_info(f"\n详细结果:")
    for result in all_results:
        status = "✓" if result.get("overall_success") else "✗"
        validation = "✓" if result.get("validation_passed") else "⚠"
        print_info(f"  {status} {validation} {result['id']}: {result['name']}")
    
    # 保存详细结果
    output_file = "test_complete_pipeline_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_tests": total_tests,
                "successful_tests": successful_tests,
                "validated_tests": validated_tests,
                "success_rate": successful_tests / total_tests,
                "validation_rate": validated_tests / total_tests
            },
            "results": all_results
        }, f, ensure_ascii=False, indent=2)
    
    print_info(f"\n详细结果已保存到: {output_file}")
    
    # 清理
    await env.teardown()
    print_success("\n测试完成")
    
    return successful_tests == total_tests


if __name__ == "__main__":
    success = asyncio.run(run_complete_pipeline_tests())
    sys.exit(0 if success else 1)
