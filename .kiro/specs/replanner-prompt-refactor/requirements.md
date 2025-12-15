# Requirements Document

## Introduction

本需求文档定义了重构 Replanner Agent Prompt 的功能，使其符合 `PROMPT_AND_MODEL_GUIDE.md` 规范文档的要求。当前的 `ReplannerPrompt` 实现存在以下问题：

1. Role 部分过于简单，缺少专业领域描述
2. Task 部分缺少隐式 Chain-of-Thought (CoT) 流程
3. Domain Knowledge 部分没有使用 "Think step by step" 格式
4. 整体结构与其他 Agent（Understanding、Insight）不一致

本功能将重构 `ReplannerPrompt`，使其遵循项目的 Prompt 编写规范。

## Glossary

- **VizQLPrompt**: 项目中所有 VizQL 相关 Prompt 的基类，提供 4 段式结构（Role, Task, Domain Knowledge, Constraints）
- **CoT (Chain-of-Thought)**: 思维链，引导 LLM 逐步思考的技术
- **ReplanDecision**: Replanner Agent 的输出模型，包含完整度评分、是否重规划、探索问题列表等
- **ExplorationQuestion**: 探索问题模型，包含问题文本、探索类型、目标维度、优先级等
- **dimension_hierarchy**: 维度层级信息，用于指导探索方向
- **data_insight_profile**: 数据洞察画像，Phase 1 统计分析结果

## Requirements

### Requirement 1: Role 部分重构

**User Story:** 作为开发者，我希望 Replanner Prompt 的 Role 部分符合规范，以便 LLM 能够正确理解其角色定位。

#### Acceptance Criteria

1. WHEN 定义 Role 时 THEN ReplannerPrompt SHALL 使用约 20 个单词的简洁描述
2. WHEN 定义 Role 时 THEN ReplannerPrompt SHALL 包含专业领域描述（Expertise 列表）
3. WHEN 定义 Role 时 THEN ReplannerPrompt SHALL 与 UnderstandingPrompt 和 InsightPrompt 保持一致的格式

### Requirement 2: Task 部分重构

**User Story:** 作为开发者，我希望 Replanner Prompt 的 Task 部分包含隐式 CoT 流程，以便 LLM 能够按步骤执行任务。

#### Acceptance Criteria

1. WHEN 定义 Task 时 THEN ReplannerPrompt SHALL 使用约 50 个单词的描述
2. WHEN 定义 Task 时 THEN ReplannerPrompt SHALL 包含 "Process:" 行，使用 "→" 连接步骤
3. WHEN 定义 Task 时 THEN ReplannerPrompt SHALL 明确说明任务目标（评估完整度、生成探索问题）

### Requirement 3: Domain Knowledge 部分重构

**User Story:** 作为开发者，我希望 Replanner Prompt 的 Domain Knowledge 部分使用 "Think step by step" 格式，以便 LLM 能够按照清晰的思考步骤进行推理。

#### Acceptance Criteria

1. WHEN 定义 Domain Knowledge 时 THEN ReplannerPrompt SHALL 使用 "**Think step by step:**" 开头
2. WHEN 定义 Domain Knowledge 时 THEN ReplannerPrompt SHALL 包含 4-6 个编号步骤（Step 1, Step 2, ...）
3. WHEN 定义 Domain Knowledge 时 THEN ReplannerPrompt SHALL 每个步骤包含 2-4 个子要点
4. WHEN 定义 Domain Knowledge 时 THEN ReplannerPrompt SHALL 将探索类型表格移到步骤中作为参考
5. WHEN 定义 Domain Knowledge 时 THEN ReplannerPrompt SHALL 将去重规则整合到相应步骤中

### Requirement 4: Constraints 部分优化

**User Story:** 作为开发者，我希望 Replanner Prompt 的 Constraints 部分更加精炼，以便 LLM 能够清晰理解约束条件。

#### Acceptance Criteria

1. WHEN 定义 Constraints 时 THEN ReplannerPrompt SHALL 使用 "MUST:" 和 "MUST NOT:" 格式
2. WHEN 定义 Constraints 时 THEN ReplannerPrompt SHALL 每条约束不超过 10 个单词
3. WHEN 定义 Constraints 时 THEN ReplannerPrompt SHALL 包含 3-5 条核心约束

### Requirement 5: User Template 优化

**User Story:** 作为开发者，我希望 Replanner Prompt 的 User Template 与其他 Agent 保持一致的风格。

#### Acceptance Criteria

1. WHEN 定义 User Template 时 THEN ReplannerPrompt SHALL 使用 "##" 标题格式分隔各部分
2. WHEN 定义 User Template 时 THEN ReplannerPrompt SHALL 包含所有必要的上下文信息
3. WHEN 定义 User Template 时 THEN ReplannerPrompt SHALL 在末尾包含简洁的任务说明

### Requirement 6: 单元测试

**User Story:** 作为开发者，我希望重构后的 Prompt 有单元测试验证，以确保格式正确。

#### Acceptance Criteria

1. WHEN 测试 ReplannerPrompt 时 THEN 测试 SHALL 验证 Role 部分不为空
2. WHEN 测试 ReplannerPrompt 时 THEN 测试 SHALL 验证 Task 部分包含 "Process:"
3. WHEN 测试 ReplannerPrompt 时 THEN 测试 SHALL 验证 Domain Knowledge 包含 "Think step by step"
4. WHEN 测试 ReplannerPrompt 时 THEN 测试 SHALL 验证 format_messages 能正确生成消息列表
