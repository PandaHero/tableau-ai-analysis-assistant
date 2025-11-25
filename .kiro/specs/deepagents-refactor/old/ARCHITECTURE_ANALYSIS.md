# 架构深度分析

## 📋 问题清单

1. **异步并行执行**：如何实现各代理与工具之间的异步并行 or 顺序执行？
2. **上下文管理阈值**：170k tokens 应该按照不同的模型来设置吧？
3. **缓存机制**：其他模型（Qwen、DeepSeek）就没有缓存了吗？
4. **thread_id 设置规则**：能避免冲突吗？
5. **语义字段映射的位置**：属于任务规划代理做的一部分事情，当前的数据模型和模板设计有什么问题？

---

## 1. 异步并行执行架构

### 当前系统的执行模式

通过分析代码，当前系统有以下执行模式：

```python
# 当前的执行流程（LangGraph）
understanding → planning → query_execution → insight → replanner → summarizer
```

### DeepAgents 的异步并行能力

DeepAgents 基于 LangGraph，支持以下并行模式：

#### 1.1 子代理并行（SubAgent Parallelism）

```python
# DeepAgents 自动支持
# 当多个 task() 调用没有依赖关系时，自动并行执行

# 示例：并行执行多个独立的子查询
async def main_agent_flow():
    # Planning Agent 生成查询计划
    query_plan = await task("planning-agent", understanding)
    
    # 并行执行所有独立的子查询
    query_results = await asyncio.gather(*[
        vizql_query(subtask.query, datasource_luid)
        for subtask in query_plan.subtasks
        if subtask.task_type == "query" and not subtask.depends_on
    ])
```

#### 1.2 工具并行（Tool Parallelism）

```python
# 工具调用也可以并行
# 示例：并行获取多个数据源的元数据
metadata_results = await asyncio.gather(*[
    get_metadata(datasource_luid_1),
    get_metadata(datasource_luid_2),
    get_metadata(datasource_luid_3)
])
```

#### 1.3 流水线并行（Pipeline Parallelism）

```python
# 查询执行和洞察分析的流水线并行
# 当第一个查询结果返回时，立即开始分析，同时继续执行其他查询

async def pipeline_execution(query_plan):
    results = []
    insights = []
    
    # 创建查询任务
    query_tasks = [
        vizql_query(subtask.query, datasource_luid)
        for subtask in query_plan.subtasks
        if subtask.task_type == "query"
    ]
    
    # 流水线执行：查询完成后立即分析
    for query_task in asyncio.as_completed(query_tasks):
        result = await query_task
        results.append(result)
        
        # 立即开始分析（不等待其他查询）
        insight_task = task("insight-agent", result)
        insights.append(await insight_task)
    
    return results, insights
```

### 建议的执行策略

```python
class ExecutionStrategy(Enum):
    """执行策略"""
    SEQUENTIAL = "sequential"      # 顺序执行
    PARALLEL = "parallel"          # 并行执行
    PIPELINE = "pipeline"          # 流水线执行
    ADAPTIVE = "adaptive"          # 自适应（根据依赖关系自动选择）


class TaskExecutor:
    """任务执行器"""
    
    def __init__(self, strategy: ExecutionStrategy = ExecutionStrategy.ADAPTIVE):
        self.strategy = strategy
    
    async def execute(self, query_plan: QueryPlanningResult):
        """根据策略执行任务"""
        
        if self.strategy == ExecutionStrategy.ADAPTIVE:
            # 自动分析依赖关系
            return await self._adaptive_execute(query_plan)
        elif self.strategy == ExecutionStrategy.PARALLEL:
            # 强制并行（忽略依赖）
            return await self._parallel_execute(query_plan)
        elif self.strategy == ExecutionStrategy.PIPELINE:
            # 流水线执行
            return await self._pipeline_execute(query_plan)
        else:
            # 顺序执行
            return await self._sequential_execute(query_plan)
    
    async def _adaptive_execute(self, query_plan):
        """自适应执行：根据依赖关系自动选择"""
        # 1. 构建依赖图
        dependency_graph = self._build_dependency_graph(query_plan)
        
        # 2. 拓扑排序，得到执行阶段
        stages = self._topological_sort(dependency_graph)
        
        # 3. 每个阶段内并行执行，阶段间顺序执行
        results = {}
        for stage in stages:
            # 并行执行同一阶段的所有任务
            stage_results = await asyncio.gather(*[
                self._execute_task(task, results)
                for task in stage
            ])
            
            # 保存结果
            for task, result in zip(stage, stage_results):
                results[task.question_id] = result
        
        return results
```



---

## 2. 上下文管理阈值（按模型配置）

### 问题分析

您说得对！170k tokens 是 Claude 3.5 Sonnet 的上下文窗口，不同模型有不同的限制。

### 各模型的上下文窗口

| 模型 | 上下文窗口 | 建议阈值（80%） |
|------|-----------|----------------|
| **Claude 3.5 Sonnet** | 200k tokens | 160k tokens |
| **Claude 3 Opus** | 200k tokens | 160k tokens |
| **GPT-4 Turbo** | 128k tokens | 102k tokens |
| **GPT-4o** | 128k tokens | 102k tokens |
| **GPT-4o-mini** | 128k tokens | 102k tokens |
| **Qwen-Max** | 32k tokens | 25k tokens |
| **Qwen-Plus** | 32k tokens | 25k tokens |
| **DeepSeek-V3** | 64k tokens | 51k tokens |
| **DeepSeek-Chat** | 64k tokens | 51k tokens |

### 建议的配置方案

```python
# 模型配置
MODEL_CONFIGS = {
    # Anthropic Claude
    "claude-3-5-sonnet-20241022": {
        "context_window": 200000,
        "summarization_threshold": 160000,  # 80%
        "supports_prompt_caching": True,
        "cache_ttl": 300  # 5 minutes
    },
    "claude-3-opus-20240229": {
        "context_window": 200000,
        "summarization_threshold": 160000,
        "supports_prompt_caching": True,
        "cache_ttl": 300
    },
    
    # OpenAI GPT-4
    "gpt-4-turbo": {
        "context_window": 128000,
        "summarization_threshold": 102400,  # 80%
        "supports_prompt_caching": False,
        "cache_ttl": 0
    },
    "gpt-4o": {
        "context_window": 128000,
        "summarization_threshold": 102400,
        "supports_prompt_caching": False,
        "cache_ttl": 0
    },
    "gpt-4o-mini": {
        "context_window": 128000,
        "summarization_threshold": 102400,
        "supports_prompt_caching": False,
        "cache_ttl": 0
    },
    
    # Qwen
    "qwen-max": {
        "context_window": 32000,
        "summarization_threshold": 25600,  # 80%
        "supports_prompt_caching": False,
        "cache_ttl": 0
    },
    "qwen-plus": {
        "context_window": 32000,
        "summarization_threshold": 25600,
        "supports_prompt_caching": False,
        "cache_ttl": 0
    },
    
    # DeepSeek
    "deepseek-chat": {
        "context_window": 64000,
        "summarization_threshold": 51200,  # 80%
        "supports_prompt_caching": False,
        "cache_ttl": 0
    },
    "deepseek-v3": {
        "context_window": 64000,
        "summarization_threshold": 51200,
        "supports_prompt_caching": False,
        "cache_ttl": 0
    }
}


class ContextManager:
    """上下文管理器"""
    
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.config = MODEL_CONFIGS.get(model_name, {
            "context_window": 32000,  # 默认值
            "summarization_threshold": 25600,
            "supports_prompt_caching": False,
            "cache_ttl": 0
        })
    
    def should_summarize(self, current_tokens: int) -> bool:
        """判断是否需要总结"""
        return current_tokens > self.config["summarization_threshold"]
    
    def get_max_tokens(self) -> int:
        """获取最大 token 数"""
        return self.config["context_window"]
    
    def supports_caching(self) -> bool:
        """是否支持缓存"""
        return self.config["supports_prompt_caching"]
```

### 动态中间件配置

```python
def create_deep_agent(model_name: str):
    """创建 DeepAgent，根据模型动态配置中间件"""
    
    context_manager = ContextManager(model_name)
    
    middlewares = [
        TodoListMiddleware(),
        FilesystemMiddleware(),
        SubAgentMiddleware(),
    ]
    
    # 根据模型配置添加 SummarizationMiddleware
    if context_manager.get_max_tokens() > 0:
        middlewares.append(
            SummarizationMiddleware(
                threshold=context_manager.config["summarization_threshold"]
            )
        )
    
    # 根据模型配置添加 PromptCachingMiddleware
    if context_manager.supports_caching():
        if "claude" in model_name.lower():
            middlewares.append(AnthropicPromptCachingMiddleware())
        # 未来可以添加其他模型的缓存中间件
        # elif "gpt" in model_name.lower():
        #     middlewares.append(OpenAIPromptCachingMiddleware())
    
    # 创建 Agent
    agent = create_deep_agent(
        model=model_name,
        middlewares=middlewares,
        ...
    )
    
    return agent
```

---

## 3. 缓存机制（多模型支持）

### 问题分析

您说得对！不是只有 Anthropic 支持缓存，其他模型也有类似机制。

### 各模型的缓存机制

| 模型 | 缓存机制 | 说明 |
|------|---------|------|
| **Anthropic Claude** | Prompt Caching | 官方支持，缓存系统提示词 |
| **OpenAI GPT-4** | 无官方缓存 | 但可以使用应用层缓存 |
| **Qwen** | 无官方缓存 | 但可以使用应用层缓存 |
| **DeepSeek** | 无官方缓存 | 但可以使用应用层缓存 |

### 建议的缓存策略

#### 3.1 Anthropic Prompt Caching（官方）

```python
# 已有的 AnthropicPromptCachingMiddleware
# 自动缓存系统提示词，节省 50-90% 成本
```

#### 3.2 应用层缓存（通用）

```python
class ApplicationLevelCacheMiddleware:
    """应用层缓存中间件（适用于所有模型）"""
    
    def __init__(self, cache_backend: str = "redis"):
        self.cache = self._init_cache(cache_backend)
    
    def _init_cache(self, backend: str):
        """初始化缓存后端"""
        if backend == "redis":
            import redis
            return redis.Redis(host='localhost', port=6379, db=0)
        elif backend == "memory":
            return {}
        else:
            raise ValueError(f"Unknown cache backend: {backend}")
    
    async def __call__(self, state, next_middleware):
        """缓存 LLM 响应"""
        
        # 1. 生成缓存 key
        cache_key = self._generate_cache_key(state)
        
        # 2. 检查缓存
        cached_response = self.cache.get(cache_key)
        if cached_response:
            # 缓存命中
            state["llm_response"] = cached_response
            return state
        
        # 3. 缓存未命中，调用 LLM
        state = await next_middleware(state)
        
        # 4. 保存到缓存
        self.cache.set(
            cache_key,
            state["llm_response"],
            ex=3600  # 1 小时过期
        )
        
        return state
    
    def _generate_cache_key(self, state):
        """生成缓存 key"""
        import hashlib
        
        # 使用系统提示词 + 用户输入生成 key
        content = f"{state['system_prompt']}:{state['user_input']}"
        return hashlib.sha256(content.encode()).hexdigest()
```

#### 3.3 语义缓存（Semantic Caching）

```python
class SemanticCacheMiddleware:
    """语义缓存中间件（基于向量相似度）"""
    
    def __init__(self, embeddings, vector_store, similarity_threshold=0.95):
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.similarity_threshold = similarity_threshold
    
    async def __call__(self, state, next_middleware):
        """基于语义相似度的缓存"""
        
        # 1. 向量化用户输入
        user_input = state["user_input"]
        query_vector = self.embeddings.embed_query(user_input)
        
        # 2. 搜索相似的历史查询
        similar_queries = self.vector_store.similarity_search_with_score(
            query_vector,
            k=1
        )
        
        # 3. 如果相似度足够高，返回缓存结果
        if similar_queries and similar_queries[0][1] >= self.similarity_threshold:
            cached_query, score = similar_queries[0]
            state["llm_response"] = cached_query.metadata["response"]
            state["cache_hit"] = True
            state["cache_similarity"] = score
            return state
        
        # 4. 缓存未命中，调用 LLM
        state = await next_middleware(state)
        
        # 5. 保存到向量存储
        self.vector_store.add_texts(
            texts=[user_input],
            metadatas=[{"response": state["llm_response"]}]
        )
        
        return state
```

### 推荐的缓存组合

```python
def create_caching_middlewares(model_name: str):
    """根据模型创建缓存中间件"""
    
    middlewares = []
    
    # 1. Anthropic 官方缓存
    if "claude" in model_name.lower():
        middlewares.append(AnthropicPromptCachingMiddleware())
    
    # 2. 应用层缓存（所有模型）
    middlewares.append(ApplicationLevelCacheMiddleware(cache_backend="redis"))
    
    # 3. 语义缓存（可选，用于相似问题）
    middlewares.append(SemanticCacheMiddleware(
        embeddings=embeddings,
        vector_store=vector_store,
        similarity_threshold=0.95
    ))
    
    return middlewares
```



---

## 4. thread_id 设置规则

### 问题分析

thread_id 是 LangGraph 用于隔离不同会话的关键标识符。需要确保：
1. **唯一性**：不同用户/会话的 thread_id 不能冲突
2. **可追溯性**：能够追溯到具体的用户和会话
3. **安全性**：不能被猜测或伪造

### 推荐的 thread_id 生成策略

#### 4.1 UUID 方案（推荐）

```python
import uuid
from datetime import datetime

def generate_thread_id(user_id: Optional[str] = None) -> str:
    """
    生成 thread_id
    
    格式：{user_id}_{timestamp}_{uuid}
    示例：user123_20240315_a1b2c3d4-e5f6-7890-abcd-ef1234567890
    """
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    unique_id = str(uuid.uuid4())
    
    if user_id:
        return f"{user_id}_{timestamp}_{unique_id}"
    else:
        return f"anonymous_{timestamp}_{unique_id}"


# 使用示例
thread_id = generate_thread_id(user_id="user123")
# 输出：user123_20240315143022_a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**优点**：
- ✅ UUID 保证全局唯一性
- ✅ 包含时间戳，便于追溯
- ✅ 包含用户 ID，便于管理
- ✅ 无法被猜测

#### 4.2 雪花算法（Snowflake）方案

```python
import time
import threading

class SnowflakeIDGenerator:
    """雪花算法 ID 生成器"""
    
    def __init__(self, datacenter_id: int = 0, worker_id: int = 0):
        self.datacenter_id = datacenter_id
        self.worker_id = worker_id
        self.sequence = 0
        self.last_timestamp = -1
        self.lock = threading.Lock()
        
        # 时间戳起始点（2024-01-01 00:00:00）
        self.epoch = 1704067200000
    
    def generate(self) -> str:
        """生成唯一 ID"""
        with self.lock:
            timestamp = int(time.time() * 1000)
            
            if timestamp < self.last_timestamp:
                raise Exception("Clock moved backwards!")
            
            if timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & 0xFFF
                if self.sequence == 0:
                    # 序列号用完，等待下一毫秒
                    while timestamp <= self.last_timestamp:
                        timestamp = int(time.time() * 1000)
            else:
                self.sequence = 0
            
            self.last_timestamp = timestamp
            
            # 组装 ID
            id_value = (
                ((timestamp - self.epoch) << 22) |
                (self.datacenter_id << 17) |
                (self.worker_id << 12) |
                self.sequence
            )
            
            return str(id_value)


# 使用示例
id_generator = SnowflakeIDGenerator(datacenter_id=1, worker_id=1)
thread_id = f"thread_{id_generator.generate()}"
# 输出：thread_1234567890123456789
```

**优点**：
- ✅ 高性能（每毫秒可生成 4096 个 ID）
- ✅ 趋势递增（便于数据库索引）
- ✅ 包含时间戳信息
- ✅ 分布式友好

#### 4.3 Redis 自增方案

```python
import redis

class RedisThreadIDGenerator:
    """基于 Redis 的 thread_id 生成器"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
    
    def generate(self, user_id: Optional[str] = None) -> str:
        """生成 thread_id"""
        # 1. 获取自增 ID
        counter = self.redis.incr("thread_id_counter")
        
        # 2. 生成 thread_id
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        
        if user_id:
            thread_id = f"{user_id}_{timestamp}_{counter:010d}"
        else:
            thread_id = f"anonymous_{timestamp}_{counter:010d}"
        
        # 3. 保存到 Redis（用于验证）
        self.redis.setex(
            f"thread:{thread_id}",
            3600,  # 1 小时过期
            user_id or "anonymous"
        )
        
        return thread_id


# 使用示例
redis_client = redis.Redis(host='localhost', port=6379, db=0)
id_generator = RedisThreadIDGenerator(redis_client)
thread_id = id_generator.generate(user_id="user123")
# 输出：user123_20240315143022_0000000001
```

**优点**：
- ✅ 简单可靠
- ✅ 分布式友好
- ✅ 可以验证 thread_id 的有效性

### 推荐方案

**生产环境推荐**：UUID 方案 + Redis 验证

```python
class ThreadIDManager:
    """thread_id 管理器"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
    
    def create_thread(self, user_id: Optional[str] = None) -> str:
        """创建新会话"""
        # 1. 生成 thread_id
        thread_id = generate_thread_id(user_id)
        
        # 2. 保存到 Redis
        self.redis.setex(
            f"thread:{thread_id}",
            3600,  # 1 小时过期
            json.dumps({
                "user_id": user_id or "anonymous",
                "created_at": datetime.now().isoformat(),
                "status": "active"
            })
        )
        
        return thread_id
    
    def validate_thread(self, thread_id: str) -> bool:
        """验证 thread_id 是否有效"""
        return self.redis.exists(f"thread:{thread_id}")
    
    def get_thread_info(self, thread_id: str) -> Optional[dict]:
        """获取会话信息"""
        data = self.redis.get(f"thread:{thread_id}")
        if data:
            return json.loads(data)
        return None
    
    def close_thread(self, thread_id: str):
        """关闭会话"""
        self.redis.delete(f"thread:{thread_id}")
```

### API 集成

```python
from fastapi import FastAPI, HTTPException, Header

app = FastAPI()
thread_manager = ThreadIDManager(redis_client)

@app.post("/api/chat")
async def chat(
    question: str,
    user_id: Optional[str] = None,
    thread_id: Optional[str] = Header(None, alias="X-Thread-ID")
):
    """聊天接口"""
    
    # 1. 如果没有 thread_id，创建新会话
    if not thread_id:
        thread_id = thread_manager.create_thread(user_id)
    else:
        # 验证 thread_id
        if not thread_manager.validate_thread(thread_id):
            raise HTTPException(status_code=400, detail="Invalid thread_id")
    
    # 2. 使用 thread_id 执行查询
    result = await execute_query(question, thread_id)
    
    # 3. 返回结果（包含 thread_id）
    return {
        "thread_id": thread_id,
        "result": result
    }
```



---

## 5. 语义字段映射的位置和数据模型设计

### 当前设计分析

通过分析代码，我发现了当前设计的**核心问题**：

#### 5.1 当前的数据流

```
用户问题
  ↓
Understanding Agent
  ├─ 输出：QuestionUnderstanding
  │   ├─ mentioned_dimensions: ["销售额", "地区"]  # 业务术语
  │   ├─ mentioned_measures: ["利润"]
  │   └─ mentioned_date_fields: ["订单日期"]
  ↓
Planning Agent (Task Planner)
  ├─ 输入：QuestionUnderstanding
  ├─ 任务：
  │   1. 字段映射（业务术语 → 技术字段）
  │   2. 生成 Intent 模型
  ├─ 输出：QueryPlanningResult
  │   └─ subtasks: [QuerySubTask]
  │       ├─ dimension_intents: [DimensionIntent]
  │       │   ├─ business_term: "地区"
  │       │   └─ technical_field: "[Geography].[Region]"  # 已映射
  │       ├─ measure_intents: [MeasureIntent]
  │       │   ├─ business_term: "销售额"
  │       │   └─ technical_field: "[Sales].[Sales Amount]"  # 已映射
  │       └─ date_field_intents: [DateFieldIntent]
  │           ├─ business_term: "订单日期"
  │           └─ technical_field: "[Orders].[Order Date]"  # 已映射
  ↓
Query Builder
  ├─ 输入：QuerySubTask（Intent 模型）
  ├─ 任务：Intent → VizQL
  └─ 输出：VizQL Query
```

#### 5.2 问题所在

**问题 1：Planning Agent 的职责过重**

```python
# Task Planner Prompt 中的字段映射逻辑
"""
Step 1: For each business term, find technical field from metadata
- Review available fields: Examine metadata.fields list carefully
- Identify semantic match: Find field with matching business meaning
  * Match category first: Which category does this term belong to?
  * Then match name: Search for fields within that category by name similarity
- Verify field existence: CRITICAL - technical_field MUST be exact name from metadata.fields
"""
```

这段提示词要求 Planning Agent 做：
1. 理解业务术语的语义
2. 从元数据中搜索候选字段
3. 匹配类别
4. 匹配名称
5. 验证字段存在性

**这些都是语义字段映射应该做的事情！**

**问题 2：没有利用 RAG + LLM 的优势**

当前的字段映射完全依赖 LLM 的"记忆"和"推理"，没有：
- ❌ 向量检索（快速筛选候选字段）
- ❌ 语义理解（理解同义词、多语言）
- ❌ 置信度评估（判断映射质量）
- ❌ 历史学习（保存用户确认的映射）

**问题 3：数据模型设计不合理**

```python
# Intent 模型中已经包含了映射后的字段
class DimensionIntent(BaseModel):
    business_term: str  # 业务术语
    technical_field: str  # 技术字段（已映射）
    ...
```

这意味着：
- Planning Agent 必须完成字段映射
- 无法在映射阶段插入 RAG + LLM
- 无法提供置信度和候选字段

### 建议的改进方案

#### 5.3 新的数据流

```
用户问题
  ↓
Understanding Agent
  ├─ 输出：QuestionUnderstanding
  │   ├─ mentioned_dimensions: ["销售额", "地区"]  # 业务术语
  │   ├─ mentioned_measures: ["利润"]
  │   └─ mentioned_date_fields: ["订单日期"]
  ↓
Semantic Field Mapping (新增工具)  ⭐
  ├─ 输入：业务术语列表 + 元数据
  ├─ 任务：
  │   1. 向量检索候选字段
  │   2. LLM 语义判断
  │   3. 置信度评估
  ├─ 输出：FieldMappingResult
  │   └─ mappings: [FieldMapping]
  │       ├─ business_term: "销售额"
  │       ├─ technical_field: "[Sales].[Sales Amount]"
  │       ├─ confidence: 0.95
  │       ├─ alternatives: [...]
  │       └─ reasoning: "..."
  ↓
Planning Agent (Task Planner)
  ├─ 输入：QuestionUnderstanding + FieldMappingResult
  ├─ 任务：
  │   1. 使用映射结果生成 Intent 模型
  │   2. 识别查询细节（排序、TopN、过滤）
  ├─ 输出：QueryPlanningResult
  │   └─ subtasks: [QuerySubTask]
  │       ├─ dimension_intents: [DimensionIntent]
  │       │   ├─ business_term: "地区"
  │       │   ├─ technical_field: "[Geography].[Region]"  # 来自映射结果
  │       │   └─ mapping_confidence: 0.95  # 新增字段
  │       └─ ...
  ↓
Query Builder
  ├─ 输入：QuerySubTask（Intent 模型）
  ├─ 任务：Intent → VizQL
  └─ 输出：VizQL Query
```

#### 5.4 新的数据模型

```python
# ============= 字段映射结果模型 =============

class FieldMapping(BaseModel):
    """单个字段的映射结果"""
    
    business_term: str = Field(
        description="业务术语"
    )
    
    technical_field: str = Field(
        description="技术字段名（从元数据中）"
    )
    
    field_role: Literal["dimension", "measure", "date"] = Field(
        description="字段角色"
    )
    
    field_data_type: str = Field(
        description="字段数据类型"
    )
    
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="映射置信度（0-1）"
    )
    
    alternatives: List[dict] = Field(
        default_factory=list,
        description="备选字段列表"
    )
    
    reasoning: str = Field(
        description="映射推理过程"
    )


class FieldMappingResult(BaseModel):
    """字段映射结果"""
    
    mappings: List[FieldMapping] = Field(
        description="所有字段的映射结果"
    )
    
    unmapped_terms: List[str] = Field(
        default_factory=list,
        description="无法映射的业务术语"
    )
    
    warnings: List[str] = Field(
        default_factory=list,
        description="映射警告信息"
    )


# ============= 更新 Intent 模型 =============

class DimensionIntent(BaseModel):
    """维度意图（更新版）"""
    
    business_term: str
    technical_field: str
    field_data_type: str
    aggregation: Optional[Literal["COUNTD", "MIN", "MAX"]] = None
    sort_direction: Optional[Literal["ASC", "DESC"]] = None
    sort_priority: Optional[int] = None
    
    # 新增字段
    mapping_confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="字段映射置信度"
    )
    
    mapping_alternatives: List[dict] = Field(
        default_factory=list,
        description="备选字段（低置信度时提供）"
    )


# 其他 Intent 模型类似更新...
```

#### 5.5 新的工具定义

```python
@tool
async def semantic_map_fields(
    business_terms: List[str],
    question_context: str,
    metadata: Dict[str, Any]
) -> FieldMappingResult:
    """
    语义字段映射工具
    
    使用 RAG + LLM 进行字段映射
    
    Args:
        business_terms: 业务术语列表
        question_context: 问题上下文
        metadata: 元数据
    
    Returns:
        FieldMappingResult: 映射结果
    """
    from tableau_assistant.src.components.semantic_field_mapper import SemanticFieldMapper
    
    # 1. 初始化映射器
    mapper = SemanticFieldMapper(
        embeddings=embeddings,
        llm=llm,
        metadata=metadata,
        vector_store_path="/vector_store/fields"
    )
    
    # 2. 批量映射
    mappings = []
    unmapped_terms = []
    warnings = []
    
    for term in business_terms:
        try:
            # 向量检索 + LLM 判断
            mapping = await mapper.map(
                user_term=term,
                question_context=question_context
            )
            
            mappings.append(mapping)
            
            # 低置信度警告
            if mapping.confidence < 0.8:
                warnings.append(
                    f"字段 '{term}' 的映射置信度较低（{mapping.confidence:.2f}），"
                    f"请确认是否正确"
                )
        
        except Exception as e:
            unmapped_terms.append(term)
            warnings.append(f"无法映射字段 '{term}': {str(e)}")
    
    return FieldMappingResult(
        mappings=mappings,
        unmapped_terms=unmapped_terms,
        warnings=warnings
    )
```

#### 5.6 新的 Planning Agent Prompt

```python
class TaskPlannerPrompt(VizQLPrompt):
    """优化后的 Task Planner Prompt"""
    
    def get_task(self) -> str:
        return """使用字段映射结果生成 Intent 模型。

Process: 使用映射结果 → 生成 Intent → 添加查询细节"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """Resources: {original_question}, {sub_questions}, {field_mapping_result}

**Think step by step:**

Step 1: 使用字段映射结果
- 从 field_mapping_result 中获取每个业务术语的映射
- 使用 technical_field 作为 Intent 的字段名
- 使用 field_role 判断应该生成哪种 Intent
- 使用 confidence 作为 mapping_confidence

Step 2: 生成 Intent 模型
- 根据 field_role 决定 Intent 类型：
  * dimension → DimensionIntent
  * measure → MeasureIntent
  * date → DateFieldIntent
- 从 sub-question 中获取聚合函数、排序等信息
- 添加 mapping_confidence 和 mapping_alternatives

Step 3: 识别查询细节
- 识别排序需求
- 识别 TopN 需求
- 识别过滤条件

CRITICAL: 不要重新进行字段映射！直接使用 field_mapping_result 中的结果。"""
```

### 总结

#### 当前设计的问题

1. ❌ Planning Agent 职责过重（字段映射 + 查询规划）
2. ❌ 没有利用 RAG + LLM 的优势
3. ❌ 无法提供置信度和备选字段
4. ❌ 无法进行历史学习

#### 改进后的设计

1. ✅ 分离关注点：字段映射 → 查询规划
2. ✅ 利用 RAG + LLM：向量检索 + 语义判断
3. ✅ 提供置信度：帮助用户确认映射
4. ✅ 支持历史学习：提升准确率
5. ✅ 数据模型更合理：FieldMappingResult → Intent

#### 实施建议

1. **Phase 1**：实现 `semantic_map_fields` 工具
2. **Phase 2**：更新 Intent 模型（添加 mapping_confidence）
3. **Phase 3**：更新 Planning Agent Prompt
4. **Phase 4**：集成到主流程中

