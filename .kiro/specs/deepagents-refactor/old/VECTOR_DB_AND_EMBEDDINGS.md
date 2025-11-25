# 向量数据库和 Embedding 模型选择指南

## 📚 目的

本文档对比常见的向量数据库和 Embedding 模型，帮助团队做出合适的技术选型。

---

## 1. 向量数据库对比

### 1.1 FAISS（Facebook AI Similarity Search）

**简介**：Facebook 开发的高性能向量相似度搜索库

**优点**：
- ✅ **性能极高**：C++ 实现，速度最快
- ✅ **内存高效**：支持多种索引类型（Flat, IVF, HNSW）
- ✅ **无需服务**：本地库，无需额外部署
- ✅ **成熟稳定**：Facebook 生产环境验证
- ✅ **支持 GPU**：可以利用 GPU 加速

**缺点**：
- ❌ **无持久化**：需要手动保存/加载索引
- ❌ **无元数据过滤**：只支持向量搜索，不支持元数据过滤
- ❌ **无分布式**：单机部署，不支持分布式
- ❌ **API 较底层**：需要自己管理索引

**适用场景**：
- 单机部署
- 对性能要求极高
- 数据量中等（< 1000万向量）
- 不需要复杂的元数据过滤

**示例代码**：
```python
import faiss
import numpy as np

# 创建索引
dimension = 1536  # text-embedding-3-large 的维度
index = faiss.IndexFlatIP(dimension)  # 点积相似度

# 添加向量
vectors = np.random.random((1000, dimension)).astype('float32')
faiss.normalize_L2(vectors)  # 归一化
index.add(vectors)

# 搜索
query = np.random.random((1, dimension)).astype('float32')
faiss.normalize_L2(query)
distances, indices = index.search(query, k=5)

# 保存/加载
faiss.write_index(index, "index.faiss")
index = faiss.read_index("index.faiss")
```

---

### 1.2 Chroma

**简介**：专为 LLM 应用设计的向量数据库

**优点**：
- ✅ **易用性高**：API 简单，开箱即用
- ✅ **自动持久化**：自动保存到磁盘
- ✅ **元数据过滤**：支持复杂的元数据查询
- ✅ **LangChain 集成**：与 LangChain 无缝集成
- ✅ **支持多种 Embedding**：OpenAI, Sentence Transformers 等

**缺点**：
- ❌ **性能一般**：比 FAISS 慢
- ❌ **内存占用高**：需要加载整个索引到内存
- ❌ **分布式支持弱**：主要是单机部署
- ❌ **数据量限制**：不适合超大规模（> 1000万向量）

**适用场景**：
- 快速原型开发
- 中小规模数据（< 100万向量）
- 需要元数据过滤
- 与 LangChain 集成

**示例代码**：
```python
import chromadb
from chromadb.config import Settings

# 创建客户端
client = chromadb.Client(Settings(
    chroma_db_impl="duckdb+parquet",
    persist_directory="./chroma_db"
))

# 创建集合
collection = client.create_collection(
    name="fields",
    metadata={"description": "Tableau fields"}
)

# 添加文档
collection.add(
    documents=["Sales Amount", "Sales Count", "Profit"],
    metadatas=[
        {"role": "measure", "type": "REAL"},
        {"role": "measure", "type": "INTEGER"},
        {"role": "measure", "type": "REAL"}
    ],
    ids=["field1", "field2", "field3"]
)

# 搜索（自动 embedding）
results = collection.query(
    query_texts=["销售额"],
    n_results=5,
    where={"role": "measure"}  # 元数据过滤
)

# 持久化（自动）
client.persist()
```

---

### 1.3 Qdrant

**简介**：高性能的生产级向量数据库

**优点**：
- ✅ **性能优秀**：Rust 实现，接近 FAISS 的性能
- ✅ **功能完整**：持久化、元数据过滤、分布式
- ✅ **生产级**：支持高可用、备份、监控
- ✅ **API 友好**：RESTful API + gRPC
- ✅ **支持分布式**：可以水平扩展
- ✅ **支持多种索引**：HNSW, IVF 等

**缺点**：
- ❌ **需要部署服务**：需要运行 Qdrant 服务器
- ❌ **资源占用高**：需要独立的服务器资源
- ❌ **学习曲线**：比 Chroma 复杂

**适用场景**：
- 生产环境
- 大规模数据（> 1000万向量）
- 需要分布式部署
- 需要高可用

**示例代码**：
```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

# 创建客户端
client = QdrantClient(host="localhost", port=6333)

# 创建集合
client.create_collection(
    collection_name="fields",
    vectors_config=VectorParams(size=1536, distance=Distance.COSINE)
)

# 添加向量
points = [
    PointStruct(
        id=1,
        vector=[0.1] * 1536,
        payload={"name": "Sales Amount", "role": "measure"}
    ),
    PointStruct(
        id=2,
        vector=[0.2] * 1536,
        payload={"name": "Sales Count", "role": "measure"}
    )
]
client.upsert(collection_name="fields", points=points)

# 搜索
results = client.search(
    collection_name="fields",
    query_vector=[0.15] * 1536,
    limit=5,
    query_filter={
        "must": [
            {"key": "role", "match": {"value": "measure"}}
        ]
    }
)
```

---

### 1.4 对比表

| 特性 | FAISS | Chroma | Qdrant |
|------|-------|--------|--------|
| **性能** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **易用性** | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| **持久化** | ❌ 手动 | ✅ 自动 | ✅ 自动 |
| **元数据过滤** | ❌ | ✅ | ✅ |
| **分布式** | ❌ | ❌ | ✅ |
| **部署复杂度** | 低（本地库） | 低（本地库） | 中（需要服务） |
| **数据规模** | < 1000万 | < 100万 | > 1000万 |
| **LangChain 集成** | ✅ | ✅ | ✅ |
| **生产级** | ✅ | ⚠️ | ✅ |
| **开源** | ✅ | ✅ | ✅ |

---

### 1.5 推荐方案

#### 方案 1：FAISS（推荐用于 MVP）

**理由**：
- 性能最高
- 无需额外部署
- 适合单机部署
- 数据量可控（< 1000万字段）

**实施**：
```python
class FAISSFieldVectorStore:
    def __init__(self, dimension=1536):
        self.dimension = dimension
        self.index = faiss.IndexFlatIP(dimension)
        self.metadata = []
    
    def add(self, vectors, metadatas):
        vectors = np.array(vectors).astype('float32')
        faiss.normalize_L2(vectors)
        self.index.add(vectors)
        self.metadata.extend(metadatas)
    
    def search(self, query_vector, k=5):
        query_vector = np.array([query_vector]).astype('float32')
        faiss.normalize_L2(query_vector)
        distances, indices = self.index.search(query_vector, k)
        
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            results.append({
                "metadata": self.metadata[idx],
                "score": float(dist)
            })
        return results
    
    def save(self, path):
        faiss.write_index(self.index, f"{path}/index.faiss")
        with open(f"{path}/metadata.json", "w") as f:
            json.dump(self.metadata, f)
    
    def load(self, path):
        self.index = faiss.read_index(f"{path}/index.faiss")
        with open(f"{path}/metadata.json", "r") as f:
            self.metadata = json.load(f)
```

#### 方案 2：Chroma（推荐用于快速开发）

**理由**：
- 易用性高
- 自动持久化
- 支持元数据过滤
- LangChain 集成

**实施**：
```python
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

class ChromaFieldVectorStore:
    def __init__(self, persist_directory="./chroma_db"):
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
        self.vectorstore = Chroma(
            collection_name="fields",
            embedding_function=self.embeddings,
            persist_directory=persist_directory
        )
    
    def add(self, texts, metadatas):
        self.vectorstore.add_texts(texts=texts, metadatas=metadatas)
    
    def search(self, query, k=5, filter=None):
        results = self.vectorstore.similarity_search_with_score(
            query=query,
            k=k,
            filter=filter
        )
        return results
```

#### 方案 3：Qdrant（推荐用于生产环境）

**理由**：
- 生产级
- 高性能
- 支持分布式
- 功能完整

**实施**：需要先部署 Qdrant 服务

---

## 2. Embedding 模型对比

### 2.1 OpenAI Embeddings

#### text-embedding-3-large

**参数**：
- 维度：1536（可调整到 256-3072）
- 上下文窗口：8191 tokens
- 价格：$0.13 / 1M tokens

**优点**：
- ✅ **质量最高**：MTEB 排行榜 Top 3
- ✅ **多语言支持**：支持 100+ 语言
- ✅ **维度可调**：可以降低维度节省存储
- ✅ **API 稳定**：OpenAI 官方支持

**缺点**：
- ❌ **成本较高**：比开源模型贵
- ❌ **需要网络**：依赖 OpenAI API

**适用场景**：
- 对质量要求高
- 多语言支持
- 可以接受 API 成本

#### text-embedding-3-small

**参数**：
- 维度：1536
- 上下文窗口：8191 tokens
- 价格：$0.02 / 1M tokens

**优点**：
- ✅ **成本低**：比 large 便宜 6.5 倍
- ✅ **速度快**：比 large 快
- ✅ **质量不错**：MTEB 排行榜 Top 10

**缺点**：
- ❌ **质量略低**：比 large 低 5-10%

**适用场景**：
- 对成本敏感
- 对质量要求不是特别高

---

### 2.2 开源 Embeddings

#### sentence-transformers/all-MiniLM-L6-v2

**参数**：
- 维度：384
- 上下文窗口：256 tokens
- 价格：免费（本地运行）

**优点**：
- ✅ **完全免费**：无 API 成本
- ✅ **速度快**：模型小，推理快
- ✅ **本地运行**：无需网络

**缺点**：
- ❌ **质量一般**：比 OpenAI 低 20-30%
- ❌ **上下文短**：只支持 256 tokens
- ❌ **多语言弱**：主要支持英文

**适用场景**：
- 对成本极度敏感
- 数据量小
- 主要是英文

#### BAAI/bge-large-zh-v1.5

**参数**：
- 维度：1024
- 上下文窗口：512 tokens
- 价格：免费（本地运行）

**优点**：
- ✅ **中文优化**：专门针对中文优化
- ✅ **质量不错**：中文场景接近 OpenAI
- ✅ **完全免费**：无 API 成本

**缺点**：
- ❌ **英文较弱**：主要支持中文
- ❌ **需要 GPU**：模型较大，CPU 慢

**适用场景**：
- 主要是中文数据
- 有 GPU 资源
- 对成本敏感

---

### 2.3 对比表

| 模型 | 维度 | 质量 | 成本 | 速度 | 多语言 | 推荐场景 |
|------|------|------|------|------|--------|---------|
| **text-embedding-3-large** | 1536 | ⭐⭐⭐⭐⭐ | $0.13/1M | ⭐⭐⭐ | ✅ | 生产环境 |
| **text-embedding-3-small** | 1536 | ⭐⭐⭐⭐ | $0.02/1M | ⭐⭐⭐⭐ | ✅ | 成本敏感 |
| **all-MiniLM-L6-v2** | 384 | ⭐⭐⭐ | 免费 | ⭐⭐⭐⭐⭐ | ❌ | 英文 MVP |
| **bge-large-zh-v1.5** | 1024 | ⭐⭐⭐⭐ | 免费 | ⭐⭐⭐ | 中文 | 中文场景 |

---

### 2.4 推荐方案

#### 方案 1：text-embedding-3-large（推荐）

**理由**：
- 质量最高
- 多语言支持
- API 稳定
- 成本可接受

**成本估算**：
```
假设：
- 1000 个字段
- 每个字段平均 100 tokens
- 总 tokens：1000 * 100 = 100,000 tokens

成本：
- 一次性构建：100,000 / 1,000,000 * $0.13 = $0.013（约 ¥0.09）
- 每次查询：100 / 1,000,000 * $0.13 = $0.000013（约 ¥0.0001）

结论：成本极低，可以忽略
```

#### 方案 2：text-embedding-3-small（备选）

**理由**：
- 成本更低（6.5倍）
- 质量略低但可接受
- 适合成本敏感场景

#### 方案 3：bge-large-zh-v1.5（中文场景）

**理由**：
- 中文质量接近 OpenAI
- 完全免费
- 适合纯中文场景

---

## 3. 最终推荐

### 3.1 MVP 阶段

**向量数据库**：FAISS
**Embedding 模型**：text-embedding-3-large

**理由**：
- FAISS 性能最高，无需额外部署
- text-embedding-3-large 质量最高，成本可接受
- 快速验证方案可行性

### 3.2 生产环境

**向量数据库**：Qdrant
**Embedding 模型**：text-embedding-3-large

**理由**：
- Qdrant 生产级，支持分布式
- text-embedding-3-large 质量最高
- 长期稳定运行

### 3.3 成本敏感场景

**向量数据库**：FAISS
**Embedding 模型**：bge-large-zh-v1.5（中文）或 text-embedding-3-small（多语言）

**理由**：
- FAISS 免费
- 开源 Embedding 免费
- 质量略低但可接受

---

## 4. 实施建议

### Phase 1：MVP（1-2 周）

1. 使用 FAISS + text-embedding-3-large
2. 实现基础的向量检索
3. 验证方案可行性

### Phase 2：优化（2-3 周）

1. 添加元数据过滤
2. 优化索引性能
3. 添加缓存机制

### Phase 3：生产化（可选）

1. 迁移到 Qdrant
2. 添加分布式支持
3. 添加监控和告警

---

## 5. 代码示例

### 完整的 FAISS + OpenAI Embeddings 实现

```python
import faiss
import numpy as np
from langchain_openai import OpenAIEmbeddings
import json
from pathlib import Path

class FieldVectorStore:
    """字段向量存储（FAISS + OpenAI Embeddings）"""
    
    def __init__(
        self,
        embedding_model="text-embedding-3-large",
        dimension=1536,
        persist_directory="./vector_store"
    ):
        self.embeddings = OpenAIEmbeddings(model=embedding_model)
        self.dimension = dimension
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        
        # 创建 FAISS 索引
        self.index = faiss.IndexFlatIP(dimension)
        self.metadata = []
    
    def build_index(self, fields):
        """构建向量索引"""
        # 1. 构建富文本描述
        texts = [self._build_field_text(field) for field in fields]
        
        # 2. 生成向量
        vectors = self.embeddings.embed_documents(texts)
        vectors = np.array(vectors).astype('float32')
        
        # 3. 归一化（使点积等价于余弦相似度）
        faiss.normalize_L2(vectors)
        
        # 4. 添加到索引
        self.index.add(vectors)
        
        # 5. 保存元数据
        self.metadata = fields
        
        # 6. 持久化
        self.save()
    
    def search(self, query, k=5, threshold=0.5):
        """搜索候选字段"""
        # 1. 向量化查询
        query_vector = self.embeddings.embed_query(query)
        query_vector = np.array([query_vector]).astype('float32')
        faiss.normalize_L2(query_vector)
        
        # 2. 搜索
        scores, indices = self.index.search(query_vector, k)
        
        # 3. 过滤低分候选
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if score >= threshold:
                results.append({
                    "field": self.metadata[idx],
                    "score": float(score)
                })
        
        return results
    
    def _build_field_text(self, field):
        """构建字段的富文本描述"""
        parts = []
        parts.append(f"字段名: {field['field_name']}")
        if field.get('display_name'):
            parts.append(f"显示名: {field['display_name']}")
        parts.append(f"类型: {field['data_type']}")
        if field.get('description'):
            parts.append(f"描述: {field['description']}")
        if field.get('sample_values'):
            samples = ', '.join(str(v) for v in field['sample_values'][:3])
            parts.append(f"示例值: {samples}")
        
        return "\n".join(parts)
    
    def save(self):
        """持久化索引"""
        faiss.write_index(
            self.index,
            str(self.persist_directory / "index.faiss")
        )
        with open(self.persist_directory / "metadata.json", "w") as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)
    
    def load(self):
        """加载索引"""
        self.index = faiss.read_index(
            str(self.persist_directory / "index.faiss")
        )
        with open(self.persist_directory / "metadata.json", "r") as f:
            self.metadata = json.load(f)


# 使用示例
if __name__ == "__main__":
    # 1. 创建向量存储
    store = FieldVectorStore()
    
    # 2. 构建索引
    fields = [
        {
            "field_name": "[Sales].[Sales Amount]",
            "display_name": "销售额",
            "data_type": "measure",
            "description": "销售金额总和",
            "sample_values": [1000000, 500000, 250000]
        },
        {
            "field_name": "[Sales].[Sales Count]",
            "display_name": "销售数量",
            "data_type": "measure",
            "description": "销售订单数量",
            "sample_values": [100, 50, 25]
        }
    ]
    store.build_index(fields)
    
    # 3. 搜索
    results = store.search("销售额", k=5)
    for result in results:
        print(f"{result['field']['field_name']}: {result['score']:.2f}")
```

---

## 6. 总结

### 向量数据库选择

- **MVP**：FAISS（性能高，无需部署）
- **生产**：Qdrant（功能完整，支持分布式）
- **快速开发**：Chroma（易用性高，LangChain 集成）

### Embedding 模型选择

- **推荐**：text-embedding-3-large（质量最高）
- **成本敏感**：text-embedding-3-small（成本低）
- **中文场景**：bge-large-zh-v1.5（中文优化）

### 实施路径

1. **Phase 1**：FAISS + text-embedding-3-large（MVP）
2. **Phase 2**：优化和缓存
3. **Phase 3**：Qdrant（生产化，可选）



---

## 7. 补充：BCE Embedding 模型

### 7.1 maidalun1020/bce-embedding-base-v1

**简介**：网易有道开发的中英双语 Embedding 模型

**参数**：
- 维度：768
- 上下文窗口：512 tokens
- 价格：免费（本地运行）
- 模型大小：约 400MB

**性能**（MTEB 中文榜单）：
- 中文检索：**第1名**
- 中文分类：**第2名**
- 中文聚类：**第3名**
- 综合排名：**Top 3**

**优点**：
- ✅ **中文最强**：中文检索任务第1名
- ✅ **中英双语**：同时支持中文和英文
- ✅ **完全免费**：无 API 成本
- ✅ **质量接近 OpenAI**：中文场景甚至超过 text-embedding-3-large
- ✅ **开源**：可以本地部署

**缺点**：
- ❌ **需要 GPU**：CPU 推理较慢（约 100ms/query）
- ❌ **模型较大**：400MB，需要约 2GB 显存
- ❌ **上下文短**：只支持 512 tokens

**适用场景**：
- 主要是中文数据
- 有 GPU 资源
- 对成本极度敏感
- 对质量要求高

**性能对比**（中文检索任务）：

| 模型 | NDCG@10 | 成本 | 推理速度 |
|------|---------|------|---------|
| **bce-embedding-base-v1** | **0.707** | 免费 | 100ms (CPU) / 10ms (GPU) |
| text-embedding-3-large | 0.685 | $0.13/1M | 50ms (API) |
| text-embedding-3-small | 0.652 | $0.02/1M | 30ms (API) |
| bge-large-zh-v1.5 | 0.695 | 免费 | 120ms (CPU) / 15ms (GPU) |

**结论**：中文场景下，BCE 是最强的！

---

### 7.2 使用示例

```python
from sentence_transformers import SentenceTransformer

# 加载模型
model = SentenceTransformer('maidalun1020/bce-embedding-base-v1')

# 生成向量
texts = [
    "字段名: [Sales].[Sales Amount]\n显示名: 销售额\n类型: measure",
    "字段名: [Sales].[Sales Count]\n显示名: 销售数量\n类型: measure"
]
embeddings = model.encode(texts)

# 查询
query = "销售额"
query_embedding = model.encode([query])

# 计算相似度
from sklearn.metrics.pairwise import cosine_similarity
similarities = cosine_similarity(query_embedding, embeddings)
print(similarities)  # [[0.92, 0.75]]
```

---

### 7.3 性能优化

#### 使用 GPU 加速

```python
import torch

# 检查 GPU
device = "cuda" if torch.cuda.is_available() else "cpu"
model = SentenceTransformer('maidalun1020/bce-embedding-base-v1', device=device)

# 批量编码（更快）
embeddings = model.encode(texts, batch_size=32, show_progress_bar=True)
```

#### 使用 ONNX 加速

```python
# 转换为 ONNX 格式（推理速度提升 2-3x）
model.save("bce_model")

# 使用 ONNX Runtime
from optimum.onnxruntime import ORTModelForFeatureExtraction
ort_model = ORTModelForFeatureExtraction.from_pretrained("bce_model")
```

---

## 8. 最终推荐（更新）

### 8.1 性价比排行

| 排名 | 模型 | 质量（中文） | 成本 | 推理速度 | 综合评分 |
|------|------|-------------|------|---------|---------|
| 🥇 | **bce-embedding-base-v1** | ⭐⭐⭐⭐⭐ | 免费 | ⭐⭐⭐⭐ (GPU) | **最高** |
| 🥈 | text-embedding-3-large | ⭐⭐⭐⭐ | $0.13/1M | ⭐⭐⭐⭐⭐ (API) | 高 |
| 🥉 | text-embedding-3-small | ⭐⭐⭐ | $0.02/1M | ⭐⭐⭐⭐⭐ (API) | 中 |
| 4 | bge-large-zh-v1.5 | ⭐⭐⭐⭐ | 免费 | ⭐⭐⭐ (GPU) | 中 |

### 8.2 推荐方案（更新）

#### 方案 1：bce-embedding-base-v1（最推荐）⭐

**理由**：
- 中文质量最高（超过 OpenAI）
- 完全免费
- 性价比最高

**前提条件**：
- 有 GPU 资源（推荐）
- 或者可以接受 CPU 推理速度（100ms/query）

**实施**：
```python
class BCEFieldVectorStore:
    def __init__(self):
        self.model = SentenceTransformer(
            'maidalun1020/bce-embedding-base-v1',
            device='cuda' if torch.cuda.is_available() else 'cpu'
        )
        self.index = faiss.IndexFlatIP(768)  # BCE 维度是 768
        self.metadata = []
    
    def build_index(self, fields):
        texts = [self._build_field_text(field) for field in fields]
        vectors = self.model.encode(texts, batch_size=32)
        vectors = vectors.astype('float32')
        faiss.normalize_L2(vectors)
        self.index.add(vectors)
        self.metadata = fields
    
    def search(self, query, k=5):
        query_vector = self.model.encode([query])
        query_vector = query_vector.astype('float32')
        faiss.normalize_L2(query_vector)
        scores, indices = self.index.search(query_vector, k)
        
        results = []
        for score, idx in zip(scores[0], indices[0]):
            results.append({
                "field": self.metadata[idx],
                "score": float(score)
            })
        return results
```

#### 方案 2：text-embedding-3-large（备选）

**理由**：
- 无需 GPU
- API 调用，简单方便
- 多语言支持更好

**适用场景**：
- 没有 GPU 资源
- 需要多语言支持
- 可以接受 API 成本

#### 方案 3：text-embedding-3-small（成本敏感）

**理由**：
- 成本最低（$0.02/1M）
- 质量可接受
- API 调用，简单方便

---

## 9. 成本对比（1000 个字段）

| 方案 | 一次性构建 | 每次查询 | 年成本（10万次查询） | GPU 需求 |
|------|-----------|---------|---------------------|---------|
| **bce-embedding-base-v1** | **¥0** | **¥0** | **¥0** | 推荐（可选） |
| text-embedding-3-large | ¥0.09 | ¥0.0001 | ¥10 | 不需要 |
| text-embedding-3-small | ¥0.014 | ¥0.000015 | ¥1.5 | 不需要 |

**结论**：如果有 GPU，BCE 是最佳选择！

---

## 10. 实施建议（最终）

### Phase 1：MVP（1-2 周）

**推荐方案**：
- 向量数据库：FAISS
- Embedding 模型：**bce-embedding-base-v1**（如果有 GPU）或 text-embedding-3-large（如果没有 GPU）

**理由**：
- BCE 中文质量最高，完全免费
- FAISS 性能最高，无需部署

### Phase 2：优化（2-3 周）

1. 添加元数据过滤
2. 优化索引性能
3. 添加缓存机制
4. 如果使用 BCE，考虑 ONNX 优化

### Phase 3：生产化（可选）

1. 如果数据量增长，考虑迁移到 Qdrant
2. 如果需要分布式，部署 Qdrant 集群

---

## 11. 总结

### 最佳性价比方案

**有 GPU**：
- 向量数据库：FAISS
- Embedding 模型：**bce-embedding-base-v1**
- 成本：**¥0**
- 质量：**最高**

**无 GPU**：
- 向量数据库：FAISS
- Embedding 模型：text-embedding-3-large
- 成本：约 ¥10/年
- 质量：高

### 关键决策点

1. **有 GPU？** → 使用 BCE（免费 + 质量最高）
2. **无 GPU？** → 使用 OpenAI（简单 + 质量高）
3. **成本敏感？** → 使用 text-embedding-3-small（成本低）

