"""模拟 get_data_dictionary_async 的执行"""
import asyncio
import time
import os
from dotenv import load_dotenv

load_dotenv()


async def test():
    from tableau_assistant.src.bi_platforms.tableau.auth import _get_tableau_context_from_env
    from tableau_assistant.src.bi_platforms.tableau.vizql_client import VizQLClient, VizQLClientConfig
    from tableau_assistant.src.bi_platforms.tableau.metadata import (
        _fetch_graphql_roles_async,
        _fetch_dimension_samples_async,
        _infer_role_from_aggregation
    )
    
    ctx = _get_tableau_context_from_env()
    domain = os.getenv('TABLEAU_DOMAIN', '').rstrip('/')
    luid = os.getenv('DATASOURCE_LUID')
    site = os.getenv('TABLEAU_SITE')
    api_key = ctx['api_key']
    
    print(f'Domain: {domain}')
    print(f'LUID: {luid}')
    
    total_start = time.time()
    
    # 步骤1: 创建 VizQL 客户端
    print('\n[1] 创建 VizQL 客户端...')
    config = VizQLClientConfig(base_url=domain, timeout=30, max_retries=3)
    client = VizQLClient(config=config)
    
    # 步骤2: 获取元数据
    print('[2] 获取 VizQL 元数据...')
    start = time.time()
    response = client.read_metadata(datasource_luid=luid, api_key=api_key, site=site)
    vizql_fields = response.get("data", [])
    print(f'    完成，字段数: {len(vizql_fields)}，耗时: {time.time() - start:.2f}s')
    
    # 步骤3: 获取数据模型
    print('[3] 获取数据模型...')
    start = time.time()
    model = client.get_datasource_model(datasource_luid=luid, api_key=api_key, site=site)
    print(f'    完成，逻辑表数: {len(model.get("logicalTables", []))}，耗时: {time.time() - start:.2f}s')
    
    # 关闭客户端
    client.close()
    
    # 步骤4: 获取 GraphQL roles
    print('[4] 获取 GraphQL roles...')
    start = time.time()
    role_map = await _fetch_graphql_roles_async(domain, luid, api_key, site)
    print(f'    完成，角色数: {len(role_map)}，耗时: {time.time() - start:.2f}s')
    
    # 步骤5: 构建字段列表
    print('[5] 构建字段列表...')
    simplified_fields = []
    for vf in vizql_fields:
        field_name = vf.get("fieldCaption") or vf.get("fieldName", "")
        role = role_map.get(field_name) or role_map.get(vf.get("fieldName"))
        if not role:
            role = _infer_role_from_aggregation(vf.get("defaultAggregation"), vf.get("dataType"))
        
        field_dict = {
            "name": field_name,
            "role": role.upper() if role else "DIMENSION",
            "dataType": vf.get("dataType", "UNKNOWN"),
            "aggregation": vf.get("defaultAggregation"),
        }
        simplified_fields.append(field_dict)
    print(f'    完成，字段数: {len(simplified_fields)}')
    
    # 步骤6: 获取维度样例
    print('[6] 获取维度样例...')
    dimension_names = [f['name'] for f in simplified_fields if f.get('role', '').upper() == 'DIMENSION']
    measure_field = None
    for f in simplified_fields:
        if f.get('role', '').upper() == 'MEASURE':
            measure_field = f['name']
            break
    
    print(f'    维度数: {len(dimension_names)}，度量: {measure_field}')
    
    if dimension_names and measure_field:
        # 分批处理
        batch_size = 3
        samples_dict = {}
        
        for i in range(0, len(dimension_names), batch_size):
            batch = dimension_names[i:i + batch_size]
            print(f'    处理批次 {i//batch_size + 1}，维度数: {len(batch)}')
            start = time.time()
            
            try:
                batch_result = await _fetch_dimension_samples_async(
                    api_key=api_key,
                    domain=domain,
                    datasource_luid=luid,
                    dimension_names=batch,
                    measure_field=measure_field,
                    sample_size=5,
                    site=site
                )
                samples_dict.update(batch_result)
                print(f'    批次完成，耗时: {time.time() - start:.2f}s')
            except Exception as e:
                print(f'    批次失败: {e}')
    
    print(f'\n总耗时: {time.time() - total_start:.2f}s')
    print('测试完成')


if __name__ == "__main__":
    asyncio.run(test())
