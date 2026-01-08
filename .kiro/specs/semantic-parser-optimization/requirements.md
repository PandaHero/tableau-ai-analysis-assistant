# 语义解析器优化需求文档

## 背景

当前 Tableau AI Analysis Assistant 的语义解析器（SemanticParser）和字段映射器（FieldMapper）已经实现了基本功能，但通过代码分析发现以下核心矛盾：

### 兼容性说明

> **重要**：项目未上线，本文档中的"兼容性"指的是**内部契约一致性**，而非旧行为兼容。
> 
> - 允许直接替换现有实现
> - 只需保证内部接口契约一致
> - 不做旧版本 API 兼容

### 核心矛盾

**Step1/Step2 依赖 LLM 直接产出结构化 JSON，同时承担了"语义理解 + 规范化 + schema 感知"的责任；而下游 FieldMapper 又做了一套检索/重排/LLM 选择，存在职责重叠与冲突。**

### 当前架构问题

#### 问题 1: Step1 Token 成本与噪声过高

`Step1Component._format_data_model()` 把大量字段直接塞给 LLM：
- 字段多时不但慢，还会让模型"看花眼"导致误选/幻觉
- Prompt 复杂度 O(|fields|)，应降到 O(k)

#### 问题 2: Step1 职责过重

Step1 同时承担：语义理解 + 问句改写 + 时间解析 + 字段角色判断
- 但下游 FieldMapper 又做一次语义匹配，存在重复与冲突

#### 问题 3: Step2 自校验不可控

`components/step2.py` 明确写了"validation 由 LLM 填，不由代码计算"：
- 模型说"valid"，但实际 Build/Execute 仍失败
- 浪费 LLM 调用与重试预算

#### 问题 4: ReAct 过度依赖 LLM

对于大量可规则化的错误（字段不存在、权限、类型/聚合冲突）：
- 完全可以 deterministic 分类 + 快速失败/快速修复
- LLM 只应处理长尾问题

### 当前架构流程

```
用户问题: "各地区上个月销售额是多少？"
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  SemanticParser 子图 (agents/semantic_parser/subgraph.py)       │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Step1: 语义理解 (LLM)                                    │   │
│  │   输入: 用户问题 + 全量对话历史 + 全量字段清单 + current_time │
│  │   输出: Step1Output (Pydantic, extra="forbid")           │   │
│  │   问题: 全量字段注入导致 token 高、幻觉多                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Step2: 计算推理 (LLM) - 仅非 SIMPLE 时调用               │   │
│  │   问题: self-validation 由 LLM 填，代码不校验             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Pipeline: MapFields → ResolveFilterValues → Build → Execute │
│  │   MapFields: Cache→ExactMatch→RAG→LLM fallback           │   │
│  │   问题: 与 Step1 的字段识别存在重复                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ ReAct 错误处理器 (LLM)                                   │   │
│  │   问题: 高频可规则化错误也用 LLM 处理                     │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### vNext 目标架构

```
用户问题: "各地区上个月销售额是多少？"
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: 预处理层 (Deterministic, 0 LLM)                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Preprocess Node (新增)                                   │   │
│  │   - normalize(): 全角半角、空白归一、单位归一             │   │
│  │   - extract_time(): 规则解析相对时间 → [start, end]      │   │
│  │   - extract_slots(): 从历史抽取已确认字段/粒度/偏好       │   │
│  │   - build_canonical(): 生成稳定的 canonical_question     │   │
│  │   输出: canonical_question + time_context + memory_slots │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Layer 2: Schema Linking 层 (RAG 优先, 可并行)                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Schema Linking Node (新增)                               │   │
│  │   - 问题级检索: 对整句 query 检索 top-N 相关字段          │   │
│  │   - 实体级检索: 对候选术语并行检索候选字段/候选值         │   │
│  │   输出: schema_candidates (维度/度量分桶, 含样例值/层级)  │   │
│  │   约束: 后续模型只能从候选集合中选择                      │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Layer 3: 语义解析层 (1 次主模型调用为主)                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Step1 (重构)                                             │   │
│  │   输入: canonical_question + slots + time_context        │   │
│  │        + schema_candidates (top-k, 非全量)               │   │
│  │   输出: 受约束的语义计划 (字段引用用候选ID/规范名)        │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Layer 4: 计算规划层 (模板优先, LLM 兜底)                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Computation Planner (新增, 替代大部分 Step2)             │   │
│  │   - 常见计算模板库: 同比/环比/排名/占比/移动平均/累计     │   │
│  │   - 约束求解: 通过粒度+层级决定 partition_by             │   │
│  │   - LLM fallback: 仅模板无法覆盖时调用                   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Layer 5: 后处理与校验层 (Deterministic + 小型修复器)           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Validator (新增)                                         │   │
│  │   - 强校验: 字段存在性、类型匹配、聚合合法性              │   │
│  │   - 可规则修复: 去重 measures、纠正聚合、权限快速失败     │   │
│  │   - 统一澄清协议: ClarificationRequest                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ ReAct (重构)                                             │   │
│  │   - 先走 deterministic error classifier                  │   │
│  │   - 只把"长尾不可归因"交给 LLM                           │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Layer 6: 执行层 (Pipeline 保留但"更瘦")                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ MapFields: 输入已是候选引用, 只做校验+落地               │   │
│  │ ResolveFilterValues: 先候选值检索, 再决定是否澄清        │   │
│  │ Build → Execute                                          │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## GPT-5.2 代码审查发现的工程债务

基于 GPT-5.2 对现有源码的全面审查，发现以下工程问题需要在实施 vNext 功能之前优先修复：

### 问题 1: 子图入口契约不统一

**现状**：`factory.py` 直接挂 `create_semantic_parser_subgraph()`，但主工作流路由期待 `semantic_parser_node` 的"扁平化输出"（intent_type/is_analysis_question/...）。两者并存导致路由与状态字段"各说各话"。

**影响**：降低可维护性与可观测性，路由行为不确定。

### 问题 2: Step1/Step2 解析失败不进入 ReAct 纠错链路

**现状**：路由在遇到 `pipeline_error` 时会直接结束，导致最强的"错误自愈器"（ReAct）覆盖不到 JSON 解析失败、输出不合规等高频问题。

**影响**：显著降低"自愈率"，对模型输出格式更敏感。

### 问题 3: middleware/重试体系在 Pipeline 里未闭环

**现状**：`QueryPipeline` 的注释宣称走 `call_tool_with_middleware`，但实际多处直接调用 `map_fields_async/execute_query_async`，导致"工具级重试/文件落盘/HITL"等能力可能失效或行为不一致。

**影响**：工程行为不确定，重试能力不可靠。

### 问题 4: History/Schema token 无硬性上限保护

**现状**：Step1 会把 history 格式化进 prompt，但不做硬截断，依赖 `SummarizationMiddleware`；如果 middleware 未稳定注入，token 会不受控。

**影响**：token 成本与幻觉放大，latency 随字段数线性上升。

### 问题 5: 类型声明与实际写入不一致

**现状**：例如 state 对 `data_model/query_result` 的类型标注与实际赋值不一致。

**影响**：长期会造成序列化/调试困难。

---

## 需求列表

### Phase 0: 工程债务清理（前置条件）

> **重要**：以下需求是实施 vNext 功能的前置条件，必须优先完成。

### 需求 0.1: 统一语义解析入口与状态契约

**用户故事**: 作为系统架构师，我希望语义解析器有唯一的标准入口，状态字段在各层级一致。

**优先级**: P0（阻塞后续开发）

#### 验收标准

1. THE System SHALL 只保留一种标准接入方式（包装节点或 subgraph，但要一致）
2. THE System SHALL 统一意图字段的单一事实来源（建议以 `SemanticParserState.step1_output.intent` 为准）
3. THE System SHALL 在一个地方完成状态扁平化，供主工作流路由消费
4. THE System SHALL 清理 `semantic_parser_node` 与 `create_semantic_parser_subgraph` 的重复定义

---

### 需求 0.2: 让 ReAct 覆盖 Step1/Step2 的解析失败

**用户故事**: 作为系统架构师，我希望 JSON 解析失败、输出不合规等高频问题也能进入纠错链路。

**优先级**: P0（显著提升自愈率）

#### 验收标准

1. THE System SHALL 把 `ValidationError(step="step1"/"step2")` 也纳入 ReAct 纠错链路
2. THE System SHALL 在 Step1/Step2 解析失败时，携带结构化错误信息进入 ReAct
3. THE System SHALL 支持 ReAct 对解析失败的 RETRY 决策
4. THE System SHALL 记录解析失败的错误类型分布指标

---

### 需求 0.3: Pipeline 贯通 middleware 能力

**用户故事**: 作为系统架构师，我希望 Pipeline 的每一步都能享受 middleware 提供的重试/落盘/观测能力。

**优先级**: P0（工程行为确定性）

#### 验收标准

1. THE System SHALL 确保 `map_fields_async/execute_query_async` 等调用都经过 middleware
2. THE System SHALL 把 Pipeline 的每一步变成"可插拔、可重试、可观测"的单元
3. THE System SHALL 明确每一步输入/输出与清理策略
4. THE System SHALL 确保 ReAct 决定 RETRY 时，指导信息会被真正消费

---

### 需求 0.4: History/Schema token 硬性上限保护

**用户故事**: 作为系统架构师，我希望即便 middleware 未稳定注入，token 也不会失控。

**优先级**: P0（成本与稳定性）

#### 验收标准

1. THE System SHALL 在 Step1 prompt 构建时，对 history 做硬性 token 上限截断（建议 2000 tokens）
2. THE System SHALL 在 Step1 prompt 构建时，对 schema summary 做硬性 token 上限截断（建议 3000 tokens）
3. THE System SHALL 记录截断发生的频率指标
4. THE System SHALL 在截断时保留最近/最相关的内容

---

### 需求 0.5: 基础可观测性（每层耗时/token/调用次数）

**用户故事**: 作为运维人员，我希望能够监控语义解析器各层的基础性能指标。

**优先级**: P0（问题定位基础）

#### 验收标准

1. THE System SHALL 记录每层耗时（preprocess/schema_linking/step1/step2/pipeline）
2. THE System SHALL 记录 LLM 调用的 token 数（prompt/completion 分开）
3. THE System SHALL 记录 LLM 调用次数（按类型：step1/step2/react）
4. THE System SHALL 支持结构化日志输出（JSON 格式）

---

### 需求 0.6: 组件级解析重试（简化方案）

**用户故事**: 作为系统架构师，我希望 Step1/Step2 解析失败时能够自动重试，并携带错误反馈。

**优先级**: P0（重试机制是稳定性基础）

**问题根因**（GPT-5.2 发现）：
- `OutputValidationMiddleware` 在 `after_model` 阶段抛出异常
- 但 `ModelRetryMiddleware` 在 `wrap_model_call` 阶段捕获异常
- 导致"校验失败→触发重试"这条链路实际不生效

**修正方案**（GPT-5.2 审查后调整）：
- **保留 `OutputValidationMiddleware` 作为质量闸门**（但不依赖它触发重试）
- **在组件层实现解析重试闭环**（Step1/Step2 内部）
- 组件内重试负责"格式重试"，ReAct 负责"语义重试"
- 避免"中间件校验 + 组件重试 + ReAct 决策"三套机制互相踩踏

**设计原则**：同一类错误只在一个层级负责处理
- **格式错误**（JSON 解析失败、Pydantic 校验失败）→ 组件内重试
- **语义错误**（字段不存在、计算不合法）→ ReAct 决策

#### 验收标准

1. THE System SHALL 在 Step1/Step2 组件内部实现解析重试：
   - 最大重试次数：2 次
   - 重试时携带结构化错误反馈
2. THE System SHALL 在重试时携带结构化错误反馈：
   - 解析错误类型（JSON 格式错误 / Pydantic 校验失败 / 枚举值不合法）
   - 错误位置（如果可定位）
   - 修复建议
3. THE System SHALL 记录重试触发的原因和次数
4. THE System SHALL 确保重试机制在以下场景生效：
   - JSON 解析失败
   - Pydantic 校验失败
   - 枚举值不合法
   - 必填字段缺失
5. THE System SHALL 保留 `OutputValidationMiddleware` 作为最终质量闸门（但不依赖它触发重试）
6. THE System SHALL 确保错误处理职责清晰（GPT-5.2 审查补充 - 明确分类边界）：
   - **格式错误 → 组件内重试**（不进入 ReAct）：
     - `json.JSONDecodeError`: JSON 格式错误
     - `pydantic.ValidationError`: Pydantic 校验失败
     - `KeyError` / `TypeError`: 必填字段缺失或类型错误
     - `ValueError` (枚举相关): 枚举值不合法
   - **语义错误 → ReAct 决策**（不在组件内重试）：
     - `FieldNotFoundError`: 字段不存在
     - `AggregationConflictError`: 聚合冲突
     - `PermissionDeniedError`: 权限不足
     - `TypeMismatchError`: 字段类型不匹配
     - `ExecutionError`: 查询执行失败
   - **注意**：执行失败（`ExecutionError`）不应被当作格式问题重试，否则会吃掉语义重试预算
7. THE System SHALL 实现分类重试预算管理（GPT-5.2 审查补充）：
   - 格式重试预算：`MAX_FORMAT_RETRIES = 2`（独立计数）
   - 语义重试预算：`MAX_SEMANTIC_RETRIES = 2`（独立计数）
   - 两类预算独立，互不影响
   - 记录各类重试的消耗情况

**修复方案（组件级重试）**：

```python
# components/step1.py

MAX_FORMAT_RETRIES = 2  # 格式重试（JSON/Pydantic）

class Step1Component:
    """Step1 组件 - 带格式重试闭环"""
    
    async def execute(self, ...) -> tuple[Step1Output, str]:
        """执行 Step1 - 格式重试在组件内闭环"""
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
                
                if attempt > 0:
                    logger.info(f"Step1 parse retry succeeded after {attempt} retries")
                    metrics.step1_parse_retry_success_count.inc()
                
                return result, response.thinking
                
            except (ValueError, ValidationError) as e:
                # 格式错误 → 组件内重试
                if attempt < MAX_FORMAT_RETRIES:
                    logger.warning(f"Step1 parse error, retry {attempt + 1}: {e}")
                    metrics.step1_parse_retry_count.inc()
                    error_feedback = self._build_error_feedback(e)
                    continue
                
                # 格式重试耗尽 → 抛出，由上层决定是否进入 ReAct
                logger.error(f"Step1 parse retry exhausted after {MAX_FORMAT_RETRIES} retries: {e}")
                metrics.step1_parse_failure_count.inc()
                raise
    
    def _build_error_feedback(self, error: Exception) -> str:
        """构建结构化错误反馈"""
        if isinstance(error, ValidationError):
            error_details = [f"- 字段 '{'.'.join(str(loc) for loc in err['loc'])}': {err['msg']}" 
                           for err in error.errors()]
            return f"解析失败：Pydantic 校验错误\n{''.join(error_details)}\n请修正后重新输出。"
        else:
            return f"解析失败：{str(error)[:200]}\n请确保输出是有效的 JSON 格式。"
```

---

### 需求 0.7: JSON 解析增强（JSON Mode + Provider 适配）

**用户故事**: 作为系统架构师，我希望通过启用 JSON Mode 增强 JSON 输出的可靠性，同时保持流式输出兼容和现有调用模式不变。

**优先级**: P1（稳定性增强）

**问题根因**（GPT-5.2 发现）：
- 当前结构化输出依赖 prompt + `json_repair` + Pydantic 校验
- `json_repair` 失败时缺少详细日志，问题难定位
- 没有记录修复成功率指标
- 没有利用 DeepSeek 原生的 JSON Mode 能力

**约束条件**：
- **必须保持现有 `call_llm_with_tools()` 调用模式不变**（中间件 + 流式输出）
- **不使用 `with_structured_output`**（不支持流式，且 DeepSeek 不支持）
- **不使用 `response_format: json_schema`**（Structured Output，DeepSeek 不支持）
- **可以使用 `response_format: json_object`**（JSON Mode，DeepSeek 支持，且支持流式）

**GPT-5.2 审查补充**：
- 仓库中存在 `CustomLLMChat`（custom_llm.py），使用 `extra_body` 拼 payload
- JSON Mode 需要 **provider 适配层**，而非只写一种实现方式
- 否则后续接入非 OpenAI 兼容端点时会出现"参数被忽略/被拒绝"的分叉行为

**技术背景**：

| 方案 | DeepSeek 支持 | 流式支持 | Schema 保证 | 适用场景 |
|------|--------------|----------|-------------|----------|
| Structured Output (`json_schema`) | ❌ 不支持 | ✅ 支持 | ✅ 100% 保证 | OpenAI 专用 |
| JSON Mode (`json_object`) | ✅ 支持 | ✅ 支持 | ⚠️ 只保证是 JSON | **推荐方案** |
| Prompt + json_repair + Pydantic | ✅ 支持 | ✅ 支持 | ⚠️ 依赖模型遵循 | 当前方案 |

**DeepSeek JSON Mode 使用要求**（来自官方文档）：
1. 设置 `response_format: {'type': 'json_object'}`
2. 在 system 或 user prompt 中包含 "json" 关键词
3. 提供期望的 JSON 格式示例
4. 合理设置 `max_tokens` 防止 JSON 被截断

**推荐方案**：JSON Mode + json_repair + Pydantic（三层防护）
- **第一层**：JSON Mode 保证输出是有效 JSON（减少格式错误）
- **第二层**：json_repair 修复可能的截断或小问题
- **第三层**：Pydantic 校验 schema 合规性

**实现方式**：Provider 适配层 + 模型能力开关

#### 验收标准

1. THE System SHALL 实现 Provider 适配层，支持不同 LLM 实现：
   - `ChatOpenAI`: 通过 `model_kwargs.response_format` 传入
   - `CustomLLMChat`: 通过 `extra_body.response_format` 传入
   - 其他 Provider: 提供统一的适配接口
2. THE System SHALL 支持 JSON Mode 能力检测（GPT-5.2 审查修正）：
   - **按 Provider 显式配置**（而非自动探测）：
     - 在配置中明确标记每个 Provider 是否支持 JSON Mode
     - 例如：`{"openai": true, "deepseek": true, "custom": true, "ollama": false}`
   - **不支持时自动降级**到 prompt + json_repair 方案
   - **记录降级指标**：`json_mode_fallback_count`（按 Provider 分类）
   - **不强求"自动探测"**（很多 Provider 只能通过配置白名单/试探调用/错误码判断）
3. THE System SHALL 在 Step1/Step2 的 prompt 中包含 "json" 关键词和格式示例
4. THE System SHALL 增强 `json_repair` 的错误处理和日志：
   - 记录修复尝试类型（截断修复、括号补全、引号修复等）
   - 记录修复失败时的原始输出（截断到 500 字符）
   - 记录解析错误的具体位置
5. THE System SHALL 记录 JSON 解析相关指标：
   - 直接解析成功率（按 Provider 分类）
   - json_repair 修复成功率
   - Pydantic 校验失败率
   - JSON Mode 降级率
6. THE System SHALL 在解析失败时提供结构化错误信息：
   - 错误类型（JSON 格式错误 / Pydantic 校验失败 / 枚举值不合法）
   - 错误位置（如果可定位）
   - 原始内容预览

**修复方案（Provider 适配层）**：

```python
# ============================================================
# infra/ai/json_mode_adapter.py - Provider 适配层
# ============================================================

from abc import ABC, abstractmethod
from typing import Any

class JSONModeAdapter(ABC):
    """JSON Mode 适配器基类"""
    
    @abstractmethod
    def supports_json_mode(self) -> bool:
        """检测是否支持 JSON Mode"""
        pass
    
    @abstractmethod
    def apply_json_mode(self, kwargs: dict) -> dict:
        """应用 JSON Mode 配置"""
        pass


class OpenAIJSONModeAdapter(JSONModeAdapter):
    """OpenAI/DeepSeek 兼容的 JSON Mode 适配器"""
    
    def supports_json_mode(self) -> bool:
        return True
    
    def apply_json_mode(self, kwargs: dict) -> dict:
        kwargs.setdefault("model_kwargs", {})
        kwargs["model_kwargs"]["response_format"] = {"type": "json_object"}
        return kwargs


class CustomLLMJSONModeAdapter(JSONModeAdapter):
    """CustomLLMChat 的 JSON Mode 适配器"""
    
    def supports_json_mode(self) -> bool:
        return True
    
    def apply_json_mode(self, kwargs: dict) -> dict:
        kwargs.setdefault("extra_body", {})
        kwargs["extra_body"]["response_format"] = {"type": "json_object"}
        return kwargs


class FallbackJSONModeAdapter(JSONModeAdapter):
    """不支持 JSON Mode 的降级适配器"""
    
    def supports_json_mode(self) -> bool:
        return False
    
    def apply_json_mode(self, kwargs: dict) -> dict:
        # 不做任何修改，依赖 prompt + json_repair
        logger.warning("JSON Mode not supported, falling back to prompt + json_repair")
        metrics.json_mode_fallback_count.inc()
        return kwargs


def get_json_mode_adapter(provider: str) -> JSONModeAdapter:
    """获取对应 Provider 的 JSON Mode 适配器"""
    adapters = {
        "openai": OpenAIJSONModeAdapter(),
        "deepseek": OpenAIJSONModeAdapter(),
        "custom": CustomLLMJSONModeAdapter(),
    }
    return adapters.get(provider, FallbackJSONModeAdapter())


# ============================================================
# 在 model_manager.py 中使用适配层
# ============================================================

def create_chat_model(
    config: ModelConfig,
    enable_json_mode: bool = False,
) -> BaseChatModel:
    """创建 LLM 实例 - 支持 Provider 适配的 JSON Mode"""
    
    kwargs = {
        "model": config.model_name,
        "api_key": config.api_key,
        "base_url": config.api_base,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "streaming": config.supports_streaming,
    }
    
    # 通过适配层应用 JSON Mode
    if enable_json_mode:
        adapter = get_json_mode_adapter(config.provider)
        if adapter.supports_json_mode():
            kwargs = adapter.apply_json_mode(kwargs)
        else:
            logger.info(f"Provider {config.provider} does not support JSON Mode")
    
    # 根据 Provider 创建对应的 LLM 实例
    if config.provider == "custom":
        return CustomLLMChat(**kwargs)
    else:
        return ChatOpenAI(**kwargs)


# ============================================================
# 在组件层按需启用 JSON Mode
# ============================================================

# components/step1.py
class Step1Component:
    """Step1 组件 - 支持 JSON Mode"""
    
    def __init__(self, enable_json_mode: bool = True):
        self.enable_json_mode = enable_json_mode
    
    async def execute(self, ...) -> tuple[Step1Output, str]:
        """执行 Step1"""
        # 获取 LLM（可选启用 JSON Mode）
        llm = get_llm(enable_json_mode=self.enable_json_mode)
        
        # 调用方式完全不变
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
# 方案 3: 增强版 parse_json_response（三层防护）
# ============================================================

def parse_json_response(
    content: str,
    model_class: type[BaseModel],
    repair_enabled: bool = True,
) -> BaseModel:
    """解析 JSON 响应 - 三层防护
    
    第一层：JSON Mode 已在 LLM 层保证输出是有效 JSON
    第二层：json_repair 修复可能的截断或小问题
    第三层：Pydantic 校验 schema 合规性
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
            logger.warning(f"JSON repaired but Pydantic validation failed: {repair_validation_error}")
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
```

---

### 需求 0.8: 流式 tool_calls 解析错误显式处理

**用户故事**: 作为系统架构师，我希望 tool_calls 参数解析失败时能够显式记录，而非静默吞掉。

**优先级**: P1（问题定位能力）

**问题根因**（GPT-5.2 发现）：
```python
# node.py 当前实现
try:
    args = json_module.loads(tc["args"]) if tc["args"] else {}
except json_module.JSONDecodeError:
    args = {}  # ← 静默吞掉错误
```

**影响**：
- 模型输出了坏的 tool args，但错误被吞掉
- 后续工具执行看起来像"工具没收到参数"
- 问题难定位

#### 验收标准

1. THE System SHALL 在 tool_calls 参数解析失败时记录警告日志：
   - 包含原始参数内容（截断到 200 字符）
   - 包含解析错误信息
2. THE System SHALL 尝试使用 `json_repair` 修复 tool_calls 参数
3. THE System SHALL 在修复失败时标记该 tool_call 为"参数解析失败"
4. THE System SHALL 记录 tool_calls 参数解析失败率指标

**修复方案**：

```python
try:
    args = json_module.loads(tc["args"]) if tc["args"] else {}
except json_module.JSONDecodeError as e:
    logger.warning(f"Tool call args parse failed: {e}, raw: {tc['args'][:200]}")
    metrics.tool_args_parse_failure_count.inc()
    
    # 尝试修复
    try:
        from json_repair import repair_json
        args = json_module.loads(repair_json(tc["args"]))
        logger.info("Tool call args repaired successfully")
    except Exception:
        args = {}
        tc["_parse_error"] = str(e)
```

---

### 需求 0.9: LLM 空响应显式处理

**用户故事**: 作为系统架构师，我希望 LLM 返回空响应时能够显式报错，而非返回空字符串。

**优先级**: P1（问题定位能力）

**问题根因**（GPT-5.2 发现）：
```python
# node.py 当前实现
if not model_response.result:
    return ""  # ← 返回空字符串，上层难以定位问题
```

**影响**：
- 上层以为拿到了 AIMessage，但内容是空的
- 后续 `parse_json_response("")` 报错更难定位

#### 验收标准

1. THE System SHALL 在 LLM 返回空响应时抛出明确异常
2. THE System SHALL 记录空响应发生的频率指标
3. THE System SHALL 在异常信息中包含请求上下文（模型名、消息数量等）

**修复方案**：

```python
if not model_response.result:
    logger.error(f"LLM returned empty response, model={request.model}, messages={len(request.messages)}")
    metrics.llm_empty_response_count.inc()
    raise ValueError(f"LLM returned empty response for model {request.model}")
```

---

### 需求 0.10: Step1 history 参数与 SummarizationMiddleware 对齐

**用户故事**: 作为系统架构师，我希望 Step1 的 history 能够享受 `SummarizationMiddleware` 的自动摘要能力。

**优先级**: P1（token 控制）

**问题根因**（GPT-5.2 发现）：
- `SummarizationMiddleware` 操作的是 `state["messages"]`（LangGraph 的消息列表）
- 但 Step1 的 `history` 参数是**直接传入的**，不是从 `state["messages"]` 读取的
- 所以 `SummarizationMiddleware` 对 Step1 的 history 参数**不生效**

#### 验收标准

1. THE System SHALL 修改 Step1 的 history 来源，从 `state["messages"]` 读取（而非直接传入参数）
2. THE System SHALL 确保 `SummarizationMiddleware` 能够对 Step1 的 history 生效
3. THE System SHALL 在 Step1 内部保留硬性截断作为兜底（需求 0.4）
4. THE System SHALL 记录 history 来源和 token 数

**修复方案**：

```python
# 方案：修改 Step1 从 state["messages"] 读取 history
async def execute(
    self,
    question: str,
    state: Dict[str, Any],  # ← 从 state 读取
    ...
):
    # 从 state["messages"] 读取 history（已被 SummarizationMiddleware 处理）
    messages = state.get("messages", [])
    history = self._convert_messages_to_history(messages)
    
    # 硬性截断作为兜底
    history_str = self._format_history_with_limit(history, MAX_HISTORY_TOKENS)
```

---

### 需求 0.11: 完整 middleware 钩子调用（before_agent/after_agent）

**用户故事**: 作为系统架构师，我希望 Step1/Step2 路径能够调用完整的 middleware 钩子，包括 `before_agent` 和 `after_agent`。

**优先级**: P2（完整性）

**问题根因**（GPT-5.2 发现）：
- `_call_llm_with_tools_and_middleware()` 只调用了 `before_model / wrap_model_call / after_model`
- 没有调用 `before_agent / after_agent`
- 导致 `PatchToolCallsMiddleware.before_agent()` 和 `OutputValidationMiddleware.after_agent()` 不生效

#### 验收标准

1. THE System SHALL 在 subgraph 入口处调用 `run_before_agent()`
2. THE System SHALL 在 subgraph 出口处调用 `run_after_agent()`
3. THE System SHALL 确保 `PatchToolCallsMiddleware.before_agent()` 能够修复 dangling tool calls
4. THE System SHALL 确保 `OutputValidationMiddleware.after_agent()` 能够校验最终状态
5. THE System SHALL 实现钩子执行的错误处理和降级策略：
   - 单个钩子失败不应阻塞整个流程
   - 记录钩子执行失败的指标
   - 支持配置是否跳过失败的钩子
6. THE System SHALL 确保所有终止路径都经过 exit 节点（统一出口）

**修复方案**：

```python
# subgraph.py
async def semantic_parser_entry(state: SemanticParserState) -> dict:
    """子图入口节点 - 调用 before_agent（带错误处理）"""
    runner = get_middleware_runner(state)
    runtime = runner.build_runtime(state.config)
    
    try:
        state = await runner.run_before_agent(state, runtime)
    except Exception as e:
        logger.error(f"before_agent hook failed: {e}")
        metrics.middleware_hook_failure_count.inc(labels={"hook": "before_agent"})
        # 降级：继续执行，但记录警告
        if not state.config.get("skip_failed_hooks", True):
            raise
    
    return state

async def semantic_parser_exit(state: SemanticParserState) -> dict:
    """子图出口节点 - 调用 after_agent（带错误处理）"""
    runner = get_middleware_runner(state)
    runtime = runner.build_runtime(state.config)
    
    try:
        state = await runner.run_after_agent(state, runtime)
    except Exception as e:
        logger.error(f"after_agent hook failed: {e}")
        metrics.middleware_hook_failure_count.inc(labels={"hook": "after_agent"})
        if not state.config.get("skip_failed_hooks", True):
            raise
    
    return _flatten_output(state)

# 在 subgraph 中添加入口和出口节点
graph.add_node("entry", semantic_parser_entry)
graph.add_node("exit", semantic_parser_exit)
graph.add_edge(START, "entry")
graph.add_edge("entry", "preprocess")
# ... 其他节点 ...
# 所有终止路径都经过 exit
graph.add_edge("pipeline", "exit")
graph.add_edge("exit", END)
```

---

### 需求 0.12: IntentRouter 意图识别（两阶段路由）

**用户故事**: 作为系统架构师，我希望在进入重路径（Step1/Schema Linking）之前，先用轻量级方式识别意图，减少不必要的 LLM 调用。

**优先级**: P1（降本增效）

**设计来源**：GPT-5.2 Section 8 - 主流 AI/BI 与 NL2SQL 实践对齐

**核心思路**：
- 把大量"非数据查询"的请求提前分流，减少 LLM token 与工具调用
- 对 DATA_QUERY 引入"候选约束 + 确定性校验"后，准确率上限更高

#### 验收标准

1. THE System SHALL 实现三层意图识别策略（从快到慢）：
   - **L0 规则层**（0 LLM 调用）：
     - 明确无关/闲聊：打招呼、闲聊、与数据无关的知识问答 → IRRELEVANT
     - 明确元数据："有哪些字段"、"数据源是什么"、"维度/度量有哪些" → GENERAL
     - 明确需要澄清：用户只说"帮我分析一下"但没有对象、度量、维度线索 → CLARIFICATION
   - **L1 小模型分类**（1 次低成本调用，严格 JSON 输出）：
     - 输出：`intent_type` + `confidence` + `reason` + `need_clarify_slots`（可选）
     - 仅当 L0 不触发时调用
   - **L2 Step1 兜底**（保留现状）：
     - 当 L1 置信度低或输出不合规时，进入 Step1
2. THE System SHALL 定义统一的意图类型枚举：
   - `DATA_QUERY`: 数据查询（进入重路径）
   - `CLARIFICATION`: 需要澄清（返回澄清请求）
   - `GENERAL`: 元数据问答（直接回答）
   - `IRRELEVANT`: 无关问题（礼貌拒绝）
3. THE System SHALL 把 IntentRouter 结果写入统一字段 `intent_type`
4. THE System SHALL 仅在 `intent_type == DATA_QUERY` 时进入 Schema Linking + Step1 重路径
5. THE System SHALL 记录各层命中率指标：
   - L0 规则命中率
   - L1 小模型调用率
   - L2 Step1 兜底率
6. THE System SHALL 支持配置 L1 置信度阈值（默认 0.8）

**实现建议**：

```python
# components/intent_router.py

class IntentType(str, Enum):
    DATA_QUERY = "DATA_QUERY"
    CLARIFICATION = "CLARIFICATION"
    GENERAL = "GENERAL"
    IRRELEVANT = "IRRELEVANT"

class IntentRouterOutput(BaseModel):
    intent_type: IntentType
    confidence: float
    reason: str
    need_clarify_slots: list[str] | None = None

class IntentRouter:
    """意图识别器 - 三层策略"""
    
    def __init__(self, l1_confidence_threshold: float = 0.8):
        self.l1_confidence_threshold = l1_confidence_threshold
    
    async def route(self, question: str, context: dict) -> IntentRouterOutput:
        """执行意图识别"""
        # L0: 规则层
        l0_result = self._try_l0_rules(question)
        if l0_result:
            metrics.intent_router_l0_hit_count.inc()
            return l0_result
        
        # L1: 小模型分类
        l1_result = await self._try_l1_classifier(question, context)
        if l1_result and l1_result.confidence >= self.l1_confidence_threshold:
            metrics.intent_router_l1_hit_count.inc()
            return l1_result
        
        # L2: 返回 DATA_QUERY，让 Step1 兜底
        metrics.intent_router_l2_fallback_count.inc()
        return IntentRouterOutput(
            intent_type=IntentType.DATA_QUERY,
            confidence=0.5,
            reason="L1 confidence too low, fallback to Step1",
        )
    
    def _try_l0_rules(self, question: str) -> IntentRouterOutput | None:
        """L0 规则层 - 0 LLM 调用"""
        # 闲聊/无关
        if self._is_greeting_or_chitchat(question):
            return IntentRouterOutput(
                intent_type=IntentType.IRRELEVANT,
                confidence=1.0,
                reason="Detected greeting or chitchat",
            )
        
        # 元数据问答
        if self._is_metadata_question(question):
            return IntentRouterOutput(
                intent_type=IntentType.GENERAL,
                confidence=1.0,
                reason="Detected metadata question",
            )
        
        # 明确需要澄清
        if self._needs_clarification(question):
            return IntentRouterOutput(
                intent_type=IntentType.CLARIFICATION,
                confidence=1.0,
                reason="Question too vague, needs clarification",
                need_clarify_slots=["object", "measure", "dimension"],
            )
        
        return None
```

---

### 需求 0.13: Schema Linking 回退路径（正确性护栏）

**用户故事**: 作为系统架构师，我希望 Schema Linking 召回不足时能够自动回退到 FieldMapper 路径，避免"候选过滤掉正确字段"的系统性错误。

**优先级**: P1（正确性保障）

**设计来源**：GPT-5.2 Section 9 - 正确性护栏

**核心思路**：
- Schema Linking 是优化手段，不能牺牲正确性
- 召回不足时必须有回退路径
- 所有降级必须有指标与结构化日志

#### 验收标准

1. THE System SHALL 在 Schema Linking 召回不足时自动回退到 FieldMapper 路径：
   - 触发条件：候选集为空 或 候选集置信度过低（< 0.5）
   - 回退行为：跳过 Schema Linking，直接使用 FieldMapper 的 RAG/LLM 选择
2. THE System SHALL 记录回退触发的原因和频率：
   - `schema_linking_fallback_count`（按原因分类）
   - `schema_linking_fallback_reason`（空候选 / 低置信度 / 超时 / 低覆盖）
3. THE System SHALL 在回退时记录结构化日志：
   - 原始问题
   - 召回候选数量
   - 最高置信度
   - 回退原因
4. THE System SHALL 支持配置回退阈值：
   - `schema_linking_min_candidates`: 最小候选数量（默认 1）
   - `schema_linking_min_confidence`: 最小置信度（默认 0.5）
   - `schema_linking_timeout_ms`: 超时时间（默认 2000ms）
   - `schema_linking_min_term_hit_ratio`: 最小术语命中率（默认 0.3）（GPT-5.2 审查补充）
5. THE System SHALL 在以下场景触发回退（GPT-5.2 审查补充）：
   - 候选集为空
   - 所有候选置信度 < 阈值
   - Schema Linking 超时
   - Schema Linking 异常
   - **低覆盖信号**（新增）：
     - top1 与 topk 分数差距过小（< 0.1）：表示候选区分度不足
     - 术语命中率过低（< 30%）：问题中的关键词在候选中命中不足
     - 候选分数整体偏低（平均分 < 0.4）：表示候选质量不足
6. THE System SHALL 实现低覆盖信号检测（GPT-5.2 审查补充）：
   ```python
   def _check_low_coverage_signal(self, candidates: list[FieldCandidate], question: str) -> bool:
       """检测低覆盖信号 - 避免"有候选但全是噪声"仍然硬走新链路"""
       if not candidates:
           return True
       
       # 信号 1: top1 与 topk 分数差距过小
       scores = sorted([c.confidence for c in candidates], reverse=True)
       if len(scores) >= 2 and scores[0] - scores[-1] < 0.1:
           logger.warning("Low coverage signal: score spread too small")
           return True
       
       # 信号 2: 术语命中率过低
       terms = self._extract_terms(question)
       hit_count = sum(1 for t in terms if any(t in c.field_caption for c in candidates))
       if terms and hit_count / len(terms) < self.min_term_hit_ratio:
           logger.warning(f"Low coverage signal: term hit ratio {hit_count}/{len(terms)}")
           return True
       
       # 信号 3: 候选分数整体偏低
       avg_score = sum(c.confidence for c in candidates) / len(candidates)
       if avg_score < 0.4:
           logger.warning(f"Low coverage signal: avg score {avg_score} too low")
           return True
       
       return False
   ```
   - 所有候选置信度 < 阈值
   - Schema Linking 超时
   - Schema Linking 异常

**实现建议**：

```python
# components/schema_linking.py

class SchemaLinkingResult(BaseModel):
    candidates: list[FieldCandidate]
    fallback_triggered: bool = False
    fallback_reason: str | None = None

class SchemaLinking:
    """Schema Linking 组件 - 带回退路径"""
    
    def __init__(
        self,
        min_candidates: int = 1,
        min_confidence: float = 0.5,
        timeout_ms: int = 2000,
    ):
        self.min_candidates = min_candidates
        self.min_confidence = min_confidence
        self.timeout_ms = timeout_ms
    
    async def link(
        self,
        question: str,
        data_model: DataModel,
    ) -> SchemaLinkingResult:
        """执行 Schema Linking - 带回退路径"""
        try:
            candidates = await asyncio.wait_for(
                self._do_schema_linking(question, data_model),
                timeout=self.timeout_ms / 1000,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Schema linking timeout after {self.timeout_ms}ms")
            metrics.schema_linking_fallback_count.inc(labels={"reason": "timeout"})
            return SchemaLinkingResult(
                candidates=[],
                fallback_triggered=True,
                fallback_reason="timeout",
            )
        except Exception as e:
            logger.error(f"Schema linking failed: {e}")
            metrics.schema_linking_fallback_count.inc(labels={"reason": "error"})
            return SchemaLinkingResult(
                candidates=[],
                fallback_triggered=True,
                fallback_reason=f"error: {str(e)[:100]}",
            )
        
        # 检查候选集质量
        if len(candidates) < self.min_candidates:
            logger.warning(f"Schema linking returned too few candidates: {len(candidates)}")
            metrics.schema_linking_fallback_count.inc(labels={"reason": "empty_candidates"})
            return SchemaLinkingResult(
                candidates=candidates,
                fallback_triggered=True,
                fallback_reason="empty_candidates",
            )
        
        max_confidence = max(c.confidence for c in candidates) if candidates else 0
        if max_confidence < self.min_confidence:
            logger.warning(f"Schema linking confidence too low: {max_confidence}")
            metrics.schema_linking_fallback_count.inc(labels={"reason": "low_confidence"})
            return SchemaLinkingResult(
                candidates=candidates,
                fallback_triggered=True,
                fallback_reason="low_confidence",
            )
        
        return SchemaLinkingResult(candidates=candidates)
```

---

### 需求 0.14: 灰度开关与回滚机制

**用户故事**: 作为系统架构师，我希望 vNext 功能有完善的灰度开关和回滚机制，确保工程可控性。

**优先级**: P1（工程可控性）

**设计来源**：GPT-5.2 Section 11 - 数据迁移与回滚机制

**核心思路**：
- 新功能写入新 namespace，不覆盖旧键
- 回滚只需关闭开关 + 删除/忽略新 namespace
- 数据最小化，不落盘敏感信息

#### 验收标准

1. THE System SHALL 实现以下灰度开关（可通过配置文件或环境变量控制）：
   - `SEMANTIC_PARSER_VNEXT_ENABLED`: vNext 总开关（默认 False）
   - `INTENT_ROUTER_ENABLED`: IntentRouter 开关（默认 False）
   - `SCHEMA_LINKING_ENABLED`: Schema Linking 开关（默认 False）
   - `COMPUTATION_PLANNER_ENABLED`: ComputationPlanner 开关（默认 False）
   - `VALIDATOR_ENABLED`: Validator 开关（默认 False）
2. THE System SHALL 使用版本化 namespace 存储 vNext 缓存：
   - 格式：`("semantic_parser", "vnext", datasource_luid)`
   - 与旧版 namespace 隔离，不覆盖旧键
3. THE System SHALL 支持快速回滚（GPT-5.2 审查修正）：
   - 关闭 `SEMANTIC_PARSER_VNEXT_ENABLED` 即可回退到旧链路
   - **支持两种生效方式（二选一）**：
     - 方式 A：请求级覆盖（通过请求头 `X-Semantic-Parser-Version`）
     - 方式 B：服务重启/热加载配置
   - **不强制要求"无需重启服务"**（取决于配置加载实现）
4. THE System SHALL 支持数据回滚（GPT-5.2 审查修正）：
   - **允许两种实现方式（二选一）**：
     - 方式 A：恢复 `langgraph_store.db` 备份（最可靠）
     - 方式 B：namespace 版本隔离 + 永远不读旧 vNext 数据（逻辑回滚）
   - **注意**：SqliteStore 不支持 pattern delete，因此"按 namespace 删除"需要确认存储能力
   - 如果存储不支持 `adelete_namespace`，则使用方式 A（备份恢复）
5. THE System SHALL 在缓存中不落盘敏感信息：
   - 不存储 `sample_values`（可能含业务数据）
   - 不存储用户原始问题（可能含 PII）
6. THE System SHALL 记录灰度开关状态变更日志
7. THE System SHALL 支持按请求级别的灰度控制：
   - 通过请求头 `X-Semantic-Parser-Version: vnext` 强制使用 vNext
   - 通过请求头 `X-Semantic-Parser-Version: legacy` 强制使用旧链路
   - 用于测试、验证和紧急回滚
8. THE System SHALL 定义回滚验收标准（GPT-5.2 审查补充）：
   - Golden set 全通过
   - 关键指标恢复到基线：
     - P95 延迟恢复到回滚前水平（±10%）
     - LLM calls/request 恢复到回滚前水平（±10%）
     - 错误率恢复到回滚前水平（±5%）
   - 关键接口（`/api/chat`）无异常
9. THE System SHALL 记录回滚前后的指标对比日志

**实现建议**：

```python
# config/feature_flags.py

from pydantic_settings import BaseSettings

class FeatureFlags(BaseSettings):
    """vNext 灰度开关"""
    
    # 总开关
    semantic_parser_vnext_enabled: bool = False
    
    # 子功能开关
    intent_router_enabled: bool = False
    schema_linking_enabled: bool = False
    computation_planner_enabled: bool = False
    validator_enabled: bool = False
    
    class Config:
        env_prefix = ""  # 直接使用环境变量名

# 全局实例
feature_flags = FeatureFlags()


# infra/storage/vnext_store.py

class VNextStore:
    """vNext 版本化存储"""
    
    VNEXT_NAMESPACE_PREFIX = ("semantic_parser", "vnext")
    
    def __init__(self, base_store: LangGraphStore):
        self.base_store = base_store
    
    def get_namespace(self, datasource_luid: str) -> tuple:
        """获取 vNext namespace"""
        return (*self.VNEXT_NAMESPACE_PREFIX, datasource_luid)
    
    async def put(
        self,
        datasource_luid: str,
        key: str,
        value: dict,
        exclude_sensitive: bool = True,
    ):
        """存储数据 - 自动过滤敏感字段"""
        if exclude_sensitive:
            value = self._filter_sensitive_fields(value)
        
        namespace = self.get_namespace(datasource_luid)
        await self.base_store.aput(namespace, key, value)
    
    def _filter_sensitive_fields(self, value: dict) -> dict:
        """过滤敏感字段"""
        sensitive_keys = {"sample_values", "user_question", "raw_input"}
        return {k: v for k, v in value.items() if k not in sensitive_keys}
    
    async def delete_vnext_data(self, datasource_luid: str | None = None):
        """删除 vNext 数据（用于回滚）"""
        if datasource_luid:
            namespace = self.get_namespace(datasource_luid)
            await self.base_store.adelete_namespace(namespace)
        else:
            # 删除所有 vNext 数据
            await self.base_store.adelete_namespace(self.VNEXT_NAMESPACE_PREFIX)


# subgraph.py - 灰度路由

def route_by_feature_flag(state: SemanticParserState) -> str:
    """根据灰度开关路由"""
    # 请求级别覆盖
    if state.config.get("force_vnext"):
        return "vnext_entry"
    
    # 全局开关
    if feature_flags.semantic_parser_vnext_enabled:
        return "vnext_entry"
    
    return "legacy_entry"
```

---

### Phase 1: 预处理 + Schema Linking（最大增益）

### 需求 1: 预处理层 - Preprocess Node

**用户故事**: 作为系统架构师，我希望在 LLM 调用前完成确定性预处理，把"高频可规则化"的不确定性从 LLM 中剥离。

**兼容性**: 中（新增节点，需修改子图）

#### 验收标准

1. THE System SHALL 在子图中新增 `preprocess` 节点，位于 `step1` 之前
2. THE System SHALL 实现 `normalize()` 函数：
   - 全角半角归一
   - 空白字符归一
   - 常见单位归一（万/千/亿）
   - 数字格式统一
3. THE System SHALL 实现 `extract_time()` 函数（0 LLM）：
   - 规则解析相对时间："近N天/本周/上周/本月/上月/今年/去年"
   - 输出标准 `[start_date, end_date]`（date 粒度，非秒级）
   - 标记 `is_relative=True/False` 用于缓存失效
4. THE System SHALL 实现 `extract_slots()` 函数：
   - 从最近 1-3 轮对话中解析已确认项（字段/粒度/时间范围/过滤项）
   - 输出结构化 `memory_slots`
5. THE System SHALL 实现 `build_canonical()` 函数：
   - 生成稳定的 `canonical_question` 用于缓存 key
   - 把时间表达替换成标准形式（如"上月"→`time:last_month`）
6. THE System SHALL 在 `SemanticParserState` 中新增字段：
   - `canonical_question: str`
   - `time_context: TimeContext`（含 start_date, end_date, is_relative, grain_hint）
   - `memory_slots: MemorySlots`

**关键改动**:
- 删除 `Step1Component` 中的 `current_time` 秒级依赖
- 改传入 `current_date` 与解析后的 `time_context`

---

### 需求 2: Schema Linking 层 - 候选字段前置检索

**用户故事**: 作为系统架构师，我希望在 Step1 之前完成字段候选检索，让模型只能从候选集合中选择，大幅降低幻觉。

**兼容性**: 低（需重构 Step1 输入）

#### 验收标准

1. THE System SHALL 在子图中新增 `schema_linking` 节点，位于 `preprocess` 之后、`step1` 之前
2. THE System SHALL 实现问题级 schema 检索：
   - 对整句 `canonical_question` 做一次检索
   - 返回 top-N 相关字段（维度/度量分桶）
   - 包含样例值、层级信息
3. THE System SHALL 实现实体级 schema 检索：
   - 对抽取出的候选业务术语并行检索候选字段/候选值
4. THE System SHALL 复用现有 `FieldIndexer/SemanticMapper`，增强：
   - 批量 embedding 接口
   - 候选集缓存/预热
5. THE System SHALL 在 `SemanticParserState` 中新增字段：
   - `schema_candidates: SchemaCandidates`（含 dimensions, measures, filter_values）
6. THE System SHALL 约束后续模型只能从候选集合中选择

**性能目标**:
- Step1 prompt 从 O(|fields|) 降到 O(k)，k=30~50

---

### 需求 3: Step1 重构 - 受约束生成

**用户故事**: 作为系统架构师，我希望 Step1 只在候选集中选择字段，而非自由生成字段名。

**兼容性**: 中（需修改 Step1Output Schema 和 Prompt）

#### 验收标准

1. THE System SHALL 重构 `Step1Component.execute()` 输入：
   - 从: `question + full data_model_str + history_str + current_time`
   - 改为: `canonical_question + slots + time_context + schema_candidates`
2. THE System SHALL 修改 `Step1Output` 输出格式：
   - 字段引用从"自由文本字段名"改为"候选ID/规范字段名"
   - 新增 `field_references: list[FieldReference]`（含 candidate_id, confidence）
3. THE System SHALL 删除 `_format_data_model()` 中的全量字段注入
4. THE System SHALL 修改 `prompts/step1.py`：
   - 注入 schema_candidates 摘要（非全量）
   - 指导模型从候选中选择
5. THE System SHALL 删除 `restated_question`，新增 `canonical_question`：
   - canonical form（语言无关、机器可读）
   - 用于缓存键和模板匹配

---

### 需求 4: 计算规划层 - 模板化 + 代码校验

**用户故事**: 作为系统架构师，我希望常见计算通过模板库处理，只有长尾场景才调用 LLM。

**兼容性**: 中（新增模块，弱化 Step2）

#### 验收标准

1. THE System SHALL 新增 `ComputationPlanner` 组件
2. THE System SHALL 实现计算模板库，覆盖：
   - 同比（YoY）
   - 环比（MoM）
   - 排名（Rank）
   - 占比（Percent of Total）
   - 移动平均（Moving Average）
   - 累计（Running Total）
3. THE System SHALL 实现约束求解：
   - 通过 query 粒度与 `dimension_hierarchy` 决定 `partition_by`
   - 通过字段类型与是否预聚合决定 aggregation 合法性
4. THE System SHALL 弱化 `Step2Component`：
   - 仅作为 fallback（heavy path）
   - 当模板无法覆盖或歧义很大时才调用
5. THE System SHALL 把 Step2 的 self-validation 改为代码校验的输入：
   - 不再"信任 LLM 输出"
   - 代码层做强校验

---

### 需求 5: 后处理层 - Validator 组件

**用户故事**: 作为系统架构师，我希望在执行前完成确定性校验和可规则修复，减少无效重试。

**兼容性**: 中（新增组件）

#### 验收标准

1. THE System SHALL 新增 `Validator` 组件
2. THE System SHALL 实现强校验：
   - 字段存在性
   - 类型匹配
   - 聚合合法性
   - `partition_by ⊆ query_dimensions`（分区维度必须是查询维度的子集）
   - 字段唯一性（去重）
3. THE System SHALL 实现可规则修复（替代部分 ReAct LLM）：
   - 去重 measures
   - 纠正聚合
   - 把不存在的字段转入澄清列表
   - 权限错误快速失败
4. THE System SHALL 实现统一澄清协议 `ClarificationRequest`：
   - 字段歧义
   - 低置信度映射
   - 过滤值未命中
   - 可被前端渲染为选项

---

### 需求 6: ReAct 重构 - 规则化优先

**用户故事**: 作为系统架构师，我希望高频错误通过规则快速处理，把重试预算留给长尾问题。

**兼容性**: 中（重构现有组件）

#### 验收标准

1. THE System SHALL 重构 `ReActErrorHandler`：
   - 先走 deterministic error classifier
   - 只把"长尾不可归因"交给 LLM ReAct
2. THE System SHALL 实现 deterministic error classifier，识别：
   - FIELD_NOT_FOUND → 快速失败或转澄清
   - PERMISSION_DENIED → 快速失败
   - TYPE_MISMATCH → 尝试规则修复
   - AGGREGATION_CONFLICT → 尝试规则修复
   - TIMEOUT → 快速失败
3. THE System SHALL 对可修复项优先 CORRECT（减少重试与二次 LLM）
4. THE System SHALL 记录错误分类分布指标

---

### 需求 7: 批量 Embedding 计算

**用户故事**: 作为系统架构师，我希望将多个字段的 embedding 计算合并为单次批量调用。

**兼容性**: 低（需重构 embedding provider）

#### 验收标准

1. THE System SHALL 把 `SemanticMapper/embedding provider` 的单 term `embed_query` 改为 batch 接口
2. THE System SHALL 支持配置批量大小上限（默认 20）
3. THE System SHALL 实现"先 batch embed → 再并行检索/重排"模式
4. THE System SHALL 记录批量调用的性能指标

---

### 需求 8: 精确匹配 O(1) 优化

**用户故事**: 作为系统架构师，我希望精确匹配从全表扫描优化为哈希查找。

**兼容性**: 高（内部优化）

#### 验收标准

1. THE System SHALL 在 `FieldIndexer` 内建立哈希索引：
   - `lower(field_name) -> chunk`
   - `lower(field_caption) -> chunk`
2. THE System SHALL 把 `_try_exact_match()` 从 O(n) 优化为 O(1)
3. THE System SHALL 记录精确匹配命中率指标

---

### 需求 9: 异步 Reranker + 超时降级

**用户故事**: 作为系统架构师，我希望 Reranker 超时时能快速降级，不阻塞主流程。

**兼容性**: 中（重构调用模式）

#### 验收标准

1. THE System SHALL 支持异步 Reranker 调用
2. WHEN Reranker 超时时 THEN THE System SHALL 直接返回未 rerank 的候选
3. THE System SHALL 支持配置 Reranker 超时时间（默认 3 秒）
4. THE System SHALL 记录 Reranker 超时率指标

---

### 需求 10: 候选集缓存

**用户故事**: 作为系统架构师，我希望缓存 schema linking 结果，命中时跳过检索与 rerank。

**兼容性**: 中（新增缓存层）

#### 验收标准

1. THE System SHALL 实现两级缓存：
   - L1: 请求内 memo（同一轮重试复用）
   - L2: SqliteStore（跨请求复用）
2. THE System SHALL 缓存"问题→top-k schema candidates"
3. THE System SHALL 缓存"term→top-k field candidates"
4. THE System SHALL 使用 `hash(canonical_question + current_date + datasource_luid)` 作为缓存键
5. THE System SHALL 对"含相对时间"条目跨天自动失效
6. THE System SHALL 支持配置缓存 TTL（默认 24 小时）

---

### 需求 11: FAISS 索引懒加载/预热

**用户故事**: 作为系统架构师，我希望 FAISS 索引按需加载，并支持预热策略。

**兼容性**: 中（重构存储层）

#### 验收标准

1. THE System SHALL 支持 FAISS 索引的持久化存储
2. THE System SHALL 实现 FAISS 索引的懒加载
3. THE System SHALL 支持配置索引预热策略
4. THE System SHALL 支持增量更新 FAISS 索引（避免全量重建）

---

### 需求 12: 可观测性增强

**用户故事**: 作为运维人员，我希望能够监控语义解析器各层的性能和错误率。

**兼容性**: 高（纯增量）

**GPT-5.2 审查补充**：
- 需要补充吞吐/并发指标，验证"批量 embedding"在真实并发下是否生效
- 需要明确指标的采集点和口径

#### 验收标准

1. THE System SHALL 记录以下延迟指标：
   - Preprocess 耗时
   - Schema Linking 耗时（embedding/检索/rerank 分段）
   - Step1 LLM 调用延迟、token 数
   - Step2 LLM 调用延迟（或模板命中率）
   - 缓存命中率（L1/L2 分别统计）
   - 错误分类分布
   - 重试次数分布（按类型：格式/语义）
2. THE System SHALL 记录以下吞吐/并发指标（GPT-5.2 审查补充 - 明确采集点/口径）：
   - `requests_per_minute`: 每分钟请求数
     - **采集点**：subgraph 入口
     - **口径**：滑动窗口计数器（1 分钟窗口，10 秒滑动）
     - **类型**：Counter（累计值，通过差值计算 RPM）
   - `concurrent_requests`: 并发请求数
     - **采集点**：subgraph 入口/出口
     - **口径**：进程内 Gauge（入口 +1，出口 -1）
     - **类型**：Gauge（瞬时值）
   - `batch_embedding_batch_size_distribution`: 批量 embedding 的 batch size 分布
     - **采集点**：embedding 调用处
     - **口径**：Histogram（桶：1, 2, 4, 8, 16, 32, 64）
     - **类型**：Histogram
   - `batch_embedding_utilization`: 批量 embedding 利用率
     - **采集点**：embedding 调用处
     - **口径**：实际 batch size / 配置的最大 batch size
     - **类型**：Gauge（百分比）
   - `batch_embedding_wait_time_ms`: 批量 embedding 等待时间
     - **采集点**：embedding 调用处
     - **口径**：从请求入队到开始执行的等待时间
     - **类型**：Histogram
3. THE System SHALL 支持结构化日志输出
4. THE System SHALL 支持 OpenTelemetry 集成（可选）

---

### 需求 13: 重试预算管理

**用户故事**: 作为系统架构师，我希望限制单次请求的重试次数和资源消耗。

**兼容性**: 高（增强现有机制）

**GPT-5.2 审查补充**：
- 重试预算需要分类，避免"格式问题吃掉语义重试预算"
- 格式重试（JSON/校验）与语义重试（字段/计算修复）应独立计数

#### 验收标准

1. THE System SHALL 支持分类重试预算：
   - **格式重试预算**：JSON 解析失败、Pydantic 校验失败（默认 2 次）
   - **语义重试预算**：字段不存在、计算不合法、执行失败（默认 2 次）
   - 两类预算独立计数，互不影响
2. THE System SHALL 支持配置总重试预算（按 Token 或时间）：
   - 默认 Token 预算：5000 tokens
   - 默认时间预算：10 秒
3. WHEN 任一类重试预算耗尽时 THEN THE System SHALL 返回 ABORT
4. THE System SHALL 在重试时携带结构化错误反馈给 LLM
5. THE System SHALL 记录重试次数分布指标（按类型分类）：
   - `parse_retry_count_distribution`（格式解析重试）
   - `semantic_retry_count_distribution`（语义重试）
   - `total_retry_budget_exhausted_count`

---

### 需求 14: 统一澄清协议

**用户故事**: 作为用户，当系统对我的问题理解不确定时，我希望系统能够以统一格式主动询问澄清。

**兼容性**: 中（统一现有机制）

**设计说明**：项目未上线，只做内部契约一致性，不做旧行为兼容。

#### 验收标准

1. THE System SHALL 定义统一的 `ClarificationRequest` 数据结构：
   - `type`: FIELD_AMBIGUOUS | LOW_CONFIDENCE | FILTER_VALUE_NOT_FOUND | MULTIPLE_INTERPRETATION
   - `options`: 候选选项列表（对外 API 字段名）
   - `message`: 用户友好的澄清问题
2. THE System SHALL 统一以下场景的澄清触发：
   - 字段映射置信度 < 0.7
   - 多个候选字段得分接近
   - 过滤值未命中
3. THE System SHALL 支持"用户澄清回填机制"：
   - 用户选择结果写入 `memory_slots`
   - 后续对话可复用

---

### 需求 15: MapFields 瘦身

**用户故事**: 作为系统架构师，我希望 MapFields 在 Schema Linking 前置后变得更轻量。

**兼容性**: 中（依赖需求 2）

#### 验收标准

1. WHEN Step1 输出能唯一定位字段（候选ID/规范名）THEN MapFields 只做校验，不用 RAG
2. WHEN Step1 输出仍是自由文本或置信度低 THEN MapFields 启动 RAG fallback
3. THE System SHALL 把 MapFields 输入从"业务术语"升级为"带候选/带置信度策略"的映射请求
4. THE System SHALL 支持批量与并行映射

---

### 需求 16: ResolveFilterValues 前置检索

**用户故事**: 作为系统架构师，我希望在执行前就检测过滤值问题，而非等执行完 0 行才问。

**兼容性**: 中（重构现有逻辑）

#### 验收标准

1. THE System SHALL 把 ResolveFilterValues 策略改成：
   - 先候选值检索/采样
   - 再决定是否澄清
2. THE System SHALL 在 Schema Linking 阶段就检索候选过滤值
3. WHEN 过滤值不在候选中 THEN THE System SHALL 立即触发澄清（不等执行）

---

## 非功能需求

### 性能需求

| 指标 | 当前值 | 目标值 | 说明 |
|------|--------|--------|------|
| Step1 prompt token 数 | O(\|fields\|) | O(k), k≤50 | Schema Linking 前置 |
| 平均 LLM 调用次数 | 2-3 次/请求 | ≤ 1.5 次/请求 | 模板化 + 缓存 |
| P95 延迟 | ~3s | ≤ 2s | 减少 LLM 调用 |
| 精确匹配复杂度 | O(n) | O(1) | 哈希索引 |
| 缓存命中率 | 0% | ≥ 30% | 两级缓存 |

### 质量需求

| 指标 | 当前值 | 目标值 | 说明 |
|------|--------|--------|------|
| Build 成功率 | - | ≥ 95% | 强校验 + 规则修复 |
| Execute 成功率 | - | ≥ 90% | 前置澄清 |
| 字段映射 top-1 accuracy | ~95% | ≥ 97% | 候选约束 |
| 澄清一次解决率 | - | ≥ 80% | 统一澄清协议 |

### 可维护性需求

1. 新增代码需要单元测试覆盖（≥ 80%）
2. 关键路径需要集成测试覆盖
3. 配置项需要文档说明

---

## 风险与缓解

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| Schema Linking 召回不足导致正确字段被过滤 | 高 | 中 | 增大 top-k，保留 RAG fallback |
| 时间解析规则覆盖不全 | 中 | 中 | 渐进式添加规则，LLM 兜底 |
| 计算模板库覆盖不全 | 中 | 中 | Step2 LLM 作为 fallback |
| 候选集缓存假命中（时间语义漂移） | 高 | 中 | 使用 date 粒度缓存键，跨天自动失效 |
| 大规模重构导致回归 | 高 | 中 | 渐进式改造，保持向后兼容 |
| 规则修复器覆盖不全 | 中 | 低 | ReAct LLM 作为 fallback |

---

## 实施优先级

基于 GPT-5.2 代码审查，按"先修工程闭环，再落地新功能"原则排序：

### Phase 0: 工程债务清理（前置条件，1-2 周）

| 需求 | 优先级 | 预估工时 | 依赖 |
|------|--------|----------|------|
| 需求 0.1: 统一入口与状态契约 | P0 | 1d | 无 |
| 需求 0.2: ReAct 覆盖解析失败 | P0 | 1d | 需求 0.1 |
| 需求 0.3: Pipeline 贯通 middleware | P0 | 1d | 无 |
| 需求 0.4: token 硬性上限保护 | P0 | 0.5d | 无 |
| 需求 0.5: 基础可观测性 | P0 | 1d | 无 |
| 需求 0.6: 组件级解析重试 | P0 | 1d | 无 |
| 需求 0.7: JSON 解析增强 | P1 | 0.5d | 无 |
| 需求 0.8: tool_calls 解析错误处理 | P1 | 0.5d | 无 |
| 需求 0.9: LLM 空响应处理 | P1 | 0.5d | 无 |
| 需求 0.10: Step1 history 对齐 | P1 | 1d | 需求 0.4 |
| 需求 0.11: 完整 middleware 钩子 | P2 | 1d | 需求 0.6 |
| 需求 0.12: IntentRouter 意图识别 | P1 | 2d | 无 |
| 需求 0.13: Schema Linking 回退路径 | P1 | 1d | 需求 2 |
| 需求 0.14: 灰度开关与回滚机制 | P1 | 1d | 无 |

**Phase 0 预期收益**:
- 工程行为确定性
- 自愈率显著提升
- 重试机制闭环
- 结构化输出稳定性提升
- 问题定位能力增强
- 为后续优化奠定稳定基础
- 意图识别前置分流，减少不必要的 LLM 调用
- Schema Linking 正确性护栏，避免系统性错误
- 灰度开关保障工程可控性

### Phase 1: 预处理 + Schema Linking（最大增益，1-2 周）

| 需求 | 优先级 | 预估工时 | 依赖 |
|------|--------|----------|------|
| 需求 1: 预处理层 | P0 | 3d | 无 |
| 需求 2: Schema Linking 层 | P0 | 4d | 需求 1 |
| 需求 3: Step1 重构 | P0 | 3d | 需求 2 |
| 需求 8: 精确匹配 O(1) | P0 | 0.5d | 无 |

**Phase 1 预期收益**:
- Step1 prompt token 从 O(|fields|) 降到 O(k)
- 字段幻觉大幅减少
- 为后续优化奠定基础

### Phase 2: 计算规划 + 校验（减少 LLM 调用）

| 需求 | 优先级 | 预估工时 | 依赖 |
|------|--------|----------|------|
| 需求 4: 计算规划层 | P1 | 4d | 需求 3 |
| 需求 5: Validator 组件 | P1 | 2d | 需求 3 |
| 需求 6: ReAct 重构 | P1 | 2d | 需求 5 |
| 需求 14: 统一澄清协议 | P1 | 2d | 需求 5 |

**Phase 2 预期收益**:
- Step2 LLM 调用减少 70%+（模板覆盖）
- ReAct LLM 调用减少 50%+（规则化优先）
- 澄清体验统一

### Phase 3: 性能优化（缓存 + 并行）

| 需求 | 优先级 | 预估工时 | 依赖 |
|------|--------|----------|------|
| 需求 7: 批量 Embedding | P1 | 2d | 需求 2 |
| 需求 10: 候选集缓存 | P1 | 2d | 需求 2 |
| 需求 9: 异步 Reranker | P2 | 1d | 需求 7 |
| 需求 11: FAISS 懒加载 | P2 | 2d | 需求 10 |

**Phase 3 预期收益**:
- 缓存命中率 ≥ 30%
- 批量 embedding 减少 API 调用

### Phase 4: 可观测性 + 收尾

| 需求 | 优先级 | 预估工时 | 依赖 |
|------|--------|----------|------|
| 需求 12: 可观测性增强 | P1 | 2d | 无（可并行） |
| 需求 13: 重试预算管理 | P1 | 1d | 需求 6 |
| 需求 15: MapFields 瘦身 | P2 | 1d | 需求 2 |
| 需求 16: ResolveFilterValues 前置 | P2 | 1d | 需求 2 |

---

## 依赖关系图

```
┌─────────────────────────────────────────────────────────────────┐
│  Phase 0: 工程债务清理（前置条件）                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  需求 0.1 (统一入口) ──▶ 需求 0.2 (ReAct 覆盖解析失败)         │
│                                                                 │
│  需求 0.3 (Pipeline middleware) [独立]                          │
│  需求 0.4 (token 上限) ──▶ 需求 0.10 (Step1 history 对齐)       │
│  需求 0.5 (基础可观测) [独立]                                   │
│  需求 0.6 (组件级解析重试) ──▶ 需求 0.11 (完整钩子)             │
│  需求 0.7 (JSON 解析增强) [独立]                                 │
│  需求 0.8 (tool_calls 解析) [独立]                              │
│  需求 0.9 (LLM 空响应) [独立]                                   │
│  需求 0.12 (IntentRouter) [独立]                                │
│  需求 0.13 (Schema Linking 回退) ──▶ 需求 2                     │
│  需求 0.14 (灰度开关与回滚) [独立]                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ Phase 0 完成后
┌─────────────────────────────────────────────────────────────────┐
│  Phase 1-4: vNext 功能实现                                      │
├─────────────────────────────────────────────────────────────────┤

需求 0.12 (IntentRouter)
    │
    ▼ (意图为 DATA_QUERY 时)
需求 1 (预处理)
    │
    ▼
需求 2 (Schema Linking) ──┬──▶ 需求 7 (批量 Embedding)
    │                     │
    │                     ├──▶ 需求 0.13 (回退路径)
    │                     │
    │                     └──▶ 需求 10 (候选集缓存) ──▶ 需求 11 (FAISS 懒加载)
    │                                                        │
    │                                                        ▼
    │                                                  需求 9 (异步 Reranker)
    ▼
需求 3 (Step1 重构)
    │
    ├──▶ 需求 4 (计算规划) ──▶ 弱化 Step2
    │
    └──▶ 需求 5 (Validator) ──┬──▶ 需求 6 (ReAct 重构)
                              │
                              └──▶ 需求 14 (统一澄清)

需求 8 (精确匹配 O(1)) [独立]
需求 12 (可观测性增强) [独立，可并行]
需求 13 (重试预算) ──▶ 需求 6
需求 15 (MapFields 瘦身) ──▶ 需求 2
需求 16 (FilterValues 前置) ──▶ 需求 2

需求 0.14 (灰度开关) ──▶ 所有 vNext 功能（控制开关）

└─────────────────────────────────────────────────────────────────┘
```

---

## 文件映射

### Phase 0: 工程债务清理

| 需求 | 主要修改文件 |
|------|-------------|
| 需求 0.1 | `subgraph.py`, `node.py`, `orchestration/workflow/factory.py`, `orchestration/workflow/routes.py` |
| 需求 0.2 | `subgraph.py` (路由逻辑), `components/react_error_handler.py` |
| 需求 0.3 | `components/query_pipeline.py`, `orchestration/tools/map_fields/tool.py` |
| 需求 0.4 | `components/step1.py`, `prompts/step1.py` |
| 需求 0.5 | `state.py`, `subgraph.py`, 各 components |
| 需求 0.6 | `components/step1.py`, `components/step2.py`, `agents/base/node.py` (parse_json_response) |
| 需求 0.7 | `agents/base/node.py` (parse_json_response 增强日志) |
| 需求 0.8 | `agents/base/node.py` (_call_llm_with_tools_and_middleware 中 tool_calls 解析) |
| 需求 0.9 | `agents/base/node.py` (_call_llm_with_tools_and_middleware 中空响应处理) |
| 需求 0.10 | `components/step1.py`, `state.py` |
| 需求 0.11 | `subgraph.py`, `agents/base/middleware_runner.py` |
| 需求 0.12 | `components/intent_router.py` (新建), `subgraph.py`, `state.py` |
| 需求 0.13 | `components/schema_linking.py`, `field_mapper/node.py` |
| 需求 0.14 | `config/feature_flags.py` (新建), `infra/storage/vnext_store.py` (新建), `subgraph.py` |

### Phase 1-4: vNext 功能实现

| 需求 | 主要修改/新增文件 |
|------|------------------|
| 需求 1 | `components/preprocess.py` (新建), `state.py`, `subgraph.py` |
| 需求 2 | `components/schema_linking.py` (新建), `state.py`, `subgraph.py` |
| 需求 3 | `components/step1.py`, `prompts/step1.py`, `models/step1.py` |
| 需求 4 | `components/computation_planner.py` (新建), `components/step2.py` |
| 需求 5 | `components/validator.py` (新建) |
| 需求 6 | `components/react_error_handler.py`, `prompts/react_error.py` |
| 需求 7 | `field_mapper/rag/semantic_mapper.py`, `infra/embedding/` |
| 需求 8 | `field_mapper/node.py` (修改 `_try_exact_match`)，`field_mapper/rag/field_indexer.py` (新增哈希索引) |
| 需求 9 | `field_mapper/rag/reranker.py` |
| 需求 10 | `infra/storage/candidate_cache.py` (新建) |
| 需求 11 | `field_mapper/rag/faiss_store.py` |
| 需求 12 | `infra/observability/metrics.py` (新建), 各组件 |
| 需求 13 | `subgraph.py`, `state.py` |
| 需求 14 | `models/clarification.py` (新建), `components/validator.py` |
| 需求 15 | `field_mapper/node.py`, `orchestration/tools/map_fields/` |
| 需求 16 | `components/query_pipeline.py` |

---

## 评估方法

### 性能基准测试

**离线 micro-benchmark（分模块）**:
- Preprocess: 耗时
- Schema Linking: embedding/检索/rerank 分段耗时
- Step1: P50/P95 延迟、token 数、缓存命中后延迟
- Pipeline: Map/Build/Execute 各阶段耗时、失败分布

**在线端到端 benchmark（回放真实问题）**:
- 指标: P95 总延迟、LLM 调用次数/请求、缓存命中率、重试次数分布
- 场景拆分: 字段很多/多表/含相对时间/含复杂计算/含筛选值

### 准确率验证

**Golden set**:
- 维护一份带期望输出的测试集（问题→semantic plan→最终执行是否正确）

**对比口径**:
- 旧版 vs vNext: 执行成功率、澄清率、平均 LLM 次数
- Ablation: 只替换 embedding / reranker / schema linking，定位收益来源

**误差归因**:
- 对每个失败样本记录"失败阶段 + 错误类型 + 是否可规则修复"
- 用于迭代 deterministic 修复器与模板库
