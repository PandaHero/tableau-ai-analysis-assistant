# 正确理解：累积洞察 + 重规划 + 任务调度器

## 核心理解

### 1. 累积洞察的真实含义

**不是**：对单个查询结果进行分析
**而是**：对一批查询结果进行并行的累积洞察分析

```
Task Planner 生成一批任务：
- q0: 查询华东地区利润率
- q1: 查询华北地区利润率  
- q2: 查询华南地区利润率
- q3: 查询全国平均利润率

累积洞察分析：
┌─────────────────────────────────────────────────────────────┐
│ 10个 AI 宝宝并行吃饭                                          │
├─────────────────────────────────────────────────────────────┤
│ AI宝宝1 分析 q0 结果（华东数据）                              │
│   → 如果数据量大（10,000行），分块分析                        │
│   → Top 100, 101-500, 501-1000, ...                         │
│   → 提取洞察：华东利润率 12%                                  │
│                                                              │
│ AI宝宝2 分析 q1 结果（华北数据）                              │
│   → 分块分析                                                 │
│   → 提取洞察：华北利润率 18%                                  │
│                                                              │
│ AI宝宝3 分析 q2 结果（华南数据）                              │
│   → 分块分析                                                 │
│   → 提取洞察：华南利润率 15%                                  │
│                                                              │
│ AI宝宝4 分析 q3 结果（全国数据）                              │
│   → 分块分析                                                 │
│   → 提取洞察：全国平均 15%                                    │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 洞察合成（关键！）                                            │
├─────────────────────────────────────────────────────────────┤
│ 问题：多个 AI 宝宝的洞察如何合成？                            │
│                                                              │
│ 方案1：简单拼接（不好）                                       │
│   - 华东利润率 12%                                           │
│   - 华北利润率 18%                                           │
│   - 华南利润率 15%                                           │
│   - 全国平均 15%                                             │
│                                                              │
│ 方案2：智能合成（参考 BettaFish）                             │
│   - 识别关键发现：华东利润率最低（12%）                       │
│   - 对比分析：低于全国平均 3 个百分点                         │
│   - 排名：华东 < 华南 < 华北                                 │
│   - 合成洞察："华东地区利润率最低（12%），低于全国平均        │
│     15%，需要重点关注"                                       │
└─────────────────────────────────────────────────────────────┘
                          ↓
                    重规划 Agent
```

### 2. 重规划的真实流程

```
┌─────────────────────────────────────────────────────────────┐
│ 第1轮：初始分析                                               │
├─────────────────────────────────────────────────────────────┤
│ 用户问题："为什么华东地区利润率低？"                          │
│                                                              │
│ 1. Understanding Agent                                       │
│    → 理解意图                                                │
│                                                              │
│ 2. Task Planner Agent                                        │
│    → 生成任务：                                              │
│      - q0: 查询华东地区利润率                                │
│      - q1: 查询全国平均利润率                                │
│                                                              │
│ 3. Task Scheduler                                            │
│    → 并行执行 q0, q1                                         │
│    → 缓存结果                                                │
│                                                              │
│ 4. 累积洞察分析（并行）                                       │
│    → AI宝宝1 分析 q0 → 洞察：华东利润率 12%                  │
│    → AI宝宝2 分析 q1 → 洞察：全国平均 15%                    │
│    → 合成：华东利润率低于全国平均                            │
│                                                              │
│ 5. Replan Agent                                              │
│    → 判断：是否回答了"为什么"？                              │
│    → 结论：没有，只知道"低"，不知道"为什么"                  │
│    → 决定：重规划                                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 第2轮：重规划后的分析                                         │
├─────────────────────────────────────────────────────────────┤
│ Replan Agent 生成新问题：                                     │
│   - "华东各产品类别的利润率是多少？"                          │
│   - "华东各门店的利润率是多少？"                              │
│                                                              │
│ 1. Understanding Agent（重新执行）                            │
│    → 理解新问题                                              │
│                                                              │
│ 2. Task Planner Agent（重新执行）                            │
│    → 生成新任务：                                            │
│      - q2: 查询华东各产品类别利润率                          │
│      - q3: 查询华东各门店利润率                              │
│      - q0: 查询华东地区利润率（复用缓存）                    │
│                                                              │
│ 3. Task Scheduler                                            │
│    → q0: 缓存命中，直接返回                                  │
│    → q2, q3: 并行执行新查询                                  │
│                                                              │
│ 4. 累积洞察分析（并行）                                       │
│    → AI宝宝1 分析 q2 → 洞察：家具类利润率 8%                 │
│    → AI宝宝2 分析 q3 → 洞察：A门店利润率 10%                 │
│    → 合成：家具类是主要原因                                  │
│                                                              │
│ 5. Replan Agent                                              │
│    → 判断：是否回答了"为什么"？                              │
│    → 结论：部分回答，知道是家具类，但不知道为什么家具类低    │
│    → 决定：再次重规划                                        │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 第3轮：再次重规划                                             │
├─────────────────────────────────────────────────────────────┤
│ Replan Agent 生成新问题：                                     │
│   - "家具类的成本结构是什么？"                                │
│   - "家具类的折扣情况如何？"                                  │
│                                                              │
│ ... 重复上述流程 ...                                         │
│                                                              │
│ 累积洞察分析：                                                │
│    → 发现：家具类折扣率 22%，过高                            │
│                                                              │
│ Replan Agent：                                               │
│    → 判断：已经回答了"为什么"                                │
│    → 决定：不再重规划，返回结果                              │
└─────────────────────────────────────────────────────────────┘
```

### 3. 任务 ID 生成逻辑

**当前问题**：
- 使用简单的 q0, q1, q2, ...
- 重规划后可能重复

**解决方案**：

```python
# 方案1：全局递增 ID
class TaskIDGenerator:
    def __init__(self):
        self.counter = 0
    
    def generate(self, task_type: str) -> str:
        """
        生成唯一的任务 ID
        
        Args:
            task_type: "query" 或 "processing"
        
        Returns:
            唯一的任务 ID，例如：q_0, q_1, p_0, p_1
        """
        prefix = "q" if task_type == "query" else "p"
        task_id = f"{prefix}_{self.counter}"
        self.counter += 1
        return task_id

# 使用示例
generator = TaskIDGenerator()

# 第1轮
q0 = generator.generate("query")  # q_0
q1 = generator.generate("query")  # q_1

# 第2轮（重规划后）
q2 = generator.generate("query")  # q_2
q3 = generator.generate("query")  # q_3

# 不会重复！
```

```python
# 方案2：带轮次的 ID（更清晰）
class TaskIDGenerator:
    def __init__(self):
        self.round_counter = 0
        self.task_counters = {}  # {round: counter}
    
    def new_round(self):
        """开始新一轮"""
        self.round_counter += 1
        self.task_counters[self.round_counter] = 0
    
    def generate(self, task_type: str) -> str:
        """
        生成唯一的任务 ID
        
        Returns:
            唯一的任务 ID，例如：r1_q0, r1_q1, r2_q0, r2_q1
        """
        if self.round_counter not in self.task_counters:
            self.new_round()
        
        prefix = "q" if task_type == "query" else "p"
        counter = self.task_counters[self.round_counter]
        task_id = f"r{self.round_counter}_{prefix}{counter}"
        
        self.task_counters[self.round_counter] += 1
        return task_id

# 使用示例
generator = TaskIDGenerator()

# 第1轮
generator.new_round()
q0 = generator.generate("query")  # r1_q0
q1 = generator.generate("query")  # r1_q1

# 第2轮（重规划后）
generator.new_round()
q0 = generator.generate("query")  # r2_q0（不会与 r1_q0 冲突）
q1 = generator.generate("query")  # r2_q1
```

```python
# 方案3：UUID（最安全，但不直观）
import uuid

def generate_task_id(task_type: str) -> str:
    """
    生成唯一的任务 ID
    
    Returns:
        唯一的任务 ID，例如：q_a1b2c3d4, p_e5f6g7h8
    """
    prefix = "q" if task_type == "query" else "p"
    unique_id = str(uuid.uuid4())[:8]
    return f"{prefix}_{unique_id}"

# 使用示例
q0 = generate_task_id("query")  # q_a1b2c3d4
q1 = generate_task_id("query")  # q_e5f6g7h8

# 绝对不会重复，但不直观
```

**推荐方案**：方案2（带轮次的 ID）

优点：
- 清晰：可以看出是第几轮的第几个任务
- 唯一：不会重复
- 可追溯：方便调试和分析

### 4. 累积洞察的并行分析和合成

**关键问题**：多个 AI 宝宝并行分析，如何配合？

**参考 BettaFish 的设计**：

```python
# BettaFish 的 Coordinator Pattern

class InsightCoordinator:
    """
    洞察协调器
    
    职责：
    1. 协调多个 AI 宝宝并行分析
    2. 收集所有洞察
    3. 智能合成最终洞察
    """
    
    async def coordinate_parallel_analysis(
        self,
        query_results: Dict[str, DataFrame]  # {task_id: result}
    ) -> str:
        """
        协调并行分析
        
        流程：
        1. 为每个查询结果启动一个 AI 宝宝
        2. 并行分析（每个宝宝独立分析自己的数据）
        3. 收集所有洞察
        4. 智能合成
        """
        # 1. 并行分析
        analysis_tasks = []
        for task_id, result in query_results.items():
            task = self._analyze_single_result(task_id, result)
            analysis_tasks.append(task)
        
        # 2. 等待所有分析完成
        individual_insights = await asyncio.gather(*analysis_tasks)
        
        # 3. 智能合成
        synthesized_insight = await self._synthesize_insights(
            individual_insights
        )
        
        return synthesized_insight
    
    async def _analyze_single_result(
        self,
        task_id: str,
        result: DataFrame
    ) -> Insight:
        """
        分析单个查询结果（一个 AI 宝宝）
        
        如果数据量大，使用累积洞察策略：
        - 分块：Top 100, 101-500, ...
        - 渐进分析
        - 早停
        """
        if len(result) > 1000:
            # 大数据：使用累积洞察
            return await self._progressive_insight_analysis(
                task_id, result
            )
        else:
            # 小数据：直接分析
            return await self._direct_analysis(task_id, result)
    
    async def _synthesize_insights(
        self,
        individual_insights: List[Insight]
    ) -> str:
        """
        智能合成洞察
        
        关键：不是简单拼接，而是：
        1. 识别关键发现
        2. 对比分析
        3. 排名
        4. 关联分析
        5. 生成连贯的叙述
        """
        # 使用 LLM 合成
        prompt = f"""
        你是一个数据分析专家。现在有多个分析师分别分析了不同的数据，
        你需要将他们的洞察合成为一个连贯、有洞察力的分析报告。
        
        各分析师的洞察：
        {self._format_insights(individual_insights)}
        
        请合成为一个完整的分析，要求：
        1. 识别最关键的发现
        2. 进行对比分析
        3. 找出模式和趋势
        4. 提供可行的建议
        5. 保持逻辑连贯
        """
        
        synthesized = await self.llm.invoke(prompt)
        return synthesized
```

### 5. 完整的系统流程

```
用户问题："为什么华东地区利润率低？"

┌─────────────────────────────────────────────────────────────┐
│ 第1轮                                                         │
├─────────────────────────────────────────────────────────────┤
│ Understanding → Task Planner → Task Scheduler                │
│                                                              │
│ 生成任务：q_0, q_1                                           │
│ 执行查询：并行执行                                           │
│ 缓存结果：存储到 PersistentStore                             │
│                                                              │
│ 累积洞察分析（并行）：                                        │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ AI宝宝1 分析 q_0（华东数据）                         │   │
│   │   → 如果数据大，分块分析                             │   │
│   │   → 提取洞察：华东利润率 12%                         │   │
│   │                                                      │   │
│   │ AI宝宝2 分析 q_1（全国数据）                         │   │
│   │   → 如果数据大，分块分析                             │   │
│   │   → 提取洞察：全国平均 15%                           │   │
│   └─────────────────────────────────────────────────────┘   │
│                          ↓                                   │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ Insight Coordinator 合成                             │   │
│   │   → 对比：华东 < 全国                                │   │
│   │   → 合成："华东利润率低于全国平均"                   │   │
│   └─────────────────────────────────────────────────────┘   │
│                          ↓                                   │
│ Replan Agent：                                               │
│   → 判断：是否回答了"为什么"？                              │
│   → 结论：没有                                              │
│   → 决定：重规划                                            │
│   → 生成新问题："华东各产品类别的利润率是多少？"            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 第2轮（重规划）                                               │
├─────────────────────────────────────────────────────────────┤
│ Understanding → Task Planner → Task Scheduler                │
│                                                              │
│ 生成任务：q_2, q_3, q_0（复用）                             │
│ 执行查询：                                                   │
│   - q_0: 缓存命中，直接返回                                 │
│   - q_2, q_3: 并行执行新查询                                │
│                                                              │
│ 累积洞察分析（并行）：                                        │
│   → AI宝宝1 分析 q_2 → 洞察：家具类利润率 8%                │
│   → AI宝宝2 分析 q_3 → 洞察：电器类利润率 16%               │
│   → Coordinator 合成："家具类是主要原因"                     │
│                                                              │
│ Replan Agent：                                               │
│   → 判断：部分回答，需要继续                                │
│   → 决定：再次重规划                                        │
└─────────────────────────────────────────────────────────────┘
                          ↓
                      ... 循环 ...
                          ↓
                    最终返回结果
```

---

## 总结

### 1. 累积洞察

- **对象**：一批查询结果（不是单个）
- **方式**：多个 AI 宝宝并行分析
- **策略**：每个宝宝对自己的数据分块分析（如果数据大）
- **合成**：Coordinator 智能合成所有洞察

### 2. 重规划

- **触发**：Replan Agent 判断问题未充分回答
- **流程**：生成新问题 → 重新执行 Understanding → Task Planner → ...
- **循环**：直到问题被充分回答

### 3. 任务调度器

- **职责**：
  - 执行查询计划
  - 并行执行优化
  - 查询结果缓存（重规划时复用）
  - 进度跟踪

### 4. 任务 ID

- **推荐**：带轮次的 ID（r1_q0, r1_q1, r2_q0, ...）
- **优点**：清晰、唯一、可追溯

---

**文档版本**: v1.0  
**创建时间**: 2025-11-20  
**作者**: Kiro AI Assistant
