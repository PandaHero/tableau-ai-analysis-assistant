"""
日期过滤器测试脚本 v2

修正测试 5 的语法错误，验证：
1. CalculatedFilterField 只需要 calculation，不需要 fieldCaption
2. 相对日期过滤器是否支持计算字段

使用方法：
    python test_date_filter_v2.py
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


def test_dateparse_with_relative_date_filter_fixed(client, api_key, site, datasource_luid, field_info):
    """
    测试 A: DATEPARSE + 相对日期过滤器（修正语法）
    
    修正：CalculatedFilterField 只需要 calculation，不需要 fieldCaption
    """
    logger.info("=" * 60)
    logger.info("测试 A: DATEPARSE + 相对日期过滤器（修正语法）")
    logger.info("=" * 60)
    
    if not field_info["string_fields"]:
        logger.warning("没有找到字符串字段，跳过测试")
        return False, "No string fields"
    
    string_field = field_info["string_fields"][0]["name"]
    measure_field = field_info["measure_fields"][0]["name"] if field_info["measure_fields"] else "Sales"
    
    # 修正：CalculatedFilterField 只需要 calculation
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
                    "calculation": f"DATEPARSE('yyyy-MM-dd', [{string_field}])"  # 只有 calculation
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
        logger.info(f"✅ 查询成功！返回 {len(result.get('data', []))} 行数据")
        logger.info(f"数据:\n{json.dumps(result.get('data', [])[:5], indent=2, ensure_ascii=False)}")
        return True, result
    except Exception as e:
        logger.error(f"❌ 查询失败: {e}")
        return False, str(e)


def test_dateparse_with_quantitative_date_filter(client, api_key, site, datasource_luid, field_info):
    """
    测试 B: DATEPARSE + 绝对日期过滤器（QUANTITATIVE_DATE）
    
    如果相对日期过滤器不支持计算字段，那么绝对日期过滤器是否支持？
    """
    logger.info("=" * 60)
    logger.info("测试 B: DATEPARSE + 绝对日期过滤器（QUANTITATIVE_DATE）")
    logger.info("=" * 60)
    
    if not field_info["string_fields"]:
        logger.warning("没有找到字符串字段，跳过测试")
        return False, "No string fields"
    
    string_field = field_info["string_fields"][0]["name"]
    measure_field = field_info["measure_fields"][0]["name"] if field_info["measure_fields"] else "Sales"
    
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
                "filterType": "QUANTITATIVE_DATE",
                "field": {
                    "calculation": f"DATEPARSE('yyyy-MM-dd', [{string_field}])"
                },
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
        logger.info(f"数据:\n{json.dumps(result.get('data', [])[:5], indent=2, ensure_ascii=False)}")
        return True, result
    except Exception as e:
        logger.error(f"❌ 查询失败: {e}")
        return False, str(e)


def test_dateparse_with_relative_filter_by_fieldname(client, api_key, site, datasource_luid, field_info):
    """
    测试 D: DATEPARSE + 相对日期过滤器（通过字段名引用）
    
    在 fields 中定义计算字段 ParsedDate，然后在 filter 中直接引用这个字段名
    """
    logger.info("=" * 60)
    logger.info("测试 D: DATEPARSE + 相对日期过滤器（通过字段名引用）")
    logger.info("=" * 60)
    
    if not field_info["string_fields"]:
        logger.warning("没有找到字符串字段，跳过测试")
        return False, "No string fields"
    
    string_field = field_info["string_fields"][0]["name"]
    measure_field = field_info["measure_fields"][0]["name"] if field_info["measure_fields"] else "Sales"
    
    # 在 fields 中定义计算字段，然后在 filter 中通过 fieldCaption 引用
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
                    "fieldCaption": "ParsedDate"  # 直接引用 fields 中定义的字段名
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
        logger.info(f"✅ 查询成功！返回 {len(result.get('data', []))} 行数据")
        logger.info(f"数据:\n{json.dumps(result.get('data', [])[:5], indent=2, ensure_ascii=False)}")
        return True, result
    except Exception as e:
        logger.error(f"❌ 查询失败: {e}")
        return False, str(e)


def test_dateparse_with_relative_filter_by_calculation_ref(client, api_key, site, datasource_luid, field_info):
    """
    测试 E: DATEPARSE + 相对日期过滤器（通过 calculation 引用字段名）
    
    尝试 "calculation": "[ParsedDate]" 的方式引用已定义的计算字段
    """
    logger.info("=" * 60)
    logger.info("测试 E: DATEPARSE + 相对日期过滤器（calculation引用字段名）")
    logger.info("=" * 60)
    
    if not field_info["string_fields"]:
        logger.warning("没有找到字符串字段，跳过测试")
        return False, "No string fields"
    
    string_field = field_info["string_fields"][0]["name"]
    measure_field = field_info["measure_fields"][0]["name"] if field_info["measure_fields"] else "Sales"
    
    # 尝试通过 calculation 引用已定义的字段名
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
                    "calculation": "[ParsedDate]"  # 通过 calculation 引用字段名
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
        logger.info(f"✅ 查询成功！返回 {len(result.get('data', []))} 行数据")
        logger.info(f"数据:\n{json.dumps(result.get('data', [])[:5], indent=2, ensure_ascii=False)}")
        return True, result
    except Exception as e:
        logger.error(f"❌ 查询失败: {e}")
        return False, str(e)


def test_condition_filter_with_dateparse(client, api_key, site, datasource_luid, field_info):
    """
    测试 F: CONDITION 过滤器 + DATEPARSE
    
    使用 CONDITION 过滤器的 calculation 属性来实现日期筛选
    """
    logger.info("=" * 60)
    logger.info("测试 F: CONDITION 过滤器 + DATEPARSE")
    logger.info("=" * 60)
    
    if not field_info["string_fields"]:
        logger.warning("没有找到字符串字段，跳过测试")
        return False, "No string fields"
    
    string_field = field_info["string_fields"][0]["name"]
    measure_field = field_info["measure_fields"][0]["name"] if field_info["measure_fields"] else "Sales"
    
    # 使用 CONDITION 过滤器
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
                "filterType": "CONDITION",
                "field": {
                    "fieldCaption": measure_field,
                    "function": "SUM"
                },
                "calculation": f"YEAR(DATEPARSE('yyyy-MM-dd', [{string_field}])) = 2024"
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
        logger.info(f"数据:\n{json.dumps(result.get('data', [])[:5], indent=2, ensure_ascii=False)}")
        return True, result
    except Exception as e:
        logger.error(f"❌ 查询失败: {e}")
        return False, str(e)


def test_quantitative_date_with_date_function(client, api_key, site, datasource_luid, field_info):
    """
    测试 G: QUANTITATIVE_DATE + DATE() 函数包装
    
    尝试用 DATE() 函数明确告诉 VizQL 这是日期类型
    """
    logger.info("=" * 60)
    logger.info("测试 G: QUANTITATIVE_DATE + DATE() 函数包装")
    logger.info("=" * 60)
    
    if not field_info["string_fields"]:
        logger.warning("没有找到字符串字段，跳过测试")
        return False, "No string fields"
    
    string_field = field_info["string_fields"][0]["name"]
    measure_field = field_info["measure_fields"][0]["name"] if field_info["measure_fields"] else "Sales"
    
    # 尝试用 DATE() 包装
    query = {
        "fields": [
            {
                "fieldCaption": "ParsedDate",
                "calculation": f"DATE(DATEPARSE('yyyy-MM-dd', [{string_field}]))"
            },
            {"fieldCaption": measure_field, "function": "SUM"}
        ],
        "filters": [
            {
                "filterType": "DATE",
                "field": {
                    "calculation": f"DATE(DATEPARSE('yyyy-MM-dd', [{string_field}]))"
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
        logger.info(f"✅ 查询成功！返回 {len(result.get('data', []))} 行数据")
        logger.info(f"数据:\n{json.dumps(result.get('data', [])[:5], indent=2, ensure_ascii=False)}")
        return True, result
    except Exception as e:
        logger.error(f"❌ 查询失败: {e}")
        return False, str(e)


def test_relative_date_filter_without_fields_definition(client, api_key, site, datasource_luid, field_info):
    """
    测试 H: 不在 fields 中定义计算字段，直接在 filter 中使用 DATE(DATEPARSE(...))
    
    你的建议：fields 只查询原始字段，filter 中直接写日期转换表达式
    """
    logger.info("=" * 60)
    logger.info("测试 H: 不定义计算字段，直接在 filter 中用 DATE(DATEPARSE(...))")
    logger.info("=" * 60)
    
    if not field_info["string_fields"]:
        logger.warning("没有找到字符串字段，跳过测试")
        return False, "No string fields"
    
    string_field = field_info["string_fields"][0]["name"]
    measure_field = field_info["measure_fields"][0]["name"] if field_info["measure_fields"] else "Sales"
    
    # 不在 fields 中定义计算字段，直接在 filter 中使用
    query = {
        "fields": [
            {"fieldCaption": string_field},  # 直接查询原始字符串字段
            {"fieldCaption": measure_field, "function": "SUM"}
        ],
        "filters": [
            {
                "filterType": "DATE",
                "field": {
                    "calculation": f"DATE(DATEPARSE('yyyy-MM-dd', [{string_field}]))"
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
        logger.info(f"✅ 查询成功！返回 {len(result.get('data', []))} 行数据")
        logger.info(f"数据:\n{json.dumps(result.get('data', [])[:5], indent=2, ensure_ascii=False)}")
        return True, result
    except Exception as e:
        logger.error(f"❌ 查询失败: {e}")
        return False, str(e)


def test_quantitative_date_simulating_relative(client, api_key, site, datasource_luid, field_info):
    """
    测试 I: 用 QUANTITATIVE_DATE 模拟相对日期过滤器
    
    思路：既然相对日期过滤器不支持 calculation，那我们用 QUANTITATIVE_DATE + 动态日期范围
    来实现相同的效果。例如"今年"可以用 minDate=2025-01-01, maxDate=2025-12-31
    """
    logger.info("=" * 60)
    logger.info("测试 I: 用 QUANTITATIVE_DATE 模拟相对日期过滤器（今年）")
    logger.info("=" * 60)
    
    if not field_info["string_fields"]:
        logger.warning("没有找到字符串字段，跳过测试")
        return False, "No string fields"
    
    string_field = field_info["string_fields"][0]["name"]
    measure_field = field_info["measure_fields"][0]["name"] if field_info["measure_fields"] else "Sales"
    
    # 动态计算今年的日期范围
    from datetime import datetime
    current_year = datetime.now().year
    min_date = f"{current_year}-01-01"
    max_date = f"{current_year}-12-31"
    
    # 用 QUANTITATIVE_DATE 模拟 "今年" 的相对日期过滤
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
                "filterType": "QUANTITATIVE_DATE",
                "field": {
                    "calculation": f"DATEPARSE('yyyy-MM-dd', [{string_field}])"
                },
                "quantitativeFilterType": "RANGE",
                "minDate": min_date,
                "maxDate": max_date
            }
        ]
    }
    
    logger.info(f"查询请求:\n{json.dumps(query, indent=2, ensure_ascii=False)}")
    logger.info(f"模拟相对日期：今年 ({min_date} ~ {max_date})")
    
    try:
        result = client.query_datasource(
            datasource_luid=datasource_luid,
            query=query,
            api_key=api_key,
            site=site
        )
        logger.info(f"✅ 查询成功！返回 {len(result.get('data', []))} 行数据")
        logger.info(f"数据:\n{json.dumps(result.get('data', [])[:5], indent=2, ensure_ascii=False)}")
        return True, result
    except Exception as e:
        logger.error(f"❌ 查询失败: {e}")
        return False, str(e)


def test_set_filter_with_year_calculation(client, api_key, site, datasource_luid, field_info):
    """
    测试 J: SET 过滤器 + YEAR() 计算
    
    思路：用 SET 过滤器筛选年份值，虽然 SET 不支持 calculation，
    但可以对原生日期字段使用 YEAR() 函数
    """
    logger.info("=" * 60)
    logger.info("测试 J: SET 过滤器 + 原生日期字段的 YEAR")
    logger.info("=" * 60)
    
    if not field_info["date_fields"]:
        logger.warning("没有找到日期字段，跳过测试")
        return False, "No date fields"
    
    date_field = field_info["date_fields"][0]["name"]
    measure_field = field_info["measure_fields"][0]["name"] if field_info["measure_fields"] else "Sales"
    
    from datetime import datetime
    current_year = datetime.now().year
    
    # 尝试用 SET 过滤器筛选年份
    query = {
        "fields": [
            {"fieldCaption": date_field, "function": "MONTH"},
            {"fieldCaption": measure_field, "function": "SUM"}
        ],
        "filters": [
            {
                "filterType": "SET",
                "field": {
                    "fieldCaption": date_field
                },
                "values": [str(current_year)],  # 尝试用年份值
                "exclude": False
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
        logger.info(f"数据:\n{json.dumps(result.get('data', [])[:5], indent=2, ensure_ascii=False)}")
        return True, result
    except Exception as e:
        logger.error(f"❌ 查询失败: {e}")
        return False, str(e)


def test_relative_date_with_fieldname(client, api_key, site, datasource_luid, field_info):
    """
    测试 K: 使用 fieldName 而不是 fieldCaption
    
    思路：也许 filter 中可以用 fieldName 来引用 fields 中定义的计算字段
    """
    logger.info("=" * 60)
    logger.info("测试 K: 使用 fieldName 引用计算字段")
    logger.info("=" * 60)
    
    if not field_info["string_fields"]:
        logger.warning("没有找到字符串字段，跳过测试")
        return False, "No string fields"
    
    string_field = field_info["string_fields"][0]["name"]
    measure_field = field_info["measure_fields"][0]["name"] if field_info["measure_fields"] else "Sales"
    
    # 尝试用 fieldName 引用
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
                    "fieldName": "ParsedDate"  # 尝试用 fieldName
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
        logger.info(f"✅ 查询成功！返回 {len(result.get('data', []))} 行数据")
        logger.info(f"数据:\n{json.dumps(result.get('data', [])[:5], indent=2, ensure_ascii=False)}")
        return True, result
    except Exception as e:
        logger.error(f"❌ 查询失败: {e}")
        return False, str(e)


def test_relative_date_simple_field_ref(client, api_key, site, datasource_luid, field_info):
    """
    测试 L: 最简单的字段引用方式
    
    思路：也许 filter.field 可以直接是字符串，而不是对象？
    或者用最简单的方式引用
    """
    logger.info("=" * 60)
    logger.info("测试 L: 简单字段引用（不带 calculation 关键字）")
    logger.info("=" * 60)
    
    if not field_info["string_fields"]:
        logger.warning("没有找到字符串字段，跳过测试")
        return False, "No string fields"
    
    string_field = field_info["string_fields"][0]["name"]
    measure_field = field_info["measure_fields"][0]["name"] if field_info["measure_fields"] else "Sales"
    
    # 尝试：在 filter 中只用字段名，不用 calculation
    # 但在 fields 中定义计算字段
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
                "field": "ParsedDate",  # 直接用字符串？
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
        logger.info(f"数据:\n{json.dumps(result.get('data', [])[:5], indent=2, ensure_ascii=False)}")
        return True, result
    except Exception as e:
        logger.error(f"❌ 查询失败: {e}")
        return False, str(e)


def test_raw_field_with_dateparse_filter(client, api_key, site, datasource_luid, field_info):
    """
    测试 M: fields 用原始字段名，filter 中用 DATEPARSE + 相对日期
    
    你的建议：fields 只用原始字段的 fieldCaption，
    filter 中用 fieldCaption 指向原始字段，然后用 DATEPARSE 转换
    """
    logger.info("=" * 60)
    logger.info("测试 M: fields 用原始字段名 + filter 用 DATEPARSE 相对日期")
    logger.info("=" * 60)
    
    if not field_info["string_fields"]:
        logger.warning("没有找到字符串字段，跳过测试")
        return False, "No string fields"
    
    string_field = field_info["string_fields"][0]["name"]
    measure_field = field_info["measure_fields"][0]["name"] if field_info["measure_fields"] else "Sales"
    
    # fields 用原始字段名，filter 中用 fieldCaption 指向原始字段
    query = {
        "fields": [
            {"fieldCaption": string_field},  # 原始字符串字段
            {"fieldCaption": measure_field, "function": "SUM"}
        ],
        "filters": [
            {
                "filterType": "DATE",
                "field": {
                    "fieldCaption": string_field  # 用原始字段名
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
        logger.info(f"✅ 查询成功！返回 {len(result.get('data', []))} 行数据")
        logger.info(f"数据:\n{json.dumps(result.get('data', [])[:5], indent=2, ensure_ascii=False)}")
        return True, result
    except Exception as e:
        logger.error(f"❌ 查询失败: {e}")
        return False, str(e)


def test_native_date_with_relative_filter(client, api_key, site, datasource_luid, field_info):
    """
    测试 C: 原生日期字段 + 相对日期过滤器（对照组）
    
    确认原生日期字段可以使用相对日期过滤器
    """
    logger.info("=" * 60)
    logger.info("测试 C: 原生日期字段 + 相对日期过滤器（对照组）")
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
                "field": {"fieldCaption": date_field},  # DimensionFilterField
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


def main():
    """运行所有测试"""
    logger.info("开始日期过滤器测试 v2...")
    
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
        
        # 测试 C: 原生日期字段 + 相对日期过滤器（对照组）
        all_results['test_c_native_relative'] = test_native_date_with_relative_filter(
            client, api_key, site, datasource_luid, field_info
        )
        
        # 测试 D: DATEPARSE + 相对日期过滤器（通过字段名引用）- 你的建议
        all_results['test_d_dateparse_by_fieldname'] = test_dateparse_with_relative_filter_by_fieldname(
            client, api_key, site, datasource_luid, field_info
        )
        
        # 测试 A: DATEPARSE + 相对日期过滤器（在 filter 中写 calculation）
        all_results['test_a_dateparse_relative'] = test_dateparse_with_relative_date_filter_fixed(
            client, api_key, site, datasource_luid, field_info
        )
        
        # 测试 B: DATEPARSE + 绝对日期过滤器
        all_results['test_b_dateparse_quantitative'] = test_dateparse_with_quantitative_date_filter(
            client, api_key, site, datasource_luid, field_info
        )
        
        # 测试 E: DATEPARSE + 相对日期过滤器（通过 calculation 引用字段名）
        all_results['test_e_calculation_ref'] = test_dateparse_with_relative_filter_by_calculation_ref(
            client, api_key, site, datasource_luid, field_info
        )
        
        # 测试 F: CONDITION 过滤器 + DATEPARSE
        all_results['test_f_condition_filter'] = test_condition_filter_with_dateparse(
            client, api_key, site, datasource_luid, field_info
        )
        
        # 测试 G: QUANTITATIVE_DATE + DATE() 函数包装
        all_results['test_g_date_function'] = test_quantitative_date_with_date_function(
            client, api_key, site, datasource_luid, field_info
        )
        
        # 测试 H: 不定义计算字段，直接在 filter 中用 DATE(DATEPARSE(...))
        all_results['test_h_no_fields_def'] = test_relative_date_filter_without_fields_definition(
            client, api_key, site, datasource_luid, field_info
        )
        
        # 测试 I: 用 QUANTITATIVE_DATE 模拟相对日期过滤器
        all_results['test_i_quantitative_simulate'] = test_quantitative_date_simulating_relative(
            client, api_key, site, datasource_luid, field_info
        )
        
        # 测试 J: SET 过滤器 + YEAR() 计算
        all_results['test_j_set_year'] = test_set_filter_with_year_calculation(
            client, api_key, site, datasource_luid, field_info
        )
        
        # 测试 K: 使用 fieldName 引用计算字段
        all_results['test_k_fieldname'] = test_relative_date_with_fieldname(
            client, api_key, site, datasource_luid, field_info
        )
        
        # 测试 L: 简单字段引用
        all_results['test_l_simple_ref'] = test_relative_date_simple_field_ref(
            client, api_key, site, datasource_luid, field_info
        )
        
        # 测试 M: fields 用原始字段名 + filter 用 DATEPARSE 相对日期
        all_results['test_m_raw_field_dateparse'] = test_raw_field_with_dateparse_filter(
            client, api_key, site, datasource_luid, field_info
        )
    
    # 输出总结
    logger.info("\n" + "=" * 60)
    logger.info("测试总结")
    logger.info("=" * 60)
    
    print("\n测试结果总结：")
    print("-" * 50)
    
    test_names = {
        'test_c_native_relative': '原生日期 + 相对日期过滤器（对照组）',
        'test_d_dateparse_by_fieldname': 'DATEPARSE + 相对日期过滤器（fieldCaption引用）',
        'test_e_calculation_ref': 'DATEPARSE + 相对日期过滤器（calculation: [ParsedDate]）',
        'test_a_dateparse_relative': 'DATEPARSE + 相对日期过滤器（filter中重写calculation）',
        'test_b_dateparse_quantitative': 'DATEPARSE + 绝对日期过滤器（QUANTITATIVE_DATE）',
        'test_f_condition_filter': 'CONDITION 过滤器 + DATEPARSE 计算',
        'test_g_date_function': 'DATE() 函数包装 + 相对日期过滤器',
        'test_h_no_fields_def': '不定义计算字段，直接在filter中用DATE(DATEPARSE(...))',
        'test_i_quantitative_simulate': 'QUANTITATIVE_DATE 模拟相对日期（今年）',
        'test_j_set_year': 'SET 过滤器 + 原生日期字段年份筛选',
        'test_k_fieldname': '使用 fieldName 引用计算字段',
        'test_l_simple_ref': '简单字段引用（field 直接是字符串）',
        'test_m_raw_field_dateparse': 'fields用原始字段名 + filter用fieldCaption相对日期'
    }
    
    for key, name in test_names.items():
        success, result = all_results.get(key, (False, "Not run"))
        status = '✅ 成功' if success else '❌ 失败'
        print(f"{name}: {status}")
        if not success and isinstance(result, str):
            print(f"   错误: {result[:]}...")


if __name__ == "__main__":
    main()
