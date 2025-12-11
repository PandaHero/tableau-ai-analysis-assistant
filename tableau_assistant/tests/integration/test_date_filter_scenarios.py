"""
日期筛选场景测试

测试不同数据类型（DATE、STRING）下的日期筛选方案。

数据源：
- DATE 类型日期字段: 使用 .env 中的 DATASOURCE_LUID
- STRING 类型日期字段: 使用 b9f0e505-9d74-4f4d-a629-6d1095638eaa

测试场景：
1. DATE 类型 + QUANTITATIVE_DATE 筛选（绝对日期范围）
2. DATE 类型 + RelativeDateFilter 筛选（相对日期）
3. DATE 类型 + SET 筛选（离散日期）
4. STRING 类型 + DATEPARSE + QUANTITATIVE_DATE 筛选
5. STRING 类型 + SET 筛选（直接匹配字符串）
6. STRING 类型 + MATCH 筛选（模糊匹配）
"""

import os
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

# 加载环境变量
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# 导入项目模块
from tableau_assistant.src.bi_platforms.tableau.vizql_client import VizQLClient, VizQLClientConfig
from tableau_assistant.src.bi_platforms.tableau.auth import _get_tableau_context_from_env


# ═══════════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════════

# DATE 类型数据源（从 .env 读取）
DATE_TYPE_DATASOURCE_LUID = os.getenv("DATASOURCE_LUID", "e99f1815-b3b8-4660-9624-946ea028338f")

# STRING 类型日期数据源
STRING_TYPE_DATASOURCE_LUID = "b9f0e505-9d74-4f4d-a629-6d1095638eaa"


# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════

def get_client_and_auth():
    """获取 VizQL 客户端和认证信息"""
    ctx = _get_tableau_context_from_env()
    
    if not ctx.get("api_key"):
        raise RuntimeError("认证失败，请检查 .env 配置")
    
    config = VizQLClientConfig(
        base_url=ctx["domain"],
        timeout=60,
        max_retries=3
    )
    
    client = VizQLClient(config=config)
    return client, ctx["api_key"], ctx.get("site")


def execute_query(client: VizQLClient, datasource_luid: str, query: Dict, api_key: str, site: str = None) -> Dict:
    """执行查询并返回结果"""
    try:
        result = client.query_datasource(
            datasource_luid=datasource_luid,
            query=query,
            api_key=api_key,
            site=site
        )
        return result
    except Exception as e:
        return {"error": str(e)}


def get_metadata(client: VizQLClient, datasource_luid: str, api_key: str, site: str = None) -> Dict:
    """获取元数据"""
    try:
        result = client.read_metadata(
            datasource_luid=datasource_luid,
            api_key=api_key,
            site=site
        )
        return result
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# 测试场景
# ═══════════════════════════════════════════════════════════════════════════

def test_scenario_1_date_quantitative_filter(client: VizQLClient, api_key: str, site: str):
    """
    场景 1: DATE 类型 + QUANTITATIVE_DATE 筛选（绝对日期范围）
    
    测试 DATE 类型字段使用 minDate/maxDate 进行范围筛选
    """
    print("\n" + "="*60)
    print("场景 1: DATE 类型 + QUANTITATIVE_DATE 筛选")
    print("="*60)
    
    # 先获取元数据，找到日期字段
    metadata = get_metadata(client, DATE_TYPE_DATASOURCE_LUID, api_key, site)
    
    if "error" in metadata:
        print(f"✗ 获取元数据失败: {metadata['error']}")
        return
    
    date_fields = [f for f in metadata.get("data", []) 
                   if f.get("dataType") in ("DATE", "DATETIME")]
    
    if not date_fields:
        print("✗ 未找到 DATE 类型字段")
        print(f"  可用字段: {[f.get('fieldCaption') + ':' + f.get('dataType', '') for f in metadata.get('data', [])[:10]]}")
        return
    
    date_field = date_fields[0]["fieldCaption"]
    print(f"  使用日期字段: {date_field} (类型: {date_fields[0].get('dataType')})")
    
    # 构建查询
    query = {
        "fields": [
            {"fieldCaption": date_field, "function": "YEAR"},
            {"fieldCaption": "Sales", "function": "SUM"}
        ],
        "filters": [
            {
                "field": {"fieldCaption": date_field},
                "filterType": "QUANTITATIVE_DATE",
                "quantitativeFilterType": "RANGE",
                "minDate": "2023-01-01",
                "maxDate": "2023-12-31"
            }
        ]
    }
    
    print(f"  查询: {json.dumps(query, indent=2, ensure_ascii=False)}")
    
    result = execute_query(client, DATE_TYPE_DATASOURCE_LUID, query, api_key, site)
    
    if "error" not in result:
        print(f"✓ 查询成功，返回 {len(result.get('data', []))} 条记录")
        print(f"  数据: {result.get('data', [])[:3]}")
    else:
        print(f"✗ 查询失败: {result['error']}")


def test_scenario_2_date_relative_filter(client: VizQLClient, api_key: str, site: str):
    """
    场景 2: DATE 类型 + RelativeDateFilter 筛选（相对日期）
    
    测试 DATE 类型字段使用 periodType/dateRangeType 进行相对日期筛选
    """
    print("\n" + "="*60)
    print("场景 2: DATE 类型 + RelativeDateFilter 筛选")
    print("="*60)
    
    metadata = get_metadata(client, DATE_TYPE_DATASOURCE_LUID, api_key, site)
    
    if "error" in metadata:
        print(f"✗ 获取元数据失败: {metadata['error']}")
        return
    
    date_fields = [f for f in metadata.get("data", []) 
                   if f.get("dataType") in ("DATE", "DATETIME")]
    
    if not date_fields:
        print("✗ 未找到 DATE 类型字段")
        return
    
    date_field = date_fields[0]["fieldCaption"]
    print(f"  使用日期字段: {date_field}")
    
    # 构建查询 - 最近 3 个月
    query = {
        "fields": [
            {"fieldCaption": date_field, "function": "MONTH"},
            {"fieldCaption": "Sales", "function": "SUM"}
        ],
        "filters": [
            {
                "field": {"fieldCaption": date_field},
                "filterType": "DATE",
                "periodType": "MONTHS",
                "dateRangeType": "LASTN",
                "rangeN": 3
            }
        ]
    }
    
    print(f"  查询: {json.dumps(query, indent=2, ensure_ascii=False)}")
    
    result = execute_query(client, DATE_TYPE_DATASOURCE_LUID, query, api_key, site)
    
    if "error" not in result:
        print(f"✓ 查询成功，返回 {len(result.get('data', []))} 条记录")
        print(f"  数据: {result.get('data', [])[:3]}")
    else:
        print(f"✗ 查询失败: {result['error']}")


def test_scenario_3_date_set_filter(client: VizQLClient, api_key: str, site: str):
    """
    场景 3: DATE 类型 + SET 筛选（离散日期）
    
    测试 DATE 类型字段使用 SET 筛选特定日期值
    """
    print("\n" + "="*60)
    print("场景 3: DATE 类型 + SET 筛选")
    print("="*60)
    
    metadata = get_metadata(client, DATE_TYPE_DATASOURCE_LUID, api_key, site)
    
    if "error" in metadata:
        print(f"✗ 获取元数据失败: {metadata['error']}")
        return
    
    date_fields = [f for f in metadata.get("data", []) 
                   if f.get("dataType") in ("DATE", "DATETIME")]
    
    if not date_fields:
        print("✗ 未找到 DATE 类型字段")
        return
    
    date_field = date_fields[0]["fieldCaption"]
    print(f"  使用日期字段: {date_field}")
    
    # 构建查询 - 特定日期
    query = {
        "fields": [
            {"fieldCaption": date_field},
            {"fieldCaption": "Sales", "function": "SUM"}
        ],
        "filters": [
            {
                "field": {"fieldCaption": date_field},
                "filterType": "SET",
                "values": ["2023-01-15", "2023-02-15", "2023-03-15"],
                "exclude": False
            }
        ]
    }
    
    print(f"  查询: {json.dumps(query, indent=2, ensure_ascii=False)}")
    
    result = execute_query(client, DATE_TYPE_DATASOURCE_LUID, query, api_key, site)
    
    if "error" not in result:
        print(f"✓ 查询成功，返回 {len(result.get('data', []))} 条记录")
        print(f"  数据: {result.get('data', [])[:3]}")
    else:
        print(f"✗ 查询失败: {result['error']}")


def test_scenario_4_string_dateparse_filter(client: VizQLClient, api_key: str, site: str):
    """
    场景 4: STRING 类型 + DATEPARSE + QUANTITATIVE_DATE 筛选
    
    测试 STRING 类型日期字段使用 DATEPARSE 转换后进行范围筛选
    """
    print("\n" + "="*60)
    print("场景 4: STRING 类型 + DATEPARSE + QUANTITATIVE_DATE 筛选")
    print("="*60)
    
    # 获取 STRING 类型数据源的元数据
    metadata = get_metadata(client, STRING_TYPE_DATASOURCE_LUID, api_key, site)
    
    if "error" in metadata:
        print(f"✗ 获取元数据失败: {metadata['error']}")
        return
    
    print(f"  数据源字段:")
    for field in metadata.get("data", [])[:15]:
        print(f"    - {field.get('fieldCaption')}: {field.get('dataType')}")
    
    # 找到 STRING 类型的日期字段
    string_fields = [f for f in metadata.get("data", []) 
                     if f.get("dataType") == "STRING"]
    
    if not string_fields:
        print("✗ 未找到 STRING 类型字段")
        return
    
    # 尝试找日期相关的字段
    string_date_field = None
    for f in string_fields:
        caption = f.get("fieldCaption", "").lower()
        if "date" in caption or "日期" in caption or "时间" in caption:
            string_date_field = f["fieldCaption"]
            break
    
    if not string_date_field:
        string_date_field = string_fields[0]["fieldCaption"]
    
    print(f"\n  使用字符串日期字段: {string_date_field}")
    
    # 找一个度量字段
    measure_fields = [f for f in metadata.get("data", []) 
                      if f.get("role") == "MEASURE" or f.get("dataType") in ("INTEGER", "REAL")]
    measure_field = measure_fields[0]["fieldCaption"] if measure_fields else string_date_field
    
    # 方案 A: 使用 CalculatedFilterField + DATEPARSE
    print("\n  方案 A - CalculatedFilterField + DATEPARSE:")
    query_a = {
        "fields": [
            {"fieldCaption": string_date_field},
            {"fieldCaption": measure_field, "function": "SUM"} if measure_field != string_date_field else {"fieldCaption": string_date_field}
        ],
        "filters": [
            {
                "field": {
                    "calculation": f"DATEPARSE('yyyy-MM-dd', [{string_date_field}])"
                },
                "filterType": "QUANTITATIVE_DATE",
                "quantitativeFilterType": "RANGE",
                "minDate": "2023-01-01",
                "maxDate": "2023-12-31"
            }
        ]
    }
    
    print(f"  查询: {json.dumps(query_a, indent=2, ensure_ascii=False)}")
    
    result_a = execute_query(client, STRING_TYPE_DATASOURCE_LUID, query_a, api_key, site)
    
    if "error" not in result_a:
        print(f"✓ 方案 A 成功，返回 {len(result_a.get('data', []))} 条记录")
        print(f"  数据: {result_a.get('data', [])[:3]}")
    else:
        print(f"✗ 方案 A 失败: {result_a['error'][:300]}...")
    
    # 方案 B: 先添加 DATEPARSE 计算字段到 fields，再筛选
    print("\n  方案 B - 计算字段 + 筛选引用:")
    query_b = {
        "fields": [
            {
                "fieldCaption": f"DATEPARSE_{string_date_field}",
                "calculation": f"DATEPARSE('yyyy-MM-dd', [{string_date_field}])"
            },
            {"fieldCaption": measure_field, "function": "SUM"} if measure_field != string_date_field else {"fieldCaption": string_date_field}
        ],
        "filters": [
            {
                "field": {"fieldCaption": f"DATEPARSE_{string_date_field}"},
                "filterType": "QUANTITATIVE_DATE",
                "quantitativeFilterType": "RANGE",
                "minDate": "2023-01-01",
                "maxDate": "2023-12-31"
            }
        ]
    }
    
    print(f"  查询: {json.dumps(query_b, indent=2, ensure_ascii=False)}")
    
    result_b = execute_query(client, STRING_TYPE_DATASOURCE_LUID, query_b, api_key, site)
    
    if "error" not in result_b:
        print(f"✓ 方案 B 成功，返回 {len(result_b.get('data', []))} 条记录")
        print(f"  数据: {result_b.get('data', [])[:3]}")
    else:
        print(f"✗ 方案 B 失败: {result_b['error'][:300]}...")


def test_scenario_5_string_set_filter(client: VizQLClient, api_key: str, site: str):
    """
    场景 5: STRING 类型 + SET 筛选（直接匹配字符串）
    
    测试 STRING 类型日期字段直接使用字符串值进行 SET 筛选
    """
    print("\n" + "="*60)
    print("场景 5: STRING 类型 + SET 筛选")
    print("="*60)
    
    metadata = get_metadata(client, STRING_TYPE_DATASOURCE_LUID, api_key, site)
    
    if "error" in metadata:
        print(f"✗ 获取元数据失败: {metadata['error']}")
        return
    
    string_fields = [f for f in metadata.get("data", []) 
                     if f.get("dataType") == "STRING"]
    
    if not string_fields:
        print("✗ 未找到 STRING 类型字段")
        return
    
    string_date_field = None
    for f in string_fields:
        caption = f.get("fieldCaption", "").lower()
        if "date" in caption or "日期" in caption:
            string_date_field = f["fieldCaption"]
            break
    
    if not string_date_field:
        string_date_field = string_fields[0]["fieldCaption"]
    
    print(f"  使用字符串日期字段: {string_date_field}")
    
    # 找一个度量字段
    measure_fields = [f for f in metadata.get("data", []) 
                      if f.get("role") == "MEASURE" or f.get("dataType") in ("INTEGER", "REAL")]
    measure_field = measure_fields[0]["fieldCaption"] if measure_fields else string_date_field
    
    # 构建查询 - 直接匹配字符串值
    query = {
        "fields": [
            {"fieldCaption": string_date_field},
            {"fieldCaption": measure_field, "function": "SUM"} if measure_field != string_date_field else {"fieldCaption": string_date_field}
        ],
        "filters": [
            {
                "field": {"fieldCaption": string_date_field},
                "filterType": "SET",
                "values": ["2023-01-15", "2023-02-15", "2023-03-15"],
                "exclude": False
            }
        ]
    }
    
    print(f"  查询: {json.dumps(query, indent=2, ensure_ascii=False)}")
    
    result = execute_query(client, STRING_TYPE_DATASOURCE_LUID, query, api_key, site)
    
    if "error" not in result:
        print(f"✓ 查询成功，返回 {len(result.get('data', []))} 条记录")
        print(f"  数据: {result.get('data', [])[:3]}")
    else:
        print(f"✗ 查询失败: {result['error'][:300]}...")


def test_scenario_6_string_match_filter(client: VizQLClient, api_key: str, site: str):
    """
    场景 6: STRING 类型 + MATCH 筛选（模糊匹配）
    
    测试 STRING 类型日期字段使用 MATCH 筛选进行模糊匹配
    """
    print("\n" + "="*60)
    print("场景 6: STRING 类型 + MATCH 筛选")
    print("="*60)
    
    metadata = get_metadata(client, STRING_TYPE_DATASOURCE_LUID, api_key, site)
    
    if "error" in metadata:
        print(f"✗ 获取元数据失败: {metadata['error']}")
        return
    
    string_fields = [f for f in metadata.get("data", []) 
                     if f.get("dataType") == "STRING"]
    
    if not string_fields:
        print("✗ 未找到 STRING 类型字段")
        return
    
    string_date_field = None
    for f in string_fields:
        caption = f.get("fieldCaption", "").lower()
        if "date" in caption or "日期" in caption:
            string_date_field = f["fieldCaption"]
            break
    
    if not string_date_field:
        string_date_field = string_fields[0]["fieldCaption"]
    
    print(f"  使用字符串日期字段: {string_date_field}")
    
    # 找一个度量字段
    measure_fields = [f for f in metadata.get("data", []) 
                      if f.get("role") == "MEASURE" or f.get("dataType") in ("INTEGER", "REAL")]
    measure_field = measure_fields[0]["fieldCaption"] if measure_fields else string_date_field
    
    # 构建查询 - 匹配以 "2023-01" 开头的日期
    query = {
        "fields": [
            {"fieldCaption": string_date_field},
            {"fieldCaption": measure_field, "function": "SUM"} if measure_field != string_date_field else {"fieldCaption": string_date_field}
        ],
        "filters": [
            {
                "field": {"fieldCaption": string_date_field},
                "filterType": "MATCH",
                "startsWith": "2023-01"
            }
        ]
    }
    
    print(f"  查询: {json.dumps(query, indent=2, ensure_ascii=False)}")
    
    result = execute_query(client, STRING_TYPE_DATASOURCE_LUID, query, api_key, site)
    
    if "error" not in result:
        print(f"✓ 查询成功，返回 {len(result.get('data', []))} 条记录")
        print(f"  数据: {result.get('data', [])[:3]}")
    else:
        print(f"✗ 查询失败: {result['error'][:300]}...")


def test_scenario_7_date_year_to_date(client: VizQLClient, api_key: str, site: str):
    """
    场景 7: DATE 类型 + 年初至今（TODATE）
    
    测试 DATE 类型字段使用 TODATE 进行年初至今筛选
    """
    print("\n" + "="*60)
    print("场景 7: DATE 类型 + 年初至今（TODATE）")
    print("="*60)
    
    metadata = get_metadata(client, DATE_TYPE_DATASOURCE_LUID, api_key, site)
    
    if "error" in metadata:
        print(f"✗ 获取元数据失败: {metadata['error']}")
        return
    
    date_fields = [f for f in metadata.get("data", []) 
                   if f.get("dataType") in ("DATE", "DATETIME")]
    
    if not date_fields:
        print("✗ 未找到 DATE 类型字段")
        return
    
    date_field = date_fields[0]["fieldCaption"]
    print(f"  使用日期字段: {date_field}")
    
    # 构建查询 - 年初至今
    query = {
        "fields": [
            {"fieldCaption": date_field, "function": "MONTH"},
            {"fieldCaption": "Sales", "function": "SUM"}
        ],
        "filters": [
            {
                "field": {"fieldCaption": date_field},
                "filterType": "DATE",
                "periodType": "YEARS",
                "dateRangeType": "TODATE"
            }
        ]
    }
    
    print(f"  查询: {json.dumps(query, indent=2, ensure_ascii=False)}")
    
    result = execute_query(client, DATE_TYPE_DATASOURCE_LUID, query, api_key, site)
    
    if "error" not in result:
        print(f"✓ 查询成功，返回 {len(result.get('data', []))} 条记录")
        print(f"  数据: {result.get('data', [])[:3]}")
    else:
        print(f"✗ 查询失败: {result['error']}")


# ═══════════════════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════════════════

def main():
    """运行所有测试场景"""
    print("="*60)
    print("日期筛选场景测试")
    print("="*60)
    print(f"DATE 类型数据源: {DATE_TYPE_DATASOURCE_LUID}")
    print(f"STRING 类型数据源: {STRING_TYPE_DATASOURCE_LUID}")
    
    # 获取客户端和认证
    try:
        client, api_key, site = get_client_and_auth()
        print(f"✓ 认证成功")
    except Exception as e:
        print(f"✗ 认证失败: {e}")
        return
    
    # 运行测试场景
    with client:
        test_scenarios = [
            test_scenario_1_date_quantitative_filter,
            test_scenario_2_date_relative_filter,
            test_scenario_3_date_set_filter,
            test_scenario_4_string_dateparse_filter,
            test_scenario_5_string_set_filter,
            test_scenario_6_string_match_filter,
            test_scenario_7_date_year_to_date,
        ]
        
        for scenario in test_scenarios:
            try:
                scenario(client, api_key, site)
            except Exception as e:
                print(f"✗ {scenario.__name__} 异常: {e}")
    
    print("\n" + "="*60)
    print("测试完成")
    print("="*60)


if __name__ == "__main__":
    main()
