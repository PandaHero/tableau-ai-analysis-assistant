# Design Document: Semantic Parser Refactor

## Overview

本设计文档描述了语义解析器（SemanticParser）重构的技术架构和实现方案。采用 **LLM 驱动的简化架构**，核心设计原则是信任 LLM 的推理能力，通过 Prompt 和 Few-shot 提升准确性，支持渐进式查询构建和持续学习。

### 设计目标

1. **简化架构**：减少复杂的前置处理组件，依赖 LLM 原生能力
2. **高准确性**：通过 Top-K 检索 + Few-shot 示例 + 自检机制保证准确性
3. **高效率**：通过缓存、意图路由、Token 优化减少 LLM 调用
4. **可扩展**：支持渐进式查询、用户反馈学习、持续改进

### 参考架构

- **Vanna.ai**：RAG + LLM 架构，用户感知，可训练
- **NeurIPS 2024 "The Death of Schema Linking"**：强推理模型不需要复杂的 Schema Linking

## Architecture

### 整体架构

语义解析器采用 **管道式架构**，每个阶段负责特定任务：

```
用户问题
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 阶段 1: IntentRouter (意图路由)                               │
│ ─────────────────────────────────────────────────────────────│
│ 输入: 用户问题                                                │
│ 输出: 意图类型 (DATA_QUERY / CLARIFICATION / GENERAL / IRRELEVANT) │
│ LLM调用: 0-1 次                                               │
│                                                              │
│ 如果意图是 IRRELEVANT → 直接返回礼貌拒绝                       │
│ 如果意图是 GENERAL → 直接返回元数据相关信息（如字段列表、数据源描述）│
│ 如果意图是 DATA_QUERY → 继续下一阶段                           │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 阶段 2: QueryCache (查询缓存)                                 │
│ ─────────────────────────────────────────────────────────────│
│ 输入: 用户问题, 数据源ID                                       │
│ 输出: 缓存的查询结果 或 继续下一阶段                            │
│ LLM调用: 0 次                                                 │
│                                                              │
│ 如果缓存命中 → 直接返回缓存结果                                │
│ 如果缓存未命中 → 继续下一阶段                                  │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 阶段 3: FieldRetriever (字段检索)                             │
│ ─────────────────────────────────────────────────────────────│
│ 输入: 用户问题, 数据模型                                       │
│ 输出: Top-K 相关字段列表 (默认 K=10)                           │
│ LLM调用: 0 次 (使用向量检索)                                   │
│                                                              │
│ 使用 CascadeRetriever 进行向量检索                            │
│ 精确匹配的字段优先级更高                                       │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 阶段 4: FewShotManager (示例检索)                             │
│ ─────────────────────────────────────────────────────────────│
│ 输入: 用户问题, 数据源ID                                       │
│ 输出: 2-3 个相关的 Few-shot 示例                               │
│ LLM调用: 0 次 (使用向量检索)                                   │
│                                                              │
│ 优先选择用户接受过的查询作为示例                               │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 阶段 5: SemanticUnderstanding (LLM 语义理解) ⭐ 核心阶段       │
│ ─────────────────────────────────────────────────────────────│
│ 输入:                                                        │
│   - 用户问题 + 对话历史                                       │
│   - Top-K 字段列表                                            │
│   - Few-shot 示例                                             │
│   - 当前日期、时区、业务日历配置                               │
│                                                              │
│ 输出:                                                        │
│   - restated_question (完整独立的问题描述)                     │
│   - what (度量列表)                                           │
│   - where (维度、过滤条件)                                     │
│   - computations (派生度量计算逻辑，如 利润率=利润/销售额)      │
│   - needs_clarification (是否需要澄清)                         │
│   - self_check (自检结果)                                      │
│                                                              │
│ LLM调用: 1 次                                                 │
│                                                              │
│ 如果 needs_clarification=true → 返回澄清问题，等待用户输入     │
│ 如果 needs_clarification=false → 继续下一阶段                  │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 阶段 5.5: FilterValueValidator (筛选值验证) ⭐ 新增阶段        │
│ ─────────────────────────────────────────────────────────────│
│ 输入: SemanticOutput 中的 filters                             │
│ 输出: 验证结果 (通过/需要澄清)                                 │
│ LLM调用: 0 次 (查询数据库/缓存)                                │
│                                                              │
│ 验证逻辑:                                                     │
│ 1. 对于每个筛选条件，检查筛选值是否存在于字段中                │
│    例如: filters: [{field: "省份", values: ["上海"]}]         │
│    → 查询"省份"字段是否包含"上海"                              │
│                                                              │
│ 2. 如果筛选值不存在:                                          │
│    - 返回澄清问题，提供相似的候选值                            │
│    - 例如: "省份字段中没有'上海'，您是否指的是'上海市'？"      │
│                                                              │
│ 3. 如果筛选值存在但不完整（模糊匹配）:                         │
│    - 返回澄清问题，让用户确认                                  │
│    - 例如: "找到多个匹配项：上海市、上海浦东，请选择"          │
│                                                              │
│ 如果验证通过 → 继续下一阶段                                    │
│ 如果需要澄清 → 返回澄清问题，等待用户输入                      │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 阶段 6: 查询构建与执行                                        │
│ ─────────────────────────────────────────────────────────────│
│                                                              │
│ 6.1 中间层输出 (SemanticOutput)                               │
│     SemanticUnderstanding 输出的是中间层表示，不是最终查询：    │
│     - what: 度量列表                                          │
│     - where: 维度、过滤条件                                    │
│     - computations: 派生度量计算逻辑                           │
│                                                              │
│ 6.2 查询适配器 (QueryAdapter)                                 │
│     将中间层转换为目标查询语言：                                │
│     - VizQLAdapter: 生成 Tableau VizQL                        │
│     - SQLAdapter: 生成标准 SQL (可扩展)                        │
│                                                              │
│ 6.3 简单查询 vs 复杂查询                                       │
│                                                              │
│     简单查询 (how_type=SIMPLE):                               │
│     - 直接聚合：SUM(销售额) GROUP BY 地区                      │
│     - 简单过滤：WHERE 日期 IN 上个月                           │
│     - 无派生计算                                              │
│     - Prompt: 使用简化模板，减少 token                         │
│                                                              │
│     复杂查询 (how_type=COMPLEX):                              │
│     - 派生度量：利润率 = 利润/销售额                           │
│     - LOD 表达式：FIXED [地区] : SUM(销售额)                   │
│     - 表计算：排名、同比、环比                                 │
│     - Prompt: 使用完整模板，包含计算示例                       │
│                                                              │
│ 6.4 动态 Prompt 生成                                          │
│     根据查询复杂度动态调整 Prompt：                            │
│     - 简单查询: 精简 Prompt，减少 token 消耗                   │
│     - 复杂查询: 完整 Prompt，包含计算逻辑示例                   │
│     - 根据字段类型: 包含相关字段的 Few-shot 示例               │
│                                                              │
│ 输入: SemanticOutput (中间层)                                 │
│ 输出: 目标查询语句 + 执行结果                                  │
│                                                              │
│ 如果执行成功 → 继续下一阶段                                    │
│ 如果执行失败 → 进入错误修正流程                                │
└──────────────────────────────────────────────────────────────┘
    │
    ├─── 执行失败 ───┐
    │                ▼
    │   ┌──────────────────────────────────────────────────────┐
    │   │ 阶段 6.1: ErrorCorrector (错误修正)                   │
    │   │ ──────────────────────────────────────────────────── │
    │   │ 输入: 原始问题, 之前的输出, 错误信息                   │
    │   │ 输出: 修正后的 SemanticOutput                         │
    │   │ LLM调用: 1 次                                         │
    │   │                                                      │
    │   │ 最多重试 3 次                                         │
    │   │ 如果重试成功 → 返回阶段 6 重新执行                     │
    │   │ 如果重试失败 → 返回错误信息给用户                      │
    │   └──────────────────────────────────────────────────────┘
    │                │
    │                │ 重试
    │   ◄────────────┘
    │
    ▼ 执行成功
┌──────────────────────────────────────────────────────────────┐
│ 阶段 7: FeedbackLearner (反馈学习)                            │
│ ─────────────────────────────────────────────────────────────│
│ 输入: 查询结果, 用户反馈                                       │
│ 输出: 更新缓存, 记录反馈                                       │
│ LLM调用: 0 次                                                 │
│                                                              │
│ - 缓存成功的查询                                              │
│ - 记录用户反馈 (accept/modify/reject)                         │
│ - 学习同义词映射                                              │
│ - 将高质量查询提升为 Few-shot 示例                             │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
  返回结果
```

### LLM 调用次数分析

| 场景 | LLM 调用次数 |
|------|-------------|
| 缓存命中 | 0-1 次 (IntentRouter) |
| 简单查询，一次成功 | 1-2 次 (IntentRouter + SemanticUnderstanding) |
| 需要澄清 | 1-2 次 (每轮对话) |
| 执行失败需要修正 | 2-5 次 (最多 3 次重试) |

### 错误恢复与澄清流程

当系统返回 `needs_clarification=true` 时（无论来源是 SemanticUnderstanding 还是 FilterValueValidator），用户的后续输入作为**新的对话轮次**处理：

```
错误恢复流程:
┌─────────────────────────────────────────────────────────────────┐
│                    澄清/错误恢复流程                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. SemanticUnderstanding 返回 needs_clarification=true:         │
│     └─ 用户回复 → 作为新问题，从 IntentRouter 重新开始            │
│        （对话历史会保留，LLM 可以理解上下文）                     │
│                                                                  │
│  2. FilterValueValidator 返回 has_unresolvable_filters=true:     │
│     └─ 用户回复 → 作为新问题，从 IntentRouter 重新开始            │
│        （用户需要提供正确的筛选值）                               │
│                                                                  │
│  3. FilterValueValidator 触发 interrupt()（有相似值可选）:        │
│     └─ 用户选择 → 通过 graph.update_state() 恢复执行              │
│        （不重新开始，直接继续到 QueryAdapter）                    │
│                                                                  │
│  4. ErrorCorrector 达到最大重试次数:                              │
│     └─ 返回错误信息给用户                                         │
│        用户可以重新提问，从 IntentRouter 开始                     │
└─────────────────────────────────────────────────────────────────┘

设计原则:
- 澄清后的用户输入视为新的对话轮次，符合渐进式查询的设计理念
- 对话历史通过 LangGraph checkpoint 保留，LLM 可以理解上下文
- 只有 interrupt() 中断（筛选值确认）支持原地恢复，其他情况都从头开始
```

### 渐进式查询示例

```
第1轮对话:
─────────
用户: "我想看销售数据"

IntentRouter: DATA_QUERY
FieldRetriever: 检索到 [销售额, 利润, 成本, 地区, 产品, 日期, ...]
SemanticUnderstanding:
  - restated_question: "查询销售额"
  - what: {measures: ["销售额"]}
  - where: {dimensions: [], filters: []}
  - needs_clarification: true
  - clarification_question: "请问您想看哪个时间段的销售数据？"
  - clarification_options: ["本月", "上个月", "本季度", "今年"]

系统返回: "请问您想看哪个时间段的销售数据？"


第2轮对话:
─────────
用户: "上个月的，按地区"

SemanticUnderstanding:
  - restated_question: "查询上个月各地区的销售额"
  - what: {measures: ["销售额"]}
  - where: {dimensions: ["地区"], filters: [{field: "日期", range: "上个月"}]}
  - needs_clarification: false

系统: 生成查询 → 执行 → 返回结果


第3轮对话 (派生度量示例):
─────────
用户: "利润率是多少？"

SemanticUnderstanding:
  - restated_question: "查询上个月各地区的利润率"
  - what: {measures: ["利润", "销售额"]}  # 分解为基础度量
  - where: {dimensions: ["地区"], filters: [{field: "日期", range: "上个月"}]}
  - computations: [{
      name: "profit_rate",
      display_name: "利润率",
      formula: "[利润]/[销售额]",
      calc_type: "RATIO",
      base_measures: ["利润", "销售额"]
    }]
  - needs_clarification: false

系统: 生成查询 → 执行 → 返回结果
```

## Components and Interfaces

### 1. IntentRouter

**职责**：轻量级意图识别，过滤非数据查询

```python
class IntentType(str, Enum):
    DATA_QUERY = "data_query"      # 数据查询
    CLARIFICATION = "clarification" # 需要澄清
    GENERAL = "general"            # 元数据问答
    IRRELEVANT = "irrelevant"      # 无关问题

class IntentRouterOutput(BaseModel):
    intent_type: IntentType
    confidence: float  # 0-1
    reason: str
    source: str  # L0_RULE / L1_MODEL / L2_FALLBACK

class IntentRouter:
    async def route(
        self,
        question: str,
        context: Dict[str, Any],
        config: Optional[RunnableConfig] = None,
    ) -> IntentRouterOutput:
        """执行意图识别"""
        pass
```

### 2. QueryCache

**职责**：查询缓存管理

**实现方案**：

```
缓存架构:
┌─────────────────────────────────────────────────────────────────┐
│                        QueryCache                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐    ┌─────────────────┐                     │
│  │  精确匹配缓存    │    │  语义相似缓存    │                     │
│  │  (Hash Map)     │    │  (Vector Store)  │                     │
│  └────────┬────────┘    └────────┬────────┘                     │
│           │                      │                               │
│           ▼                      ▼                               │
│  Key: hash(question + datasource_luid)                          │
│  Value: CachedQuery                                              │
│                                                                  │
│  存储后端: LangGraph SqliteStore (复用现有基础设施)               │
└─────────────────────────────────────────────────────────────────┘

缓存查询流程:
1. 精确匹配: hash(question) → 直接查找
2. 语义匹配: embedding(question) → 向量相似度搜索 → 阈值过滤 (>0.95)

缓存失效策略:
- TTL 过期: 默认 24 小时
- 数据模型变更: 通过 schema_hash 比较检测变更，自动失效
- 手动失效: 支持按数据源批量失效
```

**Schema Hash 失效机制详解**：

```
Schema Hash 计算与比较:
┌─────────────────────────────────────────────────────────────────┐
│                    Schema Hash 机制                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Schema Hash 计算:                                            │
│     hash = MD5(sorted([                                          │
│       f"{field.name}:{field.data_type}:{field.role}"            │
│       for field in data_model.fields                            │
│     ]))                                                          │
│                                                                  │
│  2. 失效触发时机:                                                │
│     ├─ 缓存读取时: 比较 cached.schema_hash vs current_schema_hash│
│     │   → 不匹配则视为缓存失效，返回 None                        │
│     └─ 数据模型加载时: 可选的主动失效扫描                        │
│                                                                  │
│  3. 变更检测范围:                                                │
│     ├─ 字段新增/删除 → schema_hash 变化 → 缓存失效               │
│     ├─ 字段类型变更 → schema_hash 变化 → 缓存失效               │
│     ├─ 字段角色变更 → schema_hash 变化 → 缓存失效               │
│     └─ 字段描述变更 → schema_hash 不变 → 缓存保留               │
│                                                                  │
│  4. 性能考虑:                                                    │
│     ├─ schema_hash 在 DataModel 加载时计算一次                   │
│     ├─ 缓存读取时只做字符串比较，O(1) 复杂度                     │
│     └─ 无需遍历所有缓存条目                                      │
└─────────────────────────────────────────────────────────────────┘
```

**接口定义**：

```python
class CachedQuery(BaseModel):
    question: str
    question_hash: str
    question_embedding: List[float]  # 用于语义相似匹配
    datasource_luid: str
    schema_hash: str  # 数据模型版本，用于失效检测
    semantic_output: Dict[str, Any]
    query: str
    created_at: datetime
    expires_at: datetime
    hit_count: int  # 命中次数统计

def compute_schema_hash(data_model: DataModel) -> str:
    """
    计算数据模型的 schema hash
    
    只包含影响查询生成的字段属性：
    - field.name: 字段名
    - field.data_type: 数据类型
    - field.role: 字段角色 (DIMENSION/MEASURE)
    
    不包含：
    - field.description: 描述变更不影响查询
    - field.caption: 显示名变更不影响查询
    """
    import hashlib
    
    field_signatures = sorted([
        f"{f.name}:{f.data_type}:{f.role}"
        for f in data_model.fields
    ])
    content = "|".join(field_signatures)
    return hashlib.md5(content.encode()).hexdigest()

class QueryCache:
    def __init__(
        self,
        store: SqliteStore,
        embedding_model: Embeddings,
        default_ttl: int = 86400,  # 24 小时
    ):
        self._store = store
        self._embedding = embedding_model
        self._ttl = default_ttl
    
    def get(
        self, 
        question: str, 
        datasource_luid: str,
        current_schema_hash: str,  # 当前数据模型的 hash
    ) -> Optional[CachedQuery]:
        """精确匹配查询缓存
        
        1. 计算 question hash
        2. 从 store 中查找
        3. 检查 TTL 是否过期
        4. 检查 schema_hash 是否匹配当前数据模型
           → 不匹配则返回 None（视为缓存失效）
        """
        cached = self._store.get(self._make_key(question, datasource_luid))
        if cached is None:
            return None
        
        # TTL 检查
        if datetime.now() > cached.expires_at:
            return None
        
        # Schema hash 检查（核心失效机制）
        if cached.schema_hash != current_schema_hash:
            # 数据模型已变更，缓存失效
            return None
        
        # 更新命中计数
        cached.hit_count += 1
        self._store.put(self._make_key(question, datasource_luid), cached)
        
        return cached
    
    def get_similar(
        self, 
        question: str, 
        datasource_luid: str,
        current_schema_hash: str,
        threshold: float = 0.95
    ) -> Optional[CachedQuery]:
        """语义相似匹配
        
        1. 计算 question embedding
        2. 在该数据源的缓存中进行向量相似度搜索
        3. 返回相似度 > threshold 的最佳匹配
        4. 同样检查 schema_hash 是否匹配
        """
        pass
    
    def set(
        self,
        question: str,
        datasource_luid: str,
        schema_hash: str,
        semantic_output: Dict[str, Any],
        query: str,
        ttl: Optional[int] = None
    ) -> None:
        """设置缓存
        
        1. 计算 question hash 和 embedding
        2. 创建 CachedQuery 对象（包含当前 schema_hash）
        3. 存储到 store
        """
        pass
    
    def invalidate_by_datasource(self, datasource_luid: str) -> int:
        """失效指定数据源的所有缓存
        
        返回失效的缓存数量
        """
        pass
    
    def invalidate_by_schema_change(
        self, 
        datasource_luid: str, 
        new_schema_hash: str
    ) -> int:
        """当数据模型变更时，主动失效旧版本的缓存
        
        遍历该数据源的所有缓存，删除 schema_hash 不匹配的条目。
        
        注意：这是可选的主动清理，即使不调用，
        get() 方法也会在读取时检测并跳过失效缓存。
        """
        pass
```

**缓存命名空间**：

```python
# 缓存存储在 LangGraph SqliteStore 中
CACHE_NAMESPACE = ("semantic_parser", "query_cache")

# 按数据源分区
# namespace: ("semantic_parser", "query_cache", datasource_luid)
# key: question_hash
# value: CachedQuery.model_dump()
```

### 3. FieldRetriever

**职责**：Top-K 字段检索

```python
class FieldCandidate(BaseModel):
    field_name: str
    field_caption: str
    field_type: str  # dimension / measure
    data_type: str
    description: Optional[str]
    sample_values: Optional[List[str]]
    confidence: float

class FieldRetriever:
    def __init__(self, cascade_retriever: CascadeRetriever):
        self.retriever = cascade_retriever
    
    async def retrieve(
        self,
        question: str,
        data_model: DataModel,
        top_k: int = 10,
    ) -> List[FieldCandidate]:
        """检索 Top-K 相关字段"""
        pass
```

### 4. FewShotManager

**职责**：Few-shot 示例管理

```python
class FewShotExample(BaseModel):
    id: str
    question: str
    restated_question: str
    what: Dict[str, Any]
    where: Dict[str, Any]
    how: str
    computations: Optional[List[Dict]]
    query: str
    datasource_luid: str
    accepted_count: int  # 用户接受次数
    created_at: datetime
    updated_at: datetime

class FewShotManager:
    async def retrieve(
        self,
        question: str,
        datasource_luid: str,
        top_k: int = 3,
    ) -> List[FewShotExample]:
        """检索相关示例"""
        pass
    
    async def add(self, example: FewShotExample) -> None:
        """添加示例"""
        pass
    
    async def update_accepted_count(self, example_id: str) -> None:
        """更新接受次数"""
        pass
```

### 5. FilterValueValidator

**职责**：验证筛选值是否存在于字段中

**性能优化策略**：

为避免每次查询都进行昂贵的字段值验证，采用智能跳过机制：

```
验证决策流程:
┌─────────────────────────────────────────────────────────────────┐
│                    FilterValueValidator                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. 检查是否需要验证:                                            │
│     ├─ 时间类型字段 → 跳过（LLM 已处理时间表达式）               │
│     ├─ 数值范围筛选 → 跳过（无需验证具体值）                     │
│     ├─ 高基数字段（>10000 唯一值）→ 跳过（验证成本过高）         │
│     └─ 低基数字段（<1000 唯一值）→ 执行验证                      │
│                                                                  │
│  2. 缓存优先:                                                    │
│     ├─ 字段值已缓存 → 直接验证                                   │
│     └─ 未缓存 → 异步加载并缓存                                   │
│                                                                  │
│  3. 验证结果:                                                    │
│     ├─ 精确匹配 → 通过                                           │
│     ├─ 模糊匹配（相似度 > 0.8）→ 返回候选值供确认                │
│     └─ 无匹配 → 返回相似值供选择                                 │
└─────────────────────────────────────────────────────────────────┘
```

```python
class FilterValidationResult(BaseModel):
    """单个筛选条件的验证结果"""
    is_valid: bool
    field_name: str
    requested_value: str
    matched_values: List[str]  # 匹配到的值
    similar_values: List[str]  # 相似的候选值（用于澄清）
    validation_type: str  # exact_match / fuzzy_match / not_found / skipped / needs_confirmation
    skip_reason: Optional[str] = None  # 跳过验证的原因
    needs_confirmation: bool = False  # 是否需要用户确认（触发 LangGraph interrupt()）
    message: Optional[str] = None  # 给用户的提示信息

class FilterValidationSummary(BaseModel):
    """所有筛选条件的验证汇总"""
    results: List[FilterValidationResult]
    all_valid: bool  # 所有筛选条件都验证通过
    has_unresolvable_filters: bool  # 是否有无法解决的筛选条件（没有相似值可选）

class FilterValueValidator:
    """筛选值验证器
    
    在执行查询前验证筛选值是否存在于字段中，
    避免执行无效查询或返回空结果。
    
    性能优化：
    - 智能跳过：时间字段、数值范围、高基数字段不验证
    - 缓存优先：字段值缓存避免重复查询
    - 异步加载：后台预加载常用字段值
    """
    
    # 高基数阈值：超过此值的字段跳过验证
    HIGH_CARDINALITY_THRESHOLD = 10000
    
    # 需要跳过验证的字段类型
    SKIP_DATA_TYPES = {"date", "datetime", "timestamp"}
    
    def __init__(
        self,
        field_value_cache: FieldValueCache,
        similarity_threshold: float = 0.8,
    ):
        self._cache = field_value_cache
        self._threshold = similarity_threshold
    
    def should_validate(
        self,
        field: Field,
        filter_operator: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        判断是否需要验证该筛选条件
        
        Returns:
            (should_validate, skip_reason)
        """
        # 时间类型字段跳过
        if field.data_type.lower() in self.SKIP_DATA_TYPES:
            return False, "time_field"
        
        # 数值范围筛选跳过
        if filter_operator in ("BETWEEN", ">", "<", ">=", "<="):
            return False, "numeric_range"
        
        # 高基数字段跳过（如果有基数信息）
        if hasattr(field, 'cardinality') and field.cardinality > self.HIGH_CARDINALITY_THRESHOLD:
            return False, "high_cardinality"
        
        return True, None
    
    async def validate(
        self,
        filters: List[Filter],
        data_model: DataModel,
        datasource_luid: str,
    ) -> List[FilterValidationResult]:
        """
        验证所有筛选条件的值是否有效
        
        流程:
        1. 对于每个筛选条件，先判断是否需要验证
        2. 需要验证时，获取字段的所有可能值（从缓存或数据库）
        3. 检查筛选值是否存在:
           - 精确匹配: 直接存在 → is_valid=True
           - 模糊匹配: 相似度 > threshold → 返回候选值供确认
           - 不存在: 返回相似值供选择
        """
        results = []
        for f in filters:
            field = data_model.get_field(f.field_name)
            if not field:
                continue
            
            should_validate, skip_reason = self.should_validate(field, f.operator)
            if not should_validate:
                results.append(FilterValidationResult(
                    is_valid=True,
                    field_name=f.field_name,
                    requested_value=str(f.values),
                    matched_values=[],
                    similar_values=[],
                    validation_type="skipped",
                    skip_reason=skip_reason,
                ))
                continue
            
            # 执行实际验证...
            result = await self._validate_filter(f, field, datasource_luid)
            results.append(result)
        
        return results
    
    async def get_field_values(
        self,
        field_name: str,
        datasource_luid: str,
        limit: int = 1000,
    ) -> List[str]:
        """
        获取字段的所有可能值
        
        优先从缓存获取，缓存未命中则查询数据库
        """
        pass
    
    def find_similar_values(
        self,
        target: str,
        candidates: List[str],
        top_k: int = 5,
    ) -> List[str]:
        """
        查找相似的候选值
        
        使用编辑距离 + 拼音相似度
        """
        pass

class FieldValueCache:
    """字段值缓存
    
    缓存每个字段的可能值，避免重复查询数据库
    
    缓存策略:
    - 最大缓存条目数: 100 个字段 (LRU 淘汰)
    - 每个字段最多缓存: 1000 个值
    - TTL: 1 小时
    - 预热: 会话开始时加载低基数维度字段 (<500 唯一值)
    
    并发安全:
    - 使用分段锁（Sharded Lock）提升并发性能
    - 16 个分片，每个分片独立的 OrderedDict + Lock
    - 不同 key 的操作可以并行执行
    """
    
    MAX_FIELDS = 100  # 最多缓存 100 个字段
    MAX_VALUES_PER_FIELD = 1000  # 每个字段最多 1000 个值
    DEFAULT_TTL = 3600  # 1 小时
    PRELOAD_CARDINALITY_THRESHOLD = 500  # 预热阈值
    MAX_PRELOAD_FIELDS = 20  # 最多预加载字段数
    SHARD_COUNT = 16  # 分片数量
    
    def __init__(self):
        from collections import OrderedDict
        import asyncio
        # 分段锁：每个分片有独立的缓存和锁
        self._shards = [
            {
                "cache": OrderedDict(),
                "lock": asyncio.Lock(),
            }
            for _ in range(self.SHARD_COUNT)
        ]
    
    def _make_key(self, field_name: str, datasource_luid: str) -> str:
        """生成缓存 key"""
        return f"{datasource_luid}:{field_name}"
    
    def _get_shard(self, key: str) -> dict:
        """根据 key 获取对应的分片"""
        shard_idx = hash(key) % self.SHARD_COUNT
        return self._shards[shard_idx]
    
    def _get_total_size(self) -> int:
        """获取所有分片的总缓存条目数（用于 LRU 淘汰判断）"""
        return sum(len(shard["cache"]) for shard in self._shards)
    
    async def get(self, field_name: str, datasource_luid: str) -> Optional[List[str]]:
        """获取缓存的字段值（异步，线程安全）
        
        使用分段锁，不同 key 的读取可以并行执行。
        
        Returns:
            字段值列表，如果未缓存或已过期则返回 None
        """
        key = self._make_key(field_name, datasource_luid)
        shard = self._get_shard(key)
        
        async with shard["lock"]:
            cache = shard["cache"]
            if key not in cache:
                return None
            
            cached = cache[key]
            
            # TTL 检查
            if datetime.now() > cached.expires_at:
                del cache[key]
                return None
            
            # LRU: 移动到末尾（最近使用）
            cache.move_to_end(key)
            
            return cached.values
    
    async def set(
        self,
        field_name: str,
        datasource_luid: str,
        values: List[str],
        ttl: int = DEFAULT_TTL,
    ) -> None:
        """缓存字段值（异步，线程安全）
        
        使用分段锁，不同 key 的写入可以并行执行。
        LRU 淘汰在分片内部进行。
        
        自动处理:
        - 值列表截断（超过 MAX_VALUES_PER_FIELD）
        - LRU 淘汰（分片内超过 MAX_FIELDS/SHARD_COUNT）
        """
        key = self._make_key(field_name, datasource_luid)
        shard = self._get_shard(key)
        
        # 截断过长的值列表
        if len(values) > self.MAX_VALUES_PER_FIELD:
            values = values[:self.MAX_VALUES_PER_FIELD]
        
        # 每个分片的最大容量
        max_per_shard = self.MAX_FIELDS // self.SHARD_COUNT + 1
        
        async with shard["lock"]:
            cache = shard["cache"]
            
            # LRU 淘汰：删除该分片中最老的条目
            while len(cache) >= max_per_shard:
                cache.popitem(last=False)  # 删除最老的条目
            
            cache[key] = CachedFieldValues(
                values=values,
                expires_at=datetime.now() + timedelta(seconds=ttl),
                cached_at=datetime.now(),
            )
    
    async def preload_common_fields(
        self,
        data_model: DataModel,
        datasource_luid: str,
        platform_client: Any,
    ) -> None:
        """
        预加载常用字段值（低基数维度字段）
        
        在会话开始时异步调用，提升后续验证性能。
        
        预热策略:
        - 只加载维度字段（DIMENSION role）
        - 只加载低基数字段（<500 唯一值）
        - 排除时间类型字段
        - 最多预加载 20 个字段
        """
        # 筛选候选字段
        candidates = [
            f for f in data_model.fields
            if f.role == "DIMENSION"
            and f.data_type.lower() not in ("date", "datetime", "timestamp")
            and (not hasattr(f, 'cardinality') or f.cardinality < self.PRELOAD_CARDINALITY_THRESHOLD)
        ][:self.MAX_PRELOAD_FIELDS]
        
        # 并发加载
        import asyncio
        tasks = [
            self._load_field_values(f.name, datasource_luid, platform_client)
            for f in candidates
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _load_field_values(
        self,
        field_name: str,
        datasource_luid: str,
        platform_client: Any,
    ) -> None:
        """加载单个字段的值"""
        try:
            values = await platform_client.get_field_distinct_values(
                datasource_luid, field_name, limit=self.MAX_VALUES_PER_FIELD
            )
            await self.set(field_name, datasource_luid, values)
        except Exception as e:
            # 预加载失败不影响主流程
            logger.warning(f"Failed to preload field values for {field_name}: {e}")
    
    async def clear(self, datasource_luid: Optional[str] = None) -> int:
        """清除缓存（异步，线程安全）
        
        需要获取所有分片的锁，性能较低，仅用于管理操作。
        
        Args:
            datasource_luid: 如果指定，只清除该数据源的缓存
        
        Returns:
            清除的条目数
        """
        total_cleared = 0
        
        for shard in self._shards:
            async with shard["lock"]:
                cache = shard["cache"]
                if datasource_luid is None:
                    total_cleared += len(cache)
                    cache.clear()
                else:
                    keys_to_delete = [
                        k for k in cache.keys()
                        if k.startswith(f"{datasource_luid}:")
                    ]
                    for k in keys_to_delete:
                        del cache[k]
                    total_cleared += len(keys_to_delete)
        
        return total_cleared

class CachedFieldValues(BaseModel):
    """缓存的字段值"""
    values: List[str]
    expires_at: datetime
    cached_at: datetime
```

### 6. SemanticUnderstanding

**职责**：LLM 语义理解核心组件

```python
class SemanticOutput(BaseModel):
    restated_question: str
    what: What  # 度量列表
    where: Where  # 维度、过滤条件
    how_type: HowType  # SIMPLE / COMPLEX
    computations: List[Computation]  # 派生度量计算逻辑
    needs_clarification: bool
    clarification_question: Optional[str]
    clarification_options: Optional[List[str]]
    self_check: SelfCheck

class SelfCheck(BaseModel):
    field_mapping_confidence: float
    time_range_confidence: float
    computation_confidence: float
    overall_confidence: float
    potential_issues: List[str]

class SemanticUnderstanding:
    async def understand(
        self,
        question: str,
        history: List[Dict[str, str]],
        field_candidates: List[FieldCandidate],
        few_shot_examples: List[FewShotExample],
        config: SemanticConfig,
        error_feedback: Optional[str] = None,
    ) -> Tuple[SemanticOutput, str]:
        """执行语义理解，返回 (输出, thinking)"""
        pass
```

### 7. QueryAdapter

**职责**：将中间层 SemanticOutput 转换为目标查询语言

```python
from abc import ABC, abstractmethod

class QueryAdapter(ABC):
    """查询适配器基类"""
    
    @abstractmethod
    def adapt(
        self,
        semantic_output: SemanticOutput,
        data_model: DataModel,
    ) -> str:
        """将 SemanticOutput 转换为目标查询语句"""
        pass
    
    @abstractmethod
    def validate(self, query: str) -> Tuple[bool, Optional[str]]:
        """验证生成的查询语法"""
        pass

class VizQLAdapter(QueryAdapter):
    """VizQL 适配器 - 生成 Tableau VizQL"""
    
    def adapt(
        self,
        semantic_output: SemanticOutput,
        data_model: DataModel,
    ) -> str:
        """
        转换逻辑:
        1. 映射 what.measures → VizQL 度量字段
        2. 映射 where.dimensions → VizQL 维度字段
        3. 映射 where.filters → VizQL 过滤条件
        4. 处理 computations → VizQL 计算字段
           - RATIO → 除法表达式
           - GROWTH → (当前-上期)/上期
           - LOD → FIXED/INCLUDE/EXCLUDE 表达式
           - TABLE_CALC → 表计算函数
        """
        pass
    
    def validate(self, query: str) -> Tuple[bool, Optional[str]]:
        """验证 VizQL 语法"""
        pass

class SQLAdapter(QueryAdapter):
    """SQL 适配器 - 生成标准 SQL (可扩展)"""
    
    def adapt(
        self,
        semantic_output: SemanticOutput,
        data_model: DataModel,
    ) -> str:
        """转换为标准 SQL"""
        pass
    
    def validate(self, query: str) -> Tuple[bool, Optional[str]]:
        """验证 SQL 语法"""
        pass
```

### 8. DynamicPromptBuilder

**职责**：根据查询复杂度动态生成 Prompt

```python
class PromptComplexity(str, Enum):
    SIMPLE = "simple"    # 简单查询
    COMPLEX = "complex"  # 复杂查询

class DynamicPromptBuilder:
    """动态 Prompt 构建器"""
    
    def __init__(
        self,
        simple_template: str,
        complex_template: str,
        few_shot_manager: FewShotManager,
    ):
        self._simple_template = simple_template
        self._complex_template = complex_template
        self._few_shot_manager = few_shot_manager
    
    def build(
        self,
        question: str,
        history: List[Dict[str, str]],
        field_candidates: List[FieldCandidate],
        few_shot_examples: List[FewShotExample],
        config: SemanticConfig,
        complexity_hint: Optional[PromptComplexity] = None,
    ) -> str:
        """
        动态构建 Prompt:
        
        1. 判断查询复杂度:
           - 如果问题包含派生度量关键词 (利润率、增长率、占比) → COMPLEX
           - 如果问题包含 LOD 关键词 (每个、各自、独立) → COMPLEX
           - 如果问题包含表计算关键词 (排名、同比、环比) → COMPLEX
           - 否则 → SIMPLE
        
        2. 选择模板:
           - SIMPLE: 使用精简模板，减少 token
           - COMPLEX: 使用完整模板，包含计算示例
        
        3. 动态选择 Few-shot 示例:
           - 根据问题类型选择相关示例
           - 复杂查询优先选择包含计算的示例
        
        4. 裁剪字段列表:
           - 根据 MAX_SCHEMA_TOKENS 限制
           - 优先保留高置信度字段
        """
        pass
    
    def _detect_complexity(self, question: str) -> PromptComplexity:
        """检测查询复杂度"""
        complex_keywords = [
            # 派生度量
            "率", "比", "占比", "百分比", "比例",
            # 时间计算
            "同比", "环比", "增长", "下降", "变化",
            # LOD
            "每个", "各自", "独立", "不考虑",
            # 表计算
            "排名", "排序", "累计", "移动平均",
        ]
        for keyword in complex_keywords:
            if keyword in question:
                return PromptComplexity.COMPLEX
        return PromptComplexity.SIMPLE
```

### 9. ErrorCorrector

**职责**：执行后错误修正

**防止无限循环机制**：

```
错误修正决策流程:
┌─────────────────────────────────────────────────────────────────┐
│                      ErrorCorrector                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. 重复检测:                                                    │
│     ├─ 记录每次重试的 (error_type, error_message_hash)          │
│     ├─ 如果相同错误出现 2 次 → 立即终止，避免无效重试            │
│     └─ 不同错误 → 继续重试                                       │
│                                                                  │
│  2. 重试次数限制:                                                │
│     ├─ 最多 3 次重试                                             │
│     └─ 达到上限 → 返回详细错误信息和修正建议                     │
│                                                                  │
│  3. 错误分类处理:                                                │
│     ├─ 字段不存在 → 提供字段列表，建议正确字段                   │
│     ├─ 语法错误 → 提供语法示例                                   │
│     ├─ 筛选值无效 → 触发 FilterValueValidator 澄清               │
│     └─ 超时/服务错误 → 直接返回，不重试                          │
└─────────────────────────────────────────────────────────────────┘
```

```python
class ErrorCorrectionHistory(BaseModel):
    """错误修正历史记录"""
    error_type: str
    error_hash: str  # error_message 的 hash，用于重复检测
    attempt_number: int
    correction_applied: str
    timestamp: datetime

class ErrorCorrector:
    """错误修正器
    
    基于执行错误反馈，让 LLM 修正语义理解输出。
    
    防止无限循环:
    - 相同错误检测：如果相同错误出现 2 次，立即终止
    - 最大重试次数：硬性限制 3 次
    - 总错误历史检查：防止交替错误（A→B→A→B）绕过检测
    - 错误分类：某些错误类型不适合重试
    """
    
    MAX_RETRIES = 3
    MAX_SAME_ERROR_COUNT = 2
    
    # 不适合重试的错误类型
    NON_RETRYABLE_ERRORS = {
        "timeout",
        "service_unavailable", 
        "authentication_error",
        "rate_limit_exceeded",
    }
    
    def __init__(self):
        self._error_history: List[ErrorCorrectionHistory] = []
    
    def _compute_error_hash(self, error_info: str) -> str:
        """计算错误信息的 hash，用于重复检测"""
        import hashlib
        # 提取错误的核心部分（去除时间戳等变化内容）
        normalized = self._normalize_error_message(error_info)
        return hashlib.md5(normalized.encode()).hexdigest()[:16]
    
    def _normalize_error_message(self, error_info: str) -> str:
        """标准化错误信息，去除变化部分"""
        import re
        # 去除时间戳
        normalized = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', '', error_info)
        # 去除具体数值
        normalized = re.sub(r'\b\d+\b', 'N', normalized)
        return normalized.strip()
    
    def should_retry(
        self,
        error_info: str,
        error_type: str,
        retry_count: int,
    ) -> Tuple[bool, Optional[str]]:
        """
        判断是否应该重试
        
        防止交替错误绕过检测：
        - 除了检查单个错误的重复次数，还检查错误历史总长度
        - 即使 A→B→A→B 模式，总历史长度也会达到上限
        
        Returns:
            (should_retry, abort_reason)
        """
        # 检查是否为不可重试的错误类型
        if error_type in self.NON_RETRYABLE_ERRORS:
            return False, f"non_retryable_error: {error_type}"
        
        # 检查重试次数（传入的 retry_count）
        if retry_count >= self.MAX_RETRIES:
            return False, "max_retries_exceeded"
        
        # 检查错误历史总长度（防止交替错误绕过）
        # 例如：A→B→A→B 模式，每个错误只出现 2 次，但总共 4 次
        if len(self._error_history) >= self.MAX_RETRIES:
            return False, "total_error_history_exceeded"
        
        # 检查是否为重复错误
        error_hash = self._compute_error_hash(error_info)
        same_error_count = sum(
            1 for h in self._error_history 
            if h.error_hash == error_hash
        )
        if same_error_count >= self.MAX_SAME_ERROR_COUNT:
            return False, "duplicate_error_detected"
        
        return True, None
    
    async def correct(
        self,
        question: str,
        previous_output: SemanticOutput,
        error_info: str,
        error_type: str,
        retry_count: int,
        config: Optional[RunnableConfig] = None,
    ) -> Tuple[Optional[SemanticOutput], str, bool]:
        """
        基于错误反馈修正
        
        Returns:
            (corrected_output, thinking, should_continue)
            - corrected_output: 修正后的输出，如果终止则为 None
            - thinking: LLM 的思考过程
            - should_continue: 是否应该继续执行
        """
        # 检查是否应该重试
        should_retry, abort_reason = self.should_retry(
            error_info, error_type, retry_count
        )
        
        if not should_retry:
            return None, f"Correction aborted: {abort_reason}", False
        
        # 记录本次错误
        error_hash = self._compute_error_hash(error_info)
        self._error_history.append(ErrorCorrectionHistory(
            error_type=error_type,
            error_hash=error_hash,
            attempt_number=retry_count + 1,
            correction_applied="",  # 稍后更新
            timestamp=datetime.now(),
        ))
        
        # 调用 LLM 进行修正
        corrected_output, thinking = await self._llm_correct(
            question, previous_output, error_info, config
        )
        
        # 更新修正记录
        self._error_history[-1].correction_applied = thinking[:100]
        
        return corrected_output, thinking, True
    
    def reset_history(self) -> None:
        """重置错误历史（新查询时调用）"""
        self._error_history.clear()
    
    async def _llm_correct(
        self,
        question: str,
        previous_output: SemanticOutput,
        error_info: str,
        config: Optional[RunnableConfig] = None,
    ) -> Tuple[SemanticOutput, str]:
        """调用 LLM 进行修正"""
        pass
```

### 10. FeedbackLearner

**职责**：用户反馈学习

```python
class FeedbackType(str, Enum):
    ACCEPT = "accept"
    MODIFY = "modify"
    REJECT = "reject"

class FeedbackRecord(BaseModel):
    id: str
    question: str
    query: str
    feedback_type: FeedbackType
    modification: Optional[Dict[str, Any]]  # 修改内容
    rejection_reason: Optional[str]
    user_id: Optional[str]
    created_at: datetime

class FeedbackLearner:
    async def record(self, feedback: FeedbackRecord) -> None:
        """记录反馈"""
        pass
    
    async def learn_synonym(
        self,
        original_term: str,
        correct_field: str,
        datasource_luid: str,
    ) -> None:
        """学习同义词映射"""
        pass
    
    async def promote_to_example(self, feedback_id: str) -> None:
        """将接受的查询提升为 Few-shot 示例"""
        pass
```

## Data Models

### SemanticParserState

```python
class FilterConfirmation(BaseModel):
    """筛选值确认记录
    
    用于累积多轮筛选值确认的结果，防止上下文丢失。
    """
    field_name: str
    original_value: str
    confirmed_value: str
    confirmed_at: datetime

class SemanticParserState(TypedDict, total=False):
    # ========== 输入字段 ==========
    question: str
    chat_history: Optional[List[Dict[str, Any]]]
    datasource_luid: Optional[str]
    current_time: Optional[str]
    
    # ========== 组件输出 ==========
    intent_router_output: Optional[Dict[str, Any]]
    cache_hit: Optional[bool]
    field_candidates: Optional[List[Dict[str, Any]]]
    few_shot_examples: Optional[List[Dict[str, Any]]]
    semantic_output: Optional[Dict[str, Any]]
    
    # ========== 筛选值确认（多轮累积）==========
    # 用于累积多轮 interrupt() 确认的结果
    # 例如：第一次确认 "北京" → "北京市"，第二次确认 "上海" → "上海市"
    # 两次确认都会保留在此列表中，不会丢失
    confirmed_filters: Optional[List[Dict[str, Any]]]  # List[FilterConfirmation]
    
    # ========== 流程控制 ==========
    needs_clarification: Optional[bool]
    clarification_question: Optional[str]
    clarification_options: Optional[List[str]]
    
    # ========== 错误处理 ==========
    retry_count: Optional[int]
    error_feedback: Optional[str]
    pipeline_error: Optional[Dict[str, Any]]
    
    # ========== 最终输出 ==========
    semantic_query: Optional[Dict[str, Any]]
    parse_result: Optional[Dict[str, Any]]
    
    # ========== 思考过程 ==========
    thinking: Optional[str]
```

### SemanticOutput Schema

```python
class What(BaseModel):
    """目标度量"""
    measures: List[MeasureField] = Field(
        default_factory=list,
        description="<what>基础度量列表</what>"
    )

class Where(BaseModel):
    """维度和筛选器"""
    dimensions: List[DimensionField] = Field(
        default_factory=list,
        description="<what>分组字段</what>"
    )
    filters: List[FilterUnion] = Field(
        default_factory=list,
        description="<what>值约束</what>"
    )

class Computation(BaseModel):
    """派生度量计算"""
    name: str = Field(description="计算名称，如 profit_rate")
    display_name: str = Field(description="显示名称，如 利润率")
    formula: str = Field(description="计算公式，如 [利润]/[销售额]")
    calc_type: CalcType = Field(description="计算类型：RATIO/GROWTH/SHARE/LOD/TABLE_CALC")
    base_measures: List[str] = Field(description="基础度量列表")

class SemanticOutput(BaseModel):
    """LLM 语义理解输出
    
    包含查询追踪字段，用于调试和错误修正历史追踪。
    """
    # ========== 追踪字段 ==========
    query_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="查询唯一标识，用于追踪和调试"
    )
    parent_query_id: Optional[str] = Field(
        default=None,
        description="如果是错误修正，指向原查询的 query_id"
    )
    
    # ========== 核心输出字段 ==========
    restated_question: str = Field(
        description="<what>完整独立的问题描述</what>"
    )
    what: What
    where: Where
    how_type: HowType = Field(
        default=HowType.SIMPLE,
        description="<what>计算复杂度</what>"
    )
    computations: List[Computation] = Field(
        default_factory=list,
        description="<what>派生度量计算逻辑</what>"
    )
    needs_clarification: bool = Field(
        default=False,
        description="<what>是否需要澄清</what>"
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="<when>needs_clarification=True</when>"
    )
    clarification_options: Optional[List[str]] = Field(
        default=None,
        description="<what>澄清选项</what>"
    )
    self_check: SelfCheck = Field(
        description="<what>自检结果</what>"
    )
    
    # ========== 调试字段（可选）==========
    parsing_warnings: List[str] = Field(
        default_factory=list,
        description="解析过程中的警告信息，用于调试"
    )
```



## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*


Based on the prework analysis, the following properties have been identified:

### Property 1: Intent Classification Coverage

*For any* user question, the IntentRouter SHALL classify it into exactly one of the defined intent types (DATA_QUERY, CLARIFICATION, GENERAL, IRRELEVANT) with a confidence score between 0 and 1.

**Validates: Requirements 1.2**

### Property 2: Cache Round-Trip Consistency

*For any* successfully executed query, caching then retrieving with the same question SHALL return an equivalent query result.

**Validates: Requirements 2.1, 2.2**

### Property 3: Cache Invalidation on Model Change

*For any* cached query associated with a datasource, changing the datasource's data model SHALL invalidate all related cache entries.

**Validates: Requirements 2.5**

### Property 4: Top-K Retrieval Threshold

*For any* data model with field count exceeding the threshold, the FieldRetriever SHALL return at most K candidates (where K is configurable).

**Validates: Requirements 3.2**

### Property 5: Exact Match Priority

*For any* field retrieval, exact matches SHALL have higher confidence scores than semantic matches for the same field.

**Validates: Requirements 3.5**

### Property 6: Restated Question Completeness

*For any* semantic understanding output, the restated_question SHALL contain all information necessary to understand the query without referring to conversation history.

**Validates: Requirements 4.7**

### Property 7: Clarification Detection

*For any* incomplete user question (missing required information like measure or time range), the output SHALL have needs_clarification=true and a non-empty clarification_question.

**Validates: Requirements 5.1 (Req 6)**

### Property 8: State Completeness

*For any* semantic understanding output, all required fields (restated_question, what, where, how_type, self_check) SHALL be present and valid.

**Validates: Requirements 5.2 (Req 6)**

### Property 9: Incremental State Update

*For any* multi-turn conversation, providing new information SHALL merge with existing state without losing previously confirmed information.

**Validates: Requirements 5.5 (Req 6)**

### Property 10: Few-Shot Example Count

*For any* query generation, the number of retrieved few-shot examples SHALL be between 0 and 3 (inclusive).

**Validates: Requirements 6.2 (Req 7)**

### Property 11: Accepted Example Priority

*For any* few-shot retrieval with both accepted and non-accepted examples of similar relevance, accepted examples SHALL rank higher.

**Validates: Requirements 6.3 (Req 7)**

### Property 12: Self-Check Presence

*For any* semantic understanding output, the self_check field SHALL be present with all confidence scores between 0 and 1.

**Validates: Requirements 7.1 (Req 8)**

### Property 13: Low Confidence Flagging

*For any* semantic output where any confidence score is below the threshold (0.7), the potential_issues list SHALL be non-empty.

**Validates: Requirements 7.5 (Req 8)**

### Property 14: Retry Limit Enforcement

*For any* query execution with repeated failures, the retry count SHALL not exceed 3.

**Validates: Requirements 8.2 (Req 9)**

### Property 15: Feedback to Example Promotion

*For any* accepted query feedback, the query SHALL be added to the few-shot example candidate pool.

**Validates: Requirements 9.4 (Req 10)**

### Property 16: Synonym Learning Threshold

*For any* field mapping confirmed by 3 or more users, the mapping SHALL be automatically added to the synonym table.

**Validates: Requirements 9.6 (Req 10)**

### Property 17: History Truncation

*For any* conversation history exceeding MAX_HISTORY_TOKENS, the truncated history SHALL preserve the most recent messages.

**Validates: Requirements 12.4 (Req 12)**

### Property 18: Streaming Output Validity

*For any* completed streaming output, the final result SHALL be a valid Pydantic object that passes schema validation.

**Validates: Requirements 13.4 (Req 13)**

### Property 19: Derived Metric Decomposition

*For any* user question containing a derived metric (e.g., "利润率"), the output SHALL include a computation with the correct formula decomposition (e.g., 利润/销售额).

**Validates: Requirements 5.1 (Req 5)**

### Property 20: Computation Pattern Recognition

*For any* derived metric matching a known pattern (RATIO, GROWTH, SHARE), the computation's calc_type SHALL correctly identify the pattern.

**Validates: Requirements 5.2 (Req 5)**

### Property 21: Context Data Model Caching

*For any* session with multiple queries to the same datasource, the data model SHALL be loaded only once and reused from WorkflowContext.

**Validates: Requirements 14.3 (Req 14)**

### Property 22: Context State Persistence

*For any* multi-turn conversation within a session, the WorkflowContext state (including field_values_cache, field_samples) SHALL persist across turns.

**Validates: Requirements 14.3 (Req 14)**

### Property 23: Filter Validation Before Execution

*For any* query with filter conditions, all filter values SHALL be validated before query execution (except for skipped fields like time fields and high-cardinality fields).

**Validates: Requirements 4.3 (Req 4)**

### Property 24: Clarification Source Tracking

*For any* clarification request, the response SHALL include a source identifier indicating whether it originated from SemanticUnderstanding or FilterValueValidator.

**Validates: Requirements 6.1 (Req 6)**

### Property 25: Prompt Complexity Adaptation

*For any* user question containing derived metric keywords (率, 比, 同比, 环比, 排名, etc.), the DynamicPromptBuilder SHALL select the COMPLEX template.

**Validates: Requirements 12.1 (Req 12)**

### Property 26: Time Expression Context

*For any* prompt built by DynamicPromptBuilder, the context section SHALL include current_date, timezone, and fiscal_year_start_month.

**Validates: Requirements 11.1, 11.2, 11.3 (Req 11)**

### Property 27: Schema Hash Consistency

*For any* data model field change (add/remove/type change), the computed schema_hash SHALL differ from the previous hash.

**Validates: Requirements 2.5 (Req 2)**

### Property 28: Hierarchy Enrichment

*For any* dimension field with inferred hierarchy, the field metadata SHALL include drill-down options (category, level, granularity).

**Validates: Requirements 3.4 (Req 3)**

### Property 29: Filter Validation Skip for Time Fields

*For any* filter condition on a time-type field (date, datetime, timestamp), the FilterValueValidator SHALL skip validation and return is_valid=True with skip_reason="time_field".

**Validates: Requirements 4.6 (Req 4)**

### Property 30: Duplicate Error Detection

*For any* error correction attempt, if the same error (by error_hash) appears 2 or more times in error_history, the ErrorCorrector SHALL abort with reason "duplicate_error_detected".

**Validates: Requirements 9.2 (Req 9)**

### Property 30.1: Alternating Error Detection

*For any* error correction sequence, if the total error_history length reaches MAX_RETRIES (3), the ErrorCorrector SHALL abort with reason "total_error_history_exceeded", preventing alternating error patterns (A→B→A→B) from bypassing duplicate detection.

**Validates: Requirements 9.2 (Req 9)**

### Property 31: Non-Retryable Error Handling

*For any* error with type in NON_RETRYABLE_ERRORS (timeout, service_unavailable, authentication_error, rate_limit_exceeded), the ErrorCorrector SHALL immediately abort without retry.

**Validates: Requirements 9.2 (Req 9)**

### Property 32: Cache Schema Validation on Read

*For any* cache read operation, if the cached entry's schema_hash does not match the current data model's schema_hash, the QueryCache SHALL return None (cache miss).

**Validates: Requirements 2.5 (Req 2)**

### Property 33: Time Hint Generation

*For any* user question containing a recognized time expression (今天, 上个月, 最近N天, 本财年, etc.), the TimeHintGenerator SHALL produce a hint with correct start_date and end_date based on current_date and fiscal_year_start_month.

**Validates: Requirements 11.4 (Req 11)**

### Property 34: Filter Confirmation via LangGraph interrupt()

*For any* filter validation result where needs_confirmation=True AND similar_values is non-empty, the filter_validator_node SHALL call LangGraph interrupt() to pause execution and await user confirmation.

**Validates: Requirements 6.4 (Req 6)**

### Property 35: Filter Value Update After Confirmation

*For any* user confirmation of a filter value, the FilterValueValidator SHALL update the corresponding filter in semantic_output.where.filters with the confirmed value.

**Validates: Requirements 6.5 (Req 6)**

### Property 36: Field Value Cache LRU Eviction

*For any* FieldValueCache shard reaching its capacity limit (MAX_FIELDS/SHARD_COUNT), the oldest (least recently used) entry SHALL be evicted before adding a new entry.

**Validates: Requirements 3.6 (Req 3)**

### Property 36.1: Field Value Cache Sharded Lock Concurrency

*For any* concurrent operations on FieldValueCache with different keys mapping to different shards, the operations SHALL execute in parallel without blocking each other.

**Validates: Requirements 3.6 (Req 3)**

### Property 37: Field Value Cache Preload Threshold

*For any* preload_common_fields() call, only dimension fields with cardinality < PRELOAD_CARDINALITY_THRESHOLD (500) and non-time data types SHALL be preloaded.

**Validates: Requirements 3.4 (Req 3)**

### Property 38: Unresolvable Filter Detection

*For any* filter validation where the requested value has no exact match AND no similar values (empty similar_values list), the result SHALL have is_unresolvable=True and the FilterValidationSummary SHALL have has_unresolvable_filters=True.

**Validates: Requirements 6.1 (Req 6)**

### Property 39: Filter Validation interrupt() Condition

*For any* filter validation result, interrupt() SHALL be called if and only if needs_confirmation=True AND similar_values is non-empty. If is_unresolvable=True (no similar values), interrupt() SHALL NOT be called.

**Validates: Requirements 6.4 (Req 6)**

### Property 40: Multi-Round Filter Confirmation Accumulation

*For any* multi-round filter confirmation scenario, the confirmed_filters list in SemanticParserState SHALL accumulate all confirmations across rounds without losing previous confirmations.

**Validates: Requirements 6.5 (Req 6)**

### Property 41: QueryAdapter Syntax Validity

*For any* SemanticOutput passed to QueryAdapter.adapt(), the generated query string SHALL be syntactically valid for the target query language (VizQL or SQL).

**Validates: Requirements 14.2 (Req 14)**

## Error Handling

### Error Categories

1. **Intent Classification Errors**
   - 无法识别意图 → 降级为 DATA_QUERY，让 LLM 处理
   - 置信度过低 → 记录日志，继续处理

2. **Cache Errors**
   - 缓存服务不可用 → 降级为无缓存模式
   - 缓存数据损坏 → 清除损坏数据，重新生成

3. **Retrieval Errors**
   - 向量检索失败 → 降级为精确匹配
   - 无候选字段 → 返回完整字段列表（如果可行）

4. **LLM Errors**
   - JSON 解析失败 → 组件内重试（最多 3 次）
   - Pydantic 验证失败 → 组件内重试（最多 3 次）
   - 语义错误 → 执行后修正机制

5. **Execution Errors**
   - 查询执行失败 → 反馈错误给 LLM，重试（最多 3 次）
   - 超时 → 返回超时错误，建议简化查询

### Error Response Format

```python
class QueryError(BaseModel):
    type: QueryErrorType
    message: str
    step: str  # intent_router / cache / retrieval / understanding / execution
    can_retry: bool
    details: Optional[Dict[str, Any]]
    suggestions: Optional[List[str]]
```

## Testing Strategy

### Unit Tests

1. **IntentRouter Tests**
   - 各意图类型的识别准确性
   - 规则匹配覆盖
   - 边界情况处理

2. **QueryCache Tests**
   - 缓存命中/未命中
   - 语义相似匹配
   - 缓存失效机制

3. **FieldRetriever Tests**
   - Top-K 检索准确性
   - 精确匹配优先级
   - 大数据模型处理

4. **SemanticUnderstanding Tests**
   - 输出结构完整性
   - 派生度量分解
   - 自检机制

5. **FeedbackLearner Tests**
   - 反馈记录
   - 同义词学习
   - 示例提升

### Property-Based Tests

每个 Correctness Property 对应一个 property-based test，使用 Hypothesis 库：

```python
# Example: Property 2 - Cache Round-Trip Consistency
@given(
    question=st.text(min_size=5, max_size=200),
    query=st.builds(SemanticQuery, ...)
)
def test_cache_round_trip(question, query):
    """Feature: semantic-parser-refactor, Property 2: Cache Round-Trip Consistency"""
    cache = QueryCache()
    cache.set(question, "ds_123", query)
    result = cache.get(question, "ds_123")
    assert result is not None
    assert result.query == query
```

### Integration Tests

1. **End-to-End Flow**
   - 完整的语义解析流程
   - 多轮对话场景
   - 错误修正流程

2. **LangGraph Integration**
   - 子图集成测试
   - 状态传递测试
   - 条件路由测试

### Performance Tests

1. **Latency Benchmarks**
   - IntentRouter: < 50ms
   - FieldRetriever: < 100ms
   - 完整流程: < 3s

2. **Token Usage**
   - Prompt token 统计
   - 截断频率监控


## LangGraph 子图实现

### 子图结构定义

语义解析器作为 LangGraph StateGraph 子图实现，可以被主工作流调用：

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

def create_semantic_parser_graph() -> StateGraph:
    """创建语义解析器子图
    
    筛选值确认机制说明：
    - 不使用独立的 filter_confirmation 节点
    - 通过 ValidateFilterValueTool + LangGraph interrupt() 实现
    - 当 FilterValueValidator 发现值不匹配时，调用工具返回 needs_confirmation=True
    - filter_validator_node 调用 interrupt() 暂停执行等待用户确认
    - 用户确认后，通过 graph.update_state() 恢复执行
    """
    
    graph = StateGraph(SemanticParserState)
    
    # ========== 添加节点 ==========
    graph.add_node("intent_router", intent_router_node)
    graph.add_node("query_cache", query_cache_node)
    graph.add_node("field_retriever", field_retriever_node)
    graph.add_node("few_shot_manager", few_shot_manager_node)
    graph.add_node("semantic_understanding", semantic_understanding_node)
    graph.add_node("filter_validator", filter_validator_node)  # 内部调用 ValidateFilterValueTool
    graph.add_node("query_adapter", query_adapter_node)
    graph.add_node("error_corrector", error_corrector_node)
    graph.add_node("feedback_learner", feedback_learner_node)
    
    # ========== 设置入口点 ==========
    graph.set_entry_point("intent_router")
    
    # ========== 添加条件边 ==========
    
    # 意图路由后的分支
    graph.add_conditional_edges(
        "intent_router",
        route_by_intent,
        {
            "data_query": "query_cache",
            "general": END,       # 直接返回元数据信息
            "irrelevant": END,    # 直接返回礼貌拒绝
            "clarification": END, # 直接返回澄清请求
        }
    )
    
    # 缓存检查后的分支
    graph.add_conditional_edges(
        "query_cache",
        route_by_cache,
        {
            "cache_hit": "feedback_learner",  # 缓存命中，直接到反馈学习
            "cache_miss": "field_retriever"   # 缓存未命中，继续检索
        }
    )

    # 字段检索 → Few-shot 检索
    graph.add_edge("field_retriever", "few_shot_manager")
    
    # Few-shot 检索 → 语义理解
    graph.add_edge("few_shot_manager", "semantic_understanding")
    
    # 语义理解后的分支
    graph.add_conditional_edges(
        "semantic_understanding",
        route_after_understanding,
        {
            "needs_clarification": END,           # 需要澄清，返回给用户
            "continue": "filter_validator"        # 继续验证筛选值
        }
    )
    
    # 筛选值验证后的分支
    # 注意：当 needs_confirmation=True 且有相似值时，filter_validator_node 会调用 interrupt()
    # 用户确认后通过 graph.update_state() 恢复执行，此时 validation 结果已更新为 valid
    graph.add_conditional_edges(
        "filter_validator",
        route_after_validation,
        {
            "valid": "query_adapter",             # 验证通过（或用户已确认），生成查询
            "needs_clarification": END            # 需要用户提供更多信息（无相似值可选）
        }
    )
    
    # 查询适配后的分支
    graph.add_conditional_edges(
        "query_adapter",
        route_after_query,
        {
            "success": "feedback_learner",        # 执行成功
            "error": "error_corrector"            # 执行失败，进入修正
        }
    )
    
    # 错误修正后的分支
    graph.add_conditional_edges(
        "error_corrector",
        route_after_correction,
        {
            "retry": "query_adapter",             # 重试查询
            "max_retries": END                    # 达到最大重试次数
        }
    )
    
    # 反馈学习 → 结束
    graph.add_edge("feedback_learner", END)
    
    return graph

```

### 路由函数定义

```python
def route_by_intent(state: SemanticParserState) -> str:
    """根据意图类型路由"""
    intent = state.get("intent_router_output", {})
    intent_type = intent.get("intent_type", "data_query")
    return intent_type

def route_by_cache(state: SemanticParserState) -> str:
    """根据缓存命中情况路由"""
    if state.get("cache_hit"):
        return "cache_hit"
    return "cache_miss"

def route_after_understanding(state: SemanticParserState) -> str:
    """语义理解后的路由"""
    if state.get("needs_clarification"):
        return "needs_clarification"
    return "continue"

def route_after_validation(state: SemanticParserState) -> str:
    """筛选值验证后的路由
    
    注意：当 FilterValueValidator 发现 needs_confirmation=True 且有相似值时，
    filter_validator_node 会调用 interrupt() 暂停执行。
    用户确认后，通过 graph.update_state() 恢复执行，FilterValueValidator 更新 filters，
    然后继续执行到这里，此时 validation_result 已经是 valid。
    
    只有当完全无法匹配（没有相似值可选）时，才返回 needs_clarification。
    """
    validation_result = state.get("filter_validation_result", {})
    
    # 检查是否有无法处理的筛选值（没有相似值可选）
    if validation_result.get("has_unresolvable_filters"):
        return "needs_clarification"
    
    return "valid"

def route_after_query(state: SemanticParserState) -> str:
    """查询执行后的路由"""
    if state.get("pipeline_error"):
        return "error"
    return "success"

def route_after_correction(state: SemanticParserState) -> str:
    """错误修正后的路由
    
    检查:
    1. 是否达到最大重试次数
    2. 是否检测到重复错误
    3. 是否为不可重试的错误类型
    """
    # 检查是否应该终止
    abort_reason = state.get("correction_abort_reason")
    if abort_reason:
        return "max_retries"  # 包括重复错误、不可重试错误等情况
    
    retry_count = state.get("retry_count", 0)
    if retry_count >= 3:
        return "max_retries"
    return "retry"
```

### 子图编译与调用

```python
# 编译子图
semantic_parser = create_semantic_parser_graph().compile(
    checkpointer=SqliteSaver.from_conn_string("sqlite:///checkpoints.db")
)

# 调用子图
async def parse_question(
    question: str,
    context: SemanticParserContext,
    config: RunnableConfig,
) -> SemanticParserState:
    """调用语义解析器子图"""
    
    initial_state: SemanticParserState = {
        "question": question,
        "chat_history": context.chat_history,
        "datasource_luid": context.datasource_luid,
        "current_time": context.current_time,
        # 上下文中的数据模型（避免重复获取）
        "data_model": context.data_model,
        "dimension_hierarchies": context.dimension_hierarchies,
    }
    
    result = await semantic_parser.ainvoke(initial_state, config)
    return result
```


## 上下文状态管理

### 与现有 WorkflowContext 的关系

语义解析器的上下文管理基于现有的 `WorkflowContext` 架构（`tableau_assistant/src/orchestration/workflow/context.py`）。

现有 `WorkflowContext` 已包含：
- `auth`: Tableau 认证上下文
- `datasource_luid`: 数据源 LUID
- `data_model`: 完整的数据模型（由 DataModelCache 加载）
- `dimension_hierarchy`: 维度层级（从 data_model 中提取）

语义解析器通过 `RunnableConfig["configurable"]["workflow_context"]` 获取这些数据，**不需要重复加载**。

### 扩展 WorkflowContext

为支持语义解析器的需求，扩展 `WorkflowContext`：

```python
# 在 analytics_assistant/src/orchestration/workflow/context.py 中扩展

class WorkflowContext(BaseModel):
    """工作流上下文 - 统一的依赖容器"""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    # ========== 现有字段（保持不变）==========
    auth: TableauAuthContext
    datasource_luid: str
    tableau_domain: Optional[str] = None
    data_model: Optional[DataModel] = None
    max_replan_rounds: int = 3
    user_id: Optional[str] = None
    metadata_load_status: Optional[MetadataLoadStatus] = None
    
    # ========== 新增：语义解析器需要的字段 ==========
    
    # 时间配置
    current_time: Optional[str] = None  # ISO 格式，每次请求时设置
    timezone: str = "Asia/Shanghai"
    fiscal_year_start_month: int = 1  # 财年起始月份
    
    # 业务日历（可选）
    business_calendar: Optional[Dict[str, Any]] = None
    
    # 字段值缓存（用于筛选值验证）
    field_values_cache: Dict[str, List[str]] = Field(default_factory=dict)
    
    # 字段样例数据（用于 Prompt）
    field_samples: Optional[Dict[str, Dict[str, Any]]] = None
    
    @property
    def dimension_hierarchy(self) -> Optional[Dict[str, Any]]:
        """获取维度层级（从 data_model 中提取）"""
        if self.data_model is None:
            return None
        return self.data_model.dimension_hierarchy
    
    def get_field_values(self, field_name: str) -> Optional[List[str]]:
        """获取字段的缓存值"""
        return self.field_values_cache.get(field_name)
    
    def set_field_values(self, field_name: str, values: List[str]) -> None:
        """缓存字段值"""
        self.field_values_cache[field_name] = values
```

### 上下文初始化流程

上下文初始化由编排层（`WorkflowExecutor`）负责，语义解析器只负责使用：

```python
# 在 WorkflowExecutor 中初始化上下文

class WorkflowExecutor:
    """工作流执行器"""
    
    def __init__(
        self,
        data_loader: TableauDataLoader,
        hierarchy_inference: DimensionHierarchyInference,
    ):
        self._data_loader = data_loader
        self._hierarchy = hierarchy_inference
    
    async def create_context(
        self,
        auth: TableauAuthContext,
        datasource_luid: str,
        **kwargs,
    ) -> WorkflowContext:
        """创建工作流上下文
        
        1. 加载数据模型（使用 TableauDataLoader）
        2. 推断维度层级（使用 DimensionHierarchyInference）
        3. 获取字段样例数据（可选）
        """
        # 1. 加载数据模型
        data_model = await self._data_loader.load_data_model(
            datasource_id=datasource_luid,
            auth=auth,
        )
        
        # 2. 推断维度层级
        if data_model:
            await self._hierarchy.infer_and_enrich(
                data_model=data_model,
                datasource_luid=datasource_luid,
            )
        
        # 3. 获取字段样例数据（可选，用于 Prompt）
        field_samples = None
        if kwargs.get("load_field_samples", False):
            field_samples = await self._data_loader.fetch_field_samples(
                datasource_id=datasource_luid,
                fields=data_model.fields,
                measure_field=kwargs.get("sample_measure_field", ""),
                auth=auth,
            )
        
        return WorkflowContext(
            auth=auth,
            datasource_luid=datasource_luid,
            data_model=data_model,
            current_time=datetime.now().isoformat(),
            field_samples=field_samples,
            **kwargs,
        )
```

### 语义解析器获取上下文

语义解析器节点通过 `RunnableConfig` 获取上下文：

```python
# 在语义解析器节点中

async def semantic_understanding_node(
    state: SemanticParserState,
    config: RunnableConfig,
) -> Dict[str, Any]:
    """语义理解节点"""
    
    # 获取上下文
    ctx = get_context_or_raise(config)
    
    # 使用上下文中的数据（不需要重新加载）
    data_model = ctx.data_model
    dimension_hierarchy = ctx.dimension_hierarchy
    current_time = ctx.current_time
    timezone = ctx.timezone
    
    # 构建 Prompt 时使用字段信息
    field_candidates = state.get("field_candidates", [])
    
    # ... 执行语义理解 ...
```

### 对话历史管理

对话历史通过 LangGraph 的 checkpoint 机制管理，不需要在 `WorkflowContext` 中存储：

```python
# 对话历史通过 State 传递
class SemanticParserState(TypedDict, total=False):
    # 对话历史（由 LangGraph checkpoint 自动管理）
    chat_history: Optional[List[Dict[str, Any]]]
    
    # 压缩后的历史摘要（当历史过长时）
    summarized_history: Optional[str]

# 在节点中更新对话历史
async def update_history_node(
    state: SemanticParserState,
    config: RunnableConfig,
) -> Dict[str, Any]:
    """更新对话历史"""
    history = state.get("chat_history", [])
    
    # 添加新的对话
    history.append({"role": "user", "content": state["question"]})
    history.append({"role": "assistant", "content": state.get("response", "")})
    
    # 如果历史过长，触发摘要压缩
    if len(history) > 10:
        summarized = await summarize_history(history)
        return {
            "chat_history": history[-4:],  # 保留最近 2 轮
            "summarized_history": summarized,
        }
    
    return {"chat_history": history}
```
    
    # ========== 组件输出 ==========
    intent_router_output: Optional[Dict[str, Any]]
    cache_hit: Optional[bool]
    cached_query: Optional[Dict[str, Any]]
    field_candidates: Optional[List[Dict[str, Any]]]
    few_shot_examples: Optional[List[Dict[str, Any]]]
    semantic_output: Optional[Dict[str, Any]]
    filter_validation_result: Optional[Dict[str, Any]]  # 包含 has_unresolvable_filters 字段
    
    # ========== 流程控制 ==========
    needs_clarification: Optional[bool]
    clarification_question: Optional[str]
    clarification_options: Optional[List[str]]
    
    # ========== 错误处理 ==========
    retry_count: Optional[int]
    error_feedback: Optional[str]
    error_type: Optional[str]  # 错误类型分类
    error_history: Optional[List[Dict[str, Any]]]  # 错误修正历史
    correction_abort_reason: Optional[str]  # 终止修正的原因
    pipeline_error: Optional[Dict[str, Any]]
    
    # ========== 最终输出 ==========
    generated_query: Optional[str]
    query_type: Optional[str]  # vizql / sql
    execution_result: Optional[Dict[str, Any]]
    parse_result: Optional[Dict[str, Any]]
    
    # ========== 思考过程 ==========
    thinking: Optional[str]
```


## Prompt 模板

### 核心语义理解 Prompt

```xml
<system>
你是一个专业的数据分析助手，负责将用户的自然语言问题转换为结构化的数据查询。

你的任务是：
1. 理解用户的问题意图
2. 识别需要查询的度量（measures）和维度（dimensions）
3. 解析筛选条件和时间范围
4. 识别派生度量并分解为基础计算
5. 评估自己的理解置信度

请严格按照输出格式返回 JSON 结果。
</system>

<context>
<current_date>{current_date}</current_date>
<timezone>{timezone}</timezone>
<fiscal_year_start>{fiscal_year_start_month}月</fiscal_year_start>
</context>

<available_fields>
{field_list_xml}
</available_fields>

<few_shot_examples>
{examples}
</few_shot_examples>

<conversation_history>
{history}
</conversation_history>

<user_question>{question}</user_question>

<output_format>
请输出以下 JSON 格式的结构化结果：

```json
{
  "restated_question": "完整独立的问题描述，不依赖对话历史",
  "what": {
    "measures": [
      {"field_name": "字段名", "aggregation": "SUM/AVG/COUNT/..."}
    ]
  },
  "where": {
    "dimensions": [
      {"field_name": "字段名", "role": "group_by/detail"}
    ],
    "filters": [
      {"field_name": "字段名", "operator": "=/IN/BETWEEN/...", "values": [...]}
    ]
  },
  "how_type": "SIMPLE 或 COMPLEX",
  "computations": [
    {
      "name": "计算名称",
      "display_name": "显示名称",
      "formula": "计算公式",
      "calc_type": "RATIO/GROWTH/SHARE/LOD/TABLE_CALC",
      "base_measures": ["基础度量1", "基础度量2"]
    }
  ],
  "needs_clarification": false,
  "clarification_question": "如果需要澄清，这里是澄清问题",
  "clarification_options": ["选项1", "选项2"],
  "self_check": {
    "field_mapping_confidence": 0.9,
    "time_range_confidence": 0.95,
    "computation_confidence": 0.85,
    "overall_confidence": 0.9,
    "potential_issues": ["如果有潜在问题，列在这里"]
  }
}
```
</output_format>
```


### 字段列表 XML 格式

```xml
<fields>
  <dimensions>
    <field name="地区" caption="地区" data_type="string">
      <description>销售地区，包含省份和城市</description>
      <sample_values>北京, 上海, 广州, 深圳</sample_values>
      <hierarchy>地区 > 省份 > 城市</hierarchy>
    </field>
    <field name="日期" caption="订单日期" data_type="date">
      <description>订单创建日期</description>
      <hierarchy>年 > 季度 > 月 > 日</hierarchy>
    </field>
  </dimensions>
  
  <measures>
    <field name="销售额" caption="销售额" data_type="number">
      <description>订单销售金额</description>
      <aggregation>SUM</aggregation>
    </field>
    <field name="利润" caption="利润" data_type="number">
      <description>订单利润 = 销售额 - 成本</description>
      <aggregation>SUM</aggregation>
    </field>
  </measures>
</fields>
```

### Few-shot 示例格式

```xml
<example id="1">
  <question>上个月各地区的销售额是多少？</question>
  <output>
    {
      "restated_question": "查询上个月（2024年12月）各地区的销售额",
      "what": {"measures": [{"field_name": "销售额", "aggregation": "SUM"}]},
      "where": {
        "dimensions": [{"field_name": "地区", "role": "group_by"}],
        "filters": [{"field_name": "日期", "operator": "IN", "values": ["上个月"]}]
      },
      "how_type": "SIMPLE",
      "computations": [],
      "needs_clarification": false,
      "self_check": {"overall_confidence": 0.95, "potential_issues": []}
    }
  </output>
</example>

<example id="2">
  <question>各地区的利润率是多少？</question>
  <output>
    {
      "restated_question": "查询各地区的利润率（利润/销售额）",
      "what": {"measures": [
        {"field_name": "利润", "aggregation": "SUM"},
        {"field_name": "销售额", "aggregation": "SUM"}
      ]},
      "where": {
        "dimensions": [{"field_name": "地区", "role": "group_by"}],
        "filters": []
      },
      "how_type": "COMPLEX",
      "computations": [{
        "name": "profit_rate",
        "display_name": "利润率",
        "formula": "SUM([利润])/SUM([销售额])",
        "calc_type": "RATIO",
        "base_measures": ["利润", "销售额"]
      }],
      "needs_clarification": false,
      "self_check": {"overall_confidence": 0.9, "potential_issues": []}
    }
  </output>
</example>

<example id="3">
  <question>销售额同比增长率</question>
  <output>
    {
      "restated_question": "查询销售额的同比增长率（与去年同期相比）",
      "what": {"measures": [{"field_name": "销售额", "aggregation": "SUM"}]},
      "where": {"dimensions": [], "filters": []},
      "how_type": "COMPLEX",
      "computations": [{
        "name": "yoy_growth",
        "display_name": "销售额同比增长率",
        "formula": "(SUM([销售额]) - LOOKUP(SUM([销售额]), -1)) / LOOKUP(SUM([销售额]), -1)",
        "calc_type": "GROWTH",
        "base_measures": ["销售额"]
      }],
      "needs_clarification": true,
      "clarification_question": "请问您想看哪个时间维度的同比？",
      "clarification_options": ["按月同比", "按季度同比", "按年同比"],
      "self_check": {"overall_confidence": 0.7, "potential_issues": ["时间维度不明确"]}
    }
  </output>
</example>
```


### 简化版 Prompt（用于简单查询）

```xml
<system>
将用户问题转换为数据查询。输出 JSON 格式。
</system>

<context>
日期: {current_date} | 时区: {timezone}
</context>

<fields>
度量: {measures_list}
维度: {dimensions_list}
</fields>

<question>{question}</question>

<format>
{"restated_question": "", "what": {"measures": []}, "where": {"dimensions": [], "filters": []}, "self_check": {"overall_confidence": 0.0}}
</format>
```

### 错误修正 Prompt

```xml
<system>
之前的查询执行失败，请根据错误信息修正。
</system>

<original_question>{question}</original_question>

<previous_output>
{previous_semantic_output}
</previous_output>

<error_info>
{error_message}
</error_info>

<available_fields>
{field_list_xml}
</available_fields>

<instructions>
请分析错误原因，修正输出。常见错误：
1. 字段名不存在 → 检查字段列表，使用正确的字段名
2. 筛选值无效 → 检查字段的有效值范围
3. 计算公式错误 → 检查公式语法和字段引用
4. 时间范围解析错误 → 重新解析时间表达式

输出修正后的完整 JSON。
</instructions>
```


## 基础设施集成

### 复用现有组件

语义解析器复用项目中已有的基础设施组件：

```python
# 1. CascadeRetriever - 向量检索
from analytics_assistant.src.infra.rag.cascade_retriever import CascadeRetriever

# 用于字段检索和 Few-shot 示例检索
field_retriever = FieldRetriever(
    cascade_retriever=CascadeRetriever(
        embedding_model=embedding_model,
        vector_store=vector_store,
    )
)

# 2. CacheManager - 缓存管理
from analytics_assistant.src.infra.storage.cache_manager import CacheManager

# 用于查询缓存和字段值缓存
query_cache = QueryCache(
    cache_manager=CacheManager(store=sqlite_store),
    embedding_model=embedding_model,
)

# 3. ModelManager - LLM 调用管理
from analytics_assistant.src.infra.ai.model_manager import ModelManager

# 用于语义理解和错误修正
model_manager = ModelManager(config=ai_config)

# 4. stream_llm_structured - 流式结构化输出
from analytics_assistant.src.infra.ai.streaming import stream_llm_structured

# 用于流式输出语义理解结果
async for chunk in stream_llm_structured(
    model=model_manager.get_model("deepseek"),
    prompt=prompt,
    output_schema=SemanticOutput,
):
    yield chunk

# 5. DimensionHierarchyInference - 维度层级推断
from analytics_assistant.src.agents.dimension_hierarchy import DimensionHierarchyInference

# 用于获取维度层级关系
hierarchy_inference = DimensionHierarchyInference(
    model_manager=model_manager,
    cache_manager=cache_manager,
)
```

### 组件依赖关系

```
SemanticParser
├── IntentRouter
│   └── (规则匹配，可选 LLM)
├── QueryCache
│   ├── CacheManager (复用)
│   └── EmbeddingModel (复用)
├── FieldRetriever
│   └── CascadeRetriever (复用)
├── FewShotManager
│   └── CascadeRetriever (复用)
├── SemanticUnderstanding
│   ├── ModelManager (复用)
│   ├── DynamicPromptBuilder
│   └── stream_llm_structured (复用)
├── FilterValueValidator
│   ├── FieldValueCache
│   └── PlatformClient (复用)
├── QueryAdapter
│   └── VizQLAdapter / SQLAdapter
├── ErrorCorrector
│   └── ModelManager (复用)
└── FeedbackLearner
    └── CacheManager (复用)
```


### 配置集成

```python
# 语义解析器配置（集成到 app.yaml）
semantic_parser:
  # 意图路由配置
  intent_router:
    use_llm: false  # 是否使用 LLM 进行意图分类
    timeout_ms: 50
  
  # 缓存配置
  cache:
    enabled: true
    ttl_seconds: 86400  # 24 小时
    similarity_threshold: 0.95
  
  # 字段检索配置
  field_retriever:
    top_k: 10
    timeout_ms: 100
    use_exact_match: true
  
  # Few-shot 配置
  few_shot:
    max_examples: 3
    prefer_accepted: true
  
  # LLM 配置
  llm:
    model: "deepseek"
    temperature: 0.1
    max_tokens: 2000
    streaming: true
  
  # 错误修正配置
  error_correction:
    max_retries: 3
    retry_delay_ms: 100
  
  # Token 优化配置
  token_optimization:
    max_schema_tokens: 2000
    max_history_tokens: 1000
    use_summarization: true
```


## 数据模型获取

### 复用现有实现

数据模型通过现有的 `TableauDataLoader`（`platform/tableau/data_loader.py`）获取，已有完整实现：

```python
# 现有实现：analytics_assistant/src/platform/tableau/data_loader.py

class TableauDataLoader:
    """Tableau 数据模型加载器"""
    
    async def load_data_model(
        self,
        datasource_id: str,
        auth: Optional[TableauAuthContext] = None,
    ) -> DataModel:
        """
        加载数据源的数据模型（推荐方法）
        
        使用 GraphQL Metadata API，获取完整的字段信息：
        - name: 用户友好的显示名称
        - role: 字段角色（DIMENSION/MEASURE）
        - dataType: 数据类型
        - aggregation: 默认聚合方式
        - description: 字段描述
        """
        pass
    
    async def fetch_field_samples(
        self,
        datasource_id: str,
        fields: List[Field],
        measure_field: str,
        auth: Optional[TableauAuthContext] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """获取字段样例数据（用于 Prompt）"""
        pass
```

### DataModel 结构

数据模型定义在 `core/schemas/data_model.py`，已有完整实现：

```python
# 现有实现：analytics_assistant/src/core/schemas/data_model.py

class Field(BaseModel):
    """字段元数据模型"""
    name: str                          # 字段名称
    caption: str                       # 字段显示名称
    data_type: str                     # 数据类型
    role: str                          # 字段角色: DIMENSION/MEASURE
    data_category: Optional[str]       # 数据类别
    aggregation: Optional[str]         # 聚合方式
    description: Optional[str]         # 字段描述
    # ... 其他字段

class DataModel(BaseModel):
    """数据模型"""
    datasource_id: str
    datasource_name: Optional[str]
    fields: List[Field]
    tables: List[LogicalTable]
    relationships: List[TableRelationship]
    
    @property
    def dimensions(self) -> List[Field]:
        return [f for f in self.fields if f.is_dimension]
    
    @property
    def measures(self) -> List[Field]:
        return [f for f in self.fields if f.is_measure]
```

### 与 DimensionHierarchy 集成

维度层级推断通过 `DimensionHierarchyInference`（`agents/dimension_hierarchy/inference.py`）实现：

```python
# 在 WorkflowExecutor 中集成

async def create_context(self, ...) -> WorkflowContext:
    # 1. 加载数据模型
    data_model = await self._data_loader.load_data_model(datasource_id, auth)
    
    # 2. 推断维度层级并写入 data_model.fields
    await self._hierarchy.infer_and_enrich(
        data_model=data_model,
        datasource_luid=datasource_id,
    )
    
    # data_model.fields 中的每个 Field 现在包含：
    # - category: 维度类别（如 "地理"、"时间"）
    # - level: 层级级别（如 1, 2, 3）
    # - granularity: 粒度描述
    
    return WorkflowContext(data_model=data_model, ...)
```

**说明**：语义解析器不需要自己加载数据模型，通过 `WorkflowContext` 获取已加载的数据。


## 文件结构

### 代码组织

基于现有的项目结构，语义解析器的文件组织如下：

```
analytics_assistant/src/agents/semantic_parser/
├── __init__.py                    # 模块导出
├── graph.py                       # LangGraph 子图定义（节点 + 路由）
├── state.py                       # SemanticParserState 定义（已存在）
│
├── components/                    # 组件实现
│   ├── __init__.py
│   ├── intent_router.py          # 意图路由
│   ├── query_cache.py            # 查询缓存
│   ├── field_retriever.py        # 字段检索（复用 CascadeRetriever）
│   ├── few_shot_manager.py       # Few-shot 管理
│   ├── semantic_understanding.py # 语义理解核心
│   ├── filter_validator.py       # 筛选值验证
│   ├── error_corrector.py        # 错误修正
│   └── feedback_learner.py       # 反馈学习
│
├── prompts/                       # Prompt 模板（已存在）
│   ├── __init__.py
│   ├── semantic_understanding.py # 语义理解 Prompt 构建逻辑
│   ├── error_correction.py       # 错误修正 Prompt 构建逻辑
│   ├── prompt_builder.py         # 动态 Prompt 构建器
│   └── templates/                # XML 模板文件
│       ├── semantic_full.xml     # 完整版语义理解模板（复杂查询）
│       ├── semantic_simple.xml   # 简化版语义理解模板（简单查询）
│       ├── error_correction.xml  # 错误修正模板
│       └── few_shot_examples.xml # Few-shot 示例模板
│
└── schemas/                       # Pydantic 模型（已存在，需扩展）
    ├── __init__.py
    ├── input.py                  # 输入模型（IntentRouterInput 等）
    ├── output.py                 # 输出模型（SemanticOutput, SelfCheck 等）
    ├── intermediate.py           # 中间模型（FieldCandidate, FewShotExample 等）
    ├── cache.py                  # 缓存模型（CachedQuery, FeedbackRecord 等）
    └── filters.py                # 筛选器模型（FilterValidationResult 等）
```

### 复用现有模块

语义解析器复用以下现有模块，**不需要重新实现**：

| 功能 | 现有模块 | 说明 |
|------|---------|------|
| 配置管理 | `infra/config/config_loader.py` | 统一配置加载 |
| 数据模型 | `core/schemas/data_model.py` | DataModel, Field 定义 |
| 查询构建 | `platform/tableau/query_builder.py` | VizQL 适配器 |
| 数据加载 | `platform/tableau/data_loader.py` | TableauDataLoader |
| 向量检索 | `infra/rag/retriever.py` | CascadeRetriever |
| 缓存管理 | `infra/storage/langgraph_store.py` | CacheManager |
| LLM 调用 | `infra/ai/model_manager.py` | ModelManager |
| 维度层级 | `agents/dimension_hierarchy/inference.py` | DimensionHierarchyInference |

### 编排层扩展

在编排层（`orchestration/`）中扩展以支持语义解析器：

```
analytics_assistant/src/orchestration/
├── __init__.py
├── workflow/
│   ├── __init__.py
│   ├── context.py               # WorkflowContext（扩展）
│   ├── state.py                 # VizQLState
│   ├── routes.py                # 路由函数
│   ├── factory.py               # 工作流工厂
│   └── executor.py              # WorkflowExecutor（扩展）
└── ...
```

### 测试文件结构

```
analytics_assistant/tests/agents/semantic_parser/
├── __init__.py
├── conftest.py                    # 测试 fixtures
│
├── unit/                          # 单元测试
│   ├── __init__.py
│   ├── test_intent_router.py
│   ├── test_query_cache.py
│   ├── test_field_retriever.py
│   ├── test_few_shot_manager.py
│   ├── test_semantic_understanding.py
│   ├── test_filter_validator.py
│   ├── test_error_corrector.py
│   └── test_feedback_learner.py
│
├── property/                      # 属性测试
│   ├── __init__.py
│   ├── test_cache_properties.py
│   ├── test_retrieval_properties.py
│   ├── test_understanding_properties.py
│   └── test_feedback_properties.py
│
└── integration/                   # 集成测试
    ├── __init__.py
    ├── test_graph_flow.py
    └── test_multi_turn.py
```


## 时间表达式处理

### 时间提示生成器

为辅助 LLM 准确解析时间表达式，引入轻量级的 `TimeHintGenerator`。它不替换原始问题文本，而是在 Prompt 中提供参考日期范围提示。

**设计原则**：
- 只处理明确的、规则化的时间表达式
- 复杂表达式（如"去年同期"、"上个财年Q3"）交给 LLM
- 提供提示而非替换，保留原始语义

```python
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from typing import Optional, List
import re

class TimeHintGenerator:
    """时间提示生成器
    
    从用户问题中提取时间表达式，生成参考日期范围提示。
    只处理明确的、规则化的时间表达式，复杂表达式交给 LLM。
    
    使用方式:
    1. 在构建 Prompt 前调用 generate_hints()
    2. 将生成的 <time_hints> 添加到 Prompt 的 <context> 中
    3. LLM 既能看到原始问题，又有明确的日期参考
    
    财年支持:
    - 通过 fiscal_year_start_month 参数配置财年起始月份
    - 支持 "本财年"、"上财年"、"财年Q1-Q4" 等表达式
    """
    
    def __init__(self, current_date: date, fiscal_year_start_month: int = 1):
        self.current_date = current_date
        self.fiscal_year_start_month = fiscal_year_start_month
        
        # 静态时间表达式 → 计算函数
        # 注意：财年相关的模式需要访问 fiscal_year_start_month，所以在 __init__ 中定义
        self.PATTERNS = {
            # 相对日期
            "今天": lambda d: (d, d),
            "昨天": lambda d: (d - timedelta(days=1), d - timedelta(days=1)),
            "前天": lambda d: (d - timedelta(days=2), d - timedelta(days=2)),
            
            # 本周/上周
            "本周": lambda d: (d - timedelta(days=d.weekday()), d),
            "上周": lambda d: (
                d - timedelta(days=d.weekday() + 7),
                d - timedelta(days=d.weekday() + 1)
            ),
            
            # 本月/上月
            "本月": lambda d: (date(d.year, d.month, 1), d),
            "这个月": lambda d: (date(d.year, d.month, 1), d),
            "上个月": lambda d: (
                (date(d.year, d.month, 1) - relativedelta(months=1)),
                (date(d.year, d.month, 1) - timedelta(days=1))
            ),
            "上月": lambda d: (
                (date(d.year, d.month, 1) - relativedelta(months=1)),
                (date(d.year, d.month, 1) - timedelta(days=1))
            ),
            
            # 本季度/上季度
            "本季度": lambda d: (
                date(d.year, ((d.month - 1) // 3) * 3 + 1, 1),
                d
            ),
            "上季度": lambda d: (
                date(d.year, ((d.month - 1) // 3) * 3 + 1, 1) - relativedelta(months=3),
                date(d.year, ((d.month - 1) // 3) * 3 + 1, 1) - timedelta(days=1)
            ),
            
            # 本年/去年
            "今年": lambda d: (date(d.year, 1, 1), d),
            "本年": lambda d: (date(d.year, 1, 1), d),
            "去年": lambda d: (date(d.year - 1, 1, 1), date(d.year - 1, 12, 31)),
            
            # 年初至今
            "年初至今": lambda d: (date(d.year, 1, 1), d),
            "YTD": lambda d: (date(d.year, 1, 1), d),
            
            # ========== 财年相关表达式 ==========
            "本财年": lambda d: self._calc_fiscal_year(d, 0),
            "上财年": lambda d: self._calc_fiscal_year(d, -1),
            "财年至今": lambda d: self._calc_fiscal_ytd(d),
            "FYTD": lambda d: self._calc_fiscal_ytd(d),
        }
        
        # 动态模式：最近N天/周/月
        self.DYNAMIC_PATTERNS = [
            (r"最近(\d+)天", lambda d, n: (d - timedelta(days=int(n)), d)),
            (r"过去(\d+)天", lambda d, n: (d - timedelta(days=int(n)), d)),
            (r"最近(\d+)周", lambda d, n: (d - timedelta(weeks=int(n)), d)),
            (r"最近(\d+)个月", lambda d, n: (d - relativedelta(months=int(n)), d)),
            (r"过去(\d+)个月", lambda d, n: (d - relativedelta(months=int(n)), d)),
        ]
        
        # 财年季度模式：财年Q1, 财年Q2, 上财年Q3 等
        self.FISCAL_QUARTER_PATTERNS = [
            (r"(?:本)?财年Q([1-4])", lambda d, q: self._calc_fiscal_quarter(d, 0, int(q))),
            (r"上财年Q([1-4])", lambda d, q: self._calc_fiscal_quarter(d, -1, int(q))),
        ]
    
    def _get_fiscal_year_start(self, calendar_date: date) -> date:
        """
        获取给定日期所属财年的起始日期
        
        例如：fiscal_year_start_month=4 (4月开始)
        - 2025-01-15 属于 FY2024，起始日期是 2024-04-01
        - 2025-05-15 属于 FY2025，起始日期是 2025-04-01
        """
        fy_start = self.fiscal_year_start_month
        if calendar_date.month >= fy_start:
            return date(calendar_date.year, fy_start, 1)
        else:
            return date(calendar_date.year - 1, fy_start, 1)
    
    def _calc_fiscal_year(self, d: date, offset: int) -> tuple:
        """
        计算财年日期范围
        
        Args:
            d: 当前日期
            offset: 0=本财年, -1=上财年, 1=下财年
        
        Returns:
            (start_date, end_date)
        """
        fy_start = self._get_fiscal_year_start(d)
        if offset != 0:
            fy_start = fy_start + relativedelta(years=offset)
        fy_end = fy_start + relativedelta(years=1) - timedelta(days=1)
        
        # 如果是本财年，结束日期是当前日期或财年结束日期（取较小值）
        if offset == 0:
            fy_end = min(fy_end, d)
        
        return (fy_start, fy_end)
    
    def _calc_fiscal_ytd(self, d: date) -> tuple:
        """计算财年至今（从财年开始到当前日期）"""
        fy_start = self._get_fiscal_year_start(d)
        return (fy_start, d)
    
    def _calc_fiscal_quarter(self, d: date, fy_offset: int, quarter: int) -> tuple:
        """
        计算财年季度日期范围
        
        Args:
            d: 当前日期
            fy_offset: 0=本财年, -1=上财年
            quarter: 1-4
        
        Returns:
            (start_date, end_date)
        """
        fy_start = self._get_fiscal_year_start(d)
        if fy_offset != 0:
            fy_start = fy_start + relativedelta(years=fy_offset)
        
        # 计算季度起始月份（相对于财年起始）
        quarter_start = fy_start + relativedelta(months=(quarter - 1) * 3)
        quarter_end = quarter_start + relativedelta(months=3) - timedelta(days=1)
        
        return (quarter_start, quarter_end)
    
    def generate_hints(self, question: str) -> List[dict]:
        """
        从问题中提取时间表达式，生成提示
        
        Returns:
            [{"expression": "上个月", "start": "2024-12-01", "end": "2024-12-31"}, ...]
        """
        hints = []
        
        # 1. 匹配静态模式
        for expr, calc_fn in self.PATTERNS.items():
            if expr in question:
                start, end = calc_fn(self.current_date)
                hints.append({
                    "expression": expr,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                })
        
        # 2. 匹配动态模式
        for pattern, calc_fn in self.DYNAMIC_PATTERNS:
            match = re.search(pattern, question)
            if match:
                n = match.group(1)
                start, end = calc_fn(self.current_date, n)
                hints.append({
                    "expression": match.group(0),
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                })
        
        # 3. 匹配财年季度模式
        for pattern, calc_fn in self.FISCAL_QUARTER_PATTERNS:
            match = re.search(pattern, question)
            if match:
                q = match.group(1)
                start, end = calc_fn(self.current_date, q)
                hints.append({
                    "expression": match.group(0),
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                })
        
        return hints
    
    def format_for_prompt(self, question: str) -> str:
        """
        生成用于 Prompt 的时间提示 XML
        
        Returns:
            "<time_hints>...</time_hints>" 或空字符串
        """
        hints = self.generate_hints(question)
        if not hints:
            return ""
        
        lines = []
        for h in hints:
            lines.append(f'  <hint expression="{h["expression"]}">{h["start"]} 到 {h["end"]}</hint>')
        
        # 如果财年起始月份不是1月，添加财年配置说明
        if self.fiscal_year_start_month != 1:
            lines.insert(0, f'  <fiscal_year_config>财年起始月份: {self.fiscal_year_start_month}月</fiscal_year_config>')
        
        return "<time_hints>\n" + "\n".join(lines) + "\n</time_hints>"
```

### 集成到 Prompt 构建

```python
# 在 DynamicPromptBuilder 中使用

class DynamicPromptBuilder:
    def __init__(self, ...):
        # ...
        self._time_hint_generator: Optional[TimeHintGenerator] = None
    
    def build(
        self,
        question: str,
        current_date: date,
        ...
    ) -> str:
        # 初始化时间提示生成器
        self._time_hint_generator = TimeHintGenerator(current_date)
        
        # 生成时间提示
        time_hints = self._time_hint_generator.format_for_prompt(question)
        
        # 构建 context 部分
        context = f"""<context>
<current_date>{current_date.isoformat()}</current_date>
<timezone>{timezone}</timezone>
<fiscal_year_start>{fiscal_year_start_month}月</fiscal_year_start>
{time_hints}
</context>"""
        
        # ... 继续构建其他部分
```

### Prompt 中的时间提示示例

```xml
<context>
<current_date>2025-01-27</current_date>
<timezone>Asia/Shanghai</timezone>
<fiscal_year_start>1月</fiscal_year_start>

<time_hints>
  <hint expression="上个月">2024-12-01 到 2024-12-31</hint>
  <hint expression="最近30天">2024-12-28 到 2025-01-27</hint>
</time_hints>
</context>

<user_question>上个月各地区的销售额是多少？最近30天的趋势呢？</user_question>
```

### 时间表达式标准化输出

LLM 负责解析时间表达式，输出标准化的时间范围：

```python
class TimeRange(BaseModel):
    """标准化的时间范围"""
    
    range_type: Literal["absolute", "relative", "fiscal"]
    
    # 绝对时间
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    
    # 相对时间
    relative_period: Optional[str] = None  # last_month, this_quarter, ytd, etc.
    offset: Optional[int] = None           # -1 表示上一个周期
    
    # 财年时间
    fiscal_year: Optional[int] = None
    fiscal_quarter: Optional[int] = None
    
    # 原始表达式（用于调试）
    original_expression: str

class TimeExpressionConfig(BaseModel):
    """时间表达式配置"""
    
    current_date: date
    timezone: str = "Asia/Shanghai"
    fiscal_year_start_month: int = 1  # 1=1月, 4=4月
    
    # 业务日历
    holidays: List[date] = Field(default_factory=list)
    workdays_override: Dict[date, bool] = Field(default_factory=dict)
```

### 常见时间表达式 Few-shot

```xml
<time_examples>
  <example>
    <input>上个月</input>
    <context>当前日期: 2025-01-27</context>
    <output>{"range_type": "relative", "relative_period": "last_month", "start_date": "2024-12-01", "end_date": "2024-12-31"}</output>
  </example>
  
  <example>
    <input>去年同期</input>
    <context>当前日期: 2025-01-27, 当前筛选: 2025年1月</context>
    <output>{"range_type": "relative", "relative_period": "same_period_last_year", "start_date": "2024-01-01", "end_date": "2024-01-31"}</output>
  </example>
  
  <example>
    <input>本季度</input>
    <context>当前日期: 2025-01-27</context>
    <output>{"range_type": "relative", "relative_period": "this_quarter", "start_date": "2025-01-01", "end_date": "2025-03-31"}</output>
  </example>
  
  <example>
    <input>最近30天</input>
    <context>当前日期: 2025-01-27</context>
    <output>{"range_type": "relative", "relative_period": "last_n_days", "offset": 30, "start_date": "2024-12-28", "end_date": "2025-01-27"}</output>
  </example>
  
  <example>
    <input>2024财年Q3</input>
    <context>当前日期: 2025-01-27, 财年起始月: 4</context>
    <output>{"range_type": "fiscal", "fiscal_year": 2024, "fiscal_quarter": 3, "start_date": "2024-10-01", "end_date": "2024-12-31"}</output>
  </example>
  
  <example>
    <input>年初至今</input>
    <context>当前日期: 2025-01-27</context>
    <output>{"range_type": "relative", "relative_period": "ytd", "start_date": "2025-01-01", "end_date": "2025-01-27"}</output>
  </example>
</time_examples>
```


## 筛选值确认机制（基于 LangGraph interrupt()）

筛选值验证通过工具调用实现，当发现值不匹配时，通过 LangGraph 的 `interrupt()` 函数暂停执行，让用户确认。

### 设计原则

1. **使用原生机制**：使用 LangGraph 的 `interrupt()` 函数，支持条件中断
2. **工具化**：验证逻辑封装在工具中，可被复用
3. **智能验证**：只验证低基数字段（值已缓存），高基数字段跳过

### 验证策略

```
验证决策流程:
┌─────────────────────────────────────────────────────────────────┐
│                    FilterValueValidator                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  对于每个筛选条件:                                               │
│                                                                  │
│  1. 时间字段 → 跳过验证（LLM 已处理时间表达式）                  │
│                                                                  │
│  2. 检查 FieldValueCache:                                        │
│     ├─ 缓存命中（低基数字段）→ 从缓存验证                        │
│     └─ 缓存未命中（高基数字段）→ 跳过验证，执行查询后再处理      │
│                                                                  │
│  3. 从缓存验证:                                                  │
│     ├─ 精确匹配 → 通过                                           │
│     ├─ 模糊匹配（相似度 > 0.8）→ 调用工具，触发人工确认          │
│     └─ 无匹配 → 调用工具，触发人工确认                           │
└─────────────────────────────────────────────────────────────────┘
```

### 完整流程

```
用户问题: "上海的销售额是多少？"
                │
                ▼
┌─────────────────────────────────────────────────────────────────┐
│ 阶段 5: SemanticUnderstanding                                    │
│ ─────────────────────────────────────────────────────────────── │
│ LLM 输出:                                                        │
│   filters: [{field: "省份", operator: "=", values: ["上海"]}]   │
└─────────────────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────┐
│ 阶段 5.5: FilterValueValidator                                   │
│ ─────────────────────────────────────────────────────────────── │
│                                                                  │
│ 1. 检查 "省份" 字段:                                             │
│    - 不是时间字段 → 需要验证                                     │
│    - 检查 FieldValueCache → 命中（低基数字段，已预加载）         │
│    - 缓存值: ["北京市", "上海市", "广州市", ...]                 │
│                                                                  │
│ 2. 验证 "上海":                                                  │
│    - 精确匹配: "上海" not in cached_values → 失败                │
│    - 模糊匹配: find_similar("上海", cached_values)               │
│      → 找到 "上海市" (相似度 0.86 > 0.8)                        │
│                                                                  │
│ 3. 调用 validate_filter_value 工具:                              │
│    → 返回 needs_confirmation=True                                │
│    → filter_validator_node 调用 interrupt()                      │
└─────────────────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────┐
│ LangGraph interrupt() 暂停执行                                   │
│ ─────────────────────────────────────────────────────────────── │
│ 返回给用户:                                                      │
│   "省份字段中没有'上海'，找到相似值：                           │
│    - 上海市                                                      │
│   请确认或输入正确的值"                                          │
└─────────────────────────────────────────────────────────────────┘
                │
                ▼
        用户确认: "上海市" 或 "是的"
                │
                ▼
┌─────────────────────────────────────────────────────────────────┐
│ 工具返回确认的值                                                 │
│ ─────────────────────────────────────────────────────────────── │
│ validate_filter_value 工具返回:                                  │
│   confirmed_value: "上海市"                                      │
└─────────────────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────┐
│ FilterValueValidator 更新 filters                                │
│ ─────────────────────────────────────────────────────────────── │
│ 原: [{field: "省份", values: ["上海"]}]                          │
│ 新: [{field: "省份", values: ["上海市"]}]                        │
└─────────────────────────────────────────────────────────────────┘
                │
                ▼
        继续阶段 6: 查询构建与执行
```

### ValidateFilterValueTool 工具定义

```python
class ValidateFilterValueResult(BaseModel):
    """验证结果"""
    is_valid: bool
    matched_value: Optional[str] = None  # 匹配到的值
    similar_values: List[str] = []  # 相似的候选值
    message: Optional[str] = None  # 给用户的提示信息
    needs_confirmation: bool = False  # 是否需要人工确认（有相似值时触发中断）
    is_unresolvable: bool = False  # 是否无法解决（没有相似值，需要用户重新输入）

class ValidateFilterValueTool(BaseTool):
    """验证筛选值工具
    
    查询数据源验证筛选值是否存在，如果不存在返回相似值。
    配合 LangGraph interrupt() 使用：
    - needs_confirmation=True AND similar_values非空 → 触发 interrupt() 等待用户选择
    - is_unresolvable=True → 不中断，由 FilterValueValidator 返回 needs_clarification
    """
    
    name: str = "validate_filter_value"
    description: str = "验证筛选条件的值是否存在于数据源中"
    
    def __init__(self, field_value_cache: FieldValueCache):
        self._cache = field_value_cache
    
    async def _arun(
        self,
        field_name: str,
        filter_value: str,
        datasource_luid: str,
    ) -> ValidateFilterValueResult:
        """
        执行验证
        
        流程:
        1. 从缓存获取字段的所有可能值
        2. 精确匹配 → 返回 is_valid=True
        3. 模糊匹配（有相似值）→ 返回 needs_confirmation=True（触发中断）
        4. 无匹配（无相似值）→ 返回 is_unresolvable=True（不中断，返回澄清）
        """
        # 1. 从缓存获取字段值
        cached_values = self._cache.get(field_name, datasource_luid)
        
        if cached_values is None:
            # 缓存未命中（高基数字段），跳过验证
            return ValidateFilterValueResult(
                is_valid=True,
                matched_value=filter_value,
                message=None,
                needs_confirmation=False,
            )
        
        # 2. 精确匹配
        if filter_value in cached_values:
            return ValidateFilterValueResult(
                is_valid=True,
                matched_value=filter_value,
                needs_confirmation=False,
            )
        
        # 3. 模糊匹配，找相似值
        similar = self._find_similar(filter_value, cached_values)
        
        if not similar:
            # 没有相似值 → 无法解决，需要用户重新输入
            # 不触发中断，由 FilterValueValidator 返回 needs_clarification
            return ValidateFilterValueResult(
                is_valid=False,
                similar_values=[],
                message=f"字段'{field_name}'中没有'{filter_value}'，也没有找到相似的值。请检查输入是否正确。",
                needs_confirmation=False,  # 不触发中断
                is_unresolvable=True,  # 标记为无法解决
            )
        
        # 4. 有相似值，需要用户确认 → 触发中断
        return ValidateFilterValueResult(
            is_valid=False,
            similar_values=similar,
            message=f"字段'{field_name}'中没有'{filter_value}'，找到相似值：{', '.join(similar)}。请选择正确的值。",
            needs_confirmation=True,  # 触发中断
            is_unresolvable=False,
        )
    
    def _find_similar(
        self,
        target: str,
        candidates: List[str],
        threshold: float = 0.8,
        top_k: int = 5,
    ) -> List[str]:
        """查找相似的候选值（编辑距离 + 包含关系）"""
        from difflib import SequenceMatcher
        
        scored = []
        for c in candidates:
            # 包含关系优先
            if target in c or c in target:
                scored.append((c, 1.0))
            else:
                ratio = SequenceMatcher(None, target, c).ratio()
                if ratio >= threshold:
                    scored.append((c, ratio))
        
        # 按相似度排序
        scored.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in scored[:top_k]]
```

### 筛选值确认中断机制

我们采用 LangGraph 的 `interrupt()` 函数实现条件中断，这是 LangGraph 原生支持的人工介入机制。

**方案：在 filter_validator 节点内部调用 interrupt()**

```python
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt

def create_semantic_parser_graph() -> StateGraph:
    graph = StateGraph(SemanticParserState)
    
    # ... 添加其他节点 ...
    
    # filter_validator 节点：执行验证并检查是否需要中断
    async def filter_validator_node(state: SemanticParserState) -> Dict[str, Any]:
        """筛选值验证节点
        
        验证完成后，如果有需要确认的筛选值（有相似值可选），
        使用 LangGraph 的 interrupt() 函数暂停执行。
        
        多轮确认支持：
        - 使用 confirmed_filters 累积所有确认结果
        - 每次确认后，将新确认添加到列表中
        - 防止多轮确认时上下文丢失
        """
        validator = FilterValueValidator(...)
        
        # 获取已确认的筛选值（用于多轮确认场景）
        existing_confirmations = state.get("confirmed_filters", [])
        
        # 应用已有的确认到 semantic_output
        semantic_output = state["semantic_output"]
        if existing_confirmations:
            for conf in existing_confirmations:
                semantic_output = validator.apply_single_confirmation(
                    semantic_output,
                    conf["field_name"],
                    conf["original_value"],
                    conf["confirmed_value"],
                )
        
        summary = await validator.validate(
            filters=semantic_output["where"]["filters"],
            data_model=state["data_model"],
            datasource_luid=state["datasource_luid"],
        )
        
        # 检查是否有需要用户确认的筛选值
        pending_confirmations = [
            r for r in summary.results
            if r.needs_confirmation and len(r.similar_values) > 0
        ]
        
        if pending_confirmations:
            # 使用 LangGraph interrupt() 暂停执行
            # 用户确认后，通过 graph.update_state() 更新状态并恢复
            confirmation_request = {
                "type": "filter_value_confirmation",
                "pending": [
                    {
                        "field_name": r.field_name,
                        "requested_value": r.requested_value,
                        "similar_values": r.similar_values,
                        "message": r.message,
                    }
                    for r in pending_confirmations
                ],
            }
            
            # interrupt() 会暂停执行并返回给调用方
            # 调用方可以通过 graph.update_state() 提供用户确认的值
            user_response = interrupt(confirmation_request)
            
            # 用户确认后，应用确认的值并累积到 confirmed_filters
            if user_response and "confirmations" in user_response:
                new_confirmations = []
                for field_name, confirmed_value in user_response["confirmations"].items():
                    # 找到原始值
                    original_value = next(
                        (r.requested_value for r in pending_confirmations 
                         if r.field_name == field_name),
                        None
                    )
                    if original_value:
                        new_confirmations.append({
                            "field_name": field_name,
                            "original_value": original_value,
                            "confirmed_value": confirmed_value,
                            "confirmed_at": datetime.now().isoformat(),
                        })
                
                # 累积所有确认（包括之前的和新的）
                all_confirmations = existing_confirmations + new_confirmations
                
                updated_output = validator.apply_confirmations(
                    semantic_output,
                    user_response["confirmations"],
                )
                return {
                    "semantic_output": updated_output,
                    "filter_validation_result": summary.model_dump(),
                    "confirmed_filters": all_confirmations,  # 累积确认结果
                }
        
        return {
            "semantic_output": semantic_output,
            "filter_validation_result": summary.model_dump(),
            "confirmed_filters": existing_confirmations,  # 保留已有确认
        }
    
    graph.add_node("filter_validator", filter_validator_node)
    # ... 其他配置 ...
```

**调用方处理中断**：

```python
# 执行工作流
config = {"configurable": {"thread_id": "session_123"}}
result = await graph.ainvoke(initial_state, config)

# 检查是否被中断
if result.get("__interrupt__"):
    interrupt_data = result["__interrupt__"]
    if interrupt_data["type"] == "filter_value_confirmation":
        # 展示给用户，获取确认
        user_confirmations = await show_confirmation_dialog(interrupt_data["pending"])
        
        # 恢复执行，提供用户确认的值
        # 注意：confirmed_filters 会自动累积，支持多轮确认
        result = await graph.ainvoke(
            {"confirmations": user_confirmations},
            config,
        )
```

**优势**：
- 使用 LangGraph 原生的 `interrupt()` 机制，无需修改中间件
- 中断点在节点内部，可以精确控制中断条件
- 支持复杂的中断数据传递（多个待确认字段）
- 与 checkpointer 配合，支持跨请求恢复

### FilterValueValidator 组件

```python
class FilterValueValidator:
    """筛选值验证器
    
    验证策略（平衡性能和用户体验）：
    1. 时间字段：跳过验证（LLM 已处理）
    2. 低基数字段（缓存命中）：从缓存验证，不匹配时调用工具
       - 有相似值 → 使用 LangGraph interrupt() 暂停执行
       - 无相似值 → 返回 has_unresolvable_filters=True
    3. 高基数字段（缓存未命中）：跳过验证，执行查询后如果空结果再处理
    """
    
    def __init__(
        self,
        field_value_cache: FieldValueCache,
        validate_tool: ValidateFilterValueTool,
    ):
        self._cache = field_value_cache
        self._tool = validate_tool
    
    async def validate(
        self,
        filters: List[Filter],
        data_model: DataModel,
        datasource_luid: str,
    ) -> FilterValidationSummary:
        """
        验证所有筛选条件
        
        Returns:
            FilterValidationSummary 包含:
            - results: 每个筛选条件的验证结果
            - all_valid: 所有筛选条件都验证通过
            - has_unresolvable_filters: 是否有无法解决的筛选条件
        """
        results = []
        has_unresolvable = False
        
        for f in filters:
            field = data_model.get_field(f.field_name)
            if not field:
                continue
            
            # 1. 时间字段跳过
            if field.data_type.lower() in ("date", "datetime", "timestamp"):
                results.append(FilterValidationResult(
                    field_name=f.field_name,
                    requested_value="",
                    matched_values=[],
                    similar_values=[],
                    is_valid=True,
                    validation_type="skipped",
                    skip_reason="time_field",
                ))
                continue
            
            # 2. 检查缓存
            cached_values = self._cache.get(f.field_name, datasource_luid)
            
            if cached_values is None:
                # 高基数字段，跳过验证
                results.append(FilterValidationResult(
                    field_name=f.field_name,
                    requested_value="",
                    matched_values=[],
                    similar_values=[],
                    is_valid=True,
                    validation_type="skipped",
                    skip_reason="high_cardinality_not_cached",
                ))
                continue
            
            # 3. 验证每个筛选值
            for value in f.values:
                # 调用工具验证
                # 如果 needs_confirmation=True 且有相似值，filter_validator_node 会调用 interrupt()
                tool_result = await self._tool._arun(
                    field_name=f.field_name,
                    filter_value=value,
                    datasource_luid=datasource_luid,
                )
                
                # 检查是否无法解决
                if tool_result.is_unresolvable:
                    has_unresolvable = True
                
                results.append(FilterValidationResult(
                    field_name=f.field_name,
                    requested_value=value,
                    matched_values=[tool_result.matched_value] if tool_result.matched_value else [],
                    similar_values=tool_result.similar_values,
                    is_valid=tool_result.is_valid,
                    validation_type="exact_match" if tool_result.is_valid else (
                        "unresolvable" if tool_result.is_unresolvable else "needs_confirmation"
                    ),
                    needs_confirmation=tool_result.needs_confirmation,
                    message=tool_result.message,
                ))
        
        return FilterValidationSummary(
            results=results,
            all_valid=all(r.is_valid for r in results),
            has_unresolvable_filters=has_unresolvable,
        )
    
    def apply_confirmations(
        self,
        semantic_output: SemanticOutput,
        confirmations: Dict[str, str],  # {original_value: confirmed_value}
    ) -> SemanticOutput:
        """
        应用用户确认的值到 semantic_output
        
        在 interrupt() 返回用户确认后调用
        """
        updated_filters = []
        for f in semantic_output.where.filters:
            new_values = [
                confirmations.get(v, v) for v in f.values
            ]
            updated_filters.append(f.model_copy(update={"values": new_values}))
        
        updated_where = semantic_output.where.model_copy(update={"filters": updated_filters})
        return semantic_output.model_copy(update={"where": updated_where})
```

### 方案优势

| 优势 | 说明 |
|------|------|
| **使用原生机制** | 使用 LangGraph 的 `interrupt()` 函数，支持条件中断 |
| **精确控制** | 中断点在节点内部，可以精确控制中断条件 |
| **工具化** | 验证逻辑封装在工具中，可被其他地方复用 |
| **智能验证** | 只验证低基数字段，高基数字段跳过，平衡性能和体验 |
| **前端统一处理** | 前端只需处理 `interrupt` 状态，不需区分确认类型 |
| **区分中断与澄清** | 有相似值时中断让用户选择，无相似值时返回澄清让用户重新输入 |


## 补充的 Correctness Properties

基于新增的设计内容，补充以下正确性属性：

### Property 21: Context Data Model Caching

*For any* session with multiple queries to the same datasource, the data model SHALL be loaded at most once within the cache TTL period.

**Validates: 上下文状态管理 - 避免重复获取**

### Property 22: Context State Persistence

*For any* multi-turn conversation, the context state (data_model, hierarchies, field_values_cache) SHALL persist across turns within the same session.

**Validates: 上下文状态管理 - 会话级缓存**

### Property 23: Filter Validation Before Execution

*For any* query with filter conditions, the FilterValueValidator SHALL validate all filter values before query execution.

**Validates: FilterValueValidator 阶段**

### Property 24: Clarification Source Tracking

*For any* clarification request, the clarification_source field SHALL indicate whether it originated from SemanticUnderstanding or FilterValueValidator.

**Validates: 流程控制 - 澄清来源追踪**

### Property 25: Prompt Complexity Adaptation

*For any* query containing derived metric keywords (率、比、同比、环比), the DynamicPromptBuilder SHALL use the COMPLEX template.

**Validates: DynamicPromptBuilder - 复杂度检测**

### Property 26: Time Expression Context

*For any* time expression parsing, the Prompt SHALL include current_date, timezone, and fiscal_year_start_month.

**Validates: 时间表达式处理 - 上下文完整性**

### Property 27: Schema Hash Consistency

*For any* data model, the schema_hash SHALL change if and only if the field list changes (name, data_type, or role).

**Validates: 数据模型获取 - 变更检测**

### Property 28: Hierarchy Enrichment

*For any* dimension field with a known hierarchy, the enriched data model SHALL include drill-down options.

**Validates: 与 DimensionHierarchy 集成**

### Property 29: Filter Validation Skip for Time Fields

*For any* filter on a date/datetime/timestamp field, the FilterValueValidator SHALL skip validation and return validation_type="skipped".

**Validates: FilterValueValidator 性能优化**

### Property 30: Duplicate Error Detection

*For any* error correction attempt where the same error (by hash) has occurred twice, the ErrorCorrector SHALL abort and return should_continue=false.

**Validates: ErrorCorrector 防止无限循环**

### Property 30.1: Alternating Error Detection

*For any* error correction sequence where the total error history length reaches MAX_RETRIES (regardless of individual error types), the ErrorCorrector SHALL abort with reason "total_error_history_exceeded". This prevents alternating error patterns (A→B→A→B) from bypassing the duplicate detection.

**Validates: ErrorCorrector 防止交替错误绕过**

### Property 31: Non-Retryable Error Handling

*For any* error of type timeout, service_unavailable, authentication_error, or rate_limit_exceeded, the ErrorCorrector SHALL NOT attempt retry.

**Validates: ErrorCorrector 错误分类处理**

### Property 32: Cache Schema Validation on Read

*For any* cache read operation, if the cached schema_hash differs from the current data model's schema_hash, the cache SHALL return None (cache miss).

**Validates: QueryCache schema_hash 失效机制**

### Property 33: Time Hint Generation

*For any* user question containing a recognized time expression (今天、上个月、最近N天 etc.), the TimeHintGenerator SHALL produce a time_hints XML with correct date ranges.

**Validates: TimeHintGenerator 时间提示生成**

### Property 34: Filter Confirmation via LangGraph interrupt()

*For any* filter value that needs confirmation (ValidateFilterValueTool returns needs_confirmation=True with non-empty similar_values), the filter_validator_node SHALL call `interrupt()` to pause execution and wait for user confirmation. The workflow resumes via `graph.update_state()` with the user's selected value.

**Validates: 筛选值确认机制 - LangGraph interrupt() 方案**

### Property 35: Filter Value Update After Confirmation

*For any* user-confirmed filter value, the ValidateFilterValueTool SHALL return the confirmed value, and FilterValueValidator SHALL update semantic_output.filters with the confirmed value before continuing to query_adapter.

**Validates: 筛选值确认机制 - 工具返回值更新**

### Property 36: Field Value Cache LRU Eviction

*For any* FieldValueCache with MAX_FIELDS entries, adding a new entry SHALL evict the least recently used entry within the same shard.

**Validates: FieldValueCache LRU 淘汰策略**

### Property 36.1: Field Value Cache Sharded Lock Concurrency

*For any* concurrent access to FieldValueCache with different keys that hash to different shards, the operations SHALL execute in parallel without blocking each other.

**Validates: FieldValueCache 分段锁并发性能**

### Property 37: Field Value Cache Preload Threshold

*For any* field preloading operation, only dimension fields with cardinality < 500 SHALL be preloaded.

**Validates: FieldValueCache 预热策略**

### Property 38: Unresolvable Filter Detection

*For any* filter value validation where no exact match AND no similar values (similarity > 0.8) are found, the FilterValidationSummary.has_unresolvable_filters SHALL be true, causing the workflow to return needs_clarification to the user.

**Validates: 筛选值验证 - 无法解决的筛选条件检测**

### Property 39: Filter Validation interrupt() Condition

*For any* ValidateFilterValueTool call that returns needs_confirmation=True AND similar_values is non-empty, the filter_validator_node SHALL call `interrupt()` to pause execution. If similar_values is empty (no candidates to choose from), the workflow SHALL NOT call `interrupt()` but instead return needs_clarification=true to the user (requiring a new dialog turn from IntentRouter).

**Validates: 筛选值确认机制 - interrupt() 触发条件**

### Property 40: Multi-Round Filter Confirmation Accumulation

*For any* multi-round filter confirmation scenario (e.g., first confirming "北京" → "北京市", then "上海" → "上海市"), the filter_validator_node SHALL accumulate all confirmations in the `confirmed_filters` state field. Previous confirmations SHALL NOT be lost when new confirmations are added.

**Validates: 多轮筛选值确认 - 上下文累积**
