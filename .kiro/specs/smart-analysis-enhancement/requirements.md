# 智能分析增强 - 需求文档

## 📖 文档导航

### 🚀 快速开始
- **[任务列表](./tasks.md)** - 可执行的任务分解（待创建）

### 📋 主文档（本文件）
- 项目简介和核心目标
- 需求列表（6个核心需求）
- 术语表
- 完整工作流设计

---

## 简介

本项目旨在增强现有VizQL多智能体系统的分析能力，引入**结果累积**、**分段处理**、**多问题并行分析**、**智能任务调度**、**上下文管理**等先进机制，实现更智能、更高效、更全面的数据分析。

### 核心目标

1. **结果累积** - 多轮分析中不断累积和整合发现，形成完整的分析图景
2. **分段处理** - 智能处理大数据量场景，避免token限制影响分析质量
3. **多问题并行** - 支持重规划生成多个问题并行分析，快速探索多个维度
4. **智能调度** - 任务调度器协调查询和洞察的并行执行，优化资源利用
5. **数据处理增强** - 支持VDS无法处理的聚合计算（同环比、增长率等）
6. **上下文管理** - 结构化的状态管理和上下文传递机制，确保分析连贯性

### 参考项目

本项目借鉴了以下优秀项目的设计思想：
- **BettaFish** - 多任务独立分析、综合决策机制、结构化状态管理、上下文传递
- **Tableau Pulse** - 多角度问题生成、智能推荐

---

## 术语表

### 核心概念
- **结果累积（Result Accumulation）** - 在多轮分析中不断累积之前的发现，避免重复分析
- **分段处理（Chunking）** - 将大型数据集拆分为多个小段，逐段处理并累积结果
- **多问题并行（Multi-Question Parallel）** - 重规划生成多个问题，并行执行分析
- **任务调度（Task Scheduling）** - 协调多个查询和洞察任务的执行顺序和并发控制
- **异步并行（Async Parallel）** - 多个任务同时执行，不等待其他任务完成
- **依赖分析（Dependency Analysis）** - 分析任务间的依赖关系，决定执行策略
- **综合决策（Comprehensive Decision）** - 基于多个维度的洞察进行关联分析和决策
- **上下文传递（Context Passing）** - 在不同Agent间传递累积的分析上下文
- **上下文压缩（Context Compression）** - 智能压缩历史信息，避免token超限
- **状态管理（State Management）** - 使用结构化数据结构管理分析状态

### 系统组件
- **TaskScheduler** - 任务调度器，管理查询和洞察的并行执行
- **DataProcessor** - 数据处理器，处理聚合计算和任务依赖
- **AnalysisState** - 整体分析状态数据结构（借鉴BettaFish的State）
- **TaskInsight** - 单个任务的洞察累积结构（借鉴BettaFish的Paragraph）
- **QueryHistory** - 查询历史记录，避免重复查询
- **ChunkProcessor** - 分段处理器，智能分段和合并
- **ContextCompressor** - 上下文压缩器，智能压缩历史信息

---

## 需求概览

本系统包含**6个核心需求**：

### 核心功能（P0）
- **需求1**: 结果累积机制
- **需求2**: 分段处理 + 结果累积
- **需求6**: 上下文管理和传递机制（新增，借鉴BettaFish）

### 系统增强（P1）
- **需求3**: 多问题并行分析
- **需求4**: 智能任务调度
- **需求5**: 数据处理增强

---

## 需求详情

### 需求1: 结果累积机制

**用户故事**: 作为业务数据分析师，我希望系统能够在多轮分析中累积之前的发现，避免重复分析，形成越来越完整的分析图景

#### 核心功能

1. **累积数据结构** - 设计清晰的累积结果数据结构
2. **独立累积** - 每个分析任务独立累积结果（参考BettaFish的段落独立分析）
3. **综合分析** - 重规划Agent综合所有任务的洞察进行决策
4. **去重逻辑** - 自动识别和去除重复的发现
5. **覆盖度计算** - 实时计算分析的完整性（维度覆盖、数据覆盖、问题覆盖）
6. **根因识别** - 自动识别是否已找到根本原因
7. **分析路径追踪** - 记录完整的分析路径（树状结构）

#### 验收标准

1. WHEN THE System执行多轮分析, THE System SHALL为每个任务独立累积洞察
2. WHEN THE ReplannerAgent决策, THE System SHALL综合所有任务的洞察结果
3. WHEN THE System发现重复的洞察, THE System SHALL自动去重并保留最详细的版本
4. WHEN THE System计算覆盖度, THE System SHALL提供维度覆盖度、数据值覆盖度和问题覆盖度三个指标
5. WHEN THE System识别到根本原因, THE System SHALL标记为root_cause并停止继续分析
6. WHEN THE System完成分析, THE System SHALL提供完整的分析路径树状图
7. THE System SHALL确保累积结果的准确率 >= 95%
8. THE System SHALL确保去重逻辑的准确率 >= 90%
9. THE System SHALL确保覆盖度计算的准确率 >= 85%

#### 数据结构设计

**单个任务的累积结果**：
```
TaskInsight {
  task_id: string
  question: string
  findings: List[Dict]
  accumulated_context: AccumulatedInsights
}
```

**累积结果数据结构**：
```
AccumulatedInsights {
  rounds: List[AnalysisRound]
  key_findings: List[Dict]  // 去重后的关键发现
  anomalies: List[Dict]  // 去重后的异常
  root_causes: List[Dict]  // 已识别的根因
  analysis_tree: Dict  // 树状分析路径
  coverage: {
    dimension_coverage: float,  // 维度覆盖度
    value_coverage: float,  // 数据值覆盖度
    question_coverage: float  // 问题覆盖度
  }
  drill_down_depth: int  // 下钻深度
  analyzed_dimensions: Set[string]  // 已分析的维度
}
```

#### 累积策略

**多任务并行场景**：
1. 每个任务独立分析，独立累积
2. 重规划Agent接收所有任务的洞察
3. 综合分析所有维度的发现
4. 进行关联分析，生成聚焦问题

**单任务分片场景**：
1. 分片1 → 洞察 → 累积v1
2. 分片2 → 洞察（传入v1）→ 累积v2
3. 分片3 → 洞察（传入v2）→ 累积v3

---

### 需求2: 分段处理 + 结果累积

**用户故事**: 作为系统，当查询结果数据量过大时，我需要自动分段处理并累积分析结果，确保洞察质量不受token限制影响

#### 核心功能

1. **智能分段** - 代码计算数据token大小，自动决定是否需要分段
2. **分段策略** - 支持多种分段策略（按TOP N、按时间窗口、按维度值）
3. **累积分析** - 洞察Agent逐段分析，每段都能看到之前的累积结果
4. **智能合并** - 自动合并分段洞察，去重和优先级排序
5. **上下文传递** - 每段分析时传递累积上下文，保持连贯性
6. **质量保证** - 确保分段分析质量不低于整体分析

#### 验收标准

1. WHEN THE QueryExecutor返回的数据行数 > 1000, THE System SHALL自动触发分段处理
2. WHEN THE System计算数据token大小 > 4000, THE System SHALL自动触发分段处理
3. WHEN THE System执行分段处理, THE System SHALL选择最合适的分段策略（TOP N优先）
4. WHEN THE InsightAgent分析每个分段, THE System SHALL传递累积上下文
5. WHEN THE System合并分段洞察, THE System SHALL去除重复发现并按重要性排序
6. THE System SHALL支持10000+行数据的分析
7. THE System SHALL确保分段洞察质量 >= 整体分析质量的90%
8. THE System SHALL确保分段处理耗时 <= 整体处理耗时的120%

#### 分段策略

**策略1: 按TOP N分段（默认）**
```python
# 适用场景：分析维度值的贡献度
# 示例：分析100个城市的销售额
segments = [
    {"name": "TOP 20", "filter": "TOP 20 by sales", "priority": "high"},
    {"name": "RANK 21-50", "filter": "RANK 21-50 by sales", "priority": "medium"},
    {"name": "OTHERS", "filter": "RANK 51+", "priority": "low"}
]
```

**策略2: 按时间窗口分段**
```python
# 适用场景：分析长时间跨度的数据
# 示例：分析全年数据
segments = [
    {"name": "Q1", "time_range": "2024-01 to 2024-03"},
    {"name": "Q2", "time_range": "2024-04 to 2024-06"},
    {"name": "Q3", "time_range": "2024-07 to 2024-09"},
    {"name": "Q4", "time_range": "2024-10 to 2024-12"}
]
```

**策略3: 按维度值分段**
```python
# 适用场景：分析多个维度组合
# 示例：分析各地区各产品类别
segments = [
    {"name": "华东", "filter": "地区=华东"},
    {"name": "华南", "filter": "地区=华南"},
    {"name": "华北", "filter": "地区=华北"}
]
```

---

### 需求3: 多任务并行执行和调度

**用户故事**: 作为业务数据分析师，当问题可能有多个原因时，我希望系统能并行分析多个维度，快速找到根因

#### 核心功能

1. **多问题生成** - 重规划Agent生成多个分析问题（类似Tableau Pulse）
2. **依赖分析** - 任务调度器分析任务间的依赖关系
3. **异步并行执行** - 无依赖任务全部异步并行执行
4. **动态调度** - 超过最大并发数时，动态调度（一个完成，启动下一个）
5. **独立洞察** - 每个任务独立分析并累积结果
6. **综合决策** - 重规划Agent综合所有洞察进行关联分析
7. **资源控制** - 限制最大并发数（3个），避免资源耗尽

#### 验收标准

1. WHEN THE ReplannerAgent生成多个问题, THE System SHALL标记每个问题的优先级和依赖关系
2. WHEN THE TaskScheduler分析依赖, THE System SHALL识别可并行执行的任务
3. WHEN THE System执行无依赖任务, THE System SHALL全部异步并行执行（受限于最大并发数3）
4. WHEN THE System执行有依赖任务, THE System SHALL按依赖顺序执行
5. WHEN THE 并发任务数 > 3, THE System SHALL动态调度（一个完成，启动下一个）
6. WHEN THE InsightAgent分析, THE System SHALL为每个任务独立累积结果
7. WHEN THE ReplannerAgent决策, THE System SHALL综合所有任务的洞察进行关联分析
8. THE System SHALL确保并行执行时间 <= 串行执行时间的60%
9. THE System SHALL确保最大并发数 <= 3

#### 并行执行策略

**策略1: 无依赖任务 - 全部异步并行**
```
3个任务，无依赖：
- Task 1: 华东各城市利润率 ┐
- Task 2: 华东各产品利润率 ├─ 异步并行（最多3个）
- Task 3: 华东折扣情况     ┘

执行时间：max(task1, task2, task3) ≈ 7秒
（而不是串行的 21秒）
```

**策略2: 有依赖任务 - 按依赖顺序**
```
同比分析（需要两个时间段）：
- Task 1: 2024年数据 ┐
- Task 2: 2023年数据 ├─ 并行执行
                     ┘
         ↓
数据处理器：合并并计算同比
         ↓
洞察Agent：分析同比结果
```

**策略3: 超过最大并发数 - 动态调度**
```
4个任务，最大并发3：
时间轴：
0s: 启动 task1, task2, task3
5s: task1完成 → 立即启动task4
6s: task2完成
7s: task3完成
9s: task4完成

总耗时：9秒（而不是串行的20秒）
```

#### 洞察综合策略

**多任务洞察处理**：
1. 每个任务独立洞察并累积（参考BettaFish的段落独立分析）
2. 重规划Agent接收所有任务的洞察结果
3. 综合分析不同维度的发现
4. 进行关联分析（如：上海 + 家具类 + 折扣高 → 上海家具类折扣过高）
5. 生成聚焦问题

**示例**：
```
Task 1洞察：上海利润率3%（城市维度）
Task 2洞察：家具类利润低（产品维度）
Task 3洞察：折扣率40%（折扣维度）

重规划Agent综合分析：
→ 关联：上海 + 家具类 + 折扣高
→ 假设：上海家具类折扣过高导致利润低
→ 聚焦问题："上海家具类的折扣率是多少？"
```

---


### 需求4: 数据处理器（纯代码组件）

**用户故事**: 作为系统，我需要处理查询结果，进行质量检查、标准化和聚合计算，为洞察分析提供高质量的数据

#### 核心功能

1. **数据质量检查** - 检查空值、异常值、数据一致性
2. **数据标准化** - 统一字段格式、统一数值精度、添加元信息
3. **聚合计算（VDS无法处理的）** - 同比、环比、增长率、占比等计算
4. **任务依赖处理** - 合并有依赖关系的任务数据（如同比需要两个时间段）
5. **数据分段检查** - 检查数据量和token大小，标记是否需要分段
6. **数据合并（按需）** - 当任务有依赖时，合并相关数据

#### 重要说明：职责边界

**数据处理器负责**：
- ✅ 数据质量检查和标准化
- ✅ VDS无法处理的聚合计算（同比、环比、增长率）
- ✅ 处理任务依赖（合并依赖任务的数据）
- ✅ 数据分段检查

**数据处理器不负责**：
- ❌ 洞察合并（由重规划Agent综合所有洞察）
- ❌ 业务分析（由洞察Agent负责）

#### 聚合计算详解

**VDS无法处理的计算**：
1. **同比计算**：需要两个时间段的数据，计算公式：(当期 - 上期) / 上期 × 100%
2. **环比计算**：需要连续时间段的数据，计算公式：(本期 - 上期) / 上期 × 100%
3. **增长率计算**：需要起始和结束数据，计算公式：(结束值 - 起始值) / 起始值 × 100%
4. **占比计算**：需要部分和总计数据，计算公式：部分值 / 总计值 × 100%

#### 验收标准

1. WHEN THE System检查数据质量, THE System SHALL识别空值、异常值和不一致数据
2. WHEN THE System标准化数据, THE System SHALL统一字段格式和数值精度
3. WHEN THE System处理同比任务, THE System SHALL正确合并两个时间段数据并计算同比
4. WHEN THE System处理环比任务, THE System SHALL正确计算环比增长率
5. WHEN THE System检查数据量, THE System SHALL标记是否需要分段（>1000行或>4000 tokens）
6. THE System SHALL确保聚合计算准确率 = 100%
7. THE System SHALL确保数据质量检查准确率 >= 95%
8. THE System SHALL确保处理耗时 <= 1秒（1000行以内）

---

### 需求5: 智能问题推荐增强

**用户故事**: 作为业务数据分析师，我希望系统推荐的后续问题有明确的理由和优先级，帮助我快速选择

#### 核心功能

1. **推荐理由** - 每个推荐问题都有明确的理由
2. **优先级排序** - 基于重要性和可行性排序
3. **一键执行** - 用户点击即可执行推荐问题
4. **多维度推荐** - 支持下钻、切换维度、时间调整等多种类型

#### 验收标准

1. WHEN THE ReplannerAgent生成推荐问题, THE System SHALL为每个问题提供推荐理由
2. WHEN THE System排序推荐问题, THE System SHALL基于优先级排序（high → medium → low）
3. WHEN THE User点击推荐问题, THE System SHALL自动执行该问题的分析
4. THE System SHALL确保推荐问题相关性 >= 90%
5. THE System SHALL确保用户采纳率 >= 60%
6. THE System SHALL确保推荐理由清晰度 >= 85%

---

### 需求6: 上下文管理和传递机制（借鉴BettaFish）

**用户故事**: 作为系统，我需要高效地管理和传递累积上下文，确保每个Agent都能获得必要的历史信息，同时避免token超限

#### 核心功能

1. **结构化状态管理** - 使用dataclass定义清晰的状态结构
2. **上下文传递策略** - 在不同Agent间传递累积上下文
3. **Prompt中的上下文** - 在prompt中明确传递累积状态
4. **上下文压缩** - 智能压缩历史信息，避免token超限
5. **搜索历史管理** - 记录所有查询和结果，避免重复
6. **分段上下文传递** - 分段处理时传递累积上下文

#### 设计借鉴（BettaFish）

**BettaFish的优秀设计**：
1. **结构化状态**：
   ```python
   @dataclass
   class Research:
       search_history: List[Search]  # 所有搜索历史
       latest_summary: str           # 最新总结
       reflection_iteration: int     # 反思次数
       is_completed: bool            # 是否完成
   ```

2. **上下文传递**：
   - 首次分析：传递 `title` + `content` + `search_results`
   - 反思分析：传递 `title` + `content` + `paragraph_latest_state` + `search_results`
   - 最终报告：传递所有段落的 `paragraph_latest_state`

3. **Prompt设计**：
   ```python
   reflection_summary_input = {
       "title": paragraph.title,
       "content": paragraph.content,
       "search_query": search_query,
       "search_results": format_search_results_for_prompt(
           search_results, self.config.MAX_CONTENT_LENGTH
       ),
       "paragraph_latest_state": paragraph.research.latest_summary  # 关键！
   }
   ```

#### 我们的实现方案

**1. 状态数据结构**：
```python
@dataclass
class TaskInsight:
    """单个任务的洞察累积"""
    task_id: str
    question: str
    query_results: List[Dict]      # 查询结果
    insights_history: List[str]    # 洞察历史（分段累积）
    latest_insight: str            # 最新洞察
    chunk_count: int               # 分段数量
    is_completed: bool             # 是否完成

@dataclass
class AnalysisState:
    """整体分析状态"""
    original_question: str
    task_insights: List[TaskInsight]  # 所有任务的洞察
    replanner_decisions: List[Dict]   # 重规划决策历史
    root_cause_found: bool
    analysis_path: List[str]          # 分析路径
```

**2. 上下文传递策略**：

| Agent | 输入上下文 | 输出 |
|-------|-----------|------|
| 洞察Agent（首次） | `question` + `query_results` | `initial_insight` |
| 洞察Agent（分段） | `question` + `query_results_chunk` + `accumulated_insights` | `updated_insight` |
| 重规划Agent | `original_question` + `all_task_insights` + `previous_decisions` | `next_action` |

**3. Prompt中的上下文**：
```python
# 洞察Agent - 分段分析时
insight_prompt = f"""
你正在分析问题：{task.question}

【累积上下文】
之前已分析的数据段：{task.chunk_count}
已发现的洞察：
{task.latest_insight}

【当前数据段】
{current_chunk_data}

请基于累积上下文，分析当前数据段，更新洞察。
"""

# 重规划Agent - 综合决策时
replanner_prompt = f"""
原始问题：{state.original_question}

【所有维度的洞察】
{format_all_task_insights(state.task_insights)}

【之前的决策历史】
{format_decision_history(state.replanner_decisions)}

请综合所有洞察，决定下一步行动。
"""
```

**4. 上下文压缩策略**：
- **搜索结果压缩**：只保留关键字段（title, key_metrics），限制长度
- **洞察历史压缩**：只保留最新的洞察，历史洞察仅保留摘要
- **决策历史压缩**：只保留最近3轮的决策
- **Token计算**：实时计算token大小，超限时触发压缩

**5. 搜索历史管理**：
```python
@dataclass
class QueryHistory:
    """查询历史记录"""
    query_text: str
    query_spec: Dict
    results_summary: str  # 结果摘要（不保存完整结果）
    timestamp: datetime
    
def avoid_duplicate_query(new_query: str, history: List[QueryHistory]) -> bool:
    """检查是否重复查询"""
    for past_query in history:
        if similarity(new_query, past_query.query_text) > 0.9:
            return True
    return False
```

#### 验收标准

1. WHEN THE System管理状态, THE System SHALL使用结构化的dataclass定义
2. WHEN THE InsightAgent分析分段数据, THE System SHALL传递累积上下文
3. WHEN THE ReplannerAgent综合决策, THE System SHALL传递所有任务的洞察
4. WHEN THE System计算token大小 > 8000, THE System SHALL触发上下文压缩
5. WHEN THE System检测到重复查询, THE System SHALL避免重复执行
6. THE System SHALL确保上下文传递准确率 = 100%
7. THE System SHALL确保压缩后信息保留率 >= 85%
8. THE System SHALL确保重复查询检测准确率 >= 90%

#### 关键设计原则

1. **明确传递** - 在prompt中明确标注"累积上下文"部分
2. **结构化** - 使用dataclass而不是字典，类型安全
3. **分层管理** - 任务级别独立累积，系统级别综合决策
4. **智能压缩** - 根据token限制动态压缩，保留关键信息
5. **历史追踪** - 记录完整的分析路径和决策历史

---

## 实施优先级

### P0（立即实施）
1. **需求1**：结果累积机制
2. **需求2**：分段处理 + 结果累积
3. **需求6**：上下文管理和传递机制（基础设施）

### P1（近期实施）
3. **需求3**：多问题并行分析
4. **需求4**：智能任务调度
5. **需求5**：数据处理增强

---

## 技术架构说明

### 整体架构

```
用户提问
  ↓
问题理解Agent
  ↓
任务规划Agent（生成查询规格）
  ↓
任务调度器（分析依赖，调度执行）
  ├─ 查询构建器（纯代码）
  ├─ 查询执行器
  ├─ 统计检测器（纯代码）
  └─ 数据处理器（纯代码）
  ↓
洞察Agent（并行分析，独立累积）
  ↓
重规划Agent（综合所有洞察，决策）
  ├─ 找到根因 → 总结Agent
  └─ 需要继续 → 回到任务规划Agent
```

### 关键组件职责

**任务调度器**：
- 接收多个问题
- 分析依赖关系
- 异步并行调度
- 动态资源控制
- 收集所有结果

**数据处理器**：
- 数据质量检查
- 数据标准化
- 聚合计算（同比、环比等）
- 任务依赖处理
- 数据分段检查

**洞察Agent**：
- 独立分析每个任务
- 独立累积结果
- 支持分段累积

**重规划Agent**：
- 综合所有洞察
- 关联分析
- 生成聚焦问题
- 决定是否继续

---

## 参考项目

本需求文档参考了以下优秀项目的设计思想：

1. **BettaFish** - 独立段落分析、反思循环、状态管理
2. **Tableau Pulse** - 多问题推荐、智能叙述
3. **ThoughtSpot AI** - 智能问题推荐、Follow-up Questions

---

**需求文档版本**: v1.0
**最后更新**: 2025-01-XX
**文档状态**: 待审核


