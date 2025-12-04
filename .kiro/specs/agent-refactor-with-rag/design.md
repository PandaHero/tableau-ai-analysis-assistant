# 设计文档：Agent 重构与 RAG 集成

## 概述

本设计文档描述了 Tableau Assistant 的 Agent 重构方案，整合现有的 RAG 增强功能和 LangChain/LangGraph 中间件系统。

### 附件文档

本设计文档包含以下附件，提供详细的实现方案：

| 附件 | 内容 | 说明 |
|------|------|------|
| [design-appendix-semantic-layer.md](./design-appendix-semantic-layer.md) | **纯语义中间层架构** | SemanticQuery、FieldMapper、ImplementationResolver、ExpressionGenerator 完整设计 |
| [design-appendix-data-models.md](./design-appendix-data-models.md) | 数据模型详细定义 | 旧版数据模型，已部分迁移到 semantic-layer |
| [design-appendix-prompts.md](./design-appendix-prompts.md) | Prompt 模板更新 | 表计算/LOD 识别规则、动态模块化扩展 |
| [design-appendix-query-builder.md](./design-appendix-query-builder.md) | QueryBuilder 实现细节 | Intent → VizQL 转换规则、API 请求示例 |

### 参考文档

| 文档 | 路径 | 说明 |
|------|------|------|
| Prompt 和数据模型编写指南 | `tableau_assistant/docs/PROMPT_AND_MODEL_GUIDE.md` | 编写规范 |
| VizQL Data Service API | `openapi.json` | API 规范 |

### 设计原则

1. **利用现有框架**：直接使用 LangChain 提供的中间件，不重复造轮子
2. **自主实现关键功能**：FilesystemMiddleware 和 PatchToolCallsMiddleware 由我们自主实现
3. **薄封装策略**：工具层是对现有组件（MetadataManager、DateManager、SemanticMapper）的薄封装
4. **保持 StateGraph 架构**：使用 LangGraph StateGraph 进行工作流编排
5. **职责分离**：渐进式洞察（处理 DataFrame）与 SummarizationMiddleware（处理 Messages）分离

### 中间件来源与分类

#### 来自 LangChain（直接使用）

| 中间件 | 功能 | 必需性 |
|--------|------|--------|
| `TodoListMiddleware` | 任务管理，提供 `write_todos` 工具 | ✅ 必需 |
| `SummarizationMiddleware` | 对话历史自动总结，避免 token 超限 | ✅ 必需 |
| `HumanInTheLoopMiddleware` | 工具调用前请求人工确认 | ⭐ 可选 |
| `ModelRetryMiddleware` | LLM 调用失败自动重试 | ✅ 必需 |
| `ToolRetryMiddleware` | 工具调用失败自动重试 | ✅ 必需 |

#### 自主实现（生产级代码）

| 中间件 | 功能 | 必需性 |
|--------|------|--------|
| `FilesystemMiddleware` | 大结果自动转存 + 文件系统工具 | ✅ 必需 |
| `PatchToolCallsMiddleware` | 修复悬空的工具调用 | ✅ 必需 |

## 架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Tableau Assistant                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         中间件栈 (7 个)                                │  │
│  │  LangChain: TodoList | Summarization | HumanInTheLoop | ModelRetry    │  │
│  │             | ToolRetry                                                │  │
│  │  自主实现: Filesystem | PatchToolCalls                                 │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    ↓                                         │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                      StateGraph 工作流                                 │  │
│  │  Boost → Understanding → QueryBuilder → Execute → Insight → Replanner │  │
│  │                              ↓                                         │  │
│  │                    FieldMapper + ImplementationResolver                │  │
│  │                    + ExpressionGenerator (确定性代码)                  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    ↓                                         │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         工具层 (薄封装)                                │  │
│  │  get_metadata | parse_date | semantic_map_fields | build_vizql_query  │  │
│  │  execute_vizql_query | detect_date_format | analyze_completeness      │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    ↓                                         │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                       现有组件                                         │  │
│  │  ✅ MetadataManager (已实现：缓存、增强、降级)                         │  │
│  │  ✅ DateManager (已实现：计算、解析、格式检测)                         │  │
│  │  ✅ SemanticMapper (已实现：向量检索、LLM 判断、缓存)                  │  │
│  │  🔧 QueryBuilder (需完善：表计算 TableCalc、LOD 计算)                  │  │
│  │  🔧 AnalysisCoordinator (需完善：渐进式洞察系统)                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 工作流架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         StateGraph 工作流                                    │
│                                                                              │
│   START                                                                      │
│     │                                                                        │
│     ▼                                                                        │
│  ┌─────────┐                                                                 │
│  │ Boost?  │──── No ────────────────────────┐                               │
│  └────┬────┘                                │                               │
│       │ Yes                                 │                               │
│       ▼                                     │                               │
│  ┌─────────────────────────────────────┐   │                               │
│  │        Boost Agent (LLM)            │   │                               │
│  │  工具: get_metadata                 │   │                               │
│  │  输出: boosted_question             │   │                               │
│  └────────────────┬────────────────────┘   │                               │
│                   │                        │                               │
│                   ▼                        ▼                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              Understanding Agent (LLM)                               │   │
│  │  工具: parse_date, detect_date_format                                │   │
│  │  输出: SemanticQuery (纯语义，无 VizQL 概念)                         │   │
│  └────────────────────────────┬────────────────────────────────────────┘   │
│                               │                                             │
│                               ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │           QueryBuilder Node (非 LLM，确定性代码)                     │   │
│  │  组件: FieldMapper (RAG+LLM) + ImplementationResolver (代码规则)    │   │
│  │        + ExpressionGenerator (代码模板)                              │   │
│  │  输出: VizQLQuery (技术字段名 + 表达式)                              │   │
│  └────────────────────────────┬────────────────────────────────────────┘   │
│                               │                                             │
│                               ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              Execute Node (非 LLM，确定性执行)                       │   │
│  │  功能: VizQLQuery → API 调用                                        │   │
│  │  输出: QueryResult                                                   │   │
│  └────────────────────────────┬────────────────────────────────────────┘   │
│                               │                                             │
│                               ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                Insight Agent (LLM)                                   │   │
│  │  系统: 渐进式累积洞察分析 (AnalysisCoordinator)                      │   │
│  │  输出: accumulated_insights                                          │   │
│  └────────────────────────────┬────────────────────────────────────────┘   │
│                               │                                             │
│                               ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │               Replanner Agent (LLM)                                  │   │
│  │  工具: analyze_completeness                                          │   │
│  │  输出: ReplanDecision                                                │   │
│  └────────────────────────────┬────────────────────────────────────────┘   │
│                               │                                             │
│                    ┌──────────┴──────────┐                                  │
│                    │                     │                                  │
│            should_replan?          completeness >= 0.9                      │
│            replan_count < max?      或 replan_count >= max                  │
│                    │                     │                                  │
│                    ▼                     ▼                                  │
│              ┌──────────────┐      ┌──────────┐                             │
│              │Understanding │      │   END    │                             │
│              │ (重新语义   │      └──────────┘                             │
│              │  理解)       │                                                │
│              └──────────────┘                                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Agent/Node 工具分配表

| Agent/Node | 类型 | 可用工具/组件 | 输入 | 输出 |
|------------|------|--------------|------|------|
| Boost Agent | LLM | get_metadata | original_question | boosted_question |
| Understanding Agent | LLM | parse_date, detect_date_format（均来自 DateManager） | current_question | SemanticQuery（纯语义） |
| QueryBuilder Node | 非 LLM | FieldMapper + ImplementationResolver + ExpressionGenerator | SemanticQuery | VizQLQuery |
| Execute Node | 非 LLM | VizQL API 调用 | VizQLQuery | QueryResult |
| Insight Agent | LLM | AnalysisCoordinator（需完善） | QueryResult, original_question | accumulated_insights |
| Replanner Agent | LLM | write_todos（来自 TodoListMiddleware） | insights, QueryResult | ReplanDecision |

**说明**：
- **parse_date / detect_date_format**：都是 DateManager 的薄封装，DateManager 统一管理日期计算、解析、格式检测
- **QueryBuilder Node**：纯语义中间层的核心，包含三个确定性代码组件：
  - **FieldMapper**：RAG + LLM 混合字段映射（业务术语 → 技术字段）
  - **ImplementationResolver**：代码规则判断表计算/LOD + addressing
  - **ExpressionGenerator**：代码模板生成 VizQL 表达式
- **AnalysisCoordinator**：渐进式洞察系统，需要完善以支持更复杂的分析场景
- **Replanner Agent**：使用 write_todos 工具管理后续问题

### 中间件 vs 工具 的区别

| 概念 | 定义 | 调用方式 | 示例 |
|-----|------|---------|------|
| **中间件（Middleware）** | Agent 执行过程中自动生效的能力增强 | 自动触发，无需显式调用 | HumanInTheLoopMiddleware、ModelRetryMiddleware |
| **工具（Tool）** | Agent 可以显式调用的功能单元 | Agent 通过 tool_calls 显式调用 | get_metadata、parse_date、write_todos |

**HumanInTheLoopMiddleware 与 Replanner 的协作**：

```
Replanner Agent
    │
    ▼ 生成 ReplanDecision（包含 2-5 个后续问题）
    │
    ▼ HumanInTheLoopMiddleware 自动暂停（中间件行为）
    │
    ▼ 用户审查问题（选择/修改/拒绝）
    │
    ▼ 用户选择的问题通过 write_todos 工具添加到 TodoList
    │
    ▼ 继续执行或结束
```

**关键点**：
- HumanInTheLoopMiddleware 是**中间件**，自动在 Replanner 输出后暂停
- write_todos 是**工具**，由 TodoListMiddleware 提供，用于管理任务队列
- Replanner Agent 可以调用 write_todos 将后续问题添加到执行队列

## 组件和接口

### 1. Agent 创建工厂

```python
# tableau_assistant/src/agents/agent_factory.py

from typing import List, Dict, Any, Optional
from langchain_core.tools import BaseTool
from langchain.agents.middleware import (
    TodoListMiddleware,
    SummarizationMiddleware,
    HumanInTheLoopMiddleware,
    ModelRetryMiddleware,
    ToolRetryMiddleware,
)
from langgraph.prebuilt import create_react_agent

# 自主实现的中间件
from tableau_assistant.src.middleware.filesystem import FilesystemMiddleware
from tableau_assistant.src.middleware.patch_tool_calls import PatchToolCallsMiddleware


def create_tableau_agent(
    tools: List[BaseTool],
    model_name: Optional[str] = None,
    store: Optional[BaseStore] = None,
    config: Optional[Dict[str, Any]] = None
) -> CompiledStateGraph:
    """
    创建 Tableau Assistant 的 Agent
    
    Args:
        tools: 业务工具列表
        model_name: LLM 模型名称
        store: 持久化存储实例
        config: 额外配置
    
    Returns:
        编译后的 Agent 图
    """
    config = config or {}
    
    middleware = [
        # LangChain 内置
        TodoListMiddleware(),
        SummarizationMiddleware(
            model=model_name,
            trigger=("tokens", config.get("summarization_token_threshold", 100000)),
            keep=("messages", config.get("messages_to_keep", 10)),
        ),
        ModelRetryMiddleware(max_retries=config.get("model_max_retries", 3)),
        ToolRetryMiddleware(max_retries=config.get("tool_max_retries", 3)),
        
        # 自主实现
        FilesystemMiddleware(
            tool_token_limit_before_evict=config.get("filesystem_token_limit", 20000),
        ),
        PatchToolCallsMiddleware(),
    ]
    
    if config.get("interrupt_on"):
        middleware.append(HumanInTheLoopMiddleware(interrupt_on=config["interrupt_on"]))
    
    return create_react_agent(
        model=model_name,
        tools=tools,
        middleware=middleware,
        checkpointer=True,
    )
```

### 2. 工具层设计（薄封装）

```python
# tableau_assistant/src/tools/metadata_tool.py

from langchain_core.tools import tool
from tableau_assistant.src.capabilities.metadata import MetadataManager


@tool
async def get_metadata(
    use_cache: bool = True,
    enhance: bool = True,
    filter_role: Optional[str] = None
) -> str:
    """
    获取数据源元数据
    
    Args:
        use_cache: 是否使用缓存 (默认 True)
        enhance: 是否增强元数据 (默认 True)
        filter_role: 按角色过滤 (dimension/measure)
    
    Returns:
        LLM 友好的字段列表摘要
    """
    # 委托给 MetadataManager
    metadata = await metadata_manager.get_metadata_async(
        use_cache=use_cache,
        enhance=enhance
    )
    
    # 转换为 LLM 友好格式
    return _format_metadata_for_llm(metadata, filter_role)
```

```python
# tableau_assistant/src/tools/date_tool.py

from langchain_core.tools import tool
from tableau_assistant.src.capabilities.date_processing import DateManager


@tool
def parse_date(
    expression: str,
    reference_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    解析日期表达式
    
    Args:
        expression: 日期表达式 (如 "最近3个月", "2024年1月")
        reference_date: 参考日期 (默认当前日期)
    
    Returns:
        {"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"} 或 {"error": "..."}
    """
    # 委托给 DateManager
    try:
        time_range = _parse_expression_to_time_range(expression)
        start, end = date_manager.parse_time_range(time_range, reference_date)
        return {"start_date": start, "end_date": end}
    except Exception as e:
        return {"start_date": None, "end_date": None, "error": str(e)}


@tool
def detect_date_format(sample_values: List[str]) -> Dict[str, Any]:
    """
    检测日期格式
    
    Args:
        sample_values: 样本值列表
    
    Returns:
        {"format_type": "ISO_DATE", "pattern": "YYYY-MM-DD", "conversion_hint": "..."}
    """
    format_type = date_manager.detect_field_date_format(sample_values)
    if format_type:
        info = date_manager.get_format_info(format_type)
        return {
            "format_type": format_type.value,
            "pattern": info["pattern"],
            "conversion_hint": f"使用 {info['pattern']} 格式解析"
        }
    return {"format_type": None, "error": "无法检测日期格式"}
```

```python
# tableau_assistant/src/tools/rag_tool.py

from langchain_core.tools import tool
from tableau_assistant.src.capabilities.rag import SemanticMapper


@tool
async def semantic_map_fields(
    business_terms: List[str],
    context: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    将业务术语映射到技术字段
    
    Args:
        business_terms: 业务术语列表
        context: 问题上下文
    
    Returns:
        映射结果列表，每个包含 matched_field, confidence, alternatives
    """
    results = await semantic_mapper.map_fields_batch(business_terms, context)
    return [
        {
            "term": r.term,
            "matched_field": r.matched_field.fieldCaption if r.matched_field else None,
            "confidence": r.confidence,
            "category": r.matched_field.category if r.matched_field else None,
            "level": r.matched_field.level if r.matched_field else None,
            "alternatives": [
                {"field": a.field.fieldCaption, "score": a.score}
                for a in r.alternatives[:3]
            ] if r.confidence < 0.7 else []
        }
        for r in results
    ]
```

### 3. QueryBuilder 完善（表计算和 LOD）

**当前状态**：QueryBuilder 已实现基本的查询构建功能，但需要完善以支持表计算和 LOD 计算。

**需要完善的功能**：

```python
# tableau_assistant/src/capabilities/query/builder.py

class QueryBuilder:
    """
    查询构建器
    
    需要完善：
    1. TableCalcIntent → TableCalcField 转换
    2. LOD 计算支持（FIXED、INCLUDE、EXCLUDE）
    3. 复杂过滤条件组合
    """
    
    def build_vizql_query(self, query_plan: QueryPlan) -> VizQLQuery:
        """
        将 QueryPlan 转换为 VizQL Query
        
        转换规则：
        - DimensionIntent → DimensionField
        - MeasureIntent → MeasureField
        - FilterIntent → Filter
        - TableCalcIntent → TableCalcField (需完善)
        - LODIntent → LODField (需完善)
        """
        query = VizQLQuery()
        
        # 基本字段转换
        for dim in query_plan.dimensions:
            query.add_dimension(self._convert_dimension(dim))
        
        for measure in query_plan.measures:
            query.add_measure(self._convert_measure(measure))
        
        for filter in query_plan.filters:
            query.add_filter(self._convert_filter(filter))
        
        # 表计算转换（需完善）
        if query_plan.table_calc:
            query.add_table_calc(self._convert_table_calc(query_plan.table_calc))
        
        # LOD 计算转换（需完善）
        if query_plan.lod_calcs:
            for lod in query_plan.lod_calcs:
                query.add_lod(self._convert_lod(lod))
        
        return query
    
    def _convert_table_calc(self, intent: TableCalcIntent) -> TableCalcField:
        """
        表计算转换（需完善）
        
        支持的表计算类型：
        - RUNNING_TOTAL: 累计总计
        - RANK: 排名
        - MOVING_CALCULATION: 移动计算
        - PERCENT_OF_TOTAL: 总计百分比
        - DIFFERENCE_FROM: 差异
        - PERCENT_DIFFERENCE_FROM: 百分比差异
        """
        pass  # TODO: 实现
    
    def _convert_lod(self, intent: LODIntent) -> LODField:
        """
        LOD 计算转换（需完善）
        
        支持的 LOD 类型：
        - FIXED: 固定粒度
        - INCLUDE: 包含维度
        - EXCLUDE: 排除维度
        """
        pass  # TODO: 实现
```

### 4. 渐进式累积洞察分析系统

**当前状态**：AnalysisCoordinator 框架已设计，需要完善具体实现。

```python
# tableau_assistant/src/capabilities/insight/coordinator.py

class AnalysisCoordinator:
    """
    分析协调器 - 三层架构的主持人层
    
    职责：
    1. 评估数据规模和复杂度
    2. 选择分析策略 (direct/progressive/hybrid)
    3. 编排分析流程
    4. 监控分析质量
    """
    
    def __init__(self):
        self.profiler = DataProfiler()
        self.chunker = SemanticChunker()
        self.analyzer = ChunkAnalyzer()
        self.accumulator = InsightAccumulator()
        self.synthesizer = InsightSynthesizer()
    
    async def analyze(
        self,
        data: DataFrame,
        context: Dict
    ) -> InsightResult:
        """主分析流程"""
        
        # 1. 数据画像
        profile = self.profiler.profile(data)
        
        # 2. 选择策略
        strategy = self._select_strategy(profile)
        
        # 3. 执行分析
        if strategy == "direct":
            return await self._direct_analysis(data, context)
        elif strategy == "progressive":
            return await self._progressive_analysis(data, context, profile)
        else:
            return await self._hybrid_analysis(data, context, profile)
    
    def _select_strategy(self, profile: DataProfile) -> str:
        """
        选择分析策略
        - < 100 行: direct
        - 100-1000 行: progressive
        - > 1000 行: hybrid
        """
        if profile.row_count < 100:
            return "direct"
        elif profile.row_count < 1000:
            return "progressive"
        return "hybrid"
```

### 6. 工具注册表

```python
# tableau_assistant/src/tools/registry.py

class ToolRegistry:
    """工具注册表"""
    
    _tools: Dict[str, List[BaseTool]] = {
        "boost": [],
        "understanding": [],
        "planning": [],
        "replanner": [],
    }
    
    @classmethod
    def register(cls, node_type: str, tool: BaseTool):
        """注册工具到指定节点"""
        cls._tools[node_type].append(tool)
    
    @classmethod
    def get_tools(cls, node_type: str) -> List[BaseTool]:
        """获取节点的工具列表"""
        return cls._tools.get(node_type, [])
    
    @classmethod
    def auto_discover(cls):
        """自动发现并注册工具"""
        # boost_tools
        cls.register("boost", get_metadata)
        
        # understanding_tools (均来自 DateManager)
        cls.register("understanding", parse_date)
        cls.register("understanding", detect_date_format)
        
        # query_builder_tools (用于 FieldMapper 组件)
        cls.register("query_builder", semantic_map_fields)
        
        # replanner_tools
        # write_todos 来自 TodoListMiddleware，用于管理后续问题
        # HumanInTheLoopMiddleware 会自动暂停让用户选择
        cls.register("replanner", write_todos)
```

## 数据模型

### VizQLState

```python
class VizQLState(TypedDict):
    """工作流状态"""
    # 问题相关
    question: str
    boost_question: bool
    boosted_question: Optional[str]
    current_question: str
    
    # 理解和查询构建
    semantic_query: Optional[SemanticQuery]  # Understanding Agent 输出（纯语义）
    vizql_query: Optional[VizQLQuery]  # QueryBuilder Node 输出（技术字段）
    
    # 执行结果
    query_result: Optional[QueryResult]
    
    # 洞察（渐进式累积）
    insights: List[Dict[str, Any]]
    all_insights: List[Dict[str, Any]]
    
    # 重规划
    replan_count: int
    replan_decision: Optional[ReplanDecision]
    
    # 任务管理
    todos: List[TodoItem]
    
    # 元数据
    metadata: Optional[Metadata]
    
    # 错误和警告
    errors: List[Dict[str, Any]]
    warnings: List[Dict[str, Any]]
```

### ReplanDecision

```python
class ReplanDecision(BaseModel):
    """重规划决策"""
    should_replan: bool
    completeness_score: float  # 0.0 - 1.0
    new_question: Optional[str]
    reasoning: str
```

### InsightResult

```python
class InsightResult(BaseModel):
    """洞察结果"""
    type: Literal["trend", "anomaly", "pattern", "comparison"]
    title: str
    description: str
    confidence: float  # 0.0 - 1.0
    evidence: List[str]
    priority: Literal["high", "medium", "low"]
```



## 正确性属性

*属性是一个特征或行为，应该在系统的所有有效执行中保持为真。属性作为人类可读规范和机器可验证正确性保证之间的桥梁。*

### 属性 1: 中间件配置完整性
*对于任何* Agent 创建请求，创建的 Agent 应该包含以下中间件：TodoListMiddleware、SummarizationMiddleware、ModelRetryMiddleware、ToolRetryMiddleware、FilesystemMiddleware、PatchToolCallsMiddleware
**验证需求: 1.1, 1.2**

### 属性 2: 工作流节点顺序保持
*对于任何* 工作流执行，当所有节点都需要执行时，节点执行顺序应该严格遵循：Boost → Understanding → Planning → Execute → Insight → Replanner
**验证需求: 2.2**

### 属性 3: Boost 节点条件跳过
*对于任何* 工作流执行，当 boost_question 标志为 False 时，工作流应该跳过 Boost 节点并直接从 Understanding 节点开始
**验证需求: 2.3**

### 属性 4: 重规划路由正确性
*对于任何* 工作流执行，当 Replanner 决定重规划（should_replan=True 且 replan_count < max）时，工作流应该路由回 Understanding 节点（重新进行语义理解）
**验证需求: 2.4, 17.1**

### 属性 5: 状态累积保持
*对于任何* 状态转换，节点输出应该合并到 VizQLState 而不丢失现有数据（insights、results、errors 应该累积而非覆盖）
**验证需求: 2.6, 18.2**

### 属性 6: 工具输入验证
*对于任何* 工具调用，输入参数应该通过 Pydantic 模型验证，无效输入应该返回结构化错误而非抛出异常
**验证需求: 3.2, 3.3**

### 属性 7: 大输出文件转存
*对于任何* 工具输出超过 token 限制（默认 20000）的情况，输出应该自动保存到文件系统并返回文件引用
**验证需求: 3.5, 12.1**

### 属性 8: RAG 高置信度快速路径
*对于任何* 向量检索 top-1 置信度 > 0.9 的字段映射请求，应该跳过 LLM 判断直接返回结果
**验证需求: 4.3**

### 属性 9: RAG 低置信度备选返回
*对于任何* 置信度 < 0.7 的字段映射结果，应该返回 top-3 备选字段及其置信度分数
**验证需求: 4.4**

### 属性 10: 字段映射缓存一致性
*对于任何* 相同业务术语的重复映射请求（在 TTL 内），应该从缓存返回相同结果
**验证需求: 4.5**

### 属性 11: 维度层级 RAG 增强
*对于任何* 维度层级推断请求，当存在相似度 > 0.8 的历史模式时，应该将 top-3 模式作为 few-shot 示例
**验证需求: 4.1.1, 4.1.2**

### 属性 12: 元数据工具委托
*对于任何* get_metadata 工具调用，应该委托给 MetadataManager.get_metadata_async() 并返回 LLM 友好格式
**验证需求: 5.1, 5.3**

### 属性 13: 日期解析往返一致性
*对于任何* 有效的日期表达式，parse_date 工具应该返回有效的日期范围（start_date <= end_date）
**验证需求: 6.2, 6.3**

### 属性 14: 查询构建正确性
*对于任何* QueryPlan，build_vizql_query 应该正确转换所有 Intent 类型（DimensionIntent → DimensionField 等）
**验证需求: 7.1**

### 属性 15: 渐进式分析策略选择
*对于任何* 数据集，AnalysisCoordinator 应该根据数据量选择正确的策略：direct（<100行）、progressive（100-1000行）、hybrid（>1000行）
**验证需求: 8.2**

### 属性 16: 洞察累积去重
*对于任何* 渐进式分析过程，InsightAccumulator 应该检查重复并合并相似洞察（相似度 > 0.8）
**验证需求: 8.5**

### 属性 17: LLM 重试指数退避
*对于任何* LLM 调用失败的重试，重试间隔应该遵循指数退避策略（1s、2s、4s）
**验证需求: 9.2**

### 属性 18: 对话总结职责分离
*对于任何* 对话总结操作，SummarizationMiddleware 应该只总结对话消息，不应该修改 VizQLState.insights
**验证需求: 11.5**

### 属性 19: 悬空工具调用修复
*对于任何* AIMessage 包含 tool_calls 但没有对应 ToolMessage 的情况，PatchToolCallsMiddleware 应该自动添加取消消息
**验证需求: 13.1**

### 属性 20: 错误分类正确性
*对于任何* 错误，Error_Handler 应该正确分类为 TransientError（可重试）、PermanentError（不可重试）或 UserError（需用户修正）
**验证需求: 21.1**

## 错误处理

### 错误类型

| 错误类型 | 描述 | 处理策略 |
|---------|------|---------|
| TransientError | 瞬态错误（网络超时、API 限流） | 自动重试，指数退避 |
| PermanentError | 永久性错误（无效配置、权限不足） | 立即终止，返回错误消息 |
| UserError | 用户错误（无效输入、字段不存在） | 返回友好消息，包含修正建议 |

### 中间件错误处理

| 中间件 | 错误类型 | 处理策略 |
|--------|----------|----------|
| SummarizationMiddleware | 总结失败 | 保留原始消息，记录警告 |
| ModelRetryMiddleware | 重试耗尽 | 抛出异常，包含原始错误和重试次数 |
| ToolRetryMiddleware | 重试耗尽 | 返回错误 ToolMessage |
| FilesystemMiddleware | 文件写入失败 | 返回原始内容，记录警告 |
| PatchToolCallsMiddleware | 修复失败 | 保留原始消息，记录警告 |

## 测试策略

### 单元测试

- 每个工具的独立测试
- 每个中间件的独立测试
- 测试覆盖率要求 >= 80%
- 测试文件位置：`tableau_assistant/tests/unit/`

### 属性测试（Property-Based Testing）

使用 Hypothesis 框架实现属性测试：

```python
from hypothesis import given, strategies as st

@given(st.integers(min_value=1, max_value=10000))
def test_analysis_strategy_selection(row_count):
    """
    **Feature: agent-refactor-with-rag, Property 15: 渐进式分析策略选择**
    """
    profile = DataProfile(row_count=row_count)
    strategy = coordinator._select_strategy(profile)
    
    if row_count < 100:
        assert strategy == "direct"
    elif row_count < 1000:
        assert strategy == "progressive"
    else:
        assert strategy == "hybrid"


@given(st.floats(min_value=0.0, max_value=1.0))
def test_rag_confidence_path(confidence):
    """
    **Feature: agent-refactor-with-rag, Property 8: RAG 高置信度快速路径**
    """
    result = mock_vector_search(confidence=confidence)
    
    if confidence > 0.9:
        assert not llm_was_called()
    else:
        # LLM 可能被调用
        pass
```

### 集成测试

- 端到端工作流测试
- 中间件协同工作测试
- 测试文件位置：`tableau_assistant/tests/integration/`

### 测试标注格式

每个属性测试必须使用以下格式标注：
```
**Feature: agent-refactor-with-rag, Property {number}: {property_text}**
```
