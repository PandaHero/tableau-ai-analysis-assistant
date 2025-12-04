"""
Tableau 元数据服务

提供数据源元数据获取功能：
- 字段信息（名称、类型、角色）
- 数据模型（逻辑表、关系）
- 维度样例值和唯一值数量

统一使用 VizQLClient 进行 API 调用
"""
import json
import requests
import asyncio
import aiohttp
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from tableau_assistant.src.bi_platforms.tableau.vizql_client import VizQLClient, VizQLClientConfig

# SSL 配置
try:
    from tableau_assistant.cert_manager import get_ssl_config
    def _get_aiohttp_ssl():
        return get_ssl_config().get_aiohttp_ssl_param()
except ImportError:
    def _get_aiohttp_ssl():
        return False


def get_data_dictionary(
    api_key: str,
    domain: str,
    datasource_luid: str,
    site: Optional[str] = None,
    include_samples: bool = True
) -> Dict[str, Any]:
    """
    获取数据源元数据
    
    Args:
        api_key: Tableau 认证 token
        domain: Tableau 域名
        datasource_luid: 数据源 LUID
        site: Tableau 站点
        include_samples: 是否包含维度样例数据
    
    Returns:
        元数据字典，包含 fields, field_count, data_model 等
    """
    domain = (domain or "").rstrip("/")
    
    config = VizQLClientConfig(base_url=domain, timeout=30, max_retries=3)
    
    with VizQLClient(config=config) as client:
        # 获取字段元数据
        vizql_fields = []
        try:
            response = client.read_metadata(datasource_luid=datasource_luid, api_key=api_key, site=site)
            vizql_fields = response.get("data", [])
        except Exception as e:
            print(f"Warning: VizQL read_metadata failed: {e}")
        
        # 获取数据模型
        data_model_dict = None
        try:
            model_response = client.get_datasource_model(datasource_luid=datasource_luid, api_key=api_key, site=site)
            data_model_dict = {
                "logicalTables": model_response.get("logicalTables", []),
                "logicalTableRelationships": model_response.get("logicalTableRelationships", [])
            }
        except Exception as e:
            print(f"Warning: get_datasource_model failed: {e}")
        
        # 获取 GraphQL roles
        role_map = _fetch_graphql_roles(domain, datasource_luid, api_key, site)
        
        # 构建字段列表
        simplified_fields = []
        for vf in vizql_fields:
            field_name = vf.get("fieldCaption") or vf.get("fieldName", "")
            
            role = role_map.get(field_name) or role_map.get(vf.get("fieldName"))
            if not role:
                role = _infer_role(vf.get("defaultAggregation"), vf.get("dataType"))
            
            simplified_fields.append({
                "name": field_name,
                "fieldCaption": vf.get("fieldCaption", ""),
                "fieldName": vf.get("fieldName"),
                "role": role.upper() if role else "DIMENSION",
                "dataType": vf.get("dataType", "UNKNOWN"),
                "dataCategory": vf.get("dataCategory"),
                "aggregation": vf.get("defaultAggregation"),
                "logicalTableId": vf.get("logicalTableId"),
                "columnClass": vf.get("columnClass"),
                "formula": vf.get("formula"),
            })
        
        # 获取维度样例数据
        if include_samples:
            dimension_names = [f['name'] for f in simplified_fields if f.get('role', '').upper() == 'DIMENSION']
            measure_field = next((f['name'] for f in simplified_fields if f.get('role', '').upper() == 'MEASURE'), None)
            
            if dimension_names and measure_field:
                samples_dict = _fetch_dimension_samples(
                    client=client,
                    datasource_luid=datasource_luid,
                    dimension_names=dimension_names,
                    measure_field=measure_field,
                    api_key=api_key,
                    site=site
                )
                
                for field in simplified_fields:
                    if field.get('role', '').upper() == 'DIMENSION':
                        field_name = field['name']
                        if field_name in samples_dict:
                            dim_data = samples_dict[field_name]
                            if dim_data.get('sample_values'):
                                field['sample_values'] = dim_data['sample_values']
                            if dim_data.get('unique_count'):
                                field['unique_count'] = dim_data['unique_count']
        
        return {
            'datasource_luid': datasource_luid,
            'fields': simplified_fields,
            'field_count': len(simplified_fields),
            'field_names': [f['name'] for f in simplified_fields],
            'data_model': data_model_dict,
        }


async def get_data_dictionary_async(
    api_key: str,
    domain: str,
    datasource_luid: str,
    site: Optional[str] = None,
    include_samples: bool = True
) -> Dict[str, Any]:
    """
    异步获取数据源元数据
    
    使用 aiohttp 实现真正的异步并发，所有维度样例请求同时发起
    """
    domain = (domain or "").rstrip("/")
    
    config = VizQLClientConfig(base_url=domain, timeout=30, max_retries=3)
    
    with VizQLClient(config=config) as client:
        # 同步获取基础元数据（这些请求较少，不需要并发）
        vizql_fields = []
        try:
            response = client.read_metadata(datasource_luid=datasource_luid, api_key=api_key, site=site)
            vizql_fields = response.get("data", [])
        except Exception as e:
            print(f"Warning: VizQL read_metadata failed: {e}")
        
        data_model_dict = None
        try:
            model_response = client.get_datasource_model(datasource_luid=datasource_luid, api_key=api_key, site=site)
            data_model_dict = {
                "logicalTables": model_response.get("logicalTables", []),
                "logicalTableRelationships": model_response.get("logicalTableRelationships", [])
            }
        except Exception as e:
            print(f"Warning: get_datasource_model failed: {e}")
        
        role_map = _fetch_graphql_roles(domain, datasource_luid, api_key, site)
        
        # 构建字段列表
        simplified_fields = []
        for vf in vizql_fields:
            field_name = vf.get("fieldCaption") or vf.get("fieldName", "")
            role = role_map.get(field_name) or role_map.get(vf.get("fieldName"))
            if not role:
                role = _infer_role(vf.get("defaultAggregation"), vf.get("dataType"))
            
            simplified_fields.append({
                "name": field_name,
                "fieldCaption": vf.get("fieldCaption", ""),
                "fieldName": vf.get("fieldName"),
                "role": role.upper() if role else "DIMENSION",
                "dataType": vf.get("dataType", "UNKNOWN"),
                "dataCategory": vf.get("dataCategory"),
                "aggregation": vf.get("defaultAggregation"),
                "logicalTableId": vf.get("logicalTableId"),
                "columnClass": vf.get("columnClass"),
                "formula": vf.get("formula"),
            })
        
        # 异步并发获取维度样例数据
        if include_samples:
            dimension_names = [f['name'] for f in simplified_fields if f.get('role', '').upper() == 'DIMENSION']
            measure_field = next((f['name'] for f in simplified_fields if f.get('role', '').upper() == 'MEASURE'), None)
            
            if dimension_names and measure_field:
                samples_dict = await _fetch_dimension_samples_async(
                    client=client,
                    datasource_luid=datasource_luid,
                    dimension_names=dimension_names,
                    measure_field=measure_field,
                    api_key=api_key,
                    site=site
                )
                
                for field in simplified_fields:
                    if field.get('role', '').upper() == 'DIMENSION':
                        field_name = field['name']
                        if field_name in samples_dict:
                            dim_data = samples_dict[field_name]
                            if dim_data.get('sample_values'):
                                field['sample_values'] = dim_data['sample_values']
                            if dim_data.get('unique_count'):
                                field['unique_count'] = dim_data['unique_count']
        
        return {
            'datasource_luid': datasource_luid,
            'fields': simplified_fields,
            'field_count': len(simplified_fields),
            'field_names': [f['name'] for f in simplified_fields],
            'data_model': data_model_dict,
        }


async def _fetch_dimension_samples_async(
    client: VizQLClient,
    datasource_luid: str,
    dimension_names: List[str],
    measure_field: str,
    api_key: str,
    site: Optional[str] = None,
    sample_size: int = 5,
    max_concurrent: int = 10
) -> Dict[str, Dict[str, Any]]:
    """
    异步并发获取所有维度的样例数据
    
    使用 VizQLClient 的异步方法，通过共享 aiohttp session 实现真正的并发
    使用 Semaphore 限制并发数，避免触发速率限制
    """
    if not dimension_names:
        return {}
    
    # 使用信号量限制并发数
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def fetch_one(session: aiohttp.ClientSession, dim: str) -> tuple:
        """获取单个维度的样例"""
        async with semaphore:  # 限制并发数
            query = {
                "fields": [
                    {"fieldCaption": dim},
                    {"fieldCaption": f"countd_{dim}", "calculation": f"{{FIXED : COUNTD([{dim}])}}"}
                ],
                "filters": [{
                    "filterType": "TOP",
                    "field": {"fieldCaption": dim},
                    "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
                    "howMany": sample_size,
                    "direction": "TOP"
                }]
            }
            
            result = {"sample_values": [], "unique_count": 0}
            try:
                # 使用 VizQLClient 的异步方法
                data = await client.query_datasource_async(
                    datasource_luid=datasource_luid,
                    query=query,
                    api_key=api_key,
                    site=site,
                    session=session
                )
                
                for row in data.get("data", []):
                    if isinstance(row, dict):
                        value = row.get(dim)
                        if value is not None:
                            value_str = str(value).strip()
                            if value_str and value_str not in result["sample_values"]:
                                result["sample_values"].append(value_str)
                        if result["unique_count"] == 0:
                            countd = row.get(f"countd_{dim}")
                            if countd is not None:
                                try:
                                    result["unique_count"] = int(countd)
                                except (ValueError, TypeError):
                                    pass
            except Exception as e:
                print(f"    [ERROR] 获取 {dim} 样例失败: {e}")
            
            return (dim, result)
    
    # 使用单个 session 并发所有请求
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [fetch_one(session, dim) for dim in dimension_names]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 处理结果
    results = {}
    for item in results_list:
        if isinstance(item, Exception):
            continue
        dim, result = item
        results[dim] = result
    
    return results


def _fetch_graphql_roles(
    domain: str,
    datasource_luid: str,
    api_key: str,
    site: Optional[str] = None
) -> Dict[str, str]:
    """从 GraphQL API 获取字段 role"""
    query = f'''
    query fieldRoles {{
      publishedDatasources(filter: {{luid: "{datasource_luid}"}}) {{
        fields {{
          name
          ... on ColumnField {{ role }}
          ... on CalculatedField {{ role }}
          ... on BinField {{ role }}
          ... on GroupField {{ role }}
        }}
      }}
    }}
    '''
    
    try:
        full_url = f"{domain}/api/metadata/graphql"
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-Tableau-Auth': api_key
        }
        if site:
            headers['X-Tableau-Site'] = site
        
        response = requests.post(full_url, headers=headers, json={"query": query, "variables": {}})
        
        if response.status_code == 200:
            data = response.json()
            if 'errors' not in data:
                ds_list = data.get('data', {}).get('publishedDatasources', [])
                if ds_list:
                    return {
                        f.get('name', ''): (f.get('role', 'dimension') or 'dimension').lower()
                        for f in ds_list[0].get('fields', [])
                        if f.get('name')
                    }
    except Exception as e:
        print(f"Warning: GraphQL roles fetch failed: {e}")
    
    return {}


def _infer_role(default_aggregation: Optional[str], data_type: Optional[str] = None) -> str:
    """推断字段 role"""
    if not default_aggregation or not default_aggregation.strip():
        return "dimension"
    
    agg = default_aggregation.upper().strip()
    dtype = (data_type or "").upper()
    
    if dtype in {"REAL", "INTEGER"} and agg in {"SUM", "AVG", "MIN", "MAX", "MEDIAN"}:
        return "measure"
    if dtype in {"DATE", "DATETIME", "STRING"}:
        return "dimension"
    if dtype in {"REAL", "INTEGER"}:
        return "measure"
    
    return "dimension"


def _fetch_dimension_samples(
    client: VizQLClient,
    datasource_luid: str,
    dimension_names: List[str],
    measure_field: str,
    api_key: str,
    site: Optional[str] = None,
    sample_size: int = 5,
    max_workers: int = 5
) -> Dict[str, Dict[str, Any]]:
    """
    获取维度的样例数据和唯一值数量
    
    使用并发请求，每个维度单独查询，确保每个维度只返回 sample_size 行数据
    """
    if not dimension_names:
        return {}
    
    results = {}
    
    def fetch_one(dim: str) -> tuple:
        """获取单个维度的样例"""
        result = _fetch_single_dimension_samples(
            client=client,
            datasource_luid=datasource_luid,
            dimension_name=dim,
            measure_field=measure_field,
            api_key=api_key,
            site=site,
            sample_size=sample_size
        )
        return (dim, result)
    
    # 使用线程池并发执行
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_one, dim): dim for dim in dimension_names}
        
        for future in as_completed(futures):
            try:
                dim, result = future.result()
                results[dim] = result
            except Exception as e:
                dim = futures[future]
                print(f"    [ERROR] 获取 {dim} 样例失败: {e}")
                results[dim] = {"sample_values": [], "unique_count": 0}
    
    return results


def _fetch_single_dimension_samples(
    client: VizQLClient,
    datasource_luid: str,
    dimension_name: str,
    measure_field: str,
    api_key: str,
    site: Optional[str] = None,
    sample_size: int = 5
) -> Dict[str, Any]:
    """获取单个维度的样例数据和 COUNTD"""
    result = {"sample_values": [], "unique_count": 0}
    
    try:
        # 构建查询：维度 + COUNTD 计算字段
        query = {
            "fields": [
                {"fieldCaption": dimension_name},
                {
                    "fieldCaption": f"countd_{dimension_name}",
                    "calculation": f"{{FIXED : COUNTD([{dimension_name}])}}"
                }
            ],
            "filters": [{
                "filterType": "TOP",
                "field": {"fieldCaption": dimension_name},
                "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"},
                "howMany": sample_size,
                "direction": "TOP"
            }]
        }
        
        response = client.query_datasource(
            datasource_luid=datasource_luid,
            query=query,
            api_key=api_key,
            site=site
        )
        
        # 处理结果
        for row in response.get("data", []):
            if isinstance(row, dict):
                # 样例值
                value = row.get(dimension_name)
                if value is not None:
                    value_str = str(value).strip()
                    if value_str and value_str not in result["sample_values"]:
                        result["sample_values"].append(value_str)
                
                # COUNTD（只取一次）
                if result["unique_count"] == 0:
                    countd = row.get(f"countd_{dimension_name}")
                    if countd is not None:
                        try:
                            result["unique_count"] = int(countd)
                        except (ValueError, TypeError):
                            pass
    
    except Exception as e:
        print(f"    [ERROR] 获取 {dimension_name} 样例失败: {e}")
    
    return result


def get_datasource_luid_by_name(
    api_key: str,
    domain: str,
    datasource_name: str,
    site: Optional[str] = None
) -> Optional[str]:
    """通过名称查找数据源 LUID"""
    if not datasource_name or not datasource_name.strip():
        return None

    domain = (domain or "").rstrip("/")
    name = datasource_name.strip()
    
    # 提取项目名（如果存在）
    project = None
    if " | 项目 : " in name:
        parts = name.split(" | 项目 : ", 1)
        name = parts[0].strip()
        project = parts[1].strip() if len(parts) > 1 else None

    def graphql_query(query: str, variables: Dict[str, Any]) -> Optional[Dict]:
        try:
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-Tableau-Auth': api_key
            }
            if site:
                headers['X-Tableau-Site'] = site
            
            response = requests.post(
                f"{domain}/api/metadata/graphql",
                headers=headers,
                json={"query": query, "variables": variables}
            )
            if response.status_code == 200:
                data = response.json()
                if 'errors' not in data:
                    return data
        except Exception:
            pass
        return None

    # 精确匹配 + 项目
    if project:
        q = """
        query($name:String!, $project:String!) {
          publishedDatasources(filter:{ name:$name, projectName:$project }) {
            luid name projectName
          }
        }
        """
        data = graphql_query(q, {"name": name, "project": project})
        if data:
            for ds in data.get("data", {}).get("publishedDatasources", []):
                if ds.get("name") == name and ds.get("projectName") == project:
                    return ds.get("luid")

    # 精确匹配
    q = """
    query($name:String!) {
      publishedDatasources(filter:{ name:$name }) {
        luid name
      }
    }
    """
    data = graphql_query(q, {"name": name})
    if data:
        items = data.get("data", {}).get("publishedDatasources", [])
        for ds in items:
            if ds.get("name") == name:
                return ds.get("luid")
        if items:
            return items[0].get("luid")

    # 模糊匹配
    q = """
    query($kw:String!) {
      publishedDatasources(filter:{ name:{ contains:$kw } }) {
        luid name
      }
    }
    """
    data = graphql_query(q, {"kw": name})
    if data:
        items = data.get("data", {}).get("publishedDatasources", [])
        if items:
            return items[0].get("luid")

    return None
