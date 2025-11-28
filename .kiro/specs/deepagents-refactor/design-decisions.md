# DeepAgents 重构 - 关键设计决策

## 决策1: 使用 VizQLContext 和 VizQLState

### 问题
DeepAgents 有自己的 Runtime 和 State 管理，是否还需要使用原系统的 VizQLContext 和 VizQLState？

### 决策
**保留并使用 VizQLContext 和 VizQLState**

### 理由

#### 1. VizQLContext 的价值
```python
@dataclass
class VizQLContext:
    datasource_luid: str
    user_id: str
    session_id: str
    max_replan_rounds: int
    parallel_upper_limit: int
    max_retry_times: int
    max_subtasks_per_round: int
```

**作用**：
- 包含不可变的运行时配置
- 从配置文件读取的系统参数
- 跨所有节点共享的上下文信息

**与 DeepAgents Runtime 的关系**：
- VizQLContext 作为 DeepAgents Runtime 的 context
- 通过 `runtime.context` 访问
- 不在 State 中传递，避免重复

#### 2. VizQLState 的价值
```python
class VizQLState(TypedDict):
    question: str
    boosted_question: Optional[str]
    understanding: Optional[QuestionUnderstanding]
    query_plan: Optional[QueryPlanningResult]
    insights: Annotated[List[Dict[str, Any]], operator.add]
    # ... 更多字段
```

**作用**：
- 定义完整的工作流状态
- 使用 TypedDict 提供类型检查
- 使用 Annotated + operator.add 实现自动累积
- 包含所有 Agent 的输出

**与 DeepAgents State 的关系**：
- VizQLState 作为 DeepAgents 的 state_schema
- 提供类型安全和自动补全
- 保持与原系统的一致性

### 实现方式

```python
# 子代理基类
class BaseSubAgent(ABC):
    async def execute(
        self,
        state: "VizQLState",  # ⭐ 使用 VizQLState
        runtime: "Runtime[VizQLContext]",  # ⭐ 使用 VizQLContext
        user_config: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        # ...
```

```python
# 具体子代理
class BoostAgent(BaseSubAgent):
    async def _execute_with_prompt(
        self,
        state: "VizQLState",  # ⭐ 类型安全
        runtime: "Runtime[VizQLContext]",  # ⭐ 类型安全
        input_data: Dict[str, Any],
        config: Dict[str, Any]
    ) -> QuestionBoost:
        # 可以访问 runtime.context.datasource_luid
        # 可以访问 state["question"]
        # ...
```

### 优势

1. **类型安全**：TypedDict 提供编译时类型检查
2. **代码补全**：IDE 可以自动补全字段
3. **一致性**：与原系统保持一致，降低迁移成本
4. **可维护性**：清晰的状态定义，易于理解和修改
5. **可扩展性**：可以轻松添加新字段

---

## 决策2: 传递完整元数据，不截断

### 问题
元数据可能包含几十甚至上百个字段，是否应该只传递前N个字段以节省 Token？

### 决策
**传递完整元数据，不截断任何字段**

### 理由

#### 1. 信息完整性
```python
# ❌ 错误做法：截断元数据
for dim in dimensions[:10]:  # 只传前10个
    parts.append(f"  - {dim.get('name')}")

if len(dimensions) > 10:
    parts.append(f"  ... 还有 {len(dimensions) - 10} 个维度")
```

**问题**：
- 用户问"某个字段"，但这个字段在后40个中
- LLM 无法看到这个字段，导致映射失败
- 后续的 planning-agent 会看到完整元数据，造成不一致

```python
# ✅ 正确做法：传递所有字段
for dim in dimensions:  # 传递所有
    field_info = f"  - {dim.get('name')} ({dim.get('data_type')})"
    if dim.get('description'):
        field_info += f" - {dim.get('description')}"
    parts.append(field_info)
```

#### 2. Prompt Caching 的价值
```
元数据特点：
- 固定不变（除非数据源更新）
- 所有查询都使用相同的元数据
- 非常适合 Prompt Caching

使用 Anthropic Prompt Caching：
- 第一次调用：传递完整元数据（假设 5000 tokens）
- 后续调用：缓存命中，只计费 10% tokens（500 tokens）
- 节省 90% 成本！

如果截断元数据：
- 节省了 2000 tokens（假设）
- 但失去了缓存的价值
- 导致信息不完整
```

#### 3. 实际 Token 消耗分析
```
假设数据源有 50 个字段：
- 每个字段平均 50 tokens（名称+类型+描述）
- 总计：50 * 50 = 2500 tokens

使用 Prompt Caching：
- 第一次：2500 tokens（全价）
- 第 2-10 次：250 tokens（缓存价格）
- 平均：(2500 + 9*250) / 10 = 475 tokens

如果截断到 10 个字段：
- 每次：10 * 50 = 500 tokens
- 无法使用缓存
- 平均：500 tokens

结论：完整元数据 + Prompt Caching 更划算！
```

#### 4. 智能格式化策略
```python
def _format_metadata(self, metadata: Dict[str, Any]) -> str:
    """
    智能格式化元数据
    
    策略：
    1. 传递所有字段（不截断）
    2. 包含字段名、类型、描述
    3. 如果有维度层级，也包含进来
    4. 使用 Prompt Caching 缓存元数据
    """
    parts = []
    
    # 数据源信息
    parts.append(f"数据源: {datasource_name}")
    
    # 所有维度（不截断）
    parts.append(f"\n维度字段 ({len(dimensions)}个):")
    for dim in dimensions:  # ⭐ 所有维度
        field_info = f"  - {dim['name']} ({dim['data_type']})"
        if dim.get('description'):
            field_info += f" - {dim['description']}"
        parts.append(field_info)
    
    # 所有度量（不截断）
    parts.append(f"\n度量字段 ({len(measures)}个):")
    for measure in measures:  # ⭐ 所有度量
        field_info = f"  - {measure['name']} ({measure['data_type']})"
        if measure.get('description'):
            field_info += f" - {measure['description']}"
        parts.append(field_info)
    
    # 维度层级（如果有）
    if metadata.get("dimension_hierarchy"):
        parts.append("\n维度层级:")
        for category, dims in metadata["dimension_hierarchy"].items():
            parts.append(f"  {category}: {', '.join(dims)}")
    
    return "\n".join(parts)
```

### 实现要点

1. **所有子代理都应该传递完整元数据**
   - boost-agent: 需要看到所有字段以优化问题
   - planning-agent: 需要看到所有字段以生成查询计划
   - replanner-agent: 需要看到所有字段以重新规划

2. **使用 Prompt Caching**
   - 元数据放在系统提示词的前面
   - 使用 AnthropicPromptCachingMiddleware
   - 节省 50-90% 成本

3. **监控 Token 使用**
   - 记录每次调用的 Token 消耗
   - 监控缓存命中率
   - 验证成本节省效果

### 性能对比

| 方案 | 第1次 Token | 第2-10次 Token | 平均 Token | 信息完整性 |
|------|------------|---------------|-----------|----------|
| 截断到10个字段 | 500 | 500 | 500 | ❌ 不完整 |
| 完整元数据（无缓存） | 2500 | 2500 | 2500 | ✅ 完整 |
| 完整元数据（有缓存） | 2500 | 250 | 475 | ✅ 完整 |

**结论**：完整元数据 + Prompt Caching 是最优方案！

---

## 决策3: 子代理的工具分配

### 问题
哪些工具应该分配给哪些子代理？

### 决策

| 工具 | 主 Agent | boost | understanding | planning | insight | replanner |
|------|---------|-------|---------------|----------|---------|-----------|
| get_metadata | ✅ | ✅ | ❌ | ✅ | ❌ | ✅ |
| semantic_map_fields | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| parse_date | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| build_vizql_query | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| execute_vizql_query | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| process_query_result | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| detect_statistics | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| save_large_result | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

### 理由

1. **boost-agent**
   - 需要 get_metadata: 查看可用字段以优化问题
   - 不需要其他工具：只做问题优化，不执行查询

2. **understanding-agent**
   - 不需要工具：纯理解任务，不需要外部数据

3. **planning-agent**
   - 需要 get_metadata: 查看可用字段
   - 需要 semantic_map_fields: 映射业务术语到技术字段
   - 需要 parse_date: 解析日期范围
   - 需要 build_vizql_query: 构建查询

4. **insight-agent**
   - 需要 detect_statistics: 统计分析辅助洞察生成

5. **replanner-agent**
   - 需要 get_metadata: 查看可用字段以生成新问题

6. **主 Agent**
   - 负责执行和数据管理
   - execute_vizql_query: 执行查询
   - process_query_result: 处理结果
   - save_large_result: 保存大结果

---

## 总结

这些设计决策的核心原则：

1. **保持一致性**：使用 VizQLContext 和 VizQLState 与原系统保持一致
2. **信息完整性**：传递完整元数据，不截断
3. **成本优化**：使用 Prompt Caching 节省成本
4. **职责分离**：清晰的工具分配，避免混淆
5. **类型安全**：使用 TypedDict 提供类型检查

这些决策确保了系统的：
- ✅ 正确性（信息完整）
- ✅ 性能（Prompt Caching）
- ✅ 可维护性（类型安全）
- ✅ 一致性（与原系统对齐）


---

## 更新：统一数据模型决策（2025-01-15）

### 最终决策

**使用统一的 VizQLContext/State 模型**

经过深入讨论和分析，我们决定：
- ✅ 使用 **VizQLContext** 和 **VizQLState**
- ❌ 删除 DeepAgentContext 和 DeepAgentState
- ✅ 保持 Pydantic 模型的类型安全
- ✅ 与现有系统保持一致

### 关键发现

**子代理和中间件支持来自框架，不是数据模型！**

```python
# DeepAgent 框架可以使用任何 TypedDict 作为 State
agent = create_deep_agent(
    state_schema=VizQLState,  # ✅ 完全支持
    subagents=[...],  # ⭐ 框架特性
    middleware=[...],  # ⭐ 框架特性
)

# Runtime 可以使用任何类型作为 Context
runtime = Runtime[VizQLContext](...)  # ✅ 完全支持
```

### 为什么删除 DeepAgentContext/State？

1. **不必要的重复**
   - DeepAgent 框架不要求特定模型
   - VizQL 模型已经满足所有需求
   - 维护两套模型增加复杂度

2. **VizQL 模型的优势**
   - ✅ Pydantic 类型安全
   - ✅ 生产环境验证
   - ✅ 完整的业务字段
   - ✅ 与现有系统一致

3. **避免混淆**
   - 只有一套模型系统
   - 清晰的架构
   - 降低学习成本

### 修正后的架构

```
DeepAgent 框架
├── 使用 VizQLContext（Runtime Context）
├── 使用 VizQLState（State Schema）
├── 使用 Pydantic 模型（QuestionBoost, QuestionUnderstanding 等）
├── 子代理系统（框架特性）
├── 中间件系统（框架特性）
└── 工具系统（框架特性）
```

### 已完成的工作

- ✅ 删除 `deepagent_context.py`
- ✅ 删除 `deepagent_state.py`
- ✅ 更新 `README_MODELS.md`
- ✅ 更新设计决策文档
- ✅ 确认 BoostAgent 使用 VizQL 模型

### 核心原则

1. **框架 ≠ 数据模型**：框架提供特性，模型只是数据容器
2. **类型安全优先**：Pydantic > Dict
3. **避免重复**：一套模型就够了
4. **保持一致性**：与现有系统对齐
