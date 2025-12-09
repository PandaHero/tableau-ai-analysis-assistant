# Requirements Document

## Introduction

本文档定义了两个关键优化需求：
1. **维度层级推断性能优化** - 当前一次性推断所有维度（20个字段耗时51秒），需要优化为增量推断 + 缓存策略
2. **FieldMapper 架构重构** - 将 FieldMapper 从 `nodes` 包移动到 `agents` 包，因为它使用了 RAG + LLM 混合方案，符合 Agent 的定义

## Glossary

- **Agent**: 使用 LLM 进行推理决策的组件，通常包含 prompt、LLM 调用、结果解析
- **Node**: 纯逻辑处理节点，不涉及 LLM 调用
- **RAG**: Retrieval-Augmented Generation，检索增强生成
- **维度层级**: 维度字段的层级属性（category、level、granularity、parent/child 关系）
- **增量推断**: 只推断新增或变更的字段，复用已有推断结果
- **StoreManager**: SQLite 持久化存储管理器

## Requirements

### Requirement 1: 维度层级推断性能优化

**User Story:** As a 用户, I want 维度层级推断能在 5 秒内完成, so that 系统响应更快，用户体验更好。

#### Acceptance Criteria

1. WHEN 系统首次推断维度层级 THEN DimensionHierarchyAgent SHALL 将推断结果持久化到 StoreManager 缓存
2. WHEN 系统再次请求维度层级推断且缓存有效 THEN DimensionHierarchyAgent SHALL 直接返回缓存结果，跳过 LLM 调用
3. WHEN 数据源元数据发生变更（字段增删改） THEN DimensionHierarchyAgent SHALL 仅对变更字段进行增量推断
4. WHEN 执行增量推断 THEN DimensionHierarchyAgent SHALL 合并新推断结果与缓存结果
5. WHEN 缓存超过 7 天 THEN DimensionHierarchyAgent SHALL 标记缓存为过期，触发重新推断
6. WHEN 推断单个字段 THEN DimensionHierarchyAgent SHALL 在 500ms 内完成（不含网络延迟）

### Requirement 2: FieldMapper 架构重构

**User Story:** As a 开发者, I want FieldMapper 放在正确的包结构中, so that 代码架构清晰，符合设计原则。

#### Acceptance Criteria

1. WHEN FieldMapper 使用 LLM 进行字段选择 THEN FieldMapper SHALL 位于 `agents` 包而非 `nodes` 包
2. WHEN 重构 FieldMapper THEN 系统 SHALL 创建 `agents/field_mapper/` 目录结构（prompt.py, node.py, __init__.py）
3. WHEN 重构 FieldMapper THEN 系统 SHALL 保持原有的 RAG + LLM 混合策略不变
4. WHEN 重构 FieldMapper THEN 系统 SHALL 更新所有引用 FieldMapper 的代码
5. WHEN 重构完成 THEN 系统 SHALL 删除 `nodes/field_mapper/` 目录

### Requirement 3: 统一 Agent 接口规范

**User Story:** As a 开发者, I want 所有 Agent 遵循统一的接口规范, so that 代码风格一致，易于维护。

#### Acceptance Criteria

1. WHEN 创建新 Agent THEN Agent SHALL 包含 prompt.py（定义 VizQLPrompt 子类）
2. WHEN 创建新 Agent THEN Agent SHALL 包含 node.py（定义异步入口函数）
3. WHEN Agent 需要缓存 THEN Agent SHALL 使用 StoreManager 进行持久化
4. WHEN Agent 调用 LLM THEN Agent SHALL 使用 base 包提供的 get_llm()、stream_llm_call()、parse_json_response()
5. WHEN 存在功能重复的组件 THEN 系统 SHALL 合并到对应的 Agent 中（如 HierarchyInferrer 合并到 DimensionHierarchyAgent）
