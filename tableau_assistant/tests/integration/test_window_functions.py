"""
测试 VizQL API 的窗口函数

测试 CUSTOM 类型的表计算，探索 WINDOW_SUM, WINDOW_AVG 等函数的正确用法
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
    
    try:
        import json
        print(f"Query: {json.dumps(query, indent=2, ensure_ascii=False)}")
    except:
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
    print("VizQL API 窗口函数测试")
    print("=" * 60)
    
    client, api_key, site, luid = get_client()
    
    # 获取字段信息
    print("\n获取元数据...")
    meta = client.read_metadata(datasource_luid=luid, api_key=api_key, site=site)
    fields = meta.get("data", [])
    
    dim_field = None
    measure_field = None
    
    for f in fields:
        caption = f.get("fieldCaption", "")
        dtype = f.get("dataType", "")
        agg = f.get("defaultAggregation")
        
        if not dim_field and dtype == "STRING" and "_nm" in caption.lower():
            dim_field = caption
        if not measure_field and dtype == "REAL" and agg == "SUM":
            measure_field = caption
    
    if not dim_field:
        for f in fields:
            if f.get("dataType") == "STRING":
                dim_field = f.get("fieldCaption")
                break
    
    print(f"维度字段: {dim_field}")
    print(f"度量字段: {measure_field}")
    
    results = {}
    
    # ==================== 测试 CUSTOM 类型表计算 ====================
    print("\n" + "=" * 60)
    print("1. 测试 CUSTOM 类型表计算 (用于自定义窗口函数)")
    print("=" * 60)
    
    # 测试1: CUSTOM 类型 + calculation 字符串中使用 WINDOW_SUM
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
    }, "CUSTOM + WINDOW_SUM calculation")
    
    # 测试2: CUSTOM 类型 + WINDOW_AVG
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
    }, "CUSTOM + WINDOW_AVG calculation")
    
    # 测试3: CUSTOM 类型 + RANK
    results["CUSTOM_RANK"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": "rank_custom",
                "calculation": f"RANK(SUM([{measure_field}]))",
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
    }, "CUSTOM + RANK calculation")
    
    # 测试4: CUSTOM 类型 + INDEX
    results["CUSTOM_INDEX"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": "index_custom",
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
    }, "CUSTOM + INDEX calculation")
    
    # 测试5: CUSTOM 类型 + LOOKUP
    results["CUSTOM_LOOKUP"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": "lookup_custom",
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
    }, "CUSTOM + LOOKUP calculation")
    
    # 测试6: CUSTOM 类型 + FIRST
    results["CUSTOM_FIRST"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": "first_custom",
                "calculation": "FIRST()",
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
    }, "CUSTOM + FIRST calculation")
    
    # 测试7: CUSTOM 类型 + LAST
    results["CUSTOM_LAST"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": "last_custom",
                "calculation": "LAST()",
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
    }, "CUSTOM + LAST calculation")
    
    # 测试8: CUSTOM 类型 + SIZE
    results["CUSTOM_SIZE"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": "size_custom",
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
    }, "CUSTOM + SIZE calculation")
    
    # 测试9: CUSTOM 类型 + RUNNING_SUM
    results["CUSTOM_RUNNING_SUM"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": "running_sum_custom",
                "calculation": f"RUNNING_SUM(SUM([{measure_field}]))",
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
    }, "CUSTOM + RUNNING_SUM calculation")
    
    # ==================== 测试 NESTED 类型 ====================
    print("\n" + "=" * 60)
    print("2. 测试 NESTED 类型表计算")
    print("=" * 60)
    
    # NESTED 需要 fieldCaption 引用另一个表计算
    results["NESTED_CALC"] = test_query(client, api_key, site, luid, {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": "running_total_base",
                "calculation": f"SUM([{measure_field}])",
                "tableCalculation": {
                    "tableCalcType": "RUNNING_TOTAL",
                    "dimensions": [{"fieldCaption": dim_field}],
                    "aggregation": "SUM"
                }
            },
            {
                "fieldCaption": "nested_pct",
                "tableCalculation": {
                    "tableCalcType": "NESTED",
                    "dimensions": [{"fieldCaption": dim_field}],
                    "fieldCaption": "running_total_base"
                },
                "nestedTableCalculations": [{
                    "tableCalcType": "PERCENT_OF_TOTAL",
                    "dimensions": [{"fieldCaption": dim_field}]
                }]
            }
        ],
        "filters": [{
            "filterType": "TOP",
            "field": {"fieldCaption": dim_field},
            "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
            "howMany": 5,
            "direction": "TOP"
        }]
    }, "NESTED 表计算")
    
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
            error_str = str(error)[:150] if len(str(error)) > 150 else str(error)
            print(f"  ✗ {name}: {error_str}...")
    
    client.close()
    print("\n测试完成!")


if __name__ == "__main__":
    main()
