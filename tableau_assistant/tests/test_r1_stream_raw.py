# -*- coding: utf-8 -*-
"""
测试 DeepSeek R1 流式响应原始格式
"""
import asyncio
import httpx
import json


async def test_r1_stream_raw():
    print("=" * 60)
    print("测试 DeepSeek R1 流式响应原始格式")
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
        "stream": True
    }
    
    full_content = ""
    
    async with httpx.AsyncClient(verify=False, timeout=120) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            async for line in resp.aiter_lines():
                if not line:
                    continue
                
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    
                    try:
                        data = json.loads(data_str)
                        if "choices" in data and data["choices"]:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_content += content
                    except json.JSONDecodeError:
                        continue
    
    print(f"完整内容:\n{full_content}")
    print(f"\n是否包含 <think> 标签: {'<think>' in full_content}")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    asyncio.run(test_r1_stream_raw())
