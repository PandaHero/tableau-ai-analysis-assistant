# -*- coding: utf-8 -*-
"""测试获取数据源模型的替代方案"""
import asyncio
import warnings
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

async def test():
    from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
    from analytics_assistant.src.platform.tableau.client import VizQLClient
    
    auth = await get_tableau_auth_async()
    print(f'Auth: method={auth.auth_method}, site={auth.site}')
    
    async with VizQLClient() as client:
        # 先获取 LUID
        luid = await client.get_datasource_luid_by_name(
            datasource_name='正大益生业绩总览数据 (IMPALA)',
            api_key=auth.api_key,
        )
        print(f'LUID: {luid}')
        
        # 方案1: 通过 GraphQL 查询数据源的表信息
        print('\n--- 方案1: GraphQL 查询表信息 ---')
        query1 = """
        query GetDatasourceTables($luid: String!) {
            publishedDatasources(filter: {luid: $luid}) {
                name
                luid
                upstreamTables {
                    id
                    name
                    schema
                    fullName
                    connectionType
                    database {
                        name
                        connectionType
                    }
                }
            }
        }
        """
        try:
            result = await client.graphql_query(query1, {"luid": luid}, auth.api_key)
            ds = result.get("data", {}).get("publishedDatasources", [])
            if ds:
                tables = ds[0].get("upstreamTables", [])
                print(f'upstreamTables: {len(tables)} 个')
                for t in tables[:3]:
                    print(f'  - {t}')
        except Exception as e:
            print(f'Error: {e}')
        
        # 方案2: 通过 read-metadata 获取 logicalTableId
        print('\n--- 方案2: VizQL read-metadata 的 logicalTableId ---')
        try:
            metadata = await client.read_metadata(
                datasource_luid=luid,
                api_key=auth.api_key,
                site=auth.site,
            )
            fields = metadata.get("data", [])
            
            # 收集所有 logicalTableId
            table_ids = set()
            for f in fields:
                table_id = f.get("logicalTableId")
                if table_id:
                    table_ids.add(table_id)
            
            print(f'找到 {len(table_ids)} 个 logicalTableId:')
            for tid in list(table_ids)[:5]:
                print(f'  - {tid}')
                
            # 查看字段的完整结构
            print('\n字段示例:')
            if fields:
                sample = fields[0]
                for k, v in sample.items():
                    print(f'  {k}: {v}')
        except Exception as e:
            print(f'Error: {e}')
        
        # 方案3: GraphQL 查询字段的 upstreamTables
        print('\n--- 方案3: GraphQL 字段的 upstreamTables ---')
        try:
            result = await client.get_datasource_fields_metadata(
                datasource_luid=luid,
                api_key=auth.api_key,
            )
            ds = result.get("data", {}).get("publishedDatasources", [])
            if ds:
                fields = ds[0].get("fields", [])
                
                # 收集所有 upstreamTables
                table_map = {}
                for f in fields:
                    for t in f.get("upstreamTables", []) or []:
                        tid = t.get("id")
                        tname = t.get("name")
                        if tid and tid not in table_map:
                            table_map[tid] = tname
                
                print(f'从字段 upstreamTables 找到 {len(table_map)} 个表:')
                for tid, tname in list(table_map.items())[:5]:
                    print(f'  - {tid}: {tname}')
        except Exception as e:
            print(f'Error: {e}')

if __name__ == '__main__':
    asyncio.run(test())
