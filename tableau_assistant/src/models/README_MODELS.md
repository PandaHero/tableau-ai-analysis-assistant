# 数据模型说明

## 模型架构

本项目使用统一的数据模型系统，适用于 DeepAgent 框架。

### VizQL 模型（统一模型）

**文件位置**：
- `context.py` - VizQLContext
- `state.py` - VizQLState

**用途**：
- 用于 DeepAgent 框架的所有子代理和工作流
- 基于 LangGraph 1.0 的 state_schema 和 context_schema
- 包含完整的 VizQL 查询执行流程
- 支持 DeepAgent 的所有特性（子代理、中间件、工具）

**特点**：
- ✅ 使用 TypedDict 定义状态（与 DeepAgent 完全兼容）
- ✅ 使用 dataclass 定义上下文（与 DeepAgent 完全兼容）
- ✅ 使用 Pydantic 模型保证类型安全
- ✅ 与现有的 Tableau VizQL 系统紧密集成
- ✅ 支持 DeepAgent 的子代理系统
- ✅ 支持 DeepAgent 的中间件系统
- ✅ 支持 DeepAgent 的工具系统

## 关键澄清：框架 vs 数据模型

**重要**：子代理和中间件支持来自于**框架**，不是来自于**数据模型**！

```python
# DeepAgent 框架提供子代理和中间件支持
from deepagents import create_deep_agent

agent = create_deep_agent(
    # ⭐ 框架特性：子代理
    subagents=[boost_agent, planning_agent],
    
    # ⭐ 框架特性：中间件
    middleware=[TableauMetadataMiddleware()],
    
    # ⭐ 数据模型：可以是任何 TypedDict
    state_schema=VizQLState,  # ✅ 完全支持！
    
    # ⭐ Runtime Context：可以是任何类型
    context=VizQLContext  # ✅ 完全支持！
)
```

### 为什么只用一套模型？

1. **DeepAgent 不要求特定模型**
   - DeepAgent 框架可以使用任何 TypedDict 作为 State
   - DeepAgent 框架可以使用任何类型作为 Context
   - 不需要创建专门的 DeepAgent 模型

2. **VizQL 模型的优势**
   - ✅ 使用 Pydantic 模型（强类型安全）
   - ✅ 已在生产环境验证
   - ✅ 包含完整的业务字段
   - ✅ 与现有系统完全一致

3. **避免重复**
   - ❌ 不需要维护两套几乎相同的模型
   - ❌ 不需要在两套模型间转换
   - ❌ 不需要最终"选择"哪套模型

### 模型特性

| 特性 | VizQLContext/State |
|------|-------------------|
| **框架兼容性** | ✅ LangGraph + DeepAgent |
| **子代理支持** | ✅（通过 DeepAgent 框架） |
| **中间件支持** | ✅（通过 DeepAgent 框架） |
| **工具系统** | ✅（通过 DeepAgent 框架） |
| **数据类型** | Pydantic 模型 |
| **类型安全** | ✅ 强类型 |
| **字段数量** | 20+（完整） |
| **生产验证** | ✅ 已验证 |
| **状态管理** | TypedDict |
| **上下文管理** | dataclass |

## 使用指南

### 在 DeepAgent 框架中使用 VizQL 模型

```python
from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.src.models.state import VizQLState, create_initial_state
from deepagents import create_deep_agent

# 1. 创建上下文
context = VizQLContext.from_config(
    datasource_luid="abc123",
    user_id="user_456",
    session_id="session_789"  # 或 thread_id
)

# 2. 创建状态
state = create_initial_state(
    question="2024年各地区的销售额是多少？",
    boost_question=False
)

# 3. 创建 DeepAgent（使用 VizQL 模型）
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
        "process_query_result"
    ]
)

# 4. 创建 Runtime（使用 VizQL Context）
from langgraph.runtime import Runtime

runtime = Runtime[VizQLContext](
    context=context,
    store=store
)

# 5. 执行
result = await agent.execute(
    state=state,
    runtime=runtime
)
```

### 在子代理中使用 VizQL 模型

```python
from tableau_assistant.src.deepagents.subagents.base import BaseSubAgent
from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.src.models.state import VizQLState
from tableau_assistant.src.models.boost import QuestionBoost

class BoostAgent(BaseSubAgent):
    async def execute(
        self,
        state: VizQLState,  # ⭐ 使用 VizQL State
        runtime: Runtime[VizQLContext],  # ⭐ 使用 VizQL Context
        **kwargs
    ) -> Dict[str, Any]:
        # 访问 Context
        datasource_luid = runtime.context.datasource_luid
        
        # 访问 State
        question = state["question"]
        
        # 返回 Pydantic 模型
        result: QuestionBoost = ...
        
        return {
            "boost": result,  # ⭐ Pydantic 对象
            "boosted_question": result.boosted_question
        }
```

## 架构优势

### 统一模型的好处

1. **类型安全**
   ```python
   # ✅ 编译时类型检查
   boost: QuestionBoost = state["boost"]
   understanding: QuestionUnderstanding = state["understanding"]
   ```

2. **IDE 支持**
   ```python
   # ✅ 自动补全
   state["boost"].  # IDE 会提示所有字段
   ```

3. **一致性**
   ```python
   # ✅ 所有子代理使用相同的模型
   # ✅ 所有中间件使用相同的模型
   # ✅ 所有工具使用相同的模型
   ```

4. **维护性**
   ```python
   # ✅ 只需要维护一套模型
   # ✅ 修改一次，全局生效
   ```

## 迁移完成

### 当前状态
- ✅ 统一使用 VizQLContext/State
- ✅ 支持 DeepAgent 所有特性
- ✅ 保持 Pydantic 类型安全
- ✅ 与现有系统完全一致

### 已删除
- ❌ DeepAgentContext（不需要）
- ❌ DeepAgentState（不需要）

### 原因
- DeepAgent 框架不要求特定模型
- VizQL 模型已经满足所有需求
- 避免维护两套重复的模型

## 注意事项

1. **统一使用 VizQL 模型**：所有代码都使用 VizQLContext/State
2. **类型安全**：充分利用 Pydantic 模型的类型检查
3. **测试覆盖**：确保所有测试使用 VizQL 模型
4. **文档同步**：修改模型时同步更新文档

## 相关文件

- `question.py` - 问题理解相关模型（两套系统共用）
- `query_plan.py` - 查询规划相关模型（两套系统共用）
- `result.py` - 结果相关模型（两套系统共用）
- `insight_result.py` - 洞察结果模型（两套系统共用）
