# -*- coding: utf-8 -*-
"""Get datasources from Tableau Server"""
import asyncio

async def main():
    from analytics_assistant.src.infra.config.config_loader import AppConfig
    AppConfig._instance = None
    from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
    from analytics_assistant.src.platform.tableau.client import VizQLClient

    auth = await get_tableau_auth_async()
    print(f"Auth OK: {auth.auth_method}")
    
    async with VizQLClient() as client:
        result = await client.graphql_query(
            query="query { publishedDatasources { luid name projectName } }",
            variables=None,
            api_key=auth.api_key,
        )
        datasources = result.get("data", {}).get("publishedDatasources", [])
        print(f"Found {len(datasources)} datasources:")
        for ds in datasources[:10]:
            print(f"  - {ds.get('name')}: {ds.get('luid')}")

if __name__ == "__main__":
    asyncio.run(main())
