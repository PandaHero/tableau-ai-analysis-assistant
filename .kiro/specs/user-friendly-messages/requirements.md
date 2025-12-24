# 需求文档

## 简介

优化后端返回给前端的消息结构，从简单的拼接字符串改为结构化数据，以便前端能够灵活渲染不同类型的消息。

## 术语表

- **消息数据 (Message_Data)**: 后端返回给前端的结构化消息对象
- **思考过程 (Thinking)**: LLM 的推理步骤和中间结果
- **查询摘要 (Query_Summary)**: 解析后的查询结构（维度、指标、筛选、计算）
- **字段映射 (Field_Mapping)**: 用户输入到实际字段的映射关系

## 需求

### 需求 1: 结构化消息数据

**用户故事:** 作为前端开发者，我希望后端返回结构化的消息数据，以便我能灵活地渲染不同类型的消息。

#### 验收标准

1. 当语义解析完成时，后端应返回 `message_data` 对象而非拼接的字符串
2. `message_data` 应包含以下字段：
   - `type`: 意图类型 (DATA_QUERY, CLARIFICATION, GENERAL, IRRELEVANT)
   - `restated_question`: 重述的问题
   - `thinking`: 思考过程对象（可选）
   - `query_summary`: 查询摘要对象（仅 DATA_QUERY）
   - `clarification_options`: 澄清选项列表（仅 CLARIFICATION）
   - `general_response`: 通用响应文本（仅 GENERAL）
3. 后端不应在返回数据中包含 emoji 或格式化字符，这些由前端处理

### 需求 2: 思考过程记录

**用户故事:** 作为用户，我希望能查看 AI 的推理过程，以便理解和验证其分析。

#### 验收标准

1. 当语义解析完成时，`thinking` 对象应包含：
   - `intent`: 识别的意图类型
   - `intent_reasoning`: 意图判断的理由
   - `how_type`: 计算类型（SIMPLE, RANK, PERCENT 等）
   - `how_reasoning`: 计算类型判断的理由（如有）
2. 思考过程应来自 Step1Output 和 Step2Output 的实际输出
3. 思考过程应为可选字段，可通过配置开启/关闭

### 需求 3: 查询摘要结构化

**用户故事:** 作为用户，我希望看到清晰的查询摘要，以便确认系统正确理解了我的问题。

#### 验收标准

1. 当检测到 DATA_QUERY 意图时，`query_summary` 应包含：
   - `dimensions`: 维度列表，每个包含 `field_name` 和 `date_granularity`（如有）
   - `measures`: 指标列表，每个包含 `field_name` 和 `aggregation`
   - `filters`: 筛选条件列表，每个包含 `field_name`、`type` 和 `values`
   - `computations`: 计算列表，每个包含 `type` 和相关参数
2. 查询摘要应直接从 SemanticQuery 对象转换，不做额外处理

### 需求 4: 字段映射信息

**用户故事:** 作为用户，我希望看到字段映射关系，以便理解系统如何将我的输入映射到实际字段。

#### 验收标准

1. 当字段映射完成时，应返回 `field_mappings` 列表
2. 每个映射应包含：
   - `user_input`: 用户输入的字段名
   - `mapped_to`: 映射到的实际字段名
   - `confidence`: 映射置信度（0-1）
3. 字段映射信息应来自 FieldMapper 的输出

### 需求 5: 澄清选项结构化

**用户故事:** 作为用户，我希望在需要澄清时看到可选的选项，以便快速选择而非手动输入。

#### 验收标准

1. 当检测到 CLARIFICATION 意图时，`clarification_options` 应包含：
   - `question`: 澄清问题文本
   - `options`: 可选选项列表（如有）
   - `field_reference`: 相关字段引用（如有）
2. 选项应来自数据模型中的可用字段或常见值
3. 选项数量应限制在 5-7 个

### 需求 6: SSE 事件扩展

**用户故事:** 作为前端开发者，我希望通过 SSE 接收更细粒度的进度事件，以便实时更新 UI。

#### 验收标准

1. SSE 事件类型应扩展为：
   - `stage_start`: 阶段开始（包含阶段名称）
   - `stage_complete`: 阶段完成（包含阶段名称和耗时）
   - `thinking`: 思考过程更新
   - `result`: 最终结果
   - `error`: 错误信息
2. 每个事件应包含 `timestamp` 字段
3. 阶段名称应使用标准化的枚举值

## 备注

### 当前实现问题

当前 `semantic_parser_node` 返回的 `user_message` 是拼接好的字符串：

```python
# 当前实现（不好）
user_message = f"🔍 理解您的问题：{result.restated_question}"
if dims:
    user_message += f"\n📊 分析维度：{', '.join(dims)}"
if measures:
    user_message += f"\n📈 分析指标：{', '.join(measures)}"
return_state["user_message"] = user_message
```

### 目标实现

改为返回结构化数据：

```python
# 目标实现（好）
return_state["message_data"] = {
    "type": result.intent.type.value,
    "restated_question": result.restated_question,
    "thinking": {
        "intent": result.intent.type.value,
        "intent_reasoning": result.intent.reasoning,
        "how_type": step1_output.how_type.value if hasattr(step1_output, 'how_type') else None,
    },
    "query_summary": {
        "dimensions": [
            {"field_name": d.field_name, "date_granularity": d.date_granularity}
            for d in (result.semantic_query.dimensions or [])
        ],
        "measures": [
            {"field_name": m.field_name, "aggregation": m.aggregation}
            for m in (result.semantic_query.measures or [])
        ],
        "filters": [
            {"field_name": f.field_name, "type": f.type, "values": getattr(f, 'values', None)}
            for f in (result.semantic_query.filters or [])
        ],
        "computations": [
            {"type": c.operation.type.value, "params": {...}}
            for c in (result.semantic_query.computations or [])
        ],
    } if result.semantic_query else None,
}
```

### 需要修改的文件

1. `tableau_assistant/src/agents/semantic_parser/node.py` - 修改返回结构
2. `tableau_assistant/src/api/models.py` - 添加新的 Pydantic 模型
3. `tableau_assistant/src/api/chat.py` - 更新 SSE 事件生成逻辑
