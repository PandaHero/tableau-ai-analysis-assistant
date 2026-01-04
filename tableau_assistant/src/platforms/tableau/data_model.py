"""
Tableau 数据模型服务

提供数据源元数据获取功能：
- 字段信息（名称、类型、角色）
- 数据模型（逻辑表、关系）
- 维度样例值和唯一值数量

统一使用 VizQLClient 进行 API 调用
"""
import json
import logging
import requests
import asyncio
import aiohttp
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from tableau_assistant.src.platforms.tableau.vizql_client import VizQLClient, VizQLClientConfig
from tableau_assistant.src.infra.certs import get_certificate_config
from tableau_assistant.src.infra.storage.data_model import (
    DataModel,
    FieldMetadata,
    LogicalTable,
    LogicalTableRelationship,
)

_metadata_logger = logging.getLogger(__name__)

def _get_aiohttp_ssl(target_domain: str = None):
    """
    获取 aiohttp 的 SSL 参数
    
    Args:
        target_domain: 目标域名（可选），用于查找域名对应的证书
    """
    # 对于 Tableau Cloud，使用系统证书
    if target_domain and "online.tableau.com" in target_domain.lower():
        return True
    
    # 对于其他域名，尝试查找对应的证书
    if target_domain:
        import ssl
        from pathlib import Path
        from urllib.parse import urlparse
        
        parsed = urlparse(target_domain)
        hostname = (parsed.netloc or target_domain).lower()
        # 注意：hostname 可能包含端口号，需要同时尝试带端口和不带端口的文件名
        safe_hostname_with_port = hostname.replace('.', '_').replace(':', '_')
        hostname_no_port = hostname.split(':')[0]
        safe_hostname_no_port = hostname_no_port.replace('.', '_')
        
        cert_config = get_certificate_config()
        cert_dir = Path(cert_config.cert_dir)
        
        # 尝试查找域名对应的证书
        possible_cert_files = [
            cert_dir / f"{safe_hostname_with_port}_cert.pem",
            cert_dir / f"{safe_hostname_no_port}_cert.pem",
            cert_dir / f"{safe_hostname_with_port}.pem",
            cert_dir / f"{safe_hostname_no_port}.pem",
            cert_dir / "tableau_cert.pem",
        ]
        
        for cert_file in possible_cert_files:
            if cert_file.exists():
                _metadata_logger.debug(f"aiohttp 使用证书: {cert_file}")
                return ssl.create_default_context(cafile=str(cert_file))
    
    return get_certificate_config().aiohttp_kwargs().get("ssl", True)

def _get_requests_verify(target_domain: str = None):
    """
    获取 requests 的 SSL 验证参数
    
    Args:
        target_domain: 目标域名（可选），用于查找域名对应的证书
    """
    from pathlib import Path
    from urllib.parse import urlparse
    
    cert_config = get_certificate_config()
    
    # 如果没有指定域名，使用全局配置
    if not target_domain:
        return cert_config.get_verify_param()
    
    # 解析域名
    parsed = urlparse(target_domain)
    hostname = (parsed.netloc or target_domain).lower()
    
    # Tableau Cloud 使用 certifi 证书包（解决 Windows 系统证书问题）
    if "online.tableau.com" in hostname:
        try:
            import certifi
            return certifi.where()
        except ImportError:
            return True
    
    # 查找域名对应的证书
    # 注意：hostname 可能包含端口号，需要同时尝试带端口和不带端口的文件名
    safe_hostname_with_port = hostname.replace('.', '_').replace(':', '_')
    hostname_no_port = hostname.split(':')[0]
    safe_hostname_no_port = hostname_no_port.replace('.', '_')
    
    cert_dir = Path(cert_config.cert_dir)
    
    possible_cert_files = [
        cert_dir / f"{safe_hostname_with_port}_cert.pem",
        cert_dir / f"{safe_hostname_no_port}_cert.pem",
        cert_dir / f"{safe_hostname_with_port}.pem",
        cert_dir / f"{safe_hostname_no_port}.pem",
        cert_dir / "tableau_cert.pem",
    ]
    
    for cert_file in possible_cert_files:
        if cert_file.exists():
            _metadata_logger.debug(f"requests 使用证书: {cert_file}")
            return str(cert_file)
    
    # 回退到全局配置
    return cert_config.get_verify_param()


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
            # 过滤掉 BIN 和 GROUP 类型的字段，这些字段不支持 TOP 过滤和计算
            dimension_names = [
                f['name'] for f in simplified_fields 
                if (f.get('role') or '').upper() == 'DIMENSION'
                and (f.get('columnClass') or '').upper() not in ('BIN', 'GROUP')
            ]
            measure_field = next((f['name'] for f in simplified_fields if (f.get('role') or '').upper() == 'MEASURE'), None)
            
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
                    if (field.get('role') or '').upper() == 'DIMENSION':
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
            # 过滤掉 BIN 和 GROUP 类型的字段，这些字段不支持 TOP 过滤和计算
            dimension_names = [
                f['name'] for f in simplified_fields 
                if (f.get('role') or '').upper() == 'DIMENSION'
                and (f.get('columnClass') or '').upper() not in ('BIN', 'GROUP')
            ]
            measure_field = next((f['name'] for f in simplified_fields if (f.get('role') or '').upper() == 'MEASURE'), None)
            
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
                    if (field.get('role') or '').upper() == 'DIMENSION':
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
    max_concurrent: int = 3
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
        result = {"sample_values": [], "unique_count": 0}
        try:
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
        except asyncio.CancelledError:
            # 协程被取消时，重新抛出让调用方处理
            raise
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
        
        response = requests.post(full_url, headers=headers, json={"query": query, "variables": {}}, verify=_get_requests_verify(domain))
        
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
    """
    通过名称查找数据源 LUID
    
    注意：Tableau Cloud 的 GraphQL API 不支持 filter 参数，
    所以我们获取所有数据源然后在本地进行过滤。
    """
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

    # 构建请求头
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-Tableau-Auth': api_key
    }
    if site:
        headers['X-Tableau-Site'] = site

    # 获取所有数据源（Tableau Cloud 不支持 filter 参数）
    try:
        query = """
        query {
          publishedDatasources {
            luid
            name
            projectName
          }
        }
        """
        
        response = requests.post(
            f"{domain}/api/metadata/graphql",
            headers=headers,
            json={"query": query},
            verify=_get_requests_verify(domain)
        )
        
        if response.status_code != 200:
            _metadata_logger.warning(f"GraphQL 请求失败: {response.status_code}")
            return None
        
        data = response.json()
        if 'errors' in data:
            _metadata_logger.warning(f"GraphQL 错误: {data['errors']}")
            return None
        
        datasources = data.get("data", {}).get("publishedDatasources", [])
        
        # 如果有项目名，先尝试精确匹配名称和项目
        if project:
            for ds in datasources:
                if ds.get("name") == name and ds.get("projectName") == project:
                    return ds.get("luid")
        
        # 精确匹配名称
        for ds in datasources:
            if ds.get("name") == name:
                return ds.get("luid")
        
        # 模糊匹配（名称包含搜索词）
        name_lower = name.lower()
        for ds in datasources:
            ds_name = ds.get("name", "")
            if name_lower in ds_name.lower():
                return ds.get("luid")
        
        return None
        
    except Exception as e:
        _metadata_logger.error(f"查找数据源失败: {e}")
        return None


async def get_datasource_metadata(
    datasource_luid: str,
    tableau_token: str,
    tableau_site: str,
    tableau_domain: str
) -> Dict[str, Any]:
    """
    从 Tableau API 获取数据源元数据（异步版本）
    
    这是 get_data_dictionary_async 的包装函数，添加了字段标准化和数据模型解析。
    
    Args:
        datasource_luid: 数据源 LUID
        tableau_token: Tableau 认证 token
        tableau_site: Tableau 站点
        tableau_domain: Tableau 域名
    
    Returns:
        元数据字典，包含标准化的字段和解析后的数据模型
    """
    logger = logging.getLogger(__name__)
    
    try:
        # 调用真实的 Tableau Metadata API（异步版本）
        metadata = await get_data_dictionary_async(
            api_key=tableau_token,
            domain=tableau_domain,
            datasource_luid=datasource_luid,
            site=tableau_site
        )
        
        # 标准化字段格式（确保同时有 name 和 fieldCaption）
        fields = metadata.get("fields", [])
        standardized_fields = []
        
        for field in fields:
            # 确保字段有必要的属性
            field_name = field.get("name", "")
            standardized_field = {
                "name": field_name,
                "fieldCaption": field_name,  # 使用 name 作为 fieldCaption
                "role": field.get("role", "dimension").lower(),  # 统一为小写
                "dataType": field.get("dataType", "STRING"),
                "dataCategory": field.get("dataCategory"),
                "aggregation": field.get("aggregation"),
            }
            
            # 添加可选字段
            if "formula" in field:
                standardized_field["formula"] = field["formula"]
            if "description" in field:
                standardized_field["description"] = field["description"]
            if "sample_values" in field:
                standardized_field["sample_values"] = field["sample_values"]
            if "unique_count" in field:
                standardized_field["unique_count"] = field["unique_count"]
            
            standardized_fields.append(standardized_field)
        
        # 分类维度和度量（注意：role 可能是 DIMENSION 或 dimension）
        dimensions = [f["name"] for f in standardized_fields if f["role"].upper() == "DIMENSION"]
        measures = [f["name"] for f in standardized_fields if f["role"].upper() == "MEASURE"]
        
        # 解析数据模型（如果存在）
        data_model_dict = metadata.get("data_model")
        data_model = None
        if data_model_dict:
            try:
                logical_tables = [
                    LogicalTable(
                        logicalTableId=t.get("logicalTableId", ""),
                        caption=t.get("caption", "")
                    )
                    for t in data_model_dict.get("logicalTables", [])
                ]
                relationships = [
                    LogicalTableRelationship(
                        fromLogicalTableId=r.get("fromLogicalTable", {}).get("logicalTableId", ""),
                        toLogicalTableId=r.get("toLogicalTable", {}).get("logicalTableId", "")
                    )
                    for r in data_model_dict.get("logicalTableRelationships", [])
                ]
                data_model = DataModel(
                    datasource_luid=datasource_luid,
                    datasource_name=metadata.get("datasource_name", "Unknown"),
                    datasource_description=metadata.get("datasource_description"),
                    datasource_owner=metadata.get("datasource_owner"),
                    logical_tables=logical_tables,
                    logical_table_relationships=relationships,
                    fields=[FieldMetadata(**f) for f in standardized_fields],
                    field_count=len(standardized_fields),
                )
                logger.info(f"解析数据模型: {len(logical_tables)} 个逻辑表, {len(relationships)} 个关系")
            except Exception as e:
                logger.warning(f"解析数据模型失败: {e}")
        
        return {
            "datasource_luid": datasource_luid,
            "datasource_name": metadata.get("datasource_name", "Unknown"),
            "datasource_description": metadata.get("datasource_description"),
            "datasource_owner": metadata.get("datasource_owner"),
            "fields": standardized_fields,
            "field_count": len(standardized_fields),
            "field_names": [f["name"] for f in standardized_fields],
            "dimensions": dimensions,
            "measures": measures,
            "data_model": data_model,  # 数据模型
            "raw_response": metadata.get("raw_graphql_response")  # 保留原始响应用于调试
        }
    
    except Exception as e:
        logger.error(f"获取数据模型失败: {e}")
        raise RuntimeError(f"无法获取数据源数据模型: {datasource_luid}") from e
