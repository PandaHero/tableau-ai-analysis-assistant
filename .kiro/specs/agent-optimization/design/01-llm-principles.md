# LLM 原理与工具化设计

## 1. 设计目标

从 LLM 原理层面思考哪些能力应该由 LLM 处理，哪些应该工具化。

## 2. LLM 能力边界分析

### 2.1 LLM 擅长的任务

| 任务类型 | 说明 | 示例 |
|---------|------|------|
| 语义理解 | 理解自然语言的含义和意图 | "各省份的销售额" → 意图=查询数据 |
| 意图分类 | 将输入分类到预定义类别 | DATA_QUERY / CLARIFICATION / GENERAL |
| 推理决策 | 基于上下文做出判断 | 判断是否需要复杂计算 |
| 从候选中选择 | 在有限选项中选择最佳匹配 | 从 5 个候选字段中选择 |
| 生成自然语言 | 生成流畅的回复 | 生成洞察报告 |
| 格式转换 | 将信息转换为指定格式 | 生成结构化 JSON |

### 2.2 LLM 不擅长的任务

| 任务类型 | 说明 | 应该工具化 |
|---------|------|-----------|
| 精确字符串匹配 | 在大量选项中精确匹配 | RAG 检索 |
| 数值计算 | 复杂的数学运算 | 代码执行 |
| 大量信息记忆 | 记住 100+ 个字段名 | 数据库/索引 |
| 实时数据获取 | 获取最新数据 | API 调用 |
| 格式验证 | 验证输出格式正确性 | Pydantic Schema |

### 2.3 能力边界图

```
┌─────────────────────────────────────────────────────────────────┐
│                      LLM 能力边界                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    LLM 核心能力                          │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐       │   │
│  │  │语义理解 │ │意图分类 │ │推理决策 │ │文本生成 │       │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    工具化能力                            │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐       │   │
│  │  │RAG检索  │ │API调用  │ │代码执行 │ │格式验证 │       │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 3. 工具化设计原则

### 3.1 核心原则

1. **LLM 做决策，工具做执行**
   - LLM 决定"做什么"
   - 工具执行"怎么做"

2. **减少 LLM 记忆负担**
   - 不传递完整数据模型
   - 使用 RAG 检索候选项

3. **利用 LLM 的选择能力**
   - 让 LLM 从候选中选择
   - 而非让 LLM 生成具体值

4. **结构化输出保证格式**
   - 使用 Pydantic Schema
   - 使用 `with_structured_output()`

### 3.2 任务分配矩阵

| 任务 | LLM 职责 | 工具职责 |
|------|---------|---------|
| 字段映射 | 从候选中选择 | RAG 检索候选字段 |
| 查询构建 | 生成语义结构 | 转换为 VizQL 语法 |
| 数据获取 | 无 | Tableau API 调用 |
| 洞察生成 | 分析数据，生成文本 | 数据预处理、统计计算 |
| 错误处理 | 判断错误类型，决定重试 | 执行重试逻辑 |

## 4. 当前架构问题分析

### 4.1 问题 1: LLM 调用过多

```
当前流程（最坏情况 13 次 LLM 调用）：
Step1 (1) + Step2 (1) + Observer (1+) + Director×N + Analyzer×N + Replanner (1)
```

**原因分析**：
- Step1 和 Step2 分离，但可以合并
- Director 和 Analyzer 分离，每批数据调用 2 次

**优化方案**：
- 合并 Step1 + Step2 为 UnifiedSemanticParser
- 合并 Director + Analyzer 为 ChainAnalyzer

### 4.2 问题 2: Token 消耗过高

```
当前做法：
- 每次调用传递完整数据模型（3000+ tokens）
- 对话历史无压缩（累积增长）
```

**原因分析**：
- LLM 不擅长从大量选项中搜索
- 但我们把搜索任务交给了 LLM

**优化方案**：
- RAG 检索候选字段，只传 Top 5-10
- 对话历史摘要压缩

### 4.3 问题 3: 中间件冗余

```
当前中间件：
- OutputValidationMiddleware（与 Pydantic 重复）
- PatchToolCallsMiddleware（结构化输出不需要）
```

**原因分析**：
- 使用 `with_structured_output()` 后，LLM 输出已经是结构化的
- 结构化输出不会产生悬空工具调用

**优化方案**：
- 移除 OutputValidationMiddleware
- 移除 PatchToolCallsMiddleware
- 使用 LangChain 内置中间件

## 5. 优化后的任务分配

### 5.1 UnifiedSemanticParser

```
LLM 职责：
├── 语义理解（What/Where/How）
├── 意图分类（DATA_QUERY/CLARIFICATION/GENERAL）
├── 计算推理（是否需要 LOD/TABLE_CALC）
└── 从候选字段中选择

工具职责：
├── RAG 检索候选字段
├── 格式验证（Pydantic Schema）
└── 查询构建（VizQL 语法转换）
```

### 5.2 ChainAnalyzer

```
LLM 职责：
├── 数据分析（识别趋势、异常、关联）
├── 洞察生成（自然语言描述）
├── 洞察去重（避免重复/冲突）
└── 报告组织（结构化输出）

工具职责：
├── 数据预处理（Profiler）
├── 统计计算（均值、方差、趋势）
├── 数据缓冲（LangGraph Store）
└── 流式输出（SSE）
```

### 5.3 Observer

```
LLM 职责：
├── 错误分类（语法错误/字段错误/权限错误）
├── 重试决策（RETRY/CLARIFY/ABORT）
└── 错误反馈生成

工具职责：
├── 错误捕获
├── 重试执行
└── 状态管理
```

## 6. 结构化输出设计

### 6.1 为什么使用结构化输出

```python
# ❌ 传统方式：解析 LLM 文本输出
response = llm.invoke(prompt)
try:
    result = json.loads(response.content)
except JSONDecodeError:
    # 处理解析错误...

# ✅ 结构化输出：直接获得 Pydantic 对象
llm_with_schema = llm.with_structured_output(SemanticQuery)
result: SemanticQuery = llm_with_schema.invoke(prompt)
```

### 6.2 结构化输出的优势

1. **类型安全**：输出直接是 Pydantic 对象
2. **自动验证**：Schema 自动验证输出格式
3. **无需解析**：不需要手动解析 JSON
4. **减少错误**：消除格式错误和解析错误

### 6.3 为什么可以移除 PatchToolCallsMiddleware

```
PatchToolCallsMiddleware 的作用：
- 修复"悬空工具调用"（有 tool_call 但无对应 tool_result）

为什么结构化输出不需要：
- 结构化输出模式下，LLM 直接输出结构化数据
- 不会产生工具调用消息
- 因此不会有悬空工具调用问题
```

## 7. 中间件优化

### 7.1 保留的中间件（LangChain 内置，已实现）

| 中间件 | 来源 | 职责 |
|--------|------|------|
| TodoListMiddleware | LangChain | 任务队列管理 |
| SummarizationMiddleware | LangChain | 对话历史压缩（已配置） |
| ModelRetryMiddleware | LangChain | LLM 调用重试（已配置） |
| ToolRetryMiddleware | LangChain | 工具调用重试（已配置） |
| FilesystemMiddleware | 自定义 | 大文件缓存（已实现） |
| HumanInTheLoopMiddleware | LangChain | 人工确认（可选） |

### 7.2 移除的中间件

| 中间件 | 移除原因 |
|--------|---------|
| OutputValidationMiddleware | JSON 模式 + Pydantic 验证已处理 |
| PatchToolCallsMiddleware | JSON 模式不会产生悬空工具调用 |

### 7.3 关于 with_structured_output 的说明

```
注意：with_structured_output() 不支持流式输出！

当前项目使用的模式：
- JSON 模式：response_format={"type": "json_object"}
- Pydantic 验证：parse_json_response(response, Schema)
- 支持流式输出

示例：
response = await call_llm_with_tools(
    llm=self.llm,
    prompt=prompt,
    tools=[],
    response_format={"type": "json_object"},  # JSON 模式
)
result = parse_json_response(response, SemanticQuery)  # Pydantic 验证
```

### 7.4 现有中间件配置

```python
# tableau_assistant/src/orchestration/workflow/factory.py

from langchain.agents.middleware import (
    TodoListMiddleware,
    SummarizationMiddleware,
    ModelRetryMiddleware,
    ToolRetryMiddleware,
    HumanInTheLoopMiddleware,
)

# 已配置在 create_middleware_stack()
middleware = [
    TodoListMiddleware(),
    SummarizationMiddleware(
        model=summarization_model,
        trigger=("tokens", 60000),  # 60K tokens 触发摘要
        keep=("messages", 10),       # 保留最近 10 条消息
    ),
    ModelRetryMiddleware(
        max_retries=3,
        initial_delay=1.0,
        backoff_factor=2.0,  # 指数退避：1s, 2s, 4s
        jitter=True,
    ),
    ToolRetryMiddleware(
        max_retries=3,
        initial_delay=1.0,
        backoff_factor=2.0,
        jitter=True,
    ),
    FilesystemMiddleware(tool_token_limit_before_evict=20000),
]
```

## 8. 性能优化预期

### 8.1 LLM 调用次数

| 场景 | 当前 | 优化后 | 减少 |
|------|------|--------|------|
| 简单查询 + 5批数据 | 12 | 7 | 42% |
| 复杂查询 + 10批数据 | 23 | 12 | 48% |

### 8.2 Token 消耗

| 优化项 | 减少 |
|--------|------|
| RAG 候选字段（不传完整模型） | -70% |
| 对话历史压缩 | -50% |
| 减少 LLM 调用次数 | -50% |

### 8.3 响应时间

| 场景 | 当前 | 优化后 | 减少 |
|------|------|--------|------|
| 简单查询 | 24s | 14s | 42% |
| 复杂查询 | 46s | 24s | 48% |

## 9. 实现路径

### Phase 1: 中间件优化（P0）
1. 移除 OutputValidationMiddleware
2. 移除 PatchToolCallsMiddleware
3. 更新 `create_middleware_stack()` 函数
4. 更新测试用例

### Phase 2: SemanticParser 合并（P1）
1. 设计 UnifiedSemanticOutput Schema
2. 设计 UnifiedSemanticPrompt
3. 实现 UnifiedSemanticComponent
4. 集成 RAG 候选字段

### Phase 3: Insight 链式分析（P1）
1. 设计 ChainAnalyzerOutput Schema
2. 设计 ChainAnalyzerPrompt
3. 实现 ChainAnalyzer
4. 集成数据缓冲
