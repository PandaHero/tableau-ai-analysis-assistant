"""调试元数据获取"""
import asyncio
import time
import os
from dotenv import load_dotenv

load_dotenv()


async def test():
    from tableau_assistant.src.bi_platforms.tableau.auth import _get_tableau_context_from_env
    from tableau_assistant.src.bi_platforms.tableau.vizql_client import VizQLClient, VizQLClientConfig
    
    ctx = _get_tableau_context_from_env()
    domain = os.getenv('TABLEAU_DOMAIN', '').rstrip('/')
    luid = os.getenv('DATASOURCE_LUID')
    site = os.getenv('TABLEAU_SITE')
    api_key = ctx['api_key']
    
    print(f'Domain: {domain}')
    print(f'LUID: {luid}')
    
    # 步骤1: VizQL 元数据
    print('\n=== 步骤1: VizQL 元数据 ===')
    start = time.time()
    config = VizQLClientConfig(base_url=domain, timeout=30)
    client = VizQLClient(config=config)
    try:
        response = client.read_metadata(datasource_luid=luid, api_key=api_key, site=site)
        fields = response.get("data", [])
        print(f'字段数: {len(fields)}')
        print(f'耗时: {time.time() - start:.2f}s')
    finally:
        client.close()
    
    # 步骤2: VizQL 数据模型
    print('\n=== 步骤2: VizQL 数据模型 ===')
    start = time.time()
    client = VizQLClient(config=config)
    try:
        model = client.get_datasource_model(datasource_luid=luid, api_key=api_key, site=site)
        print(f'逻辑表数: {len(model.get("logicalTables", []))}')
        print(f'耗时: {time.time() - start:.2f}s')
    finally:
        client.close()
    
    # 步骤3: GraphQL roles
    print('\n=== 步骤3: GraphQL roles ===')
    start = time.time()
    from tableau_assistant.src.bi_platforms.tableau.metadata import _fetch_graphql_roles_async
    role_map = await _fetch_graphql_roles_async(domain, luid, api_key, site)
    print(f'角色数: {len(role_map)}')
    print(f'耗时: {time.time() - start:.2f}s')
    
    # 步骤4: 维度样例
    print('\n=== 步骤4: 维度样例 ===')
    start = time.time()
    from tableau_assistant.src.bi_platforms.tableau.metadata import _fetch_dimension_samples_async
    
    # 找维度和度量
    dimension_names = []
    measure_field = None
    for f in fields[:10]:  # 只取前10个字段
        name = f.get("fieldCaption") or f.get("fieldName", "")
        agg = f.get("defaultAggregation", "")
        dtype = f.get("dataType", "")
        
        if agg and agg.upper() in ("SUM", "AVG") and dtype in ("REAL", "INTEGER"):
            if not measure_field:
                measure_field = name
        else:
            if len(dimension_names) < 3:
                dimension_names.append(name)
    
    print(f'维度: {dimension_names}')
    print(f'度量: {measure_field}')
    
    if dimension_names and measure_field:
        samples = await _fetch_dimension_samples_async(
            api_key=api_key,
            domain=domain,
            datasource_luid=luid,
            dimension_names=dimension_names,
            measure_field=measure_field,
            sample_size=5,
            site=site
        )
        print(f'样例结果: {samples}')
    print(f'耗时: {time.time() - start:.2f}s')
    
    print('\n=== 完成 ===')


if __name__ == "__main__":
    asyncio.run(test())
