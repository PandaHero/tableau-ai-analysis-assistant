# with_structured_output JSON格式问题修复

## 问题描述

在使用`with_structured_output`时，某些LLM会返回带markdown标记的JSON：

```
```json
{
  "field": "value"
}
```
```

这导致Pydantic验证失败：
```
Invalid JSON: expected value at line 1 column 1
```

## 根本原因

`with_structured_output`依赖于LLM理解要输出JSON格式，但不同的LLM有不同的输出习惯：
- OpenAI GPT-4: 通常输出纯JSON
- 本地LLM（如Qwen、DeepSeek等）: 倾向于使用markdown代码块包裹JSON

## 解决方案

### 方案1: 使用json_mode参数（推荐）

```python
# 使用method="json_mode"强制LLM输出纯JSON
try:
    structured_llm = llm.with_structured_output(QueryPlanningResult, method="json_mode")
except:
    # 如果不支持json_mode，使用默认方式
    structured_llm = llm.with_structured_output(QueryPlanningResult)
```

**优点**:
- LLM级别的强制约束
- 不需要修改提示词
- 更可靠

**缺点**:
- 不是所有LLM都支持json_mode
- 需要try-except处理

### 方案2: 在提示词中明确要求

在提示词末尾添加：
```
**重要**：直接返回JSON对象，不要使用markdown代码块（不要用```json```包裹）。
```

**优点**:
- 兼容所有LLM
- 简单直接

**缺点**:
- 依赖LLM理解和遵守指令
- 不是100%可靠

### 方案3: 手动解析（备选）

如果以上两种方案都不work，可以在Agent中手动解析：

```python
response = chain.invoke({...})
content = response.content if hasattr(response, 'content') else str(response)

# 提取JSON
json_text = content.strip()
if json_text.startswith('```json'):
    json_text = json_text[7:]
elif json_text.startswith('```'):
    json_text = json_text[3:]
if json_text.endswith('```'):
    json_text = json_text[:-3]
json_text = json_text.strip()

# 解析并验证
result_dict = json.loads(json_text)
result = QueryPlanningResult(**result_dict)
```

**优点**:
- 100%可靠
- 完全控制解析过程

**缺点**:
- 失去了with_structured_output的便利性
- 需要在每个Agent中重复代码

## 当前实现

我们采用了**方案1 + 方案2的组合**：

1. **优先使用json_mode**（方案1）
   ```python
   try:
       structured_llm = llm.with_structured_output(Model, method="json_mode")
   except:
       structured_llm = llm.with_structured_output(Model)
   ```

2. **在提示词中添加明确要求**（方案2）
   ```
   **重要**：直接返回JSON对象，不要使用markdown代码块（不要用```json```包裹）。
   ```

这样可以最大程度保证兼容性和可靠性。

## 修改的文件

### Agent文件
- `tableau_assistant/src/agents/query_planner_agent.py`
- `tableau_assistant/src/agents/insight_agent.py`
- `tableau_assistant/src/agents/replanner_agent.py`

### 提示词文件
- `tableau_assistant/prompts/query_planner.py`
- `tableau_assistant/prompts/insight.py`
- `tableau_assistant/prompts/replanner.py`

## 测试验证

运行以下测试验证修复：

```bash
python tableau_assistant/tests/manual/test_mvp_complete_flow.py
```

预期结果：
- ✅ 查询规划成功（不再报JSON解析错误）
- ✅ 洞察分析成功
- ✅ 重规划决策成功

## 最佳实践

在使用`with_structured_output`时：

1. **总是添加json_mode参数**（如果LLM支持）
2. **在提示词中明确输出格式要求**
3. **使用try-except处理不支持json_mode的情况**
4. **在测试中验证不同LLM的行为**

## 参考资料

- [LangChain with_structured_output文档](https://python.langchain.com/docs/how_to/structured_output/)
- [OpenAI JSON Mode](https://platform.openai.com/docs/guides/structured-outputs)
- [Pydantic模型验证](https://docs.pydantic.dev/latest/)
