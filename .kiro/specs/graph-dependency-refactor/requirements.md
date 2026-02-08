# 需求文档

## 简介

重构 `agents/semantic_parser/graph.py` 中对 `orchestration/workflow/context.py` 的违规依赖。当前 `graph.py` 直接导入 `get_context` 和 `get_context_or_raise`，违反了项目编码规范 Rule 12A.2 中规定的模块依赖方向（agents 不应导入 orchestration）。

本次重构的目标是：在 `core/interfaces.py` 中定义 Agent 可依赖的抽象接口（Protocol），将 `get_context` / `get_context_or_raise` 辅助函数迁移到 `agents/base/` 模块，使 Agent 仅依赖 `core/` 和 `agents/base/`，而具体的 `WorkflowContext` 实现保留在 `orchestration/` 中。

## 术语表

- **WorkflowContext**: 工作流运行时上下文，包含认证、数据源、数据模型、字段语义等信息的 Pydantic 模型，定义在 `orchestration/workflow/context.py`
- **Agent_Graph**: `agents/semantic_parser/graph.py` 中定义的 LangGraph 子图，包含多个节点函数
- **RunnableConfig**: LangGraph 框架提供的配置字典，用于在节点间传递上下文
- **Protocol**: Python `typing.Protocol`，用于定义结构化子类型（鸭子类型接口）
- **BasePlatformAdapter**: `core/interfaces.py` 中已有的平台适配器抽象基类
- **agents_base**: `agents/base/` 模块，存放 Agent 共享的基础设施辅助函数（如 `get_llm`）

## 需求

### 需求 1：定义工作流上下文抽象接口

**用户故事：** 作为开发者，我希望 Agent 节点依赖一个定义在 `core/` 中的抽象接口而非具体的 `WorkflowContext` 类，以便遵守依赖方向规范。

#### 验收标准

1. THE Core_Module SHALL 在 `core/interfaces.py` 中定义一个 `WorkflowContextProtocol`（使用 `typing.Protocol`），声明 Agent 节点所需的属性和方法
2. WHEN Agent_Graph 节点需要访问工作流上下文时，THE WorkflowContextProtocol SHALL 提供以下只读属性：`datasource_luid`（str）、`data_model`（Optional[Any]）、`field_semantic`（Optional[Dict[str, Any]]）、`platform_adapter`（Optional[Any]）、`auth`（Optional[Any]）、`field_values_cache`（Dict[str, List[str]]）
3. THE WorkflowContextProtocol SHALL 声明 `schema_hash` 只读属性（返回 str）
4. THE WorkflowContextProtocol SHALL 声明 `enrich_field_candidates_with_hierarchy` 方法签名（接收 List[Any]，返回 List[Any]）
5. THE WorkflowContext（orchestration 中的具体实现）SHALL 满足 WorkflowContextProtocol 的结构化子类型约束

### 需求 2：迁移上下文获取辅助函数到 agents/base

**用户故事：** 作为开发者，我希望从 `agents/base/` 模块导入上下文获取函数，以便 Agent 不再需要导入 orchestration 模块。

#### 验收标准

1. THE Agents_Base_Module SHALL 在 `agents/base/` 中提供 `get_context` 函数，从 RunnableConfig 中提取符合 WorkflowContextProtocol 的上下文对象
2. THE Agents_Base_Module SHALL 在 `agents/base/` 中提供 `get_context_or_raise` 函数，当上下文不存在时抛出 ValueError
3. WHEN `get_context` 接收 None 作为 config 参数时，THE get_context 函数 SHALL 返回 None
4. WHEN `get_context` 接收有效的 RunnableConfig 时，THE get_context 函数 SHALL 从 `config["configurable"]["workflow_context"]` 键提取上下文对象
5. THE get_context 函数和 get_context_or_raise 函数 SHALL 使用 WorkflowContextProtocol 作为返回类型注解

### 需求 3：更新 Agent Graph 导入路径

**用户故事：** 作为开发者，我希望 `agents/semantic_parser/graph.py` 不再导入 orchestration 模块，以便消除依赖方向违规。

#### 验收标准

1. THE Agent_Graph SHALL 从 `agents/base/` 导入 `get_context` 和 `get_context_or_raise`，替代从 `orchestration/workflow/context` 的导入
2. WHEN Agent_Graph 中的节点函数使用上下文对象时，THE 节点函数 SHALL 通过 WorkflowContextProtocol 接口访问属性和方法
3. THE Agent_Graph 文件 SHALL 不包含任何从 `analytics_assistant.src.orchestration` 包的导入语句
4. WHEN 重构完成后，THE Agent_Graph 中所有节点函数（`query_cache_node`、`field_retriever_node`、`semantic_understanding_node`、`filter_validator_node`、`query_adapter_node`）SHALL 保持原有功能不变

### 需求 4：依赖方向合规性验证

**用户故事：** 作为开发者，我希望重构后的代码完全符合 Rule 12A.2 依赖方向规范，以便通过代码审查。

#### 验收标准

1. THE Agent_Graph 模块 SHALL 仅依赖以下模块：`core/`、`infra/`、`agents/base/`、以及同一 Agent 内的子模块
2. THE Core_Module（`core/interfaces.py`）SHALL 不引入对 `agents/`、`infra/`、`orchestration/`、`platform/` 的新依赖
3. THE Agents_Base_Module 中新增的上下文辅助函数 SHALL 仅依赖 `core/` 模块中的类型定义
4. WHEN orchestration 模块中的 `get_context` 和 `get_context_or_raise` 不再被其他模块使用时，THE Orchestration_Module SHALL 移除这些冗余函数
