# 概念澄清文档

## 📚 目的

本文档澄清需求文档中容易混淆的概念，确保团队对架构有统一的理解。

---

## 1. SummarizationMiddleware vs 缓存

### SummarizationMiddleware（上下文总结）

**作用**：压缩对话历史，避免超出模型的上下文窗口

**触发条件**：对话历史的 token 数超过阈值（如 Claude 的 160k tokens）

**工作原理**：
```python
# 对话历史太长
messages = [
    {"role": "user", "content": "2016年各地区的销售额"},
    {"role": "assistant", "content": "华东地区销售额500万...（很长的回复）"},
    {"role": "user", "content": "那利润率呢？"},
    {"role": "assistant", "content": "华东地区利润率12%...（很长的回复）"},
    # ... 更多对话，总共 170k tokens
]

# SummarizationMiddleware 自动总结
summary = "用户询问了2016年各地区的销售额和利润率，系统返回了华东地区的数据..."

# 新的 messages（压缩后）
messages = [
    {"role": "system", "content": summary},  # 总结（5k tokens）
    {"role": "user", "content": "为什么华东利润率低？"}  # 新问题
]
```

**存储位置**：内存（LangGraph State）

**生命周期**：会话期间

---

### 缓存（Cache）

**作用**：避免重复计算，提升性能

**触发条件**：相同的输入

**类型**：

#### 1. Prompt Caching（Anthropic 官方）

**作用**：缓存系统提示词，节省 50-90% 成本

**工作原理**：
```python
# 第一次调用
system_prompt = "你是数据分析专家..." + metadata  # 10k tokens
response = llm.invoke(system_prompt + user_input)
# 成本：10k tokens（系统提示词）+ 1k tokens（用户输入）= 11k tokens

# 第二次调用（5分钟内）
response = llm.invoke(system_prompt + user_input)
# 成本：0 tokens（系统提示词缓存）+ 1k tokens（用户输入）= 1k tokens
# 节省：90%
```

**存储位置**：Anthropic 服务器

**生命周期**：5 分钟

---

#### 2. 查询结果缓存（PersistentStore - SQLite）

**作用**：缓存查询结果，避免重复查询

**工作原理**：
```python
# 第一次查询
query_key = hash("SELECT * FROM sales WHERE region='华东'")
result = execute_query(query)
store.put(("query_cache",), query_key, result, ttl=3600)  # 缓存 1 小时

# 第二次查询（1 小时内）
cached_result = store.get(("query_cache",), query_key)
if cached_result:
    return cached_result  # 直接返回，不执行查询
```

**存储位置**：SQLite 数据库（`data/langgraph_store.db`）

**生命周期**：可配置（默认 1 小时）

---

#### 3. LLM 响应缓存（可选）

**作用**：缓存 LLM 的响应，避免重复调用

**工作原理**：
```python
# 第一次调用
cache_key = hash(system_prompt + user_input)
response = llm.invoke(system_prompt + user_input)
store.put(("llm_cache",), cache_key, response, ttl=3600)

# 第二次调用（相同输入）
cached_response = store.get(("llm_cache",), cache_key)
if cached_response:
    return cached_response  # 直接返回，不调用 LLM
```

**存储位置**：SQLite 或 Redis

**生命周期**：可配置（默认 1 小时）

---

#### 4. 语义缓存（可选）

**作用**：基于语义相似度缓存，处理相似问题

**工作原理**：
```python
# 第一次查询
user_input = "2016年各地区的销售额"
response = llm.invoke(user_input)
vector_store.add(user_input, response)

# 第二次查询（相似问题）
user_input = "2016年不同地区的销售金额"
similar_queries = vector_store.similarity_search(user_input, k=1)
if similar_queries[0].similarity > 0.95:
    return similar_queries[0].response  # 返回缓存结果
```

**存储位置**：向量数据库（FAISS/Chroma）

**生命周期**：持久化

---

## 2. 当前系统的缓存机制

### 已实现

1. ✅ **PersistentStore（SQLite）**
   - 位置：`tableau_assistant/src/components/persistent_store.py`
   - 用途：持久化存储（元数据、查询缓存、累积洞察等）
   - 特性：
     - 线程安全
     - 连接池
     - 事务支持
     - WAL 模式（高并发）
     - 自动过期清理

2. ✅ **命名空间设计**
   ```python
   # 元数据
   store.put(("metadata", datasource_luid), "fields", fields_data)
   
   # 维度层级
   store.put(("hierarchies", datasource_luid), "geography", hierarchy_data)
   
   # 用户偏好
   store.put(("preferences", user_id), "default_datasource", datasource_luid)
   
   # 查询缓存（新增）
   store.put(("query_cache", thread_id), query_key, query_result, ttl=3600)
   
   # 累积洞察（新增）
   store.put(("insights", thread_id), f"round_{round_num}", insights, ttl=3600)
   ```

### 需要实现

1. ⭐ **查询结果缓存**
   - 在重规划时复用已有查询结果
   - 使用 query_key（查询参数的 hash）作为索引

2. ⭐ **累积洞察存储**
   - 保存每轮分析的洞察
   - 用于 Replanner Agent 判断

3. ⭐ **Anthropic Prompt Caching**
   - 使用 DeepAgents 的 AnthropicPromptCachingMiddleware
   - 自动缓存系统提示词

4. 🔮 **语义缓存**（可选）
   - 基于向量相似度匹配历史查询
   - 处理相似问题

---

## 3. 对比表

| 功能 | SummarizationMiddleware | Prompt Caching | 查询结果缓存 | LLM 响应缓存 | 语义缓存 |
|------|------------------------|---------------|------------|-------------|---------|
| **目的** | 压缩上下文 | 节省成本 | 避免重复查询 | 避免重复调用 | 处理相似问题 |
| **触发条件** | 上下文超过阈值 | 相同系统提示词 | 相同查询 | 相同输入 | 相似输入 |
| **作用对象** | 对话历史 | 系统提示词 | 查询结果 | LLM 响应 | LLM 响应 |
| **存储位置** | 内存（State） | Anthropic 服务器 | SQLite | SQLite/Redis | 向量数据库 |
| **生命周期** | 会话期间 | 5 分钟 | 可配置 | 可配置 | 持久化 |
| **实现状态** | ✅ DeepAgents 内置 | ✅ DeepAgents 内置 | ⭐ 需要实现 | 🔮 可选 | 🔮 可选 |

---

## 4. 实施建议

### Phase 1：基础缓存（必须）

1. ✅ 使用 PersistentStore（已实现）
2. ⭐ 实现查询结果缓存
3. ⭐ 实现累积洞察存储
4. ✅ 使用 AnthropicPromptCachingMiddleware（DeepAgents 内置）

### Phase 2：应用层缓存（必须）

1. ⭐ LLM 响应缓存（使用 PersistentStore）
   - 缓存 key：hash(system_prompt + user_input)
   - 命名空间：("llm_cache", model_name)
   - TTL：1 小时

### Phase 3：高级缓存（可选）

1. 🔮 语义缓存（基于向量相似度）

---

## 5. 常见问题

### Q1: SummarizationMiddleware 会影响性能吗？

**A**: 会有轻微影响，但利大于弊。

- **成本**：调用 LLM 总结历史（约 1-2 秒）
- **收益**：避免超出上下文窗口，保持对话连贯性
- **触发频率**：只在上下文超过阈值时触发（不频繁）

### Q2: Prompt Caching 只支持 Anthropic 吗？

**A**: 目前是的，但可以实现应用层缓存。

- **Anthropic**：官方支持，自动缓存，5 分钟 TTL
- **其他模型**：可以使用 PersistentStore 或 Redis 实现应用层缓存

### Q3: 查询结果缓存会占用多少空间？

**A**: 取决于查询结果的大小和缓存时间。

- **估算**：假设每个查询结果 1MB，缓存 1 小时，100 个查询 = 100MB
- **优化**：
  - 设置合理的 TTL（默认 1 小时）
  - 定期清理过期数据（`store.cleanup_expired()`）
  - 压缩大结果（使用 gzip）

### Q4: 为什么不使用 Redis？

**A**: SQLite 更简单，适合单机部署。

- **SQLite 优势**：
  - 无需额外服务
  - 文件存储，易于备份
  - 性能足够（WAL 模式支持高并发）
- **Redis 优势**：
  - 分布式部署
  - 更高性能
  - 更丰富的数据结构

**建议**：
- 单机部署：使用 SQLite
- 分布式部署：使用 Redis

---

## 6. 总结

### 核心概念

1. **SummarizationMiddleware**：压缩对话历史，避免超出上下文窗口
2. **Prompt Caching**：缓存系统提示词，节省成本（Anthropic 官方）
3. **查询结果缓存**：缓存查询结果，避免重复查询（PersistentStore）
4. **LLM 响应缓存**：缓存 LLM 响应，避免重复调用（可选）
5. **语义缓存**：基于语义相似度缓存（可选）

### 实施优先级

1. ✅ **Phase 1（必须）**：PersistentStore + 查询结果缓存 + Prompt Caching
2. ⭐ **Phase 2（必须）**：应用层缓存（LLM 响应缓存）
3. 🔮 **Phase 3（可选）**：语义缓存

### 预期收益

- **成本节省**：50-90%（Prompt Caching）
- **性能提升**：3-5x（查询结果缓存）
- **用户体验**：更快的响应时间

