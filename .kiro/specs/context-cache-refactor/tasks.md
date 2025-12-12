# 上下文和缓存架构重构实现任务

## 任务概览

本文档将设计分解为可执行的实现任务。任务按依赖关系排序，每个任务都是独立可测试的。

**重要设计决策**：
1. 维度层级推断在打开看板时就开始执行（而非工作流启动时），因为推断过程耗时较长，需要提前预热
2. 所有依赖通过 `WorkflowContext` 统一管理，消除全局变量
3. 数据模型通过 `State` 传递给所有节点，配置通过 `RunnableConfig` 传递

---

## Phase 0: 维度层级预热服务 (Dimension Hierarchy Preload)

### Task 0.1: 创建预热 API 端点
- [x] 创建 `tableau_assistant/src/api/preload.py`
- [x] 实现 `POST /api/preload/dimension-hierarchy` 端点
  - 接收 `datasource_luid` 和 `force` 参数
  - 返回预热状态: `{ status: "ready" | "loading" | "failed" | "expired", task_id?: str }`
- [x] 实现 `GET /api/preload/status/{task_id}` 端点
  - 查询预热任务状态
- [x] 实现 `POST /api/preload/invalidate` 端点
  - 手动使缓存失效，触发重新获取
  - 用于数据源结构变更后强制刷新
- [x] 实现 `GET /api/preload/cache-status/{datasource_luid}` 端点
  - 查询缓存状态（是否有效、剩余 TTL）
- [x] 在 `main.py` 中注册路由

**文件**: 
- `tableau_assistant/src/api/preload.py`
- `tableau_assistant/src/main.py`

_Requirements: 1.1, 2.1_

### Task 0.2: 创建维度层级预热服务
- [x] 创建 `tableau_assistant/src/services/preload_service.py`
- [x] 实现 `PreloadStatus` 枚举: `PENDING`, `LOADING`, `READY`, `FAILED`, `EXPIRED`
- [x] 实现 `PreloadService` 类:
  - `start_preload(datasource_luid: str, force: bool = False) -> str`: 启动预热，返回 task_id
    - `force=True` 时强制重新获取，忽略缓存
  - `get_status(task_id: str) -> PreloadStatus`: 获取任务状态
  - `get_result(datasource_luid: str) -> Optional[Dict]`: 获取预热结果
  - `invalidate_cache(datasource_luid: str) -> bool`: 手动使缓存失效
  - `is_cache_valid(datasource_luid: str) -> bool`: 检查缓存是否有效
- [x] 实现后台任务机制（使用 `asyncio.create_task`）
- [x] 预热流程:
  1. 检查 StoreManager 缓存（24小时 TTL）
  2. 如果缓存命中且未过期，直接返回 `READY`
  3. 如果缓存过期，返回 `EXPIRED` 并启动后台刷新
  4. 如果缓存未命中，启动后台任务:
     a. 获取 Tableau 认证
     b. 调用 Metadata API 获取字段信息
     c. 调用 dimension_hierarchy_node Agent 推断
     d. 缓存结果到 StoreManager
- [x] 实现缓存失效检测:
  - 基于 TTL 自动检测
  - 基于数据源更新时间检测（如果可用）

**文件**: `tableau_assistant/src/services/preload_service.py`

_Requirements: 2.1, 2.3_

### Task 0.3: 前端集成 - Extension 初始化时触发预热
- [x] 修改 `tableau_extension/src/App.vue` 或相关入口
- [x] 在 `initializeTableauExtension()` 成功后:
  1. 调用 `getAllDataSources()` 获取数据源
  2. 调用后端 `POST /api/preload/dimension-hierarchy`
- [x] 添加预热状态显示（可选）

**文件**: 
- `tableau_extension/src/App.vue`
- `tableau_extension/src/api/client.ts`
- `tableau_extension/src/stores/tableau.ts` (新建)
- `tableau_extension/src/vite-env.d.ts` (新建)

_Requirements: 2.1_

---

## Phase 1: WorkflowContext 基础设施

### Task 1.1: 创建 WorkflowContext Pydantic 模型
- [x] 创建 `tableau_assistant/src/workflow/context.py`
- [x] 实现 `WorkflowContext` 类:
  ```python
  class WorkflowContext(BaseModel):
      auth: TableauAuthContext          # 认证上下文
      store: StoreManager               # 持久化存储
      datasource_luid: str              # 数据源 LUID
      metadata: Optional[Metadata]      # 完整数据模型
      max_replan_rounds: int = 3        # 最大重规划轮数
      user_id: Optional[str] = None     # 用户 ID
  ```
- [x] 配置 `model_config = ConfigDict(arbitrary_types_allowed=True)`

**文件**: `tableau_assistant/src/workflow/context.py`

_Requirements: 1.1, 3.3, 4.2_

### Task 1.2: 实现 WorkflowContext 方法
- [x] 实现 `is_auth_valid(buffer_seconds: int = 60) -> bool`
- [x] 实现 `async refresh_auth_if_needed() -> WorkflowContext`
  - 如果 token 未过期，返回 self
  - 如果 token 过期，调用 `get_tableau_auth_async(force_refresh=True)`
  - 返回新的 WorkflowContext 实例（不可变）
- [x] 实现 `async ensure_metadata_loaded() -> WorkflowContext`
  - 检查预热服务状态
  - 如果 `READY`，从缓存获取
  - 如果 `LOADING`，等待完成（带超时）
  - 如果 `PENDING/FAILED`，同步执行加载
  - 如果维度层级为空，重新推断
- [x] 实现 `async refresh_metadata_if_needed(force: bool = False) -> WorkflowContext`
  - 检查 metadata 缓存是否过期（通过 StoreManager TTL）
  - 如果过期或 force=True，重新获取并缓存
  - 返回新的 WorkflowContext 实例
- [x] 实现 `dimension_hierarchy` 属性（从 metadata 提取）
- [x] 实现 `MetadataLoadStatus` 类（用于通知用户加载状态）

**文件**: `tableau_assistant/src/workflow/context.py`

_Requirements: 1.3, 2.2, 2.3_

### Task 1.3: 创建 Config 辅助函数
- [x] 实现 `create_workflow_config(thread_id, context) -> RunnableConfig`
  - 创建 `{"configurable": {"thread_id": str, "workflow_context": ctx, "tableau_auth": ctx.auth.model_dump()}}`
  - 保持向后兼容：同时提供 `tableau_auth`
- [x] 实现 `get_context(config) -> Optional[WorkflowContext]`
- [x] 实现 `get_context_or_raise(config) -> WorkflowContext`

**文件**: `tableau_assistant/src/workflow/context.py`

_Requirements: 1.2, 3.2_

### Task 1.4: 更新 workflow 包导出
- [x] 更新 `tableau_assistant/src/workflow/__init__.py`
- [x] 导出: `WorkflowContext`, `MetadataLoadStatus`, `create_workflow_config`, `get_context`, `get_context_or_raise`

**文件**: `tableau_assistant/src/workflow/__init__.py`

_Requirements: 3.1_

---

## Phase 2: 核心组件重构

### Task 2.1: 更新 VizQLState 定义
- [x] 修改 `tableau_assistant/src/models/workflow/state.py`
- [x] 添加数据模型相关字段:
  ```python
  metadata: Optional[Metadata] = None
  dimension_hierarchy: Optional[Dict[str, Any]] = None
  data_insight_profile: Optional[Dict[str, Any]] = None
  current_dimensions: List[str] = []
  ```

**文件**: `tableau_assistant/src/models/workflow/state.py`

_Requirements: 4.1_

### Task 2.2: 重构 DataModelManager
- [x] 跳过 - 当前实现通过 `WorkflowContext.ensure_metadata_loaded()` 完成
- [x] `ensure_metadata_loaded()` 内部调用 `get_datasource_metadata()` 函数
- [x] 认证通过 `ctx.auth` 获取
- [x] 缓存通过 `ctx.store` 操作

**状态**: 已完成（通过 WorkflowContext.ensure_metadata_loaded() 实现，无需修改 DataModelManager）

**文件**: `tableau_assistant/src/workflow/context.py`

_Requirements: 1.4, 5.2_

### Task 2.3: 重构 WorkflowExecutor
- [x] 修改 `tableau_assistant/src/workflow/executor.py`
- [x] 添加 `datasource_luid` 参数到 `__init__`
- [x] 修改 `run()` 方法:
  1. 获取 `TableauAuthContext`
  2. 获取 `StoreManager` (全局单例)
  3. 创建 `WorkflowContext`
  4. 调用 `ctx.ensure_metadata_loaded()`
  5. 创建 `RunnableConfig` (使用 `create_workflow_config`)
  6. 构建初始 State（包含 metadata, dimension_hierarchy）
  7. 执行工作流
- [x] 修改 `stream()` 方法（同上）
- [x] 移除旧的 `create_config_with_auth()` 调用

**文件**: `tableau_assistant/src/workflow/executor.py`

_Requirements: 1.1, 2.4, 4.1_

---

## Phase 3: 节点重构

### Task 3.1: 重构 Understanding Node
- [x] 修改 `tableau_assistant/src/agents/understanding/node.py`
- [x] 从 `state["metadata"]` 获取数据模型
- [x] 使用 `metadata.fields` 构建字段摘要
- [x] 移除对 `get_metadata` 工具的依赖（数据已在 state 中）
- [x] 备选方案：使用 `get_context(config).metadata`

**状态**: 已完成（节点已经从 state.get("metadata") 获取元数据）

**文件**: `tableau_assistant/src/agents/understanding/node.py`

_Requirements: 4.1_

### Task 3.2: 重构 FieldMapper Node
- [x] 修改 `tableau_assistant/src/agents/field_mapper/node.py`
- [x] 从 `state["metadata"].fields` 获取字段列表
- [x] 移除重复的元数据获取逻辑

**状态**: 已完成（节点已经从 state.get("metadata") 获取元数据）

**文件**: `tableau_assistant/src/agents/field_mapper/node.py`

_Requirements: 4.1_

### Task 3.3: 重构 Execute Node
- [x] 修改 `tableau_assistant/src/nodes/execute/node.py`
- [x] 使用 `ensure_valid_auth_async(config)` 获取认证（已实现）
- [x] 使用 `ctx.auth` 获取认证信息
- [x] 实现认证过期自动刷新

**状态**: 已完成（节点已经使用 ensure_valid_auth_async(config) 获取认证）

**文件**: `tableau_assistant/src/nodes/execute/node.py`

_Requirements: 1.2, 1.3_

### Task 3.4: 重构 Insight Node
- [x] 修改 `tableau_assistant/src/agents/insight/node.py`
- [x] 从 `state["dimension_hierarchy"]` 获取维度层级
- [x] 输出 `insights` 和 `insight_result` 到 state
- [x] 输出 `data_insight_profile` 到 state（从 InsightResult.data_insight_profile 提取）
- [x] 输出 `current_dimensions` 到 state（从 context["dimensions"] 提取并累积）

**状态**: 已完成

**文件**: `tableau_assistant/src/agents/insight/node.py`

_Requirements: 4.1_

### Task 3.5: 重构 Replanner Node
- [x] 修改 `tableau_assistant/src/workflow/factory.py` 中的 replanner_node
- [x] 从 `state["dimension_hierarchy"]` 获取维度层级
- [x] 从 `state["data_insight_profile"]` 获取数据洞察画像
- [x] 从 `state["current_dimensions"]` 获取已分析维度
- [x] 传递这些数据给 `ReplannerAgent.replan()`

**状态**: 已完成（replanner_node 已经从 state 获取所有需要的数据）

**文件**: `tableau_assistant/src/workflow/factory.py`

_Requirements: 4.1_

---

## Phase 4: 工具重构

### Task 4.1: 重构 metadata_tool
- [x] 修改 `tableau_assistant/src/tools/metadata_tool.py`
- [x] 使用 `InjectedToolArg` 获取 config
- [x] 使用 `get_context(config)` 获取上下文
- [x] 从 `ctx.metadata` 获取（已在工作流启动时加载）
- [x] 移除全局 `_data_model_manager` 变量
- [x] 移除 `set_metadata_manager()` 和 `get_metadata_manager()` 函数
- [x] 更新 `tools/__init__.py` 导出

**状态**: 已完成

**文件**: 
- `tableau_assistant/src/tools/metadata_tool.py`
- `tableau_assistant/src/tools/__init__.py`

_Requirements: 3.2, 5.2_

### Task 4.2: 检查并重构其他工具
- [x] 检查 `tableau_assistant/src/tools/` 下所有工具
- [x] 确保使用 `get_context(config)` 获取依赖
- [x] 移除直接调用 `get_tableau_auth()` 的代码
  - `get_tableau_config()` 已添加废弃警告
  - `DataModelManager` 已重构为接受 `auth_context` 参数
  - 内部使用 `_get_tableau_auth()` 方法，优先使用传入的认证

**状态**: 已完成

**文件**: 
- `tableau_assistant/src/tools/*.py`
- `tableau_assistant/src/models/workflow/context.py`
- `tableau_assistant/src/capabilities/data_model/manager.py`

_Requirements: 5.3_

---

## Phase 5: 清理废弃代码

### Task 5.1: 清理 models/workflow/context.py
- [x] 保留 `VizQLContext` dataclass（仍被 DataModelManager 使用）
- [x] 移除 `get_tableau_config()` 函数
- [x] 更新 `models/__init__.py` 移除导出
- [x] 更新测试文件移除相关测试

**状态**: 已完成

**文件**: 
- `tableau_assistant/src/models/workflow/context.py`
- `tableau_assistant/src/models/__init__.py`
- `tableau_assistant/tests/test_token_flow.py`

_Requirements: 5.1_

### Task 5.2: 清理 DataModelManager 向后兼容代码
- [x] `DataModelManager._get_tableau_auth()` 现在必须传入 `auth_context`
- [x] 移除对 `get_tableau_config()` 的调用
- [x] 如果未传入 `auth_context` 会抛出 `ValueError`

**状态**: 已完成

**文件**: `tableau_assistant/src/capabilities/data_model/manager.py`

_Requirements: 5.1, 5.3_

### Task 5.3: 更新所有 __init__.py 导出
- [x] 更新 `tableau_assistant/src/workflow/__init__.py`
- [x] 更新 `tableau_assistant/src/services/__init__.py`
- [x] 更新 `tableau_assistant/src/api/__init__.py`（导出 chat_router, preload_router）

**状态**: 已完成

**文件**: 各 `__init__.py` 文件

_Requirements: 3.1_

---

## Phase 6: 测试

### Task 6.1*: 单元测试 - WorkflowContext
- [x] 创建 `tableau_assistant/tests/unit/test_workflow_context.py`
- [x] 测试 `WorkflowContext` 创建和验证
- [x] 测试 `is_auth_valid()` 方法
- [ ] 测试 `refresh_auth_if_needed()` 刷新逻辑（需要更多 mock）
- [ ] 测试 `ensure_metadata_loaded()` 加载逻辑（需要更多 mock）

**状态**: 基本完成

**文件**: `tableau_assistant/tests/unit/test_workflow_context.py`

### Task 6.2*: 单元测试 - Config 辅助函数
- [x] 测试 `create_workflow_config()` 创建正确结构
- [x] 测试 `get_context()` 正确解析
- [x] 测试 `get_context_or_raise()` 异常处理

**状态**: 已完成

**文件**: `tableau_assistant/tests/unit/test_workflow_context.py`

### Task 6.3*: 集成测试 - 预热服务
- [x] 创建 `tableau_assistant/tests/integration/test_preload_service.py`
- [x] 测试预热服务启动和状态查询
- [x] 测试后台任务执行
- [x] 测试缓存命中/未命中场景
- [x] 测试强制刷新功能
- [x] 测试缓存失效功能
- [x] 测试并发预热请求处理
- [x] 测试维度层级结果验证

**状态**: 已完成（9 个测试全部通过）

**文件**: `tableau_assistant/tests/integration/test_preload_service.py`

### Task 6.4*: 集成测试 - 完整工作流
- [x] 创建 `tableau_assistant/tests/integration/test_context_flow.py`
- [x] 测试 WorkflowContext 创建和初始化
- [x] 测试元数据加载流程
- [x] 测试认证刷新机制
- [x] 测试 RunnableConfig 集成
- [x] 测试完整工作流执行
- [x] 测试 Tool 通过 config 访问上下文

**状态**: 已完成（10 通过，1 跳过，3 因 API 限制跳过）

**文件**: `tableau_assistant/tests/integration/test_context_flow.py`

### Task 6.5: 回归测试
- [x] 运行现有单元测试，确保功能不受影响
- [x] 修复 Pydantic 前向引用问题（Metadata.model_rebuild()）
- [x] 修复 WorkflowContext 类型导入问题

**状态**: 已完成

**文件**: 
- `tableau_assistant/src/models/metadata/__init__.py`
- `tableau_assistant/src/workflow/context.py`

---

## 依赖关系图

```
Phase 0 (Preload) - 最高优先级，可独立开发
├── Task 0.1: 预热 API 端点
├── Task 0.2: 预热服务 (依赖 0.1)
└── Task 0.3: 前端集成 (依赖 0.1)

Phase 1 (Foundation) - 可与 Phase 0 并行
├── Task 1.1: WorkflowContext 模型
├── Task 1.2: WorkflowContext 方法 (依赖 1.1, 0.2)
├── Task 1.3: Config 辅助函数 (依赖 1.1)
└── Task 1.4: 更新导出 (依赖 1.1, 1.3)

Phase 2 (Core) - 依赖 Phase 1
├── Task 2.1: VizQLState 更新
├── Task 2.2: DataModelManager (依赖 1.1, 1.3)
└── Task 2.3: WorkflowExecutor (依赖 1.2, 1.3, 2.1, 2.2)

Phase 3 (Nodes) - 依赖 Phase 2
├── Task 3.1: Understanding Node (依赖 2.1)
├── Task 3.2: FieldMapper Node (依赖 2.1)
├── Task 3.3: Execute Node (依赖 1.3)
├── Task 3.4: Insight Node (依赖 2.1)
└── Task 3.5: Replanner Node (依赖 2.1)

Phase 4 (Tools) - 依赖 Phase 1
├── Task 4.1: metadata_tool (依赖 1.3)
└── Task 4.2: 其他工具 (依赖 1.3)

Phase 5 (Cleanup) - 依赖 Phase 3, 4
├── Task 5.1: 清理 context.py
├── Task 5.2: 清理 auth.py
└── Task 5.3: 更新导出

Phase 6 (Testing) - 依赖各阶段
├── Task 6.1*: 单元测试 - WorkflowContext
├── Task 6.2*: 单元测试 - Config
├── Task 6.3*: 集成测试 - 预热服务
├── Task 6.4*: 集成测试 - 工作流
└── Task 6.5: 回归测试
```

---

## 实现顺序建议

1. **Day 1**: Phase 0 (Task 0.1, 0.2) + Phase 1 (Task 1.1, 1.3, 1.4)
2. **Day 2**: Phase 0 (Task 0.3) + Phase 1 (Task 1.2) + Phase 2 (Task 2.1)
3. **Day 3**: Phase 2 (Task 2.2, 2.3)
4. **Day 4**: Phase 3 (Task 3.1 - 3.5)
5. **Day 5**: Phase 4 (Task 4.1, 4.2) + Phase 5 (Task 5.1 - 5.3)
6. **Day 6**: Phase 6 (测试和回归)

---

## 移除的组件清单

| 组件 | 位置 | 替代方案 |
|------|------|----------|
| `get_tableau_config()` | `models/workflow/context.py` | `ctx.auth` |
| `_data_model_manager` 全局变量 | `tools/metadata_tool.py` | `get_context(config)` |
| `set_metadata_manager()` | `tools/metadata_tool.py` | 不再需要 |
| `VizQLContext` dataclass | `models/workflow/context.py` | `WorkflowContext` |
| `_ctx_cache` 内存缓存 | `auth.py` | 仅内部使用 |

---

## 风险和注意事项

1. **向后兼容性**: 
   - 保留 `create_config_with_auth()` 和 `tableau_auth` 字段
   - 旧代码可以继续使用，新代码使用 `workflow_context`

2. **预热超时**: 
   - 维度层级推断可能耗时较长（30秒+）
   - 需要设置合理的超时和重试机制

3. **并发安全**: 
   - `WorkflowContext` 是不可变的
   - 刷新时返回新实例，避免并发问题

4. **测试覆盖**: 
   - 每完成一个 Task 后运行相关测试
   - 确保不破坏现有功能

5. **缓存失效处理**:
   - **认证 Token**: 自动检测过期，调用 `refresh_auth_if_needed()` 自动刷新
   - **元数据缓存**: StoreManager TTL 机制（24小时），过期后自动重新获取
   - **维度层级缓存**: StoreManager TTL 机制（24小时），过期后返回 `EXPIRED` 状态并触发后台刷新
   - **手动失效**: 提供 `POST /api/preload/invalidate` API 强制刷新
   - **数据源变更检测**: 如果 Tableau API 提供数据源更新时间，可以基于此检测缓存是否需要刷新

6. **Store 访问统一**:
   - 所有组件通过 `ctx.store` 访问 StoreManager
   - 不再直接调用 `get_store_manager()` 全局函数
   - StoreManager 仍然是全局单例，但通过 WorkflowContext 传递
   - 这样可以在测试时轻松替换为 Mock Store
