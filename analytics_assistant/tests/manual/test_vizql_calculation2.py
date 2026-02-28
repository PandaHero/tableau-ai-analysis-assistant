# -*- coding: utf-8 -*-
"""测试 VizQL API 过滤器格式 - 探索正确的 MATCH 过滤器和计算字段过滤。

上一轮测试发现：
- calculation 字段作为 fields 是支持的 ✅
- 过滤器不能通过 fieldCaption 引用 calculation 字段 ❌ (Unknown Field)
- matchFilterType 不是合法字段名 ❌ (Unrecognized field)

本轮测试：
1. MATCH 过滤器的正确格式（startsWith/contains/endsWith）
2. 过滤器引用计算字段的其他方式
3. SET 过滤器对 STRING 字段
4. 计算字段同时在 fields 和 filter 中（用 calculation 属性）
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

    # 测试 1: MATCH 过滤器 - 用 startsWith 而非 matchFilterType
    results["test1_match_startsWith"] = await run_query(vizql_client, auth, {
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
            }
        ]
    }, "MATCH 过滤器 - startsWith 格式")

    # 测试 2: MATCH 过滤器 - 用 contains
    results["test2_match_contains"] = await run_query(vizql_client, auth, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {"fieldCaption": "dt"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [
            {
                "field": {"fieldCaption": "dt"},
                "filterType": "MATCH",
                "contains": "2025",
            }
        ]
    }, "MATCH 过滤器 - contains 格式")

    # 测试 3: SET 过滤器对 STRING 字段 - 用具体值
    results["test3_set_filter"] = await run_query(vizql_client, auth, {
        "fields": [
            {"fieldCaption": "pro_name"},
            {"fieldCaption": "yyyymm"},
            {"fieldCaption": "netamt", "function": "SUM"},
        ],
        "filters": [
            {
                "field": {"fieldCaption": "yyyymm"},
                "filterType": "SET",
                "values": ["202501", "202502", "202503"],
                "exclude": False,
            }
        ]
    }, "SET 过滤器 - yyyymm 具体值")

    # 测试 4: 过滤器中也用 calculation 属性
    results["test4_filter_with_calc"] = await run_query(vizql_client, auth, {
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
                "maxDate": "2025-12-31",
            }
        ]
    }, "过滤器 field 中也带 calculation")

    # 测试 5: 过滤器直接用原始字段名 dt + QUANTITATIVE_DATE
    # 但 dt 在 fields 中是 calculation 版本
    results["test5_filter_original_name"] = await run_query(vizql_client, auth, {
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
                "field": {"fieldCaption": "dt"},
                "filterType": "MATCH",
                "startsWith": "2025",
            }
        ]
    }, "fields 用 calculation, filter 用原始字段 + MATCH")

    # 测试 6: 完整环比查询 - dt 作为维度 + MATCH 过滤 + 表计算
    results["test6_full_query"] = await run_query(vizql_client, auth, {
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
                "fieldAlias": "环比增长率",
                "tableCalculation": {
                    "dimensions": [
                        {"fieldCaption": "pro_name"},
                        {
                            "fieldCaption": "dt_month",
                            "calculation": "DATETRUNC('month', DATEPARSE('yyyy-MM-dd', [dt]))",
                        },
                    ],
                    "tableCalcType": "PERCENT_DIFFERENCE_FROM",
                    "relativeTo": "PREVIOUS",
                },
            },
        ],
        "filters": [
            {
                "field": {"fieldCaption": "dt"},
                "filterType": "MATCH",
                "startsWith": "2025",
            }
        ]
    }, "完整环比查询: calculation维度 + MATCH过滤 + 表计算")

    # 汇总
    print(f"\n{'='*60}")
    print("  测试汇总")
    print(f"{'='*60}")
    for name, ok in results.items():
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")


if __name__ == "__main__":
    asyncio.run(main())
