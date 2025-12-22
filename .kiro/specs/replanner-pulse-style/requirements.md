# Requirements Document

## Introduction

重构 Replanner Agent，实现类似 Tableau Pulse 的智能探索功能。Replanner 应该直接生成结构化的查询规格（而不是自然语言问题），并路由到 query_builder 节点执行，跳过 semantic_parser 和 field_mapper。

## Glossary

- **Replanner**: 重规划代理，评估分析完整性并生成探索查询
- **ExplorationQuery**: 探索查询，包含完整的结构化查询规格和自然语言描述
- **dimension_hierarchy**: 维度层级结构，定义维度之间的父子关系和粒度级别
- **query_builder**: 查询构建节点，将结构化查询转换为 VizQL 查询

## Requirements

### Requirement 1: 结构化探索查询生成

**User Story:** As a data analyst, I want the Replanner to generate structured exploration queries directly, so that the system can execute them without re-parsing natural language.

#### Acceptance Criteria

1. WHEN Replanner decides to explore, THE Replanner SHALL generate ExplorationQuery objects containing:
   - dimensions: 目标维度列表（技术字段名）
   - measures: 指标列表（技术字段名 + 聚合方式）
   - filters: 筛选条件列表（继承自原始查询 + 新增条件）
   - display_question: 自然语言描述（用于展示给用户）

2. WHEN generating exploration queries, THE Replanner SHALL select dimensions from dimension_hierarchy based on exploration_type:
   - drill_down: 选择当前维度的子维度
   - roll_up: 选择当前维度的父维度
   - time_series: 选择时间维度
   - peer_comparison: 移除当前实体筛选，保留维度
   - cross_dimension: 选择不同类别的维度

3. WHEN generating exploration queries, THE Replanner SHALL inherit measures and filters from the original query unless explicitly modified

### Requirement 2: 直接路由到 query_builder

**User Story:** As a system architect, I want exploration queries to route directly to query_builder, so that we avoid redundant semantic parsing.

#### Acceptance Criteria

1. WHEN Replanner generates exploration queries, THE workflow SHALL route to query_builder node (not semantic_parser)

2. WHEN routing to query_builder, THE state SHALL contain:
   - vizql_query: 由 Replanner 直接构建的查询结构
   - exploration_display: 自然语言描述（用于 UI 展示）

3. WHEN exploration query execution completes, THE workflow SHALL route back to insight_analyzer for analysis

### Requirement 3: 维度层级感知

**User Story:** As a data analyst, I want the Replanner to understand dimension hierarchies, so that it can generate meaningful drill-down and roll-up queries.

#### Acceptance Criteria

1. WHEN performing drill_down, THE Replanner SHALL select child dimensions from dimension_hierarchy

2. WHEN performing roll_up, THE Replanner SHALL select parent dimensions from dimension_hierarchy

3. WHEN dimension_hierarchy is not available, THE Replanner SHALL fall back to generating natural language questions (legacy behavior)

### Requirement 4: 探索类型多样性

**User Story:** As a data analyst, I want diverse exploration types, so that I can understand data from multiple perspectives.

#### Acceptance Criteria

1. THE Replanner SHALL support the following exploration types:
   - drill_down: 向下钻取到更细粒度
   - roll_up: 向上汇总到更粗粒度
   - time_series: 时间序列分析
   - peer_comparison: 同级对比分析
   - cross_dimension: 跨维度分析
   - anomaly_investigation: 异常调查

2. WHEN selecting exploration type, THE Replanner SHALL consider:
   - 用户问题的意图（"为什么" → drill_down/anomaly）
   - 当前分析的维度（单一维度 → cross_dimension）
   - 数据洞察画像（发现异常 → anomaly_investigation）

### Requirement 5: 用户展示

**User Story:** As a user, I want to see what the system is exploring, so that I understand the analysis process.

#### Acceptance Criteria

1. WHEN generating exploration queries, THE Replanner SHALL generate display_question in Chinese

2. THE display_question SHALL describe the exploration in user-friendly terms (e.g., "正在分析 A店各产品类别的销售额分布")

3. THE display_question SHALL be stored in state for UI rendering
