# 需求文档

## 简介

本需求文档定义了 Tableau Assistant 的会话级上下文缓存功能。目标是解决当前每次请求都重新加载元数据和推断维度层级的问题。

**核心问题**：
1. 每次 API 请求创建新的 `WorkflowExecutor` → 新的 `WorkflowContext`（metadata=None）
2. 自定义 `StoreManager` 没有与 LangGraph 框架集成
3. 重复造轮子：LangGraph 已提供 `SqliteStore` 持久化能力

**解决方案**：使用 LangGraph 框架提供的 `SqliteStore` + `SqliteSaver` 实现持久化缓存，替代自定义的 `StoreManager`。

## 术语表

- **会话 (Session)**: 用户与系统的一次交互会话，由 `session_id` + `datasource_luid` 标识
- **SqliteStore**: LangGraph 提供的 SQLite 持久化键值存储，支持命名空间、TTL、向量搜索
- **SqliteSaver**: LangGraph 提供的 SQLite 检查点存储，用于保存工作流状态
- **元数据 (Metadata)**: 数据源元数据，包含字段信息、数据模型等
- **维度层级 (Dimension Hierarchy)**: 维度层级结构，由 LLM 推断生成
- **TTL**: Time To Live，缓存有效期（默认 24 小时）

## 需求

### 需求 1：使用 LangGraph SqliteStore 替代自定义 StoreManager

**用户故事:** 作为开发者，我希望使用 LangGraph 框架内置的持久化能力，这样可以减少维护成本并与框架更好地集成。

#### 验收标准

1. WHEN 系统启动时 THEN 系统 SHALL 创建全局 SqliteStore 实例并配置 TTL
2. WHEN 工作流被编译时 THEN 系统 SHALL 将 SqliteStore 传递给 `compile(store=...)` 
3. WHEN 节点需要访问缓存时 THEN 系统 SHALL 通过 `config["configurable"]["store"]` 获取 Store
4. WHEN 存储数据时 THEN 系统 SHALL 使用命名空间 `("metadata", datasource_luid)` 组织数据

### 需求 2：请求处理流程（缓存优先）

**用户故事:** 作为用户，我希望系统能够智能地使用缓存，只有在缓存不存在或过期时才重新加载。

#### 验收标准

1. WHEN 用户发送任何问题 THEN 系统 SHALL 首先查询 SqliteStore 中的缓存
2. WHEN 缓存存在且未过期（TTL 内） THEN 系统 SHALL 直接使用缓存数据（跳过 API 和推断）
3. WHEN 缓存不存在或已过期 THEN 系统 SHALL 从 Tableau API 加载元数据
4. WHEN 元数据加载完成且缓存中无维度层级 THEN 系统 SHALL 调用维度层级推断 Agent
5. WHEN 新数据加载完成 THEN 系统 SHALL 将 metadata + hierarchy 存入 SqliteStore（TTL=24h）
6. WHEN 数据准备完成后 THEN 系统 SHALL 将 metadata 注入到工作流 State 中

### 需求 3：缓存命中场景

**用户故事:** 作为用户，我希望当缓存有效时能够快速得到响应，无需等待数据加载。

#### 验收标准

1. WHEN 缓存存在且未过期 THEN 系统 SHALL 在 100ms 内完成缓存读取
2. WHEN 从缓存加载成功 THEN 系统 SHALL 跳过 Tableau API 调用
3. WHEN 从缓存加载成功 THEN 系统 SHALL 跳过维度层级推断
4. WHEN 缓存命中时 THEN 系统 SHALL 记录日志 "缓存命中: {datasource_luid}, 剩余 TTL: {remaining}h"

### 需求 4：缓存失效和刷新

**用户故事:** 作为系统管理员，我希望缓存能够自动过期并在需要时刷新。

#### 验收标准

1. WHEN 缓存 TTL 过期 THEN 系统 SHALL 在下次请求时重新加载
2. WHEN 数据源结构发生变化 THEN 系统 SHALL 提供 API 手动失效缓存
3. WHEN 缓存被失效时 THEN 系统 SHALL 记录失效原因和时间戳
4. WHEN 刷新缓存时 THEN 系统 SHALL 不阻塞当前请求（使用旧缓存 + 后台刷新）

### 需求 5：错误处理和降级

**用户故事:** 作为用户，我希望即使缓存系统出现问题，我的查询仍然能够正常工作。

#### 验收标准

1. IF SqliteStore 读取失败 THEN 系统 SHALL 回退到直接 API 加载
2. IF SqliteStore 写入失败 THEN 系统 SHALL 继续处理请求并记录警告
3. IF 维度层级推断失败 THEN 系统 SHALL 使用空层级继续执行
4. WHEN 发生降级时 THEN 系统 SHALL 记录详细错误信息

### 需求 6：日志和监控

**用户故事:** 作为系统管理员，我希望能够监控缓存的使用情况。

#### 验收标准

1. WHEN 缓存命中时 THEN 系统 SHALL 记录 INFO 日志 "缓存命中: {datasource_luid}"
2. WHEN 缓存未命中时 THEN 系统 SHALL 记录 INFO 日志 "缓存未命中: {datasource_luid}, 加载耗时: {duration}ms"
3. WHEN 维度层级推断完成时 THEN 系统 SHALL 记录 INFO 日志 "维度层级推断完成: {field_count} 个字段, 耗时: {duration}ms"
4. WHEN 缓存写入完成时 THEN 系统 SHALL 记录 DEBUG 日志 "缓存写入: {datasource_luid}, TTL: {ttl}h"

