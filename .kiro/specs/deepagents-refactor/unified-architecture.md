# 统一架构：DeepAgent 框架 + VizQL 模型

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    DeepAgent 框架                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  create_deep_agent()                                 │  │
│  │  ├── state_schema: VizQLState ⭐                     │  │
│  │  ├── context: VizQLContext ⭐                        │  │
│  │  ├── subagents: [boost, understanding, ...]         │  │
│  │  ├── middleware: [Metadata, Cache, ...]             │  │
│  │  └── tools: [get_metadata, execute_query, ...]      │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                    VizQL 数据模型                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  VizQLContext (context.py)                           │  │
│  │  - datasource_luid, user_id, session_id             │  │
│  │  - max_replan_rounds, parallel_upper_limit          │  │
│  │  - 所有运行时配置                                    │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  VizQLState (state.py)                               │  │
│  │  - question, boosted_question                        │  │
│  │  - boost: QuestionBoost (Pydantic) ⭐                │  │
│  │  - understanding: QuestionUnderstanding (Pydantic) ⭐│  │
│  │  - query_plan: QueryPlanningResult (Pydantic) ⭐     │  │
│  │  - 所有工作流状态                                    │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## 核心决策

### 决策：使用统一的 VizQL 模型

**不创建** DeepAgentContext/State，**直接使用** VizQLContext/State

### 理由

1. **框架与模型分离**
   ```
   DeepAgent 框架 = 提供子代理、中间件、工具等特性
   数据模型 = 只是数据容器（TypedDict）
   
   框架不要求特定的数据模型！
   ```

2. **VizQL 模型的优势**
   - ✅ Pydantic 类型安全
   - ✅ 生产环境验证
   - ✅ 完整的业务字段
   - ✅ 与现有系统一致

3. **避免重复**
   - ❌ 不需要维护两套模型
   - ❌ 不需要模型转换
   - ❌ 不需要最终"选择"

## 实现示例

### 1. 创建 DeepAgent

```python
from deepagents import create_deep_agent
from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.src.models.state import VizQLState

# 创建 Agent（使用 VizQL 模型）
agent = create_deep_agent(
    name="tableau-assistant",
    model="claude-3-5-sonnet-20241022",
    
    # ⭐ 使用 VizQL State
    state_schema=VizQLState,
    
    # ⭐ 子代理（框架特性）
    subagents=[
        boost_agent,
        understanding_agent,
        planning_agent,
        insight_agent,
        replanner_agent
    ],
    
    # ⭐ 中间件（框架特性）
    middleware=[
        TableauMetadataMiddleware(),
        VizQLQueryMiddleware(),
        ApplicationLevelCacheMiddleware()
    ],
    
    # ⭐ 工具（框架特性）
    tools=[
        "get_metadata",
        "execute_vizql_query",
        "process_query_result",
        "detect_statistics",
        "save_large_result"
    ]
)
```

### 2. 创建 Runtime

```python
from langgraph.runtime import Runtime

# 创建 Context
context = VizQLContext.from_config(
    datasource_luid="abc123",
    user_id="user_456",
    session_id="session_789"
)

# 创建 Runtime（使用 VizQL Context）
runtime = Runtime[VizQLContext](
    context=context,
    store=store
)
```

### 3. 子代理实现

```python
from tableau_assistant.src.deepagents.subagents.base import BaseSubAgent
from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.src.models.state import VizQLState
from tableau_assistant.src.models.boost import QuestionBoost

class BoostAgent(BaseSubAgent):
    """问题优化子代理"""
    
    async def execute(
        self,
        state: VizQLState,  # ⭐ VizQL State
        runtime: Runtime[VizQLContext],  # ⭐ VizQL Context
        **kwargs
    ) -> Dict[str, Any]:
        # 访问 Context
        datasource_luid = runtime.context.datasource_luid
        max_replan = runtime.context.max_replan_rounds
        
        # 访问 State
        question = state["question"]
        
        # 执行逻辑...
        result: QuestionBoost = await self._execute_with_prompt(...)
        
        # 返回 Pydantic 模型
        return {
            "boost": result,  # ⭐ Pydantic 对象
            "boosted_question": result.boosted_question
        }
```

## 类型安全

### Pydantic 模型的优势

```python
# ✅ 编译时类型检查
boost: QuestionBoost = state["boost"]
print(boost.boosted_question)  # IDE 自动补全
print(boost.confidence)  # IDE 自动补全

# ✅ 运行时验证
boost = QuestionBoost(
    is_data_analysis_question=True,
    original_question="销售额",
    boosted_question="2024年各地区的销售额总和",
    changes=["添加时间范围", "添加维度"],
    reasoning="补充缺失信息",
    confidence=0.95
)  # 自动验证所有字段

# ❌ 如果用 Dict（DeepAgent 模型的方式）
boost: Dict[str, Any] = state["boost"]
print(boost["boosted_question"])  # 无类型检查
print(boost["confidance"])  # 拼写错误，运行时才发现！
```

## 架构优势

### 1. 统一性

```python
# ✅ 所有组件使用相同的模型
class BoostAgent(BaseSubAgent):
    async def execute(self, state: VizQLState, ...):
        ...

class UnderstandingAgent(BaseSubAgent):
    async def execute(self, state: VizQLState, ...):
        ...

class PlanningAgent(BaseSubAgent):
    async def execute(self, state: VizQLState, ...):
        ...
```

### 2. 类型安全

```python
# ✅ IDE 自动补全
state["boost"].  # 提示所有 QuestionBoost 字段
state["understanding"].  # 提示所有 QuestionUnderstanding 字段
state["query_plan"].  # 提示所有 QueryPlanningResult 字段
```

### 3. 可维护性

```python
# ✅ 修改一次，全局生效
# 在 QuestionBoost 模型中添加新字段
class QuestionBoost(BaseModel):
    # ... 现有字段
    new_field: str  # 新字段

# 所有使用 QuestionBoost 的地方自动获得类型检查
```

### 4. 与现有系统一致

```python
# ✅ 现有的 Agent 和新的 SubAgent 使用相同的模型
# 降低迁移风险
# 便于对比测试
```

## 对比：如果用两套模型

### 问题

```python
# ❌ 需要维护两套模型
VizQLState vs DeepAgentState
VizQLContext vs DeepAgentContext

# ❌ 需要模型转换
def convert_vizql_to_deepagent(vizql_state: VizQLState) -> DeepAgentState:
    return DeepAgentState(
        question=vizql_state["question"],
        boosted_question=vizql_state["boosted_question"],
        # ... 转换所有字段
    )

# ❌ 类型不一致
VizQLState: boost: QuestionBoost (Pydantic)
DeepAgentState: boosted_question: str (Dict)

# ❌ 最终还是要选择一套
```

## 总结

### 最终架构

```
DeepAgent 框架（提供特性）
    ↓
VizQL 模型（数据容器）
    ↓
Pydantic 模型（类型安全）
```

### 核心原则

1. **框架 ≠ 数据模型**：框架提供特性，模型只是容器
2. **类型安全优先**：Pydantic > Dict
3. **避免重复**：一套模型就够了
4. **保持一致性**：与现有系统对齐

### 已完成

- ✅ 删除 DeepAgentContext.py
- ✅ 删除 DeepAgentState.py
- ✅ 确认使用 VizQLContext/State
- ✅ 实现 BoostAgent（使用 VizQL 模型）
- ✅ 更新所有文档

### 下一步

- ⏳ 实现其他子代理（understanding, planning, insight, replanner）
- ⏳ 所有子代理都使用 VizQLContext/State
- ⏳ 保持 Pydantic 类型安全
