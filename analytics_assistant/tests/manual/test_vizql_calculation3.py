# -*- coding: utf-8 -*-
"""最终验证：完整环比查询 - 正确格式。

方案：
- fields: calculation 做 DATETRUNC+DATEPARSE
- filters: 原始字段 + MATCH startsWith
- 表计算 dimensions: 只用 fieldCaption（不带 calculation）
"""
import asyncio
import json
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DATASOURCE_LUID = "b9f0e505-9d74-4f4d-a629-6d1095638eaa"


async def run_query(vizql_client, auth, query: dict, label: str) -> bool:
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
        for i, row in enumerate(rows[:10]):
            print(f"    [{i}] {row}")
        if len(rows) > 10:
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

    # 最终方案：完整环比查询
    results["final_query"] = await run_query(vizql_client, auth, {
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
                        {"fieldCaption": "dt_month"},
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
        ],
    }, "完整环比查询: DATETRUNC维度 + MATCH过滤 + 表计算(只用fieldCaption)")

    print(f"\n{'='*60}")
    print("  测试汇总")
    print(f"{'='*60}")
    for name, ok in results.items():
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")


if __name__ == "__main__":
    asyncio.run(main())
