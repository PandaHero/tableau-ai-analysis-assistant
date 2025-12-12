# 上下文和缓存架构重构需求

## Introduction

当前项目的上下文管理和缓存机制存在重复造轮子的问题。认证信息通过多种方式获取（内存缓存、RunnableConfig、直接调用），导致代码混乱且难以维护。本需求旨在统一使用 LangGraph 的原生机制来管理上下文和缓存。

## Glossary

- **RunnableConfig**: LangGraph 的配置对象，通过 `configurable` 字段传递给所有节点
- **State**: LangGraph 工作流的可变状态，在节点间传递
- **Store**: LangGraph 的持久化存储接口，用于跨会话数据
- **Checkpointer**: LangGraph 的会话状态持久化机制
- **TableauAuthContext**: Tableau 认证上下文 Pydantic 模型

## Requirements

### Requirement 1: 统一认证上下文传递

**User Story:** 作为开发者，我希望所有需要 Tableau 认证的组件都从同一个来源获取认证信息，这样可以避免重复获取和不一致的问题。

#### Acceptance Criteria

1. WHEN 工作流启动时 THEN WorkflowExecutor SHALL 获取一次 TableauAuthContext 并放入 RunnableConfig
2. WHEN 任何节点需要认证时 THEN 该节点 SHALL 从 RunnableConfig["configurable"]["tableau_auth"] 获取
3. WHEN 认证 token 过期时 THEN 系统 SHALL 自动刷新并更新 RunnableConfig
4. WHEN DataModelManager 需要认证时 THEN DataModelManager SHALL 从传入的 config 参数获取，而不是自己调用 get_tableau_auth()

### Requirement 2: 统一缓存机制

**User Story:** 作为开发者，我希望有一个统一的缓存机制，避免多个缓存层导致的数据不一致。

#### Acceptance Criteria

1. WHEN 需要缓存业务数据时 THEN 系统 SHALL 使用 StoreManager（SQLite）
2. WHEN 需要缓存认证 token 时 THEN 系统 SHALL 使用 RunnableConfig 传递，内存缓存仅作为获取新 token 时的短期缓存
3. WHEN 缓存数据过期时 THEN StoreManager SHALL 自动清理过期数据
4. IF 多个组件需要同一数据 THEN 系统 SHALL 通过 State 或 RunnableConfig 传递，而不是各自缓存

### Requirement 3: 简化依赖注入

**User Story:** 作为开发者，我希望组件的依赖通过 LangGraph 的机制注入，而不是全局变量。

#### Acceptance Criteria

1. WHEN 创建工作流时 THEN create_tableau_workflow SHALL 初始化所有必要的组件并通过 Store 或 Config 传递
2. WHEN Tool 需要访问 DataModelManager 时 THEN Tool SHALL 从 RunnableConfig 获取，而不是全局变量
3. WHEN 节点需要访问 StoreManager 时 THEN 节点 SHALL 从 RunnableConfig["configurable"]["store"] 获取

### Requirement 4: State 设计优化

**User Story:** 作为开发者，我希望 State 只包含节点间需要传递的数据，配置和依赖通过 RunnableConfig 传递。

#### Acceptance Criteria

1. WHEN 定义 VizQLState 时 THEN State SHALL 只包含工作流数据（question, semantic_query, mapped_query 等）
2. WHEN 需要传递配置时 THEN 系统 SHALL 使用 RunnableConfig["configurable"]
3. WHEN 需要传递依赖时 THEN 系统 SHALL 使用 RunnableConfig["configurable"] 或工厂函数

### Requirement 5: 移除重复代码

**User Story:** 作为开发者，我希望移除所有重复的认证获取和缓存代码。

#### Acceptance Criteria

1. WHEN 重构完成后 THEN get_tableau_config() 函数 SHALL 被移除或简化为从 config 获取
2. WHEN 重构完成后 THEN DataModelManager SHALL 不再直接调用 get_tableau_auth()
3. WHEN 重构完成后 THEN 所有认证获取 SHALL 统一通过 ensure_valid_auth_async(config) 进行
