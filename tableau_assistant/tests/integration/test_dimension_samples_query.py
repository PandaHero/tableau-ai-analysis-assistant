"""测试维度样例值和 COUNTD 的查询结构"""
import os
import asyncio
import aiohttp
from dotenv import load_dotenv

load_dotenv()


async def test_dimension_samples_query():
    """测试使用 FIXED LOD 表达式同时获取样例值和 COUNTD"""
    
    # 从环境变量获取配置
    domain = os.getenv("TABLEAU_DOMAIN", "").rstrip("/")
    datasource_luid = os.getenv("DATASOURCE_LUID")
    site = os.getenv("TABLEAU_SITE")
    
    # 获取 API Key
    from tableau_assistant.src.bi_platforms.tableau.auth import _get_tableau_context_from_env
    ctx = _get_tableau_context_from_env()
    api_key = ctx["api_key"]
    
    print(f"Domain: {domain}")
    print(f"Datasource LUID: {datasource_luid}")
    print(f"Site: {site}")
    print(f"API Key: {api_key[:20]}...")
    
    # 先获取元数据，找到维度和度量字段
    from tableau_assistant.src.bi_platforms.tableau.vizql_client import VizQLClient, VizQLClientConfig
    
    config = VizQLClientConfig(base_url=domain)
    with VizQLClient(config=config) as client:
        metadata = client.read_metadata(datasource_luid=datasource_luid, api_key=api_key, site=site)
    
    fields = metadata.get("data", [])
    
    # 找到维度和度量字段
    dimension_names = []
    measure_field = None
    
    for f in fields:
        field_name = f.get("fieldCaption") or f.get("fieldName", "")
        default_agg = f.get("defaultAggregation", "")
        data_type = f.get("dataType", "")
        
        if not field_name:
            continue
        
        # 判断是否是度量：有聚合函数且数据类型是数值
        is_measure = (
            default_agg and 
            default_agg.upper() in ("SUM", "AVG", "COUNT", "COUNTD", "MIN", "MAX", "MEDIAN") and
            data_type in ("REAL", "INTEGER")
        )
        
        if is_measure:
            if not measure_field:
                measure_field = field_name
                print(f"度量字段: {measure_field} (聚合: {default_agg}, 类型: {data_type})")
        else:
            # 维度：非度量字段
            if len(dimension_names) < 3:  # 只取前3个维度测试
                dimension_names.append(field_name)
                print(f"维度字段: {field_name} (聚合: {default_agg}, 类型: {data_type})")
    
    print(f"维度字段: {dimension_names}")
    
    if not dimension_names or not measure_field:
        print("错误：找不到维度或度量字段")
        return
    
    # 构建查询
    sample_size = 5
    fields_query = []
    
    # 添加维度字段
    for dim in dimension_names:
        fields_query.append({"fieldCaption": dim})
    
    # 添加 COUNTD 计算字段（使用 FIXED LOD）
    for dim in dimension_names:
        fields_query.append({
            "fieldCaption": f"countd_{dim}",
            "calculation": f"{{FIXED : COUNTD([{dim}])}}"
        })
    
    query = {
        "fields": fields_query,
        "filters": [
            {
                "filterType": "TOP",
                "field": {"fieldCaption": dimension_names[0]},
                "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
                "howMany": sample_size,
                "direction": "TOP"
            }
        ]
    }
    
    print("\n=== 查询结构 ===")
    import json
    print(json.dumps(query, indent=2, ensure_ascii=False))
    
    # 发送请求
    full_url = f"{domain}/api/v1/vizql-data-service/query-datasource"
    headers = {
        'X-Tableau-Auth': api_key,
        'Content-Type': 'application/json'
    }
    if site:
        headers['X-Tableau-Site'] = site
    
    payload = {
        "datasource": {"datasourceLuid": datasource_luid},
        "query": query
    }
    
    print("\n=== 发送请求 ===")
    
    # 使用 SSL 配置
    try:
        from tableau_assistant.cert_manager import get_ssl_config
        ssl_param = get_ssl_config().get_aiohttp_ssl_param()
    except ImportError:
        from tableau_assistant.src.utils.ssl_config import get_aiohttp_ssl
        ssl_param = get_aiohttp_ssl()
    
    async with aiohttp.ClientSession() as session:
        async with session.post(full_url, json=payload, headers=headers, ssl=ssl_param) as response:
            print(f"状态码: {response.status}")
            
            if response.status == 200:
                result = await response.json()
                print("\n=== 响应数据 ===")
                print(json.dumps(result, indent=2, ensure_ascii=False))
                
                # 解析结果
                data = result.get("data", [])
                print(f"\n返回 {len(data)} 行数据")
                
                # 提取样例值和 COUNTD
                dimension_results = {dim: {"sample_values": [], "unique_count": 0} for dim in dimension_names}
                
                for row in data:
                    if isinstance(row, dict):
                        for dim in dimension_names:
                            # 样例值
                            value = row.get(dim)
                            if value is not None:
                                value_str = str(value).strip()
                                if value_str and value_str not in dimension_results[dim]["sample_values"]:
                                    dimension_results[dim]["sample_values"].append(value_str)
                            
                            # COUNTD
                            if dimension_results[dim]["unique_count"] == 0:
                                countd_value = row.get(f"countd_{dim}")
                                if countd_value is not None:
                                    try:
                                        dimension_results[dim]["unique_count"] = int(countd_value)
                                    except (ValueError, TypeError):
                                        pass
                
                print("\n=== 解析结果 ===")
                for dim, result in dimension_results.items():
                    print(f"{dim}:")
                    print(f"  样例值: {result['sample_values']}")
                    print(f"  唯一值数量: {result['unique_count']}")
            else:
                error_text = await response.text()
                print(f"错误: {error_text}")


if __name__ == "__main__":
    asyncio.run(test_dimension_samples_query())
