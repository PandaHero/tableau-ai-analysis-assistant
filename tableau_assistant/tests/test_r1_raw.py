# -*- coding: utf-8 -*-
"""
测试 DeepSeek R1 原始响应格式
"""
import asyncio
import httpx


async def test_r1_raw():
    print("=" * 60)
    print("测试 DeepSeek R1 原始响应")
    print("=" * 60)
    
    url = "https://ai.cpgroup.cn/api/v1/offline/deep/think"
    headers = {
        "Content-Type": "application/json",
        "Apikey": "oxPQEbwRu42AiFKS85sUBg",
    }
    payload = {
        "model": "deepseek-r1-distill-qwen",
        "max_tokens": 4096,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "你是助手"},
            {"role": "user", "content": "1+1=? 简短回答"}
        ],
        "stream": False
    }
    
    async with httpx.AsyncClient(verify=False, timeout=120) as client:
        resp = await client.post(url, json=payload, headers=headers)
        data = resp.json()
    
    content = data["choices"][0]["message"]["content"]
    print(f"原始内容:\n{content}")
    print(f"\n是否包含 <think> 标签: {'<think>' in content}")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    asyncio.run(test_r1_raw())
