# 缓存系统详细设计

## 概述

缓存系统是DeepAgent性能优化的关键组件，通过四层缓存架构显著降低LLM调用成本和响应延迟。

**设计目标**：
- ✅ **成本优化** - 通过缓存减少50-90%的LLM调用成本
- ✅ **性能提升** - 缓存命中时响应时间从秒级降至毫秒级
- ✅ **透明集成** - 对Agent代码透明，无需修改现有逻辑
- ✅ **灵活配置** - 支持不同的TTL和失效策略

---

## 1. 四层缓存架构

```
┌─────────────────────────────────────────────────────────┐
│  L1: Prompt Caching (Anthropic API)                     │
│  - 存储: Anthropic服务端                                 │
│  - TTL: 5分钟                                            │
│  - 命中率: 60-80%                                        │
│  - 成本节省: 50-90%                                      │
│  - 适用: Claude模型的系统提示词                          │
└─────────────────────────────────────────────────────────┘
                          ↓ Miss
┌─────────────────────────────────────────────────────────┐
│  L2: Application Cache (PersistentStore/SQLite)         │
│  - 存储: 本地SQLite                                      │
│  - TTL: 1小时                                            │
│  - 命中率: 40-60%                                        │
│  - 成本节省: 30-50%                                      │
│  - 适用: 所有模型的LLM响应                               │
└─────────────────────────────────────────────────────────┘
                          ↓ Miss
┌─────────────────────────────────────────────────────────┐
│  L3: Query Result Cache (PersistentStore/SQLite)        │
│  - 存储: 本地SQLite                                      │
│  - TTL: 会话期间                                         │
│  - 命中率: 20-40%                                        │
│  - 成本节省: 10-30%                                      │
│  - 适用: VizQL查询结果                                   │
└─────────────────────────────────────────────────────────┘
                          ↓ Miss
┌─────────────────────────────────────────────────────────┐
│  L4: Semantic Cache (Vector Store/FAISS) [可选]         │
│  - 存储: FAISS向量索引                                   │
│  - TTL: 永久                                             │
│  - 命中率: 5-15%                                         │
│  - 成本节省: 5-10%                                       │
│  - 适用: 语义相似的查询                                  │
└─────────────────────────────────────────────────────────┘
```

---

## 2. L1: Prompt Caching（Anthropic）

### 2.1 工作原理

Anthropic的Prompt Caching功能会自动缓存长的系统提示词，在5分钟内重复使用时只需支付缓存读取费用（比正常费用低90%）。

**关键特性**：
- 自动缓存：无需额外代码
- 服务端存储：不占用本地资源
- 5分钟TTL：适合会话内重复调用
- 成本极低：缓存读取费用仅为正常费用的10%

### 2.2 使用方式

```python
from langchain_anthropic import ChatAnthropic

# 配置Prompt Caching
llm = ChatAnthropic(
    model="claude-3-5-sonnet-20241022",
    temperature=0,
    # Prompt Caching自动启用，无需额外配置
)

# 使用SystemMessage时，长提示词会自动缓存
from langchain_core.messages import SystemMessage, HumanMessage

messages = [
    SystemMessage(content=long_system_prompt),  # 会被缓存
    HumanMessage(content=user_question)
]

response = await llm.ainvoke(messages)
```

### 2.3 最佳实践

**1. 提示词结构优化**

```python
# ✅ 好的做法：将固定内容放在前面
system_prompt = f"""
{FIXED_INSTRUCTIONS}  # 固定的指令（会被缓存）
{FIXED_EXAMPLES}      # 固定的示例（会被缓存）

# 动态内容放在最后
Current metadata: {metadata}  # 动态内容（不会被缓存）
"""

# ❌ 不好的做法：动态内容在前面
system_prompt = f"""
Current metadata: {metadata}  # 动态内容在前面
{FIXED_INSTRUCTIONS}          # 固定内容在后面
"""
```

**2. 缓存命中率监控**

```python
# 检查响应中的缓存使用情况
response = await llm.ainvoke(messages)

# Anthropic会在响应头中返回缓存统计
# 可以通过日志查看
logger.info(f"Cache read tokens: {response.response_metadata.get('cache_read_input_tokens', 0)}")
logger.info(f"Cache creation tokens: {response.response_metadata.get('cache_creation_input_tokens', 0)}")
```

---

## 3. L2: Application Cache（PersistentStore）

### 3.1 设计

Application Cache缓存所有LLM的响应（不仅限于Claude），使用LangChain的PersistentStore存储在SQLite中。

**缓存Key生成**：

```python
import hashlib
import json

def generate_cache_key(
    model: str,
    messages: List[Dict],
    temperature: float = 0.0
) -> str:
    """
    生成缓存Key
    
    Args:
        model: 模型名称
        messages: 消息列表
        temperature: 温度参数
    
    Returns:
        缓存Key（SHA256哈希）
    """
    # 构建缓存内容
    cache_content = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }
    
    # 序列化并哈希
    content_str = json.dumps(cache_content, sort_keys=True)
    cache_key = hashlib.sha256(content_str.encode()).hexdigest()
    
    return cache_key
```

### 3.2 实现

```python
from langchain_core.stores import InMemoryStore
from langchain.globals import set_llm_cache
from langchain_community.cache import SQLiteCache
import time

class ApplicationCache:
    """应用级缓存"""
    
    def __init__(
        self,
        store: InMemoryStore,
        ttl: int = 3600  # 1小时
    ):
        self.store = store
        self.ttl = ttl
        self.namespace = ("llm_cache",)
    
    async def get(
        self,
        model: str,
        messages: List[Dict],
        temperature: float = 0.0
    ) -> Optional[str]:
        """获取缓存"""
        
        # 生成Key
        cache_key = generate_cache_key(model, messages, temperature)
        
        # 查询缓存
        cached_data = await self.store.aget(self.namespace + (model,), cache_key)
        
        if cached_data is None:
            return None
        
        # 检查TTL
        cached_time = cached_data.get("timestamp", 0)
        if time.time() - cached_time > self.ttl:
            # 过期，删除
            await self.store.adelete(self.namespace + (model,), [cache_key])
            return None
        
        return cached_data.get("content")
    
    async def set(
        self,
        model: str,
        messages: List[Dict],
        temperature: float,
        content: str
    ):
        """设置缓存"""
        
        # 生成Key
        cache_key = generate_cache_key(model, messages, temperature)
        
        # 保存缓存
        await self.store.aput(
            self.namespace + (model,),
            cache_key,
            {
                "content": content,
                "timestamp": time.time()
            }
        )
```

### 3.3 集成到Agent

```python
class CachedLLMWrapper:
    """带缓存的LLM包装器"""
    
    def __init__(
        self,
        llm: Any,
        cache: ApplicationCache
    ):
        self.llm = llm
        self.cache = cache
    
    async def ainvoke(
        self,
        messages: List[Dict],
        **kwargs
    ) -> str:
        """调用LLM（带缓存）"""
        
        model = self.llm.model_name
        temperature = kwargs.get("temperature", 0.0)
        
        # 1. 检查缓存
        cached_content = await self.cache.get(model, messages, temperature)
        
        if cached_content is not None:
            logger.info(f"L2 Cache hit for model {model}")
            return cached_content
        
        # 2. 缓存未命中，调用LLM
        logger.info(f"L2 Cache miss for model {model}")
        response = await self.llm.ainvoke(messages, **kwargs)
        
        # 3. 保存到缓存
        await self.cache.set(
            model,
            messages,
            temperature,
            response.content
        )
        
        return response.content

# 使用示例
llm = ChatAnthropic(model="claude-3-5-sonnet-20241022")
cache = ApplicationCache(store=persistent_store)
cached_llm = CachedLLMWrapper(llm, cache)

# 调用（会自动使用缓存）
response = await cached_llm.ainvoke(messages)
```

---

## 4. L3: Query Result Cache

### 4.1 设计

Query Result Cache缓存VizQL查询结果，避免重复执行相同的查询。

**缓存Key生成**：

```python
def generate_query_cache_key(
    datasource_luid: str,
    vizql_query: str
) -> str:
    """
    生成查询缓存Key
    
    Args:
        datasource_luid: 数据源LUID
        vizql_query: VizQL查询语句
    
    Returns:
        缓存Key
    """
    content = f"{datasource_luid}:{vizql_query}"
    return hashlib.sha256(content.encode()).hexdigest()
```

### 4.2 实现

```python
class QueryResultCache:
    """查询结果缓存"""
    
    def __init__(
        self,
        store: InMemoryStore,
        ttl: Optional[int] = None  # None表示会话期间有效
    ):
        self.store = store
        self.ttl = ttl
        self.namespace = ("query_cache",)
    
    async def get(
        self,
        datasource_luid: str,
        vizql_query: str
    ) -> Optional[Dict]:
        """获取缓存的查询结果"""
        
        cache_key = generate_query_cache_key(datasource_luid, vizql_query)
        
        cached_data = await self.store.aget(
            self.namespace + (datasource_luid,),
            cache_key
        )
        
        if cached_data is None:
            return None
        
        # 检查TTL（如果设置）
        if self.ttl is not None:
            cached_time = cached_data.get("timestamp", 0)
            if time.time() - cached_time > self.ttl:
                await self.store.adelete(
                    self.namespace + (datasource_luid,),
                    [cache_key]
                )
                return None
        
        return cached_data.get("result")
    
    async def set(
        self,
        datasource_luid: str,
        vizql_query: str,
        result: Dict
    ):
        """缓存查询结果"""
        
        cache_key = generate_query_cache_key(datasource_luid, vizql_query)
        
        await self.store.aput(
            self.namespace + (datasource_luid,),
            cache_key,
            {
                "result": result,
                "timestamp": time.time()
            }
        )
    
    async def clear_datasource(self, datasource_luid: str):
        """清除特定数据源的所有缓存"""
        # 注意：InMemoryStore不支持按namespace删除
        # 需要手动实现或等待TTL过期
        pass
```

### 4.3 集成到工具

```python
class CachedExecuteVizQLQuery:
    """带缓存的VizQL查询工具"""
    
    def __init__(
        self,
        tableau_client: Any,
        cache: QueryResultCache
    ):
        self.tableau_client = tableau_client
        self.cache = cache
    
    async def execute(
        self,
        datasource_luid: str,
        vizql_query: str
    ) -> Dict:
        """执行VizQL查询（带缓存）"""
        
        # 1. 检查缓存
        cached_result = await self.cache.get(datasource_luid, vizql_query)
        
        if cached_result is not None:
            logger.info(f"L3 Cache hit for query: {vizql_query[:50]}...")
            return cached_result
        
        # 2. 缓存未命中，执行查询
        logger.info(f"L3 Cache miss for query: {vizql_query[:50]}...")
        result = await self.tableau_client.execute_query(
            datasource_luid,
            vizql_query
        )
        
        # 3. 保存到缓存
        await self.cache.set(datasource_luid, vizql_query, result)
        
        return result
```

---

