# 智能分析增强 - 设计文档

## 📖 文档导航

### 🔗 相关文档
- **[需求文档](./requirements.md)** - 功能需求和验收标准
- **[任务列表](./tasks.md)** - 可执行的任务分解（待创建）

### 📋 本文档内容
- 系统架构设计
- 核心组件设计
- 数据结构设计
- 工作流设计（探索式分析 + 普通分析）
- 数据流设计
- 接口设计

---

## 1. 系统架构概览

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户交互层                                │
│                    (Tableau Extension UI)                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      智能分析引擎                                 │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐                             │
│  │ 问题理解Agent │→│ 任务规划Agent │                             │
│  └──────────────┘  └──────────────┘                             │
│                             │                                     │
│                             ▼                                     │
│  ┌─────────────────────────────────────────────────┐            │
│  │            任务调度器 (TaskScheduler)            │            │
│  │  - 依赖分析  - 并发控制  - 动态调度             │            │
│  └─────────────────────────────────────────────────┘            │
│                             │                                     │
│                             ▼                                     │
│  ┌──────────────────────────────────────────────┐               │
│  │         查询执行流水线 (并行)                 │               │
│  │  ┌────────────┐  ┌────────────┐              │               │
│  │  │查询构建器  │→│查询执行器  │              │               │
│  │  └────────────┘  └────────────┘              │               │
│  │         │                │                    │               │
│  │         ▼                ▼                    │               │
│  │  ┌────────────┐  ┌────────────┐              │               │
│  │  │统计检测器  │  │数据处理器  │              │               │
│  │  └────────────┘  └────────────┘              │               │
│  └──────────────────────────────────────────────┘               │
│                             │                                     │
│                             ▼                                     │
│  ┌──────────────────────────────────────────────┐               │
│  │         洞察生成流水线 (并行)                 │               │
│  │  ┌────────────┐  ┌────────────┐              │               │
│  │  │洞察Agent   │  │分段处理器  │              │               │
│  │  └────────────┘  └────────────┘              │               │
│  │         │                │                    │               │
│  │         ▼                ▼                    │               │
│  │  ┌────────────┐  ┌────────────┐              │               │
│  │  │上下文管理  │  │结果累积    │              │               │
│  │  └────────────┘  └────────────┘              │               │
│  └──────────────────────────────────────────────┘               │
│                             │                                     │
│                             ▼                                     │
│  ┌──────────────────────────────────────────────┐               │
│  │            重规划Agent                        │               │
│  │  - 综合所有洞察                               │               │
│  │  - 关联分析                                   │               │
│  │  - 决策下一步行动                             │               │
│  │    * CONTINUE_EXPLORE → 回到任务规划Agent     │               │
│  │    * FOCUS_ANALYSIS → 回到任务规划Agent       │               │
│  │    * COMPLETE → 进入总结Agent                 │               │
│  └──────────────────────────────────────────────┘               │
│                   │                        │                     │
│                   │ (继续探索)             │ (完成)              │
│                   ▼                        ▼                     │
│         ┌──────────────┐         ┌──────────────┐               │
│         │任务规划Agent │         │  总结Agent   │               │
│         └──────────────┘         │ - 生成报告   │               │
│                                   │ - 推荐问题   │               │
│                                   └──────────────┘               │
│                                            │                     │
└────────────────────────────────────────────┼─────────────────────┘
                                             │
                                             ▼
                                    ┌──────────────┐
                                    │  返回用户    │
                                    └──────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      数据访问层                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  VDS查询     │  │  数据缓存    │  │  元数据服务  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 核心设计原则

1. **独立累积，综合决策** - 每个任务独立累积洞察，重规划Agent综合所有洞察决策
2. **异步并行执行** - 查询和洞察都支持异步并行，不等待其他任务
3. **结构化状态管理** - 使用dataclass管理分析状态，类型安全
4. **智能上下文传递** - 在prompt中明确传递累积上下文
5. **分段累积处理** - 大数据集分段处理，每段累积结果
6. **动态任务调度** - 根据依赖关系和资源情况动态调度

---

## 2. 核心数据结构设计

### 2.1 分析状态 (AnalysisState)

```python
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
from enum import Enum

class AnalysisMode(Enum):
    """分析模式"""
    NORMAL = "normal"          # 普通分析（单次问答）
    EXPLORATORY = "exploratory"  # 探索式分析（多轮重规划）

@dataclass
class AnalysisState:
    """整体分析状态（借鉴BettaFish的State设计）"""
    # 基本信息
    session_id: str
    original_question: str
    analysis_mode: AnalysisMode
    
    # 任务洞察列表
    task_insights: List['TaskInsight'] = field(default_factory=list)
    
    # 重规划历史
    replanner_decisions: List['ReplannerDecision'] = field(default_factory=list)
    
    # 分析状态
    root_cause_found: bool = False
    is_completed: bool = False
    
    # 分析路径（树状结构）
    analysis_path: List[str] = field(default_factory=list)
    
    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def add_task_insight(self, task_insight: 'TaskInsight'):
        """添加任务洞察"""
        self.task_insights.append(task_insight)
        self.updated_at = datetime.now()
    
    def add_replanner_decision(self, decision: 'ReplannerDecision'):
        """添加重规划决策"""
        self.replanner_decisions.append(decision)
        self.analysis_path.append(decision.action_type)
        self.updated_at = datetime.now()

    def get_all_insights_summary(self) -> str:
        """获取所有任务洞察的摘要"""
        summaries = []
        for task in self.task_insights:
            summaries.append(f"问题: {task.question}\n洞察: {task.latest_insight}")
        return "\n\n".join(summaries)
    
    def get_replanner_count(self) -> int:
        """获取重规划次数"""
        return len(self.replanner_decisions)
```

### 2.2 任务洞察 (TaskInsight)

```python
@dataclass
class TaskInsight:
    """单个任务的洞察累积（借鉴BettaFish的Paragraph设计）"""
    # 任务信息
    task_id: str
    question: str
    query_spec: Dict  # 查询规格
    
    # 查询结果
    query_results: Optional[Dict] = None
    query_metadata: Dict = field(default_factory=dict)  # 行数、列数、token大小等
    
    # 洞察累积
    insights_history: List[str] = field(default_factory=list)  # 分段洞察历史
    latest_insight: str = ""  # 最新洞察（累积后的）
    
    # 分段信息
    chunk_count: int = 0
    needs_chunking: bool = False
    
    # 状态
    is_completed: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    
    def add_insight(self, insight: str):
        """添加洞察（分段累积）"""
        self.insights_history.append(insight)
        self.latest_insight = insight
    
    def mark_completed(self):
        """标记完成"""
        self.is_completed = True
```

### 2.3 重规划决策 (ReplannerDecision)

```python
class ActionType(Enum):
    """重规划动作类型"""
    CONTINUE_EXPLORE = "continue_explore"  # 继续探索（生成新问题）
    FOCUS_ANALYSIS = "focus_analysis"      # 聚焦分析（单个问题深入）
    COMPLETE = "complete"                  # 完成分析

@dataclass
class ReplannerDecision:
    """重规划决策记录"""
    round_number: int  # 第几轮重规划
    action_type: ActionType
    reasoning: str  # 决策理由
    
    # 生成的问题（如果是continue_explore或focus_analysis）
    generated_questions: List['GeneratedQuestion'] = field(default_factory=list)
    
    # 综合分析
    insights_summary: str = ""  # 对所有洞察的综合分析
    coverage_analysis: Dict = field(default_factory=dict)  # 覆盖度分析
    root_cause_analysis: str = ""  # 根因分析
    
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class GeneratedQuestion:
    """生成的探索问题"""
    question: str
    priority: str  # high, medium, low
    reasoning: str  # 为什么生成这个问题
    question_type: str  # drill_down, switch_dimension, time_adjust, etc.
```

### 2.4 查询历史 (QueryHistory)

```python
@dataclass
class QueryHistory:
    """查询历史记录（避免重复查询）"""
    query_text: str
    query_spec: Dict
    results_summary: str  # 结果摘要（不保存完整结果）
    row_count: int
    timestamp: datetime = field(default_factory=datetime.now)
    
    def is_similar_to(self, other_query: str, threshold: float = 0.9) -> bool:
        """检查是否与另一个查询相似"""
        # 简单的相似度检查（实际可用更复杂的算法）
        return self.query_text.lower() == other_query.lower()
```

### 2.5 上下文压缩器配置

```python
@dataclass
class ContextConfig:
    """上下文管理配置"""
    max_total_tokens: int = 8000  # 最大token数
    max_search_results_per_query: int = 100  # 每个查询最多保留的结果数
    max_insight_history: int = 3  # 最多保留的洞察历史数
    max_decision_history: int = 3  # 最多保留的决策历史数
    compression_threshold: float = 0.8  # 达到80%时触发压缩
```

---

## 3. 核心组件设计

### 3.1 任务调度器 (TaskScheduler)

**职责**：
- 接收多个任务（问题）
- 分析任务间的依赖关系
- 异步并行调度执行
- 动态资源控制（最大并发数3）
- 收集所有任务的结果

**接口设计**：
```python
class TaskScheduler:
    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self.running_tasks: List[Task] = []
        self.waiting_queue: List[Task] = []
    
    async def schedule_tasks(
        self, 
        tasks: List[Task]
    ) -> List[TaskResult]:
        """
        调度多个任务执行
        
        Args:
            tasks: 任务列表
            
        Returns:
            所有任务的执行结果
        """
        pass

    def analyze_dependencies(self, tasks: List[Task]) -> Dict[str, List[str]]:
        """
        分析任务依赖关系
        
        Returns:
            依赖图 {task_id: [dependent_task_ids]}
        """
        pass
    
    async def execute_task(self, task: Task) -> TaskResult:
        """执行单个任务（查询 + 洞察）"""
        pass
```

**调度策略**：
1. **无依赖任务**：全部异步并行执行（受限于max_concurrent）
2. **有依赖任务**：等待依赖任务完成后再执行
3. **动态调度**：任务完成后立即从等待队列启动下一个

### 3.2 数据处理器 (DataProcessor)

**职责**：
- 数据质量检查
- 数据标准化
- 聚合计算（同比、环比、增长率等）
- 任务依赖处理（合并依赖任务的数据）
- 数据分段检查

**接口设计**：
```python
class DataProcessor:
    def process_query_result(
        self, 
        query_result: Dict,
        task: Task
    ) -> ProcessedData:
        """
        处理查询结果
        
        Args:
            query_result: 原始查询结果
            task: 任务信息
            
        Returns:
            处理后的数据
        """
        pass
    
    def check_data_quality(self, data: Dict) -> QualityReport:
        """数据质量检查"""
        pass
    
    def calculate_aggregations(
        self, 
        data: Dict, 
        agg_type: str
    ) -> Dict:
        """
        计算聚合指标
        
        Args:
            data: 数据
            agg_type: 聚合类型（yoy, mom, growth_rate, etc.）
        """
        pass
    
    def check_chunking_needed(self, data: Dict) -> ChunkingInfo:
        """
        检查是否需要分段
        
        Returns:
            ChunkingInfo(needs_chunking, row_count, token_size, strategy)
        """
        pass
```

### 3.3 分段处理器 (ChunkProcessor)

**职责**：
- 智能分段策略选择
- 数据分段
- 分段结果合并

**接口设计**：
```python
class ChunkProcessor:
    def chunk_data(
        self, 
        data: Dict, 
        strategy: ChunkStrategy
    ) -> List[DataChunk]:
        """
        分段数据
        
        Args:
            data: 原始数据
            strategy: 分段策略（TOP_N, TIME_WINDOW, DIMENSION）
            
        Returns:
            数据分段列表
        """
        pass
    
    def select_strategy(self, data: Dict, metadata: Dict) -> ChunkStrategy:
        """选择最合适的分段策略"""
        pass
```

**分段策略**：
1. **TOP_N策略**：TOP 20 → RANK 21-50 → OTHERS
2. **TIME_WINDOW策略**：Q1 → Q2 → Q3 → Q4
3. **DIMENSION策略**：按维度值分段

### 3.4 重规划Agent (ReplannerAgent)

**职责**：
- 综合所有任务的洞察
- 进行关联分析
- 评估覆盖度和完整性
- 决定下一步行动（继续探索/聚焦分析/完成）
- 生成新的探索问题

**接口设计**：
```python
class ReplannerAgent:
    async def decide_next_action(
        self, 
        state: AnalysisState
    ) -> ReplannerDecision:
        """
        决定下一步行动
        
        Args:
            state: 当前分析状态
            
        Returns:
            重规划决策
        """
        pass
    
    def analyze_coverage(self, state: AnalysisState) -> Dict:
        """
        分析覆盖度
        
        Returns:
            {
                "dimension_coverage": 0.7,
                "data_coverage": 0.65,
                "question_coverage": 0.8
            }
        """
        pass
    
    def identify_root_cause(self, insights: List[str]) -> Optional[str]:
        """识别是否已找到根本原因"""
        pass
    
    def generate_questions(
        self, 
        insights: List[str], 
        action_type: ActionType
    ) -> List[GeneratedQuestion]:
        """
        生成探索问题
        
        Args:
            insights: 所有洞察
            action_type: CONTINUE_EXPLORE（2-5个问题）或 FOCUS_ANALYSIS（1个问题）
        """
        pass
```

**决策逻辑**：
1. **CONTINUE_EXPLORE**：
   - 条件：覆盖度 < 70%，未找到根因
   - 生成：2-5个并行问题，多维度探索
   
2. **FOCUS_ANALYSIS**：
   - 条件：发现关键线索，需要深入分析
   - 生成：1个聚焦问题，深入挖掘
   
3. **COMPLETE**：
   - 条件：找到根因 OR 覆盖度 >= 85% OR 达到最大重规划次数
   - 生成：无，进入总结阶段

### 3.5 总结Agent (SummarizerAgent)

**职责**：
- 生成最终分析报告
- 提取关键发现
- 生成行动建议
- 推荐后续问题

**接口设计**：
```python
class SummarizerAgent:
    async def generate_report(
        self, 
        state: AnalysisState
    ) -> AnalysisReport:
        """
        生成最终报告
        
        Args:
            state: 完整的分析状态
            
        Returns:
            分析报告
        """
        pass
    
    def extract_key_findings(
        self, 
        insights: List[str]
    ) -> List[str]:
        """提取3-5个关键发现"""
        pass
    
    def generate_recommendations(
        self, 
        insights: List[str]
    ) -> List[str]:
        """生成行动建议"""
        pass
    
    def recommend_followup_questions(
        self, 
        state: AnalysisState
    ) -> List[GeneratedQuestion]:
        """推荐后续问题"""
        pass
```

**报告结构**：
```python
@dataclass
class AnalysisReport:
    """分析报告"""
    # 基本信息
    original_question: str
    analysis_mode: AnalysisMode
    
    # 分析路径
    analysis_path: List[str]
    total_rounds: int
    
    # 关键发现
    key_findings: List[str]  # 3-5个关键发现
    
    # 详细洞察
    all_insights: List[TaskInsight]
    
    # 根因分析（如果找到）
    root_cause: Optional[str]
    
    # 行动建议
    recommendations: List[str]
    
    # 推荐后续问题
    followup_questions: List[GeneratedQuestion]
    
    # 元数据
    total_queries: int
    total_data_rows: int
    execution_time: float
```

### 3.6 上下文管理器 (ContextManager)

**职责**：
- 管理分析状态
- 传递累积上下文
- 压缩历史信息
- 避免重复查询

**接口设计**：
```python
class ContextManager:
    def __init__(self, config: ContextConfig):
        self.config = config
        self.state: AnalysisState = None
        self.query_history: List[QueryHistory] = []

    def get_context_for_insight(
        self, 
        task: TaskInsight, 
        chunk_index: Optional[int] = None
    ) -> Dict:
        """
        获取洞察Agent需要的上下文
        
        Args:
            task: 任务洞察
            chunk_index: 分段索引（如果是分段分析）
            
        Returns:
            上下文字典，包含：
            - question: 问题
            - query_results: 查询结果（或分段）
            - accumulated_insights: 累积的洞察（如果是分段）
        """
        pass
    
    def get_context_for_replanner(self) -> Dict:
        """
        获取重规划Agent需要的上下文
        
        Returns:
            上下文字典，包含：
            - original_question: 原始问题
            - all_task_insights: 所有任务的洞察
            - previous_decisions: 之前的决策历史
            - analysis_path: 分析路径
        """
        pass
    
    def compress_context(self):
        """压缩上下文（当token超限时）"""
        pass
    
    def is_duplicate_query(self, query: str) -> bool:
        """检查是否重复查询"""
        pass
    
    def calculate_token_size(self, text: str) -> int:
        """计算文本的token大小"""
        pass
```

---

## 4. 工作流设计

### 4.1 探索式分析工作流（三次重规划）

**场景**：用户提出一个开放性问题，需要多轮探索才能找到根因

**示例问题**："为什么华东地区的利润率比其他地区低？"

#### 完整流程图

```
用户提问："为什么华东地区的利润率比其他地区低？"
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 第0轮：初始分析                                              │
├─────────────────────────────────────────────────────────────┤
│ 问题理解Agent                                                │
│  - 识别分析模式：exploratory（探索式）                       │
│  - 提取关键信息：地区=华东，指标=利润率，对比=其他地区       │
│  - 初始假设：可能是成本、折扣、产品结构等因素                │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 任务规划Agent                                                │
│  - 生成初始问题："华东地区各城市的利润率分别是多少？"        │
│  - 查询规格：GROUP BY 城市, MEASURE 利润率                   │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 任务调度器 → 查询执行 → 数据处理 → 洞察生成                  │
│  查询结果：上海 12%, 杭州 11%, 南京 10%, ...                │
│  洞察：华东各城市利润率普遍偏低，上海略高但仍低于全国平均    │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 第1轮重规划：多维度探索                                      │
├─────────────────────────────────────────────────────────────┤
│ 重规划Agent                                                  │
│  【输入上下文】                                              │
│  - 原始问题：为什么华东地区利润率低？                        │
│  - 已有洞察：华东各城市利润率普遍偏低                        │
│  - 覆盖度分析：维度覆盖30%，数据覆盖40%                      │
│  - 根因分析：未找到根本原因                                  │
│                                                              │
│  【决策】action_type = CONTINUE_EXPLORE                      │
│  【理由】需要从多个维度探索原因                              │
│                                                              │
│  【生成3个并行问题】                                         │
│  1. "华东各产品类别的利润率分别是多少？" (priority: high)    │
│     理由：切换维度，可能是产品结构问题                        │
│                                                              │
│  2. "华东地区的折扣情况如何？" (priority: high)              │
│     理由：折扣可能影响利润率                                 │
│                                                              │
│  3. "华东地区的成本结构如何？" (priority: medium)            │
│     理由：成本可能是关键因素                                 │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 任务调度器：并行执行3个任务                                  │
├─────────────────────────────────────────────────────────────┤
│ 【依赖分析】3个任务无依赖，可以并行执行                      │
│ 【并发控制】最大并发3个，全部启动                            │
│                                                              │
│ 时间轴：                                                     │
│ 0s:  启动 Task1, Task2, Task3                               │
│ 3s:  Task1完成（产品类别分析）                               │
│ 4s:  Task2完成（折扣分析）                                   │
│ 5s:  Task3完成（成本分析）                                   │
│                                                              │
│ 【Task1结果】                                                │
│ 洞察：家具类产品利润率仅8%，远低于其他类别                   │
│                                                              │
│ 【Task2结果】                                                │
│ 洞察：华东地区平均折扣率18%，高于全国平均15%                 │
│                                                              │
│ 【Task3结果】                                                │
│ 洞察：华东地区运输成本比其他地区高20%                        │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 第2轮重规划：聚焦分析                                        │
├─────────────────────────────────────────────────────────────┤
│ 重规划Agent                                                  │
│  【输入上下文】                                              │
│  - 原始问题：为什么华东地区利润率低？                        │
│  - 所有洞察：                                                │
│    * 华东各城市利润率普遍偏低                                │
│    * 家具类产品利润率仅8%                                    │
│    * 平均折扣率18%，高于全国                                 │
│    * 运输成本比其他地区高20%                                 │
│  - 覆盖度分析：维度覆盖70%，数据覆盖65%                      │
│                                                              │
│  【综合分析】                                                │
│  发现关联：家具类产品 + 高折扣 + 高运输成本 → 利润率低       │
│  关键发现：家具类产品可能是主要原因                          │
│                                                              │
│  【决策】action_type = FOCUS_ANALYSIS                        │
│  【理由】需要深入分析家具类产品的情况                        │
│                                                              │
│  【生成1个聚焦问题】                                         │
│  "华东地区家具类产品的销售额、折扣和成本详情是什么？"        │
│  (priority: high)                                            │
│  理由：深入分析家具类产品，验证假设                          │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 任务调度器：执行聚焦任务                                     │
├─────────────────────────────────────────────────────────────┤
│ 【查询结果】                                                 │
│ 家具类产品：                                                 │
│ - 销售额：500万（占华东总销售额30%）                         │
│ - 平均折扣：22%（远高于其他类别）                            │
│ - 运输成本：占销售额15%（其他类别仅5%）                      │
│ - 利润率：8%                                                 │
│                                                              │
│ 【洞察】                                                     │
│ 找到根本原因：                                               │
│ 1. 家具类产品占华东销售额30%，比重大                         │
│ 2. 家具类产品折扣率22%，远高于其他类别                       │
│ 3. 家具类产品运输成本高（体积大、易损）                      │
│ 4. 综合导致华东地区整体利润率偏低                            │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 第3轮重规划：完成分析                                        │
├─────────────────────────────────────────────────────────────┤
│ 重规划Agent                                                  │
│  【输入上下文】                                              │
│  - 所有洞察（5个任务的洞察）                                 │
│  - 覆盖度分析：维度覆盖90%，数据覆盖85%                      │
│                                                              │
│  【根因识别】                                                │
│  ✅ 已找到根本原因：                                         │
│  华东地区家具类产品占比高（30%），且该类别利润率低（8%），    │
│  主要由于高折扣（22%）和高运输成本（15%）导致                │
│                                                              │
│  【决策】action_type = COMPLETE                              │
│  【理由】已找到根本原因，覆盖度充分                          │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 总结Agent：生成最终报告                                      │
├─────────────────────────────────────────────────────────────┤
│ 【分析路径】                                                 │
│ 初始问题 → 城市下钻 → 多维度探索 → 聚焦家具类 → 找到根因    │
│                                                              │
│ 【关键发现】                                                 │
│ 1. 华东地区利润率低的根本原因是家具类产品                    │
│ 2. 家具类产品占比30%，但利润率仅8%                           │
│ 3. 高折扣（22%）和高运输成本（15%）是主要因素                │
│                                                              │
│ 【行动建议】                                                 │
│ 1. 优化华东地区家具类产品的折扣策略                          │
│ 2. 改善物流配送，降低运输成本                                │
│ 3. 考虑调整产品组合，增加高利润率产品占比                    │
└─────────────────────────────────────────────────────────────┘
```

#### 关键设计点

1. **第1轮重规划**：生成3个并行问题，多维度探索
2. **第2轮重规划**：综合分析后，聚焦到关键维度（家具类产品）
3. **第3轮重规划**：确认找到根因，完成分析
4. **并行执行**：第1轮的3个任务并行执行，总耗时5秒（串行需要12秒）
5. **上下文传递**：每轮重规划都能看到之前所有的洞察

---

### 4.2 普通分析工作流（单次问答）

**场景**：用户提出一个明确的问题，一次查询即可回答

**示例问题**："2024年各地区的销售额是多少？"

#### 完整流程图

```
用户提问："2024年各地区的销售额是多少？"
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 问题理解Agent                                                │
│  - 识别分析模式：normal（普通分析）                          │
│  - 提取关键信息：时间=2024年，维度=地区，指标=销售额         │
│  - 判断：问题明确，无需探索                                  │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 任务规划Agent                                                │
│  - 生成查询规格：                                            │
│    * 时间范围：2024-01-01 to 2024-12-31                      │
│    * 维度：地区                                              │
│    * 指标：SUM(销售额)                                       │
│    * GROUP BY：地区                                          │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 任务调度器：执行单个任务                                     │
├─────────────────────────────────────────────────────────────┤
│ 查询构建器 → 查询执行器 → 统计检测器 → 数据处理器            │
│                                                              │
│ 【查询结果】                                                 │
│ 华东: 5000万                                                 │
│ 华南: 4500万                                                 │
│ 华北: 4000万                                                 │
│ 西南: 3000万                                                 │
│ 西北: 2000万                                                 │
│                                                              │
│ 【数据处理】                                                 │
│ - 数据质量检查：✅ 无异常                                    │
│ - 数据标准化：✅ 完成                                        │
│ - 分段检查：5行数据，无需分段                                │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 洞察Agent：生成洞察                                          │
├─────────────────────────────────────────────────────────────┤
│ 【输入上下文】                                               │
│ - 问题：2024年各地区的销售额是多少？                         │
│ - 查询结果：5个地区的销售额数据                              │
│                                                              │
│ 【洞察】                                                     │
│ 1. 华东地区销售额最高，达到5000万，占总销售额27%             │
│ 2. 华南和华北紧随其后，分别为4500万和4000万                  │
│ 3. 西部地区（西南+西北）销售额较低，合计5000万               │
│ 4. 东部地区（华东+华南+华北）占总销售额73%                   │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 重规划Agent：判断是否需要继续                                │
├─────────────────────────────────────────────────────────────┤
│ 【输入上下文】                                               │
│ - 原始问题：2024年各地区的销售额是多少？                     │
│ - 洞察：已提供各地区销售额及占比分析                         │
│ - 分析模式：normal                                           │
│                                                              │
│ 【决策】action_type = COMPLETE                               │
│ 【理由】问题已完整回答，无需继续探索                         │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 总结Agent：生成最终回答                                      │
├─────────────────────────────────────────────────────────────┤
│ 【回答】                                                     │
│ 2024年各地区销售额如下：                                     │
│ - 华东：5000万（27%）                                        │
│ - 华南：4500万（24%）                                        │
│ - 华北：4000万（22%）                                        │
│ - 西南：3000万（16%）                                        │
│ - 西北：2000万（11%）                                        │
│                                                              │
│ 【推荐后续问题】                                             │
│ 1. "各地区的同比增长率是多少？" (priority: high)             │
│ 2. "华东地区各城市的销售额分布如何？" (priority: medium)     │
│ 3. "各地区的产品类别销售结构如何？" (priority: medium)       │
└─────────────────────────────────────────────────────────────┘
```

#### 关键设计点

1. **快速响应**：识别为普通分析，直接执行查询
2. **单次完成**：一次查询即可回答问题
3. **智能推荐**：提供有理由的后续问题推荐
4. **无需重规划**：重规划Agent判断无需继续，直接完成

---

## 5. 数据流设计

### 5.1 探索式分析数据流

```
┌─────────────────────────────────────────────────────────────┐
│ 第1轮：初始分析                                              │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
AnalysisState {
    session_id: "session_001"
    original_question: "为什么华东地区利润率低？"
    analysis_mode: EXPLORATORY
    task_insights: [
        TaskInsight {
            task_id: "task_001"
            question: "华东各城市的利润率是多少？"
            query_results: {...}
            latest_insight: "华东各城市利润率普遍偏低"
            is_completed: true
        }
    ]
    replanner_decisions: []
    root_cause_found: false
}
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 第1轮重规划：生成3个并行问题                                 │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
AnalysisState {
    task_insights: [
        TaskInsight {...},  // task_001
        TaskInsight {       // task_002
            task_id: "task_002"
            question: "华东各产品类别的利润率是多少？"
            latest_insight: "家具类产品利润率仅8%"
            is_completed: true
        },
        TaskInsight {       // task_003
            task_id: "task_003"
            question: "华东地区的折扣情况如何？"
            latest_insight: "平均折扣率18%，高于全国"
            is_completed: true
        },
        TaskInsight {       // task_004
            task_id: "task_004"
            question: "华东地区的成本结构如何？"
            latest_insight: "运输成本比其他地区高20%"
            is_completed: true
        }
    ]
    replanner_decisions: [
        ReplannerDecision {
            round_number: 1
            action_type: CONTINUE_EXPLORE
            reasoning: "需要从多个维度探索原因"
            generated_questions: [3个问题]
            insights_summary: "华东各城市利润率普遍偏低"
        }
    ]
}
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 第2轮重规划：聚焦分析                                        │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
AnalysisState {
    task_insights: [
        // 前4个任务...
        TaskInsight {       // task_005
            task_id: "task_005"
            question: "华东家具类产品的详细情况？"
            latest_insight: "找到根本原因：家具类产品占比高..."
            is_completed: true
        }
    ]
    replanner_decisions: [
        // 第1轮决策...
        ReplannerDecision {
            round_number: 2
            action_type: FOCUS_ANALYSIS
            reasoning: "需要深入分析家具类产品"
            generated_questions: [1个聚焦问题]
            insights_summary: "发现家具类产品可能是主要原因"
            coverage_analysis: {
                dimension_coverage: 0.7,
                data_coverage: 0.65
            }
        }
    ]
}
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 第3轮重规划：完成分析                                        │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
AnalysisState {
    task_insights: [5个任务的洞察]
    replanner_decisions: [
        // 前2轮决策...
        ReplannerDecision {
            round_number: 3
            action_type: COMPLETE
            reasoning: "已找到根本原因，覆盖度充分"
            root_cause_analysis: "华东地区家具类产品占比高..."
            coverage_analysis: {
                dimension_coverage: 0.9,
                data_coverage: 0.85
            }
        }
    ]
    root_cause_found: true
    is_completed: true
    analysis_path: [
        "初始分析",
        "多维度探索",
        "聚焦分析",
        "完成"
    ]
}
```

### 5.2 分段处理数据流

**场景**：查询返回5000行数据，需要分段处理

```
┌─────────────────────────────────────────────────────────────┐
│ 查询执行完成                                                 │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
QueryResult {
    data: [5000行数据]
    row_count: 5000
    columns: ["城市", "销售额", "利润率"]
}
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 数据处理器：检查分段                                         │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
ChunkingInfo {
    needs_chunking: true
    row_count: 5000
    token_size: 12000
    strategy: TOP_N
    chunk_plan: [
        {name: "TOP 20", rows: 20},
        {name: "RANK 21-50", rows: 30},
        {name: "RANK 51-100", rows: 50},
        {name: "OTHERS", rows: 4900}
    ]
}
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 分段处理器：分段数据                                         │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
[
    DataChunk {
        chunk_id: 1,
        name: "TOP 20",
        data: [20行数据],
        metadata: {rank_range: "1-20"}
    },
    DataChunk {
        chunk_id: 2,
        name: "RANK 21-50",
        data: [30行数据],
        metadata: {rank_range: "21-50"}
    },
    DataChunk {
        chunk_id: 3,
        name: "RANK 51-100",
        data: [50行数据],
        metadata: {rank_range: "51-100"}
    },
    DataChunk {
        chunk_id: 4,
        name: "OTHERS",
        data: [聚合后的数据],
        metadata: {rank_range: "100+", aggregated: true}
    }
]
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 洞察Agent：逐段分析并累积                                    │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
TaskInsight {
    task_id: "task_001"
    question: "各城市的销售额是多少？"
    chunk_count: 4
    insights_history: [
        "【分段1/4】TOP 20城市中，上海销售额最高...",
        "【分段2/4】RANK 21-50城市中，苏州表现突出...",
        "【分段3/4】RANK 51-100城市销售额相对平稳...",
        "【分段4/4】其他城市合计销售额占比15%..."
    ]
    latest_insight: """
    【综合分析】
    1. TOP 20城市贡献了60%的销售额，上海、北京、深圳位列前三
    2. RANK 21-50城市贡献了25%，苏州、杭州表现突出
    3. RANK 51-100城市贡献了10%，销售额相对平稳
    4. 其他城市合计贡献15%，长尾效应明显
    """
    is_completed: true
}
```

#### 分段分析的上下文传递

**第1段分析**：
```python
context = {
    "question": "各城市的销售额是多少？",
    "chunk_info": "分段1/4: TOP 20城市",
    "data": [20行数据],
    "accumulated_insights": ""  # 第一段没有累积
}
```

**第2段分析**：
```python
context = {
    "question": "各城市的销售额是多少？",
    "chunk_info": "分段2/4: RANK 21-50城市",
    "data": [30行数据],
    "accumulated_insights": """
    【之前的发现】
    - TOP 20城市贡献了60%的销售额
    - 上海、北京、深圳位列前三
    """
}
```

**第3段分析**：
```python
context = {
    "question": "各城市的销售额是多少？",
    "chunk_info": "分段3/4: RANK 51-100城市",
    "data": [50行数据],
    "accumulated_insights": """
    【之前的发现】
    - TOP 20城市贡献了60%的销售额
    - RANK 21-50城市贡献了25%，苏州、杭州表现突出
    """
}
```

**第4段分析（最后一段）**：
```python
context = {
    "question": "各城市的销售额是多少？",
    "chunk_info": "分段4/4: 其他城市（聚合）",
    "data": [聚合数据],
    "accumulated_insights": """
    【之前的发现】
    - TOP 20城市贡献了60%的销售额
    - RANK 21-50城市贡献了25%
    - RANK 51-100城市贡献了10%
    """,
    "is_final_chunk": true  # 标记为最后一段，需要生成综合分析
}
```

---

## 6. Prompt设计

### 6.1 洞察Agent Prompt（分段分析）

```python
INSIGHT_AGENT_PROMPT_CHUNKED = """
你是一位专业的数据分析师。你正在分析一个大型数据集，数据已被分段处理。

【问题】
{question}

【当前分段信息】
{chunk_info}

【累积上下文】
{accumulated_insights}

【当前分段数据】
{current_chunk_data}

【任务】
1. 分析当前分段的数据
2. 结合累积上下文，避免重复分析
3. 提取当前分段的关键发现
4. {final_instruction}

请提供你的分析。
"""

# final_instruction根据是否是最后一段而不同：
# - 非最后一段："关注当前分段的特点和发现"
# - 最后一段："生成综合分析，整合所有分段的发现"
```

### 6.2 重规划Agent Prompt（综合决策）

```python
REPLANNER_AGENT_PROMPT = """
你是一位资深的数据分析专家。你需要综合所有维度的洞察，决定下一步行动。

【原始问题】
{original_question}

【分析模式】
{analysis_mode}  # exploratory 或 normal

【所有维度的洞察】
{all_task_insights}

【之前的决策历史】
{previous_decisions}

【分析路径】
{analysis_path}

【覆盖度分析】
- 维度覆盖度：{dimension_coverage}%
- 数据覆盖度：{data_coverage}%
- 问题覆盖度：{question_coverage}%

【任务】
1. 综合分析所有洞察，识别关联关系
2. 判断是否已找到根本原因
3. 评估分析的完整性
4. 决定下一步行动：
   - CONTINUE_EXPLORE: 生成多个问题并行探索（2-5个）
   - FOCUS_ANALYSIS: 生成1个聚焦问题深入分析
   - COMPLETE: 完成分析

请提供你的决策和理由。
"""
```

---

## 7. 接口设计

### 7.1 主流程接口

```python
class AnalysisEngine:
    async def analyze(
        self, 
        question: str,
        mode: AnalysisMode = AnalysisMode.AUTO
    ) -> AnalysisResult:
        """
        执行分析
        
        Args:
            question: 用户问题
            mode: 分析模式（AUTO自动判断，NORMAL普通，EXPLORATORY探索式）
            
        Returns:
            分析结果
        """
        pass
```

### 7.2 状态查询接口

```python
class AnalysisEngine:
    def get_analysis_state(self, session_id: str) -> AnalysisState:
        """获取分析状态"""
        pass
    
    def get_progress(self, session_id: str) -> ProgressInfo:
        """获取分析进度"""
        pass
```

---

## 8. 错误处理和边界情况

### 8.1 查询失败处理

- 查询超时：重试3次，失败后标记任务失败
- 查询错误：记录错误信息，继续执行其他任务
- 数据为空：生成"无数据"洞察，继续分析

### 8.2 Token超限处理

- 实时监控token大小
- 达到80%阈值时触发压缩
- 压缩策略：保留最新洞察，历史洞察仅保留摘要

### 8.3 重规划循环控制

- 最大重规划次数：5次
- 超过限制时强制完成
- 记录警告信息

---

## 9. 性能优化

### 9.1 并行执行优化

- 最大并发数：3个任务
- 动态调度：任务完成后立即启动下一个
- 预期性能提升：40%（相比串行执行）

### 9.2 缓存策略

- 查询结果缓存：相同查询直接返回缓存
- 洞察缓存：相同数据的洞察可复用
- 缓存过期时间：1小时

### 9.3 分段优化

- 智能分段策略选择
- 分段大小动态调整
- 预期支持数据量：10000+行

---

## 10. 测试策略

### 10.1 单元测试

- 数据结构测试
- 组件接口测试
- 工具函数测试

### 10.2 集成测试

- 完整工作流测试
- 并行执行测试
- 分段处理测试

### 10.3 端到端测试

- 探索式分析场景测试
- 普通分析场景测试
- 边界情况测试

---

**设计文档版本**: v1.0
**最后更新**: 2025-01-XX
**文档状态**: 待审核
