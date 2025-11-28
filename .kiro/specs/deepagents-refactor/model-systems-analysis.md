# 数据模型系统分析：VizQL vs DeepAgent

## 问题

项目中存在两套并行的数据模型系统：
1. **VizQL 系统**：`VizQLContext` + `VizQLState`
2. **DeepAgent 系统**：`DeepAgentContext` + `DeepAgentState`

需要明确：
- 这两套系统的区别是什么？
- 应该使用哪一套？
- 如何避免混淆？

---

## 详细对比

### 1. Context 对比

#### VizQLContext (context.py)
```python
@dataclass
class VizQLContext:
    """VizQL运行时上下文 - 用于 LangGraph 工作流"""
    datasource_luid: str
    user_id: str
    session_id: str  # ⭐ 注意：叫 session_id
    max_replan_rounds: int
    parallel_upper_limit: int
    max_retry_times: int
    max_subtasks_per_round: int
    
    # 注意：tableau_token 等通过 StoreManager 管理，不在这里
```

**特点**：
- 为 **LangGraph 原生工作流** 设计
- 使用 `session_id`（LangGraph 术语）
- 不包含 tableau_token（通过 Store 管理）
- 包含详细的业务配置（parallel_upper_limit, max_subtasks_per_round）
- 从配置文件读取默认值

#### DeepAgentContext (deepagent_context.py)
```python
@dataclass(frozen=True)
class DeepAgentContext:
    """运行时上下文 - 用于 DeepAgent 框架"""
    datasource_luid: str
    user_id: str
    thread_id: str  # ⭐ 注意：叫 thread_id
    tableau_token: str  # ⭐ 直接包含 token
    
    max_replan: int = 3
    enable_boost: bool = False
    enable_cache: bool = True
    model_config: Optional[Dict[str, Any]] = None
    
    # 性能配置
    timeout: int = 300
    max_tokens_per_call: int = 4000
    temperature: float = 0.0
    
    # 缓存配置
    cache_ttl: int = 3600
    enable_prompt_cache: bool = True
    enable_query_cache: bool = True
```

**特点**：
- 为 **DeepAgent 框架** 设计
- 使用 `thread_id`（DeepAgent 术语）
- 直接包含 tableau_token
- 包含更多性能和缓存配置
- 使用 frozen=True（不可变）

### 2. State 对比

#### VizQLState (state.py)
```python
class VizQLState(TypedDict):
    """VizQL workflow state - 用于 LangGraph 工作流"""
    
    # 用户输入
    question: str
    boosted_question: Optional[str]
    
    # Agent 输出（使用 Pydantic 模型）
    boost: Optional[QuestionBoost]  # ⭐ Pydantic 对象
    understanding: Optional[QuestionUnderstanding]  # ⭐ Pydantic 对象
    query_plan: Optional[QueryPlanningResult]  # ⭐ Pydantic 对象
    
    # 累积列表
    subtask_results: Annotated[List[Dict[str, Any]], operator.add]
    all_query_results: Annotated[List[Dict[str, Any]], operator.add]
    insights: Annotated[List[Dict[str, Any]], operator.add]
    all_insights: Annotated[List[Dict[str, Any]], operator.add]
    
    # 更多字段...
    metadata: Optional[Dict[str, Any]]
    dimension_hierarchy: Optional[Dict[str, Any]]
    statistics: Optional[Dict[str, Any]]
    errors: Annotated[List[Dict[str, Any]], operator.add]
    warnings: Annotated[List[Dict[str, Any]], operator.add]
    performance: Optional[Dict[str, Any]]
    visualizations: Annotated[List[Dict[str, Any]], operator.add]
```

**特点**：
- 为 **LangGraph 原生工作流** 设计
- 使用 **Pydantic 模型**（QuestionBoost, QuestionUnderstanding 等）
- 非常详细和完整（包含 metadata, hierarchy, statistics, errors, warnings 等）
- 适合复杂的多轮分析流程

#### DeepAgentState (deepagent_state.py)
```python
class DeepAgentState(TypedDict):
    """DeepAgent 主状态定义 - 用于 DeepAgent 框架"""
    
    # 用户输入
    question: str
    boost_question: bool
    
    # Agent 输出（使用 Dict）
    boosted_question: Optional[str]
    understanding: Optional[Dict[str, Any]]  # ⭐ Dict，不是 Pydantic
    query_plan: Optional[Dict[str, Any]]  # ⭐ Dict，不是 Pydantic
    
    # 累积列表
    query_results: Annotated[List[Dict[str, Any]], operator.add]
    insights: Annotated[List[Dict[str, Any]], operator.add]
    
    # 控制流程
    current_round: int
    max_rounds: int
    needs_replan: bool
    
    # 元数据（在 State 中，不在 Context 中）
    datasource_luid: str
    thread_id: str
    user_id: str
    
    # 性能监控
    start_time: float
    performance_metrics: Dict[str, Any]
```

**特点**：
- 为 **DeepAgent 框架** 设计
- 使用 **Dict**，不使用 Pydantic 模型
- 更简洁（字段较少）
- 元数据在 State 中（datasource_luid, thread_id, user_id）

---

## 核心区别总结

| 维度 | VizQL 系统 | DeepAgent 系统 |
|------|-----------|---------------|
| **设计目标** | LangGraph 原生工作流 | DeepAgent 框架 |
| **Context 命名** | session_id | thread_id |
| **Token 管理** | 通过 Store | 直接在 Context |
| **State 类型** | Pydantic 模型 | Dict |
| **State 复杂度** | 非常详细（20+字段） | 简洁（10+字段） |
| **元数据位置** | State 中 | State 中 |
| **适用场景** | 复杂多轮分析 | 简化的 Agent 流程 |

---

## 关键问题：应该使用哪一套？

### 分析

#### 选项1：使用 VizQL 系统
```python
class BoostAgent(BaseSubAgent):
    async def execute(
        self,
        state: VizQLState,
        runtime: Runtime[VizQLContext],
        ...
    ):
        # 访问 Pydantic 模型
        boost_result: QuestionBoost = ...
        state["boost"] = boost_result  # 存储 Pydantic 对象
```

**优点**：
- ✅ 使用 Pydantic 模型，类型安全
- ✅ 与现有系统完全一致
- ✅ 详细的状态管理
- ✅ 已经在生产环境验证

**缺点**：
- ❌ 不是为 DeepAgent 设计的
- ❌ 可能与 DeepAgent 的某些特性不兼容

#### 选项2：使用 DeepAgent 系统
```python
class BoostAgent(BaseSubAgent):
    async def execute(
        self,
        state: DeepAgentState,
        runtime: Runtime[DeepAgentContext],
        ...
    ):
        # 使用 Dict
        boost_result = {
            "boosted_question": "...",
            "confidence": 0.95
        }
        state["boosted_question"] = boost_result["boosted_question"]
```

**优点**：
- ✅ 专为 DeepAgent 设计
- ✅ 更简洁
- ✅ 与 DeepAgent 特性完全兼容

**缺点**：
- ❌ 失去 Pydantic 的类型安全
- ❌ 与现有系统不一致
- ❌ 需要重新定义所有数据结构

#### 选项3：混合使用（最糟糕）
```python
# ❌ 不要这样做！
class BoostAgent(BaseSubAgent):
    async def execute(
        self,
        state: VizQLState,  # 使用 VizQL State
        runtime: Runtime[DeepAgentContext],  # 使用 DeepAgent Context
        ...
    ):
        # 混乱！
```

**问题**：
- ❌ 概念混乱
- ❌ 难以维护
- ❌ 容易出错

---

## 推荐方案

### 🎯 推荐：使用 VizQL 系统

**理由**：

1. **类型安全**
   - VizQLState 使用 Pydantic 模型
   - 编译时类型检查
   - IDE 自动补全

2. **与现有系统一致**
   - 所有现有的 Agent 都使用 VizQL 系统
   - 所有 Pydantic 模型已经定义好
   - 降低迁移风险

3. **DeepAgent 兼容性**
   - DeepAgent 的 Runtime 可以使用任何 Context
   - DeepAgent 的 State 可以使用任何 TypedDict
   - 不需要使用 DeepAgentContext/State

4. **渐进式迁移**
   - 先使用 VizQL 系统完成迁移
   - 后续如果需要，再考虑优化

### 实现方式

```python
# base.py
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tableau_assistant.src.models.context import VizQLContext
    from tableau_assistant.src.models.state import VizQLState
    from langgraph.runtime import Runtime

class BaseSubAgent(ABC):
    async def execute(
        self,
        state: "VizQLState",  # ⭐ 使用 VizQL
        runtime: "Runtime[VizQLContext]",  # ⭐ 使用 VizQL
        user_config: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        ...
```

```python
# boost_agent.py
from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.src.models.state import VizQLState
from tableau_assistant.src.models.boost import QuestionBoost

class BoostAgent(BaseSubAgent):
    def _process_result(
        self,
        result: QuestionBoost,  # ⭐ Pydantic 模型
        state: VizQLState
    ) -> Dict[str, Any]:
        return {
            "boost": result,  # ⭐ 存储 Pydantic 对象
            "boosted_question": result.boosted_question
        }
```

### DeepAgentContext/State 的处理

**建议**：
1. **保留但不使用**：这两个文件可以保留，作为未来优化的参考
2. **添加文档说明**：在文件顶部说明这是备选方案
3. **统一使用 VizQL 系统**：所有子代理都使用 VizQL 系统

---

## 行动计划

### 1. 更新文档
在 `deepagent_context.py` 和 `deepagent_state.py` 顶部添加说明：

```python
"""
注意：这是为 DeepAgent 框架设计的备选数据模型。

当前实现使用 VizQLContext 和 VizQLState（见 context.py 和 state.py）
以保持与现有系统的一致性和类型安全。

这个文件保留作为未来优化的参考。
"""
```

### 2. 统一子代理实现
所有子代理都使用：
- `VizQLContext` 作为 Runtime context
- `VizQLState` 作为 State
- Pydantic 模型作为数据结构

### 3. 更新设计文档
在设计文档中明确说明：
- 使用 VizQL 系统
- DeepAgent 系统是备选方案
- 原因和权衡

---

## 总结

**最终决策**：
- ✅ 使用 **VizQLContext** 和 **VizQLState**
- ✅ 保留 Pydantic 模型的类型安全
- ✅ 与现有系统保持一致
- ✅ DeepAgentContext/State 保留但不使用

**核心原则**：
1. **类型安全优先**：Pydantic > Dict
2. **一致性优先**：与现有系统对齐
3. **渐进式迁移**：先完成功能，再优化
4. **避免混淆**：只使用一套系统
