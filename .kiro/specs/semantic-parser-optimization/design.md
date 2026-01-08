# 语义解析器优化设计文档

## 概述

本设计文档描述 SemanticParser 的 vNext 架构优化，核心目标是：
1. **降低 Token 成本**：Step1 prompt 从 O(|fields|) 降到 O(k)
2. **减少 LLM 调用**：模板化常见计算，规则化错误处理
3. **提升准确率**：候选约束 + 前置校验 + 统一澄清

## 设计原则（GPT-5.2 审查补充）

### 数据结构使用规范

为避免实现时的混乱，明确以下规范：

| 场景 | 使用类型 | 原因 |
|------|---------|------|
| LLM 输出承载结构 | `Pydantic BaseModel` | 需要 JSON schema 校验、序列化、错误提示 |
| 内部数据传递 | `Pydantic BaseModel` 或 `@dataclass` | 根据是否需要校验决定 |
| 纯配置/常量 | `@dataclass` | 简单、无校验需求 |
| State 中的字段 | 基本类型 / 可 JSON 化结构 | 支持 checkpoint 和持久化 |

**关键约束**：
- `Step1Output`、`Step2Output`、`ClarificationRequest` 等 LLM 输出结构 **必须使用 Pydantic**
- `FieldReference`、`FieldCandidate` 等需要 JSON 序列化的结构 **建议使用 Pydantic**
- `SemanticParserMetrics` 等纯内部指标 **可以使用 @dataclass**
- **State 中不应存放复杂对象**（如 `SemanticParserMetrics` 实例），只存基本类型/可 JSON 化结构
- **Metrics 存放策略**：metrics 作为 runtime 对象在组件间传递，不进入 State；在 subgraph 出口处序列化为 `dict[str, int|float|bool|str]` 后输出到日志/监控系统

### 字段来源单一事实原则

为避免字段在不同段落出现漂移，明确以下规范：

| 字段 | 单一事实来源 | 说明 |
|------|-------------|------|
| `canonical_question` | `PreprocessResult` | Preprocess 产出，Step1 只引用 |
| `time_context` | `PreprocessResult` | Preprocess 产出，Step1 只引用 |
| `memory_slots` | `PreprocessResult` | Preprocess 产出，Step1 只引用 |
| `schema_candidates` | `SchemaLinkingResult` | Schema Linking 产出，Step1 只引用 |
| `intent_type` | `Step1Output.intent.type` | Step1 产出，扁平化到 state |

**关键约束**：
- Step1 **不产出** `canonical_question`、`time_context`、`memory_slots`，只引用
- 这些字段在 state 中只有一份，避免重复定义

### 阈值层级关系

为避免阈值冲突，明确以下层级关系：

```
置信度阈值层级（从严到松）：
┌─────────────────────────────────────────────────────────────┐
│ MapFields fast-path: confidence ≥ 0.9                       │
│   → 直接使用候选，跳过 RAG/LLM                               │
├─────────────────────────────────────────────────────────────┤
│ Schema Linking 正常路径: 0.5 ≤ confidence < 0.9             │
│   → 使用候选，但可能需要 fallback 验证                       │
├─────────────────────────────────────────────────────────────┤
│ Schema Linking 回退: confidence < 0.5                       │
│   → 触发 FieldMapper fallback                               │
├─────────────────────────────────────────────────────────────┤
│ 澄清触发: confidence < 0.7 且无法自动修复                    │
│   → 触发 ClarificationRequest                               │
└─────────────────────────────────────────────────────────────┘
```

### 术语澄清：dimensions 的多重含义

为避免命名冲突，明确以下术语区分：

| 术语 | 上下文 | 含义 | 示例 |
|------|--------|------|------|
| `query_dimensions` | Step1Output.where.dimensions | 查询中的维度字段列表 | `["Region", "Month"]` |
| `table_calc.dimensions` | TableCalcSpecification.dimensions | 表计算的分区/寻址字段 | `[{"fieldCaption": "Region"}]` |
| `partition_by` | 内部推断变量 | 分区维度（计算范围） | `["Region"]` |
| `addressing` | 内部推断变量 | 寻址维度（计算方向） | `["Month"]` |

**关键约束**：
- 约束 `partition_by ⊆ query_dimensions` 表示：分区维度必须是查询维度的子集
- `table_calc.dimensions` 的语义取决于 `tableCalcType`（见 4.4 节 TableCalcOutput 注释）
- 代码中应使用 `query_dimensions` 而非 `dimensions` 来引用查询维度，避免歧义

### 对外契约定义表（Table Calc）

**⚠️ 单一事实来源**：以下表格定义了 `tableCalcType` 与 `dimensions`/`restartEvery` 的唯一映射规则。

| tableCalcType | dimensions 语义 | restartEvery 支持 | 分区表达方式 | 示例 |
|---------------|-----------------|-------------------|--------------|------|
| `PERCENT_OF_TOTAL` | partitioning | ❌ | 只能用 dimensions | `dimensions: [Region]` |
| `RANK` | partitioning | ❌ | 只能用 dimensions | `dimensions: [Region]` |
| `PERCENTILE` | partitioning | ❌ | 只能用 dimensions | `dimensions: [Region]` |
| `MOVING_CALCULATION` | partitioning | ❌ | 只能用 dimensions | `dimensions: [Region]` |
| `DIFFERENCE_FROM` | partitioning | ❌ | 只能用 dimensions | `dimensions: [Month]` |
| `PERCENT_DIFFERENCE_FROM` | partitioning | ❌ | 只能用 dimensions | `dimensions: [Month]` |
| `RUNNING_TOTAL` | 留空 | ✅ | **统一用 restartEvery** | `dimensions: [], restartEvery: Region` |
| `CUSTOM` | addressing | ✅ | 可用 restartEvery 或 dimensions | 视场景而定 |
| `NESTED` | addressing | ✅ | 可用 restartEvery 或 dimensions | 视场景而定 |

**设计决策（RUNNING_TOTAL）**：
- 虽然 RUNNING_TOTAL 同时支持 `restartEvery` 和 `dimensions` 两种分区表达方式
- **本系统统一采用 `restartEvery` 方式**，`dimensions` 留空
- 这样可以避免"双口径"导致的实现分叉和验收困难

**降级规则（硬规则）**：
| 场景 | 处理方式 |
|------|---------|
| `partition_by` 为空 | `restartEvery: null`，全局累计 |
| `partition_by` 单字段 | `restartEvery: {fieldCaption: partition_by[0]}` |
| `partition_by` 多字段 | **降级到 Step2 LLM fallback**（restartEvery 只支持单字段） |

**内部 IR 到 OpenAPI 映射规则**：
```python
def map_partition_to_api(calc_type: str, partition_by: list[str]) -> dict:
    """内部 partition_by 到 OpenAPI 字段的映射"""
    if calc_type == "RUNNING_TOTAL":
        # RUNNING_TOTAL 统一使用 restartEvery
        return {
            "dimensions": [],
            "restartEvery": {"fieldCaption": partition_by[0]} if partition_by else None
        }
    else:
        # 其他类型使用 dimensions
        return {
            "dimensions": [{"fieldCaption": f} for f in partition_by]
        }
```

## GPT-5.2 代码审查结论

> "这份 vNext 升级方案在架构方向上非常贴合主流 AI/BI 的'RAG Grounding + 受约束 IR + Validator + 执行反馈'范式，性能与稳定性上限都很高。"

### 与主流 AI/BI 架构对比

| 范式 | 说明 | vNext 对齐度 |
|------|------|-------------|
| 受控 IR → 规划 → 执行器 | LLM 只负责"提案"，确定性层做"把关" | ✓ 完全对齐 |
| RAG Grounding + 强约束生成 | 先检索候选，再从候选中"选择" | ✓ Schema Linking 前置 |
| Execution-guided / Feedback loop | 执行错误回流到纠错器，规则优先 | ✓ ReAct 规则化 |

### 当前代码的关键短板（需先修）

| 问题 | 影响 | 优先级 |
|------|------|--------|
| 子图入口契约不统一 | 路由与状态字段"各说各话"，降低可维护性 | P0 |
| Step1/Step2 解析失败不进 ReAct | 最强的自愈器覆盖不到高频问题 | P0 |
| middleware/重试体系未闭环 | 工具级重试/落盘能力可能失效 | P0 |
| History/Schema token 无硬性上限 | token 成本与幻觉放大器 | P0 |

### 技术路线图

```
Phase 0（1 周）：工程债务清理
├── 统一入口与状态契约
├── 打通 Step1/2 解析失败的纠错链路
├── Pipeline 贯通 middleware
├── token 硬性上限保护
└── 基础可观测性

Phase 1（1-2 周）：Preprocess + Schema Linking
├── 时间解析、canonical、slots、terms
└── 问题级 + 实体级检索 + 缓存

Phase 2（2-3 周）：Step1 重构 + 计算规划
├── Step1 受约束生成（只从候选选字段）← 核心性能开关
├── ComputationPlanner 模板化
└── Validator 前置校验/规则修复

Phase 3（2-3 周）：性能优化
├── 批量 embedding + 多级缓存
├── 异步 Reranker + 超时降级
└── FAISS 懒加载/预热

Phase 4（持续迭代）：可观测性 + 收尾
├── Golden set 回归与指标驱动调参
└── 规则化错误修复扩充
```

## 1. 架构概览

### 1.1 当前架构 vs vNext 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    当前架构（问题）                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  START ──→ step1 ──→ step2? ──→ pipeline ──→ react? ──→ END   │
│              │                      │            │              │
│              │                      │            │              │
│         全量字段注入            职责重叠      LLM 处理所有错误   │
│         O(|fields|)            与 Step1       包括可规则化的    │
│         token 高、幻觉多        字段识别重复                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    vNext 架构（优化）                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  START ──→ preprocess ──→ schema_linking ──→ step1             │
│               │                 │               │               │
│          0 LLM 调用        RAG 检索         受约束生成          │
│          时间解析          top-k 候选       O(k) token          │
│          规范化            缓存复用                             │
│                                                                 │
│         ──→ computation_planner ──→ validator ──→ pipeline     │
│                    │                    │             │         │
│               模板优先              强校验         瘦身后       │
│               LLM 兜底              规则修复       只做落地     │
│                                     统一澄清                    │
│                                                                 │
│         ──→ react ──→ END                                      │
│               │                                                 │
│          规则分类器优先                                         │
│          LLM 只处理长尾                                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 六层架构数据流

```
┌─────────────────────────────────────────────────────────────────┐
│              SemanticParser vNext 数据流                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  用户问题: "各地区上个月销售额占比是多少？"                      │
│      │                                                          │
│      v                                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Layer 1: 预处理层 (Deterministic, 0 LLM)                │   │
│  │                                                         │   │
│  │   normalize() ──→ 全角半角归一、空白归一                │   │
│  │   extract_time() ──→ "上个月" → [2024-12-01, 2024-12-31]│   │
│  │   extract_slots() ──→ 从历史提取已确认项                │   │
│  │   build_canonical() ──→ "time:last_month 各地区销售额占比"│  │
│  │                                                         │   │
│  │   输出: canonical_question + time_context + memory_slots│   │
│  └─────────────────────────────────────────────────────────┘   │
│      │                                                          │
│      v                                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Layer 2: Schema Linking 层 (RAG 优先, 可并行)           │   │
│  │                                                         │   │
│  │   ┌─────────────────┐    ┌─────────────────┐           │   │
│  │   │ 问题级检索      │    │ 实体级检索      │           │   │
│  │   │ 整句 query      │    │ "地区"、"销售额" │           │   │
│  │   │ top-N 相关字段  │    │ 并行检索候选    │           │   │
│  │   └────────┬────────┘    └────────┬────────┘           │   │
│  │            │                      │                     │   │
│  │            └──────────┬───────────┘                     │   │
│  │                       v                                 │   │
│  │              合并去重 + 缓存                            │   │
│  │                                                         │   │
│  │   输出: schema_candidates (维度/度量分桶, 含样例值/层级)│   │
│  │   约束: 后续模型只能从候选集合中选择                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│      │                                                          │
│      v                                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Layer 3: 语义解析层 (1 次主模型调用为主)                │   │
│  │                                                         │   │
│  │   输入: canonical_question + slots + time_context       │   │
│  │        + schema_candidates (top-k, 非全量)              │   │
│  │                                                         │   │
│  │   Step1 重构: 从候选集中选择字段                        │   │
│  │   - 字段引用用候选 ID/规范名                            │   │
│  │   - prompt token 从 O(|fields|) 降到 O(k)               │   │
│  │                                                         │   │
│  │   输出: 受约束的语义计划 (Step1Output)                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│      │                                                          │
│      v                                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Layer 4: 计算规划层 (模板优先, LLM 兜底)                │   │
│  │                                                         │   │
│  │   how_type == SIMPLE? ──→ 跳过                          │   │
│  │         │                                               │   │
│  │         v                                               │   │
│  │   ┌─────────────────────────────────────────────────┐   │   │
│  │   │ 计算模板库                                      │   │   │
│  │   │ - 占比 → PERCENT_OF_TOTAL (表计算)              │   │   │
│  │   │ - 同比 → PERCENT_DIFFERENCE (表计算)            │   │   │
│  │   │ - 排名 → RANK (表计算)                          │   │   │
│  │   │ - 每客户 → LOD_FIXED (粒度改变)                 │   │   │
│  │   └─────────────────────────────────────────────────┘   │   │
│  │         │                                               │   │
│  │    模板匹配? ──→ 是 ──→ 生成 Computation                │   │
│  │         │                                               │   │
│  │         v 否                                            │   │
│  │   Step2 LLM Fallback (仅长尾场景)                       │   │
│  │                                                         │   │
│  │   输出: computations (LOD 在前, 表计算在后)             │   │
│  └─────────────────────────────────────────────────────────┘   │
│      │                                                          │
│      v                                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Layer 5: 后处理与校验层 (Deterministic + 小型修复器)    │   │
│  │                                                         │   │
│  │   Validator 强校验:                                     │   │
│  │   - 字段存在性                                          │   │
│  │   - 类型匹配                                            │   │
│  │   - 聚合合法性                                          │   │
│  │   - partition_by ⊆ query_dimensions                     │   │
│  │   - 字段去重                                            │   │
│  │         │                                               │   │
│  │    校验通过? ──→ 是 ──→ 继续执行                        │   │
│  │         │                                               │   │
│  │         v 否                                            │   │
│  │   可规则修复? ──→ 是 ──→ 自动修复后继续                 │   │
│  │         │                                               │   │
│  │         v 否                                            │   │
│  │   触发 ClarificationRequest (统一澄清协议)              │   │
│  └─────────────────────────────────────────────────────────┘   │
│      │                                                          │
│      v                                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Layer 6: 执行层 (Pipeline 保留但"更瘦")                 │   │
│  │                                                         │   │
│  │   MapFields: 输入已是候选引用, 只做校验+落地            │   │
│  │   ResolveFilterValues: 先候选值检索, 再决定是否澄清     │   │
│  │   Build → Execute                                       │   │
│  │         │                                               │   │
│  │    执行成功? ──→ 是 ──→ 返回结果                        │   │
│  │         │                                               │   │
│  │         v 否                                            │   │
│  │   ReAct 规则化:                                         │   │
│  │   - 先走 deterministic error classifier                 │   │
│  │   - FIELD_NOT_FOUND → 快速失败或转澄清                  │   │
│  │   - PERMISSION_DENIED → 快速失败                        │   │
│  │   - TYPE_MISMATCH → 尝试规则修复                        │   │
│  │   - 只把"长尾不可归因"交给 LLM ReAct                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│      │                                                          │
│      v                                                          │
│   返回结果 / 澄清请求 / 错误信息                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 性能对比

| 指标 | 当前值 | 目标值 | 优化手段 |
|------|--------|--------|----------|
| Step1 prompt token | O(\|fields\|) | O(k), k≤50 | Schema Linking 前置 |
| 平均 LLM 调用次数 | 2-3 次/请求 | ≤ 1.5 次/请求 | 模板化 + 缓存 |
| P95 延迟 | ~3s | ≤ 2s | 减少 LLM 调用 |
| 精确匹配复杂度 | O(n) | O(1) | 哈希索引 |
| 缓存命中率 | 0% | ≥ 30% | 两级缓存 |

## 2. Phase 0: 工程债务清理设计

> **重要**：以下设计是实施 vNext 功能的前置条件，必须优先完成。

### 2.0.1 统一语义解析入口与状态契约

**问题**：`factory.py` 直接挂 `create_semantic_parser_subgraph()`，但主工作流路由期待 `semantic_parser_node` 的扁平化输出。

**解决方案**：

```python
# 方案：保留 subgraph，但在出口处统一扁平化

class SemanticParserState(VizQLState):
    """统一状态定义
    
    ⚠️ State 序列化原则（支持 checkpoint/持久化/回放）：
    - State 中只存可 JSON 化的基本类型或结构
    - 复杂对象（如 Pydantic BaseModel）在存入 State 前必须调用 .model_dump()
    - 从 State 读取后需要重新构造对象
    
    字段类型约定：
    - 基本类型：str, int, float, bool, None
    - 容器类型：list[基本类型], dict[str, 基本类型]
    - 嵌套结构：dict（已序列化的 Pydantic 对象）
    """
    
    # 核心输出（扁平化，供主工作流路由消费）
    intent_type: str | None = None  # IntentType.value，非枚举对象
    is_analysis_question: bool = False
    
    # 内部状态（存储为 dict，非 Pydantic 对象）
    # 写入时：state.step1_output = step1_output.model_dump()
    # 读取时：Step1Output.model_validate(state.step1_output)
    step1_output: dict | None = None
    step2_output: dict | None = None
    preprocess_result: dict | None = None
    schema_candidates: dict | None = None
    
    # 错误状态（基本类型）
    step1_parse_error: str | None = None
    step2_parse_error: str | None = None
    pipeline_error: str | None = None
    
    # 重试计数（基本类型）
    # ⚠️ 命名约定：parse_retry 表示格式解析重试，semantic_retry 表示语义重试
    parse_retry_count: int = 0
    semantic_retry_count: int = 0

def _flatten_output(state: SemanticParserState) -> SemanticParserState:
    """在 subgraph 出口处统一扁平化"""
    if state.step1_output:
        # 从 dict 重构对象以获取字段
        step1 = Step1Output.model_validate(state.step1_output)
        state.intent_type = step1.intent.type.value  # 存储枚举值，非枚举对象
        state.is_analysis_question = (
            step1.intent.type == IntentType.DATA_QUERY
        )
    return state

# 在 subgraph 的 END 节点前调用 _flatten_output
```

**State 序列化示例**：
```python
# 写入 State（Pydantic → dict）
step1_output = Step1Output(...)
state.step1_output = step1_output.model_dump()

# 读取 State（dict → Pydantic）
step1_output = Step1Output.model_validate(state.step1_output)
```

**文件改动**：
- `state.py`：统一状态定义，所有字段使用可 JSON 化类型
- `subgraph.py`：在出口处调用 `_flatten_output`
- `node.py`：删除重复的扁平化逻辑
- `orchestration/workflow/routes.py`：统一消费扁平化字段

### 2.0.2 让 ReAct 覆盖 Step1/Step2 的解析失败

**问题**：路由在遇到 `pipeline_error` 时会直接结束，ReAct 覆盖不到 JSON 解析失败。

**解决方案**：

```python
# 在 subgraph.py 的路由逻辑中

def route_after_step1(state: SemanticParserState) -> str:
    """Step1 后的路由"""
    
    # 新增：解析失败也进入 ReAct
    if state.step1_parse_error:
        state.react_error_context = ReactErrorContext(
            error_type="STEP1_PARSE_ERROR",
            error_message=state.step1_parse_error,
            step="step1",
            can_retry=True,
        )
        return "react_error_handler"
    
    # 原有逻辑...
    if state.step1_output.intent.type != IntentType.DATA_QUERY:
        return "exit"  # 统一使用 "exit" 作为终止路由目标
    ...

# ReAct 错误处理器增加对解析失败的处理
class ReactErrorHandler:
    def handle(self, state: SemanticParserState) -> ReactDecision:
        error_context = state.react_error_context
        
        # 新增：解析失败的处理
        if error_context.error_type == "STEP1_PARSE_ERROR":
            if state.retry_count < MAX_RETRIES:
                return ReactDecision(
                    action=ReactAction.RETRY,
                    guidance="请严格按照 JSON 格式输出，确保所有字段都有值。",
                )
            else:
                return ReactDecision(action=ReactAction.ABORT)
        
        # 原有逻辑...
```

**文件改动**：
- `subgraph.py`：路由逻辑增加解析失败分支
- `state.py`：新增 `step1_parse_error`、`step2_parse_error` 字段
- `components/react_error_handler.py`：增加解析失败处理

### 2.0.3 Pipeline 贯通 middleware 能力

**问题**：`QueryPipeline` 多处直接调用 `map_fields_async/execute_query_async`，绕过 middleware。

**解决方案**：

```python
# 在 query_pipeline.py 中

class QueryPipeline:
    def __init__(self, middleware_runner: MiddlewareRunner | None = None):
        self.middleware_runner = middleware_runner or get_default_middleware_runner()
    
    async def _map_fields(self, state: PipelineState) -> MappedQuery:
        """通过 middleware 调用 map_fields"""
        return await self.middleware_runner.run(
            tool_name="map_fields",
            tool_fn=map_fields_async,
            input=state.semantic_query,
            config=state.config,
        )
    
    async def _execute_query(self, state: PipelineState) -> QueryResult:
        """通过 middleware 调用 execute_query"""
        return await self.middleware_runner.run(
            tool_name="execute_query",
            tool_fn=execute_query_async,
            input=state.vizql_query,
            config=state.config,
        )
```

**文件改动**：
- `components/query_pipeline.py`：所有工具调用都经过 middleware
- 确保 `MiddlewareRunner` 正确注入

### 2.0.4 History/Schema token 硬性上限保护

**问题**：Step1 prompt 的 history 和 schema 没有硬性 token 上限。

**解决方案**：

```python
# 在 components/step1.py 中

MAX_HISTORY_TOKENS = 2000
MAX_SCHEMA_TOKENS = 3000

class Step1Component:
    def _format_history(self, history: list[dict]) -> str:
        """格式化历史，带硬性截断"""
        formatted = self._do_format_history(history)
        
        # 硬性截断
        tokens = count_tokens(formatted)
        if tokens > MAX_HISTORY_TOKENS:
            # 保留最近的对话
            formatted = truncate_to_tokens(formatted, MAX_HISTORY_TOKENS)
            logger.warning(f"History truncated: {tokens} -> {MAX_HISTORY_TOKENS}")
            metrics.history_truncation_count.inc()
        
        return formatted
    
    def _format_schema(self, schema_candidates: SchemaCandidates) -> str:
        """格式化 schema，带硬性截断"""
        formatted = schema_candidates.to_prompt_summary()
        
        # 硬性截断
        tokens = count_tokens(formatted)
        if tokens > MAX_SCHEMA_TOKENS:
            # 保留分数最高的候选
            formatted = truncate_to_tokens(formatted, MAX_SCHEMA_TOKENS)
            logger.warning(f"Schema truncated: {tokens} -> {MAX_SCHEMA_TOKENS}")
            metrics.schema_truncation_count.inc()
        
        return formatted
```

**文件改动**：
- `components/step1.py`：增加硬性截断逻辑
- `prompts/step1.py`：确保 prompt 模板支持截断后的输入

### 2.0.5 基础可观测性

**解决方案**：

```python
# 新建 infra/observability/metrics.py

from dataclasses import dataclass, asdict
from typing import Literal

@dataclass
class SemanticParserMetrics:
    """语义解析器基础指标
    
    ⚠️ 重要：此对象不进入 State，只作为 runtime 对象在组件间传递。
    在 subgraph 出口处通过 asdict() 序列化后输出到日志/监控系统。
    """
    
    # 耗时（毫秒）
    preprocess_ms: int = 0
    schema_linking_ms: int = 0
    step1_ms: int = 0
    step2_ms: int = 0
    pipeline_ms: int = 0
    total_ms: int = 0
    
    # Token 数
    step1_prompt_tokens: int = 0
    step1_completion_tokens: int = 0
    step2_prompt_tokens: int = 0
    step2_completion_tokens: int = 0
    
    # LLM 调用次数
    step1_call_count: int = 0
    step2_call_count: int = 0
    react_call_count: int = 0
    
    # 截断
    history_truncated: bool = False
    schema_truncated: bool = False
    
    def to_dict(self) -> dict[str, int | float | bool | str]:
        """序列化为可 JSON 化的 dict，用于日志/监控输出"""
        return asdict(self)


# Metrics 传递方式：通过 RunnableConfig 的 configurable 传递，不进入 State
def get_metrics_from_config(config: RunnableConfig) -> SemanticParserMetrics:
    """从 config 获取 metrics 对象"""
    return config.get("configurable", {}).get("metrics") or SemanticParserMetrics()


def set_metrics_to_config(config: RunnableConfig, metrics: SemanticParserMetrics) -> RunnableConfig:
    """将 metrics 对象设置到 config"""
    configurable = config.get("configurable", {})
    configurable["metrics"] = metrics
    return {**config, "configurable": configurable}


# 在各组件中埋点
class Step1Component:
    async def execute(
        self,
        question: str,
        state: Dict[str, Any],
        config: RunnableConfig | None = None,
    ) -> tuple[Step1Output, str]:
        # 从 config 获取 metrics（不从 state）
        metrics = get_metrics_from_config(config)
        start_time = time.monotonic()
        
        # ... 执行逻辑 ...
        
        # 记录指标
        metrics.step1_ms = int((time.monotonic() - start_time) * 1000)
        metrics.step1_prompt_tokens = response.usage.prompt_tokens
        metrics.step1_completion_tokens = response.usage.completion_tokens
        metrics.step1_call_count += 1
        
        return result, thinking


# 在 subgraph 出口处输出结构化日志
async def semantic_parser_exit(state: SemanticParserState, config: RunnableConfig) -> dict:
    """子图出口节点 - 输出 metrics 到日志"""
    metrics = get_metrics_from_config(config)
    
    # 输出结构化日志（metrics 不进入 state）
    logger.info(
        "SemanticParser completed",
        extra={"metrics": metrics.to_dict()}
    )
    
    return _flatten_output(state)
```

**文件改动**：
- 新建 `infra/observability/metrics.py`
- 各组件：通过 `config` 获取/更新 metrics，不通过 state
- `subgraph.py`：在出口处输出结构化日志

### 2.0.6 组件级解析重试（格式重试闭环）

**问题**：`OutputValidationMiddleware` 在 `after_model` 阶段抛出异常，但 `ModelRetryMiddleware` 在 `wrap_model_call` 阶段捕获异常，导致"校验失败→触发重试"这条链路实际不生效。

**修正方案**（GPT-5.2 审查后调整）：
- **保留 `OutputValidationMiddleware` 作为最终质量闸门**（但不依赖它触发重试）
- **在组件层实现格式重试闭环**（Step1/Step2 内部）
- **职责分离**：格式错误在组件内重试，语义错误交给 ReAct
- 避免"中间件校验 + 组件重试 + ReAct 决策"三套机制互相踩踏

**设计原则**：同一类错误只在一个层级负责处理
| 错误类型 | 处理层级 | 处理方式 |
|---------|---------|---------|
| 格式错误（JSON 解析失败、Pydantic 校验失败） | 组件内 | 重试 + 错误反馈 |
| 语义错误（字段不存在、计算不合法） | ReAct | 决策 + 修复/澄清 |
| 最终校验（兜底） | OutputValidationMiddleware | 记录 + 告警（不触发重试） |

```python
# components/step1.py

MAX_FORMAT_RETRIES = 2  # 格式重试次数（JSON/Pydantic）

class Step1Component:
    """Step1 组件 - 格式重试在组件内闭环"""
    
    async def execute(
        self,
        question: str,
        state: Dict[str, Any],
        config: RunnableConfig | None = None,
    ) -> tuple[Step1Output, str]:
        """执行 Step1 - 格式重试闭环"""
        error_feedback: str | None = None
        
        for attempt in range(MAX_FORMAT_RETRIES + 1):
            try:
                # 构建消息（包含错误反馈）
                messages = self._build_messages(
                    question=question,
                    error_feedback=error_feedback,
                )
                
                # LLM 调用
                response = await self._call_llm_with_tools_and_middleware(
                    messages=messages,
                    config=config,
                )
                
                # 解析响应（格式校验）
                result = parse_json_response(response.content, Step1Output)
                
                # 记录成功
                if attempt > 0:
                    logger.info(f"Step1 parse retry succeeded after {attempt} retries")
                    metrics.step1_parse_retry_success_count.inc()
                
                return result, response.thinking
                
            except (ValueError, ValidationError) as e:
                # 格式错误 → 组件内重试
                if attempt < MAX_FORMAT_RETRIES:
                    logger.warning(
                        f"Step1 parse error, retry {attempt + 1}/{MAX_FORMAT_RETRIES}: {e}"
                    )
                    metrics.step1_parse_retry_count.inc()
                    
                    # 构建结构化错误反馈
                    error_feedback = self._build_error_feedback(e)
                    continue
                
                # 格式重试耗尽 → 抛出，由上层决定是否进入 ReAct
                logger.error(f"Step1 parse retry exhausted after {MAX_FORMAT_RETRIES} retries: {e}")
                metrics.step1_parse_failure_count.inc()
                raise
    
    def _build_error_feedback(self, error: Exception) -> str:
        """构建结构化错误反馈"""
        if isinstance(error, ValidationError):
            # Pydantic 校验错误 - 提取具体字段
            error_details = []
            for err in error.errors():
                field = ".".join(str(loc) for loc in err["loc"])
                msg = err["msg"]
                error_details.append(f"- 字段 '{field}': {msg}")
            
            return (
                f"解析失败：Pydantic 校验错误\n"
                f"{''.join(error_details)}\n"
                f"请修正上述字段后重新输出。"
            )
        else:
            # JSON 解析错误
            return (
                f"解析失败：{str(error)[:200]}\n"
                f"请确保输出是有效的 JSON 格式。"
            )
    
    def _build_messages(
        self,
        question: str,
        error_feedback: str | None = None,
    ) -> list[BaseMessage]:
        """构建消息列表"""
        messages = [
            # ... 原有消息构建逻辑 ...
        ]
        
        # 如果有错误反馈，添加到消息中
        if error_feedback:
            messages.append(HumanMessage(content=error_feedback))
        
        return messages
```

**Step2 同样实现**：

```python
# components/step2.py

MAX_PARSE_RETRIES = 2

class Step2Component:
    """Step2 组件 - 带解析重试"""
    
    async def execute(self, ...) -> tuple[Step2Output, str]:
        """执行 Step2 - 带解析重试"""
        error_feedback: str | None = None
        
        for attempt in range(MAX_PARSE_RETRIES + 1):
            try:
                messages = self._build_messages(error_feedback=error_feedback)
                response = await self._call_llm_with_tools_and_middleware(messages=messages)
                result = parse_json_response(response.content, Step2Output)
                
                if attempt > 0:
                    logger.info(f"Step2 parse succeeded after {attempt} retries")
                    metrics.step2_parse_retry_success_count.inc()
                
                return result, response.thinking
                
            except (ValueError, ValidationError) as e:
                if attempt < MAX_PARSE_RETRIES:
                    logger.warning(f"Step2 parse failed, retry {attempt + 1}: {e}")
                    metrics.step2_parse_retry_count.inc()
                    error_feedback = self._build_error_feedback(e)
                    continue
                
                logger.error(f"Step2 parse failed after {MAX_PARSE_RETRIES} retries: {e}")
                metrics.step2_parse_failure_count.inc()
                raise
```

**文件改动**：
- `components/step1.py`：增加格式重试逻辑
- `components/step2.py`：增加格式重试逻辑
- `orchestration/middleware/output_validation.py`：**保留**作为最终质量闸门（但不依赖它触发重试）
- `infra/observability/metrics.py`：新增重试相关指标（按格式/语义分类）

### 2.0.7 JSON 解析增强（JSON Mode + 流式兼容）

**问题**：
- `json_repair` 失败时缺少详细日志，问题难定位
- 没有利用 DeepSeek 原生的 JSON Mode 能力

**约束**：
- 必须保持流式输出兼容
- **必须保持现有 `call_llm_with_tools()` 调用模式不变**

**技术背景 - DeepSeek 支持的 JSON 输出方案**：

| 方案 | DeepSeek 支持 | 流式支持 | Schema 保证 | 适用场景 |
|------|--------------|----------|-------------|----------|
| Structured Output (`json_schema`) | ❌ 不支持 | ✅ 支持 | ✅ 100% 保证 | OpenAI 专用 |
| JSON Mode (`json_object`) | ✅ 支持 | ✅ 支持 | ⚠️ 只保证是 JSON | **推荐方案** |
| Prompt + json_repair + Pydantic | ✅ 支持 | ✅ 支持 | ⚠️ 依赖模型遵循 | 当前方案 |

**DeepSeek JSON Mode 官方文档要求**：
1. 设置 `response_format: {'type': 'json_object'}`
2. 在 system 或 user prompt 中包含 "json" 关键词
3. 提供期望的 JSON 格式示例
4. 合理设置 `max_tokens` 防止 JSON 被截断

**推荐方案**：JSON Mode + json_repair + Pydantic（三层防护）
- **第一层**：JSON Mode 保证输出是有效 JSON（减少格式错误）
- **第二层**：json_repair 修复可能的截断或小问题
- **第三层**：Pydantic 校验 schema 合规性

**实现方式**：在 LLM 创建时通过 `model_kwargs` 添加 `response_format`，不改变调用方式

**Provider 适配层设计**：

由于不同 LLM Provider 对 JSON Mode 的支持方式不同，需要适配层统一处理：

| Provider | JSON Mode 参数 | 传递方式 | 备注 |
|----------|---------------|----------|------|
| DeepSeek | `response_format: {type: "json_object"}` | `model_kwargs` | 本项目主要使用 |
| OpenAI | `response_format: {type: "json_object"}` | `model_kwargs` | 兼容 |
| CustomLLMChat | `response_format: {type: "json_object"}` | `extra_body` | 仓库现有实现 |
| Anthropic | 不支持原生 JSON Mode | Prompt 约束 | 依赖 json_repair |
| 本地模型 | 取决于具体实现 | `extra_body` 或 `model_kwargs` | 需测试 |

**⚠️ 重要**：requirements.md 明确要求按 Provider **显式配置**支持与否（而非自动探测）。`detect_provider_from_base_url()` 仅作为**默认推断**，生产环境应通过配置文件明确指定。

```python
# infra/ai/json_mode_adapter.py

from enum import Enum
from typing import Any

class ProviderType(Enum):
    """LLM Provider 类型"""
    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    CUSTOM = "custom"  # CustomLLMChat（仓库现有实现）
    ANTHROPIC = "anthropic"
    LOCAL = "local"  # 本地模型（如 Ollama）

def get_json_mode_kwargs(
    provider: ProviderType,
    enable_json_mode: bool = True,
) -> dict[str, Any]:
    """获取 JSON Mode 参数 - Provider 适配层
    
    Args:
        provider: LLM Provider 类型
        enable_json_mode: 是否启用 JSON Mode
        
    Returns:
        传递给 LLM 构造函数的参数字典
        
    ⚠️ 注意：不同 Provider 使用不同的参数传递方式：
    - ChatOpenAI: 通过 model_kwargs.response_format
    - CustomLLMChat: 通过 extra_body.response_format
    """
    if not enable_json_mode:
        return {}
    
    if provider in (ProviderType.DEEPSEEK, ProviderType.OPENAI):
        # DeepSeek 和 OpenAI 使用 ChatOpenAI，通过 model_kwargs 传递
        return {
            "model_kwargs": {
                "response_format": {"type": "json_object"}
            }
        }
    
    elif provider == ProviderType.CUSTOM:
        # CustomLLMChat（仓库现有实现）使用 extra_body 拼 payload
        # 见 custom_llm.py 的实现
        return {
            "extra_body": {
                "response_format": {"type": "json_object"}
            }
        }
    
    elif provider == ProviderType.LOCAL:
        # 本地模型（如通过 OpenAI 兼容 API 访问）
        # 优先尝试 model_kwargs，如果不生效再尝试 extra_body
        return {
            "model_kwargs": {
                "response_format": {"type": "json_object"}
            }
        }
    
    elif provider == ProviderType.ANTHROPIC:
        # Anthropic 不支持原生 JSON Mode
        # 返回空，依赖 Prompt 约束 + json_repair
        logger.info("Anthropic does not support native JSON Mode, relying on prompt constraints")
        metrics.json_mode_fallback_count.inc(labels={"provider": "anthropic"})
        return {}
    
    return {}


def detect_provider_from_base_url(base_url: str | None) -> ProviderType:
    """从 base_url 推断 Provider 类型（仅作为默认推断，生产环境应显式配置）
    
    Args:
        base_url: API base URL
        
    Returns:
        推断的 Provider 类型
        
    ⚠️ 注意：此函数仅用于默认推断，requirements.md 要求生产环境通过配置显式指定 Provider。
    """
    if not base_url:
        return ProviderType.OPENAI  # 默认 OpenAI
    
    base_url_lower = base_url.lower()
    
    if "deepseek" in base_url_lower:
        return ProviderType.DEEPSEEK
    elif "anthropic" in base_url_lower:
        return ProviderType.ANTHROPIC
    elif "localhost" in base_url_lower or "127.0.0.1" in base_url_lower:
        return ProviderType.LOCAL
    elif "openai" in base_url_lower:
        return ProviderType.OPENAI
    
    # 默认假设 OpenAI 兼容
    return ProviderType.LOCAL


# ============================================================
# Provider 配置（推荐方式：显式配置而非自动探测）
# ============================================================

# 配置示例（config.yaml 或环境变量）
# llm:
#   provider: "custom"  # 显式指定 Provider
#   json_mode_enabled: true
#   base_url: "http://localhost:8000/v1"

def get_provider_from_config(config: dict) -> ProviderType:
    """从配置获取 Provider 类型（推荐方式）
    
    Args:
        config: LLM 配置字典
        
    Returns:
        Provider 类型
    """
    provider_str = config.get("provider", "").lower()
    
    provider_map = {
        "deepseek": ProviderType.DEEPSEEK,
        "openai": ProviderType.OPENAI,
        "custom": ProviderType.CUSTOM,
        "anthropic": ProviderType.ANTHROPIC,
        "local": ProviderType.LOCAL,
    }
    
    if provider_str in provider_map:
        return provider_map[provider_str]
    
    # 未配置时回退到 URL 推断
    logger.warning(f"Provider not explicitly configured, falling back to URL detection")
    return detect_provider_from_base_url(config.get("base_url"))
```

**在 model_manager.py 中集成适配层**：

```python
# infra/ai/model_manager.py

from .json_mode_adapter import get_json_mode_kwargs, get_provider_from_config, ProviderType

def create_chat_model(
    config: ModelConfig,
    enable_json_mode: bool = False,
) -> BaseChatModel:
    """创建 LLM 实例 - 支持可选的 JSON Mode（带 Provider 适配）
    
    ⚠️ 重要：根据 Provider 类型选择不同的 LLM 类和参数传递方式：
    - ChatOpenAI: 用于 OpenAI/DeepSeek/本地模型
    - CustomLLMChat: 用于仓库自定义实现（使用 extra_body）
    """
    
    # 从配置获取 Provider 类型（推荐显式配置）
    provider = get_provider_from_config(config.__dict__)
    
    # 通过适配层获取 JSON Mode 参数
    json_mode_kwargs = get_json_mode_kwargs(provider, enable_json_mode)
    
    if provider == ProviderType.CUSTOM:
        # CustomLLMChat 使用 extra_body 传递参数
        custom_kwargs = {
            "model": config.model_name,
            "api_key": config.api_key,
            "base_url": config.api_base,
            "streaming": config.supports_streaming,
        }
        if config.temperature is not None:
            custom_kwargs["temperature"] = config.temperature
        if config.max_tokens is not None:
            custom_kwargs["max_tokens"] = config.max_tokens
        
        # JSON Mode 通过 extra_body 传递
        if json_mode_kwargs.get("extra_body"):
            custom_kwargs["extra_body"] = json_mode_kwargs["extra_body"]
        
        if enable_json_mode:
            logger.debug(f"JSON Mode enabled for CustomLLMChat via extra_body")
        
        return CustomLLMChat(**custom_kwargs)
    
    else:
        # ChatOpenAI 及其兼容实现
        openai_kwargs = {
            "model": config.model_name,
            "api_key": config.api_key,
            "base_url": config.api_base,
            "streaming": config.supports_streaming,
        }
        
        if config.temperature is not None:
            openai_kwargs["temperature"] = config.temperature
        if config.max_tokens is not None:
            openai_kwargs["max_tokens"] = config.max_tokens
        
        # JSON Mode 通过 model_kwargs 传递
        if json_mode_kwargs.get("model_kwargs"):
            openai_kwargs["model_kwargs"] = json_mode_kwargs["model_kwargs"]
        
        if enable_json_mode:
            logger.debug(f"JSON Mode enabled for {provider.value} via model_kwargs")
        
        return ChatOpenAI(**openai_kwargs)
```

**requirements.md 对应条目**：此实现满足需求 0.7 中关于 Provider 适配层的要求，特别是：
- 按 Provider 显式配置支持与否（而非自动探测）
- CustomLLMChat 通过 `extra_body.response_format` 传入
- 不支持时自动降级到 prompt + json_repair 方案

**解决方案**：

```python
# ============================================================
# 1. 在 model_manager.py 中支持 JSON Mode
# ============================================================

# infra/ai/model_manager.py

def create_chat_model(
    config: ModelConfig,
    enable_json_mode: bool = False,
) -> BaseChatModel:
    """创建 LLM 实例 - 支持可选的 JSON Mode
    
    Args:
        config: 模型配置
        enable_json_mode: 是否启用 JSON Mode
        
    Returns:
        LLM 实例
    """
    openai_kwargs = {
        "model": config.model_name,
        "api_key": config.api_key,
        "base_url": config.api_base,
        "streaming": config.supports_streaming,
    }
    
    # 只传入非 None 的参数
    if config.temperature is not None:
        openai_kwargs["temperature"] = config.temperature
    if config.max_tokens is not None:
        openai_kwargs["max_tokens"] = config.max_tokens
    
    # 启用 JSON Mode（通过 model_kwargs 传入）
    if enable_json_mode:
        openai_kwargs["model_kwargs"] = {
            "response_format": {"type": "json_object"}
        }
        logger.debug(f"JSON Mode enabled for model {config.model_name}")
    
    return ChatOpenAI(**openai_kwargs)


# ============================================================
# 2. 在组件层按需启用 JSON Mode
# ============================================================

# components/step1.py

class Step1Component:
    """Step1 组件 - 支持 JSON Mode"""
    
    def __init__(
        self,
        enable_json_mode: bool = True,  # 默认启用
    ):
        self.enable_json_mode = enable_json_mode
    
    async def execute(
        self,
        question: str,
        state: Dict[str, Any],
        config: RunnableConfig | None = None,
    ) -> tuple[Step1Output, str]:
        """执行 Step1 - 调用方式完全不变"""
        
        # 获取 LLM（可选启用 JSON Mode）
        llm = get_llm(enable_json_mode=self.enable_json_mode)
        
        # 构建消息
        messages = self._build_messages(question=question)
        
        # ⭐ 调用方式完全不变 - 保持中间件和流式输出
        response = await call_llm_with_tools(
            llm=llm,
            messages=messages,
            tools=tools,
            streaming=True,
            middleware=middleware,
            state=state,
            config=config,
        )
        
        # 解析响应（三层防护）
        result = parse_json_response(response.content, Step1Output)
        return result, response.thinking


# ============================================================
# 3. 增强版 parse_json_response（三层防护）
# ============================================================

# agents/base/node.py

class JSONParseError(Exception):
    """JSON 解析错误 - 结构化"""
    
    def __init__(
        self,
        message: str,
        content_preview: str,
        error_type: str,
        error_position: int | None = None,
    ):
        self.message = message
        self.content_preview = content_preview
        self.error_type = error_type
        self.error_position = error_position
        super().__init__(message)


def parse_json_response(
    content: str,
    model_class: type[BaseModel],
    repair_enabled: bool = True,
) -> BaseModel:
    """解析 JSON 响应 - 三层防护
    
    第一层：JSON Mode 已在 LLM 层保证输出是有效 JSON
    第二层：json_repair 修复可能的截断或小问题
    第三层：Pydantic 校验 schema 合规性
    
    Args:
        content: LLM 输出内容
        model_class: Pydantic 模型类
        repair_enabled: 是否启用 json_repair
        
    Returns:
        解析后的 Pydantic 模型实例
        
    Raises:
        JSONParseError: JSON 解析失败
        ValidationError: Pydantic 校验失败
    """
    original_content = content
    
    # 第一层：尝试直接解析（JSON Mode 应该保证成功）
    try:
        data = json.loads(content)
        result = model_class.model_validate(data)
        metrics.json_direct_parse_success_count.inc()
        return result
    except json.JSONDecodeError as e:
        logger.debug(f"Direct JSON parse failed at position {e.pos}: {e.msg}")
        metrics.json_direct_parse_failure_count.inc()
    except ValidationError as e:
        # JSON 格式正确但 Pydantic 校验失败
        logger.debug(f"Pydantic validation failed: {e}")
        metrics.pydantic_validation_failure_count.inc()
        raise
    
    # 第二层：尝试 json_repair 修复
    if repair_enabled:
        try:
            from json_repair import repair_json
            
            repaired = repair_json(content)
            data = json.loads(repaired)
            result = model_class.model_validate(data)
            
            logger.info("JSON repaired successfully")
            metrics.json_repair_success_count.inc()
            return result
            
        except json.JSONDecodeError as repair_json_error:
            logger.warning(
                f"JSON repair failed (still invalid JSON): {repair_json_error}, "
                f"original content (truncated): {original_content[:500]}"
            )
            metrics.json_repair_failure_count.inc()
            
        except ValidationError as repair_validation_error:
            # 修复后 JSON 格式正确但 Pydantic 校验失败
            logger.warning(
                f"JSON repaired but Pydantic validation failed: {repair_validation_error}"
            )
            metrics.json_repair_failure_count.inc()
            raise
            
        except Exception as repair_error:
            logger.warning(
                f"JSON repair failed (unexpected error): {repair_error}, "
                f"original content (truncated): {original_content[:500]}"
            )
            metrics.json_repair_failure_count.inc()
    
    # 第三层：解析失败，抛出结构化错误
    raise JSONParseError(
        message="Failed to parse JSON response",
        content_preview=original_content[:200],
        error_type="json_parse",
    )


# ============================================================
# 4. 确保 prompt 包含 "json" 关键词（DeepSeek 要求）
# ============================================================

# prompts/step1.py

STEP1_SYSTEM_PROMPT = """你是一个语义解析助手，负责分析用户的数据查询问题。

请严格按照以下 JSON 格式输出结果：

```json
{
    "intent": {
        "type": "DATA_QUERY",
        "confidence": 0.95
    },
    "dimensions": ["地区"],
    "measures": ["销售额"],
    "filters": [],
    "time_context": {
        "start_date": "2024-12-01",
        "end_date": "2024-12-31"
    }
}
```

注意：
1. 必须输出有效的 JSON 格式
2. 所有字段都必须填写
3. 不要输出任何 JSON 以外的内容
"""
```

**文件改动**：
- `infra/ai/model_manager.py`：新增 `create_chat_model` 函数支持 JSON Mode
- `components/step1.py`：在初始化时支持 `enable_json_mode` 参数
- `components/step2.py`：同上
- `agents/base/node.py`：增强 `parse_json_response` 的错误处理和日志
- `prompts/step1.py`：确保包含 "json" 关键词和格式示例
- `prompts/step2.py`：同上

### 2.0.8 流式 tool_calls 解析错误显式处理

**问题**：tool_calls 参数解析失败时静默变成 `{}`，问题难定位。

**解决方案**：

```python
# agents/base/node.py

def _parse_tool_calls(
    tool_calls: list[dict],
) -> list[ParsedToolCall]:
    """解析 tool_calls - 显式错误处理"""
    
    parsed_calls = []
    
    for tc in tool_calls:
        tool_name = tc.get("name", "")
        raw_args = tc.get("args", "")
        
        # 尝试解析参数
        args: dict = {}
        parse_error: str | None = None
        
        if raw_args:
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError as e:
                # 记录警告日志
                logger.warning(
                    f"Tool call args parse failed for '{tool_name}': {e}, "
                    f"raw args (truncated): {raw_args[:200]}"
                )
                metrics.tool_args_parse_failure_count.inc(
                    labels={"tool_name": tool_name}
                )
                
                # 尝试修复
                try:
                    from json_repair import repair_json
                    repaired = repair_json(raw_args)
                    args = json.loads(repaired)
                    logger.info(f"Tool call args repaired successfully for '{tool_name}'")
                    metrics.tool_args_repair_success_count.inc()
                except Exception as repair_error:
                    logger.warning(
                        f"Tool call args repair failed for '{tool_name}': {repair_error}"
                    )
                    metrics.tool_args_repair_failure_count.inc()
                    parse_error = str(e)
        
        parsed_calls.append(ParsedToolCall(
            id=tc.get("id", ""),
            name=tool_name,
            args=args,
            parse_error=parse_error,
        ))
    
    return parsed_calls

@dataclass
class ParsedToolCall:
    """解析后的 tool call"""
    id: str
    name: str
    args: dict
    parse_error: str | None = None  # 解析错误信息（如果有）
```

**文件改动**：
- `agents/base/node.py`：重构 tool_calls 解析逻辑
- `infra/observability/metrics.py`：新增 tool_args 相关指标

### 2.0.9 LLM 空响应显式处理

**问题**：LLM 返回空响应时返回空字符串，上层难以定位问题。

**解决方案**：

```python
# agents/base/node.py

class LLMEmptyResponseError(Exception):
    """LLM 空响应异常"""
    
    def __init__(self, model: str, message_count: int, request_id: str | None = None):
        self.model = model
        self.message_count = message_count
        self.request_id = request_id
        super().__init__(
            f"LLM returned empty response. "
            f"Model: {model}, Messages: {message_count}, Request ID: {request_id}"
        )

async def _call_llm_with_tools_and_middleware(
    self,
    messages: list[BaseMessage],
    config: RunnableConfig | None = None,
    **kwargs,
) -> ModelResponse:
    """调用 LLM - 增强空响应处理"""
    
    # ... 现有逻辑 ...
    
    response = await self._execute_model_call(request)
    
    # 检查空响应
    if not response.result or not response.result.content:
        logger.error(
            f"LLM returned empty response. "
            f"Model: {request.model}, "
            f"Messages: {len(messages)}, "
            f"Request ID: {config.get('request_id') if config else None}"
        )
        metrics.llm_empty_response_count.inc(
            labels={"model": request.model}
        )
        
        raise LLMEmptyResponseError(
            model=request.model,
            message_count=len(messages),
            request_id=config.get("request_id") if config else None,
        )
    
    return response
```

**文件改动**：
- `agents/base/node.py`：新增 `LLMEmptyResponseError` 异常类，增强空响应检测
- `infra/observability/metrics.py`：新增空响应指标

### 2.0.10 Step1 history 参数与 SummarizationMiddleware 对齐

**问题**：Step1 的 `history` 参数是直接传入的，不是从 `state["messages"]` 读取的，所以 `SummarizationMiddleware` 对 Step1 的 history 不生效。

**解决方案**：

```python
# components/step1.py

class Step1Component:
    """Step1 组件 - 修复 history 来源"""
    
    async def execute(
        self,
        question: str,
        state: Dict[str, Any],  # 从 state 读取 history
        data_model: DataModel,
        config: RunnableConfig | None = None,
        error_feedback: str | None = None,
    ) -> tuple[Step1Output, str]:
        """
        执行 Step1
        
        重要变更：history 从 state["messages"] 读取，而非直接传入参数
        这样 SummarizationMiddleware 的处理结果才能生效
        """
        # 从 state["messages"] 读取 history（已被 SummarizationMiddleware 处理）
        messages = state.get("messages", [])
        history = self._convert_messages_to_history(messages)
        
        # 硬性截断作为兜底（需求 0.4）
        history_str = self._format_history_with_limit(history, MAX_HISTORY_TOKENS)
        
        # 记录 history 来源和 token 数
        history_tokens = count_tokens(history_str)
        logger.debug(
            f"Step1 history: source=state['messages'], "
            f"message_count={len(messages)}, "
            f"tokens={history_tokens}"
        )
        metrics.step1_history_tokens.observe(history_tokens)
        
        # ... 后续逻辑 ...
    
    def _convert_messages_to_history(
        self,
        messages: list[BaseMessage],
    ) -> list[dict]:
        """将 LangGraph 消息转换为 history 格式"""
        history = []
        
        for msg in messages:
            if isinstance(msg, HumanMessage):
                history.append({
                    "role": "user",
                    "content": msg.content,
                })
            elif isinstance(msg, AIMessage):
                history.append({
                    "role": "assistant",
                    "content": msg.content,
                })
        
        return history
    
    def _format_history_with_limit(
        self,
        history: list[dict],
        max_tokens: int,
    ) -> str:
        """格式化 history，带硬性截断"""
        # 从最近的消息开始，逐步添加
        formatted_parts = []
        total_tokens = 0
        
        for msg in reversed(history):
            part = f"{msg['role']}: {msg['content']}"
            part_tokens = count_tokens(part)
            
            if total_tokens + part_tokens > max_tokens:
                # 超出限制，停止添加
                if formatted_parts:
                    logger.warning(
                        f"History truncated: {len(history)} messages -> {len(formatted_parts)} messages"
                    )
                    metrics.history_truncation_count.inc()
                break
            
            formatted_parts.insert(0, part)
            total_tokens += part_tokens
        
        return "\n".join(formatted_parts)
```

**调用方修改**：

```python
# subgraph.py 或调用 Step1 的地方

async def step1_node(state: SemanticParserState) -> dict:
    """Step1 节点"""
    step1_component = Step1Component()
    
    # 不再直接传入 history 参数，而是传入整个 state
    result, thinking = await step1_component.execute(
        question=state.question,
        state=state.model_dump(),  # 传入整个 state
        data_model=state.data_model,
        config=state.config,
    )
    
    return {"step1_output": result, "step1_thinking": thinking}
```

**文件改动**：
- `components/step1.py`：修改 history 来源为 `state["messages"]`
- `subgraph.py`：修改 Step1 调用方式
- `state.py`：确保 `messages` 字段正确传递

### 2.0.11 完整 middleware 钩子调用（before_agent/after_agent）

**问题**：`_call_llm_with_tools_and_middleware()` 只调用了 `before_model / wrap_model_call / after_model`，没有调用 `before_agent / after_agent`。

**解决方案（带错误处理和降级策略）**：

```python
# subgraph.py

from agents.base.middleware_runner import get_middleware_runner

async def semantic_parser_entry(state: SemanticParserState) -> dict:
    """
    子图入口节点 - 调用 before_agent（带错误处理）
    
    确保 PatchToolCallsMiddleware.before_agent() 等钩子能够生效
    单个钩子失败不阻塞整个流程
    """
    runner = get_middleware_runner(state.config)
    runtime = runner.build_runtime(state.config)
    skip_failed_hooks = state.config.get("skip_failed_hooks", True)
    
    try:
        updated_state = await runner.run_before_agent(
            state.model_dump(), 
            runtime,
            skip_on_error=skip_failed_hooks,
        )
        logger.debug("Semantic parser entry: before_agent hooks executed successfully")
        return updated_state
    except Exception as e:
        logger.error(f"before_agent hooks failed: {e}")
        metrics.middleware_hook_failure_count.inc(labels={"hook": "before_agent", "phase": "entry"})
        
        if skip_failed_hooks:
            logger.warning("Continuing with original state due to skip_failed_hooks=True")
            return state.model_dump()
        raise

async def semantic_parser_exit(state: SemanticParserState) -> dict:
    """
    子图出口节点 - 调用 after_agent（带错误处理）
    
    确保 OutputValidationMiddleware.after_agent() 等钩子能够生效
    单个钩子失败不阻塞整个流程
    """
    runner = get_middleware_runner(state.config)
    runtime = runner.build_runtime(state.config)
    skip_failed_hooks = state.config.get("skip_failed_hooks", True)
    
    try:
        updated_state = await runner.run_after_agent(
            state.model_dump(), 
            runtime,
            skip_on_error=skip_failed_hooks,
        )
        logger.debug("Semantic parser exit: after_agent hooks executed successfully")
    except Exception as e:
        logger.error(f"after_agent hooks failed: {e}")
        metrics.middleware_hook_failure_count.inc(labels={"hook": "after_agent", "phase": "exit"})
        
        if skip_failed_hooks:
            logger.warning("Continuing with original state due to skip_failed_hooks=True")
            updated_state = state.model_dump()
        else:
            raise
    
    # 扁平化输出
    flattened = _flatten_output(updated_state)
    return flattened

def create_semantic_parser_subgraph() -> CompiledGraph:
    """创建语义解析器子图 - 增加入口和出口节点"""
    
    graph = StateGraph(SemanticParserState)
    
    # 入口节点（调用 before_agent）
    graph.add_node("entry", semantic_parser_entry)
    
    # 现有节点
    graph.add_node("preprocess", preprocess_node)
    graph.add_node("schema_linking", schema_linking_node)
    graph.add_node("step1", step1_node)
    graph.add_node("step2", step2_node)
    graph.add_node("pipeline", pipeline_node)
    graph.add_node("react", react_node)
    
    # 出口节点（调用 after_agent）
    graph.add_node("exit", semantic_parser_exit)
    
    # 边
    graph.add_edge(START, "entry")
    graph.add_edge("entry", "preprocess")
    graph.add_edge("preprocess", "schema_linking")
    graph.add_edge("schema_linking", "step1")
    graph.add_conditional_edges("step1", route_after_step1)
    graph.add_conditional_edges("step2", route_after_step2)
    graph.add_conditional_edges("pipeline", route_after_pipeline)
    graph.add_conditional_edges("react", route_after_react)
    
    # 所有终止路径都经过 exit
    # 在 route_* 函数中，将 END 替换为 "exit"
    graph.add_edge("exit", END)
    
    return graph.compile()
```

**middleware_runner 增强（带错误处理）**：

```python
# agents/base/middleware_runner.py

@dataclass
class HookExecutionResult:
    """钩子执行结果"""
    success: bool
    middleware_name: str
    error: Exception | None = None
    duration_ms: int = 0

class MiddlewareRunner:
    """中间件运行器 - 增强版（带错误处理和降级）"""
    
    async def run_before_agent(
        self,
        state: dict,
        runtime: MiddlewareRuntime,
        skip_on_error: bool = True,
    ) -> dict:
        """
        运行 before_agent 钩子
        
        Args:
            state: 当前状态
            runtime: 中间件运行时
            skip_on_error: 单个钩子失败时是否跳过继续执行
        
        Returns:
            更新后的状态
        
        Raises:
            Exception: 当 skip_on_error=False 且钩子执行失败时
        """
        results: list[HookExecutionResult] = []
        
        for middleware in runtime.middlewares:
            middleware_name = middleware.__class__.__name__
            start_time = time.monotonic()
            
            try:
                if hasattr(middleware, "before_agent"):
                    state = await middleware.before_agent(state)
                elif hasattr(middleware, "abefore_agent"):
                    state = await middleware.abefore_agent(state)
                
                duration_ms = int((time.monotonic() - start_time) * 1000)
                results.append(HookExecutionResult(
                    success=True,
                    middleware_name=middleware_name,
                    duration_ms=duration_ms,
                ))
                
            except Exception as e:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                results.append(HookExecutionResult(
                    success=False,
                    middleware_name=middleware_name,
                    error=e,
                    duration_ms=duration_ms,
                ))
                
                logger.error(
                    f"before_agent hook failed for {middleware_name}: {e}",
                    exc_info=True,
                )
                metrics.middleware_hook_failure_count.inc(
                    labels={"hook": "before_agent", "middleware": middleware_name}
                )
                
                if not skip_on_error:
                    raise
                
                logger.warning(f"Skipping failed hook {middleware_name}, continuing...")
        
        # 记录执行摘要
        self._log_hook_summary("before_agent", results)
        return state
    
    async def run_after_agent(
        self,
        state: dict,
        runtime: MiddlewareRuntime,
        skip_on_error: bool = True,
    ) -> dict:
        """
        运行 after_agent 钩子
        
        Args:
            state: 当前状态
            runtime: 中间件运行时
            skip_on_error: 单个钩子失败时是否跳过继续执行
        
        Returns:
            更新后的状态
        
        Raises:
            Exception: 当 skip_on_error=False 且钩子执行失败时
        """
        results: list[HookExecutionResult] = []
        
        for middleware in runtime.middlewares:
            middleware_name = middleware.__class__.__name__
            start_time = time.monotonic()
            
            try:
                if hasattr(middleware, "after_agent"):
                    state = await middleware.after_agent(state)
                
                duration_ms = int((time.monotonic() - start_time) * 1000)
                results.append(HookExecutionResult(
                    success=True,
                    middleware_name=middleware_name,
                    duration_ms=duration_ms,
                ))
                
            except Exception as e:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                results.append(HookExecutionResult(
                    success=False,
                    middleware_name=middleware_name,
                    error=e,
                    duration_ms=duration_ms,
                ))
                
                logger.error(
                    f"after_agent hook failed for {middleware_name}: {e}",
                    exc_info=True,
                )
                metrics.middleware_hook_failure_count.inc(
                    labels={"hook": "after_agent", "middleware": middleware_name}
                )
                
                if not skip_on_error:
                    raise
                
                logger.warning(f"Skipping failed hook {middleware_name}, continuing...")
        
        # 记录执行摘要
        self._log_hook_summary("after_agent", results)
        return state
    
    def _log_hook_summary(self, hook_name: str, results: list[HookExecutionResult]):
        """记录钩子执行摘要"""
        total = len(results)
        success = sum(1 for r in results if r.success)
        failed = total - success
        total_duration = sum(r.duration_ms for r in results)
        
        logger.info(
            f"{hook_name} hooks summary: "
            f"total={total}, success={success}, failed={failed}, "
            f"duration={total_duration}ms"
        )
        
        if failed > 0:
            failed_names = [r.middleware_name for r in results if not r.success]
            logger.warning(f"{hook_name} failed middlewares: {failed_names}")
```

**配置项**：

```python
# 在 config 中添加配置项
MIDDLEWARE_CONFIG = {
    # 是否跳过失败的钩子继续执行（默认 True，保证流程不中断）
    "skip_failed_hooks": True,
    
    # 钩子执行超时时间（毫秒）
    "hook_timeout_ms": 5000,
    
    # 是否记录详细的钩子执行日志
    "verbose_hook_logging": False,
}
```

**文件改动**：
- `subgraph.py`：新增 `semantic_parser_entry` 和 `semantic_parser_exit` 节点（带错误处理）
- `agents/base/middleware_runner.py`：新增 `run_before_agent` 和 `run_after_agent` 方法（带错误处理和降级）
- `infra/observability/metrics.py`：新增 `middleware_hook_failure_count` 指标

## 3. Phase 1-4: vNext 功能设计

### 3.1 Step1Output 重构（直接替换）

vNext 直接替换现有 Step1Output，不做兼容：

```python
class Step1Output(BaseModel):
    """Step1 输出 - vNext 版本（直接替换）
    
    ⚠️ 单一事实来源原则：
    - canonical_question 由 PreprocessResult 产出，Step1 只引用（不产出）
    - time_context 由 PreprocessResult 产出，Step1 只引用（不产出）
    - memory_slots 由 PreprocessResult 产出，Step1 只引用（不产出）
    
    Step1Output 不包含上述字段，避免"双权威来源"。
    """
    
    # 字段引用（从候选集选择）
    field_references: list[FieldReference]
    
    # 保留核心字段
    what: What
    where: Where
    how_type: HowType
    intent: Intent
    validation: Step1Validation
    
    # 删除 restated_question（不再需要英文独立问题）
    # 删除 canonical_question（由 PreprocessResult 产出，Step1 只引用）
```

**变更点**：
- 删除 `restated_question`：不再需要英文独立问题
- 删除 `canonical_question`：由 PreprocessResult 产出，Step1 只引用（单一事实来源原则）
- 新增 `field_references`：字段引用列表，从候选集选择

**canonical_question 获取方式**：
```python
# 在需要 canonical_question 的地方，从 state 获取（而非从 Step1Output）
canonical_question = state.preprocess_result.canonical_question
```

### 字段引用协议（FieldReference）

```python
@dataclass
class FieldReference:
    """字段引用 - Step1 输出到 MapFields 的契约"""
    
    # 必填：候选 ID（Schema Linking 生成）
    candidate_id: str
    
    # 必填：规范字段名（优先 caption，无则 name）
    canonical_name: str
    
    # 必填：字段角色
    role: Literal["dimension", "measure"]
    
    # 必填：置信度（0-1）
    confidence: float
    
    # 可选：表名（多表场景）
    table_name: str | None = None
    
    # 可选：原始业务术语（用户输入）
    original_term: str | None = None

# Schema Linking 输出的候选
@dataclass
class FieldCandidate:
    """字段候选 - Schema Linking 输出"""
    candidate_id: str  # 格式: "{role}_{index}" 如 "dim_0", "meas_1"
    field_name: str
    field_caption: str
    canonical_name: str  # = caption if caption else name
    role: Literal["dimension", "measure"]
    score: float
    sample_values: list[str] | None = None
    hierarchy_info: dict | None = None
    table_name: str | None = None
```

### MapFields 行为分流

```
Step1 输出 FieldReference
         │
         ▼
    confidence >= 0.9?
         │
    ┌────┴────┐
    │ Yes     │ No
    ▼         ▼
 Fast Path   RAG Fallback
 (校验+落地)  (检索+重排)
```

**Fast Path（校验+落地）**：
- 条件：`field_reference.confidence >= 0.9` 且 `candidate_id` 有效
- 行为：直接使用 `canonical_name`，跳过 RAG 检索
- 校验：确认字段存在于 DataModel

**RAG Fallback（检索+重排）**：
- 条件：`confidence < 0.9` 或 `candidate_id` 无效
- 行为：使用 `original_term` 走现有 RAG+LLM 流程

### 3.2 错误码与澄清协议

### 现有错误类型映射

```python
# 现有 QueryErrorType → vNext ErrorAction 映射
ERROR_ACTION_MAP = {
    # 快速失败（不重试）
    QueryErrorType.AUTH_ERROR: ErrorAction.ABORT,
    QueryErrorType.NO_METADATA: ErrorAction.ABORT,
    QueryErrorType.TIMEOUT: ErrorAction.ABORT,
    
    # 转澄清
    QueryErrorType.FIELD_NOT_FOUND: ErrorAction.CLARIFY,
    QueryErrorType.AMBIGUOUS_FIELD: ErrorAction.CLARIFY,
    
    # 尝试规则修复
    QueryErrorType.INVALID_COMPUTATION: ErrorAction.FIX,
    QueryErrorType.BUILD_FAILED: ErrorAction.FIX,
    
    # LLM ReAct（长尾）
    QueryErrorType.UNKNOWN: ErrorAction.LLM_REACT,
    QueryErrorType.EXECUTION_FAILED: ErrorAction.LLM_REACT,
}
```

### ClarificationRequest 定义（对外契约）

```python
class ClarificationRequest(BaseModel):
    """统一澄清请求
    
    ⚠️ 对外契约（与 requirements.md 保持一致）：
    - type: 大写枚举值（FIELD_AMBIGUOUS | LOW_CONFIDENCE | FILTER_VALUE_NOT_FOUND | MULTIPLE_INTERPRETATION）
    - options: 候选选项列表（对外 API 统一使用 options）
    - message: 用户友好的澄清问题
    
    注意：项目未上线，只做内部契约一致性，不做旧行为兼容。
    不包含 field/user_values/available_values 等旧字段。
    """
    
    type: ClarificationType
    message: str
    options: list[ClarificationOption]
```

## 组件和接口

### 1. Preprocess 组件

**文件**: `components/preprocess.py`

```python
@dataclass
class TimeContext:
    """时间上下文"""
    start_date: date | None = None
    end_date: date | None = None
    is_relative: bool = False
    grain_hint: str | None = None  # DAY/WEEK/MONTH/QUARTER/YEAR
    original_expression: str | None = None  # "上月"、"近7天"

@dataclass
class MemorySlots:
    """从历史对话中提取的已确认项"""
    confirmed_dimensions: list[str] = field(default_factory=list)
    confirmed_measures: list[str] = field(default_factory=list)
    confirmed_filters: list[dict] = field(default_factory=list)
    time_preference: TimeContext | None = None
    granularity_preference: str | None = None

@dataclass
class PreprocessResult:
    """预处理结果"""
    canonical_question: str
    normalized_question: str
    time_context: TimeContext | None
    memory_slots: MemorySlots
    extracted_terms: list[str]  # 候选业务术语

class PreprocessComponent:
    """预处理组件 - 0 LLM 调用"""
    
    def execute(
        self,
        question: str,
        history: list[dict] | None = None,
        current_date: date | None = None,
    ) -> PreprocessResult:
        """执行预处理"""
        # 1. 规范化
        normalized = self._normalize(question)
        
        # 2. 时间解析
        time_context = self._extract_time(normalized, current_date)
        
        # 3. 历史槽位提取
        memory_slots = self._extract_slots(history)
        
        # 4. 构建 canonical question
        canonical = self._build_canonical(normalized, time_context)
        
        # 5. 提取候选术语
        terms = self._extract_terms(normalized)
        
        return PreprocessResult(
            canonical_question=canonical,
            normalized_question=normalized,
            time_context=time_context,
            memory_slots=memory_slots,
            extracted_terms=terms,
        )
```

#### GPT-5.2 建议：术语提取增强

> "term 抽取应更 deterministic：仅靠 LLM/粗分词会导致召回不稳；建议 Preprocess 增加'字典/字段名/别名/同义词'的轻量 NER。"

```python
class TermExtractor:
    """增强版术语提取器 - 字典驱动"""
    
    def __init__(self, data_model: DataModel):
        # 构建字段名词典
        self._field_dict: set[str] = set()
        self._alias_map: dict[str, str] = {}  # 别名 -> 规范名
        
        for field in data_model.fields:
            # 字段名和标题
            self._field_dict.add(field.name.lower())
            self._field_dict.add(field.caption.lower())
            
            # 加入 jieba 自定义词典（高频词）
            jieba.add_word(field.caption, freq=1000)
            jieba.add_word(field.name, freq=1000)
            
            # 别名映射（如果有）
            for alias in field.aliases or []:
                self._alias_map[alias.lower()] = field.caption
                jieba.add_word(alias, freq=1000)
    
    def extract(self, question: str) -> list[str]:
        """提取术语"""
        terms = []
        
        # 1. 字典匹配（优先级最高）
        for word in self._field_dict:
            if word in question.lower():
                terms.append(word)
        
        # 2. jieba 分词（已加载自定义词典）
        words = jieba.lcut(question)
        for word in words:
            if self._is_valid_term(word):
                # 别名归一化
                normalized = self._alias_map.get(word.lower(), word)
                terms.append(normalized)
        
        # 3. N-gram 补充（捕获复合词）
        for i in range(len(words) - 1):
            bigram = words[i] + words[i+1]
            if len(bigram) >= 3 and len(bigram) <= 8:
                if bigram.lower() in self._field_dict:
                    terms.append(bigram)
        
        return list(set(terms))
    
    def _is_valid_term(self, word: str) -> bool:
        """判断是否为有效术语"""
        if len(word) < 2:
            return False
        if word in STOPWORDS:
            return False
        if word in TIME_WORDS:
            return False
        if word in COMPUTATION_WORDS:
            return False
        return True
```

**关键改进**：
1. 用数据源字段名/caption 构建 jieba 自定义词典
2. 支持别名归一化（如"销售金额" → "销售额"）
3. N-gram 补充捕获复合词
4. 字典匹配优先级最高，确保召回稳定

### 2. Schema Linking 组件

**文件**: `components/schema_linking.py`

#### 参数配置表

| 参数 | 默认值 | 说明 | 边界条件 |
|------|--------|------|----------|
| `top_k_question` | 30 | 问题级检索返回数 | 字段数 > 500 时降为 20 |
| `top_k_term` | 10 | 实体级检索返回数/term | - |
| `min_score` | 0.3 | 最低相关性阈值 | 低于此分数不纳入候选 |
| `max_terms` | 10 | 最大提取术语数 | 超过时按 TF-IDF 排序截断 |
| `dedup_key` | `field_name` | 去重键 | 同名字段保留分数最高的 |
| `language_strategy` | `auto` | 语言策略 | auto/zh/en |
| `fallback_on_empty` | `true` | 空结果时降级 | 降级到全量字段 top-k |

#### GPT-5.2 建议：两阶段打分融合

> "Schema Linking 引入两阶段打分：融合问题级 embedding 分 + term 精确/模糊匹配分 +（可选）reranker 分，做加权融合排序，减少'union 乱序'带来的噪声。"

```python
@dataclass
class ScoringWeights:
    """打分权重配置"""
    exact_match: float = 1.0      # 精确匹配（最高优先级）
    fuzzy_match: float = 0.8      # N-gram 模糊匹配
    embedding: float = 0.6        # 向量相似度
    reranker: float = 0.4         # Reranker 分数（可选）

def compute_final_score(
    candidate: FieldCandidate,
    weights: ScoringWeights,
) -> float:
    """计算融合分数"""
    score = 0.0
    
    # 精确匹配：直接置顶
    if candidate.exact_match:
        return 1.0
    
    # 加权融合
    if candidate.fuzzy_score:
        score += weights.fuzzy_match * candidate.fuzzy_score
    if candidate.embedding_score:
        score += weights.embedding * candidate.embedding_score
    if candidate.reranker_score:
        score += weights.reranker * candidate.reranker_score
    
    # 归一化
    total_weight = weights.fuzzy_match + weights.embedding + weights.reranker
    return score / total_weight
```

**打分流程**：

```
输入: canonical_question + extracted_terms
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 1: 多路召回                                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  精确匹配 O(1)     N-gram 模糊 O(k)     向量检索 O(log n)       │
│       │                  │                    │                 │
│       ▼                  ▼                    ▼                 │
│  exact_matches      fuzzy_matches      vector_candidates        │
│  (score=1.0)        (score=0.8)        (score=embedding)        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 2: 融合排序                                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 合并所有候选（按 field_name 去重）                          │
│  2. 计算融合分数 = weighted_sum(exact, fuzzy, embedding)        │
│  3. 按融合分数降序排序                                          │
│  4. 取 top-k                                                    │
│                                                                 │
│  可选：Reranker 精排（有超时降级）                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
输出: SchemaCandidates (维度/度量分桶)
```

#### 降级策略

```
字段数检查
    │
    ▼
字段数 <= 2000? ──→ 是 ──→ 正常 Schema Linking
    │
    ▼ 否
降级模式:
- top_k_question: 20 (降低)
- 禁用实体级检索
- 启用缓存预热
- 记录 degraded_mode 指标
```

#### 成本上限

| 字段数范围 | embedding 调用次数 | 预估延迟 |
|------------|-------------------|----------|
| ≤ 500 | 1 (问题) + N (术语) | < 200ms |
| 500-2000 | 1 (问题) | < 100ms |
| > 2000 | 建议预热 + 缓存 | 首次 > 500ms |

#### P0 优化：预计算字段 Embedding 池化

```python
class SchemaLinkingV2:
    """优化版 Schema Linking - 按 role 过滤检索空间"""
    
    def __init__(self, field_indexer: FieldIndexer):
        self.field_indexer = field_indexer
        # 预计算维度/度量的中心向量
        self._dim_centroid: np.ndarray | None = None
        self._meas_centroid: np.ndarray | None = None
    
    def precompute_centroids(self, fields: list[Field]):
        """预计算角色中心向量（数据源加载时调用）"""
        dim_embeddings = [f.embedding for f in fields if f.role == "dimension"]
        meas_embeddings = [f.embedding for f in fields if f.role == "measure"]
        
        self._dim_centroid = np.mean(dim_embeddings, axis=0)
        self._meas_centroid = np.mean(meas_embeddings, axis=0)
    
    async def execute(self, question: str, ...):
        # 1. 判断意图偏向（维度 or 度量）
        intent_vector = await embed_query(question)
        dim_sim = cosine(intent_vector, self._dim_centroid)
        meas_sim = cosine(intent_vector, self._meas_centroid)
        
        # 2. 针对性检索（减少 50% 检索空间）
        if dim_sim > meas_sim + 0.2:
            search_pool = "dimensions_only"
        elif meas_sim > dim_sim + 0.2:
            search_pool = "measures_only"
        else:
            search_pool = "both"
        
        # 3. 执行检索
        candidates = await self._retrieve(question, search_pool)
        return candidates
```

**收益**：Schema Linking 延迟 -30%，召回率 +5%

#### P0 优化：N-gram 模糊匹配索引

```python
class FieldIndexerV2:
    """优化版字段索引 - 支持 N-gram 模糊匹配"""
    
    def __init__(self):
        # 精确匹配索引 O(1)
        self._exact_index: dict[str, Field] = {}
        self._caption_index: dict[str, Field] = {}
        
        # N-gram 倒排索引（支持容错）
        self._ngram_index: dict[str, set[str]] = {}
    
    def build_index(self, fields: list[Field]):
        """构建索引"""
        for field in fields:
            # 精确匹配
            self._exact_index[field.name.lower()] = field
            self._caption_index[field.caption.lower()] = field
            
            # N-gram (n=2,3)
            text = f"{field.caption} {field.name}".lower()
            for i in range(len(text) - 1):
                ngram = text[i:i+2]
                self._ngram_index.setdefault(ngram, set()).add(field.name)
            for i in range(len(text) - 2):
                ngram = text[i:i+3]
                self._ngram_index.setdefault(ngram, set()).add(field.name)
    
    def exact_match(self, term: str) -> Field | None:
        """精确匹配 O(1)"""
        term_lower = term.lower()
        return self._exact_index.get(term_lower) or self._caption_index.get(term_lower)
    
    def fuzzy_match(self, term: str) -> list[str]:
        """
        N-gram 模糊匹配 O(k), k=term长度
        
        示例："销售金额" 可以匹配到 "销售额"（容错）
        """
        term_lower = term.lower()
        candidate_sets = []
        
        for i in range(len(term_lower) - 1):
            ngram = term_lower[i:i+2]
            if ngram in self._ngram_index:
                candidate_sets.append(self._ngram_index[ngram])
        
        if candidate_sets:
            # 取交集：必须包含所有 ngram
            return list(set.intersection(*candidate_sets))
        return []
```

**收益**：召回率 +10%（覆盖用户拼写变体），比向量检索快 10x

#### P0 优化：Batch Embedding

```python
class BatchEmbeddingOptimizer:
    """批量 Embedding 优化器"""
    
    def __init__(self, provider, batch_size: int = 20, flush_delay_ms: int = 50):
        self.provider = provider
        self.batch_size = batch_size
        self.flush_delay_ms = flush_delay_ms
        self._pending_queue: list[tuple[str, asyncio.Future]] = []
        self._batch_task: asyncio.Task | None = None
    
    async def embed_query(self, text: str) -> list[float]:
        """
        批量 Embedding 入口
        
        策略：
        1. 请求进入队列
        2. 队列达到 batch_size 或 超时 50ms → 触发批处理
        3. 调用 provider.embed_batch() 一次性计算
        4. 分发结果给各个等待者
        """
        future = asyncio.Future()
        self._pending_queue.append((text, future))
        
        if len(self._pending_queue) >= self.batch_size:
            await self._flush_batch()
        elif self._batch_task is None:
            self._batch_task = asyncio.create_task(
                self._auto_flush()
            )
        
        return await future
    
    async def _flush_batch(self):
        """执行批处理"""
        if not self._pending_queue:
            return
        
        batch = self._pending_queue[:self.batch_size]
        self._pending_queue = self._pending_queue[self.batch_size:]
        
        texts = [text for text, _ in batch]
        
        # 批量调用
        embeddings = await self.provider.embed_batch(texts)
        
        # 分发结果
        for (text, future), embedding in zip(batch, embeddings):
            future.set_result(embedding)
        
        self._batch_task = None
    
    async def _auto_flush(self):
        """超时自动 flush"""
        await asyncio.sleep(self.flush_delay_ms / 1000)
        await self._flush_batch()
```

**收益**：
- Embedding 调用次数 -80%（20 个请求 → 1 次批处理）
- Schema Linking 延迟 -50%
- API 费用 -80%

```python
@dataclass
class FieldCandidate:
    """字段候选"""
    candidate_id: str  # 格式: "{role}_{index}" 如 "dim_0", "meas_1"
    field_name: str
    field_caption: str
    canonical_name: str  # = caption if caption else name
    role: str  # dimension/measure
    score: float
    sample_values: list[str] | None = None  # 不缓存，实时获取
    hierarchy_info: dict | None = None
    table_name: str | None = None  # 多表场景

@dataclass
class SchemaCandidates:
    """Schema 候选集"""
    dimensions: list[FieldCandidate]
    measures: list[FieldCandidate]
    filter_value_candidates: dict[str, list[str]]  # field_name -> candidate values
    
    # 元信息
    total_fields: int = 0  # 数据源总字段数
    is_degraded: bool = False  # 是否降级模式
    search_pool: str = "both"  # 检索池：dimensions_only/measures_only/both
    
    def to_prompt_summary(self, max_dims: int = 20, max_meas: int = 15) -> str:
        """生成用于 Step1 prompt 的摘要"""
        ...

class SchemaLinkingComponent:
    """Schema Linking 组件 - RAG 检索"""
    
    def __init__(
        self,
        field_indexer: FieldIndexerV2,
        embedding_optimizer: BatchEmbeddingOptimizer,
        cache: CandidateCache | None = None,
        config: SchemaLinkingConfig | None = None,
    ):
        self.field_indexer = field_indexer
        self.embedding_optimizer = embedding_optimizer
        self.cache = cache
        self.config = config or SchemaLinkingConfig()
        
        # 预计算中心向量
        self._dim_centroid: np.ndarray | None = None
        self._meas_centroid: np.ndarray | None = None
    
    async def execute(
        self,
        canonical_question: str,
        extracted_terms: list[str],
        data_model: DataModel,
        datasource_luid: str,
    ) -> SchemaCandidates:
        """执行 Schema Linking"""
        # 1. 检查缓存
        cache_key = self._build_cache_key(canonical_question, datasource_luid)
        if self.cache and (cached := self.cache.get(cache_key)):
            return cached
        
        # 2. 精确匹配 + N-gram 模糊匹配（O(1) + O(k)）
        exact_matches = []
        fuzzy_matches = []
        for term in extracted_terms:
            if exact := self.field_indexer.exact_match(term):
                exact_matches.append(exact)
            else:
                fuzzy_matches.extend(self.field_indexer.fuzzy_match(term))
        
        # 3. 判断检索池（维度/度量/全部）
        search_pool = await self._determine_search_pool(canonical_question)
        
        # 4. 向量检索（使用 Batch Embedding）
        question_embedding = await self.embedding_optimizer.embed_query(canonical_question)
        vector_candidates = await self._vector_search(
            question_embedding,
            search_pool=search_pool,
            top_k=self.config.top_k_question,
        )
        
        # 5. 合并去重
        candidates = self._merge_candidates(exact_matches, fuzzy_matches, vector_candidates)
        candidates.search_pool = search_pool
        
        # 6. 缓存结果
        if self.cache:
            self.cache.set(cache_key, candidates)
        
        return candidates
```

### 3. Step1 重构

**文件**: `components/step1.py` (修改)

```python
class Step1Component:
    """Step1 重构 - 受约束生成"""
    
    async def execute(
        self,
        canonical_question: str,
        time_context: TimeContext | None,
        memory_slots: MemorySlots,
        schema_candidates: SchemaCandidates,
        state: dict | None = None,
        config: RunnableConfig | None = None,
        error_feedback: str | None = None,
    ) -> tuple[Step1Output, str]:
        """执行 Step1 - 从候选集中选择"""
        # 构建 prompt（注入候选摘要，非全量字段）
        messages = STEP1_PROMPT_V2.format_messages(
            question=canonical_question,
            time_context=time_context.model_dump() if time_context else None,
            slots=memory_slots.model_dump(),
            schema_candidates=schema_candidates.to_prompt_summary(),
            error_feedback=error_feedback,
        )
        
        # LLM 调用
        response = await call_llm_with_tools(...)
        
        # 解析（字段引用为候选 ID）
        result = parse_json_response(response.content, Step1OutputV2)
        
        return result, thinking
```

### 4. Computation Planner 组件

**文件**: `components/computation_planner.py`

#### 4.1 核心概念：partition_by 与 addressing 的推断

**Tableau 表计算的核心概念**：

| 概念 | 含义 | API 字段 | 推断规则 |
|------|------|----------|----------|
| **Partitioning** | 分区：在哪些维度上"重新开始"计算 | `dimensions` | 计算在这些维度内进行，每个分区独立计算 |
| **Addressing** | 寻址：沿着哪些维度进行计算 | 隐式（查询维度 - dimensions） | 计算沿着这些维度进行 |
| **Restart Every** | 重新开始：在哪个维度上重新开始累计 | `restartEvery` | **仅 RUNNING_TOTAL/CUSTOM/NESTED 支持** |

**关键洞察**：
- `dimensions` 在 API 中是 **必填字段**，对应 Tableau 的 **Partitioning（分区）**
- `restartEvery` 是 **可选字段**，**仅部分表计算类型支持**（见下方支持矩阵）
- 代码实现中：`comp.partition_by` → API `dimensions`

**⚠️ restartEvery 支持矩阵（基于 OpenAPI 规范）**：

| tableCalcType | dimensions | restartEvery | levelAddress | 其他特有字段 |
|---------------|------------|--------------|--------------|-------------|
| `PERCENT_OF_TOTAL` | ✅ 必填 | ❌ 不支持 | ✅ 可选 | customSort |
| `RANK` | ✅ 必填 | ❌ 不支持 | ❌ | rankType, direction |
| `PERCENTILE` | ✅ 必填 | ❌ 不支持 | ❌ | direction |
| `RUNNING_TOTAL` | ✅ 必填 | ✅ 可选 | ❌ | aggregation, customSort |
| `MOVING_CALCULATION` | ✅ 必填 | ❌ 不支持 | ❌ | aggregation, previous, next, includeCurrent |
| `DIFFERENCE_FROM` | ✅ 必填 | ❌ 不支持 | ✅ 可选 | relativeTo, customSort |
| `PERCENT_DIFFERENCE_FROM` | ✅ 必填 | ❌ 不支持 | ✅ 可选 | relativeTo, customSort |
| `CUSTOM` | ✅ 必填 | ✅ 可选 | ✅ 可选 | customSort |
| `NESTED` | ✅ 必填 | ✅ 可选 | ✅ 可选 | fieldCaption, customSort |

**设计约束**：
- 对于不支持 `restartEvery` 的类型，分区语义只能通过 `dimensions` 表达
- 如果需要"按某维度重新开始"但该类型不支持 `restartEvery`，需要将该维度放入 `dimensions`

#### 4.2 快速表计算 API 映射

根据 `openapi.json` 中的 `TableCalcSpecification`，我们优先使用快速表计算 API 而非自定义公式：

```python
# ============================================================
# 快速表计算类型映射（how_type → tableCalcType）
# ============================================================

HOW_TYPE_TO_TABLE_CALC_TYPE: dict[HowType, str] = {
    HowType.PERCENT_OF_TOTAL: "PERCENT_OF_TOTAL",
    HowType.RANKING: "RANK",
    HowType.CUMULATIVE: "RUNNING_TOTAL",
    HowType.MOVING_AVG: "MOVING_CALCULATION",
    HowType.YOY: "PERCENT_DIFFERENCE_FROM",  # relativeTo=PREVIOUS, 时间粒度=年
    HowType.MOM: "PERCENT_DIFFERENCE_FROM",  # relativeTo=PREVIOUS, 时间粒度=月
    HowType.DIFFERENCE: "DIFFERENCE_FROM",
    HowType.PERCENTILE: "PERCENTILE",
}

# ============================================================
# API 字段说明（已对齐 OpenAPI 规范）
# ============================================================

"""
TableCalcSpecification 核心字段：

1. tableCalcType (必填): 计算类型枚举
   - PERCENT_OF_TOTAL: 占比
   - RANK: 排名
   - RUNNING_TOTAL: 累计
   - MOVING_CALCULATION: 移动计算
   - DIFFERENCE_FROM / PERCENT_DIFFERENCE_FROM / PERCENT_FROM: 差异计算

2. dimensions (必填): 分区维度列表 = Partitioning
   - 计算在这些维度内进行分区
   - 对应内部 IR 的 partition_by
   - 格式: [{"fieldCaption": "Region"}, {"fieldCaption": "Month"}]
   - 空数组 [] 表示全局计算（不分区）

3. levelAddress (可选): 粒度级别
   - 控制计算在哪个维度级别进行
   - 用于层级维度（如 年→季→月）

4. restartEvery (可选): 重新开始维度
   - ⚠️ 仅 RUNNING_TOTAL/CUSTOM/NESTED 支持！
   - 其他类型（PERCENT_OF_TOTAL/RANK/MOVING_CALCULATION 等）不支持
   - 在这个维度上重新开始计算
   - 例如：按年重新开始累计

5. relativeTo (差异计算专用): PREVIOUS / NEXT / FIRST / LAST
   - 同比/环比用 PREVIOUS

6. aggregation (累计/移动计算专用): SUM / AVG / MIN / MAX
   - 累计求和用 SUM
   - 移动平均用 AVG
"""
```

#### 4.3 partition_by 与 addressing 推断规则

```python
# ============================================================
# 推断规则详解（已对齐 OpenAPI 规范）
# ============================================================

"""
核心公式：
  全部维度 = partition_by ∪ addressing
  partition_by ∩ addressing = ∅ (互斥)

API 映射：
  partition_by → dimensions（分区维度，必填）
  addressing → 隐式（查询维度 - partition_by）
  
⚠️ 重要：restartEvery 仅 RUNNING_TOTAL/CUSTOM/NESTED 支持！
  其他类型（PERCENT_OF_TOTAL/RANK/MOVING_CALCULATION 等）不支持 restartEvery

推断逻辑：
1. 从 Step1 获取查询维度列表: query_dimensions = step1_output.where.dimensions
2. 根据计算类型和语义推断 partition_by
3. addressing = query_dimensions - partition_by
4. partition_by → API dimensions

常见场景推断规则：

┌─────────────────────────────────────────────────────────────────────────┐
│ 场景 1: "各地区销售额占比"                                               │
├─────────────────────────────────────────────────────────────────────────┤
│ 语义: 每个地区的销售额占总销售额的百分比                                  │
│ query_dimensions: ["Region"]                                            │
│ partition_by: [] (空 = 全局计算，不分区)                                 │
│ addressing: ["Region"] (沿着地区维度计算)                                │
│                                                                         │
│ API 输出:                                                               │
│ {                                                                       │
│   "tableCalcType": "PERCENT_OF_TOTAL",                                  │
│   "dimensions": []  // partition_by = 空，全局计算                       │
│   // ❌ 不能使用 restartEvery，PERCENT_OF_TOTAL 不支持                   │
│ }                                                                       │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ 场景 2: "各地区每月销售额占比"（按地区分区）                             │
├─────────────────────────────────────────────────────────────────────────┤
│ 语义: 每个地区内，各月销售额占该地区总销售额的百分比                      │
│ query_dimensions: ["Region", "Month"]                                   │
│ partition_by: ["Region"] (按地区分区，每个地区内部计算占比)              │
│ addressing: ["Month"] (沿着月份维度计算)                                 │
│                                                                         │
│ API 输出:                                                               │
│ {                                                                       │
│   "tableCalcType": "PERCENT_OF_TOTAL",                                  │
│   "dimensions": [{"fieldCaption": "Region"}]  // partition_by           │
│   // ❌ 不能使用 restartEvery，PERCENT_OF_TOTAL 不支持                   │
│   // 分区语义通过 dimensions 表达                                        │
│ }                                                                       │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ 场景 3: "各地区销售额排名"                                               │
├─────────────────────────────────────────────────────────────────────────┤
│ 语义: 按销售额对地区进行排名                                             │
│ query_dimensions: ["Region"]                                            │
│ partition_by: [] (全局排名)                                              │
│ addressing: ["Region"] (沿着地区维度排名)                                │
│                                                                         │
│ API 输出:                                                               │
│ {                                                                       │
│   "tableCalcType": "RANK",                                              │
│   "dimensions": [],  // partition_by = 空，全局排名                      │
│   "rankType": "COMPETITION",                                            │
│   "direction": "DESC"                                                   │
│   // ❌ RANK 不支持 restartEvery                                         │
│ }                                                                       │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ 场景 4: "各地区每月销售额累计"（✅ 支持 restartEvery）                   │
├─────────────────────────────────────────────────────────────────────────┤
│ 语义: 每个地区按月累计销售额                                             │
│ query_dimensions: ["Region", "Month"]                                   │
│ partition_by: ["Region"] (按地区分区，每个地区内部累计)                  │
│ addressing: ["Month"] (沿着月份维度累计)                                 │
│                                                                         │
│ ✅ 规范化 API 输出（使用 restartEvery 表达分区 - 唯一推荐方式）:         │
│ {                                                                       │
│   "tableCalcType": "RUNNING_TOTAL",                                     │
│   "dimensions": [],  // addressing 为空（沿默认方向累计）               │
│   "restartEvery": {"fieldCaption": "Region"}, // partitioning（分区）   │
│   "aggregation": "SUM"                                                  │
│ }                                                                       │
│                                                                         │
│ ⚠️ 设计决策说明：                                                        │
│ RUNNING_TOTAL 同时支持 restartEvery 和 dimensions 两种分区表达方式，    │
│ 为保证生成一致性，本系统统一采用 restartEvery 方式：                     │
│ - partition_by → restartEvery（分区字段）                               │
│ - dimensions 留空或用于 addressing（计算方向字段，可选）                │
│                                                                         │
│ 验收要求：实现时需添加对应的单元测试验证此行为。                         │                                                                       │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ 场景 5: "销售额同比增长率"                                               │
├─────────────────────────────────────────────────────────────────────────┤
│ 语义: 与去年同期相比的增长百分比                                         │
│ query_dimensions: ["Year", "Month"] 或 ["Date"]                         │
│ partition_by: ["Month"] (按月分区，比较同月不同年)                       │
│ addressing: ["Year"] (沿着年份维度比较)                                  │
│                                                                         │
│ API 输出:                                                               │
│ {                                                                       │
│   "tableCalcType": "PERCENT_DIFFERENCE_FROM",                           │
│   "dimensions": [{"fieldCaption": "Month"}],  // partition_by           │
│   "relativeTo": "PREVIOUS"                                              │
│   // ❌ PERCENT_DIFFERENCE_FROM 不支持 restartEvery                      │
│ }                                                                       │
└─────────────────────────────────────────────────────────────────────────┘
"""
```

#### 4.4 推断算法实现

```python
class ComputationType(Enum):
    """计算类型"""
    PERCENT_OF_TOTAL = "percent_of_total"
    YOY = "yoy"
    MOM = "mom"
    RANK = "rank"
    RUNNING_TOTAL = "running_total"
    MOVING_AVG = "moving_avg"
    LOD_FIXED = "lod_fixed"
    LOD_INCLUDE = "lod_include"
    LOD_EXCLUDE = "lod_exclude"

@dataclass
class TableCalcFieldReference:
    """表计算字段引用（对应 API 中的 TableCalcFieldReference）"""
    field_caption: str
    function: str | None = None  # 可选的聚合函数

@dataclass
class TableCalcOutput:
    """快速表计算输出（对应 API 中的 TableCalcSpecification）
    
    ⚠️ dimensions 字段语义取决于 tableCalcType：
    
    | tableCalcType          | dimensions 语义 | restartEvery 支持 |
    |------------------------|-----------------|-------------------|
    | PERCENT_OF_TOTAL       | partitioning    | ❌                |
    | RANK                   | partitioning    | ❌                |
    | PERCENTILE             | partitioning    | ❌                |
    | MOVING_CALCULATION     | partitioning    | ❌                |
    | DIFFERENCE_FROM        | partitioning    | ❌                |
    | PERCENT_DIFFERENCE_FROM| partitioning    | ❌                |
    | RUNNING_TOTAL          | addressing*     | ✅                |
    | CUSTOM                 | addressing*     | ✅                |
    | NESTED                 | addressing*     | ✅                |
    
    * 当使用 restartEvery 时，dimensions 表示 addressing（计算方向）
      当不使用 restartEvery 时，dimensions 表示 partitioning（分区范围）
    """
    table_calc_type: str  # PERCENT_OF_TOTAL, RANK, RUNNING_TOTAL, etc.
    dimensions: list[TableCalcFieldReference]  # 语义取决于类型，见上表（必填）
    level_address: TableCalcFieldReference | None = None  # 粒度级别
    restart_every: TableCalcFieldReference | None = None  # 重启点（仅 RUNNING_TOTAL/CUSTOM/NESTED 支持）
    relative_to: str | None = None  # PREVIOUS/NEXT/FIRST/LAST
    rank_type: str | None = None  # COMPETITION/MODIFIED COMPETITION/DENSE/UNIQUE（对照 OpenAPI）
    direction: str | None = None  # ASC/DESC
    aggregation: str | None = None  # SUM/AVG/MIN/MAX
    previous: int | None = None  # 移动计算窗口
    next: int | None = None

class ComputationPlanner:
    """计算规划器 - 使用快速表计算 API"""
    
    def plan(
        self,
        step1_output: Step1Output,
        data_model: DataModel,
        canonical_question: str,  # 从 state.preprocess_result 传入
    ) -> tuple[TableCalcOutput | None, bool]:
        """
        规划计算
        
        Args:
            step1_output: Step1 输出
            data_model: 数据模型
            canonical_question: 规范化问题（从 state.preprocess_result.canonical_question 获取）
        
        Returns:
            (table_calc_output, needs_llm_fallback)
            - table_calc_output: 快速表计算配置，None 表示 SIMPLE 类型
            - needs_llm_fallback: 是否需要 LLM 兜底（模板无法覆盖）
        """
        if step1_output.how_type == HowType.SIMPLE:
            return None, False
        
        # 获取查询维度
        query_dimensions = self._get_query_dimensions(step1_output)
        
        # 根据 how_type 推断 partition_by 和 addressing
        partition_by, addressing = self._infer_partition_and_addressing(
            how_type=step1_output.how_type,
            query_dimensions=query_dimensions,
            canonical_question=canonical_question,
            data_model=data_model,
        )
        
        # 构建快速表计算输出
        table_calc = self._build_table_calc(
            how_type=step1_output.how_type,
            target=step1_output.what.measures[0].field_name,
            partition_by=partition_by,
            addressing=addressing,
            canonical_question=canonical_question,
        )
        
        if table_calc:
            return table_calc, False
        
        # 无法匹配，需要 LLM fallback
        return None, True
    
    def _get_query_dimensions(self, step1_output: Step1Output) -> list[str]:
        """获取查询中的所有维度"""
        return [d.field_name for d in step1_output.where.dimensions]
    
    def _infer_partition_and_addressing(
        self,
        how_type: HowType,
        query_dimensions: list[str],
        canonical_question: str,
        data_model: DataModel,
    ) -> tuple[list[str], list[str]]:
        """
        推断 partition_by 和 addressing
        
        核心规则：
        1. 全部维度 = partition_by ∪ addressing
        2. partition_by ∩ addressing = ∅
        3. 默认情况：partition_by = [], addressing = 全部维度
        4. 特殊情况：根据语义和维度类型调整
        """
        # 识别时间维度和非时间维度
        time_dims = []
        non_time_dims = []
        
        for dim in query_dimensions:
            field_meta = data_model.get_field(dim)
            if field_meta and self._is_time_dimension(field_meta):
                time_dims.append(dim)
            else:
                non_time_dims.append(dim)
        
        # 根据计算类型推断
        if how_type == HowType.PERCENT_OF_TOTAL:
            return self._infer_percent_of_total(
                query_dimensions, time_dims, non_time_dims, canonical_question
            )
        
        elif how_type == HowType.RANKING:
            return self._infer_ranking(
                query_dimensions, time_dims, non_time_dims, canonical_question
            )
        
        elif how_type == HowType.CUMULATIVE:
            return self._infer_cumulative(
                query_dimensions, time_dims, non_time_dims, canonical_question
            )
        
        elif how_type in (HowType.YOY, HowType.MOM):
            return self._infer_time_comparison(
                how_type, query_dimensions, time_dims, non_time_dims
            )
        
        elif how_type == HowType.MOVING_AVG:
            return self._infer_moving_calc(
                query_dimensions, time_dims, non_time_dims
            )
        
        # 默认：全局计算
        return [], query_dimensions
    
    def _infer_percent_of_total(
        self,
        query_dimensions: list[str],
        time_dims: list[str],
        non_time_dims: list[str],
        canonical_question: str,
    ) -> tuple[list[str], list[str]]:
        """
        推断占比计算的 partition_by 和 addressing
        
        规则：
        1. 单维度：partition_by=[], addressing=[该维度]
        2. 多维度 + 问题含"每X的Y占比"：partition_by=[X], addressing=[Y]
        3. 多维度 + 无明确分区语义：partition_by=[], addressing=全部维度
        """
        if len(query_dimensions) == 1:
            # 单维度：全局占比
            return [], query_dimensions
        
        # 多维度：检查是否有明确的分区语义
        # 例如："各地区每月销售额占比" → 按地区分区
        partition_patterns = [
            (r"每个?(\w+)的", 1),  # "每个地区的"
            (r"各(\w+).*占比", 1),  # "各地区...占比"
            (r"按(\w+).*占比", 1),  # "按地区...占比"
        ]
        
        for pattern, group in partition_patterns:
            match = re.search(pattern, canonical_question)
            if match:
                partition_hint = match.group(group)
                # 尝试匹配到具体维度
                for dim in non_time_dims:
                    if partition_hint in dim or dim in partition_hint:
                        partition_by = [dim]
                        addressing = [d for d in query_dimensions if d != dim]
                        return partition_by, addressing
        
        # 默认：全局占比
        return [], query_dimensions
    
    def _infer_ranking(
        self,
        query_dimensions: list[str],
        time_dims: list[str],
        non_time_dims: list[str],
        canonical_question: str,
    ) -> tuple[list[str], list[str]]:
        """
        推断排名计算的 partition_by 和 addressing
        
        规则：
        1. 单维度：partition_by=[], addressing=[该维度]
        2. 多维度 + 含时间维度：partition_by=[时间维度], addressing=[非时间维度]
           （每个时间点内排名）
        3. 多维度 + 无时间维度：partition_by=[], addressing=全部维度
        """
        if len(query_dimensions) == 1:
            return [], query_dimensions
        
        # 多维度 + 含时间维度：按时间分区
        if time_dims and non_time_dims:
            return time_dims, non_time_dims
        
        # 默认：全局排名
        return [], query_dimensions
    
    def _infer_cumulative(
        self,
        query_dimensions: list[str],
        time_dims: list[str],
        non_time_dims: list[str],
        canonical_question: str,
    ) -> tuple[list[str], list[str]]:
        """
        推断累计计算的 partition_by 和 addressing
        
        规则：
        1. 含时间维度：addressing=[时间维度], partition_by=[非时间维度]
           （沿时间累计，按其他维度分区）
        2. 无时间维度：addressing=全部维度, partition_by=[]
        """
        if time_dims:
            # 沿时间累计，按非时间维度分区
            return non_time_dims, time_dims
        
        # 无时间维度：全局累计
        return [], query_dimensions
    
    def _infer_time_comparison(
        self,
        how_type: HowType,
        query_dimensions: list[str],
        time_dims: list[str],
        non_time_dims: list[str],
    ) -> tuple[list[str], list[str]]:
        """
        推断同比/环比的 partition_by 和 addressing
        
        规则：
        - 同比(YoY)：addressing=[年], partition_by=[月/季/周等]
        - 环比(MoM)：addressing=[月], partition_by=[年]
        """
        if how_type == HowType.YOY:
            # 同比：沿年份比较
            year_dims = [d for d in time_dims if "year" in d.lower() or "年" in d]
            other_time_dims = [d for d in time_dims if d not in year_dims]
            
            if year_dims:
                return other_time_dims + non_time_dims, year_dims
        
        elif how_type == HowType.MOM:
            # 环比：沿月份比较
            month_dims = [d for d in time_dims if "month" in d.lower() or "月" in d]
            other_time_dims = [d for d in time_dims if d not in month_dims]
            
            if month_dims:
                return other_time_dims + non_time_dims, month_dims
        
        # 默认
        return non_time_dims, time_dims
    
    def _infer_moving_calc(
        self,
        query_dimensions: list[str],
        time_dims: list[str],
        non_time_dims: list[str],
    ) -> tuple[list[str], list[str]]:
        """
        推断移动计算的 partition_by 和 addressing
        
        规则：沿时间维度移动，按非时间维度分区
        """
        if time_dims:
            return non_time_dims, time_dims
        
        return [], query_dimensions
    
    def _is_time_dimension(self, field_meta: FieldMetadata) -> bool:
        """判断是否为时间维度"""
        # 根据字段类型或名称判断
        # 注意：这里的 DATE/DATETIME 是内部数据源元数据类型，
        # 非 OpenAPI DataType（OpenAPI 只有 DATE/DATETIME，无 TIMESTAMP）
        if field_meta.data_type in ("DATE", "DATETIME"):
            return True
        
        time_keywords = ["date", "time", "year", "month", "day", "quarter", "week",
                        "日期", "时间", "年", "月", "日", "季", "周"]
        field_name_lower = field_meta.field_caption.lower()
        
        return any(kw in field_name_lower for kw in time_keywords)
    
    def _build_table_calc(
        self,
        how_type: HowType,
        target: str,
        partition_by: list[str],
        addressing: list[str],
        canonical_question: str,
    ) -> TableCalcOutput | None:
        """构建快速表计算输出（已对齐 OpenAPI 规范）
        
        ⚠️ 重要：restartEvery 仅以下类型支持：
        - RUNNING_TOTAL ✅
        - CUSTOM ✅
        - NESTED ✅
        
        其他类型（PERCENT_OF_TOTAL/RANK/MOVING_CALCULATION 等）不支持 restartEvery，
        分区语义通过 dimensions 表达。
        """
        
        # 根据 how_type 构建具体配置
        if how_type == HowType.PERCENT_OF_TOTAL:
            # ❌ PERCENT_OF_TOTAL 不支持 restartEvery
            # 分区语义通过 dimensions 表达
            dimensions = [TableCalcFieldReference(field_caption=d) for d in partition_by]
            return TableCalcOutput(
                table_calc_type="PERCENT_OF_TOTAL",
                dimensions=dimensions,
                # restart_every=None  # 不支持
            )
        
        elif how_type == HowType.RANKING:
            # ❌ RANK 不支持 restartEvery
            # 分区语义通过 dimensions 表达
            dimensions = [TableCalcFieldReference(field_caption=d) for d in partition_by]
            return TableCalcOutput(
                table_calc_type="RANK",
                dimensions=dimensions,
                rank_type="COMPETITION",
                direction="DESC",
                # restart_every=None  # 不支持
            )
        
        elif how_type == HowType.CUMULATIVE:
            # ✅ RUNNING_TOTAL 支持 restartEvery
            # ⚠️ 本系统统一采用 restartEvery 方式，dimensions 留空
            # 这样可以避免"双口径"导致的实现分叉和验收困难
            restart_every = None
            if partition_by:
                if len(partition_by) == 1:
                    restart_every = TableCalcFieldReference(field_caption=partition_by[0])
                else:
                    # ⚠️ 多个 partition_by 时的降级策略（硬规则）：
                    # restartEvery 只支持单字段，多字段分区无法用 RUNNING_TOTAL 表达
                    # → 返回 None，由上层决定：
                    #   1. 降级到 CUSTOM 类型（需要手写表达式）
                    #   2. 或进入 Step2 LLM fallback
                    logger.warning(
                        f"RUNNING_TOTAL 不支持多字段分区: {partition_by}，"
                        f"降级到 Step2 LLM fallback"
                    )
                    return None
            return TableCalcOutput(
                table_calc_type="RUNNING_TOTAL",
                dimensions=[],  # 留空，统一使用 restartEvery
                restart_every=restart_every,
                aggregation="SUM",
            )
        
        elif how_type in (HowType.YOY, HowType.MOM):
            # ❌ PERCENT_DIFFERENCE_FROM 不支持 restartEvery
            # 分区语义通过 dimensions 表达
            dimensions = [TableCalcFieldReference(field_caption=d) for d in partition_by]
            return TableCalcOutput(
                table_calc_type="PERCENT_DIFFERENCE_FROM",
                dimensions=dimensions,
                relative_to="PREVIOUS",
                # restart_every=None  # 不支持
            )
        
        elif how_type == HowType.MOVING_AVG:
            # ❌ MOVING_CALCULATION 不支持 restartEvery
            # 分区语义通过 dimensions 表达
            dimensions = [TableCalcFieldReference(field_caption=d) for d in partition_by]
            return TableCalcOutput(
                table_calc_type="MOVING_CALCULATION",
                dimensions=dimensions,
                aggregation="AVG",
                previous=2,  # 默认前2期
                next=0,
                # restart_every=None  # 不支持
            )
        
        return None
```

#### 4.5 与 VizQL API 的集成

```python
# restartEvery 支持的类型（基于 OpenAPI 规范）
RESTART_EVERY_SUPPORTED_TYPES = {"RUNNING_TOTAL", "CUSTOM", "NESTED"}

def table_calc_output_to_api_spec(
    table_calc: TableCalcOutput,
    target_field: str,
    target_function: str = "SUM",
) -> dict:
    """
    将 TableCalcOutput 转换为 VizQL API 的 TableCalcField 格式
    
    对应 openapi.json 中的 TableCalcField schema
    
    ⚠️ 重要：restartEvery 仅以下类型支持：
    - RUNNING_TOTAL ✅
    - CUSTOM ✅
    - NESTED ✅
    """
    # 构建 tableCalculation 部分
    table_calculation = {
        "tableCalcType": table_calc.table_calc_type,
        "dimensions": [
            {"fieldCaption": d.field_caption}
            for d in table_calc.dimensions
        ],
    }
    
    # 添加可选字段（带类型检查）
    if table_calc.restart_every:
        # ⚠️ 只有支持的类型才能添加 restartEvery
        if table_calc.table_calc_type in RESTART_EVERY_SUPPORTED_TYPES:
            table_calculation["restartEvery"] = {
                "fieldCaption": table_calc.restart_every.field_caption
            }
        else:
            # 不支持的类型，记录警告但不添加该字段
            logger.warning(
                f"restartEvery not supported for {table_calc.table_calc_type}, "
                f"ignoring partition_by. Use dimensions for partitioning instead."
            )
    
    if table_calc.level_address:
        table_calculation["levelAddress"] = {
            "fieldCaption": table_calc.level_address.field_caption
        }
    
    if table_calc.relative_to:
        table_calculation["relativeTo"] = table_calc.relative_to
    
    if table_calc.rank_type:
        table_calculation["rankType"] = table_calc.rank_type
    
    if table_calc.direction:
        table_calculation["direction"] = table_calc.direction
    
    if table_calc.aggregation:
        table_calculation["aggregation"] = table_calc.aggregation
    
    if table_calc.previous is not None:
        table_calculation["previous"] = table_calc.previous
    
    if table_calc.next is not None:
        table_calculation["next"] = table_calc.next
    
    # 构建完整的 TableCalcField
    return {
        "fieldCaption": f"{target_field}_{table_calc.table_calc_type}",
        "function": target_function,
        "tableCalculation": table_calculation,
    }
```

#### 4.6 完整示例：从用户问题到 API 调用

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 示例 1: "各地区销售额占比是多少？"                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│ Step 1: 用户输入                                                            │
│ ─────────────────                                                           │
│ question = "各地区销售额占比是多少？"                                        │
│                                                                             │
│ Step 2: Layer 1 预处理                                                      │
│ ─────────────────────                                                       │
│ canonical_question = "各地区销售额占比"                                      │
│ time_context = None                                                         │
│                                                                             │
│ Step 3: Layer 2 Schema Linking                                              │
│ ──────────────────────────────                                              │
│ schema_candidates = {                                                       │
│   dimensions: [                                                             │
│     {candidate_id: "dim_0", field_caption: "Region", score: 0.95}           │
│   ],                                                                        │
│   measures: [                                                               │
│     {candidate_id: "meas_0", field_caption: "Sales", score: 0.92}           │
│   ]                                                                         │
│ }                                                                           │
│                                                                             │
│ Step 4: Layer 3 Step1 语义解析                                              │
│ ────────────────────────────                                                │
│ step1_output = {                                                            │
│   what: {measures: [{field_name: "Sales", aggregation: "SUM"}]},            │
│   where: {dimensions: [{field_name: "Region"}]},                            │
│   how_type: "PERCENT_OF_TOTAL"                                              │
│   // ⚠️ canonical_question 不在 step1_output 中                              │
│   // 从 state.preprocess_result.canonical_question 获取                      │
│ }                                                                           │
│                                                                             │
│ Step 5: Layer 4 ComputationPlanner 推断                                     │
│ ─────────────────────────────────────                                       │
│ query_dimensions = ["Region"]                                               │
│ time_dims = []                                                              │
│ non_time_dims = ["Region"]                                                  │
│                                                                             │
│ 推断规则（单维度占比）:                                                      │
│   partition_by = []  (空 = 全局计算)                                        │
│   addressing = ["Region"]  (沿地区维度计算)                                  │
│                                                                             │
│ table_calc_output = TableCalcOutput(                                        │
│   table_calc_type = "PERCENT_OF_TOTAL",                                     │
│   dimensions = []  // partition_by = 空，全局计算                            │
│   // ❌ 不能使用 restart_every，PERCENT_OF_TOTAL 不支持                      │
│ )                                                                           │
│                                                                             │
│ Step 6: 生成 VizQL API 请求                                                 │
│ ─────────────────────────                                                   │
│ {                                                                           │
│   "fields": [                                                               │
│     {"fieldCaption": "Region"},                                             │
│     {                                                                       │
│       "fieldCaption": "Sales_PERCENT_OF_TOTAL",                             │
│       "function": "SUM",                                                    │
│       "tableCalculation": {                                                 │
│         "tableCalcType": "PERCENT_OF_TOTAL",                                │
│         "dimensions": []  // 空 = 全局计算                                   │
│       }                                                                     │
│     }                                                                       │
│   ]                                                                         │
│ }                                                                           │
│                                                                             │
│ 结果解读:                                                                   │
│ - 每个地区的销售额占总销售额的百分比                                         │
│ - Region=East: 25%, Region=West: 35%, Region=North: 20%, Region=South: 20%  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ 示例 2: "各地区每月销售额占比"（按地区分区）                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│ Step 1-4: 同上，但 step1_output 包含两个维度                                 │
│ ──────────────────────────────────────────                                  │
│ step1_output = {                                                            │
│   what: {measures: [{field_name: "Sales", aggregation: "SUM"}]},            │
│   where: {dimensions: [                                                     │
│     {field_name: "Region"},                                                 │
│     {field_name: "Month"}                                                   │
│   ]},                                                                       │
│   how_type: "PERCENT_OF_TOTAL"                                              │
│   // ⚠️ canonical_question 不在 step1_output 中                              │
│   // 从 state.preprocess_result.canonical_question 获取                      │
│ }                                                                           │                                                                           │
│                                                                             │
│ Step 5: ComputationPlanner 推断                                             │
│ ──────────────────────────────                                              │
│ query_dimensions = ["Region", "Month"]                                      │
│ time_dims = ["Month"]                                                       │
│ non_time_dims = ["Region"]                                                  │
│                                                                             │
│ 语义分析: "各地区每月" → 按地区分区，每个地区内部计算月度占比                 │
│                                                                             │
│ 推断规则（多维度 + 明确分区语义）:                                           │
│   partition_by = ["Region"]  (按地区分区)                                   │
│   addressing = ["Month"]  (沿月份维度计算)                                   │
│                                                                             │
│ ⚠️ 注意：PERCENT_OF_TOTAL 不支持 restartEvery！                              │
│ 分区语义通过 dimensions 表达                                                 │
│                                                                             │
│ table_calc_output = TableCalcOutput(                                        │
│   table_calc_type = "PERCENT_OF_TOTAL",                                     │
│   dimensions = [{"fieldCaption": "Region"}]  // partition_by                │
│   // ❌ 不能使用 restart_every，PERCENT_OF_TOTAL 不支持                      │
│ )                                                                           │
│                                                                             │
│ Step 6: 生成 VizQL API 请求                                                 │
│ ─────────────────────────                                                   │
│ {                                                                           │
│   "fields": [                                                               │
│     {"fieldCaption": "Region"},                                             │
│     {"fieldCaption": "Month"},                                              │
│     {                                                                       │
│       "fieldCaption": "Sales_PERCENT_OF_TOTAL",                             │
│       "function": "SUM",                                                    │
│       "tableCalculation": {                                                 │
│         "tableCalcType": "PERCENT_OF_TOTAL",                                │
│         "dimensions": [{"fieldCaption": "Region"}]  // 分区维度              │
│         // ❌ 无 restartEvery，该类型不支持                                  │
│       }                                                                     │
│     }                                                                       │
│   ]                                                                         │
│ }                                                                           │
│                                                                             │
│ 结果解读:                                                                   │
│ - 每个地区内，各月销售额占该地区总销售额的百分比                              │
│ - East-Jan: 30%, East-Feb: 25%, East-Mar: 45%                               │
│ - West-Jan: 20%, West-Feb: 40%, West-Mar: 40%                               │
│ - 每个地区的占比加起来 = 100%                                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ 示例 3: "各地区每月销售额累计"（✅ 支持 restartEvery）                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│ Step 5: ComputationPlanner 推断                                             │
│ ──────────────────────────────                                              │
│ query_dimensions = ["Region", "Month"]                                      │
│ time_dims = ["Month"]                                                       │
│ non_time_dims = ["Region"]                                                  │
│                                                                             │
│ 推断规则（累计 + 含时间维度）:                                               │
│   partition_by = ["Region"]  (按地区分区，每个地区内部累计)                  │
│   addressing = ["Month"]  (沿月份维度累计)                                   │
│                                                                             │
│ ✅ RUNNING_TOTAL 支持 restartEvery！                                         │
│ ⚠️ 本系统统一采用 restartEvery 方式，dimensions 留空                         │
│                                                                             │
│ table_calc_output = TableCalcOutput(                                        │
│   table_calc_type = "RUNNING_TOTAL",                                        │
│   dimensions = [],  // 留空，统一使用 restartEvery 表达分区                  │
│   restart_every = {"fieldCaption": "Region"},  // partitioning（分区）      │
│   aggregation = "SUM"                                                       │
│ )                                                                           │                                                                           │
│                                                                             │
│ Step 6: 生成 VizQL API 请求                                                 │
│ ─────────────────────────                                                   │
│ {                                                                           │
│   "fields": [                                                               │
│     {"fieldCaption": "Region"},                                             │
│     {"fieldCaption": "Month"},                                              │
│     {                                                                       │
│       "fieldCaption": "Sales_RUNNING_TOTAL",                                │
│       "function": "SUM",                                                    │
│       "tableCalculation": {                                                 │
│         "tableCalcType": "RUNNING_TOTAL",                                   │
│         "dimensions": [],  // 留空，统一使用 restartEvery                    │
│         "restartEvery": {"fieldCaption": "Region"},  // partitioning（分区）│
│         "aggregation": "SUM"                                                │
│       }                                                                     │
│     }                                                                       │
│   ]                                                                         │
│ }                                                                           │
│                                                                             │
│ 结果解读:                                                                   │
│ - 每个地区按月累计销售额                                                     │
│ - East-Jan: 100, East-Feb: 250 (100+150), East-Mar: 450 (250+200)           │
│ - West-Jan: 80, West-Feb: 200 (80+120), West-Mar: 380 (200+180)             │
│ - 每个地区从 Jan 重新开始累计                                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ 示例 4: "销售额排名"                                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│ Step 5: ComputationPlanner 推断                                             │
│ ──────────────────────────────                                              │
│ query_dimensions = ["Region"]                                               │
│                                                                             │
│ 推断规则（排名 + 单维度）:                                                   │
│   partition_by = []  (全局排名)                                              │
│   addressing = ["Region"]  (沿地区维度排名)                                  │
│                                                                             │
│ ⚠️ RANK 不支持 restartEvery！                                                │
│                                                                             │
│ table_calc_output = TableCalcOutput(                                        │
│   table_calc_type = "RANK",                                                 │
│   dimensions = []  // partition_by = 空，全局排名                            │
│   rank_type = "COMPETITION",                                                │
│   direction = "DESC"                                                        │
│   // ❌ 不能使用 restart_every，RANK 不支持                                  │
│ )                                                                           │
│                                                                             │
│ Step 6: 生成 VizQL API 请求                                                 │
│ ─────────────────────────                                                   │
│ {                                                                           │
│   "fields": [                                                               │
│     {"fieldCaption": "Region"},                                             │
│     {                                                                       │
│       "fieldCaption": "Sales_RANK",                                         │
│       "function": "SUM",                                                    │
│       "tableCalculation": {                                                 │
│         "tableCalcType": "RANK",                                            │
│         "dimensions": [],  // 空 = 全局排名                                  │
│         "rankType": "COMPETITION",                                          │
│         "direction": "DESC"                                                 │
│       }                                                                     │
│     }                                                                       │
│   ]                                                                         │
│ }                                                                           │
│                                                                             │
│ 结果解读:                                                                   │
│ - 按销售额对所有地区进行排名                                                 │
│ - West: 1, East: 2, North: 3, South: 4                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 4.7 partition_by 与 addressing 推断决策树

```
                    ┌─────────────────────────┐
                    │ 输入: how_type,         │
                    │ query_dimensions,       │
                    │ canonical_question      │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │ how_type == SIMPLE?     │
                    └───────────┬─────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │ Yes             │ No              │
              ▼                 ▼                 │
    ┌─────────────────┐  ┌─────────────────┐     │
    │ 无表计算        │  │ 继续推断        │     │
    │ return None     │  └────────┬────────┘     │
    └─────────────────┘           │              │
                                  │              │
                    ┌─────────────▼─────────────┐
                    │ 识别时间维度 vs 非时间维度 │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │ how_type 类型分支         │
                    └─────────────┬─────────────┘
                                  │
    ┌─────────────┬───────────────┼───────────────┬─────────────┐
    │             │               │               │             │
    ▼             ▼               ▼               ▼             ▼
┌───────┐   ┌───────┐       ┌───────┐       ┌───────┐     ┌───────┐
│PERCENT│   │RANKING│       │CUMUL- │       │YoY/MoM│     │MOVING │
│OF_TOTAL   │       │       │ATIVE  │       │       │     │AVG    │
└───┬───┘   └───┬───┘       └───┬───┘       └───┬───┘     └───┬───┘
    │           │               │               │             │
    ▼           ▼               ▼               ▼             ▼
┌─────────┐ ┌─────────┐   ┌─────────┐     ┌─────────┐   ┌─────────┐
│单维度?  │ │含时间?  │   │含时间?  │     │识别年/月│   │含时间?  │
└────┬────┘ └────┬────┘   └────┬────┘     │维度     │   └────┬────┘
     │           │             │          └────┬────┘        │
  ┌──┴──┐     ┌──┴──┐       ┌──┴──┐          │           ┌──┴──┐
  │Yes  │No   │Yes  │No     │Yes  │No        │           │Yes  │No
  ▼     ▼     ▼     ▼       ▼     ▼          ▼           ▼     ▼
┌───┐ ┌───┐ ┌───┐ ┌───┐ ┌─────┐ ┌───┐   ┌─────┐     ┌─────┐ ┌───┐
│P=[]│ │检查│ │P= │ │P=[]│ │P=非 │ │P=[]│   │P=其他│     │P=非 │ │P=[]│
│A=全│ │语义│ │时间│ │A=全│ │时间 │ │A=全│   │时间  │     │时间 │ │A=全│
│部  │ │分区│ │A=非│ │部  │ │A=时│ │部  │   │A=年/│     │A=时│ │部  │
└───┘ └───┘ │时间│ └───┘ │间  │ └───┘   │月    │     │间  │ └───┘
            └───┘       └─────┘         └─────┘     └─────┘

图例:
P = partition_by
A = addressing
全部 = query_dimensions
时间 = time_dims
非时间 = non_time_dims
```

**文件**: `components/validator.py`

```python
class ValidationErrorType(Enum):
    """校验错误类型"""
    FIELD_NOT_FOUND = "field_not_found"
    TYPE_MISMATCH = "type_mismatch"
    AGGREGATION_CONFLICT = "aggregation_conflict"
    PARTITION_NOT_IN_DIMS = "partition_not_in_dims"
    DUPLICATE_FIELD = "duplicate_field"
    PERMISSION_DENIED = "permission_denied"

@dataclass
class ValidationError:
    """校验错误"""
    type: ValidationErrorType
    message: str
    field: str | None = None
    can_fix: bool = False
    fix_suggestion: str | None = None

@dataclass
class ValidationResult:
    """校验结果"""
    valid: bool
    errors: list[ValidationError]
    fixed_output: Step1Output | None = None  # 自动修复后的输出
    clarification: ClarificationRequest | None = None

class Validator:
    """校验器 - 确定性校验 + 规则修复"""
    
    def validate(
        self,
        step1_output: Step1Output,
        computations: list[Computation] | None,
        data_model: DataModel,
    ) -> ValidationResult:
        """执行校验"""
        errors = []
        
        # 1. 字段存在性
        errors.extend(self._check_field_existence(step1_output, data_model))
        
        # 2. 类型匹配
        errors.extend(self._check_type_match(step1_output, data_model))
        
        # 3. 聚合合法性
        errors.extend(self._check_aggregation(step1_output, data_model))
        
        # 4. partition_by ⊆ query_dimensions
        if computations:
            errors.extend(self._check_partition_constraint(computations, step1_output))
        
        # 5. 字段去重
        errors.extend(self._check_duplicates(step1_output))
        
        # 尝试自动修复
        if errors and all(e.can_fix for e in errors):
            fixed = self._auto_fix(step1_output, errors)
            return ValidationResult(valid=True, errors=[], fixed_output=fixed)
        
        # 需要澄清
        if any(e.type == ValidationErrorType.FIELD_NOT_FOUND for e in errors):
            clarification = self._build_clarification(errors)
            return ValidationResult(valid=False, errors=errors, clarification=clarification)
        
        return ValidationResult(valid=len(errors) == 0, errors=errors)
```

### 6. 统一澄清协议

**文件**: `models/clarification.py`

```python
class ClarificationType(str, Enum):
    """澄清类型
    
    ⚠️ 枚举值使用大写，与 requirements.md 保持一致。
    对外 API 契约值：FIELD_AMBIGUOUS | LOW_CONFIDENCE | FILTER_VALUE_NOT_FOUND | MULTIPLE_INTERPRETATION
    """
    FIELD_AMBIGUOUS = "FIELD_AMBIGUOUS"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    FILTER_VALUE_NOT_FOUND = "FILTER_VALUE_NOT_FOUND"
    MULTIPLE_INTERPRETATION = "MULTIPLE_INTERPRETATION"  # 扩展：多种解释可能

class ClarificationOption(BaseModel):
    """澄清选项
    
    ⚠️ 使用 Pydantic BaseModel（而非 dataclass）以保证：
    - 与 ClarificationRequest 序列化方式一致
    - 支持 .model_dump() 统一序列化
    - 支持 JSON Schema 生成
    """
    id: str
    label: str
    description: str | None = None
    field_name: str | None = None

class ClarificationRequest(BaseModel):
    """统一澄清请求
    
    对外契约：
    - type: 大写枚举值（FIELD_AMBIGUOUS | LOW_CONFIDENCE | FILTER_VALUE_NOT_FOUND | MULTIPLE_INTERPRETATION）
    - options: 候选选项列表（对外 API 统一使用 options，与 requirements.md 保持一致）
    - message: 用户友好的澄清问题
    """
    type: ClarificationType
    message: str  # 用户友好的问题
    options: list[ClarificationOption]  # 对外 API 字段名（requirements.md 统一为 options）
    context: dict | None = None  # 额外上下文
    
    def to_user_message(self) -> str:
        """生成用户消息"""
        lines = [self.message]
        for i, opt in enumerate(self.options, 1):
            lines.append(f"{i}. {opt.label}")
            if opt.description:
                lines.append(f"   {opt.description}")
        return "\n".join(lines)
```

## 数据模型

### 扩展 SemanticParserState

```python
class SemanticParserState(VizQLState):
    """扩展状态
    
    ⚠️ 重要：此处展示的是概念模型，用于说明各层产出的数据。
    实际持久化形态遵循 2.0.1 节的 State 序列化原则：
    - 所有复杂对象在存入 State 前必须调用 .model_dump() 转为 dict
    - 从 State 读取后需要重新构造对象
    
    持久化形态示例：
    - time_context: dict | None  # TimeContext.model_dump()
    - memory_slots: dict | None  # MemorySlots.model_dump()
    - schema_candidates: dict | None  # SchemaCandidates.model_dump()
    - step1_output: dict | None  # Step1Output.model_dump()
    """
    
    # 新增字段 - Layer 1（存储为 dict）
    canonical_question: str | None  # 基本类型，直接存储
    time_context: dict | None  # TimeContext.model_dump()
    memory_slots: dict | None  # MemorySlots.model_dump()
    
    # 新增字段 - Layer 2（存储为 dict）
    schema_candidates: dict | None  # SchemaCandidates.model_dump()
    
    # 新增字段 - Layer 4（存储为 list[dict]）
    computation_plan: list[dict] | None  # [Computation.model_dump(), ...]
    planner_used_template: bool | None  # 基本类型，直接存储
    
    # 新增字段 - Layer 5（存储为 dict）
    validation_result: dict | None  # ValidationResult.model_dump()
    
    # 现有字段保留（存储为 dict）
    step1_output: dict | None  # Step1Output.model_dump()
    step2_output: dict | None  # Step2Output.model_dump()
    ...

# 读写示例
def write_to_state(state: SemanticParserState, time_ctx: TimeContext):
    """写入 State - 复杂对象转 dict"""
    state.time_context = time_ctx.model_dump()

def read_from_state(state: SemanticParserState) -> TimeContext | None:
    """从 State 读取 - dict 转复杂对象"""
    if state.time_context:
        return TimeContext.model_validate(state.time_context)
    return None
```

## 正确性属性

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: 时间解析一致性
*For any* 用户问题包含相对时间表达（如"上月"、"近7天"），`extract_time()` 解析的 `[start_date, end_date]` 应该与当前日期一致，且 `is_relative=True`。
**Validates: Requirements 1.3**

### Property 2: Canonical Question 稳定性
*For any* 相同语义的用户问题（仅时间表达不同），`build_canonical()` 生成的 `canonical_question` 应该相同（时间部分被标准化）。
**Validates: Requirements 1.5**

### Property 3: Schema Linking 召回率
*For any* 用户问题中提到的字段，如果该字段存在于数据模型中，则 `schema_candidates` 应该包含该字段（召回率 ≥ 95%）。
**Validates: Requirements 2.2, 2.3**

### Property 4: Step1 候选约束
*For any* Step1 输出的字段引用，该字段必须存在于 `schema_candidates` 中（除非使用 RAG fallback）。
**Validates: Requirements 3.2**

### Property 5: 计算模板正确性
*For any* 匹配到计算模板的问题，生成的 `Computation` 应该与模板定义一致，且 `partition_by ⊆ query_dimensions`。
**Validates: Requirements 4.2, 4.3**

### Property 6: Validator 完备性
*For any* 校验通过的 `Step1Output`，后续 `BuildQuery` 不应因字段不存在、类型不匹配、聚合冲突而失败。
**Validates: Requirements 5.2**

### Property 7: 澄清协议一致性
*For any* 触发澄清的场景，`ClarificationRequest` 应该包含至少一个有效选项，且选项与错误类型匹配。
**Validates: Requirements 14.1, 14.2**

### Property 8: 缓存键唯一性
*For any* 不同语义的问题，`hash(canonical_question + current_date)` 应该不同；相同语义的问题应该相同。
**Validates: Requirements 10.4**

### Property 9: 精确匹配 O(1)
*For any* 精确匹配查询，`_try_exact_match()` 的时间复杂度应该是 O(1)，不随字段数量增长。
**Validates: Requirements 8.2**

### Property 10: LOD vs 表计算决策正确性
*For any* 占比/份额类问题，`ComputationPlanner` 应该生成 `PERCENT_OF_TOTAL`（表计算），而非 `LOD_FIXED`。
*For any* 粒度改变类问题（如"每客户销售额"），应该生成 `LOD_FIXED/INCLUDE/EXCLUDE`。
**Validates: Requirements 4.2**

## 错误处理

### 错误分类器

```python
class ErrorClassifier:
    """确定性错误分类器"""
    
    RULE_BASED_ERRORS = {
        QueryErrorType.FIELD_NOT_FOUND: ErrorAction.CLARIFY,
        QueryErrorType.PERMISSION_DENIED: ErrorAction.ABORT,
        QueryErrorType.TYPE_MISMATCH: ErrorAction.FIX,
        QueryErrorType.AGGREGATION_CONFLICT: ErrorAction.FIX,
        QueryErrorType.TIMEOUT: ErrorAction.ABORT,
    }
    
    def classify(self, error: QueryError) -> tuple[ErrorAction, str | None]:
        """分类错误并决定动作"""
        if error.type in self.RULE_BASED_ERRORS:
            return self.RULE_BASED_ERRORS[error.type], self._get_fix_guidance(error)
        
        # 长尾错误交给 LLM
        return ErrorAction.LLM_REACT, None
```

## Reranker 超时与降级

### 超时配置

```python
@dataclass
class RerankerConfig:
    """Reranker 配置"""
    timeout_seconds: float = 3.0  # 超时时间
    fallback_on_timeout: bool = True  # 超时时降级
    fallback_on_error: bool = True  # 错误时降级
    min_candidates_for_rerank: int = 5  # 少于此数量跳过 rerank

async def rerank_with_timeout(
    candidates: list[FieldCandidate],
    query: str,
    config: RerankerConfig,
) -> list[FieldCandidate]:
    """带超时的 Rerank"""
    if len(candidates) < config.min_candidates_for_rerank:
        return candidates  # 跳过 rerank
    
    try:
        result = await asyncio.wait_for(
            _do_rerank(candidates, query),
            timeout=config.timeout_seconds,
        )
        return result
    except asyncio.TimeoutError:
        logger.warning(f"Reranker timeout after {config.timeout_seconds}s, using original order")
        metrics.rerank_timeout_count.inc()
        if config.fallback_on_timeout:
            return candidates  # 降级：返回原始顺序
        raise
    except Exception as e:
        logger.error(f"Reranker error: {e}")
        metrics.rerank_error_count.inc()
        if config.fallback_on_error:
            return candidates
        raise
```

### 降级一致性要求

- 超时降级后，候选集内容不变，仅顺序可能非最优
- 降级不影响后续流程的正确性
- 降级事件必须记录指标

## 可观测性指标

### 结构化日志 Schema

```python
@dataclass
class SemanticParserLog:
    """语义解析器结构化日志"""
    
    # 请求标识
    request_id: str
    thread_id: str
    datasource_luid: str
    
    # 时间戳
    timestamp: str  # ISO 8601
    
    # 各层耗时（毫秒）
    preprocess_ms: int
    schema_linking_ms: int
    step1_ms: int
    computation_planner_ms: int
    validator_ms: int
    pipeline_ms: int
    total_ms: int
    
    # Schema Linking 详情
    schema_linking_embedding_ms: int
    schema_linking_retrieval_ms: int
    schema_linking_rerank_ms: int
    schema_linking_cache_hit: bool
    schema_linking_is_degraded: bool
    
    # Step1 详情
    step1_prompt_tokens: int
    step1_completion_tokens: int
    step1_field_count: int  # 候选字段数
    
    # 计算规划
    planner_template_matched: bool
    planner_template_name: str | None
    step2_called: bool
    
    # 缓存
    l1_cache_hit: bool
    l2_cache_hit: bool
    
    # 结果
    success: bool
    error_type: str | None
    error_action: str | None  # ABORT/CLARIFY/FIX/LLM_REACT
    retry_count: int
    
    # Reranker
    rerank_timeout: bool
    rerank_error: bool

# 埋点位置
LOG_POINTS = {
    "preprocess_start": "PreprocessComponent.execute() 入口",
    "preprocess_end": "PreprocessComponent.execute() 出口",
    "schema_linking_start": "SchemaLinkingComponent.execute() 入口",
    "schema_linking_cache_check": "缓存检查后",
    "schema_linking_embedding": "embedding 完成后",
    "schema_linking_retrieval": "检索完成后",
    "schema_linking_rerank": "rerank 完成后",
    "schema_linking_end": "SchemaLinkingComponent.execute() 出口",
    "step1_start": "Step1Component.execute() 入口",
    "step1_llm_call": "LLM 调用完成后",
    "step1_end": "Step1Component.execute() 出口",
    # ... 其他埋点
}
```

### 指标列表

| 指标名 | 类型 | 说明 |
|--------|------|------|
| `preprocess_duration_ms` | Histogram | 预处理耗时 |
| `schema_linking_duration_ms` | Histogram | Schema Linking 耗时 |
| `schema_linking_cache_hit_rate` | Gauge | 缓存命中率 |
| `schema_linking_degraded_rate` | Gauge | 降级模式比例 |
| `step1_prompt_tokens` | Histogram | Step1 prompt token 数 |
| `step1_duration_ms` | Histogram | Step1 耗时 |
| `step1_history_tokens` | Histogram | Step1 history token 数 |
| `step1_parse_retry_count` | Counter | Step1 解析重试次数 |
| `step1_parse_retry_success_count` | Counter | Step1 解析重试成功次数 |
| `step1_parse_failure_count` | Counter | Step1 解析最终失败次数 |
| `step2_parse_retry_count` | Counter | Step2 解析重试次数 |
| `step2_parse_retry_success_count` | Counter | Step2 解析重试成功次数 |
| `step2_parse_failure_count` | Counter | Step2 解析最终失败次数 |
| `planner_template_hit_rate` | Gauge | 模板命中率 |
| `step2_call_rate` | Gauge | Step2 调用率 |
| `rerank_timeout_rate` | Gauge | Reranker 超时率 |
| `error_type_distribution` | Counter | 错误类型分布 |
| `total_duration_ms` | Histogram | 端到端耗时 |
| `json_direct_parse_failure_count` | Counter | JSON 直接解析失败次数 |
| `json_repair_success_count` | Counter | JSON 修复成功次数 |
| `json_repair_failure_count` | Counter | JSON 修复失败次数 |
| `tool_args_parse_failure_count` | Counter | tool_calls 参数解析失败次数（按 tool_name 分组） |
| `tool_args_repair_success_count` | Counter | tool_calls 参数修复成功次数 |
| `tool_args_repair_failure_count` | Counter | tool_calls 参数修复失败次数 |
| `llm_empty_response_count` | Counter | LLM 空响应次数（按 model 分组） |
| `history_truncation_count` | Counter | history 截断次数 |
| `schema_truncation_count` | Counter | schema 截断次数 |
| `middleware_hook_failure_count` | Counter | middleware 钩子执行失败次数（按 hook 和 middleware 分组） |

## 测试策略

### 单元测试
- Preprocess: 时间解析规则覆盖、规范化边界
- Schema Linking: 召回率、缓存命中
- Validator: 各类校验规则
- ComputationPlanner: 模板匹配

### 属性测试
- 使用 Hypothesis 生成随机问题，验证正确性属性
- 每个属性测试运行 100+ 次迭代

### 集成测试
- Golden set 回归测试
- 端到端延迟基准测试

### Golden Set 格式

```python
@dataclass
class GoldenSample:
    """Golden Set 样本"""
    
    # 输入
    question: str
    datasource_luid: str
    history: list[dict] | None = None
    
    # 期望输出（分层级）
    expected_canonical_question: str | None = None  # L1: 预处理
    expected_dimensions: list[str] | None = None  # L2: 字段识别
    expected_measures: list[str] | None = None
    expected_computation_type: str | None = None  # L3: 计算类型
    expected_can_build: bool = True  # L4: 能否构建
    expected_can_execute: bool = True  # L5: 能否执行
    expected_row_count_gt: int | None = None  # L6: 结果非空
    expected_result_hash: str | None = None  # L7: 结果一致（可选）
    
    # 元信息
    category: str  # simple/complex/time/filter/computation
    priority: str  # P0/P1/P2
    notes: str | None = None

# 判定层级
GOLDEN_LEVELS = {
    "L1_PREPROCESS": "canonical_question 匹配",
    "L2_FIELD_MATCH": "dimensions/measures 匹配",
    "L3_COMPUTATION": "computation_type 匹配",
    "L4_CAN_BUILD": "BuildQuery 成功",
    "L5_CAN_EXECUTE": "ExecuteQuery 成功",
    "L6_NON_EMPTY": "row_count > 0",
    "L7_RESULT_MATCH": "结果 hash 一致（严格）",
}
```

### Golden Set 示例

```json
[
  {
    "question": "各地区上月销售额",
    "datasource_luid": "test_ds_001",
    "expected_dimensions": ["Region"],
    "expected_measures": ["Sales"],
    "expected_can_build": true,
    "expected_can_execute": true,
    "category": "simple",
    "priority": "P0"
  },
  {
    "question": "各产品类别销售额占比",
    "datasource_luid": "test_ds_001",
    "expected_dimensions": ["Category"],
    "expected_measures": ["Sales"],
    "expected_computation_type": "PERCENT_OF_TOTAL",
    "expected_can_build": true,
    "category": "computation",
    "priority": "P0"
  }
]
```

## 附录

详细设计请参考：
- [附录 A: Preprocess 时间解析规则](./appendix-a-time-parsing.md)
- [附录 B: 计算模板库](./appendix-b-computation-templates.md)
- [附录 C: 缓存策略](./appendix-c-caching.md)

---

## 7. 基于现有源码的对齐审查（关键断点与缺口）

> 说明：本节结论来自对当前仓库源码的核验（不是推演）。由于项目尚未上线，你可以选择“不做兼容”，但这些断点若不修复，会直接影响 vNext 的正确性与可观测性。

### 7.1 关键断点（必须在 Phase 0 修复）

- **Step1/Step2 失败绕过 ReAct**：`agents/semantic_parser/subgraph.py` 的 `route_after_step1()` / `route_after_step2()` 在存在 `pipeline_error` 时直接 `END`，因此 Step1/Step2 的 `ValidationError/QueryError` 无法进入 `react_error_handler_node()`。
- **SummarizationMiddleware 对 Step1 输入不生效**：`Step1Component.execute()` 在 middleware 运行前把 `history` 转成字符串，并把它直接注入 prompt；而 SummarizationMiddleware 主要作用于 `state["messages"]`（或模型请求 messages），所以当前“摘要/截断”不会影响已构造的 `history_str`。
- **middleware hooks 未闭环**：`agents/base/node.py::_call_llm_with_tools_and_middleware()` 仅调用 `before_model / wrap_model_call / after_model`，没有调用 `before_agent / after_agent`，导致依赖 `before_agent` 的能力（如 `PatchToolCallsMiddleware.before_agent()`）在该路径上不保证生效。
- **LLM 空响应被吞掉**：`agents/base/node.py::_call_llm_with_tools_and_middleware()` 当 `model_response.result` 为空时直接 `return ""`，上层会在 `parse_json_response("")` 处以更不透明的方式失败。
- **Pipeline 工具调用未走 ToolRetryMiddleware 等中间件**：`QueryPipeline` 直接调用 `map_fields_async/build_query_async/execute_query_async`，而这些异步函数本身并未通过 `MiddlewareRunner.call_tool_with_middleware()` 包装，因此 workflow 里配置的 `ToolRetryMiddleware/FilesystemMiddleware/HITL` 无法保证覆盖。

### 7.2 建议把“方案中的前置条件”改为可验收的代码级条款

- **对齐规则**：在 `design.md` 中，凡是依赖 middleware 的能力（摘要、重试、tool_call 修补、输出校验），都必须明确“发生在哪个 hook、由哪个调用路径触发”。
- **验收口径**：用“可观测信号”验收（如：结构化日志字段/指标有值、特定错误能进入 ReAct、特定重试次数可复现）。

---

## 8. 意图识别方案（主流 AI/BI 与 NL2SQL 实践对齐）

### 8.1 主流做法概览（可直接映射到本项目）

- **两阶段路由（推荐）**：
  - **Stage A：轻量 Intent Router**（规则 + 小模型）决定走哪条“主路径”：数据查询（DATA_QUERY）/澄清（CLARIFICATION）/元数据问答（GENERAL）/无关（IRRELEVANT）。
  - **Stage B：数据查询才进入重路径**（Schema Linking + 受约束生成 + Validator + 执行反馈）。
- **为什么有效**：
  - 把大量“非数据查询”的请求提前分流，减少 LLM token 与工具调用。
  - 对 DATA_QUERY 引入“候选约束 + 确定性校验”后，准确率上限更高。

### 8.2 本项目落地设计（尽量复用现有框架能力）

- **新增组件**：`IntentRouter`（可以是一个 LangChain `Runnable`，也可以是子图中的一个节点）。
- **三层策略（从快到慢）**：
  - **L0 规则**（0 LLM）：
    - 明确无关/闲聊：打招呼、闲聊、与数据无关的知识问答（→ IRRELEVANT）。
    - 明确元数据："有哪些字段"、"数据源是什么"、"维度/度量有哪些"（→ GENERAL）。
    - 明确需要澄清：用户只说"帮我分析一下"但没有对象、度量、维度线索（→ CLARIFICATION）。
  - **L1 小模型分类**（1 次低成本调用，严格 JSON 输出）：
    - 输出：`intent_type` + `confidence` + `reason` + `need_clarify_slots`（可选）。
    - 仅当 L0 不触发时调用。
  - **L2 Step1 兜底**（保留现状）：
    - 当 L1 置信度低或输出不合规时，进入 Step1（但 Step1 在 vNext 中应只处理 DATA_QUERY 的结构化计划）。

### 8.3 与现有工作流的集成建议

- `route_after_semantic_parser()` 目前依赖 `intent_type` 扁平字段；建议把 `IntentRouter` 的结果写入统一字段（例如 `intent_type`），并让 SemanticParser 子图内部只在 `intent_type == DATA_QUERY` 时进入重路径。

---

## 9. 在保证准确率前提下的耗时优化（端到端）

> 目标：减少“高成本 LLM 调用次数”和“每次调用 token”，并用缓存与并行把尾延迟压下来。

### 9.1 不牺牲准确率的优化杠杆（按收益排序）

- **O(|fields|) → O(k) 的候选约束**：用 `schema_candidates` 替代全量字段注入（这是最确定的降本增效点）。
- **把 Step2 大部分场景模板化**：让 LLM 只处理长尾计算，常见计算用 `ComputationPlanner` 规则模板完成。
- **确定性 Validator 前置**：减少“构建/执行失败 → ReAct → 重试”的高代价链路。
- **并行化**：
  - Schema Linking 的多路召回（精确/模糊/向量）并行；Reranker 异步超时降级。
  - 允许在 Step1 进行时并行做部分轻量模板命中预判（只读字符串匹配）。
- **分层模型策略**：
  - Intent Router 用小模型/短上下文。
  - Step1 用主模型，但 token 受控。
  - 长尾 ReAct 只在“无法规则归因”时触发。

### 9.2 需要特别声明的“正确性护栏”

- Schema Linking 召回不足时必须允许 **回退路径**（例如回退到 FieldMapper 现有 RAG/LLM 选择），否则会出现“候选过滤掉正确字段”的系统性错误。
- 所有降级（超时、空候选、缓存失败）必须有指标与结构化日志，否则性能优化无法验收。

---

## 10. 性能提升关键指标（定义 + 口径 + 目标）

### 10.1 北极星指标

- **端到端 P95 响应时间（ms）**：从收到用户问题到返回结果/澄清/终止。
- **成功执行率（%）**：`BuildQuery` 成功率、`ExecuteQuery` 成功率。
- **单请求成本**：LLM 调用次数、prompt/completion tokens、外部 API 次数。

### 10.2 分层指标（建议全部做成结构化日志 + 指标）

| 指标 | 口径 | 目标建议 |
|---|---|---|
| `total_latency_ms_p50/p95` | 全链路 | P95 ≤ 2000ms（视模型/网络调整） |
| `step1_latency_ms` | Step1 LLM 调用耗时 | P95 可控且随字段数不再线性增长 |
| `step1_prompt_tokens` | Step1 prompt token | 从 O(|fields|) 降到 O(k) |
| `llm_calls_per_request` | Step1/Step2/ReAct 总次数 | 平均 ≤ 1.5 |
| `schema_linking_cache_hit_rate` | L1+L2 命中率 | ≥ 30%（先从 10% 起步） |
| `template_hit_rate` | ComputationPlanner 模板命中率 | ≥ 80%（占比/同比/环比/排名等） |
| `clarification_resolution_rate` | 一次澄清解决率 | ≥ 80% |
| `retry_count_distribution` | ReAct/模型重试分布 | 尾部受控（避免无限重试） |

---

## 11. 数据迁移流程与回滚机制（未上线版本的“工程可控性”）

> 即使未上线，也建议按照“可回滚/可重复”的工程流程做一次，避免后续迭代堆积技术债。

### 11.1 迁移对象

- **LangGraph Store**：`data/langgraph_store.db`（新增 namespace 及条目）。
- **索引文件**：FAISS/PKL（新增 schema linking 或 reranker 相关索引时）。
- **配置**：新增 vNext 开关、阈值、TTL、超时等。

### 11.2 迁移原则

- **增量式**：新功能写入新 namespace（如 `("semantic_parser", "vnext", datasource_luid)`），不要覆盖旧键。
- **可回滚**：回滚只需要关闭开关 + 删除/忽略新 namespace（必要时恢复 db 备份）。
- **数据最小化**：候选缓存不落盘 `sample_values` 等可能带业务敏感信息的字段（详见附录 C）。

### 11.3 迁移步骤（建议）

1. **冻结当前数据文件**：备份 `data/langgraph_store.db` 与 `data/indexes/`。
2. **引入版本化 namespace**：上线前所有 vNext 缓存写到 `("semantic_parser", "vnext", datasource_luid)`。
3. **灰度开关**：增加配置项（建议）：
   - `SEMANTIC_PARSER_VNEXT_ENABLED`
   - `SCHEMA_LINKING_ENABLED`
   - `COMPUTATION_PLANNER_ENABLED`
   - `VALIDATOR_ENABLED`
4. **预热（可选）**：对高频问题模板做 schema linking 缓存预热。
5. **验收**：跑 Golden set 与基准压测，确认指标达标。

### 11.4 回滚机制

- **快速回滚（首选）**：关闭 `SEMANTIC_PARSER_VNEXT_ENABLED`，回退到当前 Step1/Step2/Pipeline 路径。
- **数据回滚**：
  - 删除 vNext namespace 条目（或直接恢复 `langgraph_store.db` 备份）。
  - 删除 vNext 新增索引文件。
- **回滚验收**：
  - Golden set 全通过。
  - 关键接口（`/api/chat`）无异常。

---

## 12. 升级步骤文档（阶段划分 / 任务 / 负责人 / 时间节点 / 验收 / 应急）

> 负责人这里用“角色”占位（架构/后端/算法/测试/运维），你也可以替换成具体姓名。

| 阶段 | 目标 | 关键任务（摘要） | 负责人 | 时间（建议） | 验收标准 | 应急预案 |
|---|---|---|---|---|---|---|
| Phase 0 | 打通工程闭环 | 修复 Step1/2 失败进入 ReAct；middleware hooks 闭环；token 硬上限；空响应显式错误；Pipeline 工具走 middleware | 架构 + 后端 | 1 周 | 指标可打点；重试可复现；Step1/2 失败可进入 ReAct | 关闭相关开关回退旧链路 |
| Phase 1 | 降 token、控幻觉 | Preprocess（0 LLM）；Schema Linking（top-k 候选）；Step1 改为从候选选择 | 后端 + 算法 | 1–2 周 | Step1 token 从 O(|fields|)→O(k)；字段幻觉显著下降 | Schema Linking 召回不足时回退 FieldMapper 路径 |
| Phase 2 | 减少 LLM 调用 | ComputationPlanner 模板化；Validator 前置校验/修复；ReAct 规则化优先 | 后端 + 算法 | 2 周 | Step2 调用率下降；Build/Execute 成功率提升 | 模板不覆盖时 fallback Step2 |
| Phase 3 | 压尾延迟 | 批量 embedding；缓存（L1/L2）；Reranker 超时降级；FAISS 懒加载/预热 | 算法 + 后端 | 1–2 周 | P95 延迟下降；缓存命中率达标 | 降级策略生效且可观测 |
| Phase 4 | 稳定迭代 | Golden set 体系；回放压测；调参；错误规则库扩充 | 测试 + 运维 | 持续 | 指标长期稳定；回归自动化 | 一键回滚 + 数据恢复脚本 |

