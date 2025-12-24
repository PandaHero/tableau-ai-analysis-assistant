# -*- coding: utf-8 -*-
"""
测试 DeepSeek R1 JSON 输出场景（模拟语义理解）
"""
import asyncio
import json
from tableau_assistant.src.infra.ai import get_llm
from tableau_assistant.src.agents.base import call_llm_with_tools


async def test_r1_json():
    print("=" * 60)
    print("测试 DeepSeek R1 JSON 输出")
    print("=" * 60)
    
    llm = get_llm()
    print(f"LLM 类型: {type(llm).__name__}")
    
    messages = [
        {"role": "system", "content": """你是一个语义理解助手。请分析用户问题，输出 JSON 格式。

输出格式：
```json
{
  "intent": "查询/比较/趋势",
  "measures": ["度量1", "度量2"],
  "dimensions": ["维度1", "维度2"]
}
```

只输出 JSON，不要其他内容。"""},
        {"role": "user", "content": "各省份的销售额是多少？"}
    ]
    
    print("\n调用 LLM...")
    response = await call_llm_with_tools(
        llm=llm,
        messages=messages,
        tools=[],
        streaming=True,
    )
    
    print(f"\n响应类型: {type(response).__name__}")
    print(f"响应内容:\n{response.content}")
    
    # 检查思考过程
    thinking = response.additional_kwargs.get("thinking", "")
    if thinking:
        print(f"\n✅ 思考过程 ({len(thinking)} 字符):\n{thinking[:300]}...")
    
    # 尝试解析 JSON
    print("\n尝试解析 JSON...")
    try:
        # 清理 markdown 代码块
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        result = json.loads(content.strip())
        print(f"✅ JSON 解析成功: {result}")
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败: {e}")
        print(f"原始内容: {response.content}")


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    asyncio.run(test_r1_json())
