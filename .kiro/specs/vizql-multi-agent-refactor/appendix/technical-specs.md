# 技术规格

本文档包含系统架构、数据模型、缓存架构、性能优化、数据采样策略等技术细节。

---

## tableau_sdk的作用

### 概述

**tableau_sdk** 是一个TypeScript SDK，位于 `tableau_sdk/apis/vizqlDataServiceApi.ts`，提供了VizQL Data Service的完整类型定义。

### 提供的价值

1. **完整的类型定义**（TypeScript + Zod schema）
   - `Field` - 字段类型（FieldBase、Function Field、Calculation Field）
   - `Filter` - 筛选器类型（SetFilter、TopNFilter、RelativeDateFilter、QuantitativeFilter等）
   - `Query` - 查询结构（fields + filters）
   - `Function` - 支持的函数枚举（SUM、AVG、YEAR、MONTH等）

2. **类型验证**
   - 使用Zod schema验证查询结构
   - 确保生成的查询符合VDS规范

3. **API定义**
   - `queryDatasource` - 查询数据源
   - `readMetadata` - 读取元数据

### 对Python项目的帮助

虽然tableau_sdk是TypeScript实现，但对Python项目有重要参考价值：

1. **查询构建器（需求8）**
   - 参考tableau_sdk的类型定义，创建对应的Python Pydantic模型
   - 确保生成的VizQL查询100%符合规范
   - 示例：
     ```python
     # 参考 tableau_sdk 的 Field 类型
     class FieldBase(BaseModel):
         fieldCaption: str
         fieldAlias: Optional[str] = None
         sortDirection: Optional[Literal["ASC", "DESC"]] = None
         sortPriority: Optional[int] = None

     class FunctionField(FieldBase):
         function: Literal["SUM", "AVG", "COUNT", ...]

     class CalculationField(FieldBase):
         calculation: str

     Field = Union[FieldBase, FunctionField, CalculationField]
     ```

2. **查询验证**
   - 参考tableau_sdk的验证规则
   - 实现Python版本的查询验证器
   - 验证规则：
     - 至少包含一个field
     - fieldCaption不能为空
     - sortPriority不能重复
     - function和calculation互斥

3. **API调用**
   - 参考tableau_sdk的API定义
   - 确保Python调用VDS API时使用正确的请求格式

### 使用建议

1. **创建Python类型定义**
   - 在 `experimental/types/vizql_types.py` 中创建Pydantic模型
   - 参考tableau_sdk的TypeScript类型定义
   - 保持与tableau_sdk的类型一致性

2. **查询生成**
   - 使用Pydantic模型生成VizQL查询
   - 自动验证查询结构
   - 序列化为JSON发送给VDS

3. **持续同步**
   - 当tableau_sdk更新时，同步更新Python类型定义
   - 确保两者保持一致

---

## 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                         前端层 (Vue 3)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ 对话界面 │  │ 进度展示 │  │ 数据可视化│  │ 重规划交互│   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │ SSE / HTTP
┌─────────────────────────────────────────────────────────────┐
│                    LangGraph编排层                           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  StateGraph: 状态管理 + 对话历史 + 检查点机制        │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                      Agent层 (6个Agent)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                 │
│  │维度层级  │  │问题理解  │  │查询规划  │                 │
│  └──────────┘  └──────────┘  └──────────┘                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                 │
│  │  洞察    │  │  重规划  │  │  总结    │                 │
│  └──────────┘  └──────────┘  └──────────┘                 │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                   代码组件层 (6个组件)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │元数据管理│  │查询构建  │  │查询执行  │  │统计检测  │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│  ┌──────────┐  ┌──────────┐                               │
│  │数据合并  │  │任务调度  │                               │
│  └──────────┘  └──────────┘                               │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                      数据层                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                 │
│  │  Redis   │  │ Tableau  │  │   LLM    │                 │
│  │  缓存    │  │   VDS    │  │ (Qwen3)  │                 │
│  └──────────┘  └──────────┘  └──────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

### 数据流图

```
用户提问
  │
  ├─> [元数据管理器] 获取数据源元数据
  │     │
  │     └─> [维度层级推断Agent] (首次访问)
  │           │
  │           └─> Redis缓存 (24小时)
  │
  ├─> [问题理解Agent] 理解用户意图
  │     │
  │     └─> 问题理解结果
  │
  ├─> [查询规划Agent] 选择字段 + 生成Spec + 拆分子任务
  │     │
  │     └─> SubTask列表（包含完整的StructuredQuestionSpec）
  │
  ├─> [任务调度器] 并行执行
  │     │
  │     ├─> [查询构建器] 生成VizQL查询
  │     │     │
  │     │     └─> VizQL JSON
  │     │
  │     ├─> [查询执行器] 执行查询
  │     │     │
  │     │     └─> 查询结果 (DataFrame)
  │     │
  │     └─> [统计检测器] 统计分析
  │           │
  │           └─> 统计报告
  │
  ├─> [洞察Agent] 业务解读 (并行)
  │     │
  │     └─> 关键发现 + 异常分析
  │
  ├─> [数据合并器] 合并结果
  │     │
  │     └─> 合并后的数据
  │
  ├─> [重规划Agent] 决策
  │     │
  │     ├─> 需要重规划 → 回到问题理解Agent
  │     │
  │     └─> 不需要重规划 → 继续
  │
  └─> [总结Agent] 生成最终报告
        │
        └─> 最终分析报告
```

---

## 数据模型

### StructuredQuestionSpec

```python
class StructuredQuestionSpec(TypedDict):
    """结构化问题规格"""

    # 基础信息
    question_text: str  # 问题文本
    question_type: List[str]  # 问题类型：对比、趋势、排名等
    complexity: str  # 复杂度：Simple/Medium/Complex

    # 字段选择
    dimensions: List[str]  # 维度字段列表
    measures: List[Dict[str, Any]]  # 度量字段列表
    # measures示例：[{"field": "销售额", "function": "SUM"}]

    # 筛选条件
    filters: Dict[str, Any]  # 筛选条件
    # filters示例：{
    #   "dimensions": [{"field": "地区", "operator": "=", "value": "北京"}],
    #   "measures": [{"field": "销售额", "operator": ">", "value": 1000}]
    # }

    # 时间范围
    time_range: Dict[str, Any]  # 时间范围
    # time_range示例：
    # 明确时间：{"type": "absolute", "start": "2016-01-01", "end": "2016-12-31"}
    # 相对时间：{"type": "relative", "relative": "LAST", "period": "MONTH", "count": 3}
    # 同比时间：{"type": "comparison", "current": {...}, "comparison": {"type": "year_over_year"}}

    # 排序和限制
    order_by: List[Dict[str, str]]  # 排序规则
    # order_by示例：[{"field": "销售额", "direction": "DESC", "priority": 1}]

    limit: Optional[Union[int, Dict[str, Any]]]  # TopN限制
    # limit示例：
    # 简单限制：10
    # 复杂限制：{"top": 10, "field_to_measure": "销售额", "direction": "DESC"}

    # 聚合和粒度
    grain: Optional[str]  # 时间粒度：日/周/月/季/年
    aggregation: str  # 聚合方式：SUM/AVG/COUNT/MIN/MAX

    # 元信息
    rationale: str  # 拆分理由
    depends_on: List[str]  # 依赖的任务ID
    stage: int  # 执行阶段
    priority: str  # 优先级：HIGH/MEDIUM/LOW
```

### DimensionHierarchy

```python
class DimensionHierarchy(TypedDict):
    """维度层级信息"""

    # 基础属性
    category: str  # 维度类别：地理、时间、产品、客户、组织、财务、其他
    category_detail: str  # 详细类别：地理-省级、时间-月等
    unique_count: int  # 唯一值数量
    sample_values: List[str]  # 示例值列表

    # 层级属性
    level: int  # 层级级别：1(粗粒度)、2(中粒度)、3(细粒度)
    granularity: str  # 粒度描述：粗粒度/中粒度/细粒度
    parent_dimension: Optional[str]  # 父维度
    child_dimension: Optional[str]  # 子维度

    # 质量属性
    level_confidence: float  # 置信度：0-1
    reasoning: str  # 推理过程
```

### SubTask

```python
class SubTask(TypedDict):
    """子任务"""

    question_id: str  # 任务ID
    question_text: str  # 任务描述
    spec: StructuredQuestionSpec  # 结构化规格
    stage: int  # 执行阶段
    depends_on: List[str]  # 依赖的任务ID
    priority: str  # 优先级
    rationale: str  # 拆分理由
    options: Dict[str, Any]  # 配置选项
```

### SubTaskResult

```python
class SubTaskResult(TypedDict):
    """子任务执行结果"""

    question_id: str  # 任务ID
    status: str  # 状态：completed/error/timeout
    query_result: Dict[str, Any]  # 查询结果
    # query_result示例：{
    #   "data": [...],  # 数据行列表
    #   "columns": [...],  # 列名列表
    #   "row_count": 100  # 行数
    # }

    statistics: Dict[str, Any]  # 统计报告
    insights: Dict[str, Any]  # 洞察结果
    error: Optional[str]  # 错误信息
    execution_time: float  # 执行时间（秒）
    task: SubTask  # 原始任务
```

---

## 性能优化策略

### 1. Token优化

#### 元数据精简

**问题**：完整元数据可能包含数百个字段，导致token消耗过大

**优化策略**：
- 只传递必要的字段信息（fieldCaption、dataType、defaultAggregation）
- 维度层级信息单独缓存，按需加载
- 字段描述和样例值只在需要时传递

**示例**：
```python
# 完整元数据（~10,000 tokens）
full_metadata = {
    "fields": [
        {
            "fieldCaption": "销售额",
            "dataType": "REAL",
            "defaultAggregation": "SUM",
            "description": "订单的销售金额，包含税费",
            "sample_values": [1000, 2000, 3000, ...],
            "statistics": {...}
        },
        # ... 200个字段
    ]
}

# 精简元数据（~2,000 tokens）
simplified_metadata = {
    "dimensions": ["地区", "产品类别", "门店"],
    "measures": [
        {"field": "销售额", "type": "REAL", "agg": "SUM"},
        {"field": "利润", "type": "REAL", "agg": "SUM"}
    ]
}
```

#### 数据采样

**问题**：查询结果可能包含数万行，无法全部传递给LLM

**优化策略**：
- 智能采样：保留关键行（最大值、最小值、异常值）
- 分层采样：按维度分层采样
- 统计摘要：传递统计信息而非原始数据

**示例**：
```python
def intelligent_sampling(df: pd.DataFrame, max_rows: int = 30) -> pd.DataFrame:
    """智能采样，保留关键行"""
    if len(df) <= max_rows:
        return df

    # 1. 保留Top 10和Bottom 10
    top_10 = df.nlargest(10, "销售额")
    bottom_10 = df.nsmallest(10, "销售额")

    # 2. 保留异常值（Z-score > 3）
    z_scores = np.abs((df["销售额"] - df["销售额"].mean()) / df["销售额"].std())
    outliers = df[z_scores > 3]

    # 3. 随机采样剩余行
    remaining = max_rows - len(top_10) - len(bottom_10) - len(outliers)
    random_sample = df.sample(n=remaining)

    # 合并
    sampled = pd.concat([top_10, bottom_10, outliers, random_sample]).drop_duplicates()

    return sampled
```

#### 摘要传递

**问题**：重规划Agent需要了解之前的分析结果，但不需要完整数据

**优化策略**：
- 只传递关键发现摘要（而非完整数据）
- 只传递统计报告（而非原始数据）
- 只传递异常列表（而非所有数据点）

**示例**：
```python
# 完整数据（~5,000 tokens）
full_data = {
    "data": [...],  # 1000行数据
    "statistics": {...},
    "insights": {...}
}

# 摘要（~500 tokens）
summary = {
    "key_findings": [
        "华东地区销售额最高，达到500万元",
        "西北地区利润率异常低，只有5%"
    ],
    "anomalies": [
        {"dimension": "西北地区", "metric": "利润率", "value": 0.05, "expected": 0.12}
    ],
    "statistics": {
        "total_sales": 2000000,
        "avg_profit_rate": 0.12
    }
}
```

### 2. 并行优化

#### 同Stage并行执行

**策略**：同stage内的子任务可以并行执行

**示例**：
```python
# 3个子任务，都在stage 1
tasks = [
    {"question_id": "q1", "stage": 1, "question": "2024年各地区的销售额"},
    {"question_id": "q2", "stage": 1, "question": "2023年各地区的销售额"},
    {"question_id": "q3", "stage": 1, "question": "总销售额"}
]

# 并行执行（使用ThreadPoolExecutor）
with ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(execute_task, task) for task in tasks]
    results = [future.result() for future in as_completed(futures)]
```

**性能提升**：
- 串行执行：3 × 5秒 = 15秒
- 并行执行：max(5秒, 5秒, 5秒) = 5秒
- 提升：3倍

#### 洞察Agent并行调用

**策略**：每个子任务的洞察Agent可以并行调用

**示例**：
```python
# 3个子任务的洞察Agent并行调用
with ThreadPoolExecutor(max_workers=3) as executor:
    futures = [
        executor.submit(insight_agent.invoke, task_result)
        for task_result in task_results
    ]
    insights = [future.result() for future in as_completed(futures)]
```

**性能提升**：
- 串行执行：3 × 2秒 = 6秒
- 并行执行：max(2秒, 2秒, 2秒) = 2秒
- 提升：3倍

### 3. 缓存优化

#### 多层缓存架构

```
┌─────────────────────────────────────────┐
│         应用层（Python）                 │
│  ┌─────────────────────────────────┐   │
│  │  内存缓存（LRU Cache）           │   │
│  │  - 最近使用的元数据              │   │
│  │  - 有效期：进程生命周期          │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│         Redis缓存层                      │
│  ┌─────────────────────────────────┐   │
│  │  元数据缓存（1小时）             │   │
│  │  维度层级缓存（24小时）          │   │
│  │  查询结果缓存（5分钟）           │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│         数据源层                         │
│  ┌─────────────────────────────────┐   │
│  │  Tableau Metadata API            │   │
│  │  Tableau VDS API                 │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

#### 缓存预热

**策略**：在系统启动时预加载常用数据源的元数据

**示例**：
```python
def warmup_cache():
    """缓存预热"""
    # 获取最近7天访问最多的10个数据源
    popular_datasources = get_popular_datasources(days=7, limit=10)

    # 预加载元数据和维度层级
    for datasource_luid in popular_datasources:
        metadata = get_metadata(datasource_luid)
        dimension_hierarchy = get_dimension_hierarchy(datasource_luid)

        # 写入缓存
        cache_metadata(datasource_luid, metadata)
        cache_dimension_hierarchy(datasource_luid, dimension_hierarchy)
```

### 4. 查询优化

#### 查询合并

**策略**：将多个相似的查询合并为一个查询

**示例**：
```python
# 原始：3个查询
query1 = {"dims": ["地区"], "metrics": [{"field": "销售额", "agg": "sum"}]}
query2 = {"dims": ["地区"], "metrics": [{"field": "利润", "agg": "sum"}]}
query3 = {"dims": ["地区"], "metrics": [{"field": "订单量", "agg": "count"}]}

# 合并：1个查询
merged_query = {
    "dims": ["地区"],
    "metrics": [
        {"field": "销售额", "agg": "sum"},
        {"field": "利润", "agg": "sum"},
        {"field": "订单量", "agg": "count"}
    ]
}
```

**性能提升**：
- 原始：3次API调用
- 合并：1次API调用
- 提升：3倍

#### 查询下推

**策略**：将筛选条件下推到VizQL查询中，减少数据传输

**示例**：
```python
# 不推荐：在Python中筛选
query = {"dims": ["地区"], "metrics": [{"field": "销售额", "agg": "sum"}]}
result = execute_query(query)
filtered = result[result["销售额"] > 1000]  # 在Python中筛选

# 推荐：在VizQL中筛选
query = {
    "dims": ["地区"],
    "metrics": [{"field": "销售额", "agg": "sum"}],
    "filters": [{"field": "销售额", "operator": ">", "value": 1000}]
}
result = execute_query(query)  # 在VDS中筛选
```

### 5. 失败处理优化

#### 智能重试

**策略**：只对可重试的错误重试，使用指数退避

**示例**：
```python
def execute_with_retry(func, max_retries=2):
    """智能重试"""
    for attempt in range(max_retries + 1):
        try:
            return func()
        except RetryableError as e:
            if attempt < max_retries:
                wait_time = 2 ** attempt  # 指数退避：2秒、4秒
                time.sleep(wait_time)
            else:
                raise
        except NonRetryableError as e:
            # 不可重试的错误，直接抛出
            raise
```

#### 降级策略

**策略**：当查询失败时，使用降级策略

**示例**：
```python
def execute_with_fallback(query):
    """带降级的查询执行"""
    try:
        # 尝试完整查询
        return execute_query(query)
    except QueryTooComplexError:
        # 降级1：减少维度
        simplified_query = simplify_query(query, reduce_dims=True)
        return execute_query(simplified_query)
    except QueryTimeoutError:
        # 降级2：使用采样数据
        sampled_query = add_sampling(query, sample_rate=0.1)
        return execute_query(sampled_query)
    except Exception as e:
        # 降级3：使用缓存结果（如果有）
        cached = get_cached_result(query)
        if cached:
            return cached
        else:
            raise
```

---

## 缓存架构

### Redis缓存策略

#### 1. 元数据缓存

**缓存key**: `metadata:{datasource_luid}`
**有效期**: 1小时
**内容**: 数据源的字段列表、类型、描述

**缓存逻辑**：
```python
def get_metadata(datasource_luid: str) -> Dict:
    cache_key = f"metadata:{datasource_luid}"

    # 尝试从缓存获取
    cached = redis.get(cache_key)
    if cached:
        return json.loads(cached)

    # 缓存未命中，调用API获取
    metadata = fetch_metadata_from_tableau(datasource_luid)

    # 写入缓存
    redis.setex(cache_key, 3600, json.dumps(metadata))

    return metadata
```

#### 2. 维度层级缓存

**缓存key**: `dimension_hierarchy:{datasource_luid}`
**有效期**: 24小时
**内容**: 维度的层级信息（category、level、granularity等）

**缓存逻辑**：
```python
def get_dimension_hierarchy(datasource_luid: str) -> Dict:
    cache_key = f"dimension_hierarchy:{datasource_luid}"

    # 尝试从缓存获取
    cached = redis.get(cache_key)
    if cached:
        return json.loads(cached)

    # 缓存未命中，调用维度层级推断Agent
    hierarchy = infer_dimension_hierarchy(datasource_luid)

    # 写入缓存
    redis.setex(cache_key, 86400, json.dumps(hierarchy))

    return hierarchy
```

#### 3. 查询结果缓存

**缓存key**: `query_result:{query_fingerprint}`
**有效期**: 5分钟
**内容**: VizQL查询的结果

**查询指纹计算**：
```python
def calculate_query_fingerprint(query: Dict) -> str:
    """计算查询指纹（用于缓存key）"""
    # 提取关键字段
    key_fields = {
        "datasource_luid": query.get("datasource_luid"),
        "fields": sorted(query.get("fields", [])),
        "filters": sorted(query.get("filters", [])),
        "order_by": query.get("order_by")
    }

    # 计算MD5
    import hashlib
    fingerprint = hashlib.md5(
        json.dumps(key_fields, sort_keys=True).encode()
    ).hexdigest()

    return fingerprint
```

**缓存逻辑**：
```python
def execute_query_with_cache(query: Dict) -> Dict:
    fingerprint = calculate_query_fingerprint(query)
    cache_key = f"query_result:{fingerprint}"

    # 尝试从缓存获取
    cached = redis.get(cache_key)
    if cached:
        return json.loads(cached)

    # 缓存未命中，执行查询
    result = execute_vizql_query(query)

    # 写入缓存（5分钟）
    redis.setex(cache_key, 300, json.dumps(result))

    return result
```

---



---

## 数据采样策略

### 1. 采样场景

#### 场景1：洞察Agent输入

**问题**：查询结果可能包含数万行，无法全部传递给LLM

**采样策略**：智能采样，保留关键行

**采样规则**：
- 最多保留30行
- 保留Top 10和Bottom 10（按主要度量排序）
- 保留异常值（Z-score > 3）
- 随机采样剩余行

**示例**：
```python
def sample_for_insight(df: pd.DataFrame, metric: str = "销售额") -> pd.DataFrame:
    """为洞察Agent采样数据"""
    if len(df) <= 30:
        return df

    # 1. Top 10
    top_10 = df.nlargest(10, metric)

    # 2. Bottom 10
    bottom_10 = df.nsmallest(10, metric)

    # 3. 异常值
    z_scores = np.abs((df[metric] - df[metric].mean()) / df[metric].std())
    outliers = df[z_scores > 3]

    # 4. 随机采样
    remaining = 30 - len(top_10) - len(bottom_10) - len(outliers)
    if remaining > 0:
        random_sample = df.sample(n=min(remaining, len(df)))
    else:
        random_sample = pd.DataFrame()

    # 合并
    sampled = pd.concat([top_10, bottom_10, outliers, random_sample]).drop_duplicates()

    return sampled.head(30)
```

#### 场景2：重规划Agent输入

**问题**：重规划Agent需要了解之前的分析结果，但不需要完整数据

**采样策略**：只传递摘要信息

**采样规则**：
- 只传递关键发现（最多5条）
- 只传递异常列表（最多3条）
- 只传递统计摘要（均值、中位数、标准差）

**示例**：
```python
def summarize_for_replanner(results: List[Dict]) -> Dict:
    """为重规划Agent生成摘要"""
    summary = {
        "key_findings": [],
        "anomalies": [],
        "statistics": {}
    }

    for result in results:
        # 提取关键发现（最多5条）
        findings = result.get("insights", {}).get("key_findings", [])
        summary["key_findings"].extend(findings[:5])

        # 提取异常（最多3条）
        anomalies = result.get("insights", {}).get("anomalies", [])
        summary["anomalies"].extend(anomalies[:3])

        # 提取统计摘要
        stats = result.get("statistics", {})
        summary["statistics"][result["question_id"]] = {
            "mean": stats.get("mean"),
            "median": stats.get("median"),
            "std": stats.get("std")
        }

    return summary
```

#### 场景3：总结Agent输入

**问题**：总结Agent需要整合所有结果，但不需要完整数据

**采样策略**：只传递去重后的关键发现

**采样规则**：
- 去重关键发现（基于相似度）
- 按重要性排序
- 最多保留10条

**示例**：
```python
def deduplicate_findings(findings: List[Dict]) -> List[Dict]:
    """去重关键发现"""
    # 1. 计算相似度矩阵
    similarity_matrix = compute_similarity_matrix(findings)

    # 2. 去重（相似度 > 0.8的合并）
    deduplicated = []
    used = set()

    for i, finding in enumerate(findings):
        if i in used:
            continue

        # 找到相似的发现
        similar_indices = [j for j in range(len(findings)) if similarity_matrix[i][j] > 0.8]

        # 合并相似的发现
        merged_finding = merge_findings([findings[j] for j in similar_indices])
        deduplicated.append(merged_finding)

        # 标记为已使用
        used.update(similar_indices)

    # 3. 按重要性排序
    deduplicated.sort(key=lambda x: x.get("importance", 0), reverse=True)

    # 4. 最多保留10条
    return deduplicated[:10]
```

### 2. 采样质量评估

#### 评估指标

1. **覆盖率** - 采样数据是否覆盖了原始数据的主要特征
2. **代表性** - 采样数据是否能代表原始数据的分布
3. **信息损失** - 采样后损失了多少信息

#### 评估方法

```python
def evaluate_sampling_quality(original_df: pd.DataFrame, sampled_df: pd.DataFrame) -> Dict:
    """评估采样质量"""
    metrics = {}

    # 1. 覆盖率（采样数据覆盖的值域范围）
    original_range = original_df["销售额"].max() - original_df["销售额"].min()
    sampled_range = sampled_df["销售额"].max() - sampled_df["销售额"].min()
    metrics["coverage"] = sampled_range / original_range

    # 2. 代表性（采样数据的均值和中位数与原始数据的差异）
    mean_diff = abs(sampled_df["销售额"].mean() - original_df["销售额"].mean())
    median_diff = abs(sampled_df["销售额"].median() - original_df["销售额"].median())
    metrics["representativeness"] = 1 - (mean_diff + median_diff) / (original_df["销售额"].mean() + original_df["销售额"].median())

    # 3. 信息损失（采样后损失的行数占比）
    metrics["information_loss"] = 1 - len(sampled_df) / len(original_df)

    return metrics
```

### 3. 自适应采样

#### 策略

根据数据特征动态调整采样策略：
- 数据分布均匀 → 随机采样
- 数据分布不均匀 → 分层采样
- 存在明显异常值 → 保留异常值

#### 实现

```python
def adaptive_sampling(df: pd.DataFrame, max_rows: int = 30) -> pd.DataFrame:
    """自适应采样"""
    if len(df) <= max_rows:
        return df

    # 1. 评估数据分布
    skewness = df["销售额"].skew()
    kurtosis = df["销售额"].kurtosis()

    # 2. 选择采样策略
    if abs(skewness) < 0.5 and abs(kurtosis) < 3:
        # 数据分布均匀 → 随机采样
        return df.sample(n=max_rows)
    elif abs(skewness) >= 0.5:
        # 数据分布不均匀 → 分层采样
        return stratified_sampling(df, max_rows)
    else:
        # 存在明显异常值 → 智能采样
        return intelligent_sampling(df, max_rows)
```

---

## 错误处理策略

### 1. 错误分类

#### 可重试错误

- **网络错误** - 连接超时、连接重置
- **临时错误** - 服务暂时不可用、限流
- **超时错误** - 查询超时

**处理策略**：指数退避重试（最多2次）

#### 不可重试错误

- **认证错误** - 认证失败、权限不足
- **参数错误** - 查询参数错误、数据源不存在
- **业务错误** - 数据源已删除、字段不存在

**处理策略**：直接返回错误，不重试

### 2. 错误恢复

#### 降级策略

```python
def execute_with_fallback(query: Dict) -> Dict:
    """带降级的查询执行"""
    try:
        # 尝试完整查询
        return execute_query(query)
    except QueryTooComplexError:
        # 降级1：减少维度
        logger.warning("查询过于复杂，尝试减少维度")
        simplified_query = reduce_dimensions(query)
        return execute_query(simplified_query)
    except QueryTimeoutError:
        # 降级2：使用采样数据
        logger.warning("查询超时，尝试使用采样数据")
        sampled_query = add_sampling(query, sample_rate=0.1)
        return execute_query(sampled_query)
    except Exception as e:
        # 降级3：使用缓存结果
        logger.error(f"查询失败: {e}，尝试使用缓存")
        cached = get_cached_result(query)
        if cached:
            return cached
        else:
            raise
```

#### 部分失败处理

```python
def execute_all_tasks(tasks: List[Dict]) -> List[Dict]:
    """执行所有任务，部分失败不影响整体"""
    results = []

    for task in tasks:
        try:
            result = execute_task(task)
            results.append(result)
        except Exception as e:
            logger.error(f"任务 {task['question_id']} 失败: {e}")
            # 记录失败，但继续执行其他任务
            results.append({
                "question_id": task["question_id"],
                "status": "error",
                "error": str(e)
            })

    return results
```

### 3. 错误日志

#### 日志级别

- **DEBUG** - 调试信息（查询参数、中间结果）
- **INFO** - 正常信息（任务开始、任务完成）
- **WARNING** - 警告信息（降级策略、缓存未命中）
- **ERROR** - 错误信息（查询失败、重试失败）
- **CRITICAL** - 严重错误（系统崩溃、数据丢失）

#### 日志格式

```python
import logging

# 配置日志格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# 记录日志
logger.info(f"开始执行任务: {task_id}")
logger.warning(f"缓存未命中: {cache_key}")
logger.error(f"查询失败: {error_message}", exc_info=True)
```

---

## 监控和告警

### 1. 监控指标

#### 系统指标

- **CPU使用率** - 当前CPU使用率
- **内存使用率** - 当前内存使用率
- **磁盘使用率** - 当前磁盘使用率
- **网络流量** - 入站/出站流量

#### 应用指标

- **请求数** - 每秒请求数（QPS）
- **响应时间** - 平均响应时间、P95响应时间、P99响应时间
- **错误率** - 错误请求占比
- **缓存命中率** - 缓存命中次数 / 总请求次数

#### 业务指标

- **LLM调用次数** - 每个Agent的调用次数
- **Token消耗** - 每个Agent的token消耗
- **查询成功率** - 查询成功次数 / 总查询次数
- **重规划率** - 重规划次数 / 总查询次数

### 2. 告警规则

#### 系统告警

- **CPU使用率 > 80%** - 警告
- **内存使用率 > 80%** - 警告
- **磁盘使用率 > 90%** - 严重

#### 应用告警

- **错误率 > 5%** - 警告
- **错误率 > 10%** - 严重
- **P95响应时间 > 30秒** - 警告
- **缓存命中率 < 80%** - 警告

#### 业务告警

- **查询成功率 < 95%** - 警告
- **查询成功率 < 90%** - 严重
- **单次token消耗 > 10,000** - 警告

### 3. 监控实现

#### Prometheus + Grafana

```python
from prometheus_client import Counter, Histogram, Gauge

# 定义指标
request_count = Counter('request_count', 'Total request count', ['agent', 'status'])
response_time = Histogram('response_time', 'Response time in seconds', ['agent'])
token_usage = Gauge('token_usage', 'Token usage', ['agent'])

# 记录指标
def execute_agent(agent_name: str, func):
    """执行Agent并记录指标"""
    start_time = time.time()

    try:
        result = func()
        request_count.labels(agent=agent_name, status='success').inc()
        return result
    except Exception as e:
        request_count.labels(agent=agent_name, status='error').inc()
        raise
    finally:
        elapsed_time = time.time() - start_time
        response_time.labels(agent=agent_name).observe(elapsed_time)
```

---

**文档版本**: v1.0
**最后更新**: 2025-10-30
