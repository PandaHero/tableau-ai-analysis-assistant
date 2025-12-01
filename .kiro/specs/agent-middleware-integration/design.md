# 设计文档：Agent 中间件集成

## 概述

本设计文档描述了 Tableau Assistant 的 Agent 中间件集成方案，基于 DeepAgents 框架和 LangChain 中间件系统实现完整的 Agent 能力增强。

### 设计原则

1. **利用现有框架**：直接使用 DeepAgents 和 LangChain 提供的中间件，不重复造轮子
2. **统一架构**：所有 Agent 节点通过工具系统交互，而不是直接调用 LLM
3. **渐进式增强**：保持现有功能，逐步添加中间件能力
4. **可配置性**：所有中间件参数可通过环境变量或配置文件调整

### 核心架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DeepAgent (主 Agent)                              │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                    内置中间件栈                                   ││
│  │                                                                   ││
│  │  1. TodoListMiddleware          - 任务管理                       ││
│  │  2. FilesystemMiddleware        - 文件系统 + 大结果处理          ││
│  │  3. SubAgentMiddleware          - 子代理（task 工具）            ││
│  │  4. SummarizationMiddleware     - 对话总结                       ││
│  │  5. AnthropicPromptCachingMiddleware - Claude Prompt 缓存        ││
│  │  6. PatchToolCallsMiddleware    - 参数修复                       ││
│  │  7. HumanInTheLoopMiddleware    - 人工介入（可选）               ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

### 工作流架构与 Agent 工具分配

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         StateGraph 工作流                                    │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                                                                       │   │
│  │   START                                                               │   │
│  │     │                                                                 │   │
│  │     ▼                                                                 │   │
│  │  ┌─────────┐                                                          │   │
│  │  │ Boost?  │──── No ────────────────────────┐                        │   │
│  │  └────┬────┘                                │                        │   │
│  │       │ Yes                                 │                        │   │
│  │       ▼                                     │                        │   │
│  │  ┌─────────────────────────────────────┐   │                        │   │
│  │  │        Boost Agent (LLM)            │   │                        │   │
│  │  │  工具: get_metadata                 │   │                        │   │
│  │  │  输入: original_question            │   │                        │   │
│  │  │  输出: boosted_question             │   │                        │   │
│  │  └────────────────┬────────────────────┘   │                        │   │
│  │                   │                        │                        │   │
│  │                   ▼                        ▼                        │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │              Understanding Agent (LLM)                       │   │   │
│  │  │  工具: parse_date                                            │   │   │
│  │  │  输入: current_question                                      │   │   │
│  │  │  输出: QuestionUnderstanding                                │   │   │
│  │  │        (dimensions, measures, filters, table_calc_type,     │   │   │
│  │  │         table_calc_dimensions) - 使用语义字段名              │   │   │
│  │  └────────────────────────────┬────────────────────────────────┘   │   │
│  │                               │                                     │   │
│  │                               ▼                                     │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │                Planning Agent (LLM)                          │   │   │
│  │  │  工具: get_metadata, semantic_map_fields                     │   │   │
│  │  │  输入: QuestionUnderstanding                                 │   │   │
│  │  │  输出: QueryPlan                                             │   │   │
│  │  │        (dimensions, measures, filters, table_calc: Intent)   │   │   │
│  │  └────────────────────────────┬────────────────────────────────┘   │   │
│  │                               │                                     │   │
│  │                               ▼                                     │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │              Execute Node (非 LLM，确定性执行)               │   │   │
│  │  │  功能:                                                       │   │   │
│  │  │    1. QueryPlan → VizQL Query 转换                          │   │   │
│  │  │       (TableCalcIntent → TableCalcField)                    │   │   │
│  │  │    2. 调用 VizQL Data Service API                           │   │   │
│  │  │    3. 返回查询结果                                          │   │   │
│  │  │  输入: QueryPlan                                             │   │   │
│  │  │  输出: QueryResult                                           │   │   │
│  │  └────────────────────────────┬────────────────────────────────┘   │   │
│  │                               │                                     │   │
│  │                               ▼                                     │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │                Insight Agent (LLM)                           │   │   │
│  │  │  工具: detect_statistics, analyze_chunk                      │   │   │
│  │  │  输入: QueryResult, original_question                        │   │   │
│  │  │  输出: accumulated_insights                                  │   │   │
│  │  │  特性: 渐进式分析（大数据分块处理）                          │   │   │
│  │  └────────────────────────────┬────────────────────────────────┘   │   │
│  │                               │                                     │   │
│  │                               ▼                                     │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │               Replanner Agent (LLM)                          │   │   │
│  │  │  工具: analyze_completeness                                  │   │   │
│  │  │  输入: original_question, accumulated_insights, QueryResult  │   │   │
│  │  │  输出: ReplanDecision                                        │   │   │
│  │  │        (should_replan, completeness_score, new_question)     │   │   │
│  │  └────────────────────────────┬────────────────────────────────┘   │   │
│  │                               │                                     │   │
│  │                    ┌──────────┴──────────┐                         │   │
│  │                    │                     │                         │   │
│  │            should_replan?          completeness >= 0.9             │   │
│  │            replan_count < max?      或 replan_count >= max         │   │
│  │                    │                     │                         │   │
│  │                    ▼                     ▼                         │   │
│  │              ┌──────────┐          ┌──────────┐                    │   │
│  │              │ Planning │          │   END    │                    │   │
│  │              │ (跳过    │          └──────────┘                    │   │
│  │              │Understanding)                                       │   │
│  │              └──────────┘                                          │   │
│  │                                                                    │   │
│  └────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Agent 工具分配表

| Agent | 类型 | 可用工具 | 输入 | 输出 |
|-------|------|---------|------|------|
| Boost Agent | LLM | get_metadata | original_question | boosted_question |
| Understanding Agent | LLM | parse_date | current_question | QuestionUnderstanding（语义字段名） |
| Planning Agent | LLM | get_metadata, semantic_map_fields | QuestionUnderstanding | QueryPlan（映射后字段名） |
| Execute Node | 非 LLM | 内部调用 VizQL API | QueryPlan | QueryResult |
| Insight Agent | LLM | detect_statistics, analyze_chunk | QueryResult, original_question | accumulated_insights |
| Replanner Agent | LLM | analyze_completeness | insights, QueryResult, original_question | ReplanDecision |

### 数据流转图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              数据流转                                        │
│                                                                              │
│  original_question                                                           │
│        │                                                                     │
│        ▼                                                                     │
│  ┌──────────┐     boosted_question                                          │
│  │  Boost   │ ─────────────────────┐                                        │
│  └──────────┘                      │                                        │
│        │                           │                                        │
│        ▼                           ▼                                        │
│  ┌──────────────────────────────────────┐                                   │
│  │         Understanding Agent          │                                   │
│  │                                      │                                   │
│  │  current_question (仅问题文本)       │                                   │
│  │            ↓                         │                                   │
│  │  QuestionUnderstanding (语义字段名): │                                   │
│  │  - question_type                     │                                   │
│  │  - dimensions: [语义字段名]          │                                   │
│  │  - measures: [语义字段名]            │                                   │
│  │  - filters: [语义字段名]             │                                   │
│  │  - table_calc_type: TableCalcType    │  ← 识别表计算类型                 │
│  │  - table_calc_dimensions: [语义名]   │  ← 识别表计算维度                 │
│  └──────────────────┬───────────────────┘                                   │
│                     │                                                        │
│                     ▼                                                        │
│  ┌──────────────────────────────────────┐                                   │
│  │           Planning Agent             │                                   │
│  │  工具: get_metadata, semantic_map    │                                   │
│  │                                      │                                   │
│  │  QuestionUnderstanding (语义字段名)  │                                   │
│  │            ↓                         │                                   │
│  │  调用 semantic_map_fields() 映射     │                                   │
│  │            ↓                         │                                   │
│  │  QueryPlan (映射后实际字段名):       │                                   │
│  │  - dimensions: [mapped_field]        │                                   │
│  │  - measures: [mapped_field]          │                                   │
│  │  - filters: [mapped_field]           │                                   │
│  │  - table_calc: TableCalcIntent       │  ← 中间层表计算意图               │
│  │  - topn: TopNIntent                  │                                   │
│  └──────────────────┬───────────────────┘                                   │
│                     │                                                        │
│                     ▼                                                        │
│  ┌──────────────────────────────────────┐                                   │
│  │         Execute Node (非 LLM)        │                                   │
│  │                                      │                                   │
│  │  QueryPlan (中间层)                  │                                   │
│  │            ↓                         │                                   │
│  │  转换为 VizQL Query:                 │                                   │
│  │  - DimensionIntent → DimensionField  │                                   │
│  │  - MeasureIntent → MeasureField      │                                   │
│  │  - FilterIntent → Filter             │                                   │
│  │  - TableCalcIntent → TableCalcField  │  ← 在这里转换！                   │
│  │            ↓                         │                                   │
│  │  调用 VizQL Data Service API         │                                   │
│  │            ↓                         │                                   │
│  │  QueryResult                         │                                   │
│  └──────────────────┬───────────────────┘                                   │
│                     │                                                        │
│                     ▼                                                        │
│  ┌──────────────────────────────────────┐                                   │
│  │           Insight Agent              │                                   │
│  │                                      │                                   │
│  │  QueryResult + original_question     │                                   │
│  │            ↓                         │                                   │
│  │  accumulated_insights                │                                   │
│  └──────────────────┬───────────────────┘                                   │
│                     │                                                        │
│                     ▼                                                        │
│  ┌──────────────────────────────────────┐                                   │
│  │          Replanner Agent             │                                   │
│  │                                      │                                   │
│  │  insights + QueryResult + question   │                                   │
│  │            ↓                         │                                   │
│  │  ReplanDecision:                     │                                   │
│  │  - should_replan: bool               │                                   │
│  │  - completeness_score: float         │                                   │
│  │  - new_question: str (如果重规划)    │                                   │
│  └──────────────────────────────────────┘                                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 组件设计

### 1. DeepAgent 工厂（重构）

```python
# tableau_assistant/src/agents/deep_agent_factory.py

from deepagents import create_deep_agent, FilesystemMiddleware, SubAgentMiddleware
from langchain.agents.middleware import (
    TodoListMiddleware,
    SummarizationMiddleware,
    HumanInTheLoopMiddleware,
    PatchToolCallsMiddleware,
)
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
from deepagents.backends import StateBackend, StoreBackend, CompositeBackend

def create_tableau_deep_agent(
    tools: List[BaseTool],
    model_name: Optional[str] = None,
    store: Optional[BaseStore] = None,
    system_prompt: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None
) -> CompiledStateGraph:
    """
    创建 Tableau Assistant 的 DeepAgent
    
    使用 create_deep_agent() 自动获得所有内置中间件：
    - TodoListMiddleware: 任务管理
    - FilesystemMiddleware: 文件系统工具 + 大结果处理
    - SubAgentMiddleware: 子代理支持
    - SummarizationMiddleware: 对话总结
    - AnthropicPromptCachingMiddleware: Claude Prompt 缓存
    - PatchToolCallsMiddleware: 参数修复
    
    Args:
        tools: 业务工具列表
        model_name: LLM 模型名称
        store: 持久化存储实例
        system_prompt: 系统提示词
        config: 额外配置
            - max_tokens_before_summary: 触发总结的 token 阈值
            - messages_to_keep: 总结后保留的消息数
            - tool_token_limit_before_evict: 触发文件写入的 token 阈值
            - interrupt_on: 需要人工确认的工具列表
    
    Returns:
        编译后的 DeepAgent 图
    """
    config = config or {}
    
    # 配置后端
    # 使用 CompositeBackend 支持混合存储：
    # - 默认使用 StateBackend（临时存储）
    # - /persistent/ 路径使用 StoreBackend（持久化）
    if store:
        backend = CompositeBackend(
            default=lambda rt: StateBackend(rt),
            routes={"/persistent/": lambda rt: StoreBackend(rt, store)}
        )
    else:
        backend = lambda rt: StateBackend(rt)
    
    # 配置中断
    interrupt_on = config.get("interrupt_on")
    
    # 创建 DeepAgent
    # create_deep_agent 自动配置所有中间件
    agent = create_deep_agent(
        model=model_name or get_default_model(),
        tools=tools,
        subagents=[],  # 不使用自定义子代理，但保留通用子代理
        store=store,
        backend=backend,
        system_prompt=system_prompt,
        interrupt_on=interrupt_on,
        checkpointer=True,
        debug=config.get("debug", False)
    )
    
    return agent
```

### 2. 中间件配置详解

#### 2.1 TodoListMiddleware

```python
# 自动由 create_deep_agent 配置
# 提供 write_todos 工具

# 状态结构
class TodoState(TypedDict):
    todos: List[TodoItem]

class TodoItem(TypedDict):
    id: str
    description: str
    status: Literal["pending", "in_progress", "completed"]

# 使用示例（Agent 自动调用）
# Agent 会在复杂任务时自动使用 write_todos 工具
```

#### 2.2 FilesystemMiddleware

```python
# 配置
FilesystemMiddleware(
    backend=backend,  # StateBackend 或 CompositeBackend
    tool_token_limit_before_evict=20000,  # 超过此阈值写入文件
)

# 提供的工具
# - ls: 列出目录
# - read_file: 读取文件（支持 offset + limit 分页）
# - write_file: 写入文件
# - edit_file: 编辑文件
# - glob: 文件模式匹配
# - grep: 文件内容搜索
# - execute: 执行命令（需要 SandboxBackend）

# 大结果处理
# 当工具输出超过 tool_token_limit_before_evict 时：
# 1. 自动写入 /large_tool_results/{tool_call_id}
# 2. 返回文件路径和前 10 行预览
# 3. Agent 可以使用 read_file 分页读取
```

#### 2.3 SummarizationMiddleware

```python
# 配置
SummarizationMiddleware(
    model=model,
    max_tokens_before_summary=170000,  # 触发总结的阈值
    messages_to_keep=6,  # 保留最近 N 条消息
)

# 工作流程
# 1. 监控消息 token 数
# 2. 超过阈值时触发总结
# 3. 保留最近 N 条消息
# 4. 用总结替换旧消息
```

#### 2.4 PatchToolCallsMiddleware

```python
# 自动由 create_deep_agent 配置
# 功能：
# - 自动修复工具调用参数类型错误
# - 尝试从上下文推断缺失参数
# - 修复失败时返回清晰错误信息
```

#### 2.5 AnthropicPromptCachingMiddleware

```python
# 配置
AnthropicPromptCachingMiddleware(
    unsupported_model_behavior="ignore"  # 非 Claude 模型时静默忽略
)

# 功能：
# - 为 Claude 模型启用 Prompt 缓存
# - 降低成本和延迟
# - 自动处理缓存键生成
```

#### 2.6 HumanInTheLoopMiddleware

```python
# 配置
HumanInTheLoopMiddleware(
    interrupt_on={
        "execute_vizql_query": True,  # 执行查询前确认
        "write_file": InterruptOnConfig(
            description_prefix="文件写入需要确认"
        )
    }
)

# 工作流程
# 1. 检测到配置的工具调用
# 2. 返回中断状态
# 3. 等待用户确认/拒绝
# 4. 继续或跳过工具调用
```

#### 2.7 SubAgentMiddleware

```python
# 配置
SubAgentMiddleware(
    default_model=model,
    default_tools=tools,
    subagents=[],  # 可以添加自定义子代理
    general_purpose_agent=True,  # 启用通用子代理
    default_middleware=[
        TodoListMiddleware(),
        FilesystemMiddleware(backend=backend),
        SummarizationMiddleware(model=model, ...),
        AnthropicPromptCachingMiddleware(...),
        PatchToolCallsMiddleware(),
    ]
)

# 提供 task 工具
# Agent 可以启动子代理处理复杂任务
# 子代理独立运行，返回最终结果
```

### 3. Understanding Agent 表计算识别

#### 3.1 现有架构说明

Understanding Agent 已经使用 `BaseVizQLAgent` 架构和 4 段式 Prompt 模板（`VizQLPrompt`）。本次需求是在现有基础上**添加表计算识别能力**。

```python
# 现有架构（保持不变）
class UnderstandingAgent(BaseVizQLAgent):
    def __init__(self):
        super().__init__(UNDERSTANDING_PROMPT)  # 使用 VizQLPrompt 模板
```

#### 3.2 Prompt 模板增强（遵循 unified-refactor 中的模板规则）

需要在现有的 `UnderstandingPrompt` 的 `get_specific_domain_knowledge()` 方法中添加表计算识别规则：

```python
# tableau_assistant/prompts/understanding.py (enhancement)

# Add the following content to get_specific_domain_knowledge():

"""
Step 6: Identify table calculation requirements
For each question, check for table calculation keywords:

| Keywords | Table Calc Type |
|----------|-----------------|
| running total, cumulative, accumulated | RUNNING_TOTAL |
| rank, ranking, top N, position | RANK |
| moving average, rolling average, sliding | MOVING_CALCULATION |
| percent of total, percentage, share, proportion | PERCENT_OF_TOTAL |
| difference from, change from, compared to, year over year, month over month | DIFFERENCE_FROM |
| percent difference from, percentage change | PERCENT_DIFFERENCE_FROM |
| percentile, quartile | PERCENTILE |

Step 7: Determine table calc dimensions (if table calc detected)

**Table Calculation dimensions determination:**

Rule: dimensions = fields where calculation operates ACROSS
      partition = fields where calculation RESTARTS (NOT in dimensions)

Step 7.1: List all dimension fields in query

Step 7.2: For each dimension, ask:
- "Should calculation operate ACROSS this field's values?" → Include in dimensions
- "Should calculation RESTART for each value of this field?" → Exclude from dimensions

Step 7.3: Verify
- dimensions must be non-empty
- dimensions must be subset of query dimensions

| Category | Types | dimensions Question |
|----------|-------|---------------------|
| Sequential | RUNNING_TOTAL, MOVING_CALCULATION | "Calculate ACROSS which field in order?" |
| Range-based | RANK, PERCENTILE, PERCENT_OF_TOTAL | "Calculate WITHIN which field's scope?" |
| Comparison | DIFFERENCE_FROM, PERCENT_FROM, PERCENT_DIFFERENCE_FROM | "Compare ALONG which field?" |
"""
```

#### 3.3 数据模型增强（遵循 unified-refactor 中的数据模型格式）

在现有的 `QuestionUnderstanding` 模型中添加两个字段，**严格遵循 unified-refactor 中定义的 Field description 格式**：

```python
# tableau_assistant/src/models/question.py（新增字段）

from enum import Enum

class TableCalcType(str, Enum):
    """Table calculation types supported by VizQL Data Service."""
    RUNNING_TOTAL = "RUNNING_TOTAL"
    RANK = "RANK"
    MOVING_CALCULATION = "MOVING_CALCULATION"
    PERCENT_OF_TOTAL = "PERCENT_OF_TOTAL"
    DIFFERENCE_FROM = "DIFFERENCE_FROM"
    PERCENT_FROM = "PERCENT_FROM"
    PERCENT_DIFFERENCE_FROM = "PERCENT_DIFFERENCE_FROM"
    PERCENTILE = "PERCENTILE"
    CUSTOM = "CUSTOM"
    NESTED = "NESTED"


# 在 QuestionUnderstanding 类中添加以下字段：

table_calc_type: Optional[TableCalcType] = Field(
    default=None,
    description="""Table calculation type identified from keywords.

Usage:
- Set based on keyword detection in user question
- null if no table calculation needed

Values: TableCalcType enum or null
- RUNNING_TOTAL: running total, cumulative, accumulated
- RANK: rank, ranking, top N, position
- MOVING_CALCULATION: moving average, rolling average
- PERCENT_OF_TOTAL: percent of total, percentage, share
- DIFFERENCE_FROM: difference from, change from, year over year
- PERCENT_DIFFERENCE_FROM: percent difference, percentage change
- PERCENTILE: percentile, quartile"""
)

table_calc_dimensions: Optional[List[TableCalcFieldReference]] = Field(
    default=None,
    description="""Fields that define calculation scope.

Usage:
- Include fields where calculation operates ACROSS their values
- Exclude fields where calculation RESTARTS for each value
- Must be subset of query's dimension fields
- null if no table calculation needed

Values: List of TableCalcFieldReference or null
- fieldCaption: Field name from query dimensions
- function: Optional, for date fields (YEAR, MONTH, etc.)

Examples:

1. RUNNING_TOTAL - "Running total of sales by region over time"
   Query dimensions: [Region, Order Date]
   table_calc_dimensions: [TableCalcFieldReference(fieldCaption="Order Date")]
   Why: Calculate across dates, restart for each region

2. RANK - "Rank products by sales within each category"
   Query dimensions: [Category, Product]
   table_calc_dimensions: [TableCalcFieldReference(fieldCaption="Product")]
   Why: Rank across products, restart for each category

3. PERCENT_OF_TOTAL - "Each region's percent of total sales"
   Query dimensions: [Region]
   table_calc_dimensions: [TableCalcFieldReference(fieldCaption="Region")]
   Why: Calculate percent across all regions

4. DIFFERENCE_FROM - "Month over month sales change"
   Query dimensions: [Order Date(MONTH)]
   table_calc_dimensions: [TableCalcFieldReference(fieldCaption="Order Date", function="MONTH")]
   Why: Compare across months"""
)

### 4. Planning Agent（工具辅助 LLM）

Planning Agent 使用工具将语义字段名映射到实际字段名。

#### 4.1 工具定义

```python
# tableau_assistant/src/tools/planning.py

async def get_metadata(datasource_id: str) -> Dict[str, Any]:
    """
    获取数据源元数据
    
    Returns:
        {
            "dimensions": [{"fieldCaption": str, "dataType": str, ...}],
            "measures": [{"fieldCaption": str, "dataType": str, ...}]
        }
    """
    pass


async def semantic_map_fields(
    semantic_fields: List[str],
    metadata: Dict[str, Any]
) -> Dict[str, str]:
    """
    将语义字段名映射到实际字段名
    
    Args:
        semantic_fields: 语义字段名列表（如 ["销售额", "地区", "日期"]）
        metadata: 数据源元数据
    
    Returns:
        映射字典 {"销售额": "Sales", "地区": "Region", "日期": "Order Date"}
    """
    pass
```

#### 4.2 输入输出

```
输入:
- QuestionUnderstanding (来自 Understanding Agent，使用语义字段名)

输出:
- QueryPlan (中间层，使用映射后的实际字段名)
```

#### 4.3 Prompt 模板规则（遵循 4 段式 VizQLPrompt 格式）

```python
# tableau_assistant/prompts/planning.py

class PlanningPrompt(VizQLPrompt):
    """Planning Agent 的 4 段式 Prompt 模板"""
    
    def get_system_role(self) -> str:
        return """You are a query planning expert for Tableau data analysis.

Your role:
- Convert QuestionUnderstanding (semantic field names) to QueryPlan (actual field names)
- Use get_metadata() to get data source schema
- Use semantic_map_fields() to map semantic names to actual fieldCaption
- Generate Intent-level specifications (not VizQL API format)"""
    
    def get_task_description(self) -> str:
        return """Generate a QueryPlan based on QuestionUnderstanding.

Input:
- QuestionUnderstanding: Parsed question with semantic field names

Available Tools:
- get_metadata(datasource_id): Get data source schema
- semantic_map_fields(semantic_fields, metadata): Map semantic names to actual field names

Output:
- QueryPlan: Query specification with mapped actual field names"""
    
    def get_output_format(self) -> str:
        return """Return a valid QueryPlan JSON object.

Required fields:
- plan_id: string (generate unique ID)
- original_question: string (copy from input)
- description: string (human-readable description)
- dimensions: array of DimensionIntent objects (with mapped_field)
- measures: array of MeasureIntent objects (with mapped_field)
- filters: array of FilterIntent objects (with mapped_field)
- date_filters: array of DateFilterIntent objects (with mapped_field)
- table_calc: TableCalcIntent object or null
- topn: TopNIntent object or null"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """**Query Planning Process:**

Step 1: Get metadata and map semantic fields
- Call get_metadata() to get data source schema
- Extract all semantic field names from QuestionUnderstanding
- Call semantic_map_fields() to map to actual fieldCaption

Step 2: Build dimension specifications
- For each QuestionUnderstanding.dimensions:
  * Use mapped field name from semantic_map_fields result
  * Preserve date function if specified
  * Create DimensionIntent with mapped_field

Step 3: Build measure specifications
- For each QuestionUnderstanding.measures:
  * Use mapped field name from semantic_map_fields result
  * Validate aggregation function (SUM, AVG, COUNT, etc.)
  * Create MeasureIntent with mapped_field and aggregation

Step 4: Build filter specifications
- For each QuestionUnderstanding.filters:
  * Use mapped field name from semantic_map_fields result
  * Validate operator and values
  * Create FilterIntent with mapped_field

Step 5: Build table calculation specification (if needed)
- If QuestionUnderstanding.table_calc_type is not null:
  * Select base_measure from measures list
  * Map table_calc_dimensions field names using semantic_map_fields
  * Create TableCalcIntent with mapped dimensions

Step 6: Use RAG for optimization
- Call rag_search("best_practices", query_description)
- Apply best practices for field combinations
- Optimize filter conditions

**Field Mapping Rules:**
- Always use semantic_map_fields() for field name mapping
- Store original semantic name in field_name
- Store mapped actual name in mapped_field
- Validate all mapped fields exist in metadata

**Validation Rules:**
- All mapped_field values must exist in metadata
- dimensions must be non-empty for table calculations
- table_calc.dimensions must be subset of query dimensions"""
```

#### 4.4 工作流程示例

```
输入 QuestionUnderstanding:
{
  "dimensions": [{"field_name": "地区"}, {"field_name": "日期", "function": "MONTH"}],
  "measures": [{"field_name": "销售额", "aggregation": "SUM"}],
  "table_calc_type": "RUNNING_TOTAL",
  "table_calc_dimensions": [{"fieldCaption": "日期"}]
}

Step 1: 调用 get_metadata()
→ 获取数据源字段列表

Step 2: 调用 semantic_map_fields(["地区", "日期", "销售额"], metadata)
→ {"地区": "Region", "日期": "Order Date", "销售额": "Sales"}

Step 3: 调用 rag_search("running total by region over time", "query_patterns")
→ 获取相似查询模式

Step 4: 构建 QueryPlan（使用映射后的字段名）
{
  "dimensions": [
    {"field_name": "地区", "mapped_field": "Region"},
    {"field_name": "日期", "mapped_field": "Order Date", "function": "MONTH"}
  ],
  "measures": [
    {"field_name": "销售额", "mapped_field": "Sales", "aggregation": "SUM"}
  ],
  "table_calc": {
    "calc_type": "RUNNING_TOTAL",
    "base_measure": {"mapped_field": "Sales", "aggregation": "SUM"},
    "dimensions": [{"fieldCaption": "Order Date", "function": "MONTH"}]
  }
}
```

#### 4.5 旧格式参考（已废弃）

以下是旧的对话式格式，**不要使用**：

```python
# ❌ 错误格式 - 不要使用
"""
你是一个查询规划专家。根据问题理解结果，生成查询计划。

**输入:**
- QuestionUnderstanding: 问题理解结果
- metadata: 数据源元数据

**输出:**
- QueryPlan: 查询计划（中间层）

**规则:**

Step 1: 确定维度字段
- 从 QuestionUnderstanding.dimensions 复制
- 验证字段存在于 metadata 中

Step 2: 确定度量字段
- 从 QuestionUnderstanding.measures 复制
- 验证聚合函数有效

Step 3: 确定过滤条件
- 从 QuestionUnderstanding.filters 复制
- 从 QuestionUnderstanding.date_filters 复制

Step 4: 确定表计算（如果有）
- 如果 QuestionUnderstanding.table_calc_type 不为空
- 构建 TableCalcIntent:
  * calc_type: 从 table_calc_type 复制
  * base_measure: 选择主要度量
  * dimensions: 从 table_calc_dimensions 复制
  * 类型特定参数（window_size, rank_order, compare_to）

Step 5: 确定 TopN（如果有）
- 从 QuestionUnderstanding.topn 复制

**注意:**
- QueryPlan 是中间层，使用 Intent 类型
- 不要生成 VizQL API 格式
- TableCalcIntent → TableCalcField 的转换在 Execute Node 中进行
"""
```

### 5. Execute Node（非 LLM，确定性执行）

Execute Node 是**非 LLM 节点**，执行确定性的转换和 API 调用。

#### 5.1 职责

1. **QueryPlan → VizQL Query 转换**
   - DimensionIntent → DimensionField
   - MeasureIntent → MeasureField
   - FilterIntent → Filter
   - TableCalcIntent → TableCalcField ← **在这里转换！**
   - TopNIntent → TopNFilter

2. **调用 VizQL Data Service API**

3. **返回查询结果**

#### 5.2 转换逻辑

```python
# tableau_assistant/src/agents/nodes/execute.py

async def execute_query_node(
    state: VizQLState,
    config: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    执行查询节点（非 LLM，确定性执行）
    
    1. 将 QueryPlan (Intent) 转换为 VizQL Query (Field)
    2. 调用 VizQL Data Service API
    3. 返回查询结果
    """
    query_plan = state.get("query_plan")
    
    # 1. 转换为 VizQL Query
    vizql_query = QueryBuilder.build_vizql_query(query_plan)
    
    # 2. 调用 API
    result = await VizQLClient.query_datasource(vizql_query)
    
    # 3. 返回结果
    return {
        "query_result": QueryResult(
            plan_id=query_plan.plan_id,
            data=result.data,
            row_count=len(result.data),
            columns=result.columns,
            execution_time_ms=result.execution_time_ms,
            is_replan=query_plan.is_replan
        )
    }
```

#### 5.3 QueryBuilder 转换逻辑

```python
# tableau_assistant/src/capabilities/query/builder.py

class QueryBuilder:
    """将 QueryPlan (Intent) 转换为 VizQL Query (Field)"""
    
    @staticmethod
    def build_vizql_query(query_plan: QueryPlan) -> VizQLQuery:
        """构建 VizQL 查询"""
        fields = []
        filters = []
        
        # 1. 转换维度字段
        for dim in query_plan.dimensions:
            fields.append(QueryBuilder._build_dimension_field(dim))
        
        # 2. 转换度量字段
        for measure in query_plan.measures:
            fields.append(QueryBuilder._build_measure_field(measure))
        
        # 3. 转换表计算字段（如果有）
        if query_plan.table_calc:
            fields.append(QueryBuilder._build_table_calc_field(
                query_plan.table_calc,
                query_plan.dimensions
            ))
        
        # 4. 转换过滤器
        for f in query_plan.filters:
            filters.append(QueryBuilder._build_filter(f))
        
        for df in query_plan.date_filters:
            filters.append(QueryBuilder._build_date_filter(df))
        
        # 5. 转换 TopN（如果有）
        if query_plan.topn:
            filters.append(QueryBuilder._build_topn_filter(query_plan.topn))
        
        return VizQLQuery(fields=fields, filters=filters)
    
    @staticmethod
    def _build_table_calc_field(
        intent: TableCalcIntent,
        query_dimensions: List[DimensionIntent]
    ) -> TableCalcField:
        """
        将 TableCalcIntent 转换为 TableCalcField
        
        这是 Intent → Field 转换的核心逻辑
        """
        # 1. 验证 dimensions 是查询维度的子集
        query_dim_names = {d.mapped_field for d in query_dimensions}
        intent_dim_names = {d.fieldCaption for d in intent.dimensions}
        
        if not intent_dim_names.issubset(query_dim_names):
            invalid = intent_dim_names - query_dim_names
            raise ValidationError(f"Invalid dimensions: {invalid}")
        
        # 2. 生成 fieldCaption
        field_caption = f"{intent.base_measure.mapped_field}_{intent.calc_type.value}"
        
        # 3. 构建 tableCalculation
        table_calc_spec = QueryBuilder._build_table_calc_specification(intent)
        
        # 4. 返回 TableCalcField
        return TableCalcField(
            fieldCaption=field_caption,
            function=Function(intent.base_measure.aggregation),
            tableCalculation=table_calc_spec
        )
    
    @staticmethod
    def _build_table_calc_specification(intent: TableCalcIntent) -> TableCalcSpecification:
        """根据 calc_type 构建对应的 TableCalcSpecification"""
        
        base_spec = {
            "tableCalcType": intent.calc_type.value,
            "dimensions": [d.model_dump() for d in intent.dimensions]
        }
        
        if intent.calc_type == TableCalcType.RUNNING_TOTAL:
            return RunningTotalTableCalcSpecification(
                **base_spec,
                aggregation=intent.aggregation or "SUM"
            )
        
        elif intent.calc_type == TableCalcType.MOVING_CALCULATION:
            return MovingTableCalcSpecification(
                **base_spec,
                aggregation=intent.aggregation or "AVG",
                previous=intent.window_size or -2,
                next=0,
                includeCurrent=True
            )
        
        elif intent.calc_type == TableCalcType.RANK:
            return RankTableCalcSpecification(
                **base_spec,
                rankType="COMPETITION",
                direction=SortDirection(intent.rank_order or "DESC")
            )
        
        elif intent.calc_type in [TableCalcType.DIFFERENCE_FROM, 
                                   TableCalcType.PERCENT_FROM, 
                                   TableCalcType.PERCENT_DIFFERENCE_FROM]:
            return DifferenceTableCalcSpecification(
                **base_spec,
                relativeTo=intent.compare_to or "PREVIOUS"
            )
        
        elif intent.calc_type == TableCalcType.PERCENT_OF_TOTAL:
            return PercentOfTotalTableCalcSpecification(**base_spec)
        
        elif intent.calc_type == TableCalcType.PERCENTILE:
            return PercentileTableCalcSpecification(**base_spec)
        
        else:
            raise ValueError(f"Unsupported calc_type: {intent.calc_type}")

### 6. Boost Agent 元数据使用

```python
# tableau_assistant/src/agents/nodes/question_boost.py

async def question_boost_agent_node(
    state: VizQLState,
    runtime: Runtime[VizQLContext],
    metadata: Optional[Dict[str, Any]] = None,
    use_metadata: bool = True,  # 改为默认 True
    model_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    问题 Boost Agent 节点
    
    默认使用元数据来优化问题：
    - 参考维度层级关系
    - 参考 sample values
    - 补充缺失信息
    """
    # 如果 use_metadata=True 且元数据不可用，尝试获取
    if use_metadata and metadata is None and "metadata" not in state:
        try:
            metadata_manager = MetadataManager(runtime)
            metadata_obj = await metadata_manager.get_metadata_async(
                use_cache=True,
                enhance=True
            )
            metadata = metadata_obj.model_dump()
        except Exception as e:
            logger.warning(f"获取元数据失败，降级为不使用元数据: {e}")
            metadata = None
    
    return await question_boost_agent.execute(
        state=state,
        runtime=runtime,
        metadata=metadata,
        use_metadata=use_metadata,
        model_config=model_config
    )
```

### 7. Replanner Agent 智能重规划

#### 7.1 工具定义

Replanner Agent 使用以下工具来评估完成度：

```python
# tableau_assistant/src/tools/analysis.py

async def analyze_completeness(
    original_question: str,
    insights: List[Insight],
    query_result: QueryResult,
    query_history: List[QueryResult]
) -> Dict[str, Any]:
    """
    分析查询结果的完成度
    
    Args:
        original_question: 原始问题
        insights: 已生成的洞察
        query_result: 当前查询结果
        query_history: 历史查询结果
    
    Returns:
        {
            "completeness_score": float,  # 0.0-1.0
            "question_coverage": float,   # 问题覆盖度
            "data_completeness": float,   # 数据完整性
            "insight_depth": float,       # 洞察深度
            "anomaly_handling": float,    # 异常处理
            "missing_aspects": List[str]  # 缺失的分析维度
        }
    """
    pass
```

#### 7.2 重规划路由逻辑

```python
# tableau_assistant/src/agents/workflows/vizql_workflow.py

def should_replan(state: VizQLState) -> str:
    """
    决定是否重规划
    
    重规划类型：
    1. 补充缺失信息 - 原问题部分未回答，生成补充问题
    2. 深入分析异常 - 发现异常需要深入分析
    3. 洞察不足 - 分析过于表面，需要更深入
    
    路由策略：
    - 所有重规划问题都路由到 Planning 节点
    - 因为 Understanding 已经完成了原问题的理解
    - 新问题基于已有的元数据和字段映射
    """
    replan_decision = state.get("replan_decision", {})
    replan_count = state.get("replan_count", 0)
    max_rounds = state.get("max_replan_rounds", 3)
    completeness_score = state.get("completeness_score", 0.0)
    
    # 智能终止策略
    # 1. 完成度足够高，无需继续重规划
    if completeness_score >= 0.9:
        _record_termination(state, "completeness_sufficient", completeness_score)
        return END
    
    # 2. 达到硬限制
    if replan_count >= max_rounds:
        _record_termination(state, "max_rounds_reached", completeness_score)
        return END
    
    # 3. Replanner 决定需要重规划且完成度不足
    if replan_decision.get("should_replan") and completeness_score < 0.7:
        return "planning"  # 跳过 Understanding，直接到 Planning
    
    # 4. 完成度在 0.7-0.9 之间，由 Replanner 决定
    if replan_decision.get("should_replan"):
        return "planning"  # 跳过 Understanding，直接到 Planning
    
    return END


def _record_termination(state: VizQLState, reason: str, score: float):
    """记录终止原因到 replan_history"""
    history = state.get("replan_history", [])
    history.append({
        "termination_reason": reason,
        "completeness_score": score,
        "replan_count": state.get("replan_count", 0),
        "timestamp": datetime.now().isoformat()
    })
    state["replan_history"] = history
```

#### 5.2 Replanner Agent 实现

```python
# tableau_assistant/src/agents/nodes/replanner.py

class ReplannerAgent(BaseVizQLAgent):
    """
    重规划 Agent
    
    职责：
    1. 评估当前分析完成度
    2. 决定是否需要重规划
    3. 生成补充问题（基于已有洞察，不重复原问题）
    """
    
    async def execute(
        self,
        state: VizQLState,
        runtime: Runtime[VizQLContext],
        **kwargs
    ) -> Dict[str, Any]:
        """执行重规划决策"""
        
        # 1. 获取已有洞察和原问题
        insights = state.get("accumulated_insights", [])
        original_question = state.get("original_question", "")
        query_result = state.get("query_result", {})
        query_history = state.get("query_history", [])
        
        # 2. 评估完成度（基于当前结果和历史结果）
        completeness = await self._evaluate_completeness(
            original_question, insights, query_result, query_history
        )
        
        # 3. 决定是否重规划
        should_replan, replan_reason, new_question = await self._decide_replan(
            original_question, insights, completeness
        )
        
        # 4. 更新状态
        return {
            "completeness_score": completeness.score,
            "replan_decision": {
                "should_replan": should_replan,
                "reason": replan_reason,
                "new_question": new_question,
                "replan_type": completeness.missing_aspects[0] if completeness.missing_aspects else None
            },
            "replan_count": state.get("replan_count", 0) + (1 if should_replan else 0),
            # 如果重规划，将新问题设置为当前问题（供 Planning 使用）
            "current_question": new_question if should_replan else state.get("current_question")
        }
    
    async def _evaluate_completeness(
        self,
        original_question: str,
        insights: List[Insight],
        results: List[Dict]
    ) -> CompletenessEvaluation:
        """
        评估分析完成度
        
        评估维度：
        - 问题覆盖度：是否回答了用户问题的所有方面
        - 数据完整性：是否获取了所需的所有数据
        - 洞察深度：分析是否足够深入
        - 异常处理：是否解释了发现的异常
        """
        prompt = f"""
        评估以下分析的完成度：
        
        原始问题：{original_question}
        
        已有洞察：
        {self._format_insights(insights)}
        
        查询结果摘要：
        {self._format_results_summary(results)}
        
        请评估：
        1. 问题覆盖度 (0-1)：是否回答了问题的所有方面？
        2. 数据完整性 (0-1)：是否获取了足够的数据？
        3. 洞察深度 (0-1)：分析是否足够深入？
        4. 异常处理 (0-1)：是否解释了发现的异常？
        
        返回 JSON：
        {{
            "score": 0.0-1.0,  // 综合完成度
            "question_coverage": 0.0-1.0,
            "data_completeness": 0.0-1.0,
            "insight_depth": 0.0-1.0,
            "anomaly_handling": 0.0-1.0,
            "missing_aspects": ["缺失的方面列表"]
        }}
        """
        
        response = await self.call_llm(prompt)
        return CompletenessEvaluation(**json.loads(response))
    
    async def _decide_replan(
        self,
        original_question: str,
        insights: List[Insight],
        completeness: CompletenessEvaluation
    ) -> Tuple[bool, str, Optional[str]]:
        """
        决定是否重规划并生成新问题
        
        关键：新问题基于已有洞察，不重复原问题
        """
        if completeness.score >= 0.9:
            return False, "分析已足够完整", None
        
        if not completeness.missing_aspects:
            return False, "没有明确的缺失方面", None
        
        # 生成补充问题
        prompt = f"""
        基于以下信息，生成一个补充问题：
        
        原始问题：{original_question}
        
        已有洞察：
        {self._format_insights(insights)}
        
        缺失方面：{completeness.missing_aspects}
        
        要求：
        1. 补充问题应该针对缺失的方面
        2. 不要重复原问题
        3. 利用已有洞察作为上下文
        4. 问题应该具体、可执行
        
        返回 JSON：
        {{
            "should_replan": true/false,
            "reason": "重规划原因",
            "new_question": "补充问题"
        }}
        """
        
        response = await self.call_llm(prompt)
        result = json.loads(response)
        
        return result["should_replan"], result["reason"], result.get("new_question")
```

#### 5.3 完成度评估模型

```python
# tableau_assistant/src/models/replan_decision.py

class CompletenessEvaluation(BaseModel):
    """完成度评估结果"""
    score: float = Field(ge=0.0, le=1.0, description="综合完成度分数")
    question_coverage: float = Field(ge=0.0, le=1.0, description="问题覆盖度")
    data_completeness: float = Field(ge=0.0, le=1.0, description="数据完整性")
    insight_depth: float = Field(ge=0.0, le=1.0, description="洞察深度")
    anomaly_handling: float = Field(ge=0.0, le=1.0, description="异常处理")
    missing_aspects: List[str] = Field(default_factory=list, description="缺失的方面")


class ReplanDecision(BaseModel):
    """重规划决策"""
    should_replan: bool = Field(description="是否需要重规划")
    reason: str = Field(description="决策原因")
    new_question: Optional[str] = Field(default=None, description="补充问题")
    replan_type: Optional[str] = Field(default=None, description="重规划类型")
```

### 8. Insight Agent 渐进式分析

```python
# tableau_assistant/src/agents/nodes/insight.py

class ProgressiveInsightAgent(BaseVizQLAgent):
    """
    渐进式洞察 Agent
    
    实现"AI 宝宝吃饭"理念：
    - 智能分块
    - 优先级处理
    - 累积洞察
    - 早停机制
    """
    
    async def execute(
        self,
        state: VizQLState,
        runtime: Runtime[VizQLContext],
        **kwargs
    ) -> Dict[str, Any]:
        """执行渐进式分析"""
        
        # 获取查询结果（单查询结构）
        query_result = state.get("query_result", {})
        
        # 判断是否需要渐进式分析
        total_rows = len(query_result.get("data", []))
        
        if total_rows <= 100:
            # 小数据：直接分析
            return await self._direct_analysis(state, runtime)
        else:
            # 大数据：渐进式分析
            return await self._progressive_analysis(state, runtime)
    
    async def _progressive_analysis(
        self,
        state: VizQLState,
        runtime: Runtime[VizQLContext]
    ) -> Dict[str, Any]:
        """渐进式分析"""
        
        # 1. 智能分块
        chunks = self._intelligent_chunking(state)
        
        # 2. 渐进式分析循环
        accumulated_insights = []
        
        for chunk, priority, chunk_type in chunks:
            # 2.1 AI 分析当前块
            new_insights, next_decision = await self._analyze_chunk(
                chunk, chunk_type, accumulated_insights, state
            )
            
            # 2.2 累积洞察
            accumulated_insights = self._accumulate_insights(
                accumulated_insights, new_insights
            )
            
            # 2.3 检查早停
            if next_decision.should_stop:
                break
        
        # 3. 合成最终洞察
        return self._synthesize_insights(accumulated_insights, state)
    
    def _intelligent_chunking(
        self,
        state: VizQLState
    ) -> List[Tuple[DataFrame, Priority, str]]:
        """
        智能优先级分块
        
        优先级：
        - URGENT: 异常值
        - HIGH: Top 100 行
        - MEDIUM: 101-500 行
        - LOW: 501-1000 行
        - DEFERRED: 1000+ 行（保留摘要）
        """
        chunks = []
        data = self._get_combined_data(state)
        total_rows = len(data)
        
        # 1. 异常值检测
        anomalies = self._detect_anomalies(data)
        if len(anomalies) > 0:
            chunks.append((anomalies, Priority.URGENT, "anomalies"))
        
        # 2. Top 数据
        if total_rows > 0:
            chunks.append((data.head(100), Priority.HIGH, "top_data"))
        
        # 3. 中间数据
        if total_rows > 100:
            chunks.append((data.iloc[100:min(500, total_rows)], Priority.MEDIUM, "mid_data"))
        
        # 4. 低优先级数据
        if total_rows > 500:
            chunks.append((data.iloc[500:min(1000, total_rows)], Priority.LOW, "low_data"))
        
        # 5. 尾部数据（保留摘要）
        if total_rows > 1000:
            tail_summary = self._create_tail_summary(data.iloc[1000:])
            chunks.append((tail_summary, Priority.DEFERRED, "tail_data"))
        
        return chunks
```

## 数据模型

### Intent 模型层次结构

```
Intent 模型（intent.py）
├── DimensionIntent（维度意图）
├── MeasureIntent（度量意图）
├── DateFieldIntent（日期字段意图）
├── TableCalcIntent（表计算意图）★ 本次增强
├── DateFilterIntent（日期过滤意图）
├── FilterIntent（非日期过滤意图）
└── TopNIntent（TopN 意图）
```

### VizQL 模型层次结构（基于 OpenAPI 规范）

```
VizQLField（vizql_types.py）- 对应 OpenAPI Field oneOf
├── DimensionField（维度字段）
│   └── fieldCaption, fieldAlias, sortDirection, sortPriority
├── MeasureField（度量字段）
│   └── fieldCaption, function (required), fieldAlias, sortDirection, sortPriority
├── CalculatedField（计算字段）
│   └── fieldCaption, calculation (required), fieldAlias, sortDirection, sortPriority
├── BinField（分箱字段）
│   └── fieldCaption, binSize (required), fieldAlias, sortDirection, sortPriority
└── TableCalcField（表计算字段）★ 本次增强
    └── fieldCaption, function, calculation, tableCalculation (required)
        └── tableCalculation: TableCalcSpecification
            ├── CustomTableCalcSpecification
            ├── NestedTableCalcSpecification
            ├── DifferenceTableCalcSpecification (DIFFERENCE_FROM, PERCENT_DIFFERENCE_FROM, PERCENT_FROM)
            ├── PercentOfTotalTableCalcSpecification
            ├── RankTableCalcSpecification
            ├── PercentileTableCalcSpecification
            ├── RunningTotalTableCalcSpecification
            └── MovingTableCalcSpecification

Filter（vizql_types.py）- 对应 OpenAPI Filter discriminator
├── QuantitativeDateFilter (filterType: QUANTITATIVE_DATE)
├── QuantitativeNumericalFilter (filterType: QUANTITATIVE_NUMERICAL)
├── SetFilter (filterType: SET)
├── MatchFilter (filterType: MATCH)
├── RelativeDateFilter (filterType: DATE)
└── TopNFilter (filterType: TOP)
```

### Function 枚举（基于 OpenAPI 规范）

```python
# tableau_assistant/src/models/vizql_types.py

class Function(str, Enum):
    """Tableau aggregation and date functions."""
    # 聚合函数
    SUM = "SUM"
    AVG = "AVG"
    MEDIAN = "MEDIAN"
    COUNT = "COUNT"
    COUNTD = "COUNTD"
    MIN = "MIN"
    MAX = "MAX"
    STDEV = "STDEV"
    VAR = "VAR"
    COLLECT = "COLLECT"
    
    # 日期函数
    YEAR = "YEAR"
    QUARTER = "QUARTER"
    MONTH = "MONTH"
    WEEK = "WEEK"
    DAY = "DAY"
    
    # 截断日期函数
    TRUNC_YEAR = "TRUNC_YEAR"
    TRUNC_QUARTER = "TRUNC_QUARTER"
    TRUNC_MONTH = "TRUNC_MONTH"
    TRUNC_WEEK = "TRUNC_WEEK"
    TRUNC_DAY = "TRUNC_DAY"
    
    # 特殊值
    AGG = "AGG"
    NONE = "NONE"
    UNSPECIFIED = "UNSPECIFIED"
```

### TableCalcSpecification 子类型（基于 OpenAPI 规范）

```python
# tableau_assistant/src/models/vizql_types.py

class TableCalcSpecificationBase(BaseModel):
    """表计算规范基类"""
    model_config = ConfigDict(extra="forbid")
    
    tableCalcType: TableCalcType = Field(
        description="Table calculation type"
    )
    
    dimensions: List[TableCalcFieldReference] = Field(
        min_length=1,
        description="""Fields that define calculation scope.

Usage:
- Include fields where calculation operates ACROSS their values
- Exclude fields where calculation RESTARTS for each value
- Must be subset of query's dimension fields"""
    )


class DifferenceTableCalcSpecification(TableCalcSpecificationBase):
    """差异计算规范 (DIFFERENCE_FROM, PERCENT_DIFFERENCE_FROM, PERCENT_FROM)"""
    
    levelAddress: Optional[TableCalcFieldReference] = Field(
        default=None,
        description="Level address for calculation"
    )
    
    relativeTo: Literal["PREVIOUS", "NEXT", "FIRST", "LAST"] = Field(
        default="PREVIOUS",
        description="""Comparison target.

Values:
- PREVIOUS: Compare to previous value (default)
- NEXT: Compare to next value
- FIRST: Compare to first value
- LAST: Compare to last value"""
    )
    
    customSort: Optional[TableCalcCustomSort] = Field(
        default=None,
        description="Custom sort specification"
    )


class RankTableCalcSpecification(TableCalcSpecificationBase):
    """排名计算规范"""
    
    rankType: Literal["COMPETITION", "MODIFIED COMPETITION", "DENSE", "UNIQUE"] = Field(
        default="COMPETITION",
        description="""Rank type.

Values:
- COMPETITION: Standard competition ranking (1, 2, 2, 4)
- MODIFIED COMPETITION: Modified competition (1, 2, 2, 3)
- DENSE: Dense ranking (1, 2, 2, 3)
- UNIQUE: Unique ranking (1, 2, 3, 4)"""
    )
    
    direction: Optional[SortDirection] = Field(
        default=None,
        description="Sort direction for ranking"
    )


class RunningTotalTableCalcSpecification(TableCalcSpecificationBase):
    """累计计算规范"""
    
    aggregation: Literal["SUM", "AVG", "MIN", "MAX"] = Field(
        default="SUM",
        description="Aggregation type for running total"
    )
    
    restartEvery: Optional[TableCalcFieldReference] = Field(
        default=None,
        description="Field to restart calculation at"
    )
    
    customSort: Optional[TableCalcCustomSort] = Field(
        default=None,
        description="Custom sort specification"
    )
    
    secondaryTableCalculation: Optional["TableCalcSpecification"] = Field(
        default=None,
        description="Secondary table calculation"
    )


class MovingTableCalcSpecification(TableCalcSpecificationBase):
    """移动计算规范"""
    
    aggregation: Literal["SUM", "AVG", "MIN", "MAX"] = Field(
        default="SUM",
        description="Aggregation type for moving calculation"
    )
    
    previous: int = Field(
        default=-2,
        description="Number of previous values to include"
    )
    
    next: int = Field(
        default=0,
        description="Number of next values to include"
    )
    
    includeCurrent: bool = Field(
        default=True,
        description="Whether to include current value"
    )
    
    fillInNull: bool = Field(
        default=False,
        description="Whether to fill in null values"
    )
    
    customSort: Optional[TableCalcCustomSort] = Field(
        default=None,
        description="Custom sort specification"
    )
    
    secondaryTableCalculation: Optional["TableCalcSpecification"] = Field(
        default=None,
        description="Secondary table calculation"
    )


class PercentOfTotalTableCalcSpecification(TableCalcSpecificationBase):
    """百分比计算规范"""
    
    levelAddress: Optional[TableCalcFieldReference] = Field(
        default=None,
        description="Level address for calculation"
    )
    
    customSort: Optional[TableCalcCustomSort] = Field(
        default=None,
        description="Custom sort specification"
    )


class PercentileTableCalcSpecification(TableCalcSpecificationBase):
    """百分位计算规范"""
    
    direction: Optional[SortDirection] = Field(
        default=None,
        description="Sort direction for percentile"
    )
```

### TableCalcCustomSort 模型

```python
class TableCalcCustomSort(BaseModel):
    """表计算自定义排序"""
    model_config = ConfigDict(extra="forbid")
    
    fieldCaption: str = Field(
        description="Field to sort by"
    )
    
    function: Function = Field(
        description="Function to apply to field"
    )
    
    direction: SortDirection = Field(
        description="Sort direction"
    )


class SortDirection(str, Enum):
    """排序方向"""
    ASC = "ASC"
    DESC = "DESC"
```

### Filter 模型（基于 OpenAPI 规范）

```python
# tableau_assistant/src/models/vizql_types.py

class FilterType(str, Enum):
    """Filter types supported by VizQL Data Service."""
    QUANTITATIVE_DATE = "QUANTITATIVE_DATE"
    QUANTITATIVE_NUMERICAL = "QUANTITATIVE_NUMERICAL"
    SET = "SET"
    MATCH = "MATCH"
    DATE = "DATE"  # RelativeDateFilter
    TOP = "TOP"    # TopNFilter


class FilterBase(BaseModel):
    """Filter 基类"""
    model_config = ConfigDict(extra="forbid")
    
    field: FilterField = Field(
        description="Field to filter on"
    )
    
    filterType: FilterType = Field(
        description="Type of filter"
    )
    
    context: bool = Field(
        default=False,
        description="Make this a context filter"
    )


class SetFilter(FilterBase):
    """集合过滤器"""
    
    values: List[str] = Field(
        description="Values to include/exclude"
    )
    
    exclude: bool = Field(
        default=False,
        description="Whether to exclude the values"
    )


class MatchFilter(FilterBase):
    """匹配过滤器"""
    
    contains: Optional[str] = Field(
        default=None,
        description="Match when field contains this value"
    )
    
    startsWith: Optional[str] = Field(
        default=None,
        description="Match when field starts with this value"
    )
    
    endsWith: Optional[str] = Field(
        default=None,
        description="Match when field ends with this value"
    )
    
    exclude: bool = Field(
        default=False,
        description="Invert the matching logic"
    )


class QuantitativeNumericalFilter(FilterBase):
    """数值范围过滤器"""
    
    quantitativeFilterType: Literal["RANGE", "MIN", "MAX", "ONLY_NULL", "ONLY_NON_NULL"] = Field(
        description="Type of quantitative filter"
    )
    
    min: Optional[float] = Field(
        default=None,
        description="Minimum value"
    )
    
    max: Optional[float] = Field(
        default=None,
        description="Maximum value"
    )
    
    includeNulls: Optional[bool] = Field(
        default=None,
        description="Whether to include null values"
    )


class QuantitativeDateFilter(FilterBase):
    """日期范围过滤器"""
    
    quantitativeFilterType: Literal["RANGE", "MIN", "MAX", "ONLY_NULL", "ONLY_NON_NULL"] = Field(
        description="Type of quantitative filter"
    )
    
    minDate: Optional[str] = Field(
        default=None,
        description="Minimum date (RFC 3339 format)"
    )
    
    maxDate: Optional[str] = Field(
        default=None,
        description="Maximum date (RFC 3339 format)"
    )
    
    includeNulls: Optional[bool] = Field(
        default=None,
        description="Whether to include null values"
    )


class RelativeDateFilter(FilterBase):
    """相对日期过滤器"""
    
    # 相对日期字段根据实际 API 补充
    pass


class TopNFilter(FilterBase):
    """TopN 过滤器"""
    
    # TopN 字段根据实际 API 补充
    pass
```

### QuestionUnderstanding 模型（问题理解）

```python
# tableau_assistant/src/models/question.py

class QuestionUnderstanding(BaseModel):
    """问题理解结果"""
    model_config = ConfigDict(extra="forbid")
    
    original_question: str = Field(
        description="""Original user question.

Usage:
- Store the exact user input
- Used for reference in later stages"""
    )
    
    question_type: QuestionType = Field(
        description="""Type of analysis question.

Usage:
- Determines query strategy
- Affects insight generation

Values: QuestionType enum
- RANKING: Who/what is first/last
- TREND: How does X change over time
- COMPARISON: Compare A vs B
- DISTRIBUTION: How is X distributed
- AGGREGATION: What is the total/average"""
    )
    
    dimensions: List[DimensionIntent] = Field(
        default_factory=list,
        description="""Dimension fields identified from question.

Usage:
- Fields for grouping data
- Mapped to VizQL dimension fields

Values: List of DimensionIntent
- field_name: Semantic field name from question
- mapped_field: Actual field caption from metadata
- function: Optional date function (YEAR, MONTH, etc.)"""
    )
    
    measures: List[MeasureIntent] = Field(
        default_factory=list,
        description="""Measure fields identified from question.

Usage:
- Fields for aggregation
- Mapped to VizQL measure fields

Values: List of MeasureIntent
- field_name: Semantic field name from question
- mapped_field: Actual field caption from metadata
- aggregation: SUM, AVG, COUNT, etc."""
    )
    
    filters: List[FilterIntent] = Field(
        default_factory=list,
        description="""Filter conditions identified from question.

Usage:
- Conditions to filter data
- Mapped to VizQL filter fields

Values: List of FilterIntent
- field_name: Field to filter on
- operator: EQ, NE, GT, LT, IN, etc.
- values: Filter values"""
    )
    
    date_filters: List[DateFilterIntent] = Field(
        default_factory=list,
        description="""Date filter conditions.

Usage:
- Date-specific filter conditions
- Supports relative dates (last 7 days, this month)

Values: List of DateFilterIntent
- field_name: Date field to filter on
- date_type: RELATIVE or ABSOLUTE
- relative_period: LAST_N_DAYS, THIS_MONTH, etc.
- start_date: Absolute start date
- end_date: Absolute end date"""
    )
    
    table_calc_type: Optional[TableCalcType] = Field(
        default=None,
        description="""Table calculation type identified from keywords.

Usage:
- Set based on keyword detection in user question
- null if no table calculation needed

Values: TableCalcType enum or null
- RUNNING_TOTAL: running total, cumulative, accumulated
- RANK: rank, ranking, top N, position
- MOVING_CALCULATION: moving average, rolling average
- PERCENT_OF_TOTAL: percent of total, percentage, share
- DIFFERENCE_FROM: difference from, change from, year over year
- PERCENT_DIFFERENCE_FROM: percent difference, percentage change
- PERCENTILE: percentile, quartile"""
    )
    
    table_calc_dimensions: Optional[List[TableCalcFieldReference]] = Field(
        default=None,
        description="""Fields that define calculation scope.

Usage:
- Include fields where calculation operates ACROSS their values
- Exclude fields where calculation RESTARTS for each value
- Must be subset of query's dimension fields
- null if no table calculation needed

Values: List of TableCalcFieldReference or null
- fieldCaption: Field name from query dimensions
- function: Optional, for date fields (YEAR, MONTH, etc.)

Examples:

1. RUNNING_TOTAL - "Running total of sales by region over time"
   Query dimensions: [Region, Order Date]
   table_calc_dimensions: [TableCalcFieldReference(fieldCaption="Order Date")]
   Why: Calculate across dates, restart for each region

2. RANK - "Rank products by sales within each category"
   Query dimensions: [Category, Product]
   table_calc_dimensions: [TableCalcFieldReference(fieldCaption="Product")]
   Why: Rank across products, restart for each category

3. PERCENT_OF_TOTAL - "Each region's percent of total sales"
   Query dimensions: [Region]
   table_calc_dimensions: [TableCalcFieldReference(fieldCaption="Region")]
   Why: Calculate percent across all regions

4. DIFFERENCE_FROM - "Month over month sales change"
   Query dimensions: [Order Date(MONTH)]
   table_calc_dimensions: [TableCalcFieldReference(fieldCaption="Order Date", function="MONTH")]
   Why: Compare across months"""
    )
    
    topn: Optional[TopNIntent] = Field(
        default=None,
        description="""TopN specification if applicable.

Usage:
- Set when question asks for top/bottom N
- null if no TopN needed

Values: TopNIntent or null
- n: Number of items
- direction: TOP or BOTTOM
- by_field: Field to rank by"""
    )
```

### QueryPlan 模型（任务规划 - 单查询结构）

```python
# tableau_assistant/src/models/query_plan.py

class QueryPlan(BaseModel):
    """
    查询计划（单查询结构）
    
    设计决策：
    - 每个 QueryPlan 只包含一个查询
    - 如果需要补充查询，由 Replanner 生成新的 QueryPlan
    - 这样更符合"渐进式分析"理念，降低复杂度
    """
    model_config = ConfigDict(extra="forbid")
    
    plan_id: str = Field(
        description="""Unique identifier for this plan.

Usage:
- Track plan execution
- Reference in logs and debugging
- Used in replan_history"""
    )
    
    original_question: str = Field(
        description="""Original user question.

Usage:
- Reference for insight generation
- Used in Replanner evaluation"""
    )
    
    description: str = Field(
        description="""Human-readable description of what this query does.

Usage:
- Logging and debugging
- User-facing progress updates"""
    )
    
    dimensions: List[DimensionIntent] = Field(
        default_factory=list,
        description="""Dimension fields for this query.

Usage:
- Fields for grouping data
- Converted to VizQL dimension fields

Values: List of DimensionIntent
- field_name: Semantic field name from question
- mapped_field: Actual field caption from metadata
- function: Optional date function (YEAR, MONTH, etc.)"""
    )
    
    measures: List[MeasureIntent] = Field(
        default_factory=list,
        description="""Measure fields for this query.

Usage:
- Fields for aggregation
- Converted to VizQL measure fields

Values: List of MeasureIntent
- field_name: Semantic field name from question
- mapped_field: Actual field caption from metadata
- aggregation: SUM, AVG, COUNT, etc."""
    )
    
    filters: List[FilterIntent] = Field(
        default_factory=list,
        description="""Filter conditions for this query.

Usage:
- Conditions to filter data
- Converted to VizQL filter fields

Values: List of FilterIntent
- field_name: Field to filter on
- operator: EQ, NE, GT, LT, IN, etc.
- values: Filter values"""
    )
    
    date_filters: List[DateFilterIntent] = Field(
        default_factory=list,
        description="""Date filter conditions.

Usage:
- Date-specific filter conditions
- Supports relative dates (last 7 days, this month)

Values: List of DateFilterIntent
- field_name: Date field to filter on
- date_type: RELATIVE or ABSOLUTE
- relative_period: LAST_N_DAYS, THIS_MONTH, etc."""
    )
    
    table_calc: Optional[TableCalcIntent] = Field(
        default=None,
        description="""Table calculation specification.

Usage:
- Set if this query requires table calculation
- Converted to TableCalcField in VizQL query
- null if no table calculation needed

Values: TableCalcIntent or null"""
    )
    
    topn: Optional[TopNIntent] = Field(
        default=None,
        description="""TopN specification if applicable.

Usage:
- Set when question asks for top/bottom N
- null if no TopN needed

Values: TopNIntent or null
- n: Number of items
- direction: TOP or BOTTOM
- by_field: Field to rank by"""
    )
    
    is_replan: bool = Field(
        default=False,
        description="""Whether this plan is from a replan.

Usage:
- True if generated by Replanner
- False if from initial Planning

Values: true or false"""
    )
    
    replan_reason: Optional[str] = Field(
        default=None,
        description="""Reason for replan if is_replan=True.

Usage:
- Explains why this replan was needed
- null if not a replan

Values: String or null"""
    )
```

### TableCalcIntent 模型（表计算意图）

```python
# tableau_assistant/src/models/intent.py

class TableCalcIntent(BaseModel):
    """表计算意图"""
    model_config = ConfigDict(extra="forbid")
    
    calc_type: TableCalcType = Field(
        description="""Type of table calculation.

Usage:
- Determines which TableCalcSpecification to use

Values: TableCalcType enum
- RUNNING_TOTAL, RANK, MOVING_CALCULATION, etc."""
    )
    
    base_measure: MeasureIntent = Field(
        description="""The measure to apply table calculation on.

Usage:
- The field being calculated
- Must be a valid measure field"""
    )
    
    dimensions: List[TableCalcFieldReference] = Field(
        min_length=1,
        description="""Fields that define calculation scope.

Usage:
- Include fields where calculation operates ACROSS their values
- Exclude fields where calculation RESTARTS for each value
- Must be subset of query's dimension fields

Values: List of TableCalcFieldReference
- fieldCaption: Field name from query dimensions
- function: Optional, for date fields (YEAR, MONTH, etc.)

Examples:

1. RUNNING_TOTAL - "Running total of sales by region over time"
   Query dimensions: [Region, Order Date]
   dimensions: [TableCalcFieldReference(fieldCaption="Order Date")]
   Why: Calculate across dates, restart for each region

2. RANK - "Rank products by sales within each category"
   Query dimensions: [Category, Product]
   dimensions: [TableCalcFieldReference(fieldCaption="Product")]
   Why: Rank across products, restart for each category"""
    )
    
    # 特定类型的参数
    window_size: Optional[int] = Field(
        default=None,
        description="""Window size for MOVING_CALCULATION.

Usage:
- Only for MOVING_CALCULATION type
- Number of periods to include

Values: Positive integer or null"""
    )
    
    rank_order: Optional[Literal["ASC", "DESC"]] = Field(
        default="DESC",
        description="""Rank order for RANK type.

Usage:
- Only for RANK type
- DESC: Highest value = rank 1
- ASC: Lowest value = rank 1

Values: "ASC" or "DESC" """
    )
    
    compare_to: Optional[Literal["PREVIOUS", "FIRST", "LAST"]] = Field(
        default="PREVIOUS",
        description="""Comparison target for DIFFERENCE_FROM types.

Usage:
- Only for DIFFERENCE_FROM, PERCENT_FROM, PERCENT_DIFFERENCE_FROM
- PREVIOUS: Compare to previous value
- FIRST: Compare to first value
- LAST: Compare to last value

Values: "PREVIOUS", "FIRST", or "LAST" """
    )
```

### TableCalcFieldReference 模型

```python
# tableau_assistant/src/models/vizql_types.py

class TableCalcFieldReference(BaseModel):
    """表计算字段引用"""
    model_config = ConfigDict(extra="forbid")
    
    fieldCaption: str = Field(
        description="""Field name from query dimensions.

Usage:
- Must match a dimension field in the query
- Case-sensitive"""
    )
    
    function: Optional[DateFunction] = Field(
        default=None,
        description="""Date function for date fields.

Usage:
- Only for date dimension fields
- Specifies the date granularity

Values: DateFunction enum or null
- YEAR, QUARTER, MONTH, WEEK, DAY, etc."""
    )
```

### 中间件状态扩展

```python
# tableau_assistant/src/models/state.py

class VizQLState(TypedDict):
    """VizQL 工作流状态"""
    
    # 基础字段
    original_question: str
    current_question: str  # 可能被 Boost 或 Replan 修改
    
    # Understanding 输出
    question_understanding: NotRequired[QuestionUnderstanding]
    
    # Planning 输出
    query_plan: NotRequired[QueryPlan]
    
    # Execute 输出（单查询结构）
    query_result: NotRequired[QueryResult]  # 单个查询结果
    
    # Insight 输出
    accumulated_insights: NotRequired[List[Insight]]
    analysis_progress: NotRequired[AnalysisProgress]
    
    # Replanner 输出
    completeness_score: NotRequired[float]
    replan_decision: NotRequired[ReplanDecision]
    replan_count: NotRequired[int]
    replan_history: NotRequired[List[Dict]]
    query_history: NotRequired[List[QueryResult]]  # 历史查询结果（用于重规划）
    
    # 中间件状态
    todos: NotRequired[List[TodoItem]]
    files: NotRequired[Dict[str, FileData]]
    
    # 配置
    boost_question: NotRequired[bool]
    max_replan_rounds: NotRequired[int]


class QueryResult(TypedDict):
    """单个查询结果"""
    plan_id: str  # 对应的 QueryPlan ID
    data: List[Dict[str, Any]]  # 查询返回的数据
    row_count: int
    columns: List[str]
    execution_time_ms: int
    is_replan: bool  # 是否来自重规划


class AnalysisProgress(TypedDict):
    """分析进度"""
    total_chunks: int
    analyzed_chunks: int
    current_chunk_type: str
    early_stopped: bool
    stop_reason: Optional[str]
```

## 正确性属性

*属性是系统在所有有效执行中应该保持为真的特征或行为。*

### 属性 1: DeepAgent 中间件完整性
*对于任何*通过 `create_tableau_deep_agent()` 创建的 Agent，应该包含所有 6 个核心中间件
**验证需求: 1.2**

### 属性 2: TodoList 状态一致性
*对于任何*任务状态更新，状态中的 `todos` 数组应该反映最新的任务列表
**验证需求: 2.4**

### 属性 3: Summarization 触发正确性
*对于任何*超过配置 token 阈值的对话，SummarizationMiddleware 应该触发总结
**验证需求: 3.1**

### 属性 4: Summarization 消息保留正确性
*对于任何*总结操作，应该保留配置数量的最近消息
**验证需求: 3.2, 3.5**

### 属性 5: Filesystem 大结果处理正确性
*对于任何*超过 token 限制的工具输出，FilesystemMiddleware 应该将结果写入文件系统
**验证需求: 4.1**

### 属性 6: Filesystem 分页读取正确性
*对于任何*带有 offset 和 limit 参数的 read_file 调用，应该返回正确范围的内容
**验证需求: 4.3**

### 属性 7: PatchToolCalls 修复正确性
*对于任何*参数类型错误的工具调用，PatchToolCallsMiddleware 应该尝试修复并使用修复后的参数
**验证需求: 5.1, 5.4**

### 属性 8: AnthropicPromptCaching 模型兼容性
*对于任何*非 Claude 模型，AnthropicPromptCachingMiddleware 应该静默忽略
**验证需求: 6.2, 6.3**

### 属性 9: HumanInTheLoop 中断正确性
*对于任何*配置了 interrupt_on 的工具调用，系统应该在调用前暂停
**验证需求: 7.1, 7.2**

### 属性 10: SubAgent task 工具可用性
*对于任何*配置了 subagents 的 DeepAgent，应该提供 task 工具
**验证需求: 8.1**

### 属性 11: 表计算关键词识别正确性
*对于任何*包含表计算关键词的用户问题，Understanding Agent 应该正确识别表计算类型
**验证需求: 9.1, 9.2, 9.3, 9.4**

### 属性 12: Boost Agent 元数据默认使用
*对于任何*Boost Agent 执行，use_metadata 应该默认为 True
**验证需求: 10.1**

### 属性 13: 渐进式分析触发正确性
*对于任何*超过 100 行的查询结果，Insight Agent 应该使用渐进式分析
**验证需求: 11.1**

### 属性 14: 渐进式分析优先级正确性
*对于任何*渐进式分析，数据块应该按 URGENT → HIGH → MEDIUM → LOW → DEFERRED 顺序处理
**验证需求: 11.2**

### 属性 15: 渐进式分析早停正确性
*对于任何*洞察质量足够的情况，系统应该支持早停
**验证需求: 11.4**

### 属性 16: 工具封装正确性
*对于任何*业务工具，应该使用 @tool 装饰器或 StructuredTool.from_function() 封装
**验证需求: 13.1**

### 属性 17: 重规划路由正确性
*对于任何*should_replan=True 且 replan_count < max_rounds 的情况，系统应该从 Replanner 路由回 Planning 节点（跳过 Understanding）
**验证需求: 12.1, 12.2**

### 属性 18: 智能终止策略正确性
*对于任何*completeness_score >= 0.9 的情况，系统应该终止重规划循环
**验证需求: 12.3**

### 属性 19: 重规划问题生成正确性
*对于任何*重规划决策，生成的新问题应该基于已有洞察，不重复原问题
**验证需求: 12.7**

### 属性 20: 重规划历史记录正确性
*对于任何*重规划循环终止，系统应该记录终止原因和完成度到 replan_history
**验证需求: 12.6**

## 错误处理

### 中间件错误处理

| 中间件 | 错误类型 | 处理策略 |
|--------|---------|---------|
| TodoListMiddleware | 状态更新失败 | 记录日志，继续执行 |
| FilesystemMiddleware | 文件写入失败 | 返回原始结果，记录警告 |
| SummarizationMiddleware | 总结失败 | 保留原始消息，记录错误 |
| PatchToolCallsMiddleware | 修复失败 | 返回原始错误信息 |
| AnthropicPromptCachingMiddleware | 缓存失败 | 静默忽略，继续执行 |
| HumanInTheLoopMiddleware | 超时 | 返回超时错误 |
| SubAgentMiddleware | 子代理失败 | 返回子代理错误信息 |

## 测试策略

### 单元测试

1. **中间件配置测试**
   - 验证 create_deep_agent 返回的 Agent 包含所有中间件
   - 验证中间件参数配置正确

2. **TodoList 测试**
   - 验证任务状态转换
   - 验证 todos 数组更新

3. **Filesystem 测试**
   - 验证大结果写入文件
   - 验证分页读取

4. **Summarization 测试**
   - 验证触发条件
   - 验证消息保留数量

5. **表计算识别测试**
   - 验证关键词识别
   - 验证 table_calc_type 设置

6. **渐进式分析测试**
   - 验证分块逻辑
   - 验证优先级顺序
   - 验证早停机制

### 属性测试

使用 Hypothesis 库进行属性测试，每个属性至少 200 次迭代。

```python
from hypothesis import given, settings, strategies as st

@given(st.lists(st.text(), min_size=1))
@settings(max_examples=200)
def test_property_table_calc_keywords(questions):
    """Feature: agent-middleware-integration, Property 11: 表计算关键词识别"""
    for question in questions:
        if any(kw in question.lower() for kw in ["累计", "running total", "累积"]):
            result = understanding_agent.identify_table_calc(question)
            assert result.table_calc_type == TableCalcType.RUNNING_TOTAL
```

## 实施路径

### 阶段 1: DeepAgent 工厂重构 (2 天)

1. 更新 `deep_agent_factory.py` 使用正确的 `create_deep_agent()` 调用
2. 配置所有中间件参数
3. 编写中间件配置测试

### 阶段 2: 工具层封装 (3 天)

1. 将所有业务组件封装为 LangChain 工具
2. 添加工具文档和参数说明
3. 编写工具单元测试

### 阶段 3: Understanding Agent 增强 (2 天)

1. 添加表计算关键词识别
2. 更新 QuestionUnderstanding 模型
3. 编写表计算识别测试

### 阶段 4: Boost Agent 修复 (1 天)

1. 修改 use_metadata 默认值为 True
2. 添加元数据降级处理
3. 编写元数据使用测试

### 阶段 5: Insight Agent 渐进式分析 (5 天)

1. 实现智能分块逻辑
2. 实现 AI 驱动的洞察累积
3. 实现早停机制
4. 编写渐进式分析测试

### 阶段 6: Replanner Agent 智能重规划 (3 天)

1. 实现完成度评估模型
2. 实现重规划路由逻辑（跳过 Understanding）
3. 实现 Replanner Agent
4. 编写重规划测试

### 阶段 7: 集成测试 (2 天)

1. 运行所有单元测试
2. 运行属性测试
3. 端到端测试

**总计: 约 18 天（3.5 周）**



## 9. 多数据源支持（基于 Tableau Data Model）

### 9.1 Tableau 数据模型概念

Tableau 的数据模型基于 **Logical Tables（逻辑表）** 和 **Relationships（关系）**，VizQL Data Service 通过 `/get-datasource-model` API 暴露这些信息。

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Tableau Data Model 架构                                   │
│                                                                              │
│  ┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐│
│  │   Orders        │         │   Products      │         │   Customers     ││
│  │  (逻辑表)       │────────▶│  (逻辑表)       │         │  (逻辑表)       ││
│  │                 │         │                 │◀────────│                 ││
│  │  - Order ID     │         │  - Product ID   │         │  - Customer ID  ││
│  │  - Order Date   │         │  - Product Name │         │  - Customer Name││
│  │  - Product ID   │         │  - Category     │         │  - Region       ││
│  │  - Customer ID  │         │  - Price        │         │  - Segment      ││
│  │  - Sales        │         │                 │         │                 ││
│  └─────────────────┘         └─────────────────┘         └─────────────────┘│
│                                                                              │
│  关系（Relationships）：                                                     │
│  - Orders.Product ID → Products.Product ID                                  │
│  - Orders.Customer ID → Customers.Customer ID                               │
│                                                                              │
│  VizQL 特点：                                                                │
│  - 自动 JOIN（基于关系定义，无需手动指定）                                  │
│  - 字段来自不同逻辑表时，VizQL 自动处理关联                                 │
│  - 查询时只需指定字段名，不需要指定表名                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 9.2 数据模型 API

```python
# VizQL Data Service API: /get-datasource-model

# 请求
{
    "datasource": {
        "datasourceLuid": "abc123"
    }
}

# 响应
{
    "logicalTables": [
        {"logicalTableId": "orders", "caption": "Orders"},
        {"logicalTableId": "products", "caption": "Products"},
        {"logicalTableId": "customers", "caption": "Customers"}
    ],
    "logicalTableRelationships": [
        {
            "fromLogicalTable": {"logicalTableId": "orders"},
            "toLogicalTable": {"logicalTableId": "products"}
        },
        {
            "fromLogicalTable": {"logicalTableId": "orders"},
            "toLogicalTable": {"logicalTableId": "customers"}
        }
    ]
}
```

### 9.3 数据模型管理器

```python
# tableau_assistant/src/capabilities/datamodel/manager.py

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from langgraph.runtime import Runtime

from tableau_assistant.src.models.context import VizQLContext


class LogicalTable(BaseModel):
    """逻辑表"""
    logical_table_id: str = Field(description="逻辑表ID")
    caption: str = Field(description="逻辑表显示名称")
    fields: List[str] = Field(default_factory=list, description="该表包含的字段列表")


class TableRelationship(BaseModel):
    """表关系"""
    from_table_id: str = Field(description="源表ID")
    to_table_id: str = Field(description="目标表ID")
    from_field: Optional[str] = Field(default=None, description="源表关联字段")
    to_field: Optional[str] = Field(default=None, description="目标表关联字段")


class DataModel(BaseModel):
    """数据模型"""
    datasource_luid: str = Field(description="数据源LUID")
    logical_tables: List[LogicalTable] = Field(description="逻辑表列表")
    relationships: List[TableRelationship] = Field(description="表关系列表")
    field_to_table_map: Dict[str, str] = Field(
        default_factory=dict,
        description="字段到逻辑表的映射 {fieldCaption: logicalTableId}"
    )
    
    def get_table_for_field(self, field_caption: str) -> Optional[str]:
        """获取字段所属的逻辑表"""
        return self.field_to_table_map.get(field_caption)
    
    def get_related_tables(self, table_id: str) -> List[str]:
        """获取与指定表有关系的所有表"""
        related = []
        for rel in self.relationships:
            if rel.from_table_id == table_id:
                related.append(rel.to_table_id)
            elif rel.to_table_id == table_id:
                related.append(rel.from_table_id)
        return related
    
    def can_query_together(self, fields: List[str]) -> bool:
        """
        检查字段是否可以在同一查询中使用
        
        规则：
        - 同一逻辑表的字段可以一起查询
        - 有关系连接的逻辑表的字段可以一起查询
        """
        if not fields:
            return True
        
        # 获取所有字段所属的表
        tables = set()
        for field in fields:
            table = self.get_table_for_field(field)
            if table:
                tables.add(table)
        
        if len(tables) <= 1:
            return True
        
        # 检查所有表是否通过关系连接
        # 简化实现：检查是否所有表都与第一个表有直接或间接关系
        tables_list = list(tables)
        root_table = tables_list[0]
        connected = {root_table}
        
        # BFS 查找连接的表
        queue = [root_table]
        while queue:
            current = queue.pop(0)
            for related in self.get_related_tables(current):
                if related in tables and related not in connected:
                    connected.add(related)
                    queue.append(related)
        
        return tables.issubset(connected)


class DataModelManager:
    """
    数据模型管理器
    
    负责获取和缓存 Tableau 数据模型信息
    """
    
    def __init__(self, runtime: Runtime[VizQLContext]):
        self.runtime = runtime
        self.store_manager = StoreManager(runtime.store)
    
    async def get_data_model_async(
        self,
        use_cache: bool = True
    ) -> DataModel:
        """
        获取数据模型（异步版本）
        
        Args:
            use_cache: 是否使用缓存
        
        Returns:
            DataModel 对象
        """
        datasource_luid = self.runtime.context.datasource_luid
        
        # 1. 尝试从缓存获取
        if use_cache:
            cached_model = self.store_manager.get_data_model(datasource_luid)
            if cached_model:
                return cached_model
        
        # 2. 从 VizQL API 获取
        from tableau_assistant.src.bi_platforms.tableau.datamodel import get_datasource_model_async
        from tableau_assistant.src.models.context import get_tableau_config
        
        tableau_config = get_tableau_config(self.store_manager)
        
        raw_model = await get_datasource_model_async(
            api_key=tableau_config["tableau_token"],
            domain=tableau_config["tableau_domain"],
            datasource_luid=datasource_luid,
            site=tableau_config["tableau_site"]
        )
        
        # 3. 转换为 DataModel 对象
        data_model = self._convert_to_data_model(raw_model, datasource_luid)
        
        # 4. 构建字段到表的映射（需要结合 metadata）
        await self._build_field_to_table_map(data_model)
        
        # 5. 缓存
        self.store_manager.put_data_model(datasource_luid, data_model)
        
        return data_model
    
    def _convert_to_data_model(
        self,
        raw_model: Dict[str, Any],
        datasource_luid: str
    ) -> DataModel:
        """转换原始 API 响应为 DataModel 对象"""
        logical_tables = [
            LogicalTable(
                logical_table_id=t["logicalTableId"],
                caption=t["caption"]
            )
            for t in raw_model.get("logicalTables", [])
        ]
        
        relationships = [
            TableRelationship(
                from_table_id=r["fromLogicalTable"]["logicalTableId"],
                to_table_id=r["toLogicalTable"]["logicalTableId"]
            )
            for r in raw_model.get("logicalTableRelationships", [])
        ]
        
        return DataModel(
            datasource_luid=datasource_luid,
            logical_tables=logical_tables,
            relationships=relationships
        )
    
    async def _build_field_to_table_map(self, data_model: DataModel) -> None:
        """
        构建字段到逻辑表的映射
        
        通过 Metadata API 获取字段信息，结合数据模型推断字段所属表
        """
        # 获取 metadata
        from tableau_assistant.src.capabilities.metadata import MetadataManager
        
        metadata_manager = MetadataManager(self.runtime)
        metadata = await metadata_manager.get_metadata_async(use_cache=True)
        
        # 简化实现：如果只有一个逻辑表，所有字段都属于该表
        if len(data_model.logical_tables) == 1:
            table_id = data_model.logical_tables[0].logical_table_id
            for field in metadata.fields:
                data_model.field_to_table_map[field.fieldCaption] = table_id
            return
        
        # 多表情况：需要通过字段名匹配或其他启发式方法
        # TODO: 实现更智能的字段-表映射逻辑
        # 目前简化为：将所有字段映射到第一个表（VizQL 会自动处理 JOIN）
        default_table = data_model.logical_tables[0].logical_table_id
        for field in metadata.fields:
            data_model.field_to_table_map[field.fieldCaption] = default_table
```

### 9.4 Planning Agent 集成数据模型

```python
# 在 Planning Agent 中使用数据模型验证查询

class PlanningAgent(BaseVizQLAgent):
    """Planning Agent with Data Model awareness"""
    
    async def execute(
        self,
        state: VizQLState,
        runtime: Runtime[VizQLContext],
        **kwargs
    ) -> Dict[str, Any]:
        # 1. 获取数据模型
        data_model_manager = DataModelManager(runtime)
        data_model = await data_model_manager.get_data_model_async()
        
        # 2. 获取 QuestionUnderstanding
        understanding = state.get("question_understanding")
        
        # 3. 提取所有字段
        all_fields = []
        all_fields.extend([d.field_name for d in understanding.dimensions])
        all_fields.extend([m.field_name for m in understanding.measures])
        all_fields.extend([f.field_name for f in understanding.filters])
        
        # 4. 验证字段是否可以一起查询
        if not data_model.can_query_together(all_fields):
            # 字段来自不相关的表，需要拆分查询或报错
            raise QueryValidationError(
                f"字段来自不相关的逻辑表，无法在同一查询中使用: {all_fields}"
            )
        
        # 5. 继续正常的查询规划...
        return await self._build_query_plan(understanding, data_model)
```

### 9.5 多表查询示例

```
用户问题: "各地区各产品类别的销售额是多少？"

字段分析:
- 地区 (Region) → Customers 表
- 产品类别 (Category) → Products 表
- 销售额 (Sales) → Orders 表

数据模型检查:
- Orders → Products (有关系)
- Orders → Customers (有关系)
- 所有字段可以一起查询 ✓

VizQL 查询（自动 JOIN）:
{
    "datasource": {"datasourceLuid": "abc123"},
    "query": {
        "fields": [
            {"fieldCaption": "Region"},
            {"fieldCaption": "Category"},
            {"fieldCaption": "Sales", "function": "SUM"}
        ]
    }
}

VizQL 自动处理:
- 识别字段来自不同逻辑表
- 根据预定义的关系自动 JOIN
- 返回聚合结果
```

### 9.6 数据模型缓存策略

```python
# 缓存配置
DATA_MODEL_CACHE_TTL = 24 * 60 * 60  # 24小时（数据模型结构不常变）

# 缓存键
# namespace: ("data_model",)
# key: datasource_luid
```

## 10. 现有能力集成说明

### 10.1 元数据管理（已实现）

项目已有完整的元数据管理能力：

```python
# tableau_assistant/src/capabilities/metadata/manager.py

class MetadataManager:
    """
    元数据管理器（已实现）
    
    功能：
    - 从 Tableau Metadata API 获取字段信息
    - 缓存元数据到 Store（1小时 TTL）
    - 调用维度层级推断 Agent 增强元数据
    - 检测 STRING 类型日期字段格式
    - 获取日期字段的有效最大值（valid_max_date）
    """
```

**与设计文档的集成点**：
- `get_metadata` 工具：直接使用 `MetadataManager.get_metadata_async()`
- `semantic_map_fields` 工具：基于 `Metadata.fields` 进行字段名匹配

### 10.2 上下文管理（已实现）

项目已有运行时上下文管理：

```python
# tableau_assistant/src/models/context.py

@dataclass
class VizQLContext:
    """
    VizQL 运行时上下文（已实现）
    
    包含：
    - datasource_luid: 数据源 LUID
    - user_id: 用户 ID
    - session_id: 会话 ID
    - max_replan_rounds: 最大重规划轮数
    - parallel_upper_limit: 并行任务上限
    - max_retry_times: 最大重试次数
    - max_subtasks_per_round: 每轮最大子任务数
    """
```

**与设计文档的集成点**：
- 所有 Agent 通过 `runtime.context` 访问上下文
- Tableau 配置通过 `get_tableau_config(store_manager)` 获取

### 10.3 存储管理（已实现）

项目已有 Store 管理能力：

```python
# tableau_assistant/src/capabilities/storage/store_manager.py

class StoreManager:
    """
    存储管理器（已实现）
    
    功能：
    - 元数据缓存（1小时 TTL）
    - 维度层级缓存（24小时 TTL）
    - Tableau 配置存储
    """
```

## 11. 错误处理策略

### 11.1 API 调用错误

```python
# tableau_assistant/src/exceptions.py

class TableauAPIError(Exception):
    """Tableau API 调用错误"""
    def __init__(self, message: str, error_code: str = None, retry_after: int = None):
        self.message = message
        self.error_code = error_code
        self.retry_after = retry_after
        super().__init__(message)


class QueryValidationError(Exception):
    """查询验证错误"""
    pass


class FieldMappingError(Exception):
    """字段映射错误"""
    def __init__(self, semantic_field: str, candidates: List[str] = None):
        self.semantic_field = semantic_field
        self.candidates = candidates or []
        super().__init__(f"无法映射字段: {semantic_field}")
```

### 11.2 重试策略

```python
# tableau_assistant/src/utils/retry.py

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(TableauAPIError)
)
async def call_vizql_api_with_retry(func, *args, **kwargs):
    """带重试的 VizQL API 调用"""
    return await func(*args, **kwargs)
```

### 11.3 降级策略

```python
# 字段映射降级
async def semantic_map_fields_with_fallback(
    semantic_fields: List[str],
    metadata: Dict[str, Any]
) -> Dict[str, str]:
    """
    带降级的字段映射
    
    策略：
    1. 精确匹配
    2. 模糊匹配（Levenshtein 距离）
    3. 返回候选列表让 LLM 选择
    """
    result = {}
    unmapped = []
    
    for semantic_field in semantic_fields:
        # 1. 精确匹配
        exact_match = find_exact_match(semantic_field, metadata)
        if exact_match:
            result[semantic_field] = exact_match
            continue
        
        # 2. 模糊匹配
        fuzzy_matches = find_fuzzy_matches(semantic_field, metadata, threshold=0.7)
        if len(fuzzy_matches) == 1:
            result[semantic_field] = fuzzy_matches[0]
            continue
        
        # 3. 多候选或无匹配
        unmapped.append({
            "semantic_field": semantic_field,
            "candidates": fuzzy_matches
        })
    
    if unmapped:
        # 让 LLM 选择或报错
        raise FieldMappingError(
            f"无法映射字段: {[u['semantic_field'] for u in unmapped]}",
            candidates=unmapped
        )
    
    return result
```

## 12. Insight 数据模型

### 12.1 Insight 类型定义

```python
# tableau_assistant/src/models/insight.py

from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class InsightType(str, Enum):
    """洞察类型"""
    TREND = "TREND"              # 趋势洞察
    ANOMALY = "ANOMALY"          # 异常洞察
    COMPARISON = "COMPARISON"    # 对比洞察
    DISTRIBUTION = "DISTRIBUTION"  # 分布洞察
    CORRELATION = "CORRELATION"  # 相关性洞察
    RANKING = "RANKING"          # 排名洞察
    SUMMARY = "SUMMARY"          # 汇总洞察


class InsightPriority(str, Enum):
    """洞察优先级"""
    CRITICAL = "CRITICAL"  # 关键洞察（异常、重大变化）
    HIGH = "HIGH"          # 高优先级
    MEDIUM = "MEDIUM"      # 中优先级
    LOW = "LOW"            # 低优先级


class Insight(BaseModel):
    """洞察模型"""
    
    insight_id: str = Field(description="洞察唯一ID")
    
    type: InsightType = Field(description="洞察类型")
    
    priority: InsightPriority = Field(
        default=InsightPriority.MEDIUM,
        description="洞察优先级"
    )
    
    title: str = Field(description="洞察标题（简短描述）")
    
    description: str = Field(description="洞察详细描述")
    
    evidence: Dict[str, Any] = Field(
        default_factory=dict,
        description="""支撑数据
        
        示例：
        {
            "metric": "销售额",
            "value": 1000000,
            "change": 0.15,
            "period": "2024-Q4",
            "comparison_period": "2024-Q3"
        }
        """
    )
    
    confidence: float = Field(
        ge=0.0, le=1.0,
        default=0.8,
        description="置信度（0-1）"
    )
    
    related_fields: List[str] = Field(
        default_factory=list,
        description="相关字段列表"
    )
    
    source_chunk: Optional[str] = Field(
        default=None,
        description="来源数据块类型（用于渐进式分析追踪）"
    )


class InsightCollection(BaseModel):
    """洞察集合"""
    
    insights: List[Insight] = Field(default_factory=list)
    
    total_count: int = Field(default=0)
    
    by_type: Dict[InsightType, int] = Field(
        default_factory=dict,
        description="按类型统计"
    )
    
    by_priority: Dict[InsightPriority, int] = Field(
        default_factory=dict,
        description="按优先级统计"
    )
    
    def add_insight(self, insight: Insight) -> None:
        """添加洞察"""
        self.insights.append(insight)
        self.total_count += 1
        
        # 更新统计
        self.by_type[insight.type] = self.by_type.get(insight.type, 0) + 1
        self.by_priority[insight.priority] = self.by_priority.get(insight.priority, 0) + 1
    
    def get_top_insights(self, n: int = 5) -> List[Insight]:
        """获取 Top N 洞察（按优先级排序）"""
        priority_order = {
            InsightPriority.CRITICAL: 0,
            InsightPriority.HIGH: 1,
            InsightPriority.MEDIUM: 2,
            InsightPriority.LOW: 3
        }
        
        sorted_insights = sorted(
            self.insights,
            key=lambda x: (priority_order[x.priority], -x.confidence)
        )
        
        return sorted_insights[:n]
    
    def merge(self, other: "InsightCollection") -> None:
        """合并另一个洞察集合（用于渐进式分析）"""
        for insight in other.insights:
            self.add_insight(insight)
```

### 12.2 Insight Agent 输出格式

```python
# Insight Agent 返回格式

{
    "accumulated_insights": InsightCollection(
        insights=[
            Insight(
                insight_id="ins_001",
                type=InsightType.ANOMALY,
                priority=InsightPriority.CRITICAL,
                title="华东地区销售额异常下降",
                description="华东地区 2024-Q4 销售额同比下降 25%，显著低于其他地区",
                evidence={
                    "region": "华东",
                    "current_value": 750000,
                    "previous_value": 1000000,
                    "change_rate": -0.25,
                    "period": "2024-Q4"
                },
                confidence=0.95,
                related_fields=["Region", "Sales", "Order Date"],
                source_chunk="anomalies"
            ),
            Insight(
                insight_id="ins_002",
                type=InsightType.TREND,
                priority=InsightPriority.HIGH,
                title="整体销售额持续增长",
                description="过去 4 个季度销售额保持 10% 以上的增长率",
                evidence={
                    "trend_direction": "UP",
                    "growth_rate": 0.12,
                    "periods": ["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4"]
                },
                confidence=0.88,
                related_fields=["Sales", "Order Date"],
                source_chunk="top_data"
            )
        ],
        total_count=2,
        by_type={InsightType.ANOMALY: 1, InsightType.TREND: 1},
        by_priority={InsightPriority.CRITICAL: 1, InsightPriority.HIGH: 1}
    ),
    "analysis_progress": {
        "total_chunks": 4,
        "analyzed_chunks": 2,
        "current_chunk_type": "mid_data",
        "early_stopped": False,
        "stop_reason": None
    }
}
```



