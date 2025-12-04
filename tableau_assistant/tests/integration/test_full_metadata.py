"""测试完整的元数据获取"""
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
    
    print('=== 测试 get_data_dictionary_async ===')
    print(f'Domain: {domain}')
    print(f'LUID: {luid}')
    
    start = time.time()
    try:
        meta = await asyncio.wait_for(
            get_data_dictionary_async(
                api_key=ctx['api_key'],
                domain=domain,
                datasource_luid=luid,
                site=site,
                include_samples=True
            ),
            timeout=60  # 60秒超时
        )
        elapsed = time.time() - start
        
        print(f'\n耗时: {elapsed:.2f}s')
        print(f'字段数: {meta.get("field_count", 0)}')
        
        # 检查维度字段
        fields = meta.get('fields', [])
        dims_with_samples = sum(1 for f in fields if f.get('sample_values'))
        dims_with_countd = sum(1 for f in fields if f.get('unique_count', 0) > 0)
        
        print(f'有样例值的维度: {dims_with_samples}')
        print(f'有 COUNTD 的维度: {dims_with_countd}')
        
        # 打印前3个维度的详情
        print('\n=== 前3个维度详情 ===')
        count = 0
        for f in fields:
            if f.get('role', '').upper() == 'DIMENSION':
                print(f"  {f['name']}: 样例={f.get('sample_values', [])[:3]}, COUNTD={f.get('unique_count', 0)}")
                count += 1
                if count >= 3:
                    break
                    
    except asyncio.TimeoutError:
        print(f'\n超时！已运行 {time.time() - start:.2f}s')
    except Exception as e:
        print(f'\n错误: {e}')
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test())
