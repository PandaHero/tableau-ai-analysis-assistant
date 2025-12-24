# -*- coding: utf-8 -*-
"""
测试公司部署的 DeepSeek R1 模型 API

API 端点: https://ai.cpgroup.cn/api/v1/offline/deep/think
模型: deepseek-r1-distill-qwen
"""
import httpx
import json

BASE_URL = "https://ai.cpgroup.cn"
API_ENDPOINT = "/api/v1/offline/deep/think"
API_KEY = "oxPQEbwRu42AiFKS85sUBg"


def test_deepseek_r1_api():
    """测试 DeepSeek R1 API"""
    print("=" * 60)
    print("测试 DeepSeek R1 API")
    print(f"端点: {BASE_URL}{API_ENDPOINT}")
    print("=" * 60)
    
    payload = {
        "model": "deepseek-r1-distill-qwen",
        "max_tokens": 1024,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": "你是一个有帮助的助手。",
                "model_name": "deepseek-r1"
            },
            {
                "role": "user",
                "content": "1+1等于几？请简短回答。"
            }
        ],
        "files_id": [],
        "stream": False  # 先测试非流式
    }
    
    headers = {
        "Content-Type": "application/json",
        "Apikey": API_KEY,
        "Accept": "text/event-stream",
    }
    
    print("\n1. 测试非流式请求...")
    try:
        resp = httpx.post(
            f"{BASE_URL}{API_ENDPOINT}",
            json=payload,
            headers=headers,
            timeout=60,
            verify=False
        )
        print(f"   状态码: {resp.status_code}")
        
        if resp.status_code == 200:
            try:
                data = resp.json()
                print(f"   响应: {json.dumps(data, indent=2, ensure_ascii=False)[:2000]}")
                
                # 检查是否有思考过程
                if "choices" in data and data["choices"]:
                    message = data["choices"][0].get("message", {})
                    if "reasoning_content" in message:
                        print(f"\n   ✅ 发现 reasoning_content（R1 思考过程）!")
                        print(f"   思考内容: {message['reasoning_content'][:500]}...")
                    elif "thinking" in message:
                        print(f"\n   ✅ 发现 thinking（R1 思考过程）!")
                        print(f"   思考内容: {message['thinking'][:500]}...")
                    else:
                        print(f"\n   消息内容: {message.get('content', '')[:500]}")
            except json.JSONDecodeError:
                print(f"   响应（非JSON）: {resp.text[:1000]}")
        else:
            print(f"   响应: {resp.text[:500]}")
    except Exception as e:
        print(f"   错误: {e}")
    
    # 测试流式请求
    print("\n2. 测试流式请求...")
    payload["stream"] = True
    
    try:
        with httpx.stream(
            "POST",
            f"{BASE_URL}{API_ENDPOINT}",
            json=payload,
            headers=headers,
            timeout=60,
            verify=False
        ) as resp:
            print(f"   状态码: {resp.status_code}")
            print(f"   响应流:")
            
            full_content = ""
            full_thinking = ""
            
            for line in resp.iter_lines():
                if line:
                    # SSE 格式: data: {...}
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            print("   [DONE]")
                            break
                        try:
                            data = json.loads(data_str)
                            # 提取内容
                            if "choices" in data and data["choices"]:
                                delta = data["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                thinking = delta.get("reasoning_content", "") or delta.get("thinking", "")
                                
                                if thinking:
                                    full_thinking += thinking
                                if content:
                                    full_content += content
                        except json.JSONDecodeError:
                            pass
                    else:
                        # 可能是其他格式
                        print(f"   {line[:200]}")
            
            if full_thinking:
                print(f"\n   ✅ 思考过程: {full_thinking[:500]}...")
            if full_content:
                print(f"\n   最终回答: {full_content}")
                
    except Exception as e:
        print(f"   错误: {e}")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    
    test_deepseek_r1_api()
