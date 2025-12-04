"""
测试 VizQL API 的计算功能

测试内容：
1. LOD 计算（FIXED, INCLUDE, EXCLUDE）
2. 表计算（窗口函数：RUNNING_SUM, RUNNING_AVG, WINDOW_SUM 等）
3. 聚合函数（SUM, AVG, COUNT, COUNTD, MIN, MAX 等）

目的：探索 VizQL API 支持的计算类型，补充 openapi.json 文档
"""
import os
import sys
import time

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv

load_dotenv()


def get_client():
    """获取 VizQL 客户端"""
    from tableau_assistant.src.bi_platforms.tableau.auth import _get_tableau_context_from_env
    from tableau_assistant.src.bi_platforms.tableau.vizql_client import VizQLClient, VizQLClientConfig
    
    ctx = _get_tableau_context_from_env()
    domain = os.getenv('TABLEAU_DOMAIN')
    
    config = VizQLClientConfig(base_url=domain, timeout=30, max_retries=3)
    client = VizQLClient(config=config)
    
    return client, ctx['api_key'], os.getenv('TABLEAU_SITE'), os.getenv('DATASOURCE_LUID')


def test_query(client, api_key, site, luid, query, description):
    """执行查询并打印结果"""
    print(f"\n{'='*60}")
    print(f"测试: {description}")
    print(f"{'='*60}")
    print(f"Query: {query}")
    
    try:
        start = time.time()
        result = client.query_datasource(
            datasource_luid=luid,
            query=query,
            api_key=api_key,
            site=site
        )
        elapsed = time.time() - start
        
        data = result.get("data", [])
        print(f"✓ 成功! 耗时: {elapsed:.2f}s, 返回 {len(data)} 行")
        
        # 打印前3行数据
        if data:
            print("数据示例:")
            for i, row in enumerate(data[:3]):
                print(f"  {i+1}. {row}")
        
        return True, result
        
    except Exception as e:
        print(f"✗ 失败: {e}")
        return False, str(e)


def main():
    print("=" * 60)
    print("VizQL API 计算功能测试")
    print("=" * 60)
    
    client, api_key, site, luid = get_client()
    
    # 先获取一些字段信息
    print("\n获取元数据...")
    meta = client.read_metadata(datasource_luid=luid, api_key=api_key, site=site)
    fields = meta.get("data", [])
    
    # 找维度和度量字段
    # 根据实际数据：STRING 类型且 aggregation=COUNT 的是维度，REAL 类型且 aggregation=SUM 的是度量
    dim_field = None
    measure_field = None
    date_field = None
    
    for f in fields:
        caption = f.get("fieldCaption", "")
        dtype = f.get("dataType", "")
        agg = f.get("defaultAggregation")
        
        # 维度：STRING 类型，通常是名称类字段
        if not dim_field and dtype == "STRING" and "_nm" in caption.lower():
            dim_field = caption
        # 度量：REAL 类型，SUM 聚合
        if not measure_field and dtype == "REAL" and agg == "SUM":
            measure_field = caption
        # 日期：字段名包含 dt 且是 DATE 类型，或者字段名明确是日期
        if not date_field and ("_dt" in caption.lower() or dtype in ["DATE", "DATETIME"]):
            date_field = caption
    
    # 如果没找到合适的维度，用第一个 STRING 字段
    if not dim_field:
        for f in fields:
            if f.get("dataType") == "STRING":
                dim_field = f.get("fieldCaption")
                break
    
    print(f"维度字段: {dim_field}")
    print(f"度量字段: {measure_field}")
    print(f"日期字段: {date_field}")
    
    results = {}
    
    # ==================== 1. 基础聚合函数 ====================
    print("\n" + "=" * 60)
    print("1. 基础聚合函数测试")
    print("=" * 60)
    
    # SUM
    results["SUM"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"}
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "SUM 聚合")
    
    # AVG
    results["AVG"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "AVG"}
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "AVG 聚合")
    
    # COUNT
    results["COUNT"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "COUNT"}
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "COUNT 聚合")
    
    # COUNTD
    results["COUNTD"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": "countd_test", "calculation": f"COUNTD([{dim_field}])"}
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "COUNTD 聚合")
    
    # MIN
    results["MIN"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "MIN"}
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "MIN 聚合")
    
    # MAX
    results["MAX"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "MAX"}
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "MAX 聚合")
    
    # ==================== 2. LOD 计算 ====================
    print("\n" + "=" * 60)
    print("2. LOD 计算测试 (FIXED, INCLUDE, EXCLUDE)")
    print("=" * 60)
    
    # FIXED LOD - 全局 COUNTD
    results["FIXED_COUNTD"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": "fixed_countd", "calculation": f"{{FIXED : COUNTD([{dim_field}])}}"}
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "FIXED LOD - 全局 COUNTD")
    
    # FIXED LOD - 按维度计算 SUM
    results["FIXED_SUM"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": "fixed_sum", "calculation": f"{{FIXED [{dim_field}] : SUM([{measure_field}])}}"}
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "FIXED LOD - 按维度 SUM")
    
    # INCLUDE LOD
    results["INCLUDE"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": "include_sum", "calculation": f"{{INCLUDE [{dim_field}] : SUM([{measure_field}])}}"}
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "INCLUDE LOD")
    
    # EXCLUDE LOD
    results["EXCLUDE"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": "exclude_sum", "calculation": f"{{EXCLUDE [{dim_field}] : SUM([{measure_field}])}}"}
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "EXCLUDE LOD")
    
    # ==================== 3. 表计算（窗口函数） ====================
    print("\n" + "=" * 60)
    print("3. 表计算测试 (窗口函数)")
    print("=" * 60)
    
    # RUNNING_TOTAL - 使用正确的 tableCalculation 格式
    # 必须包含 tableCalcType 和 dimensions
    results["RUNNING_TOTAL"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": "running_total",
                "calculation": f"SUM([{measure_field}])",
                "tableCalculation": {
                    "tableCalcType": "RUNNING_TOTAL",
                    "dimensions": [{"fieldCaption": dim_field}],
                    "aggregation": "SUM"
                }
            }
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "RUNNING_TOTAL 表计算")
    
    # RUNNING_TOTAL with AVG
    results["RUNNING_AVG"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": "running_avg",
                "calculation": f"SUM([{measure_field}])",
                "tableCalculation": {
                    "tableCalcType": "RUNNING_TOTAL",
                    "dimensions": [{"fieldCaption": dim_field}],
                    "aggregation": "AVG"
                }
            }
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "RUNNING_AVG 表计算")
    
    # PERCENT_OF_TOTAL
    results["PERCENT_OF_TOTAL"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": "pct_total",
                "calculation": f"SUM([{measure_field}])",
                "tableCalculation": {
                    "tableCalcType": "PERCENT_OF_TOTAL",
                    "dimensions": [{"fieldCaption": dim_field}]
                }
            }
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "PERCENT_OF_TOTAL 表计算")
    
    # RANK
    results["RANK"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": "rank",
                "calculation": f"SUM([{measure_field}])",
                "tableCalculation": {
                    "tableCalcType": "RANK",
                    "dimensions": [{"fieldCaption": dim_field}]
                }
            }
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "RANK 表计算")
    
    # PERCENTILE
    results["PERCENTILE"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": "percentile",
                "calculation": f"SUM([{measure_field}])",
                "tableCalculation": {
                    "tableCalcType": "PERCENTILE",
                    "dimensions": [{"fieldCaption": dim_field}]
                }
            }
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "PERCENTILE 表计算")
    
    # MOVING_CALCULATION (移动平均)
    results["MOVING_CALC"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": "moving_avg",
                "calculation": f"SUM([{measure_field}])",
                "tableCalculation": {
                    "tableCalcType": "MOVING_CALCULATION",
                    "dimensions": [{"fieldCaption": dim_field}],
                    "aggregation": "AVG",
                    "previous": -2,
                    "next": 0
                }
            }
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "MOVING_CALCULATION 表计算 (窗口 -2 到 0)")
    
    # DIFFERENCE_FROM
    results["DIFFERENCE_FROM"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": "difference",
                "calculation": f"SUM([{measure_field}])",
                "tableCalculation": {
                    "tableCalcType": "DIFFERENCE_FROM",
                    "dimensions": [{"fieldCaption": dim_field}],
                    "relativeTo": "PREVIOUS"
                }
            }
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "DIFFERENCE_FROM 表计算")
    
    # PERCENT_DIFFERENCE_FROM
    results["PERCENT_DIFFERENCE_FROM"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": "pct_diff",
                "calculation": f"SUM([{measure_field}])",
                "tableCalculation": {
                    "tableCalcType": "PERCENT_DIFFERENCE_FROM",
                    "dimensions": [{"fieldCaption": dim_field}],
                    "relativeTo": "PREVIOUS"
                }
            }
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "PERCENT_DIFFERENCE_FROM 表计算")
    
    # ==================== 4. CUSTOM 类型表计算（窗口函数） ====================
    # 使用 tableCalcType: "CUSTOM" + calculation 字符串可以支持所有窗口函数
    print("\n" + "=" * 60)
    print("4. CUSTOM 类型表计算 (窗口函数)")
    print("=" * 60)
    
    # WINDOW_SUM - 使用 CUSTOM 类型
    results["CUSTOM_WINDOW_SUM"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": "window_sum",
                "calculation": f"WINDOW_SUM(SUM([{measure_field}]))",
                "tableCalculation": {
                    "tableCalcType": "CUSTOM",
                    "dimensions": [{"fieldCaption": dim_field}]
                }
            }
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "CUSTOM + WINDOW_SUM")
    
    # WINDOW_AVG - 使用 CUSTOM 类型
    results["CUSTOM_WINDOW_AVG"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": "window_avg",
                "calculation": f"WINDOW_AVG(SUM([{measure_field}]), -2, 0)",
                "tableCalculation": {
                    "tableCalcType": "CUSTOM",
                    "dimensions": [{"fieldCaption": dim_field}]
                }
            }
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "CUSTOM + WINDOW_AVG")
    
    # INDEX - 使用 CUSTOM 类型
    results["CUSTOM_INDEX"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": "index_val",
                "calculation": "INDEX()",
                "tableCalculation": {
                    "tableCalcType": "CUSTOM",
                    "dimensions": [{"fieldCaption": dim_field}]
                }
            }
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "CUSTOM + INDEX")
    
    # LOOKUP - 使用 CUSTOM 类型
    results["CUSTOM_LOOKUP"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": "lookup_val",
                "calculation": f"LOOKUP(SUM([{measure_field}]), -1)",
                "tableCalculation": {
                    "tableCalcType": "CUSTOM",
                    "dimensions": [{"fieldCaption": dim_field}]
                }
            }
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "CUSTOM + LOOKUP")
    
    # SIZE - 使用 CUSTOM 类型
    results["CUSTOM_SIZE"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": "size_val",
                "calculation": "SIZE()",
                "tableCalculation": {
                    "tableCalcType": "CUSTOM",
                    "dimensions": [{"fieldCaption": dim_field}]
                }
            }
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "CUSTOM + SIZE")
    
    # ==================== 总结 ====================
    print("\n" + "=" * 60)
    print("测试结果总结")
    print("=" * 60)
    
    success_count = sum(1 for r in results.values() if r[0])
    fail_count = sum(1 for r in results.values() if not r[0])
    
    print(f"\n成功: {success_count}, 失败: {fail_count}")
    
    print("\n成功的测试:")
    for name, (success, _) in results.items():
        if success:
            print(f"  ✓ {name}")
    
    print("\n失败的测试:")
    for name, (success, error) in results.items():
        if not success:
            print(f"  ✗ {name}: {error[:100]}...")
    
    client.close()
    print("\n测试完成!")


if __name__ == "__main__":
    main()
