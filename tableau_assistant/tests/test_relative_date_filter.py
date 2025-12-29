"""
测试 STRING 类型日期字段的过滤方案

关键发现：
- VizQL API 明确拒绝 SetFilter、MatchFilter、RelativeDateFilter 使用 CalculatedFilterField
- STRING 类型日期字段不能使用 RelativeDateFilter（Can't compare string and datetime values）
- QuantitativeDateFilter 对 STRING 类型字段也会报错

可行方案：
1. MatchFilter + startsWith - 按年月前缀过滤
2. SetFilter + 具体日期值列表 - 直接列出所有日期字符串
"""
import os
import sys
import json
import asyncio

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from tableau_assistant.src.platforms.tableau.vizql_client import VizQLClient
from tableau_assistant.src.platforms.tableau.auth import get_tableau_auth_async


async def get_auth_token(domain: str) -> tuple[str, str]:
    """获取认证 token"""
    # 临时禁用 SSL 验证
    import os
    os.environ['CURL_CA_BUNDLE'] = ''
    
    # 使用 verify=False 的方式获取 token
    from tableau_assistant.src.infra.config.tableau_env import get_tableau_config
    import requests
    import jwt
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4
    
    config = get_tableau_config(domain)
    
    # 使用 JWT 认证
    token = jwt.encode(
        {
            "iss": config.jwt_client_id,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            "jti": str(uuid4()),
            "aud": "tableau",
            "sub": config.user,
            "scp": ["tableau:content:read"]
        },
        config.jwt_secret,
        algorithm="HS256",
        headers={"kid": config.jwt_secret_id, "iss": config.jwt_client_id}
    )
    
    endpoint = f"{config.domain}/api/{config.api_version}/auth/signin"
    payload = {
        "credentials": {
            "jwt": token,
            "site": {"contentUrl": config.site}
        }
    }
    
    response = requests.post(
        endpoint,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        json=payload,
        verify=False  # 禁用 SSL 验证
    )
    
    if response.status_code == 200:
        api_key = response.json().get("credentials", {}).get("token")
        return api_key, config.site
    else:
        raise Exception(f"认证失败: {response.status_code} - {response.text}")


async def test_queries():
    """测试各种查询"""
    # 使用 Tableau Server
    domain = "https://cpse.cpgroup.cn:11080"
    datasource_luid = "dd01d2bd-bc89-4478-9ad5-656ca9d506cf"
    
    # 使用用户指定的日期字段
    date_field = "dt"
    
    # 临时禁用 SSL 验证（仅用于测试）
    import ssl
    import certifi
    ssl._create_default_https_context = ssl._create_unverified_context
    
    print(f"Domain: {domain}")
    print(f"Datasource LUID: {datasource_luid}")
    print(f"Date Field: {date_field}")
    print("=" * 60)
    
    # 获取认证
    api_key, site = await get_auth_token(domain)
    print(f"Site: {site}")
    print(f"API Key: {api_key[:20]}...")
    print("=" * 60)
    
    # 创建客户端（禁用 SSL 验证）
    from tableau_assistant.src.platforms.tableau.vizql_client import VizQLClient, VizQLClientConfig
    
    client_config = VizQLClientConfig(
        base_url=domain,
        verify_ssl=False,  # 禁用 SSL 验证
        timeout=60,
    )
    client = VizQLClient(config=client_config)
    
    # 先获取元数据，看看 dt 字段的类型
    print("\n1. 获取元数据，检查 dt 字段类型...")
    try:
        metadata = await client.read_metadata_async(
            datasource_luid=datasource_luid,
            api_key=api_key,
            site=site,
        )
        
        fields = metadata.get("data", [])
        print(f"   字段数量: {len(fields)}")
        
        # 找出 dt 字段
        dt_field_info = None
        string_fields = []
        for f in fields:
            field_name = f.get("fieldCaption", f.get("fieldName", ""))
            data_type = f.get("dataType", "")
            field_role = f.get("fieldRole", "")
            
            if field_name == date_field:
                dt_field_info = f
                print(f"   找到 dt 字段: dataType={data_type}, fieldRole={field_role}")
            
            # 收集所有 STRING 类型字段（不限制 fieldRole）
            if data_type == "STRING":
                string_fields.append(field_name)
        
        if not dt_field_info:
            print(f"   ⚠️ 未找到 dt 字段!")
            # 列出所有字段
            print(f"   可用字段: {[f.get('fieldCaption', f.get('fieldName', '')) for f in fields[:10]]}")
        
        print(f"   字符串维度字段: {string_fields[:5]}")
        
    except Exception as e:
        print(f"   错误: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 测试 2: dt 字段 + RelativeDateFilter (直接使用字段) - 使用 LASTN
    print(f"\n2. 测试 dt 字段 + RelativeDateFilter (dateRangeType=LASTN)...")
    
    query = {
        "fields": [
            {"fieldCaption": date_field},
        ],
        "filters": [
            {
                "field": {"fieldCaption": date_field},
                "filterType": "DATE",
                "periodType": "MONTHS",
                "dateRangeType": "LASTN",  # 使用 LASTN 而不是 LAST
                "rangeN": 3,
            }
        ],
    }
    
    print(f"   Query: {json.dumps(query, indent=2, ensure_ascii=False)}")
    
    try:
        result = await client.query_datasource_async(
            datasource_luid=datasource_luid,
            query=query,
            api_key=api_key,
            site=site,
        )
        print(f"   ✅ 成功! 返回 {len(result.get('data', []))} 行")
        if result.get('data'):
            print(f"   示例数据: {result['data'][:3]}")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
    
    # 测试 3: CalculatedFilterField + RelativeDateFilter
    print(f"\n3. 测试 CalculatedFilterField + RelativeDateFilter...")
    print(f"   使用计算字段: [{date_field}]")
    
    query = {
        "fields": [
            {"fieldCaption": date_field},
        ],
        "filters": [
            {
                "field": {
                    "calculation": f"[{date_field}]"
                },
                "filterType": "DATE",
                "periodType": "MONTHS",  # 注意是 MONTHS 不是 MONTH
                "dateRangeType": "LAST",
                "rangeN": 3,
            }
        ],
    }
    
    print(f"   Query: {json.dumps(query, indent=2, ensure_ascii=False)}")
    
    try:
        result = await client.query_datasource_async(
            datasource_luid=datasource_luid,
            query=query,
            api_key=api_key,
            site=site,
        )
        print(f"   ✅ 成功! 返回 {len(result.get('data', []))} 行")
        if result.get('data'):
            print(f"   示例数据: {result['data'][:3]}")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
    
    # 测试 4: 如果 dt 是 STRING 类型，测试 DATEPARSE + RelativeDateFilter
    if dt_field_info and dt_field_info.get("dataType") == "STRING":
        print(f"\n4. 测试 STRING 类型 + DATEPARSE + RelativeDateFilter...")
        print(f"   使用计算字段: DATEPARSE('yyyy-MM-dd', [{date_field}])")
        
        query = {
            "fields": [
                {"fieldCaption": date_field},
            ],
            "filters": [
                {
                    "field": {
                        "calculation": f"DATEPARSE('yyyy-MM-dd', [{date_field}])"
                    },
                    "filterType": "DATE",
                    "periodType": "MONTHS",  # 注意是 MONTHS 不是 MONTH
                    "dateRangeType": "LAST",
                    "rangeN": 6,
                }
            ],
        }
        
        print(f"   Query: {json.dumps(query, indent=2, ensure_ascii=False)}")
        
        try:
            result = await client.query_datasource_async(
                datasource_luid=datasource_luid,
                query=query,
                api_key=api_key,
                site=site,
            )
            print(f"   ✅ 成功! 返回 {len(result.get('data', []))} 行")
            if result.get('data'):
                print(f"   示例数据: {result['data'][:3]}")
        except Exception as e:
            print(f"   ❌ 失败: {e}")
    else:
        print(f"\n4. 跳过 DATEPARSE 测试 (dt 字段类型不是 STRING)")
    
    # 测试 5: CalculatedFilterField + SetFilter (多值模糊匹配)
    if string_fields:
        string_field = string_fields[0]
        print(f"\n5. 测试 CalculatedFilterField + SetFilter (多值模糊匹配)...")
        print(f"   字段: {string_field}")
        print(f"   计算: CONTAINS([{string_field}], 'a') OR CONTAINS([{string_field}], 'e')")
        
        query = {
            "fields": [
                {"fieldCaption": string_field},
            ],
            "filters": [
                {
                    "field": {
                        "calculation": f"CONTAINS([{string_field}], 'a') OR CONTAINS([{string_field}], 'e')"
                    },
                    "filterType": "SET",
                    "values": [True],
                    "exclude": False,
                }
            ],
        }
        
        print(f"   Query: {json.dumps(query, indent=2, ensure_ascii=False)}")
        
        try:
            result = await client.query_datasource_async(
                datasource_luid=datasource_luid,
                query=query,
                api_key=api_key,
                site=site,
            )
            print(f"   ✅ 成功! 返回 {len(result.get('data', []))} 行")
            if result.get('data'):
                print(f"   示例数据: {result['data'][:3]}")
        except Exception as e:
            print(f"   ❌ 失败: {e}")
    
    # 测试 6: MatchFilter - startsWith 方案
    print(f"\n6. 测试 MatchFilter - startsWith (按年月前缀过滤)...")
    
    query = {
        "fields": [
            {"fieldCaption": date_field},
        ],
        "filters": [
            {
                "field": {"fieldCaption": date_field},
                "filterType": "MATCH",
                "startsWith": "2024-1",  # 2024年10-12月
            }
        ],
    }
    
    print(f"   Query: {json.dumps(query, indent=2, ensure_ascii=False)}")
    
    try:
        result = await client.query_datasource_async(
            datasource_luid=datasource_luid,
            query=query,
            api_key=api_key,
            site=site,
        )
        print(f"   ✅ 成功! 返回 {len(result.get('data', []))} 行")
        if result.get('data'):
            print(f"   示例数据: {result['data'][:5]}")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
    
    # 测试 7: SetFilter - 直接用日期字符串值
    print(f"\n7. 测试 SetFilter - 直接用日期字符串值...")
    
    # 生成最近几个月的日期值
    from datetime import datetime, timedelta
    dates = []
    today = datetime.now()
    for i in range(90):  # 最近90天
        d = today - timedelta(days=i)
        dates.append(d.strftime('%Y-%m-%d'))
    
    query = {
        "fields": [
            {"fieldCaption": date_field},
        ],
        "filters": [
            {
                "field": {"fieldCaption": date_field},
                "filterType": "SET",
                "values": dates[:30],  # 只用最近30天测试
                "exclude": False,
            }
        ],
    }
    
    print(f"   Query: 使用 {len(dates[:30])} 个日期值")
    
    try:
        result = await client.query_datasource_async(
            datasource_luid=datasource_luid,
            query=query,
            api_key=api_key,
            site=site,
        )
        print(f"   ✅ 成功! 返回 {len(result.get('data', []))} 行")
        if result.get('data'):
            print(f"   示例数据: {result['data'][:5]}")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
    
    # 测试 8: QuantitativeDateFilter + DATEPARSE (STRING 类型日期字段的正确方案)
    print(f"\n8. 测试 QuantitativeDateFilter + DATEPARSE...")
    
    query = {
        "fields": [
            {"fieldCaption": date_field},
        ],
        "filters": [
            {
                "field": {
                    "calculation": f"DATEPARSE('yyyy-MM-dd', [{date_field}])"
                },
                "filterType": "QUANTITATIVE_DATE",
                "quantitativeFilterType": "RANGE",
                "minDate": "2024-10-01",
                "maxDate": "2024-12-31",
            }
        ],
    }
    
    print(f"   Query: {json.dumps(query, indent=2, ensure_ascii=False)}")
    
    try:
        result = await client.query_datasource_async(
            datasource_luid=datasource_luid,
            query=query,
            api_key=api_key,
            site=site,
        )
        print(f"   ✅ 成功! 返回 {len(result.get('data', []))} 行")
        if result.get('data'):
            print(f"   示例数据: {result['data'][:5]}")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
    
    print("\n" + "=" * 60)
    print("测试完成!")


if __name__ == "__main__":
    asyncio.run(test_queries())
