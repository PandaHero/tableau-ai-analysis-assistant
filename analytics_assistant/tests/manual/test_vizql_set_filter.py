# -*- coding: utf-8 -*-
"""测试 SET 过滤器对 STRING 日期字段的精确范围过滤。

方案：生成日期范围内所有日期值，用 SET 过滤器精确匹配。
但 SET 要求精确值匹配，dt 字段值是 "2025-01-15" 格式。

测试：
1. SET 过滤器 + 具体日期值列表
2. SET 过滤器 + 年月前缀（如 "2025-01"）- 可能不行因为不是精确匹配
3. MATCH 过滤器 + contains 多个值（如果支持数组）
4. 多个 MATCH 过滤器对同一字段（测试 AND/OR 语义）
"""
import asyncio
import json
import re
import time
import logging
from datetime import date, timedelta

logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DATASOURCE_LUID = "b9f0e505-9d74-4f4d-a629-6d1095638eaa"


async def run_query(vizql_client, auth, query: dict, label: str) -> bool:
    print(f"\n{'='*60}")
    print(f"  Test: {label}")
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
        print(f"\n  [OK] rows={len(rows)}, time={elapsed:.1f}s")
        for i, row in enumerate(rows[:5]):
            print(f"    [{i}] {row}")
        if len(rows) > 5:
            print(f"    ... total {len(rows)} rows")
        return True
    except Exception as e:
        elapsed = time.time() - start
        err_str = str(e)
        msgs = re.findall(r'"message":"([^"]+)"', err_str)
        if msgs:
            print(f"\n  [FAIL] time={elapsed:.1f}s")
            for m in msgs:
                print(f"    - {m}")
        else:
            print(f"\n  [FAIL] {err_str[:300]}")
        return False


async def main():
    from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
    from analytics_assistant.src.platform.tableau.client import VizQLClient

    auth = await get_tableau_auth_async()
    vizql_client = VizQLClient()

    results = {}

    # 测试 1: SET 过滤器 + 具体日期值（生成 2025-01 的所有日期）
    jan_dates = [f"2025-01-{d:02d}" for d in range(1, 32)]
    results["test1_set_exact_dates"] = await run_query(vizql_client, auth, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {"fieldCaption": "dt"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [
            {
                "field": {"fieldCaption": "dt"},
                "filterType": "SET",
                "values": jan_dates,
                "exclude": False,
            }
        ]
    }, "SET + exact dates (2025-01-01 to 2025-01-31)")

    # 测试 2: 两个 MATCH 过滤器对同一字段（测试是否 AND 语义）
    results["test2_two_match_same_field"] = await run_query(vizql_client, auth, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {"fieldCaption": "dt"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [
            {
                "field": {"fieldCaption": "dt"},
                "filterType": "MATCH",
                "startsWith": "2025-01",
            },
            {
                "field": {"fieldCaption": "dt"},
                "filterType": "MATCH",
                "startsWith": "2025-02",
            },
        ]
    }, "Two MATCH on same field (AND? OR?)")


    # 测试 3: SET 过滤器 + 跨年日期值（2024-12 + 2025-01 的所有日期）
    dec_dates = [f"2024-12-{d:02d}" for d in range(1, 32)]
    jan_dates_2 = [f"2025-01-{d:02d}" for d in range(1, 32)]
    cross_year_dates = dec_dates + jan_dates_2
    results["test3_set_cross_year"] = await run_query(vizql_client, auth, {
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
                "field": {"fieldCaption": "dt"},
                "filterType": "SET",
                "values": cross_year_dates,
                "exclude": False,
            }
        ]
    }, "SET + cross-year dates (2024-12 + 2025-01)")

    # 测试 4: MATCH + contains 用年月（不是 startsWith）
    results["test4_match_contains_month"] = await run_query(vizql_client, auth, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {"fieldCaption": "dt"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [
            {
                "field": {"fieldCaption": "dt"},
                "filterType": "MATCH",
                "startsWith": "2025-01",
            },
        ]
    }, "MATCH startsWith=2025-01 (single month)")

    # 测试 5: SET 过滤器 + exclude=True（排除模式）
    results["test5_set_exclude"] = await run_query(vizql_client, auth, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {"fieldCaption": "dt"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [
            {
                "field": {"fieldCaption": "dt"},
                "filterType": "SET",
                "values": ["2025-01-01", "2025-01-02", "2025-01-03"],
                "exclude": False,
            }
        ]
    }, "SET + 3 specific dates")

    # 汇总
    print(f"\n{'='*60}")
    print("  Summary")
    print(f"{'='*60}")
    for name, ok in results.items():
        status = "[OK]" if ok else "[FAIL]"
        print(f"  {status} {name}")


if __name__ == "__main__":
    asyncio.run(main())
