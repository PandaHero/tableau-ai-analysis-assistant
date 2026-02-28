# -*- coding: utf-8 -*-
"""快速 VizQL 查询验证脚本"""
import asyncio
import json
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


async def test_datetrunc_month():
    """验证 DATETRUNC month 聚合是否生效"""
    from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
    from analytics_assistant.src.platform.tableau.client import VizQLClient

    auth = await get_tableau_auth_async()
    client = VizQLClient()
    ds = "b9f0e505-9d74-4f4d-a629-6d1095638eaa"

    # 测试 1: DATETRUNC month + DATEPARSE
    print("=== 测试 1: DATETRUNC month ===")
    query = {
        "fields": [
            {
                "fieldCaption": "dt_month",
                "calculation": "DATETRUNC('month', DATEPARSE('yyyy-MM-dd', [dt]))"
            },
            {"fieldCaption": "netamt", "function": "SUM"}
        ],
        "filters": [
            {
                "field": {"calculation": "DATEPARSE('yyyy-MM-dd', [dt])"},
                "filterType": "QUANTITATIVE_DATE",
                "quantitativeFilterType": "RANGE",
                "minDate": "2024-01-01",
                "maxDate": "2024-12-31",
            }
        ]
    }
    try:
        resp = await client.query_datasource(
            datasource_luid=ds, query=query,
            api_key=auth.api_key, site=auth.site,
        )
        data = resp.get("data", [])
        print(f"行数: {len(data)}")
        for row in data[:5]:
            print(f"  {json.dumps(row, ensure_ascii=False)}")
    except Exception as e:
        print(f"失败: {e}")

    # 测试 2: 不带 DATETRUNC，只有 DATEPARSE 过滤
    print("\n=== 测试 2: 无 DATETRUNC，原始 dt ===")
    query2 = {
        "fields": [
            {"fieldCaption": "dt"},
            {"fieldCaption": "netamt", "function": "SUM"}
        ],
        "filters": [
            {
                "field": {"calculation": "DATEPARSE('yyyy-MM-dd', [dt])"},
                "filterType": "QUANTITATIVE_DATE",
                "quantitativeFilterType": "RANGE",
                "minDate": "2024-01-01",
                "maxDate": "2024-12-31",
            }
        ]
    }
    try:
        resp = await client.query_datasource(
            datasource_luid=ds, query=query2,
            api_key=auth.api_key, site=auth.site,
        )
        data = resp.get("data", [])
        print(f"行数: {len(data)}")
        for row in data[:3]:
            print(f"  {json.dumps(row, ensure_ascii=False)}")
    except Exception as e:
        print(f"失败: {e}")

    # 测试 3: 用 yyyymm 字段做维度
    print("\n=== 测试 3: yyyymm 字段 ===")
    query3 = {
        "fields": [
            {"fieldCaption": "yyyymm"},
            {"fieldCaption": "netamt", "function": "SUM"}
        ],
    }
    try:
        resp = await client.query_datasource(
            datasource_luid=ds, query=query3,
            api_key=auth.api_key, site=auth.site,
        )
        data = resp.get("data", [])
        print(f"行数: {len(data)}")
        for row in data[:5]:
            print(f"  {json.dumps(row, ensure_ascii=False)}")
    except Exception as e:
        print(f"失败: {e}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(test_datetrunc_month())
