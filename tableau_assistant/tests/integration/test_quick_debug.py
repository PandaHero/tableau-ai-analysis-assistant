"""快速调试"""
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
    
    # 创建客户端
    config = VizQLClientConfig(base_url=domain, timeout=30, max_retries=3)
    client = VizQLClient(config=config)
    
    print('开始 read_metadata...')
    start = time.time()
    
    try:
        response = client.read_metadata(datasource_luid=luid, api_key=api_key, site=site)
        print(f'read_metadata 完成，耗时: {time.time() - start:.2f}s')
        print(f'字段数: {len(response.get("data", []))}')
    except Exception as e:
        print(f'错误: {e}')
    finally:
        client.close()
    
    print('测试完成')


if __name__ == "__main__":
    asyncio.run(test())
