# DeepAgents 重构方案 - 重要修正

本文档记录了在讨论过程中发现的问题和相应的修正。

## 📝 修正清单

### 1. ❌ 删除 InsightGenerationMiddleware

**问题**: 最初设计中包含了 `InsightGenerationMiddleware`，但这是错误的。

**原因**: 
- 洞察生成是一个业务任务，应该由子代理完成
- 中间件用于扩展基础能力（如文件管理、元数据注入），不是执行业务任务

**修正**:
```python
# ❌ 错误
middleware=[
    TableauMetadataMiddleware(),
    VizQLQueryMiddleware(),
    InsightGenerationMiddleware()  # 不需要
]

# ✅ 正确
middleware=[
    TableauMetadataMiddleware(),
    VizQLQueryMiddleware()
]

# 洞察生成应该是子代理
subagents=[
    understanding_agent,
    planning_agent,
    insight_agent,  # ✅ 作为子代理
    replanner_agent
]
```

---

### 2. ✅ 修正执行流程

**问题**: 最初的执行流程示例不准确，没有体现 Understanding Agent 的问题分解功能。

**修正后的流程**:

```
用户: "2016年各地区的销售额"
  ↓
主 Agent 调用 task(understanding-agent)
  ↓
Understanding Agent 执行:
  - 分析问题意图
  - 识别实体（地区、销售额）
  - 分解为子问题（如果需要）✅ 关键：问题分解在这里
  - 返回 QuestionUnderstanding（包含 sub_questions 列表）
  ↓
主 Agent 收到理解结果（包含 N 个 sub_questions）
  ↓
主 Agent 使用 write_todos 创建任务列表 ✅ 基于理解结果创建
  ↓
主 Agent 调用 task(planning-agent)
  ↓
Planning Agent 执行:
  - 为每个 sub_question 生成一个 subtask ✅ 一对一映射
  - 映射字段
  - 生成 Intent 模型
  - 返回 QueryPlanningResult（包含 N 个 subtasks）
  ↓
主 Agent 执行查询...
```

**关键点**:
- ✅ Understanding Agent 负责问题分解（生成 sub_questions）
- ✅ Planning Agent 为每个 sub_question 生成 subtask
- ✅ 主 Agent 使用 write_todos 管理整体工作流

---

### 3. ✅ 澄清上下文长度配置

**问题**: 文档中写死了 170k tokens，但这应该根据模型动态配置。

**修正**:

```python
# ❌ 错误：写死 170k
SummarizationMiddleware(
    model=model,
    max_tokens_before_summary=170000  # 不应该写死
)

# ✅ 正确：根据模型配置
MODEL_CONTEXT_LIMITS = {
    "claude-sonnet-4-5": 200000,
    "claude-sonnet-4": 200000,
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "deepseek-chat": 64000,
}

context_limit = MODEL_CONTEXT_LIMITS.get(model_name, 128000)
summary_threshold = int(context_limit * 0.85)  # 85% 作为阈值

SummarizationMiddleware(
    model=model,
    max_tokens_before_summary=summary_threshold  # ✅ 动态配置
)
```

**说明**:
- 170k 是 DeepAgents 针对 Claude 的默认值
- 应该根据实际使用的模型动态调整
- 建议使用上下文限制的 85% 作为总结阈值

---

### 4. ✅ 澄清两种任务规划的区别

**问题**: DeepAgent 的任务规划和项目的任务规划容易混淆。

**澄清**:

| 维度 | DeepAgent 任务规划 | 项目任务规划 |
|------|-------------------|-------------|
| **层次** | 基础设施层 | 业务层 |
| **粒度** | 粗粒度（5-10个任务） | 细粒度（N个子任务） |
| **内容** | 工作流步骤 | VizQL 查询配置 |
| **生成者** | 主 Agent | Planning Agent |
| **用途** | 进度跟踪 | 查询执行 |
| **可见性** | 用户可见 | 内部使用 |

**示例**:

```python
# DeepAgent 任务规划（高层工作流）
write_todos([
    "理解问题",
    "生成查询计划",
    "执行查询",
    "分析结果",
    "生成报告"
])

# 项目任务规划（详细的 VizQL 配置）
QueryPlanningResult(
    subtasks=[
        QuerySubTask(
            question_id="q1",
            dimension_intents=[...],
            measure_intents=[...],
            # ... 详细的 VizQL 配置
        )
    ]
)
```

**关系**: 两者是互补的，不是替代关系
- DeepAgent 管理高层工作流
- 项目任务规划提供详细的查询配置

---

### 5. ✅ 补充重规划 Agent

**问题**: 最初的架构图中遗漏了重规划 Agent。

**修正**:

```python
# ✅ 完整的子代理列表（4个）
subagents = [
    understanding_agent,   # 问题理解和分解
    planning_agent,        # 查询规划
    insight_agent,         # 洞察生成
    replanner_agent        # ✅ 重规划评估
]
```

**重规划流程**:

```
主 Agent 执行查询
  ↓
主 Agent: task(insight-agent) → 分析结果
  ↓
主 Agent: task(replanner-agent) → 评估是否需要重规划
  ↓
Replanner Agent 返回 ReplanDecision:
  - need_replan: true/false
  - reason: "需要更详细的维度分解"
  - additional_queries: [...]
  ↓
如果 need_replan = true:
  ├─ 生成新的查询计划
  ├─ 执行新查询
  ├─ 分析新结果
  └─ 再次评估（最多 2-3 轮）
  
如果 need_replan = false:
  └─ 生成最终报告
```

---

### 6. ✅ 升级字段映射方案

**问题**: 最初使用简单的字符串匹配，不够智能。

**修正**: 采用 **RAG + LLM 语义理解** 方案

#### 方案对比

| 方案 | 准确度 | 速度 | 成本 | 推荐度 |
|------|--------|------|------|--------|
| 字符串匹配 ❌ | ⭐⭐ | ⭐⭐⭐⭐⭐ | $ | ⭐⭐ |
| **RAG + LLM** ✅ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | $$$ | ⭐⭐⭐⭐⭐ |

#### 新方案架构

```
用户输入："销售额"
  ↓
1. 向量检索（RAG）
  ├─ 将"销售额"转换为向量
  ├─ 在字段向量库中检索 Top-K 相似字段
  └─ 返回候选：["Sales", "Revenue", "Total Sales"]
  ↓
2. LLM 语义判断
  ├─ 输入：用户问题 + 候选字段 + 字段描述
  ├─ LLM 理解上下文和业务语义
  └─ 返回：最佳匹配 + 置信度 + 理由
  ↓
3. 结果
  {
    "matched_field": "Sales",
    "confidence": 0.95,
    "reasoning": "根据上下文，用户询问的是销售金额"
  }
```

#### 优势

- ✅ 理解业务语义（"销售额" vs "销售数量"）
- ✅ 考虑上下文（"去年的销售额" vs "今年的销售额"）
- ✅ 处理同义词（"收入" = "营收" = "销售额"）
- ✅ 处理多语言（"Sales" = "销售额"）
- ✅ 向量库持久化，避免重复构建

#### 工具更新

```python
# ❌ 旧工具：简单字符串匹配
@tool
def map_fields(user_input: str, metadata: Dict) -> Dict:
    """使用字符串相似度匹配"""
    pass

# ✅ 新工具：RAG + LLM 语义理解
@tool
async def semantic_map_fields(
    user_input: str,
    question_context: str,
    metadata: Dict
) -> Dict:
    """
    使用 RAG + LLM 进行语义映射
    
    1. 向量检索候选字段
    2. LLM 理解上下文选择最佳匹配
    """
    pass
```

---

## 📊 更新后的完整架构

```
DeepAgent (主编排器)
├─ 内置中间件
│   ├─ TodoListMiddleware (高层任务管理)
│   ├─ FilesystemMiddleware (文件管理)
│   ├─ SubAgentMiddleware (子代理委托)
│   ├─ SummarizationMiddleware (自动总结，阈值可配置)
│   └─ AnthropicPromptCachingMiddleware (缓存)
├─ 自定义中间件（2个）
│   ├─ TableauMetadataMiddleware
│   └─ VizQLQueryMiddleware
├─ 子代理（4个）
│   ├─ understanding-agent (问题理解和分解)
│   ├─ planning-agent (查询规划)
│   ├─ insight-agent (洞察生成)
│   └─ replanner-agent (重规划评估)
└─ 工具
    ├─ vizql_query
    ├─ get_metadata
    ├─ semantic_map_fields (RAG + LLM)
    └─ parse_date
```

---

## ✅ 修正总结

1. **删除** InsightGenerationMiddleware（洞察生成应该是子代理）
2. **修正** 执行流程（Understanding Agent 负责问题分解）
3. **澄清** 上下文长度配置（应根据模型动态调整）
4. **澄清** 两种任务规划的区别（基础设施层 vs 业务层）
5. **补充** 重规划 Agent（4个子代理，不是3个）
6. **升级** 字段映射方案（从字符串匹配升级到 RAG + LLM）

---

## 📅 下一步

明天开始重构时，将按照这些修正后的设计实施：

1. ✅ 只创建 2 个自定义中间件
2. ✅ 创建 4 个子代理（包含 replanner）
3. ✅ 实现 RAG + LLM 语义字段映射
4. ✅ 根据模型动态配置总结阈值
5. ✅ 正确实现两层任务规划

所有相关文档已更新！🎉
