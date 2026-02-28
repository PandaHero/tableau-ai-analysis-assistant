# -*- coding: utf-8 -*-
"""测试 DATEPARSE + QUANTITATIVE_DATE 过滤器的各种组合方式。

目标：找到 STRING 日期字段精确范围过滤的可行方案。

之前已知：
- test_vizql_calculation.py test3: filter 用 fieldCaption="dt_parsed" 引用计算字段 → ❌ Unknown Field
- test_vizql_calculation2.py test4: filter.field 中带 calculation 属性 → ❌ 失败

本轮测试新的组合：
1. filter 中用独立的 calculation（不引用 fields 中的计算字段）
2. filter 中用 DATEPARSE calculation + QUANTITATIVE_DATE
3. filter 中用 calculation 但 filterType 用 QUANTITATIVE_NUMERICAL（日期转数值）
4. fields 中同时有原始字段和计算字段，filter 引用计算字段
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
        print(f"\n  [OK] rows={len(rows)}, time={elapsed:.1f}s")
        for i, row in enumerate(rows[:5]):
            print(f"    [{i}] {row}")
        if len(rows) > 5:
            print(f"    ... total {len(rows)} rows")
        return True
    except Exception as e:
        elapsed = time.time() - start
        err_str = str(e)
        # 截取关键错误信息
        if "messages" in err_str:
            import re
            msgs = re.findall(r'"message":"([^"]+)"', err_str)
            print(f"\n  [FAIL] time={elapsed:.1f}s")
            for m in msgs:
                print(f"    - {m}")
        else:
            print(f"\n  [FAIL] {err_str[:200]}")
        return False


async def main():
    from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
    from analytics_assistant.src.platform.tableau.client import VizQLClient

    auth = await get_tableau_auth_async()
    vizql_client = VizQLClient()

    results = {}

    # 测试 1: filter.field 中用独立的 calculation + QUANTITATIVE_DATE
    # 关键区别：filter 中的 fieldCaption 和 fields 中的不同
    results["test1_filter_independent_calc"] = await run_query(vizql_client, auth, {
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
                    "fieldCaption": "dt_as_date",
                    "calculation": "DATEPARSE('yyyy-MM-dd', [dt])",
                },
                "filterType": "QUANTITATIVE_DATE",
                "quantitativeFilterType": "RANGE",
                "minDate": "2025-01-01",
                "maxDate": "2025-03-31",
            }
        ]
    }, "filter 独立 calculation (dt_as_date) + QUANTITATIVE_DATE")

    # 测试 2: filter.field 中用和 fields 相同的 fieldCaption
    results["test2_filter_same_caption"] = await run_query(vizql_client, auth, {
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
                "field": {
                    "fieldCaption": "dt_parsed",
                    "calculation": "DATEPARSE('yyyy-MM-dd', [dt])",
                },
                "filterType": "QUANTITATIVE_DATE",
                "quantitativeFilterType": "RANGE",
                "minDate": "2025-01-01",
                "maxDate": "2025-03-31",
            }
        ]
    }, "filter 用相同 caption (dt_parsed) + calculation + QUANTITATIVE_DATE")


    # 测试 3: filter 只用 fieldCaption 引用 fields 中的计算字段（不带 calculation）
    # 之前 test_vizql_calculation.py test3 失败过，但那时 fields 中的 caption 可能不同
    results["test3_filter_ref_by_caption"] = await run_query(vizql_client, auth, {
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
                "maxDate": "2025-03-31",
            }
        ]
    }, "filter 只用 fieldCaption 引用 fields 中的计算字段")

    # 测试 4: 跨年范围 - 2024-06 到 2025-03
    results["test4_cross_year"] = await run_query(vizql_client, auth, {
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
                    "fieldCaption": "dt_as_date",
                    "calculation": "DATEPARSE('yyyy-MM-dd', [dt])",
                },
                "filterType": "QUANTITATIVE_DATE",
                "quantitativeFilterType": "RANGE",
                "minDate": "2024-06-01",
                "maxDate": "2025-03-31",
            }
        ]
    }, "跨年范围: 2024-06 到 2025-03 (DATEPARSE + QUANTITATIVE_DATE)")

    # 测试 5: 对比 - 用 MATCH startsWith 做同年过滤（基准）
    results["test5_match_baseline"] = await run_query(vizql_client, auth, {
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
                "filterType": "MATCH",
                "startsWith": "2025",
            }
        ]
    }, "基准: MATCH startsWith (当前方案)")

    # 汇总
    print(f"\n{'='*60}")
    print("  Summary")
    print(f"{'='*60}")
    for name, ok in results.items():
        status = "[OK]" if ok else "[FAIL]"
        print(f"  {status} {name}")


if __name__ == "__main__":
    asyncio.run(main())
