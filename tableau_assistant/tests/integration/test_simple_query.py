"""简单测试 VizQL 查询"""
import asyncio
import time
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()


async def test():
    from tableau_assistant.src.bi_platforms.tableau.auth import _get_tableau_context_from_env
    
    ctx = _get_tableau_context_from_env()
    domain = os.getenv('TABLEAU_DOMAIN', '').rstrip('/')
    luid = os.getenv('DATASOURCE_LUID')
    site = os.getenv('TABLEAU_SITE')
    api_key = ctx['api_key']
    
    print(f'Domain: {domain}')
    print(f'LUID: {luid}')
    
    # 简单查询
    query = {
        "fields": [
            {"fieldCaption": "first_receive_dt"},
            {"fieldCaption": "countd_test", "calculation": "{FIXED : COUNTD([first_receive_dt])}"}
        ],
        "filters": [
            {
                "filterType": "TOP",
                "field": {"fieldCaption": "first_receive_dt"},
                "fieldToMeasure": {"fieldCaption": "first_receive_sale_num", "function": "SUM"},
                "howMany": 5,
                "direction": "TOP"
            }
        ]
    }
    
    full_url = f"{domain}/api/v1/vizql-data-service/query-datasource"
    headers = {
        'X-Tableau-Auth': api_key,
        'Content-Type': 'application/json'
    }
    if site:
        headers['X-Tableau-Site'] = site
    
    payload = {
        "datasource": {"datasourceLuid": luid},
        "query": query
    }
    
    try:
        from tableau_assistant.cert_manager import get_ssl_config
        ssl_param = get_ssl_config().get_aiohttp_ssl_param()
    except ImportError:
        ssl_param = False
    
    print('发送请求...')
    start = time.time()
    
    async with aiohttp.ClientSession() as session:
        async with session.post(full_url, json=payload, headers=headers, ssl=ssl_param, timeout=aiohttp.ClientTimeout(total=30)) as response:
            print(f'状态码: {response.status}')
            if response.status == 200:
                result = await response.json()
                print(f'数据行数: {len(result.get("data", []))}')
                print(f'耗时: {time.time() - start:.2f}s')
            else:
                print(f'错误: {await response.text()}')


if __name__ == "__main__":
    asyncio.run(test())
