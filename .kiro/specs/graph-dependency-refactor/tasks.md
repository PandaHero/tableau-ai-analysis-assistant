# 实现计划：Graph 依赖方向重构

## 概述

将 `agents/semantic_parser/graph.py` 对 `orchestration/workflow/context.py` 的违规依赖重构为合规的依赖方向：通过在 `core/interfaces.py` 定义 Protocol、在 `agents/base/context.py` 提供辅助函数来解耦。

## Tasks

- [x] 1. 在 core/interfaces.py 中新增 WorkflowContextProtocol
  - [x] 1.1 在 `core/interfaces.py` 中定义 `WorkflowContextProtocol`（`typing.Protocol`，`@runtime_checkable`），声明 `datasource_luid`、`data_model`、`field_semantic`、`platform_adapter`、`auth`、`field_values_cache`、`schema_hash` 属性和 `enrich_field_candidates_with_hierarchy` 方法
    - 使用 `typing` 模块的泛型类型（`Dict`、`List`、`Optional`）
    - 更新 `__all__` 导出列表
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - [x] 1.2 编写属性测试验证 WorkflowContext 满足 Protocol
    - **Property 1: WorkflowContext 满足 Protocol 约束**
    - **Validates: Requirements 1.5**

- [x] 2. 在 agents/base/ 中新增上下文辅助函数
  - [x] 2.1 创建 `agents/base/context.py`，实现 `get_context` 和 `get_context_or_raise` 函数
    - 返回类型使用 `WorkflowContextProtocol`
    - 从 `core/interfaces` 导入 Protocol 类型
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  - [x] 2.2 更新 `agents/base/__init__.py`，导出 `get_context` 和 `get_context_or_raise`
    - _Requirements: 2.1, 2.2_
  - [x] 2.3 编写属性测试验证 get_context 提取等价性
    - **Property 2: get_context 提取等价性**
    - **Validates: Requirements 2.4, 3.4**
  - [x] 2.4 编写单元测试覆盖边界情况
    - 测试 `get_context(None)` 返回 None
    - 测试 `get_context_or_raise(None)` 抛出 ValueError
    - 测试空 config 和缺少 workflow_context 键的情况
    - _Requirements: 2.3_

- [x] 3. 更新 graph.py 导入路径并清理 orchestration 导出
  - [x] 3.1 修改 `agents/semantic_parser/graph.py`，将 `from analytics_assistant.src.orchestration.workflow.context import get_context, get_context_or_raise` 替换为 `from analytics_assistant.src.agents.base.context import get_context, get_context_or_raise`
    - _Requirements: 3.1, 3.3_
  - [x] 3.2 从 `orchestration/__init__.py` 和 `orchestration/workflow/__init__.py` 的导出中移除 `get_context` 和 `get_context_or_raise`
    - 保留 `context.py` 中的函数定义（orchestration 内部仍可使用）
    - _Requirements: 4.4_
  - [x] 3.3 编写静态分析单元测试验证依赖方向合规
    - 验证 `graph.py` 不包含 `orchestration` 导入
    - 验证 `agents/base/context.py` 仅依赖 `core/` 模块
    - _Requirements: 3.3, 4.1, 4.2, 4.3_

- [x] 4. 最终检查点
  - 确保所有测试通过，ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 节点函数内部代码无需修改，因为返回的运行时对象仍是 WorkflowContext 实例
- Property 测试使用 Hypothesis 库，每个属性至少 100 次迭代
