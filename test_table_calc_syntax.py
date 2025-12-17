"""
表计算语法测试脚本

测试目的：比较 Tableau 公式语法和 VizQL 结构化语法在表计算中的行为

测试场景：
1. 使用 CalculatedField + Tableau 公式语法（RUNNING_SUM）
2. 使用 TableCalcField + VizQL 结构化语法（TableCalcSpecification）
3. 测试 Tableau 公式中是否能指定分区/寻址参数

使用方法：
    python test_table_calc_syntax.py
"""
import os
import json
import logging
from dotenv import load_dotenv

# 加载环境变量
load_dotenv("tableau_assistant/.env")

from tableau_assistant.src.bi_platforms.tableau.vizql_client import VizQLClient, VizQLClientConfig
from tableau_assistant.src.bi_platforms.tableau.auth import get_tableau_auth

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_client_and_auth():
    """获取 VizQL 客户端和认证信息"""
    # 使用项目的认证方式获取 token
    auth_ctx = get_tableau_auth()
    
    domain = auth_ctx.domain
    site = auth_ctx.site
    api_key = auth_ctx.api_key
    datasource_luid = os.getenv("DATASOURCE_LUID")
    
    if not datasource_luid:
        raise ValueError("请确保设置了 DATASOURCE_LUID 环境变量")
    
    # 创建客户端
    config = VizQLClientConfig(
        base_url=domain,
        verify_ssl=os.getenv("VIZQL_VERIFY_SSL", "true").lower() == "true",
        ca_bundle=os.getenv("VIZQL_CA_BUNDLE"),
        timeout=30,
        max_retries=3
    )
    client = VizQLClient(config=config)
    
    return client, api_key, site, datasource_luid


def get_field_names(client, api_key, site, datasource_luid):
    """从 Tableau API 获取真实的字段名"""
    logger.info("正在获取数据源元数据...")
    
    metadata = client.read_metadata(
        datasource_luid=datasource_luid,
        api_key=api_key,
        site=site
    )
    
    fields = metadata.get("data", [])
    
    # 打印原始数据结构以便调试
    if fields:
        logger.info(f"原始字段示例: {json.dumps(fields[0], indent=2, ensure_ascii=False)}")
    else:
        logger.warning("没有找到字段数据！")
        logger.info(f"元数据响应键: {metadata.keys()}")
        if "data" not in metadata:
            logger.info(f"完整响应: {json.dumps(metadata, indent=2, ensure_ascii=False)[:1000]}")
    
    # 分类字段
    # VizQL API 使用 defaultAggregation 和 dataType 来区分维度和度量
    # - 度量: 有 defaultAggregation (SUM, AVG, COUNT 等) 且 dataType 是数值类型
    # - 维度: 没有 defaultAggregation 或 dataType 是 STRING/DATE 等
    dimensions = []
    measures = []
    date_fields = []
    
    for field in fields:
        name = field.get("fieldCaption") or field.get("fieldName") or ""
        data_type = (field.get("dataType") or "").upper()
        default_agg = field.get("defaultAggregation", "")
        column_class = field.get("columnClass", "")
        
        if not name:
            continue
        
        # 判断是否为度量：数值类型且有默认聚合
        is_measure = data_type in ("INTEGER", "REAL", "FLOAT", "NUMBER") or \
                     (default_agg in ("SUM", "AVG", "MIN", "MAX") and data_type not in ("STRING", "DATE", "DATETIME"))
        
        if is_measure:
            measures.append(name)
        else:
            dimensions.append(name)
            if data_type in ("DATE", "DATETIME"):
                date_fields.append(name)
    
    logger.info(f"找到 {len(dimensions)} 个维度, {len(measures)} 个度量, {len(date_fields)} 个日期字段")
    logger.info(f"维度示例: {dimensions[:5]}")
    logger.info(f"度量示例: {measures[:5]}")
    logger.info(f"日期字段: {date_fields[:5]}")
    
    return {
        "dimensions": dimensions,
        "measures": measures,
        "date_fields": date_fields,
        "all_fields": fields
    }


def test_vizql_structured_syntax(client, api_key, site, datasource_luid, field_info):
    """
    测试 1: VizQL 结构化语法（TableCalcField + TableCalcSpecification）
    
    这是当前系统使用的方式
    """
    logger.info("=" * 60)
    logger.info("测试 1: VizQL 结构化语法 (TableCalcField)")
    logger.info("=" * 60)
    
    # 使用真实字段名
    date_field = field_info["date_fields"][0] if field_info["date_fields"] else field_info["dimensions"][0]
    measure_field = field_info["measures"][0] if field_info["measures"] else "Sales"
    
    logger.info(f"使用字段: 日期={date_field}, 度量={measure_field}")
    
    query = {
        "fields": [
            # 维度：月份
            {
                "fieldCaption": date_field,
                "function": "MONTH"
            },
            # 度量
            {
                "fieldCaption": measure_field,
                "function": "SUM"
            },
            # 表计算：累计（使用结构化语法）
            {
                "fieldCaption": f"累计{measure_field}",
                "function": "SUM",
                "tableCalculation": {
                    "tableCalcType": "RUNNING_TOTAL",
                    "dimensions": [
                        {"fieldCaption": date_field, "function": "MONTH"}
                    ],
                    "aggregation": "SUM"
                }
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
        logger.info(f"查询成功！返回 {len(result.get('data', []))} 行数据")
        logger.info(f"前 5 行数据:\n{json.dumps(result.get('data', [])[:5], indent=2, ensure_ascii=False)}")
        return True, result
    except Exception as e:
        logger.error(f"查询失败: {e}")
        return False, str(e)


def test_tableau_formula_basic(client, api_key, site, datasource_luid, field_info):
    """
    测试 2: Tableau 公式语法（CalculatedField + RUNNING_SUM）
    
    不指定分区/寻址，看默认行为
    """
    logger.info("=" * 60)
    logger.info("测试 2: Tableau 公式语法 - 基础 (CalculatedField + RUNNING_SUM)")
    logger.info("=" * 60)
    
    # 使用真实字段名
    date_field = field_info["date_fields"][0] if field_info["date_fields"] else field_info["dimensions"][0]
    measure_field = field_info["measures"][0] if field_info["measures"] else "Sales"
    
    logger.info(f"使用字段: 日期={date_field}, 度量={measure_field}")
    
    query = {
        "fields": [
            # 维度：月份
            {
                "fieldCaption": date_field,
                "function": "MONTH"
            },
            # 度量
            {
                "fieldCaption": measure_field,
                "function": "SUM"
            },
            # 表计算：使用 Tableau 公式语法
            {
                "fieldCaption": f"累计{measure_field}_公式",
                "calculation": f"RUNNING_SUM(SUM([{measure_field}]))"
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
        logger.info(f"查询成功！返回 {len(result.get('data', []))} 行数据")
        logger.info(f"前 5 行数据:\n{json.dumps(result.get('data', [])[:5], indent=2, ensure_ascii=False)}")
        return True, result
    except Exception as e:
        logger.error(f"查询失败: {e}")
        return False, str(e)


def test_tableau_formula_with_partition(client, api_key, site, datasource_luid, field_info):
    """
    测试 3: Tableau 公式语法 + 尝试指定分区/寻址
    
    尝试在公式中使用 {PARTITION} 或 {ORDERBY} 语法（如果支持的话）
    """
    logger.info("=" * 60)
    logger.info("测试 3: Tableau 公式语法 - 尝试 PARTITION/ORDERBY")
    logger.info("=" * 60)
    
    # 使用真实字段名
    date_field = field_info["date_fields"][0] if field_info["date_fields"] else field_info["dimensions"][0]
    measure_field = field_info["measures"][0] if field_info["measures"] else "Sales"
    dim_field = field_info["dimensions"][0] if field_info["dimensions"] else "Category"
    
    logger.info(f"使用字段: 日期={date_field}, 度量={measure_field}, 维度={dim_field}")
    
    # 尝试不同的语法变体
    test_formulas = [
        # 变体 1: 尝试 {ORDERBY} 语法
        f"RUNNING_SUM(SUM([{measure_field}]) {{ORDERBY [{date_field}]}})",
        # 变体 2: 尝试 {PARTITION} 语法
        f"RUNNING_SUM(SUM([{measure_field}]) {{PARTITION [{dim_field}]}})",
        # 变体 3: 尝试 ALONG 语法
        f"RUNNING_SUM(SUM([{measure_field}]) ALONG [{date_field}])",
        # 变体 4: 尝试第二个参数
        f"RUNNING_SUM(SUM([{measure_field}]), [{date_field}])",
    ]
    
    results = []
    for i, formula in enumerate(test_formulas, 1):
        logger.info(f"\n--- 变体 {i}: {formula} ---")
        
        query = {
            "fields": [
                {"fieldCaption": date_field, "function": "MONTH"},
                {"fieldCaption": measure_field, "function": "SUM"},
                {
                    "fieldCaption": f"累计_变体{i}",
                    "calculation": formula
                }
            ]
        }
        
        try:
            result = client.query_datasource(
                datasource_luid=datasource_luid,
                query=query,
                api_key=api_key,
                site=site
            )
            logger.info(f"✅ 变体 {i} 成功！")
            results.append((formula, True, result))
        except Exception as e:
            logger.error(f"❌ 变体 {i} 失败: {e}")
            results.append((formula, False, str(e)))
    
    return results


def test_tableau_formula_with_tablecalc_spec(client, api_key, site, datasource_luid, field_info):
    """
    测试 4: CalculatedField + tableCalculation 组合
    
    尝试在 CalculatedField 中同时使用 calculation 和 tableCalculation
    """
    logger.info("=" * 60)
    logger.info("测试 4: CalculatedField + tableCalculation 组合")
    logger.info("=" * 60)
    
    # 使用真实字段名
    date_field = field_info["date_fields"][0] if field_info["date_fields"] else field_info["dimensions"][0]
    measure_field = field_info["measures"][0] if field_info["measures"] else "Sales"
    
    logger.info(f"使用字段: 日期={date_field}, 度量={measure_field}")
    
    query = {
        "fields": [
            {"fieldCaption": date_field, "function": "MONTH"},
            {"fieldCaption": measure_field, "function": "SUM"},
            # 尝试组合使用
            {
                "fieldCaption": f"累计{measure_field}_组合",
                "calculation": f"SUM([{measure_field}])",  # 基础计算
                "tableCalculation": {  # 表计算规格
                    "tableCalcType": "RUNNING_TOTAL",
                    "dimensions": [
                        {"fieldCaption": date_field, "function": "MONTH"}
                    ],
                    "aggregation": "SUM"
                }
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
        logger.info(f"查询成功！返回 {len(result.get('data', []))} 行数据")
        logger.info(f"前 5 行数据:\n{json.dumps(result.get('data', [])[:5], indent=2, ensure_ascii=False)}")
        return True, result
    except Exception as e:
        logger.error(f"查询失败: {e}")
        return False, str(e)


def test_rank_comparison(client, api_key, site, datasource_luid, field_info):
    """
    测试 5: RANK 函数对比
    
    比较 Tableau 公式语法和 VizQL 结构化语法的 RANK 实现
    """
    logger.info("=" * 60)
    logger.info("测试 5: RANK 函数对比")
    logger.info("=" * 60)
    
    # 使用真实字段名
    dim_field = field_info["dimensions"][0] if field_info["dimensions"] else "Category"
    measure_field = field_info["measures"][0] if field_info["measures"] else "Sales"
    
    logger.info(f"使用字段: 维度={dim_field}, 度量={measure_field}")
    
    # 5a: VizQL 结构化语法
    query_structured = {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": f"{measure_field}排名_结构化",
                "function": "SUM",
                "tableCalculation": {
                    "tableCalcType": "RANK",
                    "dimensions": [{"fieldCaption": dim_field}],
                    "rankType": "COMPETITION",
                    "direction": "DESC"
                }
            }
        ]
    }
    
    # 5b: Tableau 公式语法
    query_formula = {
        "fields": [
            {"fieldCaption": dim_field},
            {"fieldCaption": measure_field, "function": "SUM"},
            {
                "fieldCaption": f"{measure_field}排名_公式",
                "calculation": f"RANK(SUM([{measure_field}]))"
            }
        ]
    }
    
    results = {}
    
    logger.info("\n--- 5a: VizQL 结构化语法 ---")
    logger.info(f"查询:\n{json.dumps(query_structured, indent=2, ensure_ascii=False)}")
    try:
        result = client.query_datasource(
            datasource_luid=datasource_luid,
            query=query_structured,
            api_key=api_key,
            site=site
        )
        logger.info(f"✅ 结构化语法成功！")
        logger.info(f"数据:\n{json.dumps(result.get('data', []), indent=2, ensure_ascii=False)}")
        results['structured'] = (True, result)
    except Exception as e:
        logger.error(f"❌ 结构化语法失败: {e}")
        results['structured'] = (False, str(e))
    
    logger.info("\n--- 5b: Tableau 公式语法 ---")
    logger.info(f"查询:\n{json.dumps(query_formula, indent=2, ensure_ascii=False)}")
    try:
        result = client.query_datasource(
            datasource_luid=datasource_luid,
            query=query_formula,
            api_key=api_key,
            site=site
        )
        logger.info(f"✅ 公式语法成功！")
        logger.info(f"数据:\n{json.dumps(result.get('data', []), indent=2, ensure_ascii=False)}")
        results['formula'] = (True, result)
    except Exception as e:
        logger.error(f"❌ 公式语法失败: {e}")
        results['formula'] = (False, str(e))
    
    return results


def main():
    """运行所有测试"""
    logger.info("开始表计算语法测试...")
    
    try:
        client, api_key, site, datasource_luid = get_client_and_auth()
        logger.info(f"连接到 Tableau: {os.getenv('TABLEAU_DOMAIN')}")
        logger.info(f"数据源 LUID: {datasource_luid}")
    except Exception as e:
        logger.error(f"初始化失败: {e}")
        return
    
    # 运行测试
    all_results = {}
    
    with client:
        # 首先获取真实字段名
        field_info = get_field_names(client, api_key, site, datasource_luid)
        
        if not field_info["measures"]:
            logger.error("数据源中没有找到度量字段！")
            return
        
        # 测试 1: VizQL 结构化语法
        all_results['test1_vizql_structured'] = test_vizql_structured_syntax(
            client, api_key, site, datasource_luid, field_info
        )
        
        # 测试 2: Tableau 公式语法（基础）
        all_results['test2_tableau_basic'] = test_tableau_formula_basic(
            client, api_key, site, datasource_luid, field_info
        )
        
        # 测试 3: Tableau 公式语法（尝试分区/寻址）
        all_results['test3_tableau_partition'] = test_tableau_formula_with_partition(
            client, api_key, site, datasource_luid, field_info
        )
        
        # 测试 4: CalculatedField + tableCalculation 组合
        all_results['test4_combined'] = test_tableau_formula_with_tablecalc_spec(
            client, api_key, site, datasource_luid, field_info
        )
        
        # 测试 5: RANK 对比
        all_results['test5_rank'] = test_rank_comparison(
            client, api_key, site, datasource_luid, field_info
        )
    
    # 输出总结
    logger.info("\n" + "=" * 60)
    logger.info("测试总结")
    logger.info("=" * 60)
    
    print("\n测试结果总结：")
    print("-" * 40)
    
    # 测试 1
    success, _ = all_results['test1_vizql_structured']
    print(f"测试 1 (VizQL 结构化): {'✅ 成功' if success else '❌ 失败'}")
    
    # 测试 2
    success, _ = all_results['test2_tableau_basic']
    print(f"测试 2 (Tableau 公式基础): {'✅ 成功' if success else '❌ 失败'}")
    
    # 测试 3
    print("测试 3 (Tableau 公式 + 分区/寻址):")
    for formula, success, _ in all_results['test3_tableau_partition']:
        status = '✅' if success else '❌'
        print(f"  {status} {formula[:50]}...")
    
    # 测试 4
    success, _ = all_results['test4_combined']
    print(f"测试 4 (组合语法): {'✅ 成功' if success else '❌ 失败'}")
    
    # 测试 5
    print("测试 5 (RANK 对比):")
    for name, (success, _) in all_results['test5_rank'].items():
        print(f"  {'✅' if success else '❌'} {name}")


if __name__ == "__main__":
    main()
