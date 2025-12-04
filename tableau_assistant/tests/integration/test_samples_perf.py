"""测试样本获取性能"""
import os
import time
import asyncio
from dotenv import load_dotenv
load_dotenv()

async def test():
    from tableau_assistant.src.bi_platforms.tableau.auth import _get_tableau_context_from_env
    from tableau_assistant.src.bi_platforms.tableau.metadata import get_data_dictionary_async
    
    ctx = _get_tableau_context_from_env()
    print(f"Token: OK")
    
    domain = os.getenv("TABLEAU_DOMAIN")
    luid = os.getenv("DATASOURCE_LUID")
    site = os.getenv("TABLEAU_SITE")
    
    # 测试不含样本
    print("\n=== 不含样本 ===")
    start = time.time()
    meta = await get_data_dictionary_async(
        api_key=ctx["api_key"],
        domain=domain,
        datasource_luid=luid,
        site=site,
        include_samples=False
    )
    print(f"耗时: {time.time()-start:.2f}s, 字段数: {meta.get('field_count', 0)}")
    
    # 测试含样本
    print("\n=== 含样本（这里可能卡住）===")
    start = time.time()
    meta = await get_data_dictionary_async(
        api_key=ctx["api_key"],
        domain=domain,
        datasource_luid=luid,
        site=site,
        include_samples=True
    )
    print(f"耗时: {time.time()-start:.2f}s")

if __name__ == "__main__":
    asyncio.run(test())
