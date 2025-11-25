# 缓存系统详细设计 - Part 2

## 5. L4: Semantic Cache（可选）

### 5.1 设计

Semantic Cache使用向量相似度检索语义相似的查询，即使问法不同也能命中缓存。

**适用场景**：
- "华东地区的销售额" vs "华东的销售情况"
- "2023年Q1的数据" vs "今年第一季度的数据"

**不适用场景**：
- 需要精确匹配的查询
- 数据频繁变化的场景

### 5.2 实现

```python
from typing import Tuple
import numpy as np

class SemanticCache:
    """语义缓存"""
    
    def __init__(
        self,
        vector_store: Any,  # FAISS向量存储
        embedding_model: Any,  # Embedding模型
        similarity_threshold: float = 0.95  # 相似度阈值
    ):
        self.vector_store = vector_store
        self.embedding_model = embedding_model
        self.similarity_threshold = similarity_threshold
        
        # 缓存映射：query_id -> result
        self.cache_map = {}
    
    async def get(
        self,
        query: str,
        context: Optional[Dict] = None
    ) -> Optional[Tuple[Dict, float]]:
        """
        获取语义相似的缓存结果
        
        Returns:
            (result, similarity) 或 None
        """
        
        # 1. 生成查询向量
        query_vector = await self._embed_query(query, context)
        
        # 2. 向量检索
        results = self.vector_store.similarity_search_with_score(
            query_vector,
            k=1
        )
        
        if not results:
            return None
        
        # 3. 检查相似度
        similar_query_id, similarity = results[0]
        
        if similarity < self.similarity_threshold:
            return None
        
        # 4. 返回缓存结果
        cached_result = self.cache_map.get(similar_query_id)
        
        if cached_result is None:
            return None
        
        logger.info(f"L4 Semantic cache hit: similarity={similarity:.3f}")
        return cached_result, similarity
    
    async def set(
        self,
        query: str,
        result: Dict,
        context: Optional[Dict] = None
    ):
        """保存查询结果到语义缓存"""
        
        # 1. 生成查询向量
        query_vector = await self._embed_query(query, context)
        
        # 2. 生成唯一ID
        query_id = hashlib.sha256(query.encode()).hexdigest()
        
        # 3. 保存到向量存储
        self.vector_store.add_texts(
            texts=[query],
            embeddings=[query_vector],
            metadatas=[{"query_id": query_id}]
        )
        
        # 4. 保存到缓存映射
        self.cache_map[query_id] = result
    
    async def _embed_query(
        self,
        query: str,
        context: Optional[Dict] = None
    ) -> np.ndarray:
        """生成查询向量"""
        
        # 可以结合上下文信息
        if context:
            enhanced_query = f"{query} | Context: {context.get('datasource_name', '')}"
        else:
            enhanced_query = query
        
        # 调用Embedding模型
        vector = await self.embedding_model.aembed_query(enhanced_query)
        
        return np.array(vector)
```

### 5.3 使用示例

```python
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings

# 初始化
embedding_model = HuggingFaceEmbeddings(
    model_name="maidalun1020/bce-embedding-base_v1"
)
vector_store = FAISS.from_texts([], embedding_model)
semantic_cache = SemanticCache(vector_store, embedding_model)

# 查询1
result1 = await execute_query("华东地区的销售额")
await semantic_cache.set("华东地区的销售额", result1)

# 查询2（语义相似）
cached_result = await semantic_cache.get("华东的销售情况")
if cached_result:
    result2, similarity = cached_result
    print(f"使用缓存结果，相似度: {similarity:.3f}")
else:
    result2 = await execute_query("华东的销售情况")
```

---

## 6. 缓存管理

### 6.1 缓存失效策略

**1. TTL（Time To Live）**

```python
class TTLCache:
    """基于TTL的缓存"""
    
    def __init__(self, ttl: int):
        self.ttl = ttl
        self.cache = {}
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        if key not in self.cache:
            return None
        
        value, timestamp = self.cache[key]
        
        # 检查是否过期
        if time.time() - timestamp > self.ttl:
            del self.cache[key]
            return None
        
        return value
    
    def set(self, key: str, value: Any):
        """设置缓存"""
        self.cache[key] = (value, time.time())
```

**2. LRU（Least Recently Used）**

```python
from collections import OrderedDict

class LRUCache:
    """LRU缓存"""
    
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = OrderedDict()
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        if key not in self.cache:
            return None
        
        # 移到最后（最近使用）
        self.cache.move_to_end(key)
        return self.cache[key]
    
    def set(self, key: str, value: Any):
        """设置缓存"""
        if key in self.cache:
            # 更新并移到最后
            self.cache.move_to_end(key)
        
        self.cache[key] = value
        
        # 检查容量
        if len(self.cache) > self.capacity:
            # 删除最久未使用的
            self.cache.popitem(last=False)
```

**3. 主动失效**

```python
class CacheInvalidator:
    """缓存失效器"""
    
    def __init__(
        self,
        app_cache: ApplicationCache,
        query_cache: QueryResultCache
    ):
        self.app_cache = app_cache
        self.query_cache = query_cache
    
    async def invalidate_on_data_change(
        self,
        datasource_luid: str
    ):
        """数据变化时失效缓存"""
        
        # 清除该数据源的所有查询缓存
        await self.query_cache.clear_datasource(datasource_luid)
        
        logger.info(f"Invalidated cache for datasource {datasource_luid}")
    
    async def invalidate_on_metadata_change(
        self,
        datasource_luid: str
    ):
        """元数据变化时失效缓存"""
        
        # 清除相关的LLM缓存
        # 注意：这需要追踪哪些LLM调用使用了该数据源的元数据
        pass
```

### 6.2 缓存预热

```python
class CacheWarmer:
    """缓存预热器"""
    
    def __init__(
        self,
        semantic_cache: SemanticCache
    ):
        self.semantic_cache = semantic_cache
    
    async def warm_up(
        self,
        common_queries: List[str],
        datasource_luid: str
    ):
        """预热常见查询"""
        
        for query in common_queries:
            # 执行查询
            result = await execute_query(query, datasource_luid)
            
            # 保存到缓存
            await self.semantic_cache.set(
                query,
                result,
                context={"datasource_luid": datasource_luid}
            )
            
            logger.info(f"Warmed up cache for query: {query}")

# 使用示例
common_queries = [
    "销售额趋势",
    "各地区销售对比",
    "Top 10产品"
]

warmer = CacheWarmer(semantic_cache)
await warmer.warm_up(common_queries, datasource_luid)
```

---

## 7. 缓存监控

### 7.1 性能指标

```python
from dataclasses import dataclass
from typing import Dict

@dataclass
class CacheMetrics:
    """缓存性能指标"""
    
    # L1: Prompt Caching
    l1_hits: int = 0
    l1_misses: int = 0
    l1_tokens_saved: int = 0
    
    # L2: Application Cache
    l2_hits: int = 0
    l2_misses: int = 0
    l2_time_saved: float = 0.0  # 秒
    
    # L3: Query Result Cache
    l3_hits: int = 0
    l3_misses: int = 0
    l3_queries_saved: int = 0
    
    # L4: Semantic Cache
    l4_hits: int = 0
    l4_misses: int = 0
    l4_avg_similarity: float = 0.0
    
    @property
    def total_hits(self) -> int:
        return self.l1_hits + self.l2_hits + self.l3_hits + self.l4_hits
    
    @property
    def total_misses(self) -> int:
        return self.l1_misses + self.l2_misses + self.l3_misses + self.l4_misses
    
    @property
    def overall_hit_rate(self) -> float:
        total = self.total_hits + self.total_misses
        return self.total_hits / total if total > 0 else 0.0
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "l1": {
                "hits": self.l1_hits,
                "misses": self.l1_misses,
                "hit_rate": self.l1_hits / (self.l1_hits + self.l1_misses) if (self.l1_hits + self.l1_misses) > 0 else 0,
                "tokens_saved": self.l1_tokens_saved
            },
            "l2": {
                "hits": self.l2_hits,
                "misses": self.l2_misses,
                "hit_rate": self.l2_hits / (self.l2_hits + self.l2_misses) if (self.l2_hits + self.l2_misses) > 0 else 0,
                "time_saved_seconds": self.l2_time_saved
            },
            "l3": {
                "hits": self.l3_hits,
                "misses": self.l3_misses,
                "hit_rate": self.l3_hits / (self.l3_hits + self.l3_misses) if (self.l3_hits + self.l3_misses) > 0 else 0,
                "queries_saved": self.l3_queries_saved
            },
            "l4": {
                "hits": self.l4_hits,
                "misses": self.l4_misses,
                "hit_rate": self.l4_hits / (self.l4_hits + self.l4_misses) if (self.l4_hits + self.l4_misses) > 0 else 0,
                "avg_similarity": self.l4_avg_similarity
            },
            "overall": {
                "total_hits": self.total_hits,
                "total_misses": self.total_misses,
                "hit_rate": self.overall_hit_rate
            }
        }
```

### 7.2 监控收集器

```python
class CacheMonitor:
    """缓存监控器"""
    
    def __init__(self):
        self.metrics = CacheMetrics()
    
    def record_l1_hit(self, tokens_saved: int):
        """记录L1缓存命中"""
        self.metrics.l1_hits += 1
        self.metrics.l1_tokens_saved += tokens_saved
    
    def record_l1_miss(self):
        """记录L1缓存未命中"""
        self.metrics.l1_misses += 1
    
    def record_l2_hit(self, time_saved: float):
        """记录L2缓存命中"""
        self.metrics.l2_hits += 1
        self.metrics.l2_time_saved += time_saved
    
    def record_l2_miss(self):
        """记录L2缓存未命中"""
        self.metrics.l2_misses += 1
    
    def record_l3_hit(self):
        """记录L3缓存命中"""
        self.metrics.l3_hits += 1
        self.metrics.l3_queries_saved += 1
    
    def record_l3_miss(self):
        """记录L3缓存未命中"""
        self.metrics.l3_misses += 1
    
    def record_l4_hit(self, similarity: float):
        """记录L4缓存命中"""
        self.metrics.l4_hits += 1
        
        # 更新平均相似度
        total_hits = self.metrics.l4_hits
        current_avg = self.metrics.l4_avg_similarity
        self.metrics.l4_avg_similarity = (
            (current_avg * (total_hits - 1) + similarity) / total_hits
        )
    
    def record_l4_miss(self):
        """记录L4缓存未命中"""
        self.metrics.l4_misses += 1
    
    def get_metrics(self) -> Dict:
        """获取指标"""
        return self.metrics.to_dict()
    
    def reset(self):
        """重置指标"""
        self.metrics = CacheMetrics()
```

### 7.3 日志和报告

```python
import logging

logger = logging.getLogger(__name__)

class CacheReporter:
    """缓存报告器"""
    
    def __init__(self, monitor: CacheMonitor):
        self.monitor = monitor
    
    def log_summary(self):
        """记录缓存摘要"""
        metrics = self.monitor.get_metrics()
        
        logger.info("=== Cache Performance Summary ===")
        logger.info(f"Overall Hit Rate: {metrics['overall']['hit_rate']:.2%}")
        logger.info(f"Total Hits: {metrics['overall']['total_hits']}")
        logger.info(f"Total Misses: {metrics['overall']['total_misses']}")
        
        logger.info("\n--- L1: Prompt Caching ---")
        logger.info(f"Hit Rate: {metrics['l1']['hit_rate']:.2%}")
        logger.info(f"Tokens Saved: {metrics['l1']['tokens_saved']:,}")
        
        logger.info("\n--- L2: Application Cache ---")
        logger.info(f"Hit Rate: {metrics['l2']['hit_rate']:.2%}")
        logger.info(f"Time Saved: {metrics['l2']['time_saved_seconds']:.2f}s")
        
        logger.info("\n--- L3: Query Result Cache ---")
        logger.info(f"Hit Rate: {metrics['l3']['hit_rate']:.2%}")
        logger.info(f"Queries Saved: {metrics['l3']['queries_saved']}")
        
        logger.info("\n--- L4: Semantic Cache ---")
        logger.info(f"Hit Rate: {metrics['l4']['hit_rate']:.2%}")
        logger.info(f"Avg Similarity: {metrics['l4']['avg_similarity']:.3f}")
    
    def generate_report(self) -> str:
        """生成报告"""
        metrics = self.monitor.get_metrics()
        
        report = f"""
# Cache Performance Report

## Overall Statistics
- **Total Hits**: {metrics['overall']['total_hits']}
- **Total Misses**: {metrics['overall']['total_misses']}
- **Overall Hit Rate**: {metrics['overall']['hit_rate']:.2%}

## L1: Prompt Caching (Anthropic)
- **Hits**: {metrics['l1']['hits']}
- **Misses**: {metrics['l1']['misses']}
- **Hit Rate**: {metrics['l1']['hit_rate']:.2%}
- **Tokens Saved**: {metrics['l1']['tokens_saved']:,}

## L2: Application Cache (SQLite)
- **Hits**: {metrics['l2']['hits']}
- **Misses**: {metrics['l2']['misses']}
- **Hit Rate**: {metrics['l2']['hit_rate']:.2%}
- **Time Saved**: {metrics['l2']['time_saved_seconds']:.2f}s

## L3: Query Result Cache (SQLite)
- **Hits**: {metrics['l3']['hits']}
- **Misses**: {metrics['l3']['misses']}
- **Hit Rate**: {metrics['l3']['hit_rate']:.2%}
- **Queries Saved**: {metrics['l3']['queries_saved']}

## L4: Semantic Cache (FAISS)
- **Hits**: {metrics['l4']['hits']}
- **Misses**: {metrics['l4']['misses']}
- **Hit Rate**: {metrics['l4']['hit_rate']:.2%}
- **Avg Similarity**: {metrics['l4']['avg_similarity']:.3f}
"""
        return report
```

---

## 8. 完整集成示例

```python
class CachedDeepAgent:
    """带缓存的DeepAgent"""
    
    def __init__(
        self,
        llm: Any,
        tableau_client: Any,
        persistent_store: InMemoryStore
    ):
        # 初始化缓存
        self.app_cache = ApplicationCache(persistent_store, ttl=3600)
        self.query_cache = QueryResultCache(persistent_store)
        
        # 可选：语义缓存
        embedding_model = HuggingFaceEmbeddings(
            model_name="maidalun1020/bce-embedding-base_v1"
        )
        vector_store = FAISS.from_texts([], embedding_model)
        self.semantic_cache = SemanticCache(vector_store, embedding_model)
        
        # 包装LLM和工具
        self.cached_llm = CachedLLMWrapper(llm, self.app_cache)
        self.cached_query_tool = CachedExecuteVizQLQuery(
            tableau_client,
            self.query_cache
        )
        
        # 监控
        self.monitor = CacheMonitor()
        self.reporter = CacheReporter(self.monitor)
    
    async def process_question(
        self,
        question: str,
        datasource_luid: str
    ) -> Dict:
        """处理问题（带缓存）"""
        
        # 1. 检查语义缓存
        semantic_result = await self.semantic_cache.get(
            question,
            context={"datasource_luid": datasource_luid}
        )
        
        if semantic_result:
            result, similarity = semantic_result
            self.monitor.record_l4_hit(similarity)
            return result
        
        self.monitor.record_l4_miss()
        
        # 2. 执行分析（使用缓存的LLM和工具）
        result = await self._execute_analysis(question, datasource_luid)
        
        # 3. 保存到语义缓存
        await self.semantic_cache.set(
            question,
            result,
            context={"datasource_luid": datasource_luid}
        )
        
        # 4. 记录监控指标
        self.reporter.log_summary()
        
        return result
    
    async def _execute_analysis(
        self,
        question: str,
        datasource_luid: str
    ) -> Dict:
        """执行分析"""
        # 使用cached_llm和cached_query_tool
        # 这些会自动使用L2和L3缓存
        pass
```

---

**文档版本**: v1.0  
**最后更新**: 2025-01-15

