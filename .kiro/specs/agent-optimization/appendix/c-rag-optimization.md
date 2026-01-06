# 附录 C：RAG 优化详解

## 1. 现有 RAG 实现

项目已有完整的自定义 RAG 实现，位于 `tableau_assistant/src/agents/field_mapper/rag/`：

```
field_mapper/rag/
├── semantic_mapper.py    # SemanticMapper - RAG 语义映射
├── field_indexer.py      # FieldIndexer - FAISS 向量索引
├── retriever.py          # 检索器（向量检索 + BM25 混合）
├── reranker.py           # 重排序器
├── embeddings.py         # 嵌入模型
├── cache.py              # 缓存管理
└── ...
```

### 1.1 技术栈

| 组件 | 实现 | 说明 |
|------|------|------|
| 向量存储 | FAISS | 高性能向量检索 |
| 嵌入模型 | 自定义 | 通过 embeddings.py 管理 |
| 检索策略 | 混合检索 | 向量检索 + BM25 |
| 重排序 | 自定义 | 可选的 Reranker |

### 1.2 为什么使用自定义实现而非 LangChain RAG

```
LangChain 提供的 RAG 功能：
- VectorStoreRetriever
- FAISS 集成
- 各种检索策略

项目选择自定义实现的原因：
1. 更精细的控制（置信度阈值、缓存策略）
2. 特定的业务逻辑（字段映射、消歧）
3. 性能优化（批量检索、增量更新）
4. 可观测性（延迟分解、来源追踪）
```

## 2. RAG + Candidate Fields 策略

### 2.1 策略概述

```
┌─────────────────────────────────────────────────────────────────┐
│                RAG + Candidate Fields 策略                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  用户问题                                                        │
│      ↓                                                          │
│  Step1 提取实体（业务术语）                                      │
│      ↓                                                          │
│  RAG 检索候选字段（top-k）                                       │
│      ↓                                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ confidence >= 0.9 ?                                      │   │
│  │   YES → 直接返回映射结果                                 │   │
│  │   NO  → LLM 从候选字段中选择                            │   │
│  └─────────────────────────────────────────────────────────┘   │
│      ↓                                                          │
│  返回映射结果                                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 现有实现

```python
# tableau_assistant/src/orchestration/tools/map_fields/tool.py

class MapFieldsTool:
    """字段映射工具
    
    策略（保留现有 RAG+LLM 混合策略）：
    1. 缓存检查 → 命中直接返回
    2. RAG 检索 → confidence >= 0.9 直接返回
    3. LLM Fallback → 从 top-k candidates 中选择
    4. RAG 不可用 → LLM Only
    """
```

### 2.3 映射来源

```python
# tableau_assistant/src/orchestration/tools/map_fields/models.py

class MappedFieldItem(BaseModel):
    """映射结果项"""
    business_term: str = Field(description="业务术语")
    technical_field: str = Field(description="技术字段名")
    confidence: float = Field(ge=0.0, le=1.0, description="映射置信度")
    mapping_source: str = Field(
        description="映射来源: cache_hit, rag_direct, rag_llm_fallback, llm_only"
    )
```

## 3. 优化建议

### 3.1 置信度阈值调优

```python
# 当前阈值
RAG_CONFIDENCE_THRESHOLD = 0.9

# 建议：根据实际数据调整
# - 字段名称规范的数据源：可提高到 0.95
# - 字段名称混乱的数据源：可降低到 0.85
```

### 3.2 候选字段数量

```python
# 当前 top-k
TOP_K_CANDIDATES = 5

# 建议：
# - 字段数量少（<50）：top-3 足够
# - 字段数量多（>200）：top-5 或 top-10
```

### 3.3 索引更新策略

```python
# 建议：数据模型变更时自动更新索引
class FieldIndexer:
    async def update_index_if_needed(self, data_model: DataModel):
        """检查并更新索引"""
        if self._is_index_stale(data_model):
            await self._rebuild_index(data_model)
```

## 4. 性能优化

### 4.1 缓存策略

```
┌─────────────────────────────────────────────────────────────────┐
│                    缓存层级                                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  L1: 内存缓存（LRU）                                            │
│      - 最近使用的映射结果                                        │
│      - TTL: 5 分钟                                              │
│                                                                 │
│  L2: LangGraph Store                                            │
│      - 持久化的映射结果                                          │
│      - 按 datasource_luid 分区                                  │
│                                                                 │
│  L3: RAG 检索                                                   │
│      - 向量相似度搜索                                            │
│      - 返回 top-k 候选                                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 批量映射

```python
# 建议：支持批量映射以减少 RAG 调用次数
async def map_fields_batch(
    self,
    business_terms: List[str],
    data_model: DataModel,
) -> List[MappedFieldItem]:
    """批量映射字段"""
    # 1. 批量缓存检查
    # 2. 批量 RAG 检索
    # 3. 批量 LLM Fallback
```

## 5. 与 LLM 的协作

### 5.1 不传递完整 DataModel

```
优势：
- Token 消耗少（只传候选字段）
- 准确率高（LLM 从候选中选择，而非生成）
- 可解释（可以看到 RAG 检索过程）
```

### 5.2 LLM Fallback Prompt

```xml
<context>
用户提到的业务术语：{business_term}

RAG 检索到的候选字段（按相似度排序）：
1. {candidate_1} (相似度: {score_1})
2. {candidate_2} (相似度: {score_2})
3. {candidate_3} (相似度: {score_3})
</context>

<task>
从候选字段中选择最匹配的字段。
如果没有合适的候选，返回 null。
</task>
```

## 6. 监控指标

### 6.1 关键指标

| 指标 | 说明 | 目标 |
|------|------|------|
| cache_hit_rate | 缓存命中率 | > 60% |
| rag_direct_rate | RAG 直接返回率 | > 70% |
| llm_fallback_rate | LLM Fallback 率 | < 20% |
| mapping_accuracy | 映射准确率 | > 95% |

### 6.2 日志记录

```python
logger.info(
    "Field mapping completed",
    extra={
        "business_term": business_term,
        "technical_field": result.technical_field,
        "confidence": result.confidence,
        "mapping_source": result.mapping_source,
        "latency_ms": latency_ms,
    }
)
```
