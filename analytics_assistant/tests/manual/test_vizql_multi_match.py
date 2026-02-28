# -*- coding: utf-8 -*-
"""测试同一字段多个 MATCH 过滤器。

VizQL 错误信息说 MATCH 类型允许多个过滤器，但之前测试失败了。
可能是因为两个 MATCH 都用了 startsWith，需要用不同的 match 属性。
"""
import asyncio
import json
import re
import time
import logging

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

    # 测试 1: MATCH + SET 组合（不同过滤器类型对同一字段）
    results["test1_match_and_set"] = await run_query(vizql_client, auth, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {"fieldCaption": "dt"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [
            {
                "field": {"fieldCaption": "dt"},
                "filterType": "MATCH",
                "startsWith": "2025",
            },
            {
                "field": {"fieldCaption": "dt"},
                "filterType": "SET",
                "values": ["2025-01-01", "2025-01-02"],
                "exclude": False,
            },
        ]
    }, "MATCH + SET on same field")

    # 测试 2: 单个 MATCH 用 startsWith + endsWith 组合
    results["test2_match_multi_cond"] = await run_query(vizql_client, auth, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {"fieldCaption": "dt"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [
            {
                "field": {"fieldCaption": "dt"},
                "filterType": "MATCH",
                "startsWith": "2025",
                "contains": "-01-",
            },
        ]
    }, "Single MATCH with startsWith + contains")

    # 测试 3: SET 过滤器生成跨年月份的所有日期
    # 2024-11 到 2025-02 的所有日期
    from datetime import date, timedelta
    start_d = date(2024, 11, 1)
    end_d = date(2025, 2, 28)
    all_dates = []
    d = start_d
    while d <= end_d:
        all_dates.append(d.isoformat())
        d += timedelta(days=1)
    
    results["test3_set_4months"] = await run_query(vizql_client, auth, {
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
                "values": all_dates,
                "exclude": False,
            }
        ]
    }, f"SET + 4 months dates ({len(all_dates)} values)")

    # 汇总
    print(f"\n{'='*60}")
    print("  Summary")
    print(f"{'='*60}")
    for name, ok in results.items():
        status = "[OK]" if ok else "[FAIL]"
        print(f"  {status} {name}")


if __name__ == "__main__":
    asyncio.run(main())
