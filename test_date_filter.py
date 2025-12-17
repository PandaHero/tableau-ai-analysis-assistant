"""
日期过滤器测试脚本

测试目的：
1. 测试 VizQL 的相对日期过滤器（RelativeDateFilter）
2. 测试 DATEPARSE 函数是否可以在 CalculatedField 中使用
3. 测试字符串类型字段是否可以通过 DATEPARSE 转换后使用日期过滤器

使用方法：
    python test_date_filter.py
"""
import os
import json
import logging
from dotenv import load_dotenv

# 加载环境变量
load_dotenv("tableau_assistant/.env")

from tableau_assistant.src.bi_platforms.tableau.vizql_client import VizQLClient, VizQLClientConfig
from tableau_assistant.src.bi_platforms.tableau.auth import get_tableau_auth

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_client_and_auth():
    """获取 VizQL 客户端和认证信息"""
    auth_ctx = get_tableau_auth()
    
    domain = auth_ctx.domain
    site = auth_ctx.site
    api_key = auth_ctx.api_key
    datasource_luid = os.getenv("DATASOURCE_LUID")
    
    if not datasource_luid:
        raise ValueError("请确保设置了 DATASOURCE_LUID 环境变量")
    
    config = VizQLClientConfig(
        base_url=domain,
        verify_ssl=os.getenv("VIZQL_VERIFY_SSL", "true").lower() == "true",
        ca_bundle=os.getenv("VIZQL_CA_BUNDLE"),
        timeout=30,
        max_retries=3
    )
    client = VizQLClient(config=config)
    
    return client, api_key, site, datasource_luid


def get_field_info(client, api_key, site, datasource_luid):
    """获取数据源字段信息"""
    logger.info("正在获取数据源元数据...")
    
    metadata = client.read_metadata(
        datasource_luid=datasource_luid,
        api_key=api_key,
        site=site
    )
    
    fields = metadata.get("data", [])
    
    date_fields = []
    string_fields = []
    measure_fields = []
    
    for field in fields:
        name = field.get("fieldCaption") or field.get("fieldName") or ""
        data_type = (field.get("dataType") or "").upper()
        default_agg = field.get("defaultAggregation", "")
        
        if not name:
            continue
        
        if data_type in ("DATE", "DATETIME"):
            date_fields.append({"name": name, "type": data_type})
        elif data_type == "STRING":
            string_fields.append({"name": name, "type": data_type})
        
        if default_agg in ("SUM", "AVG", "MIN", "MAX"):
            measure_fields.append({"name": name, "agg": default_agg})
    
    logger.info(f"日期字段: {[f['name'] for f in date_fields]}")
    logger.info(f"字符串字段示例: {[f['name'] for f in string_fields[:5]]}")
    logger.info(f"度量字段示例: {[f['name'] for f in measure_fields[:5]]}")
    
    return {
        "date_fields": date_fields,
        "string_fields": string_fields,
        "measure_fields": measure_fields,
        "all_fields": fields
    }


def test_relative_date_filter_lastn(client, api_key, site, datasource_luid, field_info):
    """
    测试 1: 相对日期过滤器 - LASTN
    
    测试 "最近 N 个月/年" 的过滤
    """
    logger.info("=" * 60)
    logger.info("测试 1: 相对日期过滤器 - LASTN (最近3个月)")
    logger.info("=" * 60)
    
    if not field_info["date_fields"]:
        logger.warning("没有找到日期字段，跳过测试")
        return False, "No date fields"
    
    date_field = field_info["date_fields"][0]["name"]
    measure_field = field_info["measure_fields"][0]["name"] if field_info["measure_fields"] else "Sales"
    
    logger.info(f"使用字段: 日期={date_field}, 度量={measure_field}")
    
    query = {
        "fields": [
            {"fieldCaption": date_field, "function": "MONTH"},
            {"fieldCaption": measure_field, "function": "SUM"}
        ],
        "filters": [
            {
                "filterType": "DATE",
                "field": {"fieldCaption": date_field},
                "periodType": "MONTHS",
                "dateRangeType": "LASTN",
                "rangeN": 3
            }
        ]
    }
    
    logger.info(f"查询请求:\n{json.dumps(query, indent=2, ensure_ascii=False)}")
    
    try:
        result = client.query_datasource(
            datasource_luid=datasource_luid,
            query=query,
            api_key=api_key,
            site=site
        )
        logger.info(f"✅ 查询成功！返回 {len(result.get('data', []))} 行数据")
        logger.info(f"数据:\n{json.dumps(result.get('data', []), indent=2, ensure_ascii=False)}")
        return True, result
    except Exception as e:
        logger.error(f"❌ 查询失败: {e}")
        return False, str(e)


def test_relative_date_filter_current(client, api_key, site, datasource_luid, field_info):
    """
    测试 2: 相对日期过滤器 - CURRENT
    
    测试 "当前年/月" 的过滤
    """
    logger.info("=" * 60)
    logger.info("测试 2: 相对日期过滤器 - CURRENT (当前年)")
    logger.info("=" * 60)
    
    if not field_info["date_fields"]:
        logger.warning("没有找到日期字段，跳过测试")
        return False, "No date fields"
    
    date_field = field_info["date_fields"][0]["name"]
    measure_field = field_info["measure_fields"][0]["name"] if field_info["measure_fields"] else "Sales"
    
    query = {
        "fields": [
            {"fieldCaption": date_field, "function": "MONTH"},
            {"fieldCaption": measure_field, "function": "SUM"}
        ],
        "filters": [
            {
                "filterType": "DATE",
                "field": {"fieldCaption": date_field},
                "periodType": "YEARS",
                "dateRangeType": "CURRENT"
            }
        ]
    }
    
    logger.info(f"查询请求:\n{json.dumps(query, indent=2, ensure_ascii=False)}")
    
    try:
        result = client.query_datasource(
            datasource_luid=datasource_luid,
            query=query,
            api_key=api_key,
            site=site
        )
        logger.info(f"✅ 查询成功！返回 {len(result.get('data', []))} 行数据")
        logger.info(f"数据:\n{json.dumps(result.get('data', []), indent=2, ensure_ascii=False)}")
        return True, result
    except Exception as e:
        logger.error(f"❌ 查询失败: {e}")
        return False, str(e)


def test_relative_date_filter_todate(client, api_key, site, datasource_luid, field_info):
    """
    测试 3: 相对日期过滤器 - TODATE
    
    测试 "年初至今" 的过滤
    """
    logger.info("=" * 60)
    logger.info("测试 3: 相对日期过滤器 - TODATE (年初至今)")
    logger.info("=" * 60)
    
    if not field_info["date_fields"]:
        logger.warning("没有找到日期字段，跳过测试")
        return False, "No date fields"
    
    date_field = field_info["date_fields"][0]["name"]
    measure_field = field_info["measure_fields"][0]["name"] if field_info["measure_fields"] else "Sales"
    
    query = {
        "fields": [
            {"fieldCaption": date_field, "function": "MONTH"},
            {"fieldCaption": measure_field, "function": "SUM"}
        ],
        "filters": [
            {
                "filterType": "DATE",
                "field": {"fieldCaption": date_field},
                "periodType": "YEARS",
                "dateRangeType": "TODATE"
            }
        ]
    }
    
    logger.info(f"查询请求:\n{json.dumps(query, indent=2, ensure_ascii=False)}")
    
    try:
        result = client.query_datasource(
            datasource_luid=datasource_luid,
            query=query,
            api_key=api_key,
            site=site
        )
        logger.info(f"✅ 查询成功！返回 {len(result.get('data', []))} 行数据")
        logger.info(f"数据:\n{json.dumps(result.get('data', []), indent=2, ensure_ascii=False)}")
        return True, result
    except Exception as e:
        logger.error(f"❌ 查询失败: {e}")
        return False, str(e)


def test_dateparse_calculated_field(client, api_key, site, datasource_luid, field_info):
    """
    测试 4: DATEPARSE 计算字段
    
    测试是否可以使用 DATEPARSE 将字符串转换为日期
    """
    logger.info("=" * 60)
    logger.info("测试 4: DATEPARSE 计算字段")
    logger.info("=" * 60)
    
    if not field_info["string_fields"]:
        logger.warning("没有找到字符串字段，跳过测试")
        return False, "No string fields"
    
    # 找一个可能包含日期的字符串字段
    string_field = field_info["string_fields"][0]["name"]
    measure_field = field_info["measure_fields"][0]["name"] if field_info["measure_fields"] else "Sales"
    
    logger.info(f"使用字段: 字符串={string_field}, 度量={measure_field}")
    
    # 尝试使用 DATEPARSE
    query = {
        "fields": [
            {
                "fieldCaption": "ParsedDate",
                "calculation": f"DATEPARSE('yyyy-MM-dd', [{string_field}])"
            },
            {"fieldCaption": measure_field, "function": "SUM"}
        ]
    }
    
    logger.info(f"查询请求:\n{json.dumps(query, indent=2, ensure_ascii=False)}")
    
    try:
        result = client.query_datasource(
            datasource_luid=datasource_luid,
            query=query,
            api_key=api_key,
            site=site
        )
        logger.info(f"✅ DATEPARSE 查询成功！")
        logger.info(f"数据:\n{json.dumps(result.get('data', [])[:5], indent=2, ensure_ascii=False)}")
        return True, result
    except Exception as e:
        logger.error(f"❌ DATEPARSE 查询失败: {e}")
        return False, str(e)


def test_dateparse_with_date_filter(client, api_key, site, datasource_luid, field_info):
    """
    测试 5: DATEPARSE + 日期过滤器
    
    测试是否可以对 DATEPARSE 转换后的字段使用日期过滤器
    """
    logger.info("=" * 60)
    logger.info("测试 5: DATEPARSE + 日期过滤器")
    logger.info("=" * 60)
    
    if not field_info["string_fields"]:
        logger.warning("没有找到字符串字段，跳过测试")
        return False, "No string fields"
    
    string_field = field_info["string_fields"][0]["name"]
    measure_field = field_info["measure_fields"][0]["name"] if field_info["measure_fields"] else "Sales"
    
    # 尝试对 DATEPARSE 结果使用日期过滤器
    query = {
        "fields": [
            {
                "fieldCaption": "ParsedDate",
                "calculation": f"DATEPARSE('yyyy-MM-dd', [{string_field}])"
            },
            {"fieldCaption": measure_field, "function": "SUM"}
        ],
        "filters": [
            {
                "filterType": "DATE",
                "field": {
                    "fieldCaption": "ParsedDate",
                    "calculation": f"DATEPARSE('yyyy-MM-dd', [{string_field}])"
                },
                "periodType": "YEARS",
                "dateRangeType": "CURRENT"
            }
        ]
    }
    
    logger.info(f"查询请求:\n{json.dumps(query, indent=2, ensure_ascii=False)}")
    
    try:
        result = client.query_datasource(
            datasource_luid=datasource_luid,
            query=query,
            api_key=api_key,
            site=site
        )
        logger.info(f"✅ DATEPARSE + 过滤器查询成功！")
        logger.info(f"数据:\n{json.dumps(result.get('data', [])[:5], indent=2, ensure_ascii=False)}")
        return True, result
    except Exception as e:
        logger.error(f"❌ DATEPARSE + 过滤器查询失败: {e}")
        return False, str(e)


def test_quantitative_date_filter(client, api_key, site, datasource_luid, field_info):
    """
    测试 6: 绝对日期范围过滤器 (QUANTITATIVE_DATE)
    
    测试使用具体日期范围的过滤
    注意：需要 quantitativeFilterType 和 minDate/maxDate（不是 min/max）
    """
    logger.info("=" * 60)
    logger.info("测试 6: 绝对日期范围过滤器 (QUANTITATIVE_DATE)")
    logger.info("=" * 60)
    
    if not field_info["date_fields"]:
        logger.warning("没有找到日期字段，跳过测试")
        return False, "No date fields"
    
    date_field = field_info["date_fields"][0]["name"]
    measure_field = field_info["measure_fields"][0]["name"] if field_info["measure_fields"] else "Sales"
    
    query = {
        "fields": [
            {"fieldCaption": date_field, "function": "MONTH"},
            {"fieldCaption": measure_field, "function": "SUM"}
        ],
        "filters": [
            {
                "filterType": "QUANTITATIVE_DATE",
                "field": {"fieldCaption": date_field},
                "quantitativeFilterType": "RANGE",
                "minDate": "2024-01-01",
                "maxDate": "2024-12-31"
            }
        ]
    }
    
    logger.info(f"查询请求:\n{json.dumps(query, indent=2, ensure_ascii=False)}")
    
    try:
        result = client.query_datasource(
            datasource_luid=datasource_luid,
            query=query,
            api_key=api_key,
            site=site
        )
        logger.info(f"✅ 查询成功！返回 {len(result.get('data', []))} 行数据")
        logger.info(f"数据:\n{json.dumps(result.get('data', []), indent=2, ensure_ascii=False)}")
        return True, result
    except Exception as e:
        logger.error(f"❌ 查询失败: {e}")
        return False, str(e)


def main():
    """运行所有测试"""
    logger.info("开始日期过滤器测试...")
    
    try:
        client, api_key, site, datasource_luid = get_client_and_auth()
        logger.info(f"连接到 Tableau: {os.getenv('TABLEAU_DOMAIN')}")
        logger.info(f"数据源 LUID: {datasource_luid}")
    except Exception as e:
        logger.error(f"初始化失败: {e}")
        return
    
    all_results = {}
    
    with client:
        # 获取字段信息
        field_info = get_field_info(client, api_key, site, datasource_luid)
        
        # 测试 1: LASTN
        all_results['test1_lastn'] = test_relative_date_filter_lastn(
            client, api_key, site, datasource_luid, field_info
        )
        
        # 测试 2: CURRENT
        all_results['test2_current'] = test_relative_date_filter_current(
            client, api_key, site, datasource_luid, field_info
        )
        
        # 测试 3: TODATE
        all_results['test3_todate'] = test_relative_date_filter_todate(
            client, api_key, site, datasource_luid, field_info
        )
        
        # 测试 4: DATEPARSE
        all_results['test4_dateparse'] = test_dateparse_calculated_field(
            client, api_key, site, datasource_luid, field_info
        )
        
        # 测试 5: DATEPARSE + 过滤器
        all_results['test5_dateparse_filter'] = test_dateparse_with_date_filter(
            client, api_key, site, datasource_luid, field_info
        )
        
        # 测试 6: QUANTITATIVE_DATE
        all_results['test6_quantitative'] = test_quantitative_date_filter(
            client, api_key, site, datasource_luid, field_info
        )
    
    # 输出总结
    logger.info("\n" + "=" * 60)
    logger.info("测试总结")
    logger.info("=" * 60)
    
    print("\n测试结果总结：")
    print("-" * 40)
    
    test_names = {
        'test1_lastn': '相对日期 LASTN (最近N个月)',
        'test2_current': '相对日期 CURRENT (当前年)',
        'test3_todate': '相对日期 TODATE (年初至今)',
        'test4_dateparse': 'DATEPARSE 计算字段',
        'test5_dateparse_filter': 'DATEPARSE + 日期过滤器',
        'test6_quantitative': '绝对日期范围 QUANTITATIVE_DATE'
    }
    
    for key, name in test_names.items():
        success, _ = all_results.get(key, (False, "Not run"))
        status = '✅ 成功' if success else '❌ 失败'
        print(f"{name}: {status}")


if __name__ == "__main__":
    main()
