"""测试优化后的元数据获取性能"""
import asyncio
import time
import os
from dotenv import load_dotenv

load_dotenv()


async def test():
    from tableau_assistant.src.bi_platforms.tableau.auth import _get_tableau_context_from_env
    from tableau_assistant.src.bi_platforms.tableau.metadata import get_data_dictionary_async
    
    ctx = _get_tableau_context_from_env()
    domain = os.getenv('TABLEAU_DOMAIN')
    luid = os.getenv('DATASOURCE_LUID')
    site = os.getenv('TABLEAU_SITE')
    
    print('=== 测试优化后的元数据获取 ===')
    start = time.time()
    meta = await get_data_dictionary_async(
        api_key=ctx['api_key'],
        domain=domain,
        datasource_luid=luid,
        site=site,
        include_samples=True
    )
    elapsed = time.time() - start
    
    print(f'耗时: {elapsed:.2f}s')
    print(f'字段数: {meta.get("field_count", 0)}')
    
    # 检查维度字段的样例值和 COUNTD
    fields = meta.get('fields', [])
    dims_with_samples = 0
    dims_with_countd = 0
    
    print('\n=== 维度字段详情 ===')
    for f in fields:
        if f.get('role', '').upper() == 'DIMENSION':
            samples = f.get('sample_values', [])
            countd = f.get('unique_count', 0)
            if samples:
                dims_with_samples += 1
            if countd > 0:
                dims_with_countd += 1
            print(f"  {f['name']}: 样例数={len(samples)}, COUNTD={countd}")
            if samples:
                print(f"    样例: {samples[:3]}")
    
    print(f'\n有样例值的维度: {dims_with_samples}')
    print(f'有 COUNTD 的维度: {dims_with_countd}')


if __name__ == "__main__":
    asyncio.run(test())
