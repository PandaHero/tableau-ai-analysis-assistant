# -*- coding: utf-8 -*-
"""测试 VizQL API 是否支持内联 calculation 字段（DATEPARSE）。

测试场景：
1. 纯 calculation 字段（不带 tableCalculation）
2. calculation 字段 + 过滤器引用
3. 直接用原始 STRING 字段 + MATCH 过滤器
"""
import asyncio
import json
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DATASOURCE_LUID = "b9f0e505-9d74-4f4d-a629-6d1095638eaa"


async def run_query(vizql_client, auth, query: dict, label: str) -> bool:
    """执行查询并打印结果，返回是否成功。"""
    print(f"\n{'='*60}")
    print(f"  测试: {label}")
    print(f"{'='*60}")
    print(json.dumps(query, indent=2, ensure_ascii=False))

    start = time.time()
    try:
        response = await vizql_client.query_datasource(
            datasource_luid=DATASOURCE_LUID,
            query=query,
            api_key=auth.api_key,
            site=auth.site,
        )
        elapsed = time.time() - start
        rows = response.get("data", [])
        print(f"\n  ✅ 成功! 行数={len(rows)}, 耗时={elapsed:.1f}s")
        for i, row in enumerate(rows[:5]):
            print(f"    [{i}] {row}")
        if len(rows) > 5:
            print(f"    ... 共 {len(rows)} 行")
        return True
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n  ❌ 失败: {e}")
        print(f"  耗时={elapsed:.1f}s")
        return False


async def main():
    from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
    from analytics_assistant.src.platform.tableau.client import VizQLClient

    auth = await get_tableau_auth_async()
    vizql_client = VizQLClient()

    results = {}

    # 测试 1: 纯 calculation 字段 - DATEPARSE
    results["test1_dateparse"] = await run_query(vizql_client, auth, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {
                "fieldCaption": "dt_parsed",
                "calculation": "DATEPARSE('yyyy-MM-dd', [dt])",
            },
            {"fieldCaption": "netamt", "function": "SUM"},
        ]
    }, "纯 calculation 字段 (DATEPARSE)")

    # 测试 2: calculation 字段 + DATETRUNC
    results["test2_datetrunc"] = await run_query(vizql_client, auth, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {
                "fieldCaption": "dt_month",
                "calculation": "DATETRUNC('month', DATEPARSE('yyyy-MM-dd', [dt]))",
            },
            {"fieldCaption": "netamt", "function": "SUM"},
        ]
    }, "calculation 字段 (DATETRUNC + DATEPARSE)")

    # 测试 3: calculation 字段 + 过滤器引用该计算字段
    results["test3_calc_filter"] = await run_query(vizql_client, auth, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {
                "fieldCaption": "dt_parsed",
                "calculation": "DATEPARSE('yyyy-MM-dd', [dt])",
            },
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [
            {
                "field": {"fieldCaption": "dt_parsed"},
                "filterType": "QUANTITATIVE_DATE",
                "quantitativeFilterType": "RANGE",
                "minDate": "2025-01-01",
                "maxDate": "2025-12-31",
            }
        ]
    }, "calculation 字段 + 日期过滤器引用")

    # 测试 4: 直接用原始 STRING 字段 + MATCH 过滤器
    results["test4_match_filter"] = await run_query(vizql_client, auth, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {"fieldCaption": "dt"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [
            {
                "field": {"fieldCaption": "dt"},
                "filterType": "MATCH",
                "matchFilterType": "STARTS_WITH",
                "value": "2025",
            }
        ]
    }, "原始 STRING 字段 + MATCH 前缀过滤")

    # 测试 5: 直接用原始 STRING 字段 + SET 过滤器 (QUANTITATIVE_DATE 对 STRING)
    results["test5_string_date_filter"] = await run_query(vizql_client, auth, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {"fieldCaption": "dt"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [
            {
                "field": {"fieldCaption": "dt"},
                "filterType": "QUANTITATIVE_DATE",
                "quantitativeFilterType": "RANGE",
                "minDate": "2025-01-01",
                "maxDate": "2025-12-31",
            }
        ]
    }, "原始 STRING 字段 + QUANTITATIVE_DATE 过滤 (可能失败)")

    # 测试 6: yyyymm 字段 + MATCH 过滤
    results["test6_yyyymm_match"] = await run_query(vizql_client, auth, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {"fieldCaption": "yyyymm"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [
            {
                "field": {"fieldCaption": "yyyymm"},
                "filterType": "MATCH",
                "matchFilterType": "STARTS_WITH",
                "value": "2025",
            }
        ]
    }, "yyyymm STRING 字段 + MATCH 前缀过滤")

    # 汇总
    print(f"\n{'='*60}")
    print("  测试汇总")
    print(f"{'='*60}")
    for name, ok in results.items():
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")


if __name__ == "__main__":
    asyncio.run(main())
