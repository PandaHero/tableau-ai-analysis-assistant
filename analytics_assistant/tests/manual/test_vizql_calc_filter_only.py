# -*- coding: utf-8 -*-
"""验证 GitHub 旧版本的过滤器格式：field 中只有 calculation，没有 fieldCaption。"""
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

    # 测试 1: GitHub 旧版格式 - field 只有 calculation，没有 fieldCaption
    results["test1_calc_only"] = await run_query(vizql_client, auth, {
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
                "field": {
                    "calculation": "DATEPARSE('yyyy-MM-dd', [dt])",
                },
                "filterType": "QUANTITATIVE_DATE",
                "quantitativeFilterType": "RANGE",
                "minDate": "2025-01-01",
                "maxDate": "2025-03-31",
            }
        ]
    }, "filter.field = {calculation only} + QUANTITATIVE_DATE (GitHub old version)")

    # 测试 2: 跨年范围
    results["test2_cross_year"] = await run_query(vizql_client, auth, {
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
                "field": {
                    "calculation": "DATEPARSE('yyyy-MM-dd', [dt])",
                },
                "filterType": "QUANTITATIVE_DATE",
                "quantitativeFilterType": "RANGE",
                "minDate": "2024-06-01",
                "maxDate": "2025-03-31",
            }
        ]
    }, "cross-year: 2024-06 to 2025-03 (calc only filter)")

    # 测试 3: 只有 minDate（开放右端）
    results["test3_min_only"] = await run_query(vizql_client, auth, {
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
                "field": {
                    "calculation": "DATEPARSE('yyyy-MM-dd', [dt])",
                },
                "filterType": "QUANTITATIVE_DATE",
                "quantitativeFilterType": "RANGE",
                "minDate": "2025-01-01",
            }
        ]
    }, "min only: >= 2025-01-01 (calc only filter)")

    # 测试 4: 完整环比查询 + calculation 过滤器
    results["test4_full_with_table_calc"] = await run_query(vizql_client, auth, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {
                "fieldCaption": "dt_month",
                "calculation": "DATETRUNC('month', DATEPARSE('yyyy-MM-dd', [dt]))",
            },
            {"fieldCaption": "netamt", "function": "SUM"},
            {
                "fieldCaption": "netamt",
                "function": "SUM",
                "fieldAlias": "MoM Growth",
                "tableCalculation": {
                    "dimensions": [
                        {"fieldCaption": "pro_name"},
                        {"fieldCaption": "dt_month"},
                    ],
                    "tableCalcType": "PERCENT_DIFFERENCE_FROM",
                    "relativeTo": "PREVIOUS",
                },
            },
        ],
        "filters": [
            {
                "field": {
                    "calculation": "DATEPARSE('yyyy-MM-dd', [dt])",
                },
                "filterType": "QUANTITATIVE_DATE",
                "quantitativeFilterType": "RANGE",
                "minDate": "2025-01-01",
                "maxDate": "2025-12-31",
            }
        ]
    }, "full query: table calc + calc filter")

    # 汇总
    print(f"\n{'='*60}")
    print("  Summary")
    print(f"{'='*60}")
    for name, ok in results.items():
        status = "[OK]" if ok else "[FAIL]"
        print(f"  {status} {name}")


if __name__ == "__main__":
    asyncio.run(main())
