# 设计文档

## 概述

本设计文档描述了将 DeepAgents 框架集成到 Tableau Assistant 系统的技术方案。集成的核心目标是利用 DeepAgents 提供的 6 个内置中间件（Prompt 缓存、对话总结、文件系统、工具调用修复、任务管理和人工介入），同时保持现有的 StateGraph 工作流架构和组件业务逻辑不变。

### 设计目标

1. **减少自定义代码**: 用 DeepAgents 内置中间件替换自定义实现，减少维护负担
2. **保持架构稳定**: 保留现有的 StateGraph 节点流程和业务逻辑
3. **提升性能**: 通过 Prompt 缓存和对话总结降低成本和延迟
4. **增强用户体验**: 通过人工介入和任务管理提供更好的交互控制
5. **简化大数据处理**: 通过文件系统中间件自动处理大结果集

### 集成范围

**包含的中间件**:
- AnthropicPromptCachingMiddleware (Claude 模型专用)
- SummarizationMiddleware
- FilesystemMiddleware
- PatchToolCallsMiddleware
- TodoListMiddleware
- HumanInTheLoopMiddleware

**排除的中间件**:
- SubAgentMiddleware (使用 StateGraph 替代)

## 架构

### 整体架构图

系统采用分层架构，从上到下分为 6 层：

```
┌─────────────────────────────────────────────────────────────────┐
│                         API 层                                   │
│                    (FastAPI Endpoints)                           │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                   DeepAgents 集成层                              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ create_deep_agent() 创建配置了 6 个中间件的 Agent:       │   │
│  │  • AnthropicPromptCachingMiddleware (Claude 专用)        │   │
│  │  • SummarizationMiddleware (对话总结)                    │   │
│  │  • FilesystemMiddleware (大文件处理)                     │   │
│  │  • PatchToolCallsMiddleware (工具调用修复)               │   │
│  │  • TodoListMiddleware (任务队列管理)                     │   │
│  │  • HumanInTheLoopMiddleware (人工介入)                   │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                   StateGraph 工作流层                            │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 节点执行顺序 (标注 LLM 使用):                            │   │
│  │  Boost (LLM) → Understanding (LLM) → Planning (LLM+RAG)  │   │
│  │  → Execute → Insight (LLM) → Replanner (LLM)             │   │
│  │                              ↑                           │   │
│  │                              │                           │   │
│  │                          (决定是否重规划)                │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                        工具层                                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 8 个 LangChain 工具 (封装现有组件):                      │   │
│  │  1. get_metadata          5. semantic_map_fields         │   │
│  │  2. parse_date            6. process_query_result        │   │
│  │  3. build_vizql_query     7. detect_statistics           │   │
│  │  4. execute_vizql_query   8. save_large_result           │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                       组件层                                     │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 现有业务组件 (业务逻辑保持不变):                         │   │
│  │  • MetadataManager (元数据管理)                          │   │
│  │  • DateParser (日期解析)                                 │   │
│  │  • QueryBuilder (查询构建)                               │   │
│  │  • QueryExecutor (查询执行)                              │   │
│  │  • SemanticMapper (语义映射 - RAG 实现)                  │   │
│  │    → 使用向量数据库 (FAISS/Chroma)                       │   │
│  │    → 语义搜索匹配字段名                                  │   │
│  │  • DataProcessor (数据处理)                              │   │
│  │  • StatisticsDetector (统计检测)                         │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                       存储层                                     │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ SQLite Store:                                            │   │
│  │  • 元数据缓存                                            │   │
│  │  • 查询结果缓存                                          │   │
│  │  • Prompt 缓存 (Claude)                                  │   │
│  │  • 对话历史总结                                          │   │
│  │  • 文件系统引用                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**关键设计点**:
1. **DeepAgents 集成层**: 负责创建和配置 Agent，管理 6 个中间件
2. **StateGraph 保持不变**: 现有的工作流节点和执行顺序完全保留
3. **工具封装**: 将现有组件封装为标准 LangChain 工具，不改变业务逻辑
4. **统一存储**: 所有持久化数据使用 SQLite Store

### 工作流执行流程

完整的查询处理流程如下：

```
用户
 │
 │ 1. 发送查询请求
 ▼
API 层
 │
 │ 2. 创建 DeepAgent
 ▼
DeepAgent (配置 6 个中间件)
 │
 │ 3. 初始化 StateGraph 工作流
 ▼
┌─────────────────────────────────────────────────────────────┐
│                    StateGraph 工作流                         │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 阶段 1: Boost (可选 - 使用 LLM)                       │  │
│  │  • 调用 get_metadata 工具                            │  │
│  │  • MetadataManager 从 Store 读取缓存                 │  │
│  │  • LLM 根据元数据优化用户问题                        │  │
│  │  • 补充缺失的上下文信息                              │  │
│  └──────────────────────────────────────────────────────┘  │
│                         │                                   │
│                         ▼                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 阶段 2: Understanding (使用 LLM)                      │  │
│  │  • 调用 parse_date 工具                              │  │
│  │  • DateParser 解析日期表达式                         │  │
│  │  • LLM 理解用户意图                                  │  │
│  │  • 提取维度、度量、时间范围等关键信息                │  │
│  │  • 识别问题类型和复杂度                              │  │
│  └──────────────────────────────────────────────────────┘  │
│                         │                                   │
│                         ▼                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 阶段 3: Planning (使用 LLM + RAG)                     │  │
│  │  • 调用 semantic_map_fields 工具 (RAG)               │  │
│  │    → SemanticMapper 使用向量数据库匹配字段           │  │
│  │    → 语义搜索找到最相关的实际字段名                  │  │
│  │  • 调用 build_vizql_query 工具                       │  │
│  │  • QueryBuilder 生成查询规格                         │  │
│  │  • 分配任务和依赖关系                                │  │
│  └──────────────────────────────────────────────────────┘  │
│                         │                                   │
│                         ▼                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 阶段 4: Execute                                       │  │
│  │  • 调用 execute_vizql_query 工具                     │  │
│  │  • QueryExecutor 执行查询                            │  │
│  │  • 如果结果 > 10MB:                                  │  │
│  │    → 触发 FilesystemMiddleware                       │  │
│  │    → 保存到文件系统                                  │  │
│  │    → 返回文件引用                                    │  │
│  │  • 如果结果 < 10MB:                                  │  │
│  │    → 直接返回数据                                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                         │                                   │
│                         ▼                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 阶段 5: Insight (使用 LLM)                            │  │
│  │  • 调用 detect_statistics 工具                       │  │
│  │  • StatisticsDetector 分析数据                       │  │
│  │  • LLM 分析查询结果生成洞察                          │  │
│  │  • 生成可操作的建议                                  │  │
│  └──────────────────────────────────────────────────────┘  │
│                         │                                   │
│                         ▼                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 阶段 6: Replanner (使用 LLM)                          │  │
│  │  • LLM 分析当前洞察决定是否需要重规划                │  │
│  │  • 如果需要重规划:                                   │  │
│  │    1. LLM 生成 2-5 个建议的后续问题                  │  │
│  │    2. 触发 HumanInTheLoopMiddleware                  │  │
│  │    3. 暂停执行，等待用户选择                         │  │
│  │    4. 用户选择问题后:                                │  │
│  │       → 添加到 TodoListMiddleware                    │  │
│  │       → 循环回 Understanding 阶段                    │  │
│  │    5. 如果超时 5 分钟:                               │  │
│  │       → 自动执行所有建议问题                         │  │
│  │  • 如果不需要重规划:                                 │  │
│  │    → 返回最终结果                                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
 │
 │ 7. 返回结果
 ▼
API 层
 │
 │ 8. 展示给用户
 ▼
用户

┌─────────────────────────────────────────────────────────────┐
│                    中间件自动触发                            │
│                                                              │
│  • 对话 ≥ 10 轮 → SummarizationMiddleware                   │
│    → 生成对话摘要                                           │
│    → 压缩历史消息                                           │
│    → 保留数据洞察                                           │
│                                                              │
│  • 结果 > 10MB → FilesystemMiddleware                       │
│    → 保存到 data/agent_files/                               │
│    → 生成唯一文件 ID                                        │
│    → 返回文件路径                                           │
│                                                              │
│  • 工具调用错误 → PatchToolCallsMiddleware                  │
│    → 自动修复类型错误                                       │
│    → 应用默认参数值                                         │
│    → 纠正参数名拼写                                         │
│    → 记录修复日志                                           │
│                                                              │
│  • Claude 模型 → AnthropicPromptCachingMiddleware           │
│    → 缓存 Prompt                                            │
│    → 降低 90% API 成本                                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**关键流程说明**:
1. **条件执行**: Boost 阶段根据 boost_question 标志决定是否执行
2. **大文件处理**: Execute 阶段自动检测结果大小并决定存储方式
3. **重规划循环**: Replanner 可以将流程路由回 Understanding，形成迭代分析
4. **人工介入**: 重规划时暂停执行，等待用户选择要执行的问题
5. **任务队列**: 用户选择的多个问题通过 TodoListMiddleware 自动管理执行
6. **中间件透明**: 所有中间件在后台自动工作，不影响主流程

### LLM 和 RAG 使用说明

系统在多个阶段使用 LLM 和 RAG 技术：

#### LLM 使用的节点

1. **Boost Agent (可选)**
   - **作用**: 优化和增强用户问题
   - **输入**: 原始问题 + 元数据
   - **输出**: 优化后的问题
   - **模型**: 使用配置的 LLM (Claude/DeepSeek/Qwen)

2. **Understanding Agent**
   - **作用**: 理解用户意图，提取语义信息
   - **输入**: 用户问题 + 元数据
   - **输出**: QuestionUnderstanding (维度、度量、时间范围等)
   - **模型**: 使用配置的 LLM

3. **Planning Agent**
   - **作用**: 生成查询计划和任务分解
   - **输入**: QuestionUnderstanding + 元数据 + 维度层级
   - **输出**: QueryPlanningResult (查询规格、任务依赖)
   - **模型**: 使用配置的 LLM
   - **特殊**: 结合 RAG 进行字段映射

4. **Insight Agent**
   - **作用**: 分析查询结果，生成洞察
   - **输入**: 查询结果 + 统计信息
   - **输出**: InsightResult (洞察列表、建议)
   - **模型**: 使用配置的 LLM

5. **Replanner Agent**
   - **作用**: 决定是否重规划，生成后续问题
   - **输入**: 当前洞察 + 历史上下文
   - **输出**: ReplanningDecision (是否重规划、建议问题)
   - **模型**: 使用配置的 LLM

#### RAG (检索增强生成) 实现

**组件**: SemanticMapper

**功能**: 将用户提到的字段名（可能不准确）映射到实际的数据库字段名

**技术栈**:
- **向量数据库**: FAISS 或 Chroma
- **嵌入模型**: 使用 OpenAI Embeddings 或本地嵌入模型
- **索引内容**: 所有数据源字段的名称、描述、示例值

**工作流程**:
1. **索引阶段** (系统初始化时):
   ```
   数据源字段 → 生成嵌入向量 → 存储到向量数据库
   ```

2. **查询阶段** (Planning 节点):
   ```
   用户提到的字段名 → 生成查询向量 → 语义搜索 → 返回最相关的实际字段名
   ```

**示例**:
- 用户说: "销售额" → RAG 找到: "Sales Amount"
- 用户说: "地区" → RAG 找到: "Region Name"
- 用户说: "去年" → RAG 找到: "Order Date" (日期字段)

**优势**:
- 支持模糊匹配和同义词
- 支持多语言（中文问题 → 英文字段名）
- 提高字段映射准确率

#### LLM 模型选择策略

系统支持多个 LLM 提供商，通过配置灵活切换：

| 提供商 | 模型 | 适用场景 | Prompt 缓存 |
|--------|------|----------|-------------|
| Claude | claude-3-5-sonnet | 复杂推理、高质量输出 | ✓ 支持 |
| DeepSeek | deepseek-chat | 国内部署、成本优化 | ✗ 使用 Store |
| Qwen | qwen-plus | 国内部署、中文优化 | ✗ 使用 Store |
| OpenAI | gpt-4 | 通用场景 | ✗ 使用 Store |

**配置示例**:
```python
model_config = {
    "provider": "claude",  # 或 "deepseek", "qwen", "openai"
    "model_name": "claude-3-5-sonnet-20241022",
    "temperature": 0.0  # 不同节点可以有不同温度
}
```

**温度设置**:
- Boost/Understanding/Planning: 0.0 (确定性输出)
- Insight/Replanner: 0.3 (适度创造性)

## 组件和接口

### 1. DeepAgent 创建器

**职责**: 创建配置了所有中间件的 DeepAgent 实例

**接口**:
```python
def create_tableau_deep_agent(
    tools: List[Tool],
    model_config: Optional[Dict[str, Any]] = None,
    store: Optional[Store] = None
) -> CompiledGraph:
    """
    创建 Tableau Assistant 的 DeepAgent
    
    Args:
        tools: 8 个 Tableau 工具列表
        model_config: 模型配置 (provider, model_name, temperature)
        store: SQLite Store 实例
    
    Returns:
        编译后的 DeepAgent 图
    """
```

**实现细节**:
- 调用 `create_deep_agent()` 函数
- 根据 model_config 中的 provider 决定是否启用 AnthropicPromptCachingMiddleware
- 配置其他 5 个中间件的参数
- 排除 SubAgentMiddleware

### 2. 工具封装层

**职责**: 将现有组件封装为 LangChain 工具

**工具列表**:

#### 2.1 get_metadata
```python
@tool
def get_metadata(
    datasource_luid: str,
    use_cache: bool = True,
    enhance: bool = True
) -> Dict[str, Any]:
    """
    获取数据源元数据
    
    Args:
        datasource_luid: 数据源 LUID
        use_cache: 是否使用缓存
        enhance: 是否增强元数据（包含 valid_max_date）
    
    Returns:
        元数据字典
    """
```

#### 2.2 parse_date
```python
@tool
def parse_date(
    date_expression: str,
    reference_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    解析日期表达式
    
    Args:
        date_expression: 日期表达式 (如 "上个月", "2023-Q1")
        reference_date: 参考日期 (默认为今天)
    
    Returns:
        解析后的日期范围
    """
```

#### 2.3 build_vizql_query
```python
@tool
def build_vizql_query(
    query_spec: Dict[str, Any],
    metadata: Dict[str, Any]
) -> str:
    """
    构建 VizQL 查询
    
    Args:
        query_spec: 查询规格
        metadata: 元数据
    
    Returns:
        VizQL 查询字符串
    """
```

#### 2.4 execute_vizql_query
```python
@tool
def execute_vizql_query(
    vizql_query: str,
    datasource_luid: str
) -> Dict[str, Any]:
    """
    执行 VizQL 查询
    
    Args:
        vizql_query: VizQL 查询字符串
        datasource_luid: 数据源 LUID
    
    Returns:
        查询结果
    """
```

#### 2.5 semantic_map_fields
```python
@tool
def semantic_map_fields(
    field_names: List[str],
    metadata: Dict[str, Any]
) -> Dict[str, str]:
    """
    语义映射字段名
    
    Args:
        field_names: 字段名列表
        metadata: 元数据
    
    Returns:
        映射结果 {原始名称: 实际字段名}
    """
```

#### 2.6 process_query_result
```python
@tool
def process_query_result(
    query_result: Dict[str, Any],
    processing_instruction: Dict[str, Any]
) -> Dict[str, Any]:
    """
    处理查询结果
    
    Args:
        query_result: 查询结果
        processing_instruction: 处理指令
    
    Returns:
        处理后的结果
    """
```

#### 2.7 detect_statistics
```python
@tool
def detect_statistics(
    data: List[Dict[str, Any]],
    columns: List[str]
) -> Dict[str, Any]:
    """
    检测统计特征
    
    Args:
        data: 数据列表
        columns: 列名列表
    
    Returns:
        统计结果
    """
```

#### 2.8 save_large_result
```python
@tool
def save_large_result(
    data: Any,
    file_id: Optional[str] = None
) -> str:
    """
    保存大结果集到文件系统
    
    注意: 此工具由 FilesystemMiddleware 自动提供
    
    Args:
        data: 要保存的数据
        file_id: 可选的文件 ID
    
    Returns:
        文件路径
    """
```

### 3. StateGraph 节点

**职责**: 保持现有的节点实现和业务逻辑

**节点列表**:
- Boost Node: 问题优化
- Understanding Node: 问题理解
- Planning Node: 查询规划
- Execute Node: 查询执行
- Insight Node: 洞察生成
- Replanner Node: 重规划决策

**关键点**:
- 节点实现保持不变
- 节点通过工具调用组件
- 节点之间的流程控制由 StateGraph 管理

### 4. 中间件配置

#### 4.1 AnthropicPromptCachingMiddleware
```python
{
    "enabled": model_config.get("provider") == "claude",
    "cache_control": {
        "type": "ephemeral",
        "ttl": 300  # 5 分钟
    }
}
```

#### 4.2 SummarizationMiddleware
```python
{
    "trigger_threshold": 10,  # 10 轮对话后触发
    "summary_model": "claude-3-haiku",  # 使用快速模型总结
    "preserve_insights": True  # 保留洞察内容
}
```

#### 4.3 FilesystemMiddleware
```python
{
    "base_path": "data/agent_files",
    "size_threshold": 10 * 1024 * 1024,  # 10MB
    "cleanup_on_session_end": True
}
```

#### 4.4 PatchToolCallsMiddleware
```python
{
    "auto_fix_types": True,
    "auto_fix_names": True,
    "use_defaults": True,
    "log_fixes": True
}
```

#### 4.5 TodoListMiddleware
```python
{
    "max_tasks": 10,
    "auto_execute": True,
    "task_timeout": 300  # 5 分钟
}
```

#### 4.6 HumanInTheLoopMiddleware
```python
{
    "approval_required": ["replanning"],
    "timeout": 300,  # 5 分钟
    "default_action": "execute_all"  # 超时后默认执行所有
}
```

## 数据模型

### VizQLContext
```python
@dataclass
class VizQLContext:
    """运行时上下文（不可变）"""
    datasource_luid: str
    user_id: str
    session_id: str
    max_replan_rounds: int = 3
    parallel_upper_limit: int = 5
    max_retry_times: int = 3
    max_subtasks_per_round: int = 10
```

### VizQLState
```python
class VizQLState(TypedDict):
    """工作流状态"""
    question: str
    boost_question: bool
    boosted_question: Optional[str]
    understanding: Optional[QuestionUnderstanding]
    query_plan: Optional[QueryPlanningResult]
    subtask_results: List[Dict[str, Any]]
    insights: List[Dict[str, Any]]
    all_insights: List[Dict[str, Any]]
    final_report: Dict[str, Any]
    replan_count: int
    current_stage: str
    metadata: Optional[Any]
    dimension_hierarchy: Optional[Dict[str, Any]]
    statistics: Optional[Dict[str, Any]]
    visualizations: List[Dict[str, Any]]
    errors: List[Dict[str, Any]]
    warnings: List[Dict[str, Any]]
```

### ReplanningDecision
```python
class ReplanningDecision(BaseModel):
    """重规划决策"""
    should_replan: bool
    suggested_questions: List[str]  # 2-5 个建议问题
    reasoning: str
```

### TaskSelection
```python
class TaskSelection(BaseModel):
    """用户任务选择"""
    action: Literal["execute_all", "select", "modify", "decline"]
    selected_indices: Optional[List[int]]  # action="select" 时使用
    modified_questions: Optional[List[str]]  # action="modify" 时使用
```

## 正确性属性

*属性是一个特征或行为，应该在系统的所有有效执行中保持为真——本质上是关于系统应该做什么的正式陈述。属性作为人类可读规范和机器可验证正确性保证之间的桥梁。*


### 属性反思

在编写正确性属性之前，我们需要识别和消除冗余：

**识别的冗余**:
1. 需求 1.3 和 4.1 都测试 Claude 模型时启用 AnthropicPromptCachingMiddleware - 可以合并
2. 需求 1.4-1.8 都测试启用不同的中间件 - 可以合并为一个综合属性
3. 需求 3.1-3.8 都测试组件到工具的封装 - 可以合并为一个综合属性
4. 需求 2.5-2.6 都测试节点使用现有实现 - 可以合并

**合并后的属性**:
- 属性 1: 中间件配置完整性（合并 1.4-1.8, 1.9）
- 属性 2: Claude 模型缓存启用（合并 1.3, 4.1）
- 属性 3: 工具封装完整性（合并 3.1-3.8）
- 属性 4: 节点实现保持性（合并 2.5-2.6）

### 正确性属性列表

**属性 1: 中间件配置完整性**
*对于任何* DeepAgent 创建请求，创建的 Agent 应该包含且仅包含以下 6 个中间件：SummarizationMiddleware、FilesystemMiddleware、PatchToolCallsMiddleware、TodoListMiddleware、HumanInTheLoopMiddleware，以及在使用 Claude 模型时的 AnthropicPromptCachingMiddleware，并且不应包含 SubAgentMiddleware
**验证需求: 1.4, 1.5, 1.6, 1.7, 1.8, 1.9**

**属性 2: 工具配置完整性**
*对于任何* DeepAgent 创建请求，创建的 Agent 应该配置恰好 8 个工具：get_metadata、parse_date、build_vizql_query、execute_vizql_query、semantic_map_fields、process_query_result、detect_statistics、save_large_result
**验证需求: 1.2, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**

**属性 3: 工作流节点顺序保持**
*对于任何* 工作流执行，当所有节点都需要执行时，节点执行顺序应该严格遵循：Boost → Understanding → Planning → Execute → Insight → Replanner
**验证需求: 2.2**

**属性 4: Boost 节点条件跳过**
*对于任何* 工作流执行，当 boost_question 标志为 False 时，工作流应该跳过 Boost 节点并直接从 Understanding 节点开始
**验证需求: 2.3**

**属性 5: 重规划循环路由**
*对于任何* 工作流执行，当 Replanner 节点决定需要重规划时（should_replan=True），工作流应该将执行路由回 Understanding 节点
**验证需求: 2.4**

**属性 6: 组件业务逻辑保持**
*对于任何* 工具调用，工具封装前后对于相同输入应该产生相同的输出，证明业务逻辑未被改变
**验证需求: 3.9**

**属性 7: 非 Claude 模型缓存策略**
*对于任何* 非 Claude 模型配置，当系统需要缓存时，应该使用 SQLite Store 而不是 AnthropicPromptCachingMiddleware
**验证需求: 4.2**

**属性 8: 模型提供商切换支持**
*对于任何* 支持的 LLM 提供商（Claude、DeepSeek、Qwen、OpenAI），系统应该能够通过配置切换而无需修改代码
**验证需求: 4.4, 10.2**

**属性 9: 对话总结触发条件**
*对于任何* 对话会话，当消息轮数达到或超过 10 轮时，系统应该触发 SummarizationMiddleware
**验证需求: 5.1**

**属性 10: 总结内容选择性**
*对于任何* 对话总结，生成的摘要应该包含对话交流内容但不应包含 Insight Agent 生成的数据洞察内容
**验证需求: 5.5**

**属性 11: 洞察内容保留**
*对于任何* 对话总结，总结后的状态应该保留所有 Insight Agent 生成的数据洞察
**验证需求: 5.4**

**属性 12: 重规划问题数量范围**
*对于任何* 重规划决策，当 should_replan=True 时，生成的建议问题数量应该在 2 到 5 个之间（包含边界）
**验证需求: 6.1**

**属性 13: 重规划暂停机制**
*对于任何* 重规划决策，当生成建议问题后，系统应该触发 HumanInTheLoopMiddleware 暂停执行并等待用户响应
**验证需求: 6.2**

**属性 14: 任务队列管理**
*对于任何* 用户选择的问题集合，这些问题应该被添加到 TodoListMiddleware 并按顺序执行，每个问题都经过完整的工作流序列
**验证需求: 6.5, 6.6, 6.7**

**属性 15: 重规划超时默认行为**
*对于任何* 重规划交互，如果用户在 5 分钟内没有响应，系统应该自动执行所有建议的问题
**验证需求: 6.10**

**属性 16: 大文件处理阈值**
*对于任何* 查询结果，当结果大小超过 10MB 时，系统应该使用 FilesystemMiddleware 保存到磁盘而不是保存在内存中
**验证需求: 7.1**

**属性 17: 文件标识符唯一性**
*对于任何* 两次不同的文件保存操作，生成的文件标识符应该是唯一的
**验证需求: 7.2**

**属性 18: 文件系统往返一致性**
*对于任何* 保存到文件系统的数据，使用返回的文件标识符加载应该得到相同的数据
**验证需求: 7.3, 7.4**

**属性 19: 会话文件清理**
*对于任何* 用户会话，当会话终止时，与该会话关联的所有临时文件应该被删除
**验证需求: 7.5**

**属性 20: 工具调用参数类型自动修复**
*对于任何* 工具调用，当参数类型不正确但可以转换时，PatchToolCallsMiddleware 应该自动转换参数类型并成功执行工具
**验证需求: 8.1**

**属性 21: 工具调用缺失参数默认值**
*对于任何* 工具调用，当缺少非必需参数时，PatchToolCallsMiddleware 应该应用默认值并成功执行工具
**验证需求: 8.2**

**属性 22: 工具调用参数名称纠正**
*对于任何* 工具调用，当参数名称拼写错误但可以识别时，PatchToolCallsMiddleware 应该自动纠正参数名称并成功执行工具
**验证需求: 8.3**

**属性 23: 工具调用修复日志记录**
*对于任何* 被自动修复的工具调用，系统应该记录修复详情到日志中
**验证需求: 8.4**

**属性 24: API 向后兼容性**
*对于任何* 前端 API 请求，集成 DeepAgents 后的响应格式应该与集成前保持一致
**验证需求: 10.3**

## 错误处理

### 错误类型

1. **配置错误**
   - 缺少必需的配置参数
   - 无效的模型提供商
   - 无效的中间件配置

2. **工具调用错误**
   - 工具不存在
   - 参数验证失败
   - 工具执行异常

3. **工作流错误**
   - 节点执行失败
   - 状态转换错误
   - 超时错误

4. **存储错误**
   - 文件系统访问失败
   - SQLite 数据库错误
   - 缓存读写失败

5. **中间件错误**
   - 中间件初始化失败
   - 中间件执行异常
   - 中间件配置错误

### 错误处理策略

#### 1. 配置错误处理
```python
try:
    agent = create_tableau_deep_agent(tools, model_config, store)
except ConfigurationError as e:
    logger.error(f"配置错误: {e}")
    # 使用默认配置或返回错误响应
    raise HTTPException(status_code=400, detail=str(e))
```

#### 2. 工具调用错误处理
```python
# PatchToolCallsMiddleware 会自动处理大部分工具调用错误
# 对于无法自动修复的错误，返回清晰的错误消息
try:
    result = tool.invoke(params)
except ToolExecutionError as e:
    logger.error(f"工具执行失败: {e}")
    return {
        "error": {
            "type": "tool_execution_failed",
            "message": str(e),
            "tool_name": tool.name,
            "params": params
        }
    }
```

#### 3. 工作流错误处理
```python
# 节点级别的错误处理
def node_with_error_handling(state, runtime):
    try:
        return node_function(state, runtime)
    except Exception as e:
        logger.error(f"节点执行失败: {e}")
        return {
            "error": {
                "type": "node_execution_failed",
                "message": str(e),
                "node_name": node_function.__name__
            },
            "current_stage": "error"
        }
```

#### 4. 存储错误处理
```python
# 文件系统错误处理
try:
    file_path = filesystem_middleware.save(data, file_id)
except FilesystemError as e:
    logger.error(f"文件保存失败: {e}")
    # 降级到内存存储
    return {"data": data, "stored_in_memory": True}

# SQLite 错误处理
try:
    store.put(namespace, key, value)
except SQLiteError as e:
    logger.error(f"存储失败: {e}")
    # 使用内存缓存作为后备
    memory_cache[key] = value
```

#### 5. 中间件错误处理
```python
# 中间件初始化错误
try:
    middleware = SummarizationMiddleware(config)
except MiddlewareInitError as e:
    logger.warning(f"中间件初始化失败: {e}")
    # 禁用该中间件并继续
    middleware = None

# 中间件执行错误
try:
    result = middleware.process(state)
except MiddlewareExecutionError as e:
    logger.error(f"中间件执行失败: {e}")
    # 跳过该中间件并继续工作流
    result = state
```

### 错误恢复机制

1. **重试机制**: 对于临时性错误（网络超时、API 限流），自动重试最多 3 次
2. **降级策略**: 当某个功能不可用时，使用简化版本或跳过该功能
3. **错误隔离**: 单个节点或中间件的错误不应导致整个工作流失败
4. **用户通知**: 对于影响用户体验的错误，通过 API 返回清晰的错误消息

## 测试策略

### 单元测试

单元测试覆盖具体的功能点和边界情况：

1. **DeepAgent 创建测试**
   - 测试使用 Claude 模型时启用 AnthropicPromptCachingMiddleware
   - 测试使用非 Claude 模型时不启用 AnthropicPromptCachingMiddleware
   - 测试所有 6 个必需中间件都被配置
   - 测试 SubAgentMiddleware 被排除

2. **工具封装测试**
   - 测试每个工具的 @tool 装饰器
   - 测试每个工具的 docstring 完整性
   - 测试工具参数验证

3. **StateGraph 测试**
   - 测试节点定义保持不变
   - 测试 boost_question=False 时跳过 Boost 节点
   - 测试重规划时路由回 Understanding 节点

4. **中间件配置测试**
   - 测试 SummarizationMiddleware 在 10 轮对话后触发
   - 测试 FilesystemMiddleware 在结果 > 10MB 时触发
   - 测试 HumanInTheLoopMiddleware 在重规划时暂停
   - 测试 TodoListMiddleware 管理任务队列

5. **错误处理测试**
   - 测试工具调用参数类型错误的自动修复
   - 测试工具调用缺失参数的默认值应用
   - 测试工具调用参数名称拼写错误的纠正
   - 测试无法修复的错误返回清晰错误消息

### 属性测试

属性测试验证系统在各种输入下的通用正确性：

1. **中间件配置属性测试**
   - 使用 Hypothesis 生成随机模型配置
   - 验证属性 1: 中间件配置完整性
   - 验证属性 2: 工具配置完整性

2. **工作流执行属性测试**
   - 生成随机的工作流输入（不同的 boost_question 值）
   - 验证属性 3: 工作流节点顺序保持
   - 验证属性 4: Boost 节点条件跳过
   - 验证属性 5: 重规划循环路由

3. **组件封装属性测试**
   - 生成随机的组件输入
   - 验证属性 6: 组件业务逻辑保持（封装前后输出一致）

4. **缓存策略属性测试**
   - 生成随机的模型配置（Claude 和非 Claude）
   - 验证属性 7: 非 Claude 模型缓存策略
   - 验证属性 8: 模型提供商切换支持

5. **对话总结属性测试**
   - 生成随机长度的对话历史
   - 验证属性 9: 对话总结触发条件
   - 验证属性 10: 总结内容选择性
   - 验证属性 11: 洞察内容保留

6. **重规划属性测试**
   - 生成随机的重规划决策
   - 验证属性 12: 重规划问题数量范围
   - 验证属性 13: 重规划暂停机制
   - 验证属性 14: 任务队列管理
   - 验证属性 15: 重规划超时默认行为

7. **文件系统属性测试**
   - 生成随机大小的数据
   - 验证属性 16: 大文件处理阈值
   - 验证属性 17: 文件标识符唯一性
   - 验证属性 18: 文件系统往返一致性
   - 验证属性 19: 会话文件清理

8. **工具调用修复属性测试**
   - 生成随机的错误工具调用（类型错误、缺失参数、拼写错误）
   - 验证属性 20: 工具调用参数类型自动修复
   - 验证属性 21: 工具调用缺失参数默认值
   - 验证属性 22: 工具调用参数名称纠正
   - 验证属性 23: 工具调用修复日志记录

9. **API 兼容性属性测试**
   - 生成随机的 API 请求
   - 验证属性 24: API 向后兼容性

### 属性测试库选择

使用 **Hypothesis** 作为 Python 的属性测试库：

```python
from hypothesis import given, strategies as st
from hypothesis import settings

# 配置每个属性测试运行至少 100 次
@settings(max_examples=100)
@given(
    model_config=st.fixed_dictionaries({
        'provider': st.sampled_from(['claude', 'deepseek', 'qwen', 'openai']),
        'model_name': st.text(min_size=1),
        'temperature': st.floats(min_value=0.0, max_value=1.0)
    })
)
def test_middleware_configuration_completeness(model_config):
    """
    属性测试: 中间件配置完整性
    
    **Feature: deepagents-integration, Property 1: 中间件配置完整性**
    """
    agent = create_tableau_deep_agent(tools=[], model_config=model_config)
    
    # 验证必需的中间件
    required_middlewares = {
        'SummarizationMiddleware',
        'FilesystemMiddleware',
        'PatchToolCallsMiddleware',
        'TodoListMiddleware',
        'HumanInTheLoopMiddleware'
    }
    
    # 如果是 Claude 模型，还应包含 AnthropicPromptCachingMiddleware
    if model_config['provider'] == 'claude':
        required_middlewares.add('AnthropicPromptCachingMiddleware')
    
    # 获取实际配置的中间件
    actual_middlewares = {m.__class__.__name__ for m in agent.middlewares}
    
    # 验证包含所有必需中间件
    assert required_middlewares.issubset(actual_middlewares)
    
    # 验证不包含 SubAgentMiddleware
    assert 'SubAgentMiddleware' not in actual_middlewares
```

### 集成测试

集成测试验证组件之间的交互：

1. **端到端工作流测试**
   - 测试完整的查询流程（从 API 请求到最终响应）
   - 测试重规划流程（包括用户交互）
   - 测试大结果集处理流程

2. **中间件集成测试**
   - 测试多个中间件协同工作
   - 测试中间件与 StateGraph 的集成
   - 测试中间件与 Store 的集成

3. **存储集成测试**
   - 测试 SQLite Store 的读写
   - 测试文件系统的读写
   - 测试缓存的命中和失效

### 测试覆盖率目标

- 单元测试覆盖率: ≥ 80%
- 属性测试覆盖所有 24 个正确性属性
- 集成测试覆盖所有主要工作流路径

## 实施计划

### 阶段 1: 基础设施准备（1-2 天）

1. 安装 DeepAgents 依赖
2. 创建 DeepAgent 创建器模块
3. 配置 SQLite Store
4. 设置测试框架（Hypothesis）

### 阶段 2: 工具封装（2-3 天）

1. 封装 8 个 Tableau 组件为 LangChain 工具
2. 编写工具的单元测试
3. 验证工具的业务逻辑保持不变

### 阶段 3: 中间件集成（3-4 天）

1. 配置 6 个 DeepAgents 中间件
2. 集成中间件到 DeepAgent 创建器
3. 编写中间件的单元测试和属性测试

### 阶段 4: StateGraph 适配（2-3 天）

1. 修改 StateGraph 以使用 DeepAgent
2. 保持现有节点实现不变
3. 编写工作流的单元测试和属性测试

### 阶段 5: 重规划功能实现（3-4 天）

1. 实现 Replanner 节点的问题生成逻辑
2. 集成 HumanInTheLoopMiddleware
3. 集成 TodoListMiddleware
4. 编写重规划的单元测试和属性测试

### 阶段 6: 测试和优化（3-4 天）

1. 运行所有单元测试和属性测试
2. 运行集成测试
3. 性能测试和优化
4. 修复发现的问题

### 阶段 7: 文档和部署（1-2 天）

1. 更新 API 文档
2. 编写部署指南
3. 准备发布说明

**总计**: 15-22 天

## 风险和缓解措施

### 风险 1: DeepAgents API 变更

**描述**: DeepAgents 是一个相对较新的框架，API 可能会变更

**影响**: 高

**缓解措施**:
- 锁定 DeepAgents 版本
- 创建适配器层隔离 DeepAgents API
- 定期关注 DeepAgents 更新

### 风险 2: 性能下降

**描述**: 引入中间件可能增加延迟

**影响**: 中

**缓解措施**:
- 进行性能基准测试
- 优化中间件配置
- 使用 Prompt 缓存降低 LLM 调用成本

### 风险 3: 兼容性问题

**描述**: 新旧代码可能存在兼容性问题

**影响**: 中

**缓解措施**:
- 保持 API 向后兼容
- 编写全面的集成测试
- 使用特性开关逐步迁移

### 风险 4: 测试覆盖不足

**描述**: 属性测试可能无法覆盖所有边界情况

**影响**: 中

**缓解措施**:
- 结合单元测试和属性测试
- 使用代码覆盖率工具
- 进行人工代码审查

### 风险 5: 用户体验变化

**描述**: 重规划功能可能改变用户交互流程

**影响**: 低

**缓解措施**:
- 提供清晰的用户指引
- 设置合理的超时默认行为
- 收集用户反馈并迭代

## 附录

### A. DeepAgents 中间件参考

#### AnthropicPromptCachingMiddleware
- **功能**: 缓存 Prompt 以降低 API 成本
- **适用模型**: Claude 系列
- **成本节省**: 约 90%
- **配置**: cache_control, ttl

#### SummarizationMiddleware
- **功能**: 自动总结长对话历史
- **触发条件**: 消息轮数 ≥ 阈值
- **配置**: trigger_threshold, summary_model

#### FilesystemMiddleware
- **功能**: 自动处理大文件
- **触发条件**: 数据大小 ≥ 阈值
- **配置**: base_path, size_threshold

#### PatchToolCallsMiddleware
- **功能**: 自动修复工具调用错误
- **修复类型**: 类型转换、默认值、名称纠正
- **配置**: auto_fix_types, auto_fix_names, use_defaults

#### TodoListMiddleware
- **功能**: 管理任务队列
- **特性**: 自动执行、依赖管理
- **配置**: max_tasks, auto_execute

#### HumanInTheLoopMiddleware
- **功能**: 暂停执行等待用户输入
- **触发点**: 重规划决策
- **配置**: approval_required, timeout, default_action

### B. 工具接口规范

所有工具必须遵循以下规范：

1. 使用 `@tool` 装饰器
2. 提供完整的 docstring（包含 Args 和 Returns）
3. 使用类型注解
4. 返回 JSON 可序列化的数据
5. 处理异常并返回错误信息

示例：
```python
from langchain_core.tools import tool
from typing import Dict, Any

@tool
def example_tool(param1: str, param2: int = 0) -> Dict[str, Any]:
    """
    工具描述
    
    Args:
        param1: 参数1描述
        param2: 参数2描述（可选，默认0）
    
    Returns:
        结果字典
    """
    try:
        # 工具逻辑
        result = {"success": True, "data": ...}
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### C. 测试数据生成策略

使用 Hypothesis 的策略组合生成测试数据：

```python
from hypothesis import strategies as st

# 模型配置策略
model_config_strategy = st.fixed_dictionaries({
    'provider': st.sampled_from(['claude', 'deepseek', 'qwen', 'openai']),
    'model_name': st.text(min_size=1, max_size=50),
    'temperature': st.floats(min_value=0.0, max_value=1.0)
})

# 查询输入策略
query_input_strategy = st.fixed_dictionaries({
    'question': st.text(min_size=10, max_size=200),
    'boost_question': st.booleans()
})

# 对话历史策略
conversation_history_strategy = st.lists(
    st.fixed_dictionaries({
        'role': st.sampled_from(['user', 'assistant']),
        'content': st.text(min_size=10, max_size=500)
    }),
    min_size=0,
    max_size=20
)

# 数据大小策略
data_size_strategy = st.integers(min_value=0, max_value=20 * 1024 * 1024)  # 0-20MB

# 重规划决策策略
replan_decision_strategy = st.fixed_dictionaries({
    'should_replan': st.booleans(),
    'suggested_questions': st.lists(
        st.text(min_size=10, max_size=100),
        min_size=2,
        max_size=5
    ),
    'reasoning': st.text(min_size=10, max_size=200)
})
```

### D. 性能基准

集成前后的性能对比目标：

| 指标 | 集成前 | 集成后目标 | 改进 |
|------|--------|-----------|------|
| 平均查询响应时间 | 5.0s | ≤ 3.5s | -30% |
| Prompt 缓存命中率（Claude） | 0% | ≥ 60% | +60% |
| 代码行数 | 10000 | ≤ 8000 | -20% |
| 自定义中间件代码 | 3000 | ≤ 2100 | -30% |
| 测试覆盖率 | 75% | ≥ 80% | +5% |

### E. 参考资料

1. [DeepAgents 官方文档](https://github.com/langchain-ai/deepagents)
2. [LangGraph 文档](https://langchain-ai.github.io/langgraph/)
3. [Hypothesis 文档](https://hypothesis.readthedocs.io/)
4. [Property-Based Testing 最佳实践](https://hypothesis.works/articles/what-is-property-based-testing/)
