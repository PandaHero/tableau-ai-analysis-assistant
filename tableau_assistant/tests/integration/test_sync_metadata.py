"""测试同步版本的元数据获取"""
import time
import os
from dotenv import load_dotenv

load_dotenv()


def test():
    from tableau_assistant.src.bi_platforms.tableau.auth import _get_tableau_context_from_env
    from tableau_assistant.src.bi_platforms.tableau.metadata import get_data_dictionary
    
    ctx = _get_tableau_context_from_env()
    domain = os.getenv('TABLEAU_DOMAIN')
    luid = os.getenv('DATASOURCE_LUID')
    site = os.getenv('TABLEAU_SITE')
    
    print('=== 测试同步版本元数据获取 ===')
    print(f'Domain: {domain}')
    print(f'LUID: {luid}')
    
    start = time.time()
    meta = get_data_dictionary(
        api_key=ctx['api_key'],
        domain=domain,
        datasource_luid=luid,
        site=site,
        include_samples=True
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
    
    # 打印前5个维度的详情
    print('\n=== 维度详情 ===')
    count = 0
    for f in fields:
        if f.get('role', '').upper() == 'DIMENSION':
            samples = f.get('sample_values', [])
            countd = f.get('unique_count', 0)
            print(f"  {f['name']}: 样例数={len(samples)}, COUNTD={countd}")
            if samples:
                print(f"    样例: {samples[:3]}")
            count += 1
            if count >= 5:
                break
    
    print('\n=== 测试完成 ===')


if __name__ == "__main__":
    test()
