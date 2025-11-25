# 数据模型说明

## 模型架构

本项目包含两套并行的状态和上下文模型：

### 1. VizQL 模型（现有系统）

**文件位置**：
- `context.py` - VizQLContext
- `state.py` - VizQLState

**用途**：
- 用于现有的 VizQL 工作流
- 基于 LangGraph 1.0 的 state_schema 和 context_schema
- 包含完整的 VizQL 查询执行流程

**特点**：
- 使用 TypedDict 定义状态
- 使用 dataclass 定义上下文
- 与现有的 Tableau VizQL 系统紧密集成

### 2. DeepAgent 模型（新框架）

**文件位置**：
- `deepagent_context.py` - DeepAgentContext
- `deepagent_state.py` - DeepAgentState

**用途**：
- 用于新的 DeepAgent 框架
- 基于 LangChain DeepAgents 的架构
- 支持子代理、中间件和工具系统

**特点**：
- 使用 TypedDict 定义状态（与 LangGraph 兼容）
- 使用 frozen dataclass 定义上下文（不可变）
- 设计用于多代理协作和复杂工作流

## 为什么有两套模型？

### 渐进式迁移策略

根据重构任务的核心原则："渐进式迁移：先搭建框架，再逐步迁移功能"

1. **阶段 1-4**：使用 DeepAgent 模型搭建新框架
   - 不修改现有 VizQL 代码
   - 降低风险
   - 保持现有功能稳定

2. **阶段 5-6**：逐步迁移功能
   - 将 VizQL 工作流逐步迁移到 DeepAgent
   - 两套系统可以共存
   - 可以对比测试

3. **最终状态**：
   - 选项 A：完全迁移到 DeepAgent，废弃 VizQL 模型
   - 选项 B：保留两套系统，用于不同场景

### 模型对比

| 特性 | VizQLContext/State | DeepAgentContext/State |
|------|-------------------|----------------------|
| 框架 | LangGraph 1.0 | LangChain DeepAgents |
| 用途 | VizQL 查询执行 | 多代理协作 |
| 子代理支持 | ❌ | ✅ |
| 中间件支持 | ❌ | ✅ |
| 工具系统 | 有限 | 完整 |
| 状态管理 | TypedDict | TypedDict |
| 上下文管理 | dataclass | frozen dataclass |
| 不可变性 | 部分 | 完全 |

## 使用指南

### 使用 VizQL 模型

```python
from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.src.models.state import create_initial_state

# 创建上下文
context = VizQLContext.from_config(
    datasource_luid="abc123",
    user_id="user_456",
    session_id="session_789"
)

# 创建状态
state = create_initial_state(
    question="2024年各地区的销售额是多少？",
    boost_question=False
)
```

### 使用 DeepAgent 模型

```python
from tableau_assistant.src.models.deepagent_context import DeepAgentContext
from tableau_assistant.src.models.deepagent_state import create_initial_state

# 创建上下文
context = DeepAgentContext(
    datasource_luid="abc123",
    user_id="user_456",
    thread_id="thread_789",
    tableau_token="token_xyz"
)

# 创建状态
state = create_initial_state(
    question="2024年各地区的销售额是多少？",
    datasource_luid="abc123",
    thread_id="thread_789",
    user_id="user_456"
)
```

## 迁移计划

### 短期（阶段 1-4）
- ✅ 创建 DeepAgent 模型
- ⏳ 搭建 DeepAgent 框架
- ⏳ 实现工具层和中间件
- ⏳ 实现子代理

### 中期（阶段 5-6）
- ⏳ 迁移核心业务逻辑
- ⏳ 对比测试两套系统
- ⏳ 性能优化

### 长期（阶段 7-10）
- ⏳ 评估是否完全迁移
- ⏳ 决定 VizQL 模型的去留
- ⏳ 文档更新

## 注意事项

1. **不要混用两套模型**：在同一个工作流中只使用一套模型
2. **类型安全**：两套模型都提供了完整的类型提示
3. **测试覆盖**：每套模型都有独立的测试
4. **文档同步**：修改模型时同步更新文档

## 相关文件

- `question.py` - 问题理解相关模型（两套系统共用）
- `query_plan.py` - 查询规划相关模型（两套系统共用）
- `result.py` - 结果相关模型（两套系统共用）
- `insight_result.py` - 洞察结果模型（两套系统共用）
