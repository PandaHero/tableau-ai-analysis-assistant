# Tableau Assistant 系统架构和流程完整梳理

## 📋 目录

1. [系统整体架构](#1-系统整体架构)
2. [核心组件详解](#2-核心组件详解)
3. [完整执行流程](#3-完整执行流程)
4. [累积洞察机制](#4-累积洞察机制)
5. [重规划机制](#5-重规划机制)
6. [查询结果缓存机制](#6-查询结果缓存机制)
7. [数据流转](#7-数据流转)
8. [关键问题核对](#8-关键问题核对)

---

## 1. 系统整体架构

### 1.1 当前架构（已有）

```
用户提问
    ↓
┌─────────────────────────────────────────────────┐
│         VizQL Workflow (LangGraph)              │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │Question  │→│Understanding│→│ Planning │     │
│  │Boost     │  │  Agent    │  │  Agent   │     │
│  │(可选)    │  │           │  │          │     │
│  └──────────┘  └──────────┘  └──────────┘     │
│                                     ↓            │
│                          生成 QuerySubTask 列表 │
│                                     ↓            │
│                          ❌ 手动调用执行         │
│                                                  │
└─────────────────────────────────────────────────┘
         ↓
    返回结果
```

**当前问题**：
- ❌ QuerySubTask 生成后需要手动调用 QueryExecutor
- ❌ 没有并行执行机制
- ❌ 没有查询结果缓存
- ❌ 重规划时需要重新执行所有查询
- ❌ 没有累积洞察机制



### 1.2 增强后的架构（目标）

```
用户提问
    ↓
┌──────────────────────────────────────────────────────────────────┐
│              VizQL Workflow (LangGraph)                          │
│                                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│  │Question  │→│Understanding│→│ Planning │                      │
│  │Boost     │  │  Agent    │  │  Agent   │                      │
│  │(可选)    │  │           │  │          │                      │
│  └──────────┘  └──────────┘  └──────────┘                      │
│                                     ↓                             │
│                          生成 QuerySubTask 列表                  │
│                          (r1_q0, r1_q1, r1_q2...)               │
│                                     ↓                             │
│  ┌─────────────────────────────────────────────────┐            │
│  │    ✅ 任务调度器 (TaskScheduler) 【新增】       │            │
│  │                                                  │            │
│  │  1. 依赖分析（拓扑排序）                        │            │
│  │  2. 并行执行（asyncio，最多3个并发）            │            │
│  │  3. 查询结果缓存（1-2小时TTL）                  │            │
│  │  4. 进度跟踪和实时反馈                          │            │
│  │                                                  │            │
│  │  执行流程：                                      │            │
│  │  - 检查缓存 → 缓存命中？返回缓存结果            │            │
│  │  - 缓存未命中 → 调用 QueryExecutor 执行查询    │            │
│  │  - 查询成功 → 缓存结果 → 返回                  │            │
│  │  - 查询失败 → 错误修正 → 重试（最多3次）       │            │
│  └─────────────────────────────────────────────────┘            │
│                                     ↓                             │
│                          收集所有查询结果                        │
│                          {r1_q0: data, r1_q1: data, ...}        │
│                                     ↓                             │
│  ┌─────────────────────────────────────────────────┐            │
│  │    ✅ 累积洞察分析 【新增】                      │            │
│  │                                                  │            │
│  │  并行启动多个 Insight Agent：                   │            │
│  │  - Insight Agent 1 分析 r1_q0 → 洞察1          │            │
│  │  - Insight Agent 2 分析 r1_q1 → 洞察2          │            │
│  │  - Insight Agent 3 分析 r1_q2 → 洞察3          │            │
│  │                                                  │            │
│  │  Insight Coordinator 智能合成：                 │            │
│  │  - 识别关键发现                                 │            │
│  │  - 对比分析                                     │            │
│  │  - 合成最终洞察                                 │            │
│  └─────────────────────────────────────────────────┘            │
│                                     ↓                             │
│  ┌──────────────┐                                                │
│  │Replan Agent  │ 判断是否充分回答问题？                        │
│  └──────────────┘                                                │
│         ↓                    ↓                                    │
│        是                   否                                    │
│         ↓                    ↓                                    │
│    返回结果          生成新问题 → 第2轮（重规划）                │
│                      (复用第1轮的查询缓存)                       │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

**关键改进**：
- ✅ 任务调度器自动执行所有 QuerySubTask
- ✅ 并行执行（最多3个并发）
- ✅ 查询结果缓存（1-2小时TTL）
- ✅ 累积洞察机制（多 AI 并行分析 + 智能合成）
- ✅ 重规划时复用缓存（避免重复查询）



---

## 2. 核心组件详解

### 2.1 任务调度器 (TaskScheduler)

**位置**：`tableau_assistant/src/components/task_scheduler.py`

**职责**：
1. 接收 QuerySubTask 列表
2. 分析任务依赖关系（`depends_on` 字段）
3. 拓扑排序，确定执行顺序
4. 并行执行独立任务（使用 asyncio.Semaphore 控制并发数）
5. 串行执行有依赖的任务
6. 查询结果缓存（检查缓存 → 执行查询 → 缓存结果）
7. 进度跟踪和实时反馈

**核心方法**：
```python
class TaskScheduler:
    async def schedule_tasks(
        self,
        tasks: List[QuerySubTask],
        progress_callback: Optional[callable] = None
    ) -> List[TaskResult]:
        """
        调度并执行任务
        
        流程：
        1. 分析依赖关系 (_analyze_dependencies)
        2. 拓扑排序 (_topological_sort)
        3. 分批执行 (_execute_batch)
           - 每批内部并行执行（最多3个并发）
           - 批次之间串行执行
        4. 返回所有结果
        """
```

**与现有组件的关系**：
- 使用 `QueryExecutor` 执行单个查询
- 使用 `PersistentStore` 缓存查询结果
- 集成到 `vizql_workflow.py` 中作为新节点



### 2.2 查询结果缓存 (QueryResultCache)

**位置**：在 `PersistentStore` 中扩展

**职责**：
1. 缓存查询结果（基于查询内容的哈希）
2. 支持 TTL（1-2小时）
3. 缓存命中率统计
4. 解决上下文长度问题（通过 task_id 引用）

**缓存键生成**：
```python
def _generate_cache_key(task_id: str, query_spec: Dict) -> str:
    """
    基于查询内容生成哈希键
    
    query_spec 包含：
    - intents: 查询意图列表
    - question_text: 问题文本
    - filters: 筛选器（如果有）
    
    相同的查询内容 → 相同的缓存键
    """
    query_str = json.dumps(query_spec, sort_keys=True)
    hash_obj = hashlib.sha256(query_str.encode())
    return f"query_cache:{hash_obj.hexdigest()}"
```

**缓存流程**：
```
执行查询前：
1. 生成缓存键
2. 从 PersistentStore 查询缓存
3. 检查是否过期（TTL 1-2小时）
4. 缓存命中 → 直接返回结果（0.1s）
5. 缓存未命中 → 执行查询 → 缓存结果 → 返回（5s）
```

**重规划场景的价值**：
```
第1轮：
- r1_q0: 查询华东地区利润率 → 执行查询 → 缓存结果
- r1_q1: 查询华北地区利润率 → 执行查询 → 缓存结果

第2轮（重规划）：
- r2_q0: 查询华东地区利润率（相同查询）→ 缓存命中 → 0.1s
- r2_q1: 查询华东地区销售额（新查询）→ 执行查询 → 5s

节省时间：5s → 0.1s（50x 提升）
```



### 2.3 查询验证和错误修正

**位置**：在 `QueryExecutor` 中扩展

**验证流程**：
```
查询执行前：
1. 验证字段存在性
   - 检查字段是否在元数据中
   - 如果不存在 → 搜索相似字段（difflib.SequenceMatcher）
   - 返回建议

2. 验证聚合函数合法性
   - 检查聚合函数是否适用于字段类型
   - 例如：SUM 只能用于数值字段
   - 如果不合法 → 返回建议的聚合函数

3. Pydantic 结构验证（已有）
   - 所有数据模型都有 Pydantic 验证
   - 自动验证数据类型和必填字段
```

**错误修正流程**：
```
查询执行失败：
1. 捕获错误信息（VDS 返回的错误）
2. 使用 LLM 分析错误原因
3. 生成修正方案
4. 执行修正后的查询

重试策略（最多3次）：
- 第1次：自动修正字段名/聚合函数
- 第2次：使用备选方案（简化查询）
- 第3次：最小化查询（只保留核心字段）
- 超过3次：返回详细错误信息给用户
```

**记录修正信息**：
```sql
CREATE TABLE correction_attempts (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    attempt_number INTEGER,
    strategy_type TEXT,  -- field_replacement, aggregation_change, simplification
    original_plan JSON,
    modified_plan JSON,
    success BOOLEAN,
    error_message TEXT,
    timestamp DATETIME
);
```



### 2.4 上下文智能管理

**位置**：在 `MetadataManager` 和 `BaseAgent` 中扩展

**元数据过滤**：
```python
# 在 MetadataManager 中添加
def filter_by_categories(
    self,
    metadata: Metadata,
    categories: List[str]
) -> Metadata:
    """
    基于 Category 过滤元数据
    
    流程：
    1. 从 Understanding 结果中提取涉及的 Category
       例如：["产品", "地区", "时间"]
    
    2. 只保留相关 Category 的维度字段
       例如：保留 "产品类别"、"地区名称"、"订单日期"
    
    3. 保留所有度量字段
       例如：保留 "销售额"、"利润"、"数量"
    
    4. 记录过滤前后的字段数量
       例如：100 个字段 → 30 个字段（减少 70%）
    """
```

**Token 预算管理**：
```python
# 在 BaseAgent 中添加
def manage_token_budget(
    self,
    contexts: Dict[str, Any],
    total_budget: int = 8000
) -> Dict[str, Any]:
    """
    管理 Token 预算
    
    优先级：
    1. 元数据（优先级 9）- 最多占 40%
    2. 维度层级（优先级 8）- 最多占 30%
    3. 对话历史（优先级 7）- 最多占 20%
    4. 示例（优先级 5）- 最多占 10%
    
    流程：
    1. 使用 tiktoken 计算每个上下文的 Token 数量
    2. 按优先级分配 Token
    3. 如果超出预算，裁剪低优先级上下文
    4. 记录裁剪的内容和原因
    """
```

**对话历史压缩**：
```python
# 在 BaseAgent 中添加
async def compress_history(
    self,
    history: List[Dict]
) -> List[Dict]:
    """
    压缩对话历史
    
    流程：
    1. 保留最近 5 轮完整对话
    2. 将早期对话（5 轮以前）压缩为摘要
    3. 使用 LLM 生成摘要
    4. 摘要长度不超过原内容的 30%
    
    示例：
    原始（10轮对话）：
    - 轮1-5：完整保留
    - 轮6-10：压缩为摘要
    
    压缩后：
    - 摘要："用户询问了销售趋势，发现华东地区表现最差"
    - 轮6-10：完整对话
    """
```



---

## 3. 完整执行流程

### 3.1 第一轮执行流程（无重规划）

```
1. 用户提问："2024年各地区的销售额和利润率对比"
   ↓
2. Question Boost Agent（可选）
   - 优化问题表达
   - 输出：boosted_question
   ↓
3. Understanding Agent
   - 理解用户意图
   - 识别涉及的 Category：["地区", "时间"]
   - 输出：UnderstandingResult {
       question_type: "comparison",
       mentioned_dimensions: ["地区", "订单日期"],
       mentioned_measures: ["销售额", "利润率"],
       categories: ["地区", "时间"]
     }
   ↓
4. MetadataManager（增强）
   - 获取元数据
   - 基于 Category 过滤：只保留 "地区" 和 "时间" 相关的维度字段
   - 过滤前：100 个字段
   - 过滤后：30 个字段（减少 70%）
   ↓
5. Planning Agent
   - 生成查询计划
   - 输出：QueryPlanningResult {
       subtasks: [
         {task_id: "r1_q0", question: "查询各地区2024年销售额"},
         {task_id: "r1_q1", question: "查询各地区2024年利润率"}
       ]
     }
   ↓
6. 任务调度器（新增）
   - 分析依赖关系：r1_q0 和 r1_q1 独立，可以并行
   - 并行执行：
     ├─ r1_q0: 检查缓存 → 未命中 → 执行查询 → 缓存结果 → 返回
     └─ r1_q1: 检查缓存 → 未命中 → 执行查询 → 缓存结果 → 返回
   - 收集结果：{
       r1_q0: {data: [...], row_count: 10},
       r1_q1: {data: [...], row_count: 10}
     }
   ↓
7. 累积洞察分析（新增）
   - 并行启动 Insight Agent：
     ├─ Insight Agent 1 分析 r1_q0 → "华东地区销售额最高（500万）"
     └─ Insight Agent 2 分析 r1_q1 → "华东地区利润率最低（12%）"
   - Insight Coordinator 智能合成：
     "华东地区销售额最高但利润率最低，可能存在价格竞争问题"
   ↓
8. Replan Agent
   - 判断是否充分回答问题？
   - 是 → 进入步骤 9
   - 否 → 生成新问题 → 第2轮（重规划）
   ↓
9. Summary Agent
   - 生成最终报告
   - 输出：FinalReport {
       executive_summary: "...",
       key_findings: [...],
       recommendations: [...]
     }
   ↓
10. 返回结果给用户
```



### 3.2 重规划流程（第2轮）

```
接上面步骤 8：Replan Agent 判断需要重规划

8. Replan Agent
   - 判断：当前洞察不够充分
   - 生成新问题："为什么华东地区利润率最低？"
   ↓
9. 第2轮 - Understanding Agent
   - 理解新问题
   - 识别涉及的 Category：["地区", "产品"]
   ↓
10. 第2轮 - Planning Agent
    - 生成新的查询计划
    - 输出：QueryPlanningResult {
        subtasks: [
          {task_id: "r2_q0", question: "查询华东地区各产品类别的利润率"},
          {task_id: "r2_q1", question: "查询华东地区的成本结构"}
        ]
      }
    ↓
11. 第2轮 - 任务调度器
    - 并行执行：
      ├─ r2_q0: 检查缓存 → 未命中 → 执行查询 → 缓存结果
      └─ r2_q1: 检查缓存 → 未命中 → 执行查询 → 缓存结果
    
    ⚠️ 关键：如果第2轮需要第1轮的数据
    - 例如：r2_q2 需要引用 r1_q0 的结果
    - 通过 task_id 引用：depends_on: ["r1_q0"]
    - 任务调度器从缓存加载 r1_q0 的结果（0.1s，不需要重新查询）
    ↓
12. 第2轮 - 累积洞察分析
    - 分析新的查询结果
    - 结合第1轮的洞察
    - 生成更深入的洞察
    ↓
13. 第2轮 - Replan Agent
    - 判断是否充分回答问题？
    - 是 → 进入 Summary Agent
    - 否 → 第3轮（继续重规划）
    ↓
14. Summary Agent
    - 生成最终报告
    ↓
15. 返回结果给用户
```

**重规划的价值**：
- ✅ 循环迭代直到充分回答问题
- ✅ 通过缓存避免重复查询（150x 提升）
- ✅ 解决上下文长度问题（不需要把所有数据都放在上下文中）



---

## 4. 累积洞察机制

### 4.1 累积洞察的正确理解

**核心概念**：多个 AI 并行分析一批查询结果，然后智能合成洞察

**参考 BettaFish 的实现**：
```python
# BettaFish 的累积洞察流程
def accumulate_insights(query_results: List[QueryResult]):
    """
    累积洞察分析
    
    1. 为每个查询结果启动独立的 Insight Agent
    2. 并行分析（使用 asyncio）
    3. 收集所有洞察
    4. Insight Coordinator 智能合成
    """
    # 并行分析
    insights = await asyncio.gather(*[
        insight_agent.analyze(result)
        for result in query_results
    ])
    
    # 智能合成
    final_insight = insight_coordinator.synthesize(insights)
    
    return final_insight
```

### 4.2 具体示例

**场景**：用户问"2024年各地区的销售额和利润率对比"

**步骤 1：Planning Agent 生成任务**
```python
subtasks = [
    {task_id: "r1_q0", question: "查询华东地区2024年销售额和利润率"},
    {task_id: "r1_q1", question: "查询华北地区2024年销售额和利润率"},
    {task_id: "r1_q2", question: "查询华南地区2024年销售额和利润率"},
    {task_id: "r1_q3", question: "查询全国平均销售额和利润率"}
]
```

**步骤 2：任务调度器并行执行**
```python
results = {
    "r1_q0": {data: [{region: "华东", sales: 500, profit_rate: 0.12}]},
    "r1_q1": {data: [{region: "华北", sales: 400, profit_rate: 0.18}]},
    "r1_q2": {data: [{region: "华南", sales: 450, profit_rate: 0.15}]},
    "r1_q3": {data: [{region: "全国", sales: 450, profit_rate: 0.15}]}
}
```

**步骤 3：累积洞察分析（并行）**
```python
# 并行启动 4 个 Insight Agent
insights = await asyncio.gather(
    insight_agent.analyze(results["r1_q0"]),  # AI宝宝1
    insight_agent.analyze(results["r1_q1"]),  # AI宝宝2
    insight_agent.analyze(results["r1_q2"]),  # AI宝宝3
    insight_agent.analyze(results["r1_q3"])   # AI宝宝4
)

# 输出：
insights = [
    "华东地区销售额最高（500万），但利润率最低（12%）",
    "华北地区销售额适中（400万），利润率最高（18%）",
    "华南地区销售额和利润率都接近平均水平",
    "全国平均销售额450万，平均利润率15%"
]
```

**步骤 4：Insight Coordinator 智能合成**
```python
final_insight = insight_coordinator.synthesize(insights)

# 输出：
final_insight = """
关键发现：
1. 华东地区销售额最高（500万），但利润率最低（12%），低于全国平均3个百分点
2. 华北地区虽然销售额不是最高，但利润率最高（18%），高于全国平均3个百分点
3. 华南地区表现平稳，接近全国平均水平

深度分析：
- 华东地区可能存在价格竞争问题，导致利润率偏低
- 华北地区的盈利能力最强，值得学习其经营策略
- 建议重点关注华东地区的成本结构和定价策略
"""
```



### 4.3 累积洞察与任务调度器的配合

**任务调度器的职责**：
1. 并行执行所有 QuerySubTask
2. 收集所有查询结果
3. 为每个查询结果启动独立的 Insight Agent

**实现方式**：
```python
class TaskScheduler:
    async def schedule_tasks_with_insights(
        self,
        tasks: List[QuerySubTask]
    ) -> Dict[str, Any]:
        """
        调度任务并启动累积洞察分析
        
        流程：
        1. 并行执行所有任务
        2. 收集所有查询结果
        3. 为每个结果启动 Insight Agent
        4. 调用 Insight Coordinator 合成洞察
        """
        # 1. 并行执行任务
        results = await self.schedule_tasks(tasks)
        
        # 2. 为每个结果启动 Insight Agent
        insights = await asyncio.gather(*[
            self._analyze_single_result(result)
            for result in results
        ])
        
        # 3. 智能合成洞察
        final_insight = await self._synthesize_insights(insights)
        
        return {
            "results": results,
            "insights": insights,
            "final_insight": final_insight
        }
    
    async def _analyze_single_result(self, result: TaskResult):
        """分析单个查询结果"""
        # 调用 Insight Agent
        insight_agent = InsightAgent()
        return await insight_agent.analyze(result)
    
    async def _synthesize_insights(self, insights: List[str]):
        """智能合成洞察"""
        # 调用 Insight Coordinator
        coordinator = InsightCoordinator()
        return await coordinator.synthesize(insights)
```

**集成到工作流**：
```python
# 在 vizql_workflow.py 中
def create_vizql_workflow():
    graph = StateGraph(...)
    
    # 添加任务调度节点
    graph.add_node("task_scheduling", task_scheduling_node)
    
    # 添加累积洞察节点
    graph.add_node("accumulate_insights", accumulate_insights_node)
    
    # 连接节点
    graph.add_edge("planning", "task_scheduling")
    graph.add_edge("task_scheduling", "accumulate_insights")
    graph.add_edge("accumulate_insights", "replan")
```



---

## 5. 重规划机制

### 5.1 重规划的触发条件

**Replan Agent 判断是否需要重规划**：
```python
class ReplanAgent:
    async def should_replan(
        self,
        question: str,
        insights: List[str],
        current_round: int,
        max_rounds: int = 3
    ) -> ReplanDecision:
        """
        判断是否需要重规划
        
        判断标准：
        1. 是否充分回答了用户的问题？
        2. 是否还有未解答的疑问？
        3. 是否需要更深入的分析？
        4. 是否达到最大轮次限制？
        
        返回：
        - need_replan: bool
        - new_question: str（如果需要重规划）
        - reason: str（重规划原因）
        """
```

### 5.2 重规划流程

```
第1轮：
用户问题："2024年各地区的销售额和利润率对比"
    ↓
Understanding → Planning → 任务调度器 → 累积洞察
    ↓
洞察："华东地区销售额最高但利润率最低"
    ↓
Replan Agent 判断：
- 问题：为什么华东地区利润率最低？
- 决定：需要重规划
- 新问题："分析华东地区的成本结构和定价策略"
    ↓
第2轮：
新问题："分析华东地区的成本结构和定价策略"
    ↓
Understanding → Planning → 任务调度器 → 累积洞察
    ↓
任务调度器：
- r2_q0: 查询华东地区各产品类别的成本
- r2_q1: 查询华东地区的定价策略
- r2_q2: 对比华东和华北的成本差异（依赖 r1_q0 和 r1_q1）
    ↓
执行 r2_q2 时：
- depends_on: ["r1_q0", "r1_q1"]
- 任务调度器从缓存加载 r1_q0 和 r1_q1 的结果（0.1s）
- 不需要重新查询（节省 10s）
    ↓
累积洞察：
- 分析新的查询结果
- 结合第1轮的洞察
- 生成更深入的洞察："华东地区成本较高，主要是物流成本"
    ↓
Replan Agent 判断：
- 问题已充分回答
- 决定：不需要重规划
    ↓
Summary Agent → 返回最终报告
```

### 5.3 任务 ID 设计

**格式**：`r{round}_q{index}`

**示例**：
```
第1轮：
- r1_q0: 查询华东地区销售额
- r1_q1: 查询华北地区销售额
- r1_q2: 查询华南地区销售额

第2轮：
- r2_q0: 查询华东地区成本
- r2_q1: 查询华东地区定价
- r2_q2: 对比华东和华北（依赖 r1_q0, r1_q1）

第3轮：
- r3_q0: ...
```

**避免 ID 冲突**：
- 每轮的任务 ID 都带有轮次前缀（r1_, r2_, r3_）
- 即使查询内容相同，不同轮次的 ID 也不同
- 但查询内容相同时，缓存键相同，可以复用缓存



---

## 6. 查询结果缓存机制

### 6.1 缓存的核心价值

**解决的问题**：
1. **重规划场景**：避免重复查询（150x 提升）
2. **上下文长度问题**：不需要把所有数据都放在上下文中
3. **多轮对话**：支持用户在会话中多次引用历史数据

### 6.2 缓存键设计

**基于查询内容的哈希**：
```python
def _generate_cache_key(task_id: str, query_spec: Dict) -> str:
    """
    生成缓存键
    
    query_spec 包含：
    - intents: 查询意图列表
    - question_text: 问题文本
    - filters: 筛选器
    
    相同的查询内容 → 相同的缓存键
    不同的 task_id，但查询内容相同 → 相同的缓存键
    """
    # 提取查询内容
    query_content = {
        "intents": query_spec["intents"],
        "question_text": query_spec["question_text"],
        "filters": query_spec.get("filters", [])
    }
    
    # 序列化为稳定的字符串
    query_str = json.dumps(query_content, sort_keys=True)
    
    # 生成哈希
    hash_obj = hashlib.sha256(query_str.encode())
    return f"query_cache:{hash_obj.hexdigest()}"
```

**示例**：
```python
# 第1轮
task_id = "r1_q0"
query_spec = {
    "intents": [{"field": "销售额", "aggregation": "SUM"}],
    "question_text": "查询华东地区销售额"
}
cache_key = "query_cache:abc123..."

# 第2轮（相同查询）
task_id = "r2_q5"  # 不同的 task_id
query_spec = {
    "intents": [{"field": "销售额", "aggregation": "SUM"}],
    "question_text": "查询华东地区销售额"  # 相同的查询内容
}
cache_key = "query_cache:abc123..."  # 相同的缓存键！
```

### 6.3 缓存流程

**执行查询时**：
```python
async def execute_with_cache(task_id: str, query_spec: Dict):
    # 1. 生成缓存键
    cache_key = _generate_cache_key(task_id, query_spec)
    
    # 2. 检查缓存
    cached_result = await cache.get(cache_key)
    if cached_result:
        # 检查是否过期（TTL 1-2小时）
        if not is_expired(cached_result):
            print(f"✓ 缓存命中: {task_id} (0.1s)")
            return cached_result
    
    # 3. 缓存未命中，执行查询
    print(f"✗ 缓存未命中: {task_id}，执行查询...")
    result = await query_executor.execute(query_spec)
    
    # 4. 缓存结果
    await cache.set(cache_key, result, ttl=7200)  # 2小时
    
    print(f"✓ 查询完成: {task_id} (5s)")
    return result
```

### 6.4 缓存数据结构

**SQLite 表结构**：
```sql
CREATE TABLE query_cache (
    cache_key TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    query_spec JSON NOT NULL,
    result JSON NOT NULL,
    timestamp DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,
    hit_count INTEGER DEFAULT 0
);

CREATE INDEX idx_expires_at ON query_cache(expires_at);
CREATE INDEX idx_task_id ON query_cache(task_id);
```

**缓存记录示例**：
```json
{
    "cache_key": "query_cache:abc123...",
    "task_id": "r1_q0",
    "query_spec": {
        "intents": [...],
        "question_text": "查询华东地区销售额"
    },
    "result": {
        "data": [...],
        "row_count": 10
    },
    "timestamp": "2025-11-20 10:00:00",
    "expires_at": "2025-11-20 12:00:00",
    "hit_count": 3
}
```

### 6.5 缓存统计

**记录缓存命中率**：
```python
class CacheStats:
    def __init__(self):
        self.hits = 0
        self.misses = 0
    
    def record_hit(self):
        self.hits += 1
    
    def record_miss(self):
        self.misses += 1
    
    def get_hit_rate(self) -> float:
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total

# 使用
stats = CacheStats()
# ... 执行查询 ...
print(f"缓存命中率: {stats.get_hit_rate():.2%}")
# 输出：缓存命中率: 65.00%
```



---

## 7. 数据流转

### 7.1 State 数据结构

**VizQLState**（LangGraph 状态）：
```python
class VizQLState(TypedDict):
    # 输入
    question: str
    boosted_question: Optional[str]
    
    # Understanding 结果
    understanding: Optional[UnderstandingResult]
    categories: Optional[List[str]]  # 新增：涉及的 Category
    
    # 元数据（过滤后）
    metadata: Optional[Metadata]
    dimension_hierarchy: Optional[Dict]
    
    # Planning 结果
    query_plan: Optional[QueryPlanningResult]
    subtasks: Optional[List[QuerySubTask]]
    
    # 任务调度结果（新增）
    task_results: Optional[Dict[str, TaskResult]]
    
    # 累积洞察结果（新增）
    insights: Optional[List[str]]
    final_insight: Optional[str]
    
    # 重规划
    current_round: int
    replan_decision: Optional[ReplanDecision]
    
    # 最终报告
    final_report: Optional[FinalReport]
```

### 7.2 数据流转示例

```
1. 用户输入
   question: "2024年各地区的销售额和利润率对比"
   ↓
2. Understanding Agent
   understanding: {
       question_type: "comparison",
       mentioned_dimensions: ["地区", "订单日期"],
       mentioned_measures: ["销售额", "利润率"],
       categories: ["地区", "时间"]  # 新增
   }
   ↓
3. MetadataManager（过滤）
   metadata: {
       fields: [
           // 只保留 "地区" 和 "时间" 相关的字段
           {name: "地区名称", category: "地区"},
           {name: "订单日期", category: "时间"},
           {name: "销售额", role: "measure"},
           {name: "利润率", role: "measure"}
       ]
   }
   ↓
4. Planning Agent
   query_plan: {
       subtasks: [
           {task_id: "r1_q0", question: "查询各地区2024年销售额"},
           {task_id: "r1_q1", question: "查询各地区2024年利润率"}
       ]
   }
   ↓
5. 任务调度器
   task_results: {
       "r1_q0": {
           success: true,
           data: [...],
           cached: false,
           execution_time: 5.2
       },
       "r1_q1": {
           success: true,
           data: [...],
           cached: false,
           execution_time: 4.8
       }
   }
   ↓
6. 累积洞察
   insights: [
       "华东地区销售额最高（500万），但利润率最低（12%）",
       "华北地区销售额适中（400万），利润率最高（18%）"
   ]
   final_insight: "华东地区销售额最高但利润率最低，可能存在价格竞争问题"
   ↓
7. Replan Agent
   replan_decision: {
       need_replan: true,
       new_question: "分析华东地区的成本结构",
       reason: "需要深入分析利润率低的原因"
   }
   current_round: 2  # 进入第2轮
   ↓
8. 第2轮...
```



---

## 8. 关键问题核对

### 8.1 任务调度器

**Q1: 任务调度器是只调度查询执行器吗？**
- ❌ 不是！任务调度器调度所有 QuerySubTask
- ✅ QuerySubTask 可以包含各种类型的任务：
  - 查询任务（调用 QueryExecutor）
  - 数据处理任务（调用 DataProcessor）
  - 日期计算任务（调用 DateUtils）
  - 其他任务...

**Q2: 任务调度器如何与累积洞察配合？**
- ✅ 任务调度器执行所有任务 → 收集所有结果
- ✅ 为每个结果启动独立的 Insight Agent（并行）
- ✅ Insight Coordinator 智能合成所有洞察
- ✅ 返回最终洞察给 Replan Agent

**Q3: 任务调度器如何处理依赖关系？**
- ✅ 分析 `depends_on` 字段
- ✅ 拓扑排序，确定执行顺序
- ✅ 独立任务并行执行（最多3个并发）
- ✅ 有依赖的任务串行执行

### 8.2 查询结果缓存

**Q1: 缓存键是基于什么生成的？**
- ✅ 基于查询内容的哈希（intents + question_text + filters）
- ✅ 不是基于 task_id（因为不同轮次的 task_id 不同）
- ✅ 相同的查询内容 → 相同的缓存键 → 可以复用缓存

**Q2: 缓存如何解决上下文长度问题？**
- ✅ 不需要把所有查询结果都放在上下文中
- ✅ 通过 task_id 引用之前的查询结果
- ✅ 只在需要时从缓存加载特定的查询结果
- ✅ 大幅减少上下文长度，支持更多轮对话

**Q3: 重规划时如何复用缓存？**
- ✅ 第2轮的任务可能依赖第1轮的结果
- ✅ 通过 `depends_on: ["r1_q0"]` 声明依赖
- ✅ 任务调度器从缓存加载 r1_q0 的结果（0.1s）
- ✅ 不需要重新查询（节省 5s，50x 提升）

### 8.3 累积洞察

**Q1: 累积洞察是什么？**
- ✅ 多个 AI 并行分析一批查询结果
- ✅ 每个 AI 分析一个查询结果 → 生成一个洞察
- ✅ Insight Coordinator 智能合成所有洞察 → 生成最终洞察
- ❌ 不是单个 AI 分析单个查询结果

**Q2: 累积洞察与任务调度器如何配合？**
- ✅ 任务调度器执行所有任务 → 收集所有结果
- ✅ 为每个结果启动独立的 Insight Agent
- ✅ 并行分析（使用 asyncio）
- ✅ Insight Coordinator 智能合成

**Q3: 累积洞察与重规划如何配合？**
- ✅ 第1轮：累积洞察分析 → Replan Agent 判断
- ✅ 如果需要重规划 → 生成新问题 → 第2轮
- ✅ 第2轮：累积洞察分析 → 结合第1轮的洞察 → 更深入的洞察
- ✅ 循环直到充分回答问题

### 8.4 上下文管理

**Q1: 上下文提供器是什么？**
- ❌ 不是 LangGraph 的 Context（那是不可变的运行时上下文）
- ✅ 是为 LLM 提供上下文数据的组件
- ✅ 包括：元数据、维度层级、对话历史、示例等
- ✅ 基于现有的 Store 和 MetadataManager

**Q2: 如何优化上下文？**
- ✅ 元数据过滤：基于 Category 只保留相关字段
- ✅ Token 预算管理：按优先级分配 Token
- ✅ 对话历史压缩：保留最近5轮，压缩早期对话
- ✅ 使用 tiktoken 准确计算 Token 数量

### 8.5 工具注册表

**Q1: 需要工具注册表吗？**
- ❌ 不需要！你们已经有 MetadataManager、QueryExecutor 等组件
- ✅ 这些组件已经提供了所有需要的功能
- ✅ 不需要额外的工具注册表来管理它们

**Q2: 需要查询验证器吗？**
- ❌ 不需要复杂的验证器！
- ✅ Pydantic 已经提供了结构验证
- ✅ 只需要在 QueryExecutor 中添加简单的验证逻辑：
  - 字段存在性验证
  - 聚合函数合法性验证
  - 使用 difflib 查找相似字段



---

## 9. 总结：核心改进点

### 9.1 四大核心功能

1. **任务调度器与查询结果缓存**
   - ✅ 自动调度执行所有 QuerySubTask
   - ✅ 并行执行（最多3个并发）
   - ✅ 查询结果缓存（1-2小时TTL）
   - ✅ 重规划时复用缓存（150x 提升）
   - ✅ 解决上下文长度问题

2. **累积洞察机制**
   - ✅ 多个 AI 并行分析一批查询结果
   - ✅ Insight Coordinator 智能合成洞察
   - ✅ 配合任务调度器自动执行
   - ✅ 支持重规划场景

3. **查询验证和错误修正**
   - ✅ 查询前验证（字段存在性、聚合函数）
   - ✅ 查询失败后自动修正
   - ✅ 智能重试（最多3次）
   - ✅ 提升查询成功率 20-30%

4. **上下文智能管理**
   - ✅ 基于 Category 过滤元数据
   - ✅ Token 预算管理（8000 tokens）
   - ✅ 对话历史压缩（保留最近5轮）
   - ✅ 减少 Token 消耗 50%

### 9.2 关键技术点

1. **任务 ID 设计**：`r{round}_q{index}`
   - 避免 ID 冲突
   - 支持跨轮次引用

2. **缓存键设计**：基于查询内容的哈希
   - 相同查询内容 → 相同缓存键
   - 支持跨轮次复用

3. **依赖管理**：拓扑排序
   - 独立任务并行执行
   - 有依赖的任务串行执行

4. **并行执行**：asyncio + Semaphore
   - 最多3个并发
   - 提升执行效率

### 9.3 预期效果

| 指标 | 当前 | 目标 | 提升 |
|------|------|------|------|
| 查询成功率 | ~70% | ~90% | +20-30% |
| Token 消耗 | 100% | 50% | -50% |
| 缓存命中时查询速度 | 5s | 0.1s | 50x |
| 重规划时查询速度 | 15s | 0.1s | 150x |
| 任务执行自动化 | 0% | 100% | +100% |

---

**请核对以上架构和流程是否正确！**

如果有任何疑问或需要修正的地方，请告诉我。

