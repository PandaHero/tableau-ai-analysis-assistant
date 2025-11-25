# DeepAgents 特性详解

本文档详细描述如何充分利用 DeepAgents 框架的高级特性。

## 目录

1. [流式输出（astream_events）](#1-流式输出astream_events)
2. [Store 高级用法](#2-store-高级用法)
3. [Context 传递机制](#3-context-传递机制)
4. [错误恢复机制](#4-错误恢复机制)
5. [性能监控和追踪](#5-性能监控和追踪)

---

## 1. 流式输出（astream_events）

### 概述

DeepAgents 支持通过 `astream_events` 实现 Token 级别的流式输出，提供实时反馈。

### 实现方式

```python
from deepagents import create_deep_agent

# 创建 Agent
agent = create_deep_agent(...)

# 流式执行
async for event in agent.astream_events(
    input_data,
    config={"configurable": {"thread_id": "abc123"}},
    version="v2"
):
    event_type = event.get("event")
    
    # Token 级流式输出
    if event_type == "on_chat_model_stream":
        chunk = event.get("data", {}).get("chunk")
        if chunk and hasattr(chunk, "content"):
            token = chunk.content
            if token:
                print(token, end="", flush=True)
    
    # Agent 开始执行
    elif event_type == "on_chain_start":
        agent_name = event.get("name")
        print(f"\n[{agent_name} 开始执行]")
    
    # Agent 执行完成
    elif event_type == "on_chain_end":
        agent_name = event.get("name")
        output = event.get("data", {}).get("output")
        print(f"\n[{agent_name} 执行完成]")
    
    # 工具调用开始
    elif event_type == "on_tool_start":
        tool_name = event.get("name")
        inputs = event.get("data", {}).get("input")
        print(f"\n[调用工具: {tool_name}]")
    
    # 工具调用完成
    elif event_type == "on_tool_end":
        tool_name = event.get("name")
        output = event.get("data", {}).get("output")
        print(f"\n[工具 {tool_name} 完成]")
```

### 事件类型

| 事件类型 | 说明 | 数据 |
|---------|------|------|
| `on_chat_model_stream` | LLM Token 流式输出 | `chunk.content` |
| `on_chain_start` | Agent/Chain 开始执行 | `name`, `inputs` |
| `on_chain_end` | Agent/Chain 执行完成 | `name`, `output` |
| `on_tool_start` | 工具调用开始 | `name`, `input` |
| `on_tool_end` | 工具调用完成 | `name`, `output` |
| `on_retriever_start` | 检索器开始 | `name`, `query` |
| `on_retriever_end` | 检索器完成 | `name`, `documents` |

### SSE 集成

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()

@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式聊天端点"""
    
    async def event_generator():
        """SSE 事件生成器"""
        async for event in agent.astream_events(
            {"question": request.question},
            config={"configurable": {"thread_id": request.thread_id}},
            version="v2"
        ):
            event_type = event.get("event")
            
            # Token 流式输出
            if event_type == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content"):
                    token = chunk.content
                    if token:
                        yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
            
            # Agent 进度
            elif event_type == "on_chain_start":
                agent_name = event.get("name")
                yield f"data: {json.dumps({'type': 'agent_start', 'agent': agent_name})}\n\n"
            
            # 工具调用
            elif event_type == "on_tool_start":
                tool_name = event.get("name")
                yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name})}\n\n"
        
        # 完成
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

### 前端集成

```typescript
// Vue 3 + TypeScript
const eventSource = new EventSource(`/api/chat/stream?question=${question}`);

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  switch (data.type) {
    case 'token':
      // 逐字显示
      currentMessage.value += data.content;
      break;
    
    case 'agent_start':
      // 显示 Agent 进度
      currentAgent.value = data.agent;
      break;
    
    case 'tool_start':
      // 显示工具调用
      currentTool.value = data.tool;
      break;
    
    case 'done':
      // 完成
      eventSource.close();
      break;
  }
};
```

---

## 2. Store 高级用法

### 概述

DeepAgents 的 `PersistentStore` 提供了强大的数据存储和检索能力，支持命名空间、TTL、语义搜索等高级功能。

### 命名空间管理

```python
from deepagents.backend import PersistentStore

# 创建 Store
store = PersistentStore(conn)

# 使用命名空间组织数据
# 命名空间格式：(category, subcategory, ...)

# 元数据缓存
store.put(
    namespace=("metadata", datasource_luid),
    key="fields",
    value=metadata,
    ttl=3600  # 1小时
)

# 用户偏好
store.put(
    namespace=("user_preferences", user_id),
    key="preferred_granularity",
    value="month",
    ttl=86400  # 24小时
)

# 问题历史
store.put(
    namespace=("question_history", user_id),
    key=f"q_{timestamp}",
    value={
        "question": "2024年各地区的销售额",
        "timestamp": timestamp,
        "result": {...}
    },
    ttl=604800  # 7天
)

# 异常知识库
store.put(
    namespace=("anomaly_knowledge", datasource_luid),
    key=f"anomaly_{anomaly_id}",
    value={
        "dimension": "地区",
        "dimension_value": "华东",
        "anomaly_type": "spike",
        "explanation": "促销活动导致"
    },
    ttl=None  # 永久保存
)
```

### 语义搜索

```python
# 搜索历史问题（语义相似）
def search_similar_questions(
    store: PersistentStore,
    user_id: str,
    current_question: str,
    top_k: int = 5
) -> List[Dict]:
    """搜索语义相似的历史问题"""
    
    # 1. 获取所有历史问题
    namespace = ("question_history", user_id)
    all_questions = store.search(namespace, filter={})
    
    # 2. 使用 Embedding 计算相似度
    from langchain_openai import OpenAIEmbeddings
    embeddings = OpenAIEmbeddings()
    
    current_embedding = embeddings.embed_query(current_question)
    
    similarities = []
    for item in all_questions:
        question = item.value["question"]
        question_embedding = embeddings.embed_query(question)
        
        # 计算余弦相似度
        similarity = cosine_similarity(current_embedding, question_embedding)
        similarities.append((similarity, item.value))
    
    # 3. 返回 Top-K
    similarities.sort(reverse=True, key=lambda x: x[0])
    return [item[1] for item in similarities[:top_k]]
```

### 批量操作

```python
# 批量写入
items = [
    {
        "namespace": ("cache", "query_results"),
        "key": f"query_{i}",
        "value": result,
        "ttl": 3600
    }
    for i, result in enumerate(results)
]

store.batch_put(items)

# 批量读取
keys = [f"query_{i}" for i in range(10)]
results = store.batch_get(
    namespace=("cache", "query_results"),
    keys=keys
)

# 批量删除
store.batch_delete(
    namespace=("cache", "query_results"),
    keys=keys
)
```

### TTL 管理

```python
# 设置不同的 TTL 策略
TTL_STRATEGIES = {
    "metadata": 3600,           # 1小时
    "query_results": 1800,      # 30分钟
    "user_preferences": 86400,  # 24小时
    "question_history": 604800, # 7天
    "anomaly_knowledge": None   # 永久
}

def store_with_ttl(
    store: PersistentStore,
    category: str,
    key: str,
    value: Any
):
    """根据类别自动设置 TTL"""
    ttl = TTL_STRATEGIES.get(category, 3600)
    store.put(
        namespace=(category,),
        key=key,
        value=value,
        ttl=ttl
    )
```

---

## 3. Context 传递机制

### 概述

DeepAgents 使用 `Runtime[Context]` 在主 Agent 和子 Agent 间传递上下文，避免上下文污染。

### Context 定义

```python
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)  # 不可变
class DeepAgentContext:
    """运行时上下文（不可变配置）"""
    
    # 必需配置
    datasource_luid: str
    user_id: str
    thread_id: str
    tableau_token: str
    
    # 可选配置
    max_replan: int = 3
    enable_boost: bool = False
    enable_cache: bool = True
    model_config: Optional[Dict[str, Any]] = None
    
    # 性能配置
    timeout: int = 300
    max_tokens_per_call: int = 4000
    temperature: float = 0.0
```

### Context 传递

```python
from langgraph.runtime import Runtime

# 主 Agent 创建 Runtime
runtime = Runtime(
    context=DeepAgentContext(
        datasource_luid="abc123",
        user_id="user_001",
        thread_id="thread_001",
        tableau_token="token_xyz"
    )
)

# 子 Agent 访问 Context
async def understanding_agent(
    state: DeepAgentState,
    runtime: Runtime[DeepAgentContext]
) -> Dict:
    """Understanding Agent 节点函数"""
    
    # 访问上下文
    datasource_luid = runtime.context.datasource_luid
    user_id = runtime.context.user_id
    
    # 访问 Store
    metadata = runtime.store.get(
        namespace=("metadata", datasource_luid),
        key="fields"
    )
    
    # 执行逻辑
    ...
    
    return {"understanding": result}
```

### 避免上下文污染

```python
# ❌ 错误：在 State 中存储大量上下文
class DeepAgentState(TypedDict):
    question: str
    metadata: Dict  # ❌ 不要在 State 中存储大对象
    tableau_token: str  # ❌ 不要在 State 中存储敏感信息
    ...

# ✅ 正确：在 Context 中存储配置，在 Store 中存储数据
class DeepAgentState(TypedDict):
    question: str
    understanding: Optional[Dict]
    query_plan: Optional[Dict]
    ...

@dataclass(frozen=True)
class DeepAgentContext:
    datasource_luid: str  # ✅ 配置信息
    tableau_token: str    # ✅ 敏感信息
    ...

# ✅ 大对象存储在 Store 中
runtime.store.put(
    namespace=("metadata", datasource_luid),
    key="fields",
    value=metadata  # ✅ 大对象
)
```

### Context 的不可变性

```python
# Context 是不可变的（frozen=True）
# 这确保了线程安全和可预测性

# ❌ 错误：尝试修改 Context
runtime.context.max_replan = 5  # 报错！

# ✅ 正确：创建新的 Context
new_context = DeepAgentContext(
    datasource_luid=runtime.context.datasource_luid,
    user_id=runtime.context.user_id,
    thread_id=runtime.context.thread_id,
    tableau_token=runtime.context.tableau_token,
    max_replan=5  # 新值
)

new_runtime = Runtime(context=new_context)
```

---

## 4. 错误恢复机制

### 概述

DeepAgents 提供了多层次的错误恢复机制，确保系统的鲁棒性。

### 重试机制

```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

# 工具级重试
@tool
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((TimeoutError, ConnectionError))
)
async def execute_vizql_query(
    query: Dict[str, Any],
    datasource_luid: str
) -> Dict[str, Any]:
    """执行 VizQL 查询（带重试）"""
    # 执行查询
    ...
```

### Agent 级错误处理

```python
async def understanding_agent(
    state: DeepAgentState,
    runtime: Runtime[DeepAgentContext]
) -> Dict:
    """Understanding Agent 节点函数（带错误处理）"""
    
    try:
        # 执行主逻辑
        result = await execute_understanding(state, runtime)
        return {"understanding": result}
    
    except ValidationError as e:
        # 输出验证错误 - 重试
        logger.error(f"输出验证失败: {e}")
        return {
            "error": {
                "type": "validation_error",
                "message": str(e),
                "retry": True
            }
        }
    
    except TimeoutError as e:
        # 超时错误 - 重试
        logger.error(f"执行超时: {e}")
        return {
            "error": {
                "type": "timeout_error",
                "message": str(e),
                "retry": True
            }
        }
    
    except Exception as e:
        # 未知错误 - 不重试
        logger.error(f"未知错误: {e}")
        return {
            "error": {
                "type": "system_error",
                "message": str(e),
                "retry": False
            }
        }
```

### 降级策略

```python
async def insight_agent_with_fallback(
    state: DeepAgentState,
    runtime: Runtime[DeepAgentContext]
) -> Dict:
    """Insight Agent 节点函数（带降级策略）"""
    
    # 策略1：尝试渐进式分析
    try:
        if len(state["query_results"]) > 100:
            return await progressive_insight_analysis(state, runtime)
    except Exception as e:
        logger.warning(f"渐进式分析失败: {e}, 降级到全量分析")
    
    # 策略2：尝试全量分析
    try:
        return await full_insight_analysis(state, runtime)
    except Exception as e:
        logger.warning(f"全量分析失败: {e}, 降级到基础分析")
    
    # 策略3：基础分析（最简单，最可靠）
    try:
        return await basic_insight_analysis(state, runtime)
    except Exception as e:
        logger.error(f"基础分析失败: {e}")
        return {
            "insights": [],
            "error": {
                "type": "analysis_failed",
                "message": "所有分析策略均失败"
            }
        }
```

### 错误传播

```python
# 在 State 中传播错误
class DeepAgentState(TypedDict):
    question: str
    understanding: Optional[Dict]
    query_plan: Optional[Dict]
    error: Optional[Dict]  # 错误信息
    retry_count: int  # 重试次数

# 主流程中处理错误
def should_retry(state: DeepAgentState) -> bool:
    """判断是否应该重试"""
    if not state.get("error"):
        return False
    
    error = state["error"]
    retry_count = state.get("retry_count", 0)
    
    # 检查是否可重试
    if not error.get("retry", False):
        return False
    
    # 检查重试次数
    if retry_count >= 3:
        return False
    
    return True

# 在 Graph 中添加重试边
graph.add_conditional_edges(
    "understanding_agent",
    should_retry,
    {
        True: "understanding_agent",  # 重试
        False: "planning_agent"       # 继续
    }
)
```

---

## 5. 性能监控和追踪

### 概述

DeepAgents 提供了完整的性能监控和追踪能力，帮助优化系统性能。

### 使用 Callbacks

```python
from langchain_core.callbacks import BaseCallbackHandler
from typing import Any, Dict, List

class PerformanceTrackingCallback(BaseCallbackHandler):
    """性能追踪回调"""
    
    def __init__(self, store: PersistentStore, user_id: str, session_id: str):
        self.store = store
        self.user_id = user_id
        self.session_id = session_id
        self.start_times = {}
        self.metrics = {
            "llm_calls": 0,
            "tool_calls": 0,
            "total_tokens": 0,
            "total_time": 0
        }
    
    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        **kwargs: Any
    ) -> None:
        """LLM 调用开始"""
        run_id = kwargs.get("run_id")
        self.start_times[run_id] = time.time()
        self.metrics["llm_calls"] += 1
    
    def on_llm_end(
        self,
        response: Any,
        **kwargs: Any
    ) -> None:
        """LLM 调用结束"""
        run_id = kwargs.get("run_id")
        if run_id in self.start_times:
            elapsed = time.time() - self.start_times[run_id]
            self.metrics["total_time"] += elapsed
            
            # 记录 Token 使用
            if hasattr(response, "llm_output"):
                token_usage = response.llm_output.get("token_usage", {})
                self.metrics["total_tokens"] += token_usage.get("total_tokens", 0)
    
    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        **kwargs: Any
    ) -> None:
        """工具调用开始"""
        run_id = kwargs.get("run_id")
        self.start_times[run_id] = time.time()
        self.metrics["tool_calls"] += 1
    
    def on_tool_end(
        self,
        output: str,
        **kwargs: Any
    ) -> None:
        """工具调用结束"""
        run_id = kwargs.get("run_id")
        if run_id in self.start_times:
            elapsed = time.time() - self.start_times[run_id]
            # 记录工具执行时间
            tool_name = kwargs.get("name", "unknown")
            self.store.put(
                namespace=("metrics", "tool_times"),
                key=f"{tool_name}_{run_id}",
                value={"tool": tool_name, "time": elapsed},
                ttl=3600
            )
    
    def save_metrics(self):
        """保存指标"""
        self.store.put(
            namespace=("metrics", "sessions"),
            key=f"{self.session_id}_{int(time.time())}",
            value=self.metrics,
            ttl=86400  # 24小时
        )
```

### 使用 Callback

```python
# 创建 Callback
callback = PerformanceTrackingCallback(
    store=runtime.store,
    user_id=runtime.context.user_id,
    session_id=runtime.context.thread_id
)

# 在 Agent 执行时使用
result = await agent.ainvoke(
    input_data,
    config={
        "configurable": {"thread_id": runtime.context.thread_id},
        "callbacks": [callback]
    }
)

# 保存指标
callback.save_metrics()
```

### 性能指标分析

```python
def analyze_performance(
    store: PersistentStore,
    session_id: str
) -> Dict[str, Any]:
    """分析性能指标"""
    
    # 获取会话指标
    metrics = store.search(
        namespace=("metrics", "sessions"),
        filter={"session_id": session_id}
    )
    
    if not metrics:
        return {}
    
    # 聚合指标
    total_llm_calls = sum(m.value["llm_calls"] for m in metrics)
    total_tool_calls = sum(m.value["tool_calls"] for m in metrics)
    total_tokens = sum(m.value["total_tokens"] for m in metrics)
    total_time = sum(m.value["total_time"] for m in metrics)
    
    # 计算平均值
    avg_time_per_llm_call = total_time / total_llm_calls if total_llm_calls > 0 else 0
    avg_tokens_per_call = total_tokens / total_llm_calls if total_llm_calls > 0 else 0
    
    return {
        "total_llm_calls": total_llm_calls,
        "total_tool_calls": total_tool_calls,
        "total_tokens": total_tokens,
        "total_time": total_time,
        "avg_time_per_llm_call": avg_time_per_llm_call,
        "avg_tokens_per_call": avg_tokens_per_call
    }
```

### 实时监控

```python
# 实时监控端点
@app.get("/api/metrics/{session_id}")
async def get_metrics(session_id: str):
    """获取会话指标"""
    metrics = analyze_performance(store, session_id)
    return metrics

# 实时监控仪表板
@app.get("/api/metrics/dashboard")
async def get_dashboard():
    """获取监控仪表板数据"""
    
    # 获取最近1小时的所有会话
    recent_sessions = store.search(
        namespace=("metrics", "sessions"),
        filter={"timestamp": {"$gte": time.time() - 3600}}
    )
    
    # 聚合数据
    total_sessions = len(recent_sessions)
    total_tokens = sum(s.value["total_tokens"] for s in recent_sessions)
    avg_time = sum(s.value["total_time"] for s in recent_sessions) / total_sessions if total_sessions > 0 else 0
    
    return {
        "total_sessions": total_sessions,
        "total_tokens": total_tokens,
        "avg_time_per_session": avg_time,
        "timestamp": time.time()
    }
```

---

## 总结

通过充分利用 DeepAgents 的这些高级特性，我们可以：

1. **流式输出** - 提供实时反馈，提升用户体验
2. **Store 高级用法** - 高效管理数据，支持语义搜索
3. **Context 传递** - 避免上下文污染，确保线程安全
4. **错误恢复** - 提高系统鲁棒性，确保服务可用性
5. **性能监控** - 实时追踪性能，持续优化系统

这些特性的组合使用，将使我们的系统更加强大、可靠和高效。

---

**文档版本**: v1.0  
**最后更新**: 2025-01-15
