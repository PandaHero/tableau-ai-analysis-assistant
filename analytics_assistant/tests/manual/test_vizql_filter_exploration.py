# -*- coding: utf-8 -*-
"""
VizQL Data Service 筛选器能力探测脚本

目标：用真实 Tableau Cloud 环境，系统性测试 VizQL API 支持的所有筛选器类型，
搞清楚：
1. STRING 日期字段（dt, yyyymm）的各种过滤方式哪些能用
2. DATEPARSE 在 filter calculation 中的行为
3. SET / MATCH / QUANTITATIVE_DATE / QUANTITATIVE_NUMERICAL / TOP 的边界
4. 字段样本值的实际格式（用于自动推断日期格式）

运行方式：
    cd analytics_assistant
    source ../venv/Scripts/activate  (Windows: ../venv/Scripts/activate)
    PYTHONPATH=".." python tests/manual/test_vizql_filter_exploration.py
"""

import asyncio
import json
import logging
import os
import sys
import time
import traceback
from typing import Any, Optional

project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

logging.basicConfig(
    level=logging.WARNING,
    format="%(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================
# 工具函数
# ============================================================

def pp(obj: Any) -> str:
    """Pretty print JSON."""
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str)


def banner(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def section(title: str) -> None:
    print(f"\n--- {title} ---")


async def run_query(
    client: Any,
    datasource_luid: str,
    api_key: str,
    site: str,
    query: dict,
    label: str,
) -> Optional[dict]:
    """执行单个 VizQL 查询并打印结果。"""
    print(f"\n  [{label}]")
    print(f"  Query: {json.dumps(query, ensure_ascii=False)[:200]}...")
    start = time.time()
    try:
        result = await client.query_datasource(
            datasource_luid=datasource_luid,
            query=query,
            api_key=api_key,
            site=site,
            options={"rowLimit": 10},
        )
        elapsed = time.time() - start
        rows = result.get("data", [])
        row_count = result.get("rowCount", len(rows))
        print(f"  OK: {row_count} rows, {elapsed:.1f}s")
        if rows:
            print(f"  Sample: {json.dumps(rows[0], ensure_ascii=False)}")
        return result
    except Exception as e:
        elapsed = time.time() - start
        err_msg = str(e)
        # 截取关键错误信息
        if len(err_msg) > 200:
            err_msg = err_msg[:200] + "..."
        print(f"  FAIL ({elapsed:.1f}s): {err_msg}")
        return None


# ============================================================
# 测试用例
# ============================================================

async def test_sample_values(client, ds_luid, api_key, site):
    """测试 1: 获取关键字段的样本值，了解实际数据格式。"""
    banner("TEST 1: 字段样本值探测")

    # dt 字段样本
    section("dt 字段样本值")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [{"fieldCaption": "dt"}],
    }, "dt raw values (top 10)")

    # yyyymm 字段样本
    section("yyyymm 字段样本值")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [{"fieldCaption": "yyyymm"}],
    }, "yyyymm raw values (top 10)")

    # pro_name 字段样本
    section("pro_name 字段样本值")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [{"fieldCaption": "pro_name"}],
    }, "pro_name raw values")


async def test_set_filter(client, ds_luid, api_key, site):
    """测试 2: SET 筛选器的各种用法。"""
    banner("TEST 2: SET 筛选器")

    # 2a: 基本 SET - 维度精确匹配
    section("2a: SET - 维度精确匹配 (pro_name)")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [{
            "field": {"fieldCaption": "pro_name"},
            "filterType": "SET",
            "values": ["上海", "北京"],
            "exclude": False,
        }],
    }, "SET include 上海+北京")

    # 2b: SET exclude
    section("2b: SET - 排除模式")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [{
            "field": {"fieldCaption": "pro_name"},
            "filterType": "SET",
            "values": ["上海"],
            "exclude": True,
        }],
    }, "SET exclude 上海")

    # 2c: SET - 对 STRING 日期字段 dt 使用 SET
    section("2c: SET - 对 dt 字段使用 SET (字符串精确匹配)")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {"fieldCaption": "dt"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [{
            "field": {"fieldCaption": "dt"},
            "filterType": "SET",
            "values": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "exclude": False,
        }],
    }, "SET dt = specific dates")

    # 2d: SET - 对 yyyymm 字段使用 SET
    section("2d: SET - 对 yyyymm 字段使用 SET")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {"fieldCaption": "yyyymm"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [{
            "field": {"fieldCaption": "yyyymm"},
            "filterType": "SET",
            "values": ["2024-01", "2024-02", "2024-03"],
            "exclude": False,
        }],
    }, "SET yyyymm = 2024-01/02/03")


async def test_match_filter(client, ds_luid, api_key, site):
    """测试 3: MATCH 筛选器。"""
    banner("TEST 3: MATCH 筛选器")

    # 3a: MATCH contains
    section("3a: MATCH contains")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [{
            "field": {"fieldCaption": "pro_name"},
            "filterType": "MATCH",
            "contains": "东",
        }],
    }, "MATCH pro_name contains '东'")

    # 3b: MATCH - 对 dt 字段用 contains 做前缀匹配
    section("3b: MATCH - dt 字段前缀匹配 (模拟年份筛选)")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {"fieldCaption": "dt"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [{
            "field": {"fieldCaption": "dt"},
            "filterType": "MATCH",
            "startsWith": "2024-01",
        }],
    }, "MATCH dt startsWith '2024-01'")

    # 3c: MATCH - 对 yyyymm 字段用 startsWith 做年份筛选
    section("3c: MATCH - yyyymm 字段年份筛选")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {"fieldCaption": "yyyymm"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [{
            "field": {"fieldCaption": "yyyymm"},
            "filterType": "MATCH",
            "startsWith": "2024",
        }],
    }, "MATCH yyyymm startsWith '2024'")


async def test_quantitative_date_filter(client, ds_luid, api_key, site):
    """测试 4: QUANTITATIVE_DATE 筛选器 (日期范围)。"""
    banner("TEST 4: QUANTITATIVE_DATE 筛选器")

    # 4a: 直接对 STRING dt 字段用 QUANTITATIVE_DATE (预期失败)
    section("4a: QUANTITATIVE_DATE 直接对 STRING dt 字段 (预期可能失败)")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {"fieldCaption": "dt"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [{
            "field": {"fieldCaption": "dt"},
            "filterType": "QUANTITATIVE_DATE",
            "quantitativeFilterType": "RANGE",
            "minDate": "2024-01-01",
            "maxDate": "2024-03-31",
        }],
    }, "QUANTITATIVE_DATE on STRING dt (direct)")

    # 4b: DATEPARSE calculation + QUANTITATIVE_DATE (yyyy-MM-dd 格式)
    section("4b: DATEPARSE(yyyy-MM-dd) + QUANTITATIVE_DATE")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {"fieldCaption": "dt"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [{
            "field": {
                "calculation": "DATEPARSE('yyyy-MM-dd', [dt])",
            },
            "filterType": "QUANTITATIVE_DATE",
            "quantitativeFilterType": "RANGE",
            "minDate": "2024-01-01",
            "maxDate": "2024-03-31",
        }],
    }, "DATEPARSE(yyyy-MM-dd, dt) + RANGE")

    # 4c: DATEPARSE(yyyy-MM) 对 yyyymm 字段 + QUANTITATIVE_DATE
    section("4c: DATEPARSE(yyyy-MM) 对 yyyymm + QUANTITATIVE_DATE")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {"fieldCaption": "yyyymm"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [{
            "field": {
                "calculation": "DATEPARSE('yyyy-MM', [yyyymm])",
            },
            "filterType": "QUANTITATIVE_DATE",
            "quantitativeFilterType": "RANGE",
            "minDate": "2024-01-01",
            "maxDate": "2024-06-30",
        }],
    }, "DATEPARSE(yyyy-MM, yyyymm) + RANGE")

    # 4d: 只有 minDate 没有 maxDate
    section("4d: QUANTITATIVE_DATE 只有 minDate")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {"fieldCaption": "dt"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [{
            "field": {
                "calculation": "DATEPARSE('yyyy-MM-dd', [dt])",
            },
            "filterType": "QUANTITATIVE_DATE",
            "quantitativeFilterType": "RANGE",
            "minDate": "2025-01-01",
        }],
    }, "DATEPARSE + RANGE (only minDate)")

    # 4e: 只有 maxDate 没有 minDate
    section("4e: QUANTITATIVE_DATE 只有 maxDate")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {"fieldCaption": "dt"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [{
            "field": {
                "calculation": "DATEPARSE('yyyy-MM-dd', [dt])",
            },
            "filterType": "QUANTITATIVE_DATE",
            "quantitativeFilterType": "RANGE",
            "maxDate": "2024-01-31",
        }],
    }, "DATEPARSE + RANGE (only maxDate)")


async def test_quantitative_numerical_filter(client, ds_luid, api_key, site):
    """测试 5: QUANTITATIVE_NUMERICAL 筛选器。"""
    banner("TEST 5: QUANTITATIVE_NUMERICAL 筛选器")

    # 5a: 数值范围
    section("5a: 数值范围 (netamt > 1000000)")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [{
            "field": {"fieldCaption": "netamt", "function": "SUM"},
            "filterType": "QUANTITATIVE_NUMERICAL",
            "quantitativeFilterType": "RANGE",
            "min": 1000000,
            "max": 99999999,
        }],
    }, "NUMERICAL RANGE SUM(netamt) 1M~99M")

    # 5b: 只有 min 没有 max
    section("5b: 数值范围 只有 min")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [{
            "field": {"fieldCaption": "netamt", "function": "SUM"},
            "filterType": "QUANTITATIVE_NUMERICAL",
            "quantitativeFilterType": "RANGE",
            "min": 5000000,
        }],
    }, "NUMERICAL RANGE SUM(netamt) >= 5M (no max)")

    # 5c: 对聚合度量过滤 (HAVING 语义)
    section("5c: 聚合度量过滤 (HAVING)")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [{
            "field": {"fieldCaption": "netamt", "function": "SUM"},
            "filterType": "QUANTITATIVE_NUMERICAL",
            "quantitativeFilterType": "RANGE",
            "min": 0,
            "max": 3000000,
        }],
    }, "HAVING SUM(netamt) between 0 and 3M")


async def test_top_filter(client, ds_luid, api_key, site):
    """测试 6: TOP 筛选器。"""
    banner("TEST 6: TOP 筛选器")

    # 6a: TOP 5
    section("6a: TOP 5 by SUM(netamt)")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [{
            "field": {"fieldCaption": "pro_name"},
            "filterType": "TOP",
            "howMany": 5,
            "fieldToMeasure": {"fieldCaption": "netamt", "function": "SUM"},
            "direction": "TOP",
        }],
    }, "TOP 5 pro_name by SUM(netamt)")

    # 6b: BOTTOM 3
    section("6b: BOTTOM 3 by SUM(netamt)")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [{
            "field": {"fieldCaption": "pro_name"},
            "filterType": "TOP",
            "howMany": 3,
            "fieldToMeasure": {"fieldCaption": "netamt", "function": "SUM"},
            "direction": "BOTTOM",
        }],
    }, "BOTTOM 3 pro_name by SUM(netamt)")


async def test_dateparse_formats(client, ds_luid, api_key, site):
    """测试 7: 各种 DATEPARSE 格式在 calculation 中的行为。"""
    banner("TEST 7: DATEPARSE 格式兼容性")

    # 7a: DATEPARSE 作为维度 calculation (yyyy-MM-dd)
    section("7a: DATEPARSE 作为维度 (dt -> date)")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {
                "fieldCaption": "dt_date",
                "calculation": "DATEPARSE('yyyy-MM-dd', [dt])",
            },
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
    }, "DATEPARSE(yyyy-MM-dd, dt) as dimension")

    # 7b: DATETRUNC + DATEPARSE (月粒度)
    section("7b: DATETRUNC(month) + DATEPARSE")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {
                "fieldCaption": "dt_month",
                "calculation": "DATETRUNC('month', DATEPARSE('yyyy-MM-dd', [dt]))",
            },
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
    }, "DATETRUNC(month, DATEPARSE(dt))")

    # 7c: DATEPARSE(yyyy-MM) 对 yyyymm 字段
    section("7c: DATEPARSE(yyyy-MM) 对 yyyymm")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {
                "fieldCaption": "ym_date",
                "calculation": "DATEPARSE('yyyy-MM', [yyyymm])",
            },
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
    }, "DATEPARSE(yyyy-MM, yyyymm) as dimension")

    # 7d: DATETRUNC(quarter) + DATEPARSE(yyyy-MM)
    section("7d: DATETRUNC(quarter) + DATEPARSE(yyyy-MM)")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {
                "fieldCaption": "ym_quarter",
                "calculation": "DATETRUNC('quarter', DATEPARSE('yyyy-MM', [yyyymm]))",
            },
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
    }, "DATETRUNC(quarter, DATEPARSE(yyyy-MM, yyyymm))")

    # 7e: DATEPARSE 错误格式 (用 yyyy-MM-dd 解析 yyyymm 数据，预期失败或 null)
    section("7e: DATEPARSE 格式不匹配 (yyyy-MM-dd 解析 yyyymm)")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {
                "fieldCaption": "wrong_parse",
                "calculation": "DATEPARSE('yyyy-MM-dd', [yyyymm])",
            },
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
    }, "DATEPARSE(yyyy-MM-dd, yyyymm) - WRONG FORMAT")


async def test_combined_filters(client, ds_luid, api_key, site):
    """测试 8: 组合筛选器。"""
    banner("TEST 8: 组合筛选器")

    # 8a: SET + DATEPARSE RANGE
    section("8a: SET(pro_name) + DATEPARSE RANGE(dt)")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {
                "fieldCaption": "dt_month",
                "calculation": "DATETRUNC('month', DATEPARSE('yyyy-MM-dd', [dt]))",
            },
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [
            {
                "field": {"fieldCaption": "pro_name"},
                "filterType": "SET",
                "values": ["上海", "广东"],
                "exclude": False,
            },
            {
                "field": {
                    "calculation": "DATEPARSE('yyyy-MM-dd', [dt])",
                },
                "filterType": "QUANTITATIVE_DATE",
                "quantitativeFilterType": "RANGE",
                "minDate": "2024-07-01",
                "maxDate": "2024-12-31",
            },
        ],
    }, "SET(上海+广东) + DATEPARSE RANGE(2024 H2)")

    # 8b: MATCH(yyyymm) + TOP
    section("8b: MATCH(yyyymm startsWith 2024) + TOP 5")
    await run_query(client, ds_luid, api_key, site, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [
            {
                "field": {"fieldCaption": "yyyymm"},
                "filterType": "MATCH",
                "startsWith": "2024",
            },
            {
                "field": {"fieldCaption": "pro_name"},
                "filterType": "TOP",
                "howMany": 5,
                "fieldToMeasure": {"fieldCaption": "netamt", "function": "SUM"},
                "direction": "TOP",
            },
        ],
    }, "MATCH(yyyymm 2024*) + TOP 5 pro_name")


# ============================================================
# 主入口
# ============================================================

async def main():
    from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
    from analytics_assistant.src.platform.tableau.client import VizQLClient

    banner("VizQL Filter Exploration - START")

    # 认证
    print("\nAuthenticating...")
    auth = await get_tableau_auth_async()
    print(f"  Auth: {auth.auth_method}, site={auth.site}")

    # 数据源 LUID (销售数据源)
    ds_luid = "b9f0e505-9d74-4f4d-a629-6d1095638eaa"

    client = VizQLClient()

    try:
        # 按顺序执行所有测试
        await test_sample_values(client, ds_luid, auth.api_key, auth.site)
        await test_set_filter(client, ds_luid, auth.api_key, auth.site)
        await test_match_filter(client, ds_luid, auth.api_key, auth.site)
        await test_quantitative_date_filter(client, ds_luid, auth.api_key, auth.site)
        await test_quantitative_numerical_filter(client, ds_luid, auth.api_key, auth.site)
        await test_top_filter(client, ds_luid, auth.api_key, auth.site)
        await test_dateparse_formats(client, ds_luid, auth.api_key, auth.site)
        await test_combined_filters(client, ds_luid, auth.api_key, auth.site)
    finally:
        await client.close()

    banner("VizQL Filter Exploration - DONE")


if __name__ == "__main__":
    asyncio.run(main())
