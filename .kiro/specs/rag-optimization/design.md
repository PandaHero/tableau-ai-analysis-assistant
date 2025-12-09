# 设计文档

## 概述

本设计文档描述了 RAG 系统优化的技术方案，主要解决两个问题：
1. 置信度计算不准确（都是 1.0）
2. 已实现的 RAG 组件未被使用

### 当前问题分析

**问题 1: 置信度计算**

当前 `FieldIndexer._faiss_search()` 中的转换公式：
```python
# 内积分数范围 [-1, 1]，转换为 [0, 1]
similarity = (score + 1.0) / 2.0
```

这个转换导致：
- 余弦相似度 0.8 → 转换后 0.9
- 余弦相似度 0.9 → 转换后 0.95
- 余弦相似度 1.0 → 转换后 1.0

当查询词和字段名完全匹配时，embedding 相似度接近 1.0，转换后仍是 1.0。

**问题 2: RAG 组件未使用**

当前字段映射流程：
```
test_e2e_workflow.py
    ↓
FieldIndexer.index_fields()  ← 直接使用
    ↓
SemanticMapper.map_field()   ← 只用向量检索
    ↓
返回结果
```

未使用的组件：
- `KnowledgeAssembler` - 分块策略
- `HybridRetriever` - 混合检索（向量 + BM25）
- `RRFReranker` - 重排序

## 架构

### 优化后的字段映射流程（两阶段检索架构）

```
┌─────────────────────────────────────────────────────────────┐
│                    两阶段检索架构                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  输入: 业务术语 (如 "销售额")                                │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 0. KnowledgeAssembler.load_metadata()               │   │
│  │    - 加载字段元数据                                  │   │
│  │    - 按字段分块 (BY_FIELD)                          │   │
│  │    - 使用 EmbeddingProvider 向量化字段元数据         │   │
│  │    - 构建 FAISS 向量索引                            │   │
│  │    - 构建 BM25 关键词索引 (jieba 分词)              │   │
│  └─────────────────────────────────────────────────────┘   │
│                          ↓                                  │
│  ╔═════════════════════════════════════════════════════╗   │
│  ║ 第一阶段: 召回 (Recall) - 快速、高召回率             ║   │
│  ╠═════════════════════════════════════════════════════╣   │
│  ║ 1. HybridRetriever.retrieve()                       ║   │
│  ║    ┌─────────────────────────────────────────────┐  ║   │
│  ║    │ EmbeddingRetriever (向量检索)               │  ║   │
│  ║    │  - 使用 EmbeddingProvider 向量化查询词      │  ║   │
│  ║    │  - FAISS 内积搜索 (余弦相似度)              │  ║   │
│  ║    │  - 返回语义相似的字段                       │  ║   │
│  ║    └─────────────────────────────────────────────┘  ║   │
│  ║    ┌─────────────────────────────────────────────┐  ║   │
│  ║    │ KeywordRetriever (BM25 检索)                │  ║   │
│  ║    │  - jieba 分词查询词                         │  ║   │
│  ║    │  - BM25 关键词匹配                          │  ║   │
│  ║    │  - 返回关键词匹配的字段                     │  ║   │
│  ║    └─────────────────────────────────────────────┘  ║   │
│  ║    - RRF 融合: score = Σ(1/(k+rank))                ║   │
│  ║    - 返回 top-5 候选                                ║   │
│  ╚═════════════════════════════════════════════════════╝   │
│                          ↓                                  │
│  ╔═════════════════════════════════════════════════════╗   │
│  ║ 第二阶段: 精排 (Rerank) - 高精度、语义理解          ║   │
│  ╠═════════════════════════════════════════════════════╣   │
│  ║ 2. LLMReranker.rerank()                             ║   │
│  ║    - 使用 LLM 判断查询与候选的语义相关性            ║   │
│  ║    - 理解同义词、上下文、业务含义                   ║   │
│  ║    - 返回 top-3 精排结果                            ║   │
│  ╚═════════════════════════════════════════════════════╝   │
│                          ↓                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 3. 置信度评估                                        │   │
│  │    - confidence >= 0.9: 快速路径，直接返回           │   │
│  │    - confidence >= 0.7: 返回结果                     │   │
│  │    - confidence < 0.7: 返回结果 + 备选列表           │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  输出: FieldMappingResult (字段名, 置信度, 来源)            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Embedding 在流程中的作用

| 阶段 | Embedding 使用 | 说明 |
|------|---------------|------|
| 索引构建 | `EmbeddingProvider.embed_documents()` | 将字段元数据（名称、描述、样本值）转换为向量 |
| 查询检索 | `EmbeddingProvider.embed_query()` | 将用户查询词转换为向量 |
| 向量搜索 | FAISS 内积搜索 | 计算查询向量与字段向量的余弦相似度 |

### 两阶段架构说明

| 阶段 | 组件 | 目标 | 特点 |
|------|------|------|------|
| 第一阶段 | HybridRetriever | 高召回率 | 快速，毫秒级，不漏掉相关结果 |
| 第二阶段 | LLMReranker | 高精度 | 语义理解，找到最相关的结果 |

**为什么需要两阶段？**
- 向量检索 + BM25 能快速召回候选，但可能排序不够精准
- LLM 能理解复杂语义（如 "销售额" vs "营业收入"），但处理大量候选太慢
- 两阶段结合：先快速召回 5 个，再用 LLM 精排 3 个

## 架构整理：SemanticMapper vs FieldMapperNode

### 当前问题

1. **功能重叠**：`SemanticMapper` 和 `FieldMapperNode` 都实现了字段映射功能
2. **缓存混乱**：存在三套缓存机制（`SemanticMapper._history`、`FieldMappingCache`、`MappingCache`）
3. **职责不清**：两阶段检索应该在哪一层实现不明确

### 整理方案：两层架构，明确职责

```
┌─────────────────────────────────────────────────────────────┐
│                     FieldMapperNode                         │
│  (业务编排层)                                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 职责:                                                │   │
│  │ - 缓存管理（统一使用 MappingCache，SQLite 持久化）   │   │
│  │ - LLM 回退（低置信度时调用 LLMCandidateSelector）    │   │
│  │ - 维度层级信息提取                                   │   │
│  │ - 批量处理和并发控制                                 │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     SemanticMapper                          │
│  (RAG 能力层)                                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 职责:                                                │   │
│  │ - 两阶段检索（HybridRetriever + LLMReranker）        │   │
│  │ - 返回检索结果和置信度                               │   │
│  │ - 删除历史复用（由上层缓存处理）                     │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     FieldIndexer                            │
│  (索引层)                                                    │
│  - FAISS 向量索引                                           │
│  - 向量搜索                                                  │
└─────────────────────────────────────────────────────────────┘
```

### 缓存策略整理

#### 统一使用 StoreManager

发现 `storage/store_manager.py` 中已有完整的 `StoreManager` 实现，具备：
- SQLite 持久化
- TTL 过期机制
- 线程安全（RLock）
- 命名空间隔离
- WAL 模式优化
- 全局实例管理 `get_store_manager()`

**决策：删除所有冗余缓存类，统一使用 StoreManager**

#### 缓存命名空间设计

| 缓存内容 | 命名空间 | TTL | 说明 |
|---------|---------|-----|------|
| **Embedding 向量** | `("embedding_cache", model_name)` | 7天 | API 调用成本高，向量不会变化 |
| **字段映射结果** | `("field_mapping", datasource_luid)` | 24小时 | 同一数据源的映射关系稳定 |

#### 删除的冗余代码

| 文件 | 删除内容 | 原因 |
|------|---------|------|
| `rag/cache.py` | `VectorCache` 类 | 使用 StoreManager 替代 |
| `rag/cache.py` | `MappingCache` 类 | 使用 StoreManager 替代 |
| `rag/cache.py` | `CacheManager` 类 | 使用 StoreManager 替代 |
| `field_mapper/cache.py` | 整个文件 | 使用 StoreManager 替代 |
| `semantic_mapper.py` | `_history` 列表 | 由 StoreManager 缓存替代 |

#### 保留并修改的代码

| 文件 | 保留内容 | 修改 |
|------|---------|------|
| `rag/cache.py` | `CachedEmbeddingProvider` | 修改为使用 `get_store_manager()` |

#### 不需要缓存的

| 内容 | 原因 |
|------|------|
| LLM Rerank 结果 | 每次查询上下文不同，不应缓存 |
| FAISS 索引 | 已有持久化机制（`save_index`/`load_index`） |

### 修改计划

1. **FieldMapperNode**：
   - 删除 `FieldMappingCache`，改用 `MappingCache`
   - 保留 LLM 回退逻辑
   - 保留维度层级信息提取

2. **SemanticMapper**：
   - 删除 `_history` 历史复用机制
   - 保留两阶段检索（HybridRetriever + Reranker）
   - 简化为纯 RAG 检索层

3. **MappingCache**：
   - TTL 从 1 小时改为 24 小时
   - 添加 `datasource_luid` 索引

## RAG 组件使用情况

### 新设计中使用的组件

| 组件 | 文件 | 用途 | 状态 |
|------|------|------|------|
| `EmbeddingProvider` | `embeddings.py` | 向量化查询和文档 | ✅ 使用 |
| `ZhipuEmbedding` | `embeddings.py` | 智谱 AI Embedding 实现 | ✅ 使用 |
| `FieldIndexer` | `field_indexer.py` | FAISS 向量索引管理 | ✅ 使用（需修改置信度计算） |
| `EmbeddingRetriever` | `retriever.py` | 向量检索器 | ✅ 使用（HybridRetriever 内部） |
| `KeywordRetriever` | `retriever.py` | BM25 关键词检索器 | ✅ 使用（HybridRetriever 内部） |
| `HybridRetriever` | `retriever.py` | 混合检索器（向量+BM25+RRF） | ✅ 使用（第一阶段召回） |
| `LLMReranker` | `reranker.py` | LLM 重排序器 | ✅ 使用（第二阶段精排） |
| `KnowledgeAssembler` | `assembler.py` | 知识组装器 | ✅ 使用（元数据加载和索引构建） |
| `StoreManager` | `storage/store_manager.py` | 统一存储管理器 | ✅ 使用（所有缓存） |
| `CachedEmbeddingProvider` | `cache.py` | 带缓存的 Embedding 包装器 | ✅ 使用（修改后使用 StoreManager） |
| `SemanticMapper` | `semantic_mapper.py` | RAG 检索层 | ✅ 使用（简化后） |
| `RAGObserver` | `observability.py` | 可观测性（日志、指标） | ✅ 使用 |
| `FieldChunk` | `models.py` | 字段分块数据模型 | ✅ 使用 |
| `RetrievalResult` | `models.py` | 检索结果数据模型 | ✅ 使用（需添加 raw_score） |

### 新设计中不使用/废弃的组件

| 组件 | 文件 | 原因 |
|------|------|------|
| `RRFReranker` | `reranker.py` | 被 `LLMReranker` 替代（LLM 精度更高） |
| `DefaultReranker` | `reranker.py` | 仅按分数排序，精度不够 |
| `CrossEncoderReranker` | `reranker.py` | 需要额外 embedding 调用，不如 LLM |
| `VectorCache` | `rag/cache.py` | 使用 StoreManager 替代，删除 |
| `MappingCache` | `rag/cache.py` | 使用 StoreManager 替代，删除 |
| `CacheManager` | `rag/cache.py` | 使用 StoreManager 替代，删除 |
| `FieldMappingCache` | `field_mapper/cache.py` | 使用 StoreManager 替代，删除整个文件 |
| `SemanticMapper._history` | `semantic_mapper.py` | 由 StoreManager 缓存替代，删除 |
| `DimensionPatternStore` | `dimension_pattern.py` | 维度层级优化暂缓，后续单独实现 |
| `DimensionHierarchyRAG` | `dimension_pattern.py` | 维度层级优化暂缓，后续单独实现 |

### 组件关系图

```
┌─────────────────────────────────────────────────────────────┐
│                     FieldMapperNode                         │
│  (业务编排层)                                                │
│  - 缓存查找 (StoreManager)                                  │
│  - LLM 回退                                                  │
│  - 维度层级提取                                              │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│      StoreManager       │     │     SemanticMapper      │
│  (统一存储管理器)        │     │  (RAG 检索层)           │
│  - 命名空间隔离          │     │  - 两阶段检索           │
│  - TTL 过期机制          │     │  - 无缓存（由上层处理） │
│  - SQLite + WAL 模式     │     └─────────────────────────┘
│  - 线程安全              │                   │
└─────────────────────────┘                   ▼
         │                    ┌───────────────────────────────┐
         │                    │      KnowledgeAssembler       │
         │                    │  - 加载元数据                  │
         │                    │  - 创建 FieldIndexer          │
         │                    │  - 创建 HybridRetriever       │
         │                    └───────────────────────────────┘
         │                                    │
         │                    ┌───────────────┼───────────────┐
         │                    ▼               ▼               │
         │        ┌─────────────────┐ ┌─────────────────────┐ │
         │        │  FieldIndexer   │ │ CachedEmbedding     │ │
         │        │  - FAISS 索引   │ │ Provider            │ │
         │        └─────────────────┘ │  - 包装 Embedding   │ │
         │                            │  - 使用 StoreManager │ │
         └────────────────────────────┤  - 命名空间:        │ │
                                      │    embedding_cache  │ │
                                      └─────────────────────┘ │
                                              │               │
                                              ▼               │
                              ┌───────────────────────────────┘
                              │
                              ▼
                  ┌───────────────────────────────┐
                  │        HybridRetriever        │
                  │  ┌───────────┐ ┌───────────┐ │
                  │  │ Embedding │ │  Keyword  │ │
                  │  │ Retriever │ │ Retriever │ │
                  │  └───────────┘ └───────────┘ │
                  │         RRF 融合              │
                  └───────────────────────────────┘
                                │
                                ▼
                  ┌───────────────────────────────┐
                  │         LLMReranker           │
                  │  - LLM 语义理解               │
                  │  - 精排 top-3                 │
                  └───────────────────────────────┘
```

### StoreManager 命名空间设计

```
data/business_cache.db
├── ("field_mapping", datasource_luid)     # 字段映射结果，TTL=24h
├── ("embedding_cache", model_name)        # Embedding 向量，TTL=7d
├── ("metadata",)                          # 元数据缓存，TTL=24h
├── ("dimension_hierarchy",)               # 维度层级，TTL=24h
├── ("data_model",)                        # 数据模型，TTL=24h
└── ...
```

## 组件和接口

### 1. FieldIndexer 修改

**修改点**: `_faiss_search()` 方法

```python
def _faiss_search(self, query_vector: List[float], top_k: int) -> List[Tuple[str, float, float]]:
    """
    使用 FAISS 进行向量搜索
    
    Returns:
        (field_name, confidence, raw_score) 列表
        - confidence: 归一化置信度 [0, 1]，使用 max(0, score) 而非 (score+1)/2
        - raw_score: 原始 FAISS 内积分数，用于调试
    """
    # ... 搜索逻辑 ...
    
    for score, idx in zip(scores_array[0], indices[0]):
        if idx >= 0 and idx < len(self._field_names):
            field_name = self._field_names[idx]
            # 修改: 直接使用余弦相似度，不做 (score+1)/2 转换
            # 归一化后的向量内积就是余弦相似度，范围 [-1, 1]
            # 对于正常的语义相似度，值通常在 [0, 1] 范围
            confidence = max(0.0, min(1.0, score))
            raw_score = float(score)
            scores.append((field_name, confidence, raw_score))
    
    return scores
```

### 2. RetrievalResult 修改

**修改点**: 添加 `raw_score` 字段

```python
@dataclass
class RetrievalResult:
    field_chunk: FieldChunk
    score: float           # 归一化置信度 [0, 1]
    source: RetrievalSource
    rank: int
    raw_score: Optional[float] = None  # 新增: 原始分数，用于调试
    rerank_score: Optional[float] = None
    original_rank: Optional[int] = None
```

### 3. 修改 FieldMapperNode

**修改现有类**: 在 `FieldMapperNode` 中集成完整的两阶段 RAG 流程

```python
class FieldMapperNode:
    """
    字段映射节点（修改后）
    
    使用两阶段检索架构：
    1. KnowledgeAssembler 加载元数据
    2. HybridRetriever 混合检索（第一阶段：召回）
    3. LLMReranker 精排序（第二阶段：精排）
    4. 置信度评估
    """
    
    def __init__(
        self,
        semantic_mapper: Optional[Any] = None,
        llm_selector: Optional[LLMCandidateSelector] = None,
        cache: Optional[FieldMappingCache] = None,
        config: Optional[FieldMappingConfig] = None,
        store_manager: Optional[Any] = None
    ):
        # ... 现有初始化代码 ...
        
        # 新增: KnowledgeAssembler 和 LLMReranker
        self._assembler: Optional[KnowledgeAssembler] = None
        self._reranker: Optional[LLMReranker] = None
    
    def load_metadata(self, fields: List[FieldMetadata], datasource_luid: str) -> int:
        """
        加载元数据并构建索引（新增方法）
        
        使用 KnowledgeAssembler 加载元数据，构建向量索引和 BM25 索引。
        """
        self._assembler = KnowledgeAssembler(
            datasource_luid=datasource_luid,
            config=AssemblerConfig(chunk_strategy=ChunkStrategy.BY_FIELD)
        )
        return self._assembler.load_metadata(fields)
    
    async def map_field(
        self,
        term: str,
        datasource_luid: str,
        context: Optional[str] = None,
        role_filter: Optional[str] = None
    ) -> MappingResult:
        """映射单个业务术语（修改后）"""
        start_time = time.time()
        latency = LatencyBreakdown()
        
        # 1. 检查缓存（现有逻辑）
        # ...
        
        # 2. 第一阶段: HybridRetriever 召回
        retrieval_start = time.time()
        retriever = self._assembler.as_retriever(
            retriever_type="hybrid",
            top_k=5  # 召回 5 个候选
        )
        filters = MetadataFilter(role=role_filter) if role_filter else None
        candidates = retriever.retrieve(query=term, filters=filters)
        latency.retrieval_ms = int((time.time() - retrieval_start) * 1000)
        
        if not candidates:
            return self._empty_result(term, latency)
        
        # 3. 第二阶段: LLMReranker 精排
        rerank_start = time.time()
        if self._reranker is None:
            self._reranker = RerankerFactory.create_llm_from_provider(
                provider="zhipu",
                model_name="glm-4-flash",
                top_k=3
            )
        reranked = self._reranker.rerank(term, candidates, top_k=3)
        latency.rerank_ms = int((time.time() - rerank_start) * 1000)
        
        # 4. 置信度评估
        top_result = reranked[0]
        confidence = top_result.score
        
        # 5. 根据置信度决定返回策略
        if confidence >= self.config.high_confidence_threshold:
            return self._fast_path_result(term, top_result, latency)
        else:
            return self._normal_result(term, top_result, reranked, latency)
```

## 数据模型

### LatencyBreakdown（已存在，无需修改）

```python
@dataclass
class LatencyBreakdown:
    embedding_ms: int = 0
    retrieval_ms: int = 0
    rerank_ms: int = 0
    disambiguation_ms: int = 0
    total_ms: int = 0
```

### MappingStats（新增）

```python
@dataclass
class MappingStats:
    """映射统计信息"""
    total_mappings: int = 0
    cache_hits: int = 0
    fast_path_hits: int = 0
    llm_fallback_count: int = 0
    hybrid_retrieval_count: int = 0
    
    def to_dict(self) -> Dict[str, int]:
        return asdict(self)
```

## 正确性属性

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: 余弦相似度范围

*For any* 查询向量和文档向量，FieldIndexer 返回的置信度应在 [0, 1] 范围内，且等于 max(0, cosine_similarity)

**Validates: Requirements 1.1**

### Property 2: 完全匹配置信度

*For any* 字段索引，当使用字段标题作为查询时，返回的置信度应在 [0.85, 0.95] 范围内

**Validates: Requirements 1.2**

### Property 3: 调试信息完整性

*For any* 检索结果，RetrievalResult 对象应同时包含 score（归一化置信度）和 raw_score（原始 FAISS 分数）

**Validates: Requirements 1.3**

### Property 4: 延迟分解完整性

*For any* 字段映射操作，返回的 LatencyBreakdown 应包含 embedding_ms、retrieval_ms、rerank_ms 三个非负整数

**Validates: Requirements 2.5**

## 错误处理

### jieba 不可用

当 jieba 分词器不可用时：
1. `KeywordRetriever` 使用 `Tokenizer.tokenize()` 的简单分词回退
2. 记录 WARNING 级别日志
3. 继续使用简单分词进行 BM25 检索

### Embedding 提供者不可用

当 Embedding 提供者不可用时：
1. `FieldIndexer.rag_available` 返回 False
2. `OptimizedFieldMapper` 直接使用 LLM 进行字段选择
3. 记录 WARNING 级别日志

## 测试策略

### 单元测试

1. `test_faiss_search_confidence_range` - 验证置信度在 [0, 1] 范围
2. `test_exact_match_confidence` - 验证完全匹配时置信度在 [0.85, 0.95]
3. `test_retrieval_result_has_raw_score` - 验证结果包含 raw_score
4. `test_hybrid_retriever_used` - 验证使用了混合检索器
5. `test_reranker_applied` - 验证应用了重排序

### 属性测试

使用 Hypothesis 库进行属性测试：

1. **Property 1 测试**: 生成随机向量，验证置信度范围
2. **Property 2 测试**: 使用字段标题查询，验证置信度范围
3. **Property 3 测试**: 执行检索，验证 raw_score 存在
4. **Property 4 测试**: 执行映射，验证延迟分解字段

### 集成测试

1. `test_e2e_field_mapping_with_hybrid` - 端到端测试完整流程
2. `test_jieba_fallback` - 测试 jieba 不可用时的降级
