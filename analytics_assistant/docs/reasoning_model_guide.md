# 推理模型使用指南

## 概述

推理模型（如 DeepSeek-R1）具有特殊的思考能力，会先输出思考过程，然后给出最终答案。ModelManager 提供了对推理模型的完整支持。

## 推理模型特点

1. **思考过程（Thinking）**：模型会先进行深度思考，输出推理过程
2. **最终答案（Answer）**：在思考后给出精确的答案
3. **特殊输出格式**：
   - `response.content`：最终答案
   - `response.additional_kwargs['thinking']`：思考过程
   - `response.additional_kwargs['raw_content']`：原始输出（包含思考和答案）

## 配置推理模型

### 1. 注册 DeepSeek-R1 模型

```python
from src.infra.ai import get_model_manager, ModelCreateRequest, ModelType, TaskType

manager = get_model_manager()

# 注册 DeepSeek-R1（推理模型）
deepseek_r1_request = ModelCreateRequest(
    name="DeepSeek-R1",
    model_type=ModelType.LLM,
    provider="deepseek",
    api_base="http://localhost:8001/v1",  # 或云端 API
    model_name="deepseek-reasoner",
    api_key="your-api-key",
    openai_compatible=True,
    temperature=0.7,
    supports_streaming=True,
    is_reasoning_model=True,  # 标记为推理模型
    suitable_tasks=[
        TaskType.REASONING,  # 推理任务
        TaskType.INSIGHT_GENERATION,  # 洞察生成
        TaskType.REPLANNING,  # 重新规划
    ],
    priority=10,
)

config = manager.create(deepseek_r1_request)
```

### 2. 环境变量配置

```bash
# .env

# DeepSeek-R1 配置
DEEPSEEK_R1_API_BASE=http://localhost:8001/v1
DEEPSEEK_R1_API_KEY=your-api-key
DEEPSEEK_R1_MODEL_NAME=deepseek-reasoner
```

## 使用推理模型

### 1. 基本调用

```python
from src.infra.ai import get_model_manager, TaskType

manager = get_model_manager()

# 方式 1：使用任务类型路由（自动选择推理模型）
llm = manager.create_llm(task_type=TaskType.REASONING)

# 方式 2：显式指定推理模型
llm = manager.create_llm(model_id="deepseek-deepseek-reasoner")

# 调用模型
response = llm.invoke("请分析为什么销售额在第三季度下降了15%")

# 获取最终答案
print("答案:", response.content)

# 获取思考过程
thinking = response.additional_kwargs.get('thinking', '')
print("思考过程:", thinking)
```

### 2. 流式输出（推荐）

推理模型的流式输出可以实时显示思考过程：

```python
# 启用流式输出
llm = manager.create_llm(
    task_type=TaskType.REASONING,
    streaming=True
)

print("思考过程:")
for chunk in llm.stream("请分析销售数据的异常模式"):
    print(chunk.content, end="", flush=True)

# 最后一个 chunk 包含完整的 additional_kwargs
# 可以从中提取思考过程和答案
```

### 3. 异步流式输出

```python
async def analyze_with_reasoning():
    llm = manager.create_llm(
        task_type=TaskType.REASONING,
        streaming=True
    )
    
    print("思考过程:")
    async for chunk in llm.astream("分析用户流失的根本原因"):
        print(chunk.content, end="", flush=True)
        
        # 检查是否包含思考过程
        if hasattr(chunk, 'additional_kwargs'):
            thinking = chunk.additional_kwargs.get('thinking')
            if thinking:
                print(f"\n\n[思考]: {thinking}")

# 运行
import asyncio
asyncio.run(analyze_with_reasoning())
```

## 推理模型的输出格式

### 标准输出格式

```python
response = llm.invoke("复杂问题")

# AIMessage 结构：
{
    "content": "最终答案（不含思考过程）",
    "additional_kwargs": {
        "thinking": "详细的思考过程...",
        "answer": "最终答案",
        "raw_content": "<think>思考过程</think>\n最终答案"
    },
    "tool_calls": []
}
```

### 提取思考过程和答案

```python
def extract_reasoning(response):
    """提取推理模型的思考过程和答案"""
    # 最终答案（已解析）
    answer = response.content
    
    # 思考过程
    thinking = response.additional_kwargs.get('thinking', '')
    
    # 原始输出（包含 <think> 标签）
    raw_content = response.additional_kwargs.get('raw_content', '')
    
    return {
        'answer': answer,
        'thinking': thinking,
        'raw_content': raw_content
    }

# 使用
response = llm.invoke("复杂问题")
result = extract_reasoning(response)

print("思考过程:", result['thinking'])
print("最终答案:", result['answer'])
```

## 在 Agent 中使用推理模型

### 1. 语义解析 Agent

```python
from src.infra.ai import get_model_manager, TaskType

class SemanticParserAgent:
    def __init__(self):
        manager = get_model_manager()
        # 对于复杂查询，使用推理模型
        self.reasoning_llm = manager.create_llm(task_type=TaskType.REASONING)
        # 对于简单查询，使用普通模型
        self.normal_llm = manager.create_llm(task_type=TaskType.SEMANTIC_PARSING)
    
    def parse(self, query: str, use_reasoning: bool = False):
        """解析用户查询"""
        llm = self.reasoning_llm if use_reasoning else self.normal_llm
        
        response = llm.invoke(f"解析查询: {query}")
        
        # 如果使用推理模型，记录思考过程
        if use_reasoning:
            thinking = response.additional_kwargs.get('thinking', '')
            print(f"[推理过程]: {thinking}")
        
        return response.content
```

### 2. 洞察生成 Agent

```python
class InsightAgent:
    def __init__(self):
        manager = get_model_manager()
        # 洞察生成需要深度思考，使用推理模型
        self.llm = manager.create_llm(task_type=TaskType.INSIGHT_GENERATION)
    
    async def generate_insights(self, data: dict):
        """生成数据洞察"""
        prompt = f"分析以下数据并生成洞察: {data}"
        
        # 流式输出思考过程
        print("正在分析...")
        async for chunk in self.llm.astream(prompt):
            print(chunk.content, end="", flush=True)
        
        # 获取完整响应
        response = await self.llm.ainvoke(prompt)
        
        return {
            'insights': response.content,
            'reasoning': response.additional_kwargs.get('thinking', '')
        }
```

## 推理模型 vs 普通模型

### 何时使用推理模型

✅ **适合使用推理模型的场景**：
- 复杂的数据分析任务
- 需要多步推理的问题
- 需要解释推理过程的场景
- 洞察生成和模式发现
- 异常检测和根因分析
- 策略规划和决策支持

❌ **不适合使用推理模型的场景**：
- 简单的字段映射
- 快速的意图分类
- 实时性要求高的场景（推理模型较慢）
- 不需要解释的简单任务

### 性能对比

| 特性 | 推理模型（R1） | 普通模型（GPT-4） |
|------|---------------|------------------|
| 推理能力 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| 响应速度 | ⭐⭐ | ⭐⭐⭐⭐ |
| 思考过程 | ✅ 可见 | ❌ 不可见 |
| 适用场景 | 复杂推理 | 通用任务 |
| Token 消耗 | 较高 | 中等 |

## 最佳实践

### 1. 混合使用推理模型和普通模型

```python
class HybridAgent:
    def __init__(self):
        manager = get_model_manager()
        self.reasoning_llm = manager.create_llm(task_type=TaskType.REASONING)
        self.fast_llm = manager.create_llm(task_type=TaskType.SEMANTIC_PARSING)
    
    def process(self, query: str, complexity: str = "auto"):
        """根据复杂度选择模型"""
        if complexity == "auto":
            # 自动判断复杂度
            complexity = self._assess_complexity(query)
        
        if complexity == "high":
            print("使用推理模型处理复杂查询...")
            return self.reasoning_llm.invoke(query)
        else:
            print("使用快速模型处理简单查询...")
            return self.fast_llm.invoke(query)
    
    def _assess_complexity(self, query: str) -> str:
        """评估查询复杂度"""
        # 简单规则：包含"为什么"、"分析"、"原因"等关键词 → 复杂
        complex_keywords = ["为什么", "分析", "原因", "趋势", "预测", "建议"]
        if any(kw in query for kw in complex_keywords):
            return "high"
        return "low"
```

### 2. 缓存推理结果

推理模型的思考过程可以缓存，避免重复计算：

```python
import hashlib
import json

class CachedReasoningAgent:
    def __init__(self):
        manager = get_model_manager()
        self.llm = manager.create_llm(task_type=TaskType.REASONING)
        self.cache = {}
    
    def reason(self, query: str, use_cache: bool = True):
        """带缓存的推理"""
        # 计算查询哈希
        query_hash = hashlib.md5(query.encode()).hexdigest()
        
        # 检查缓存
        if use_cache and query_hash in self.cache:
            print("使用缓存结果")
            return self.cache[query_hash]
        
        # 调用推理模型
        response = self.llm.invoke(query)
        
        # 缓存结果
        result = {
            'answer': response.content,
            'thinking': response.additional_kwargs.get('thinking', '')
        }
        self.cache[query_hash] = result
        
        return result
```

### 3. 显示思考进度

```python
async def reason_with_progress(query: str):
    """显示推理进度"""
    manager = get_model_manager()
    llm = manager.create_llm(task_type=TaskType.REASONING, streaming=True)
    
    print("🤔 开始思考...")
    thinking_tokens = 0
    answer_tokens = 0
    
    async for chunk in llm.astream(query):
        content = chunk.content
        if content:
            # 简单判断：前面的是思考，后面的是答案
            if thinking_tokens < 500:  # 假设前 500 tokens 是思考
                thinking_tokens += len(content)
                print(".", end="", flush=True)
            else:
                answer_tokens += len(content)
                print(content, end="", flush=True)
    
    print(f"\n\n✅ 思考完成（思考: {thinking_tokens} tokens, 答案: {answer_tokens} tokens）")
```

## 故障排查

### 问题：推理模型返回格式不正确

```python
# 检查模型是否正确标记为推理模型
config = manager.get("deepseek-deepseek-reasoner")
print(f"是否推理模型: {config.is_reasoning_model}")

# 检查 additional_kwargs
response = llm.invoke("测试")
print(f"additional_kwargs: {response.additional_kwargs}")
```

### 问题：无法提取思考过程

```python
# 确保使用流式输出或完整响应
response = llm.invoke("问题")

# 检查是否有 thinking 字段
if 'thinking' in response.additional_kwargs:
    print("思考过程:", response.additional_kwargs['thinking'])
else:
    print("未找到思考过程，可能需要检查模型配置")
```

## 总结

推理模型为复杂的分析任务提供了强大的能力：

✅ **优势**：
- 深度推理能力
- 可解释的思考过程
- 适合复杂分析任务

⚠️ **注意事项**：
- 响应速度较慢
- Token 消耗较高
- 需要合理选择使用场景

💡 **建议**：
- 混合使用推理模型和普通模型
- 缓存推理结果
- 根据任务复杂度自动选择模型
