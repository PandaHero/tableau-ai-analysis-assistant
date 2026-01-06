# Dimension Hierarchy Agent 优化设计文档

## 1. 架构概览

### 1.1 核心思路：RAG 优先 + LLM 兜底 + 延迟加载样例数据

```
┌─────────────────────────────────────────────────────────────┐
│              Dimension Hierarchy Agent (Optimized)          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  字段元数据 ──→ 缓存检查（按 LUID + field_hash）            │
│  (无样例数据)              │                                │
│                            │ 命中 ──→ 直接返回（~0.1s）     │
│                            │                                │
│                            │ 未命中                         │
│                            v                                │
│                       RAG 检索（仅用元数据）                 │
│                       ┌─────────────────────┐               │
│                       │ 1. 批量 Embedding    │               │
│                       │    (1次API调用)      │               │
│                       │ 2. FAISS 向量检索    │               │
│                       │    (本地，~1-10ms)   │               │
│                       └─────────────────────┘               │
│                            │                                │
│           ┌────────────────┴────────────────┐               │
│           │                                 │               │
│           v                                 v               │
│     相似度 >= 0.92                   相似度 < 0.92          │
│     直接复用结果                     需要 LLM 推断          │
│     (无需查样例)                           │                │
│           │                                v                │
│           │                    只对未命中字段查询样例数据    │
│           │                          (延迟加载)             │
│           │                                │                │
│           │                                v                │
│           │                    LLM 一次性推断（≤30 字段）   │
│           │                    + 种子数据作为 few-shot      │
│           │                                │                │
│           │                                v                │
│           │                    高置信度(>=0.85)存入 RAG     │
│           │                          (永久)                 │
│           │                                │                │
│           └────────────────┬───────────────┘               │
│                            v                                │
│                    合并结果 + 存入缓存                      │
│                       (永久，field_hash 变化时失效)         │
│                            │                                │
│                            v                                │
│                        返回结果                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 关键优化：延迟加载样例数据

**问题**：查询样例数据是耗时操作（需要查询 Tableau 数据源），如果对所有字段都查询会导致耗时很长。

**解决方案**：
1. 缓存检查和 RAG 检索只用元数据（name, caption, dataType）
2. 只对 RAG 未命中的字段查询样例数据
3. 样例数据仅用于 LLM 推断

```
20 个字段，80% RAG 命中：
- 原方案：查询 20 个字段的样例数据 → 耗时 ~4s
- 优化后：只查询 4 个字段的样例数据 → 耗时 ~0.8s
```

### 1.3 存储架构：FAISS + LangGraph Store 分离

采用分离存储方案，各司其职：

| 存储 | 用途 | 技术选型 | 特点 |
|------|------|----------|------|
| **缓存** | 维度层级推断结果 | LangGraph Store (SQLite) | 键值存储，支持 TTL |
| **RAG 向量索引** | 维度模式向量检索 | FAISS（本地向量数据库） | 高效 ANN 检索 |
| **RAG 元数据** | 维度模式详情 | LangGraph Store (SQLite) | 与向量索引关联 |

```
┌─────────────────────────────────────────────────────────────┐
│                      存储架构（分离）                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           LangGraph Store (SQLite)                  │   │
│  │           文件: data/langgraph_store.db             │   │
│  │                                                     │   │
│  │  namespace: "dimension_hierarchy_cache"             │   │
│  │  ├── key: {datasource_luid} 或 {luid}:{tableId}    │   │
│  │  └── value: {field_hash, hierarchy_data}           │   │
│  │      └── TTL: 永久（field_hash 变化时失效）         │   │
│  │                                                     │   │
│  │  namespace: "dimension_patterns_metadata"           │   │
│  │  ├── key: {pattern_id}                             │   │
│  │  └── value:                                        │   │
│  │      ├── field_caption, category, level, ...       │   │
│  │      ├── source: "seed" | "llm" | "manual"         │   │
│  │      ├── verified: bool                            │   │
│  │      └── 不含 vector（向量存 FAISS）                │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              FAISS (向量索引)                        │   │
│  │              文件: data/indexes/dimension_patterns   │   │
│  │                                                     │   │
│  │  索引配置:                                          │   │
│  │  ├── 向量维度: 1024 (智谱 Embedding)                │   │
│  │  ├── 索引类型: IndexFlatIP (内积，余弦相似度)       │   │
│  │  ├── 元数据: pattern_id (关联 Store 中的详情)       │   │
│  │  └── 支持规模: 10000+ 向量                          │   │
│  │                                                     │   │
│  │  生命周期:                                          │   │
│  │  ├── 启动时从磁盘加载                               │   │
│  │  ├── 新增模式时增量更新内存索引                     │   │
│  │  ├── 定期/关闭时持久化到磁盘                        │   │
│  │  └── 删除模式时标记删除，定期重建                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**为什么使用 FAISS？**
- **免费开源**：Meta 开源，MIT License
- **高效检索**：支持 ANN（近似最近邻），比内存遍历快 10-100 倍
- **可扩展**：支持 10000+ 向量，满足大规模模式存储需求
- **LangChain 集成**：`langchain_community.vectorstores.FAISS`

**缓存粒度说明**：
- 单表数据源：缓存 key = `{datasource_luid}`
- 多表数据源（基于主题搭建的数据模型）：缓存 key = `{datasource_luid}:{logicalTableId}`
- 通过 `FieldMetadata.logicalTableId` 判断字段所属表
- 多表场景下，每个表独立缓存，避免单表字段变化导致整个数据源缓存失效

**FAISS 索引类型选择**：
| 索引类型 | 适用规模 | 特点 |
|----------|----------|------|
| IndexFlatIP | < 10000 | 精确搜索，无损失 |
| IndexIVFFlat | 10000-100000 | 倒排索引，需要训练 |
| IndexHNSW | 10000-1000000 | 图索引，高召回率 |

当前选择 `IndexFlatIP`，后续模式数量增长可切换到 `IndexIVFFlat`。

### 1.4 关键阈值配置

| 参数 | 值 | 说明 |
|------|-----|------|
| RAG 相似度阈值（seed/verified） | 0.92 | 高于此值直接复用 RAG 结果 |
| RAG 相似度阈值（llm/unverified） | 0.95 | LLM 推断结果需要更高阈值才能复用 |
| RAG 存储阈值 | 0.85 | LLM 推断置信度高于此值存入 RAG |
| 缓存 TTL | 永久 | 仅在 field_hash 变化时失效 |
| 单次 LLM 最大字段数 | 30 | 超过则分批处理 |

### 1.5 相似度定义与归一化策略（重要）

**问题**：FAISS `IndexFlatIP` 使用内积（Inner Product）计算相似度，只有当向量都做 L2 归一化后，内积才等价于余弦相似度。

**归一化策略**：

```
┌─────────────────────────────────────────────────────────────┐
│                  向量归一化流程                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  【入库时】                                                  │
│    文本 → Embedding API → 原始向量 → L2 归一化 → FAISS 存储 │
│                                                             │
│  【检索时】                                                  │
│    查询文本 → Embedding API → 原始向量 → L2 归一化 → 检索   │
│                                                             │
│  【结果】                                                    │
│    score = 归一化向量的内积 = 余弦相似度                    │
│    取值范围: [-1, 1]，越大越相似                            │
│    实际场景: 通常在 [0.5, 1.0] 之间                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**实现约束**：
1. **入库归一化**：`add_pattern()` 和 `batch_add_patterns()` 必须对向量做 L2 归一化
2. **查询归一化**：`batch_search()` 必须对查询向量做 L2 归一化
3. **分数方向**：score 越大越相似（1.0 = 完全相同，0.0 = 正交无关）

**阈值验证（Sanity Check）**：

| 测试用例 | 预期相似度 | 说明 |
|----------|-----------|------|
| "年" vs "年份" | > 0.92 | 同义词，应命中 |
| "Year" vs "年" | > 0.85 | 中英同义，应接近命中 |
| "年" vs "城市" | < 0.70 | 不同类别，应不命中 |
| "省份" vs "Province" | > 0.85 | 中英同义，应接近命中 |

**阈值校准验证集（用真实 Embedding API）**：

```python
# tableau_assistant/src/agents/dimension_hierarchy/tests/test_similarity_threshold.py

import pytest
from ..faiss_store import DimensionPatternFAISS

# 阈值校准验证对（用真实 Embedding，不用 mock）
THRESHOLD_VALIDATION_PAIRS = [
    # 同义词对（应 > 0.85，理想 > 0.92）
    ("字段名: 年 | 数据类型: integer", "字段名: 年份 | 数据类型: integer", 0.85, "同义词"),
    ("字段名: 城市 | 数据类型: string", "字段名: City | 数据类型: string", 0.85, "中英同义"),
    ("字段名: 产品类别 | 数据类型: string", "字段名: Category | 数据类型: string", 0.85, "中英同义"),
    ("字段名: 省份 | 数据类型: string", "字段名: Province | 数据类型: string", 0.85, "中英同义"),
    
    # 非同义对（应 < 0.80）
    ("字段名: 年 | 数据类型: integer", "字段名: 城市 | 数据类型: string", 0.80, "不同类别"),
    ("字段名: 客户名称 | 数据类型: string", "字段名: 产品类别 | 数据类型: string", 0.80, "不同类别"),
    ("字段名: 日期 | 数据类型: date", "字段名: 金额 | 数据类型: real", 0.80, "不同类别"),
]


@pytest.mark.asyncio
async def test_similarity_threshold_calibration(faiss_store: DimensionPatternFAISS):
    """
    验证相似度阈值合理性（用真实 Embedding API）
    
    这个测试确保：
    1. 同义词对的相似度 > 0.85
    2. 非同义对的相似度 < 0.80
    3. 0.92 阈值能有效区分同义/非同义
    """
    for text1, text2, threshold, desc in THRESHOLD_VALIDATION_PAIRS:
        # 计算相似度
        similarity = await compute_similarity(faiss_store, text1, text2)
        
        if "同义" in desc:
            assert similarity > threshold, f"{desc}: {text1} vs {text2} 应 > {threshold}，实际 {similarity:.3f}"
        else:
            assert similarity < threshold, f"{desc}: {text1} vs {text2} 应 < {threshold}，实际 {similarity:.3f}"


async def compute_similarity(faiss_store: DimensionPatternFAISS, text1: str, text2: str) -> float:
    """计算两个文本的余弦相似度"""
    import numpy as np
    import faiss
    
    # 批量计算 embedding
    vectors = faiss_store._embedding_provider.embed_documents([text1, text2])
    
    # L2 归一化
    v1 = np.array(vectors[0], dtype=np.float32).reshape(1, -1)
    v2 = np.array(vectors[1], dtype=np.float32).reshape(1, -1)
    faiss.normalize_L2(v1)
    faiss.normalize_L2(v2)
    
    # 计算余弦相似度（归一化后的内积）
    similarity = float(np.dot(v1, v2.T)[0][0])
    return similarity
```

**注意**：智谱 Embedding API 输出的向量**未归一化**，必须在入库和检索时手动归一化。

### 1.6 RAG 污染控制策略

**问题**：LLM 推断结果（`source=llm`）可能存在误判，如果直接以 0.92 阈值复用，会把错误固化。

**解决方案：阈值分层**

```python
# 根据 pattern 来源使用不同阈值
def get_similarity_threshold(pattern: Dict) -> float:
    source = pattern.get("source", "llm")
    verified = pattern.get("verified", False)
    
    if source == "seed" or verified:
        return 0.92  # 种子数据或已验证，使用标准阈值
    else:
        return 0.95  # LLM 推断且未验证，使用更高阈值
```

**污染控制机制**：

| 来源 | verified | 复用阈值 | 说明 |
|------|----------|---------|------|
| seed | True | 0.92 | 预置种子数据，可信度高 |
| manual | True | 0.92 | 人工添加/修正，可信度高 |
| llm | True | 0.92 | LLM 推断但已人工验证 |
| llm | False | 0.95 | LLM 推断未验证，需要更高相似度 |

**误判发现与回滚**：
1. **发现路径**：用户反馈推断结果错误 → 查询 `get_all_pattern_metadata()` → 定位 pattern_id
2. **回滚操作**：`delete_pattern_metadata(pattern_id)` + `rebuild_index()`
3. **验证标记**：对确认正确的 LLM 结果调用 `update_pattern_verified(pattern_id, True)`

### 1.7 pattern_id 生成规则

**问题**：原设计 `md5(field_caption|datasource_luid)` 未包含 `data_type`，可能导致同名不同类型字段碰撞。

**修正后的规则**：

```python
def generate_pattern_id(
    field_caption: str,
    data_type: str,
    datasource_luid: Optional[str] = None,
) -> str:
    """
    生成模式 ID
    
    规则：md5(field_caption|data_type|scope)[:16]
    - field_caption: 字段标题
    - data_type: 数据类型（避免同名不同类型碰撞）
    - scope: datasource_luid 或 "global"（种子数据）
    """
    scope = datasource_luid or "global"
    key = f"{field_caption}|{data_type}|{scope}"
    return hashlib.md5(key.encode()).hexdigest()[:16]
```

**示例**：
| field_caption | data_type | scope | pattern_id |
|---------------|-----------|-------|------------|
| 日期 | date | global | a1b2c3d4e5f6g7h8 |
| 日期 | string | global | x9y8z7w6v5u4t3s2 |
| 年 | integer | ds-123 | m1n2o3p4q5r6s7t8 |

### 1.8 部署假设与安全说明

**单进程假设**：
- 当前设计假设单进程部署（单 worker）
- `asyncio.Lock` 和 `_seed_initialized` 都是进程内状态
- 如果需要多进程/多实例部署，需要额外实现：
  - 分布式锁（Redis Lock / 文件锁）
  - 共享的初始化状态（Redis / 数据库标记）

**FAISS 安全说明**：
- `allow_dangerous_deserialization=True` 用于加载本地 FAISS 索引
- **安全前提**：索引文件仅由本服务生成，不接受外部上传
- 索引文件路径：`data/indexes/dimension_patterns/`
- 如果索引文件来源不可信，存在反序列化攻击风险

### 1.9 RAG 命中时的数据处理

**重要**：RAG 命中时，`sample_values` 和 `unique_count` 应设为 `None`，而不是从 RAG 复制：

```python
# RAG 命中时的结果构建
if pattern and similarity >= threshold:
    results[field.name] = DimensionAttributes(
        category=pattern["category"],
        category_detail=pattern["category_detail"],
        level=pattern["level"],
        granularity=pattern["granularity"],
        # 关键：设为 None，不从 RAG 复制
        unique_count=None,      # 不是 0
        sample_values=None,     # 不是 []
        level_confidence=similarity,
        reasoning=f"RAG match: {pattern['field_caption']} (similarity={similarity:.2f})",
    )
```

**原因**：
- RAG 中的 `sample_values` 和 `unique_count` 来自历史数据源
- 当前数据源的实际数据可能完全不同
- 设为 `None` 表示"未查询"，而不是"没有数据"
- 如果业务需要这些值，应该单独查询当前数据源

**模型修改**：需要修改 `DimensionAttributes` 模型，将 `unique_count` 和 `sample_values` 改为 `Optional`：

```python
# tableau_assistant/src/agents/dimension_hierarchy/models/hierarchy.py

class DimensionAttributes(BaseModel):
    # ... 其他字段 ...
    
    # 修改为 Optional，支持 RAG 命中时不查询样例数据
    unique_count: Optional[int] = Field(
        default=None,
        description="""<what>Unique value count</what>
<when>LLM 推断时必填，RAG 命中时可为 None</when>"""
    )
    
    sample_values: Optional[List[str]] = Field(
        default=None,
        description="""<what>Sample values list</what>
<when>LLM 推断时必填，RAG 命中时可为 None</when>
<rule>Maximum 10 values when provided</rule>"""
    )
```

### 1.6 并发安全控制

**问题**：多个请求同时推断同一数据源时，可能导致重复 LLM 调用。

**解决方案**：使用 `asyncio.Lock` 按数据源粒度加锁，并添加锁清理机制防止内存泄漏：

```python
import asyncio
import time
from typing import Dict

class DimensionHierarchyInference:
    def __init__(self, ...):
        # 按 datasource_luid 的锁，防止并发重复推断
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock_last_used: Dict[str, float] = {}  # 记录最后使用时间
        self._max_locks = 1000  # 最大锁数量
    
    def _get_lock(self, cache_key: str) -> asyncio.Lock:
        """获取或创建指定 cache_key 的锁（带清理机制）"""
        # 清理过期锁（超过最大数量时触发）
        if len(self._locks) > self._max_locks:
            self._cleanup_old_locks()
        
        if cache_key not in self._locks:
            self._locks[cache_key] = asyncio.Lock()
        
        self._lock_last_used[cache_key] = time.time()
        return self._locks[cache_key]
    
    def _cleanup_old_locks(self) -> None:
        """清理过期未使用的锁"""
        now = time.time()
        expired = [
            k for k, t in self._lock_last_used.items() 
            if now - t > 3600  # LOCK_EXPIRE_SECONDS
        ]
        for k in expired:
            if k in self._locks and not self._locks[k].locked():
                del self._locks[k]
                del self._lock_last_used[k]
    
    async def infer(self, fields, datasource_luid, ...):
        cache_key = self._build_cache_key(datasource_luid, fields)
        lock = self._get_lock(cache_key)
        
        async with lock:
            # 加锁后再次检查缓存（double-check）
            cache = self.storage.get_hierarchy_cache(cache_key)
            if cache and cache.get("field_hash") == field_hash:
                return cache  # 其他请求已完成推断
            
            # 执行推断...
```

**锁粒度**：
- 单表数据源：按 `datasource_luid` 加锁
- 多表数据源：按 `datasource_luid:logicalTableId` 加锁
- 不同数据源/表之间可以并发

**锁清理机制**：
- 当锁数量超过 1000 时触发清理
- 清理 1 小时未使用且未被持有的锁
- 防止长期运行导致内存泄漏

### 1.7 Embedding 模型选择

| 模型 | 提供商 | 维度 | 优点 | 缺点 |
|------|--------|------|------|------|
| **智谱 Embedding** | 智谱 AI | 1024 | 当前使用，稳定 | 中文语义理解一般 |
| **BGE-M3** | BAAI（北京智源） | 1024 | 开源、中英双语、语义理解强 | 需要本地部署或找托管服务 |
| **text2vec-large-chinese** | 哈工大 | 1024 | 开源、中文优化 | 英文支持弱 |

**推荐**：
- 当前阶段：继续使用智谱 Embedding，稳定可靠
- 后续优化：可考虑切换到 BGE-M3，语义理解更强，且支持本地部署降低成本
- BGE-M3 安装：`pip install FlagEmbedding`，支持 HuggingFace 加载

### 1.8 性能对比

| 方案 | 20 字段耗时 | Embedding 调用 | 样例查询 | LLM 调用 | 成本 |
|------|------------|----------------|----------|----------|------|
| 当前（分批 LLM） | ~6s | 20 次 | 20 字段 | 4 次 | ~$1.00 |
| **优化后（80% RAG 命中）** | ~1.5s | **1 次（批量）** | 4 字段 | 1 次 | ~$0.15 |
| 理想状态（95% RAG 命中） | ~0.5s | **1 次（批量）** | 1 字段 | 0.05 次 | ~$0.02 |

**批量 Embedding 优化效果：**
- 原方案：20 字段 = 20 次 Embedding API 调用 ≈ 2-4s
- 优化后：20 字段 = 1 次批量 Embedding API 调用 ≈ 0.2-0.3s
- **节省 90% 的 Embedding 耗时**

**注意**：智谱 Embedding API 支持批量调用，无明确的批量大小限制。


## 2. 详细设计

### 2.1 缓存存储层：LangGraph Store

```python
# tableau_assistant/src/agents/dimension_hierarchy/cache_storage.py

from typing import Dict, Any, List, Optional
import json
import hashlib
import logging
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

# Namespace 常量
NS_HIERARCHY_CACHE = "dimension_hierarchy_cache"
NS_DIMENSION_PATTERNS_METADATA = "dimension_patterns_metadata"

# 阈值常量
RAG_SIMILARITY_THRESHOLD = 0.92  # RAG 相似度阈值
RAG_STORE_CONFIDENCE_THRESHOLD = 0.85  # LLM 结果存入 RAG 的置信度阈值

# 并发控制常量
MAX_LOCKS = 1000  # 最大锁数量
LOCK_EXPIRE_SECONDS = 3600  # 锁过期时间（秒），1 小时


class PatternSource(str, Enum):
    """RAG 模式来源"""
    SEED = "seed"      # 种子数据（预置）
    LLM = "llm"        # LLM 推断结果
    MANUAL = "manual"  # 人工添加/修正


def compute_field_hash_metadata_only(dimension_fields: List[Any]) -> str:
    """
    计算字段列表的哈希值（仅用元数据，不含样例数据）
    
    用于缓存检查，避免因样例数据变化导致缓存失效
    """
    field_info = []
    for f in sorted(dimension_fields, key=lambda x: x.name):
        info = {
            "name": f.name,
            "caption": f.fieldCaption,
            "dataType": f.dataType,
            # 不包含 sample_values 和 unique_count
        }
        field_info.append(info)
    
    content = json.dumps(field_info, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(content.encode("utf-8")).hexdigest()


class DimensionHierarchyCacheStorage:
    """
    维度层级缓存存储层（LangGraph Store）
    
    职责：
    1. 维度层级缓存（按 datasource_luid，永久，field_hash 变化时失效）
    2. RAG 模式元数据（不含向量，向量存 FAISS）
    
    支持错误纠正：
    - delete_hierarchy_cache(): 删除指定数据源的缓存
    - delete_pattern_metadata(): 删除单个 RAG 模式元数据
    - clear_pattern_metadata(): 清空所有 RAG 模式元数据
    """
    
    def __init__(self, store=None):
        """
        Args:
            store: LangGraph SqliteStore 实例
        """
        self._store = store or self._get_default_store()
    
    def _get_default_store(self):
        """获取默认 LangGraph Store"""
        from tableau_assistant.src.infra.storage import get_langgraph_store
        return get_langgraph_store()
    
    # ═══════════════════════════════════════════════════════════
    # 维度层级缓存（永久，field_hash 变化时失效）
    # ═══════════════════════════════════════════════════════════
    
    def get_hierarchy_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """获取维度层级缓存"""
        if not cache_key or not self._store:
            return None
        
        try:
            item = self._store.get((NS_HIERARCHY_CACHE,), cache_key)
            if item and item.value:
                return item.value
        except Exception as e:
            logger.warning(f"获取缓存失败: {e}")
        
        return None
    
    def put_hierarchy_cache(
        self,
        cache_key: str,
        field_hash: str,
        field_meta_hashes: Dict[str, str],
        hierarchy_data: Dict[str, Any],
    ) -> bool:
        """
        存入维度层级缓存（永久，不设 TTL）
        
        Args:
            cache_key: 缓存 key（单表: luid, 多表: luid:tableId）
            field_hash: 整体字段列表 hash（用于快速判断是否需要增量检查）
            field_meta_hashes: 每个字段的元数据 hash（用于检测字段变更）
            hierarchy_data: 推断结果
        """
        if not cache_key or not self._store:
            return False
        
        try:
            data = {
                "cache_key": cache_key,
                "field_hash": field_hash,
                "field_meta_hashes": field_meta_hashes,  # 新增：每个字段的元数据 hash
                "hierarchy_data": hierarchy_data,
                "created_at": datetime.now().isoformat(),
            }
            
            self._store.put((NS_HIERARCHY_CACHE,), cache_key, data)
            logger.debug(f"缓存已更新: {cache_key}")
            return True
        except Exception as e:
            logger.warning(f"存入缓存失败: {e}")
            return False
    
    def delete_hierarchy_cache(self, cache_key: str) -> bool:
        """删除指定数据源的维度层级缓存"""
        if not cache_key or not self._store:
            return False
        
        try:
            self._store.delete((NS_HIERARCHY_CACHE,), cache_key)
            logger.info(f"缓存已删除: {cache_key}")
            return True
        except Exception as e:
            logger.warning(f"删除缓存失败: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════
    # RAG 模式元数据（不含向量，向量存 FAISS）
    # ═══════════════════════════════════════════════════════════
    
    def get_pattern_metadata(self, pattern_id: str) -> Optional[Dict[str, Any]]:
        """获取模式元数据"""
        if not pattern_id or not self._store:
            return None
        
        try:
            item = self._store.get((NS_DIMENSION_PATTERNS_METADATA,), pattern_id)
            if item and item.value:
                return item.value
        except Exception as e:
            logger.warning(f"获取模式元数据失败: {e}")
        
        return None
    
    def store_pattern_metadata(
        self,
        pattern_id: str,
        field_caption: str,
        data_type: str,
        sample_values: List[str],
        unique_count: int,
        category: str,
        category_detail: str,
        level: int,
        granularity: str,
        reasoning: str,
        confidence: float,
        datasource_luid: Optional[str] = None,
        source: PatternSource = PatternSource.LLM,
        verified: bool = False,
    ) -> bool:
        """
        存入 RAG 模式元数据（不含向量）
        
        向量存储在 FAISS 中，这里只存元数据
        """
        if not self._store:
            return False
        
        try:
            data = {
                "pattern_id": pattern_id,
                "field_caption": field_caption,
                "data_type": data_type,
                "sample_values": sample_values[:10] if sample_values else [],
                "unique_count": unique_count,
                "category": category,
                "category_detail": category_detail,
                "level": level,
                "granularity": granularity,
                "reasoning": reasoning,
                "confidence": confidence,
                "datasource_luid": datasource_luid,
                "source": source.value if isinstance(source, PatternSource) else source,
                "verified": verified,
                "created_at": datetime.now().isoformat(),
            }
            
            self._store.put((NS_DIMENSION_PATTERNS_METADATA,), pattern_id, data)
            logger.debug(f"模式元数据已存入: {field_caption} (source={source})")
            return True
            
        except Exception as e:
            logger.warning(f"存入模式元数据失败: {e}")
            return False
    
    def delete_pattern_metadata(self, pattern_id: str) -> bool:
        """删除单个 RAG 模式元数据"""
        if not self._store:
            return False
        
        try:
            self._store.delete((NS_DIMENSION_PATTERNS_METADATA,), pattern_id)
            logger.info(f"模式元数据已删除: {pattern_id}")
            return True
        except Exception as e:
            logger.warning(f"删除模式元数据失败: {e}")
            return False
    
    def update_pattern_verified(self, pattern_id: str, verified: bool) -> bool:
        """更新模式的验证状态"""
        metadata = self.get_pattern_metadata(pattern_id)
        if not metadata:
            return False
        
        try:
            metadata["verified"] = verified
            metadata["verified_at"] = datetime.now().isoformat() if verified else None
            
            self._store.put((NS_DIMENSION_PATTERNS_METADATA,), pattern_id, metadata)
            logger.info(f"模式验证状态已更新: {pattern_id} -> verified={verified}")
            return True
        except Exception as e:
            logger.warning(f"更新验证状态失败: {e}")
            return False
    
    def get_all_pattern_metadata(self) -> List[Dict[str, Any]]:
        """
        获取所有模式元数据（用于重建 FAISS 索引）
        
        Returns:
            所有模式元数据列表
        """
        if not self._store:
            return []
        
        try:
            # 搜索该 namespace 下的所有项
            items = self._store.search((NS_DIMENSION_PATTERNS_METADATA,))
            return [item.value for item in items if item and item.value]
        except Exception as e:
            logger.warning(f"获取所有模式元数据失败: {e}")
            return []
    
    def clear_pattern_metadata(self) -> int:
        """
        清空所有 RAG 模式元数据（谨慎使用！）
        
        用于完全重置 RAG 索引，通常配合 FAISS rebuild_index 使用
        
        Returns:
            删除的模式数量
        """
        if not self._store:
            return 0
        
        try:
            # 获取所有模式
            all_patterns = self.get_all_pattern_metadata()
            count = 0
            
            # 逐个删除
            for pattern in all_patterns:
                pattern_id = pattern.get("pattern_id")
                if pattern_id:
                    self._store.delete((NS_DIMENSION_PATTERNS_METADATA,), pattern_id)
                    count += 1
            
            logger.info(f"已清空所有模式元数据: {count} 个")
            return count
        except Exception as e:
            logger.warning(f"清空模式元数据失败: {e}")
            return 0
```


### 2.2 FAISS 向量索引

**Embedding 与 FAISS 的关系：**

```
┌─────────────────────────────────────────────────────────────┐
│                  RAG 检索完整流程                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  【存储阶段】                                                │
│    文本 "字段名: 年"                                        │
│         │                                                   │
│         v                                                   │
│    Embedding API (智谱) ──→ [0.12, -0.34, ..., 0.78]       │
│         │                    (1024维向量)                   │
│         v                                                   │
│    FAISS 索引存储                                           │
│                                                             │
│  【检索阶段】                                                │
│    查询文本 "字段名: 年份"                                  │
│         │                                                   │
│         v                                                   │
│    Embedding API (智谱) ──→ [0.11, -0.35, ..., 0.79]       │
│         │                    (查询向量)                     │
│         v                                                   │
│    FAISS 向量检索 ──→ 找到最相似: "年", 相似度 0.98        │
│                                                             │
│  【批量优化】                                                │
│    20个查询文本                                             │
│         │                                                   │
│         v                                                   │
│    批量 Embedding (1次API调用) ──→ 20个向量                │
│         │                                                   │
│         v                                                   │
│    FAISS 批量检索 (本地，~10ms) ──→ 20个结果               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

```python
# tableau_assistant/src/agents/dimension_hierarchy/faiss_store.py

from typing import List, Dict, Any, Optional, Tuple
import os
import logging
from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_core.documents import Document
import faiss

logger = logging.getLogger(__name__)

# 默认索引路径
DEFAULT_INDEX_PATH = "data/indexes/dimension_patterns"


class DimensionPatternFAISS:
    """
    维度模式 FAISS 向量索引
    
    职责：
    - 向量存储和高效检索（ANN）
    - 持久化到磁盘
    - 启动时加载
    
    与 LangGraph Store 配合：
    - FAISS 存向量 + pattern_id
    - LangGraph Store 存模式详情（category, level 等）
    """
    
    def __init__(
        self,
        embedding_provider,
        index_path: str = DEFAULT_INDEX_PATH,
        dimension: int = 1024,  # 智谱 Embedding 维度
    ):
        self._embedding_provider = embedding_provider
        self._index_path = index_path
        self._dimension = dimension
        self._vectorstore: Optional[FAISS] = None
        self._loaded = False
    
    def load_or_create(self) -> bool:
        """加载或创建索引"""
        if self._loaded:
            return True
        
        index_file = Path(self._index_path)
        
        if index_file.exists() and (index_file / "index.faiss").exists():
            try:
                self._vectorstore = FAISS.load_local(
                    str(index_file),
                    self._embedding_provider,
                    allow_dangerous_deserialization=True,
                )
                self._loaded = True
                logger.info(f"FAISS 索引已加载: {self._index_path}, 向量数: {self.count}")
                return True
            except Exception as e:
                logger.warning(f"加载 FAISS 索引失败: {e}，将创建新索引")
        
        # 创建空索引
        self._create_empty_index()
        self._loaded = True
        logger.info("FAISS 空索引已创建")
        return True
    
    def _create_empty_index(self):
        """创建空的 FAISS 索引"""
        # 使用 IndexFlatIP（内积）适合余弦相似度（需要归一化向量）
        index = faiss.IndexFlatIP(self._dimension)
        
        self._vectorstore = FAISS(
            embedding_function=self._embedding_provider,
            index=index,
            docstore=InMemoryDocstore({}),
            index_to_docstore_id={},
        )
    
    def add_pattern(
        self,
        pattern_id: str,
        text: str,  # 用于 embedding 的文本
        metadata: Dict[str, Any] = None,
    ) -> bool:
        """
        添加模式到索引（带归一化）
        
        注意：必须对向量做 L2 归一化，否则 IndexFlatIP 的内积不等于余弦相似度
        """
        if not self._loaded:
            self.load_or_create()
        
        try:
            # 1. 计算 embedding
            vector = self._embedding_provider.embed_query(text)
            
            # 2. L2 归一化（关键！）
            import numpy as np
            vector_array = np.array([vector], dtype=np.float32)
            faiss.normalize_L2(vector_array)
            
            # 3. 直接添加到 FAISS 索引
            doc_id = str(len(self._vectorstore.index_to_docstore_id))
            self._vectorstore.index.add(vector_array)
            
            # 4. 更新 docstore
            doc = Document(
                page_content=text,
                metadata={"pattern_id": pattern_id, **(metadata or {})},
            )
            self._vectorstore.docstore.add({doc_id: doc})
            self._vectorstore.index_to_docstore_id[self._vectorstore.index.ntotal - 1] = doc_id
            
            logger.debug(f"模式已添加到 FAISS: {pattern_id}")
            return True
        except Exception as e:
            logger.warning(f"添加模式到 FAISS 失败: {e}")
            return False
    
    def batch_add_patterns(
        self,
        patterns: List[Dict[str, Any]],
    ) -> int:
        """
        批量添加模式到索引（带归一化）
        
        Args:
            patterns: [{"pattern_id": str, "text": str, "metadata": dict}, ...]
        
        Returns:
            成功添加的数量
            
        注意：必须对向量做 L2 归一化，否则 IndexFlatIP 的内积不等于余弦相似度
        """
        if not self._loaded:
            self.load_or_create()
        
        if not patterns:
            return 0
        
        try:
            # 1. 批量计算 embedding
            texts = [p["text"] for p in patterns]
            vectors = self._embedding_provider.embed_documents(texts)
            
            # 2. L2 归一化（关键！）
            import numpy as np
            vectors_array = np.array(vectors, dtype=np.float32)
            faiss.normalize_L2(vectors_array)
            
            # 3. 批量添加到 FAISS 索引
            start_idx = self._vectorstore.index.ntotal
            self._vectorstore.index.add(vectors_array)
            
            # 4. 更新 docstore
            for i, p in enumerate(patterns):
                doc_id = str(start_idx + i)
                doc = Document(
                    page_content=p["text"],
                    metadata={"pattern_id": p["pattern_id"], **(p.get("metadata") or {})},
                )
                self._vectorstore.docstore.add({doc_id: doc})
                self._vectorstore.index_to_docstore_id[start_idx + i] = doc_id
            
            logger.info(f"批量添加 {len(patterns)} 个模式到 FAISS（已归一化）")
            return len(patterns)
        except Exception as e:
            logger.warning(f"批量添加模式失败: {e}")
            return 0
    
    def search(
        self,
        query_text: str,
        k: int = 5,
    ) -> List[Tuple[str, float]]:
        """
        检索相似模式
        
        Returns:
            [(pattern_id, similarity_score), ...]
        """
        if not self._loaded:
            self.load_or_create()
        
        if not self._vectorstore or self.count == 0:
            return []
        
        try:
            results = self._vectorstore.similarity_search_with_score(
                query_text, k=k
            )
            
            return [
                (doc.metadata.get("pattern_id", ""), score)
                for doc, score in results
            ]
        except Exception as e:
            logger.warning(f"FAISS 检索失败: {e}")
            return []
    
    def batch_search(
        self,
        query_texts: List[str],
        k: int = 1,
    ) -> List[List[Tuple[str, float]]]:
        """
        批量检索（真正的批量 Embedding，单次 API 调用）
        
        优化点：
        - 原方案：N 个查询 = N 次 Embedding API 调用
        - 优化后：N 个查询 = 1 次批量 Embedding API 调用
        
        Returns:
            [[(pattern_id, score), ...], ...]
        """
        if not self._loaded:
            self.load_or_create()
        
        if not self._vectorstore or self.count == 0 or not query_texts:
            return [[] for _ in query_texts]
        
        try:
            # 1. 批量计算 embedding（单次 API 调用）
            query_vectors = self._embedding_provider.embed_documents(query_texts)
            
            # 2. 批量向量检索（FAISS 原生支持）
            import numpy as np
            query_array = np.array(query_vectors, dtype=np.float32)
            
            # 归一化（IndexFlatIP 需要）
            faiss.normalize_L2(query_array)
            
            # 批量搜索
            scores, indices = self._vectorstore.index.search(query_array, k)
            
            # 3. 转换结果
            results = []
            for i in range(len(query_texts)):
                query_results = []
                for j in range(k):
                    idx = indices[i][j]
                    score = scores[i][j]
                    
                    if idx == -1:  # FAISS 返回 -1 表示无结果
                        continue
                    
                    # 从 docstore 获取 pattern_id
                    doc_id = self._vectorstore.index_to_docstore_id.get(idx)
                    if doc_id:
                        doc = self._vectorstore.docstore.search(doc_id)
                        if doc and hasattr(doc, 'metadata'):
                            pattern_id = doc.metadata.get("pattern_id", "")
                            query_results.append((pattern_id, float(score)))
                
                results.append(query_results)
            
            logger.info(f"批量检索完成: {len(query_texts)} 个查询, 1 次 Embedding API 调用")
            return results
            
        except Exception as e:
            logger.warning(f"批量检索失败: {e}，回退到逐个检索")
            # 回退到逐个检索
            return [self.search(text, k) for text in query_texts]
    
    def save(self) -> bool:
        """持久化到磁盘"""
        if not self._vectorstore:
            return False
        
        try:
            index_path = Path(self._index_path)
            index_path.mkdir(parents=True, exist_ok=True)
            
            self._vectorstore.save_local(str(index_path))
            logger.info(f"FAISS 索引已保存: {self._index_path}, 向量数: {self.count}")
            return True
        except Exception as e:
            logger.warning(f"保存 FAISS 索引失败: {e}")
            return False
    
    @property
    def count(self) -> int:
        """索引中的向量数量"""
        if not self._vectorstore:
            return 0
        return self._vectorstore.index.ntotal
    
    def rebuild_index(self, patterns: List[Dict[str, Any]]) -> bool:
        """
        重建索引（用于删除模式后）
        
        FAISS 不支持高效删除，需要重建索引
        """
        try:
            self._create_empty_index()
            self._loaded = True
            
            if patterns:
                self.batch_add_patterns(patterns)
            
            self.save()
            logger.info(f"FAISS 索引已重建: {len(patterns)} 个模式")
            return True
        except Exception as e:
            logger.warning(f"重建 FAISS 索引失败: {e}")
            return False
```


### 2.3 RAG 检索器（使用 FAISS）

```python
# tableau_assistant/src/agents/dimension_hierarchy/rag_retriever.py

from typing import List, Dict, Any, Optional, Tuple
import hashlib
import logging

from .faiss_store import DimensionPatternFAISS
from .cache_storage import (
    DimensionHierarchyCacheStorage,
    RAG_SIMILARITY_THRESHOLD,
)

logger = logging.getLogger(__name__)


class DimensionRAGRetriever:
    """
    维度模式 RAG 检索器（使用 FAISS）
    
    职责：
    - 批量检索相似模式（仅用元数据）
    - 从 FAISS 获取向量相似度
    - 从 LangGraph Store 获取模式详情
    
    与存储层配合：
    - FAISS: 向量检索，返回 pattern_id + similarity
    - LangGraph Store: 根据 pattern_id 获取完整模式信息
    
    Embedding 说明：
    - FAISS 内部使用 embedding_provider 计算向量
    - 检索时：FAISS 自动将查询文本转为向量进行检索
    - 存储时：FAISS 自动将文本转为向量存入索引
    """
    
    def __init__(
        self,
        faiss_store: DimensionPatternFAISS,
        cache_storage: DimensionHierarchyCacheStorage,
        embedding_provider,  # 用于手动计算 embedding（如需要）
        similarity_threshold: float = RAG_SIMILARITY_THRESHOLD,
    ):
        self._faiss_store = faiss_store
        self._cache_storage = cache_storage
        self._embedding_provider = embedding_provider
        self.similarity_threshold = similarity_threshold
        self.similarity_threshold_unverified = 0.95  # LLM 推断未验证的更高阈值
    
    def _get_effective_threshold(self, pattern: Optional[Dict[str, Any]]) -> float:
        """
        根据 pattern 来源获取有效阈值（污染控制）
        
        - seed/verified: 使用标准阈值 0.92
        - llm/unverified: 使用更高阈值 0.95
        """
        if not pattern:
            return self.similarity_threshold
        
        source = pattern.get("source", "llm")
        verified = pattern.get("verified", False)
        
        if source == "seed" or verified:
            return self.similarity_threshold  # 0.92
        else:
            return self.similarity_threshold_unverified  # 0.95
    
    def batch_search_metadata_only(
        self,
        fields: List[Dict[str, Any]],
    ) -> Dict[str, Tuple[Optional[Dict[str, Any]], float]]:
        """
        批量检索（仅用元数据，不含样例数据）
        
        Args:
            fields: [{"field_name": str, "field_caption": str, "data_type": str}, ...]
        
        Returns:
            {field_name: (pattern_dict or None, similarity_score)}
            
        注意：使用阈值分层策略，LLM 推断未验证的结果需要更高相似度才能复用
        """
        if not fields:
            return {}
        
        results: Dict[str, Tuple[Optional[Dict[str, Any]], float]] = {}
        
        # 1. 构建查询文本（仅用元数据）
        query_texts = []
        field_names = []
        for f in fields:
            query_text = self._build_query_text_metadata_only(
                f["field_caption"],
                f["data_type"],
            )
            query_texts.append(query_text)
            field_names.append(f["field_name"])
        
        # 2. 批量 FAISS 检索
        search_results = self._faiss_store.batch_search(query_texts, k=1)
        
        # 3. 获取模式详情并判断是否命中（使用阈值分层）
        for i, field_name in enumerate(field_names):
            if not search_results[i]:
                results[field_name] = (None, 0.0)
                continue
            
            pattern_id, similarity = search_results[i][0]
            
            # 先获取 pattern 详情，再根据来源判断阈值
            pattern = self._cache_storage.get_pattern_metadata(pattern_id)
            effective_threshold = self._get_effective_threshold(pattern)
            
            if similarity >= effective_threshold:
                results[field_name] = (pattern, similarity)
            else:
                results[field_name] = (None, similarity)
        
        # 统计
        hit_count = sum(1 for _, (p, _) in results.items() if p is not None)
        logger.info(
            f"RAG 检索: {len(fields)} 字段, 命中 {hit_count} "
            f"({hit_count/len(fields)*100:.0f}%), 标准阈值={self.similarity_threshold}, 未验证阈值={self.similarity_threshold_unverified}"
        )
        
        return results
    
    def _build_query_text_metadata_only(
        self,
        field_caption: str,
        data_type: str,
    ) -> str:
        """构建查询文本（仅用元数据，不含样例数据）"""
        return f"字段名: {field_caption} | 数据类型: {data_type}"
    
    @staticmethod
    def generate_pattern_id(
        field_caption: str,
        data_type: str,
        datasource_luid: Optional[str] = None,
    ) -> str:
        """
        生成模式 ID
        
        规则：md5(field_caption|data_type|scope)[:16]
        包含 data_type 避免同名不同类型字段碰撞
        """
        scope = datasource_luid or "global"
        key = f"{field_caption}|{data_type}|{scope}"
        return hashlib.md5(key.encode()).hexdigest()[:16]
    
    def store_pattern(
        self,
        field_caption: str,
        data_type: str,
        category: str,
        category_detail: str,
        level: int,
        granularity: str,
        reasoning: str,
        confidence: float,
        datasource_luid: Optional[str] = None,
        sample_values: List[str] = None,
        unique_count: int = 0,
        source: str = "llm",
        verified: bool = False,
    ) -> bool:
        """
        存入 RAG 模式（FAISS + LangGraph Store）
        
        注意：此方法是同步的，因为 FAISS 和 LangGraph Store 操作都是同步的
        
        1. 生成 pattern_id
        2. 检查是否已存在（避免重复）
        3. 构建查询文本并添加到 FAISS
        4. 存储元数据到 LangGraph Store
        5. 保存 FAISS 索引到磁盘（每次添加后保存）
        """
        pattern_id = self.generate_pattern_id(field_caption, data_type, datasource_luid)
        
        # 检查是否已存在（避免 FAISS 中重复向量）
        existing = self._cache_storage.get_pattern_metadata(pattern_id)
        if existing:
            logger.debug(f"模式已存在，跳过: {pattern_id} ({field_caption})")
            return True
        
        # 1. 添加到 FAISS
        query_text = self._build_query_text_metadata_only(field_caption, data_type)
        self._faiss_store.add_pattern(
            pattern_id=pattern_id,
            text=query_text,
            metadata={"field_caption": field_caption, "data_type": data_type},
        )
        
        # 2. 保存 FAISS 索引到磁盘（每次添加后保存，确保持久化）
        self._faiss_store.save()
        
        # 3. 存储元数据到 LangGraph Store
        from .cache_storage import PatternSource
        source_enum = PatternSource(source) if isinstance(source, str) else source
        
        return self._cache_storage.store_pattern_metadata(
            pattern_id=pattern_id,
            field_caption=field_caption,
            data_type=data_type,
            sample_values=sample_values or [],
            unique_count=unique_count,
            category=category,
            category_detail=category_detail,
            level=level,
            granularity=granularity,
            reasoning=reasoning,
            confidence=confidence,
            datasource_luid=datasource_luid,
            source=source_enum,
            verified=verified,
        )
```


### 2.4 一次性 LLM 推断（带种子数据参考）

```python
# tableau_assistant/src/agents/dimension_hierarchy/llm_inference.py

from typing import List, Dict, Any
import json
import logging

from .models import DimensionHierarchyResult
from tableau_assistant.src.agents.base import get_llm, invoke_llm, parse_json_response
from .prompt import DIMENSION_HIERARCHY_PROMPT
from .seed_data import get_seed_few_shot_examples

logger = logging.getLogger(__name__)

# 单次推断的最大字段数（避免 token 超限）
MAX_FIELDS_PER_INFERENCE = 30


async def infer_dimensions_once(
    fields: List[Dict[str, Any]],
    include_seed_examples: bool = True,
) -> DimensionHierarchyResult:
    """
    一次性 LLM 推断所有字段
    
    Args:
        fields: 字段列表，每个包含 name, caption, dataType, sample_values, unique_count
               注意：此时字段已包含样例数据（延迟加载后）
        include_seed_examples: 是否包含种子数据作为 few-shot 参考
    
    Returns:
        DimensionHierarchyResult
    """
    if not fields:
        return DimensionHierarchyResult(dimension_hierarchy={})
    
    # 检查字段数量
    if len(fields) > MAX_FIELDS_PER_INFERENCE:
        logger.warning(
            f"字段数 {len(fields)} 超过限制 {MAX_FIELDS_PER_INFERENCE}，"
            f"将只推断前 {MAX_FIELDS_PER_INFERENCE} 个"
        )
        fields = fields[:MAX_FIELDS_PER_INFERENCE]
    
    # 构建输入数据
    dimensions_info = []
    for field in fields:
        info = {
            "name": field.get("name", ""),
            "caption": field.get("caption", field.get("field_caption", "")),
            "dataType": field.get("dataType", field.get("data_type", "")),
            "description": field.get("description", ""),
            "unique_count": field.get("unique_count", 0),
            "sample_values": (field.get("sample_values") or [])[:5],
        }
        dimensions_info.append(info)
    
    # 添加种子数据作为 few-shot 参考
    few_shot_section = ""
    if include_seed_examples:
        few_shot_examples = get_seed_few_shot_examples(fields)
        if few_shot_examples:
            few_shot_section = _build_few_shot_section(few_shot_examples)
    
    dimensions_str = json.dumps(dimensions_info, ensure_ascii=False, indent=2)
    if few_shot_section:
        dimensions_str = few_shot_section + "\n" + dimensions_str
    
    input_data = {"dimensions": dimensions_str}
    
    # 一次性 LLM 调用
    try:
        llm = get_llm(agent_name="dimension_hierarchy")
        messages = DIMENSION_HIERARCHY_PROMPT.format_messages(**input_data)
        
        logger.info(f"LLM 一次性推断: {len(fields)} 个字段")
        response = await invoke_llm(llm, messages)
        
        result = parse_json_response(response, DimensionHierarchyResult)
        logger.info(f"LLM 推断完成: {len(result.dimension_hierarchy)} 个字段")
        
        return result
        
    except Exception as e:
        logger.error(f"LLM 推断失败: {e}")
        return DimensionHierarchyResult(dimension_hierarchy={})


def _build_few_shot_section(few_shot_examples: List[str]) -> str:
    """构建 few-shot 示例部分"""
    if not few_shot_examples:
        return ""

    section = """**Reference Examples (from seed patterns):**

The following are pre-defined dimension patterns. Use them as reference for inference:

"""
    for i, example in enumerate(few_shot_examples[:3], 1):
        section += f"Example {i}:\n{example}\n\n"

    return section
```


### 2.5 主推断流程（增量推断 + 延迟加载样例数据 + 并发控制）

```python
# tableau_assistant/src/agents/dimension_hierarchy/inference.py

from typing import List, Dict, Any, Optional, Set
import asyncio
import logging

from .models import DimensionAttributes, DimensionHierarchyResult
from .cache_storage import (
    DimensionHierarchyCacheStorage,
    compute_field_hash_metadata_only,
    RAG_SIMILARITY_THRESHOLD,
    RAG_STORE_CONFIDENCE_THRESHOLD,
    MAX_LOCKS,
    LOCK_EXPIRE_SECONDS,
    PatternSource,
)
from .faiss_store import DimensionPatternFAISS
from .rag_retriever import DimensionRAGRetriever
from .llm_inference import infer_dimensions_once, MAX_FIELDS_PER_INFERENCE

logger = logging.getLogger(__name__)


def compute_single_field_hash(field: Any) -> str:
    """
    计算单个字段的元数据 hash
    
    用于检测字段元数据是否变化（caption/dataType 变化需要重新推断）
    """
    info = {
        "name": field.name,
        "caption": field.fieldCaption,
        "dataType": field.dataType,
    }
    content = json.dumps(info, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(content.encode("utf-8")).hexdigest()[:8]


def compute_incremental_fields(
    current_fields: List[Any],
    cached_data: Dict[str, Any],
) -> tuple[Set[str], Set[str], Set[str], Set[str]]:
    """
    计算增量字段（支持检测字段变更）
    
    Args:
        current_fields: 当前字段列表
        cached_data: 缓存数据，包含 hierarchy_data 和 field_meta_hashes
    
    Returns:
        (new_fields, changed_fields, deleted_fields, unchanged_fields)
        - new_fields: 新增字段名集合（需要推断）
        - changed_fields: 变更字段名集合（元数据变化，需要重新推断）
        - deleted_fields: 删除字段名集合（从结果中移除）
        - unchanged_fields: 未变化字段名集合（复用缓存）
    
    注意：new_fields + changed_fields 都需要进入 RAG/LLM 推断流程
    """
    cached_hierarchy = cached_data.get("hierarchy_data", {})
    cached_hashes = cached_data.get("field_meta_hashes", {})
    
    current_names = {f.name for f in current_fields}
    cached_names = set(cached_hierarchy.keys())
    
    new_fields = set()
    changed_fields = set()
    unchanged_fields = set()
    
    for f in current_fields:
        if f.name not in cached_names:
            # 新增字段
            new_fields.add(f.name)
        else:
            # 已存在字段，检查元数据是否变化
            current_hash = compute_single_field_hash(f)
            cached_hash = cached_hashes.get(f.name, "")
            
            if current_hash != cached_hash:
                # 元数据变化，需要重新推断
                changed_fields.add(f.name)
            else:
                # 真正未变化
                unchanged_fields.add(f.name)
    
    deleted_fields = cached_names - current_names
    
    return new_fields, changed_fields, deleted_fields, unchanged_fields


def build_cache_key(
    datasource_luid: str,
    logical_table_id: Optional[str] = None,
) -> str:
    """
    构建缓存 key
    
    Args:
        datasource_luid: 数据源 LUID
        logical_table_id: 逻辑表 ID（多表数据源时使用）
    
    Returns:
        缓存 key
        - 单表: {datasource_luid}
        - 多表: {datasource_luid}:{logical_table_id}
    """
    if logical_table_id:
        return f"{datasource_luid}:{logical_table_id}"
    return datasource_luid


class DimensionHierarchyInference:
    """
    维度层级推断（增量推断 + RAG 优先 + LLM 兜底 + 延迟加载样例数据 + 并发控制）
    
    关键优化：
    1. 增量推断：只对新增/变更字段进行推断，复用缓存中未变化的字段
       - 新增字段：字段名不在缓存中
       - 变更字段：字段名在缓存中，但 caption/dataType 变化
       - 未变化字段：字段名和元数据都未变化
    2. 缓存检查和 RAG 检索只用元数据（不查样例数据）
    3. 只对 RAG 未命中的字段查询样例数据
    4. LLM 推断时带种子数据作为 few-shot 参考
    5. 并发控制：按 cache_key 加锁，防止重复 LLM 调用
    6. 启动时自动初始化种子数据
    
    错误纠正支持：
    - force_refresh: 强制刷新，跳过缓存
    - skip_rag_store: 跳过 RAG 存储（用于测试或不信任结果时）
    """
    
    def __init__(
        self,
        cache_storage: DimensionHierarchyCacheStorage,
        retriever: DimensionRAGRetriever,
        faiss_store: DimensionPatternFAISS,
        similarity_threshold: float = RAG_SIMILARITY_THRESHOLD,  # 默认 0.92
    ):
        self.cache_storage = cache_storage
        self.retriever = retriever
        self.faiss_store = faiss_store
        self.similarity_threshold = similarity_threshold
        
        # 并发控制：按 cache_key 的锁（带清理机制）
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock_last_used: Dict[str, float] = {}  # 记录最后使用时间
        self._max_locks = MAX_LOCKS  # 最大锁数量
        
        # 种子数据初始化标记
        self._seed_initialized = False
        
        # 统计（每次调用独立统计，通过 reset_stats 重置）
        self._total_fields = 0
        self._cache_reused = 0
        self._rag_hits = 0
        self._llm_inferred = 0
    
    def reset_stats(self) -> None:
        """重置统计数据（建议在每次独立推断前调用）"""
        self._total_fields = 0
        self._cache_reused = 0
        self._rag_hits = 0
        self._llm_inferred = 0
    
    async def _ensure_seed_data(self) -> None:
        """
        确保种子数据已初始化（启动时自动调用）
        
        检查 FAISS 索引是否为空，如果为空则初始化种子数据
        同时检查 FAISS 与 LangGraph Store 的一致性，不一致时自动修复
        """
        if self._seed_initialized:
            return
        
        try:
            # 加载或创建 FAISS 索引
            self.faiss_store.load_or_create()
            
            # 如果索引为空，初始化种子数据
            if self.faiss_store.count == 0:
                logger.info("FAISS 索引为空，开始初始化种子数据...")
                from .seed_data import initialize_seed_patterns
                count = await initialize_seed_patterns(self.retriever)
                if count == 0:
                    logger.warning("种子数据初始化失败，下次调用将重试")
                    return  # 不设置 _seed_initialized，下次会重试
            else:
                # 一致性检查：FAISS 向量数 vs LangGraph Store 元数据数
                metadata_count = len(self.cache_storage.get_all_pattern_metadata())
                faiss_count = self.faiss_store.count
                
                if faiss_count != metadata_count:
                    logger.warning(
                        f"FAISS 与 LangGraph Store 数据不一致: "
                        f"FAISS={faiss_count}, Store={metadata_count}. "
                        f"开始自动修复..."
                    )
                    # 自动修复：以 LangGraph Store 为准，重建 FAISS 索引
                    await self._auto_repair_consistency()
                else:
                    logger.info(f"FAISS 索引已存在，包含 {faiss_count} 个模式")
            
            self._seed_initialized = True
            
        except Exception as e:
            logger.error(f"种子数据初始化异常: {e}，下次调用将重试")
            # 不设置 _seed_initialized，下次会重试
    
    async def _auto_repair_consistency(self) -> None:
        """
        自动修复 FAISS 与 LangGraph Store 的一致性
        
        策略：以 LangGraph Store 为准，重建 FAISS 索引
        原因：
        - LangGraph Store 是持久化的 SQLite，数据更可靠
        - FAISS 索引可以从元数据重建
        - 如果 Store 中有数据但 FAISS 中没有，说明 FAISS 索引损坏或未保存
        - 如果 FAISS 中有数据但 Store 中没有，说明元数据丢失，这些向量无意义
        """
        try:
            # 获取所有元数据
            all_patterns = self.cache_storage.get_all_pattern_metadata()
            
            if not all_patterns:
                # Store 为空，清空 FAISS 并初始化种子数据
                logger.info("LangGraph Store 为空，重新初始化种子数据...")
                self.faiss_store._create_empty_index()
                self.faiss_store._loaded = True
                from .seed_data import initialize_seed_patterns
                await initialize_seed_patterns(self.retriever)
            else:
                # 以 Store 为准重建 FAISS 索引
                logger.info(f"以 LangGraph Store 为准重建 FAISS 索引: {len(all_patterns)} 个模式")
                
                # 准备 FAISS 数据
                patterns_to_add = []
                for pattern in all_patterns:
                    query_text = f"字段名: {pattern['field_caption']} | 数据类型: {pattern['data_type']}"
                    patterns_to_add.append({
                        "pattern_id": pattern["pattern_id"],
                        "text": query_text,
                        "metadata": {
                            "field_caption": pattern["field_caption"],
                            "data_type": pattern["data_type"],
                        },
                    })
                
                # 重建索引
                self.faiss_store.rebuild_index(patterns_to_add)
                logger.info(f"FAISS 索引重建完成: {self.faiss_store.count} 个向量")
                
        except Exception as e:
            logger.error(f"自动修复一致性失败: {e}")
    
    def _get_lock(self, cache_key: str) -> asyncio.Lock:
        """获取或创建指定 cache_key 的锁（带清理机制）"""
        import time
        
        # 清理过期锁（超过最大数量时触发）
        if len(self._locks) > self._max_locks:
            self._cleanup_old_locks()
        
        if cache_key not in self._locks:
            self._locks[cache_key] = asyncio.Lock()
        
        self._lock_last_used[cache_key] = time.time()
        return self._locks[cache_key]
    
    def _cleanup_old_locks(self) -> None:
        """清理过期未使用的锁（超过 LOCK_EXPIRE_SECONDS 未使用）"""
        import time
        now = time.time()
        expired = [
            k for k, t in self._lock_last_used.items() 
            if now - t > LOCK_EXPIRE_SECONDS  # 使用常量
        ]
        for k in expired:
            if k in self._locks and not self._locks[k].locked():
                del self._locks[k]
                del self._lock_last_used[k]
        
        if expired:
            logger.debug(f"清理了 {len(expired)} 个过期锁")
    
    async def infer(
        self,
        fields: List[Any],
        datasource_luid: Optional[str] = None,
        logical_table_id: Optional[str] = None,  # 多表数据源时指定
        sample_value_fetcher=None,  # 样例数据查询函数
        force_refresh: bool = False,  # 强制刷新，跳过缓存
        skip_rag_store: bool = False,  # 跳过 RAG 存储
    ) -> DimensionHierarchyResult:
        """
        推断维度层级
        
        流程：
        1. 获取锁（按 cache_key 粒度，防止并发重复推断）
        2. 缓存检查（用元数据 hash）- 可通过 force_refresh 跳过
           - 完全命中 → 直接返回
           - 部分命中 → 增量推断（只推断新增字段）
        3. 对新增字段进行 RAG 检索（仅用元数据）
        4. 只对 RAG 未命中字段查询样例数据（延迟加载）
        5. LLM 推断（一次性，带种子数据参考）
        6. 合并结果：缓存复用 + RAG 命中 + LLM 推断
        7. 更新缓存
        
        Args:
            logical_table_id: 逻辑表 ID，多表数据源时指定，用于细粒度缓存
            force_refresh: 强制刷新，跳过缓存检查（用于错误纠正）
            skip_rag_store: 跳过 RAG 存储（用于测试或不信任结果时）
        """
        if not fields:
            return DimensionHierarchyResult(dimension_hierarchy={})
        
        # 确保种子数据已初始化（首次调用时自动初始化）
        await self._ensure_seed_data()
        
        # 构建缓存 key
        cache_key = build_cache_key(datasource_luid, logical_table_id) if datasource_luid else None
        
        # 获取锁（防止并发重复推断）
        if cache_key:
            lock = self._get_lock(cache_key)
        else:
            lock = asyncio.Lock()  # 无 cache_key 时使用临时锁
        
        async with lock:
            return await self._infer_with_lock(
                fields=fields,
                cache_key=cache_key,
                datasource_luid=datasource_luid,
                sample_value_fetcher=sample_value_fetcher,
                force_refresh=force_refresh,
                skip_rag_store=skip_rag_store,
            )
    
    async def _infer_with_lock(
        self,
        fields: List[Any],
        cache_key: Optional[str],
        datasource_luid: Optional[str],
        sample_value_fetcher,
        force_refresh: bool,
        skip_rag_store: bool,
    ) -> DimensionHierarchyResult:
        """加锁后的推断逻辑"""
        self._total_fields += len(fields)
        results: Dict[str, DimensionAttributes] = {}
        fields_need_rag: List[Any] = []
        
        # 1. 缓存检查（可通过 force_refresh 跳过）
        field_hash = compute_field_hash_metadata_only(fields)
        cache = None
        
        if not force_refresh and cache_key:
            cache = self.cache_storage.get_hierarchy_cache(cache_key)
        elif force_refresh:
            logger.info("force_refresh=True，跳过缓存检查")
        
        if cache:
            cached_hash = cache.get("field_hash")
            cached_hierarchy = cache.get("hierarchy_data", {})
            
            if cached_hash == field_hash:
                # 完全命中，直接返回
                logger.info(f"缓存完全命中: {len(cached_hierarchy)} 个字段")
                hierarchy = {
                    name: DimensionAttributes(**attrs)
                    for name, attrs in cached_hierarchy.items()
                }
                return DimensionHierarchyResult(dimension_hierarchy=hierarchy)
            else:
                # 部分命中，增量推断（支持检测字段变更）
                new_fields, changed_fields, deleted_fields, unchanged_fields = compute_incremental_fields(
                    fields, cache  # 传入完整 cache，包含 field_meta_hashes
                )
                
                logger.info(
                    f"增量推断: 新增 {len(new_fields)}, "
                    f"变更 {len(changed_fields)}, "
                    f"删除 {len(deleted_fields)}, "
                    f"复用 {len(unchanged_fields)}"
                )
                
                # 复用未变化字段的缓存结果
                for field_name in unchanged_fields:
                    if field_name in cached_hierarchy:
                        results[field_name] = DimensionAttributes(**cached_hierarchy[field_name])
                        self._cache_reused += 1
                
                # 新增 + 变更字段都需要 RAG/LLM 推断
                fields_to_infer = new_fields | changed_fields
                fields_need_rag = [f for f in fields if f.name in fields_to_infer]
        else:
            # 无缓存，全量推断
            logger.info(f"无缓存，全量推断: {len(fields)} 个字段")
            fields_need_rag = fields
        
        # 2. 对需要推断的字段进行 RAG 检索（仅用元数据）
        if fields_need_rag:
            field_metadata = [
                {
                    "field_name": f.name,
                    "field_caption": f.fieldCaption,
                    "data_type": f.dataType,
                }
                for f in fields_need_rag
            ]
            
            rag_results = self.retriever.batch_search_metadata_only(field_metadata)
            
            # 3. 分离 RAG 命中和未命中
            fields_need_llm: List[Any] = []
            
            for field in fields_need_rag:
                pattern, similarity = rag_results.get(field.name, (None, 0.0))
                
                if pattern and similarity >= self.similarity_threshold:
                    # RAG 命中，直接复用
                    # 重要：sample_values 和 unique_count 设为 None，不从 RAG 复制
                    # 因为 RAG 数据来自历史数据源，当前数据源的数据可能不同
                    self._rag_hits += 1
                    results[field.name] = DimensionAttributes(
                        category=pattern["category"],
                        category_detail=pattern["category_detail"],
                        level=pattern["level"],
                        granularity=pattern["granularity"],
                        unique_count=None,      # 不是 0，表示"未查询"
                        sample_values=None,     # 不是 []，表示"未查询"
                        level_confidence=similarity,
                        reasoning=f"RAG match: {pattern['field_caption']} (similarity={similarity:.2f}, source={pattern.get('source', 'unknown')})",
                        parent_dimension=None,
                        child_dimension=None,
                    )
                else:
                    # 未命中，需要 LLM 推断
                    fields_need_llm.append(field)
            
            # 4. 只对 RAG 未命中字段查询样例数据 + LLM 推断
            if fields_need_llm:
                logger.info(f"RAG 未命中 {len(fields_need_llm)} 个字段，开始查询样例数据")
                
                # 延迟加载样例数据
                if sample_value_fetcher:
                    await sample_value_fetcher(fields_need_llm, datasource_luid)
                
                # LLM 推断
                llm_results = await self._infer_with_llm_batched(fields_need_llm)
                
                # 合并结果 + 存入 RAG（可通过 skip_rag_store 跳过）
                for field_name, attrs in llm_results.items():
                    results[field_name] = attrs
                    
                    # 高置信度结果存入 RAG 索引（永久）
                    # 使用配置的阈值（默认 0.85）
                    if not skip_rag_store and attrs.level_confidence >= RAG_STORE_CONFIDENCE_THRESHOLD:
                        field = next((f for f in fields_need_llm if f.name == field_name), None)
                        if field:
                            await self._store_to_rag(field, attrs, datasource_luid)
                    elif skip_rag_store:
                        logger.debug(f"skip_rag_store=True，跳过存储: {field_name}")
        
        # 5. 更新缓存（包含 field_meta_hashes 用于检测字段变更）
        if cache_key:
            hierarchy_data = {
                name: attrs.model_dump()
                for name, attrs in results.items()
            }
            # 构建每个字段的元数据 hash
            field_meta_hashes = {
                f.name: compute_single_field_hash(f)
                for f in fields
            }
            self.cache_storage.put_hierarchy_cache(
                cache_key=cache_key,
                field_hash=field_hash,
                field_meta_hashes=field_meta_hashes,
                hierarchy_data=hierarchy_data,
            )
        
        logger.info(
            f"推断完成: {len(fields)} 字段, "
            f"缓存复用 {self._cache_reused}, "
            f"RAG 命中 {self._rag_hits}, "
            f"LLM 推断 {self._llm_inferred}"
        )
        
        return DimensionHierarchyResult(dimension_hierarchy=results)
    async def _infer_with_llm_batched(
        self,
        fields: List[Any],
    ) -> Dict[str, DimensionAttributes]:
        """
        LLM 推断（分批处理超过 30 个的情况）
        """
        if len(fields) <= MAX_FIELDS_PER_INFERENCE:
            # 单次推断
            fields_data = [
                {
                    "name": f.name,
                    "caption": f.fieldCaption,
                    "dataType": f.dataType,
                    "sample_values": f.sample_values or [],
                    "unique_count": f.unique_count or 0,
                }
                for f in fields
            ]
            result = await infer_dimensions_once(fields_data)
            self._llm_inferred += len(result.dimension_hierarchy)  # 推断成功后再统计
            return dict(result.dimension_hierarchy)
        else:
            # 分批推断
            all_results = {}
            for i in range(0, len(fields), MAX_FIELDS_PER_INFERENCE):
                batch = fields[i:i + MAX_FIELDS_PER_INFERENCE]
                batch_data = [
                    {
                        "name": f.name,
                        "caption": f.fieldCaption,
                        "dataType": f.dataType,
                        "sample_values": f.sample_values or [],
                        "unique_count": f.unique_count or 0,
                    }
                    for f in batch
                ]
                result = await infer_dimensions_once(batch_data)
                all_results.update(result.dimension_hierarchy)
            self._llm_inferred += len(all_results)  # 推断成功后再统计
            return all_results
    
    async def _store_to_rag(
        self,
        field: Any,
        attrs: DimensionAttributes,
        datasource_luid: Optional[str],
    ) -> None:
        """存入 RAG 索引（FAISS + LangGraph Store，标记来源为 LLM）"""
        try:
            # 注意：store_pattern 是同步方法，这里不需要 await
            self.retriever.store_pattern(
                field_caption=field.fieldCaption,
                data_type=field.dataType,
                category=attrs.category,
                category_detail=attrs.category_detail,
                level=attrs.level,
                granularity=attrs.granularity,
                reasoning=attrs.reasoning,
                confidence=attrs.level_confidence,
                datasource_luid=datasource_luid,
                sample_values=field.sample_values or [],
                unique_count=field.unique_count or 0,
                source="llm",  # 标记来源为 LLM
                verified=False,  # 未经人工验证
            )
        except Exception as e:
            logger.warning(f"存入 RAG 失败: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计"""
        return {
            "total_fields": self._total_fields,
            "cache_reused": self._cache_reused,
            "rag_hits": self._rag_hits,
            "rag_hit_rate": self._rag_hits / max(1, self._total_fields - self._cache_reused),
            "llm_inferred": self._llm_inferred,
            "similarity_threshold": self.similarity_threshold,
            "store_confidence_threshold": RAG_STORE_CONFIDENCE_THRESHOLD,
        }
```


### 2.6 种子数据初始化

```python
# tableau_assistant/src/agents/dimension_hierarchy/seed_data.py

from typing import List, Dict, Any
import logging

from .cache_storage import PatternSource

logger = logging.getLogger(__name__)

SEED_PATTERNS = [
    # ═══════════════════════════════════════════════════════════
    # TIME 时间维度（10 个）
    # 层级：年 → 季度 → 月 → 周 → 日期
    # ═══════════════════════════════════════════════════════════
    {"field_caption": "年", "data_type": "integer", "category": "time", "category_detail": "time-year", "level": 1, "granularity": "coarsest", "unique_count": 10},
    {"field_caption": "Year", "data_type": "integer", "category": "time", "category_detail": "time-year", "level": 1, "granularity": "coarsest", "unique_count": 10},
    {"field_caption": "季度", "data_type": "string", "category": "time", "category_detail": "time-quarter", "level": 2, "granularity": "coarse", "unique_count": 40},
    {"field_caption": "Quarter", "data_type": "string", "category": "time", "category_detail": "time-quarter", "level": 2, "granularity": "coarse", "unique_count": 40},
    {"field_caption": "月", "data_type": "integer", "category": "time", "category_detail": "time-month", "level": 3, "granularity": "medium", "unique_count": 120},
    {"field_caption": "Month", "data_type": "integer", "category": "time", "category_detail": "time-month", "level": 3, "granularity": "medium", "unique_count": 120},
    {"field_caption": "周", "data_type": "integer", "category": "time", "category_detail": "time-week", "level": 4, "granularity": "fine", "unique_count": 520},
    {"field_caption": "Week", "data_type": "integer", "category": "time", "category_detail": "time-week", "level": 4, "granularity": "fine", "unique_count": 520},
    {"field_caption": "日期", "data_type": "date", "category": "time", "category_detail": "time-date", "level": 5, "granularity": "finest", "unique_count": 3650},
    {"field_caption": "Date", "data_type": "date", "category": "time", "category_detail": "time-date", "level": 5, "granularity": "finest", "unique_count": 3650},
    
    # ═══════════════════════════════════════════════════════════
    # GEOGRAPHY 地理维度（8 个）
    # 层级：国家/地区 → 省/州 → 市 → 区
    # ═══════════════════════════════════════════════════════════
    {"field_caption": "国家", "data_type": "string", "category": "geography", "category_detail": "geography-country", "level": 1, "granularity": "coarsest", "unique_count": 50},
    {"field_caption": "Country", "data_type": "string", "category": "geography", "category_detail": "geography-country", "level": 1, "granularity": "coarsest", "unique_count": 50},
    {"field_caption": "省份", "data_type": "string", "category": "geography", "category_detail": "geography-province", "level": 2, "granularity": "coarse", "unique_count": 31},
    {"field_caption": "State", "data_type": "string", "category": "geography", "category_detail": "geography-state", "level": 2, "granularity": "coarse", "unique_count": 50},
    {"field_caption": "城市", "data_type": "string", "category": "geography", "category_detail": "geography-city", "level": 3, "granularity": "medium", "unique_count": 300},
    {"field_caption": "City", "data_type": "string", "category": "geography", "category_detail": "geography-city", "level": 3, "granularity": "medium", "unique_count": 300},
    {"field_caption": "区县", "data_type": "string", "category": "geography", "category_detail": "geography-district", "level": 4, "granularity": "fine", "unique_count": 2800},
    {"field_caption": "District", "data_type": "string", "category": "geography", "category_detail": "geography-district", "level": 4, "granularity": "fine", "unique_count": 2800},
    
    # ═══════════════════════════════════════════════════════════
    # PRODUCT 产品维度（8 个）
    # 层级：类别 → 子类别 → 品牌 → 产品名称/SKU
    # ═══════════════════════════════════════════════════════════
    {"field_caption": "产品类别", "data_type": "string", "category": "product", "category_detail": "product-category", "level": 1, "granularity": "coarsest", "unique_count": 10},
    {"field_caption": "Category", "data_type": "string", "category": "product", "category_detail": "product-category", "level": 1, "granularity": "coarsest", "unique_count": 10},
    {"field_caption": "子类别", "data_type": "string", "category": "product", "category_detail": "product-subcategory", "level": 2, "granularity": "coarse", "unique_count": 50},
    {"field_caption": "Sub-Category", "data_type": "string", "category": "product", "category_detail": "product-subcategory", "level": 2, "granularity": "coarse", "unique_count": 50},
    {"field_caption": "品牌", "data_type": "string", "category": "product", "category_detail": "product-brand", "level": 3, "granularity": "medium", "unique_count": 200},
    {"field_caption": "Brand", "data_type": "string", "category": "product", "category_detail": "product-brand", "level": 3, "granularity": "medium", "unique_count": 200},
    {"field_caption": "产品名称", "data_type": "string", "category": "product", "category_detail": "product-name", "level": 4, "granularity": "fine", "unique_count": 1000},
    {"field_caption": "Product Name", "data_type": "string", "category": "product", "category_detail": "product-name", "level": 4, "granularity": "fine", "unique_count": 1000},
    
    # ═══════════════════════════════════════════════════════════
    # CUSTOMER 客户维度（6 个）
    # 层级：客户群/类型 → 客户等级 → 客户名称/ID
    # ═══════════════════════════════════════════════════════════
    {"field_caption": "客户群", "data_type": "string", "category": "customer", "category_detail": "customer-segment", "level": 1, "granularity": "coarsest", "unique_count": 5},
    {"field_caption": "Segment", "data_type": "string", "category": "customer", "category_detail": "customer-segment", "level": 1, "granularity": "coarsest", "unique_count": 5},
    {"field_caption": "客户等级", "data_type": "string", "category": "customer", "category_detail": "customer-tier", "level": 2, "granularity": "coarse", "unique_count": 10},
    {"field_caption": "Customer Tier", "data_type": "string", "category": "customer", "category_detail": "customer-tier", "level": 2, "granularity": "coarse", "unique_count": 10},
    {"field_caption": "客户名称", "data_type": "string", "category": "customer", "category_detail": "customer-name", "level": 4, "granularity": "fine", "unique_count": 1000},
    {"field_caption": "Customer Name", "data_type": "string", "category": "customer", "category_detail": "customer-name", "level": 4, "granularity": "fine", "unique_count": 1000},
    
    # ═══════════════════════════════════════════════════════════
    # ORGANIZATION 组织维度（6 个）
    # 层级：公司/事业部 → 部门 → 团队/员工
    # ═══════════════════════════════════════════════════════════
    {"field_caption": "事业部", "data_type": "string", "category": "organization", "category_detail": "organization-division", "level": 1, "granularity": "coarsest", "unique_count": 5},
    {"field_caption": "Division", "data_type": "string", "category": "organization", "category_detail": "organization-division", "level": 1, "granularity": "coarsest", "unique_count": 5},
    {"field_caption": "部门", "data_type": "string", "category": "organization", "category_detail": "organization-department", "level": 2, "granularity": "coarse", "unique_count": 20},
    {"field_caption": "Department", "data_type": "string", "category": "organization", "category_detail": "organization-department", "level": 2, "granularity": "coarse", "unique_count": 20},
    {"field_caption": "团队", "data_type": "string", "category": "organization", "category_detail": "organization-team", "level": 3, "granularity": "medium", "unique_count": 100},
    {"field_caption": "Team", "data_type": "string", "category": "organization", "category_detail": "organization-team", "level": 3, "granularity": "medium", "unique_count": 100},
    
    # ═══════════════════════════════════════════════════════════
    # FINANCIAL 财务维度（6 个）
    # 层级：科目大类 → 科目类别 → 科目明细
    # ═══════════════════════════════════════════════════════════
    {"field_caption": "科目大类", "data_type": "string", "category": "financial", "category_detail": "financial-account-group", "level": 1, "granularity": "coarsest", "unique_count": 5},
    {"field_caption": "Account Group", "data_type": "string", "category": "financial", "category_detail": "financial-account-group", "level": 1, "granularity": "coarsest", "unique_count": 5},
    {"field_caption": "科目类别", "data_type": "string", "category": "financial", "category_detail": "financial-account-category", "level": 2, "granularity": "coarse", "unique_count": 20},
    {"field_caption": "Account Category", "data_type": "string", "category": "financial", "category_detail": "financial-account-category", "level": 2, "granularity": "coarse", "unique_count": 20},
    {"field_caption": "科目明细", "data_type": "string", "category": "financial", "category_detail": "financial-account-detail", "level": 4, "granularity": "fine", "unique_count": 500},
    {"field_caption": "Account Detail", "data_type": "string", "category": "financial", "category_detail": "financial-account-detail", "level": 4, "granularity": "fine", "unique_count": 500},
]


def get_seed_few_shot_examples(fields: List[Any]) -> List[str]:
    """
    根据待推断字段，获取相关的种子数据作为 few-shot 示例
    
    Args:
        fields: 待推断的字段列表
    
    Returns:
        few-shot 示例列表
    """
    examples = []
    
    # 根据字段类型选择相关的种子数据
    field_types = set()
    for f in fields:
        data_type = getattr(f, 'dataType', '') or ''
        if 'date' in data_type.lower():
            field_types.add('time')
        elif 'string' in data_type.lower():
            field_types.add('geography')
            field_types.add('product')
            field_types.add('customer')
    
    # 每种类型选 1-2 个示例
    for pattern in SEED_PATTERNS:
        if pattern['category'] in field_types:
            example = f"""字段: {pattern['field_caption']}
数据类型: {pattern['data_type']}
唯一值数量: {pattern['unique_count']}

推断结果:
- 类别: {pattern['category']} ({pattern['category_detail']})
- 层级: {pattern['level']} ({pattern['granularity']})
- 推理: Seed pattern for {pattern['category']}"""
            examples.append(example)
            
            if len(examples) >= 3:
                break
    
    return examples


async def initialize_seed_patterns(
    retriever: "DimensionRAGRetriever",
) -> int:
    """
    初始化种子数据（FAISS + LangGraph Store，标记来源为 seed）
    
    调用时机：启动时自动初始化（当 FAISS 索引为空时）
    
    优化：批量添加到 FAISS 后统一保存一次，避免多次磁盘写入
    
    Args:
        retriever: RAG 检索器（包含 FAISS 和 LangGraph Store）
    
    Returns:
        存入的模式数量
    """
    from .rag_retriever import DimensionRAGRetriever
    from .cache_storage import PatternSource
    
    # 1. 批量准备 FAISS 数据（不保存）
    patterns_to_add = []
    for pattern in SEED_PATTERNS:
        pattern_id = DimensionRAGRetriever.generate_pattern_id(
            pattern["field_caption"],
            pattern["data_type"],  # 必须包含 data_type 避免碰撞
            None  # 种子数据不绑定数据源，使用 "global"
        )
        query_text = f"字段名: {pattern['field_caption']} | 数据类型: {pattern['data_type']}"
        patterns_to_add.append({
            "pattern_id": pattern_id,
            "text": query_text,
            "metadata": {
                "field_caption": pattern["field_caption"],
                "data_type": pattern["data_type"],
            },
        })
    
    # 2. 批量添加到 FAISS
    retriever._faiss_store.batch_add_patterns(patterns_to_add)
    
    # 3. 统一保存 FAISS 索引（只保存一次）
    retriever._faiss_store.save()
    
    # 4. 存储元数据到 LangGraph Store
    count = 0
    for pattern in SEED_PATTERNS:
        try:
            pattern_id = DimensionRAGRetriever.generate_pattern_id(
                pattern["field_caption"],
                pattern["data_type"],  # 必须包含 data_type 避免碰撞
                None  # 种子数据不绑定数据源，使用 "global"
            )
            retriever._cache_storage.store_pattern_metadata(
                pattern_id=pattern_id,
                field_caption=pattern["field_caption"],
                data_type=pattern["data_type"],
                sample_values=[],
                unique_count=pattern["unique_count"],
                category=pattern["category"],
                category_detail=pattern["category_detail"],
                level=pattern["level"],
                granularity=pattern["granularity"],
                reasoning="Seed pattern",
                confidence=0.95,
                datasource_luid=None,
                source=PatternSource.SEED,
                verified=True,
            )
            count += 1
        except Exception as e:
            logger.warning(f"存入种子数据元数据失败: {pattern['field_caption']}, {e}")
    
    logger.info(f"种子数据初始化完成: {count} 个模式（FAISS 只保存 1 次）")
    return count
```

## 3. 关键改动总结

| 项目 | 当前实现 | 优化后 |
|------|---------|--------|
| **存储架构** | LangGraph Store 统一存储 | **FAISS + LangGraph Store 分离** |
| **向量索引** | 无（内存遍历） | **FAISS 持久化索引** |
| **缓存 TTL** | 7 天 | 永久（仅 field_hash 变化时失效） |
| **缓存粒度** | 按 datasource_luid | 支持 datasource_luid:tableId（多表） |
| **RAG 模式 TTL** | - | 永久（种子 + 高置信度结果） |
| **RAG 相似度阈值** | - | 0.92（高于此值直接复用） |
| **RAG 存储阈值** | - | 0.85（LLM 置信度高于此值存入） |
| **RAG 命中时 sample_values** | - | 设为 None（不从 RAG 复制） |
| **RAG 重复检查** | - | 存入前检查 pattern_id 是否已存在 |
| **缓存策略** | 全量缓存 | 增量推断（只推断新增字段） |
| **RAG 作用** | 提供 few-shot 示例 | 直接复用结果 |
| **RAG 检索** | 需要样例数据 | 仅用元数据（延迟加载） |
| **RAG 模式字段** | 基础字段 | 新增 source、verified 字段 |
| **样例数据查询** | 所有字段都查 | 只查 RAG 未命中字段 |
| **LLM 推断** | 分批（batch_size=5） | 一次性（≤30 字段） |
| **超过 30 字段** | - | 分批推断 |
| **索引加载** | 每次重建 | **启动时从磁盘加载，增量更新** |
| **种子数据** | 无 | 30+ 常见模式（永久，source=seed） |
| **并发控制** | 无 | asyncio.Lock 按 cache_key 加锁（带清理） |
| **一致性检查** | 无 | 启动时检查 FAISS 与 Store 数据一致性，**不一致时自动修复** |
| **错误纠正** | 无 | delete_cache、delete_pattern、clear_pattern、**rebuild_index** |
| **强制刷新** | 无 | force_refresh 参数 |
| **跳过存储** | 无 | skip_rag_store 参数 |
| **统计重置** | 无 | reset_stats() 方法 |
| **Embedding 模型** | 智谱 Embedding | 智谱 Embedding（后续可选 BGE-M3） |

## 4. 实施计划

| 阶段 | 内容 | 工时 |
|------|------|------|
| Phase 1 | 缓存存储层（LangGraph Store）+ FAISS 向量索引 | 1d |
| Phase 2 | RAG 检索器（FAISS 检索 + 元数据关联） | 0.5d |
| Phase 3 | 一次性 LLM 推断 + 分批处理 | 0.5d |
| Phase 4 | 增量推断 + 种子数据 + 主流程集成 | 0.5d |
| Phase 5 | 测试 + 性能验证 | 0.5d |

**总计：3 天**

## 5. 预期效果

| 场景 | 当前 | 优化后 |
|------|------|--------|
| 首次推断（20 字段） | ~6s, 查 20 样例, 4 次 LLM | ~2s, 查 20 样例, 1 次 LLM |
| 重复推断（缓存命中） | ~0.1s | ~0.1s |
| 新增 1 字段（增量） | ~6s, 查 20 样例, 4 次 LLM | ~0.5s, 查 1 样例, 0-1 次 LLM |
| 相似字段（80% RAG 命中） | ~6s, 查 20 样例, 4 次 LLM | ~1s, 查 4 样例, 1 次 LLM |
| 稳定期（95% RAG 命中） | - | ~0.5s, 查 1 样例, 0.05 次 LLM |

## 6. 流程图

```
┌─────────────────────────────────────────────────────────────┐
│           完整推断流程（增量推断 + 并发控制）                 │
└─────────────────────────────────────────────────────────────┘

0. 启动时初始化（首次调用时自动执行）
   ├── 加载 FAISS 索引
   ├── 检查 FAISS 与 LangGraph Store 一致性
   │   ├── 一致 → 继续
   │   └── 不一致 → 自动修复（以 Store 为准重建 FAISS）
   └── 如果 FAISS 为空 → 初始化种子数据

1. 输入：字段元数据（name, caption, dataType, logicalTableId）
   注意：此时没有 sample_values
   可选参数：force_refresh, skip_rag_store, logical_table_id

2. 构建缓存 key
   ├── 单表数据源: cache_key = datasource_luid
   └── 多表数据源: cache_key = datasource_luid:logicalTableId

3. 获取锁（按 cache_key 粒度）
   async with self._get_lock(cache_key):
       # 防止并发重复推断

4. 缓存检查（按 cache_key）- 可通过 force_refresh=True 跳过
   ├── force_refresh=True → 跳过缓存，全量推断
   ├── 缓存不存在 → 全量推断
   └── 缓存存在 → 检查 field_hash
       ├── hash 相同 → 完全命中，直接返回（~0.1s）
       └── hash 不同 → 增量推断
           计算差集：
           ├── 新增字段 → 需要 RAG/LLM 推断
           ├── 删除字段 → 从结果中移除
           └── 未变化字段 → 直接复用缓存结果

5. 对新增字段进行 RAG 检索（仅用元数据）
   查询文本 = "字段名: {caption} | 数据类型: {dataType}"
   ├── 相似度 >= 0.92 → RAG 命中
   │   └── 复用 category, level 等
   │   └── sample_values = None（不从 RAG 复制！）
   │   └── unique_count = None（不从 RAG 复制！）
   └── 相似度 < 0.92 → RAG 未命中

6. 只对 RAG 未命中字段查询样例数据（关键优化！）
   await fetch_sample_values(未命中字段)

7. LLM 一次性推断
   ├── 未命中字段 <= 30 → 单次调用
   └── 未命中字段 > 30 → 分批调用（每批 30）
   输入包含：字段 + 样例数据 + 种子数据参考

8. 合并结果
   最终结果 = 缓存复用 + RAG 命中 + LLM 推断

9. 高置信度结果存入 RAG（可通过 skip_rag_store=True 跳过）
   if not skip_rag_store and confidence >= 0.85:
       store_to_rag(field, result, source="llm", verified=False)

10. 完整结果存入缓存（永久，field_hash 变化时失效）
    put_hierarchy_cache(cache_key, field_hash, results)

11. 返回结果
```

**并发控制说明**：
- 使用 `asyncio.Lock` 按 `cache_key` 粒度加锁
- 不同数据源/表之间可以并发
- 同一数据源/表的多个请求会排队，避免重复 LLM 调用
- 加锁后会再次检查缓存（double-check），如果其他请求已完成推断则直接返回

## 7. 错误纠正接口

当发现推断结果有误时，可使用以下接口进行纠正：

```python
# ═══════════════════════════════════════════════════════════
# 缓存纠正（LangGraph Store）
# ═══════════════════════════════════════════════════════════

# 1. 删除指定数据源的缓存（下次请求会重新推断）
# 单表数据源
storage.delete_hierarchy_cache(cache_key="datasource_luid")
# 多表数据源（删除指定表的缓存）
storage.delete_hierarchy_cache(cache_key="datasource_luid:table_id")

# ═══════════════════════════════════════════════════════════
# RAG 模式纠正（LangGraph Store + FAISS）
# ═══════════════════════════════════════════════════════════

# 2. 删除单个 RAG 模式元数据（避免错误模式被复用）
storage.delete_pattern_metadata(pattern_id="xxx")

# 3. 清空所有 RAG 模式元数据（谨慎使用！完全重置）
storage.clear_pattern_metadata()

# 4. 重建 FAISS 索引（删除模式后需要重建）
# 获取所有有效的模式，重建索引
all_patterns = storage.get_all_pattern_metadata()
faiss_store.rebuild_index(all_patterns)

# ═══════════════════════════════════════════════════════════
# 推断参数控制
# ═══════════════════════════════════════════════════════════

# 4. 强制刷新推断（跳过缓存）
result = await inference.infer(fields, force_refresh=True)

# 5. 推断但不存入 RAG（用于测试或不信任结果时）
result = await inference.infer(fields, skip_rag_store=True)

# ═══════════════════════════════════════════════════════════
# 模式验证
# ═══════════════════════════════════════════════════════════

# 6. 标记模式为已验证（人工确认后）
storage.update_pattern_verified(pattern_id="xxx", verified=True)

# ═══════════════════════════════════════════════════════════
# 多表数据源处理
# ═══════════════════════════════════════════════════════════

# 7. 多表数据源：按表推断
result = await inference.infer(
    fields=table_fields,
    datasource_luid="xxx",
    logical_table_id="table_id",  # 指定表 ID
)
```

**FAISS 索引重建说明**：
- FAISS 不支持高效的单条删除操作
- 删除模式后，需要调用 `rebuild_index()` 重建整个索引
- 重建时会从 LangGraph Store 读取所有有效模式的元数据
- 建议在批量删除后统一重建，避免频繁重建

## 8. 多表数据源处理

### 8.1 数据模型结构

Tableau 数据源分为两种：
- **单表数据源**：只有一个逻辑表，所有字段属于同一个表
- **多表数据源**（数据模型）：基于主题搭建，包含多个逻辑表和表关系

```python
# DataModel 关键属性
class DataModel:
    datasource_luid: str
    logical_tables: List[LogicalTable]  # 逻辑表列表
    logical_table_relationships: List[LogicalTableRelationship]  # 表关系
    fields: List[FieldMetadata]  # 所有字段
    
    @property
    def is_multi_table(self) -> bool:
        """是否为多表数据源"""
        return len(self.logical_tables) > 1
    
    def get_fields_by_table(self, table_id: str) -> List[FieldMetadata]:
        """获取指定表的字段"""
        return [f for f in self.fields if f.logicalTableId == table_id]

# FieldMetadata 关键属性
class FieldMetadata:
    name: str
    fieldCaption: str
    dataType: str
    logicalTableId: Optional[str]  # 所属逻辑表 ID
    logicalTableCaption: Optional[str]  # 所属逻辑表名称
```

### 8.2 调用层处理逻辑（dimension_hierarchy_agent node）

```python
# tableau_assistant/src/agents/dimension_hierarchy/node.py

async def dimension_hierarchy_node(state: AgentState) -> AgentState:
    """
    维度层级推断节点
    
    处理逻辑：
    1. 获取数据模型
    2. 判断单表/多表
    3. 单表：直接推断所有字段
    4. 多表：按表分组，并发推断，合并结果
    """
    data_model = state.data_model
    datasource_luid = data_model.datasource_luid
    
    # 获取所有维度字段
    dimension_fields = data_model.get_dimensions()
    
    if not data_model.is_multi_table:
        # ═══════════════════════════════════════════════════════════
        # 单表数据源：直接推断
        # ═══════════════════════════════════════════════════════════
        result = await inference.infer(
            fields=dimension_fields,
            datasource_luid=datasource_luid,
            sample_value_fetcher=sample_value_fetcher,
        )
        
        # 更新字段的维度层级属性
        _update_fields_with_hierarchy(data_model.fields, result.dimension_hierarchy)
        
        # 单表场景：直接使用推断结果
        merged_hierarchy = result.dimension_hierarchy
        
    else:
        # ═══════════════════════════════════════════════════════════
        # 多表数据源：按表分组，并发推断
        # ═══════════════════════════════════════════════════════════
        logger.info(f"多表数据源: {len(data_model.logical_tables)} 个逻辑表")
        
        # 按表分组字段
        table_fields_map: Dict[str, List[FieldMetadata]] = {}
        for table in data_model.logical_tables:
            table_id = table.logicalTableId
            fields = [f for f in dimension_fields if f.logicalTableId == table_id]
            if fields:
                table_fields_map[table_id] = fields
        
        # 并发推断各表（不同表之间可以并发）
        async def infer_table(table_id: str, fields: List[FieldMetadata]):
            return await inference.infer(
                fields=fields,
                datasource_luid=datasource_luid,
                logical_table_id=table_id,  # 指定表 ID，用于细粒度缓存
                sample_value_fetcher=sample_value_fetcher,
            )
        
        tasks = [
            infer_table(table_id, fields)
            for table_id, fields in table_fields_map.items()
        ]
        
        results = await asyncio.gather(*tasks)
        
        # 合并所有表的推断结果
        merged_hierarchy = {}
        for result in results:
            merged_hierarchy.update(result.dimension_hierarchy)
        
        # 更新字段的维度层级属性
        _update_fields_with_hierarchy(data_model.fields, merged_hierarchy)
    
    # 将维度层级结果存入 data_model
    data_model.dimension_hierarchy = merged_hierarchy
    
    return state


def _update_fields_with_hierarchy(
    fields: List[FieldMetadata],
    hierarchy: Dict[str, DimensionAttributes],
) -> None:
    """将推断结果更新到字段元数据"""
    for field in fields:
        if field.name in hierarchy:
            attrs = hierarchy[field.name]
            field.category = attrs.category
            field.category_detail = attrs.category_detail
            field.level = attrs.level
            field.granularity = attrs.granularity
            field.parent_dimension = attrs.parent_dimension
            field.child_dimension = attrs.child_dimension
```

### 8.3 缓存粒度

| 场景 | cache_key | 说明 |
|------|-----------|------|
| 单表数据源 | `{datasource_luid}` | 整个数据源一个缓存 |
| 多表数据源 | `{datasource_luid}:{logicalTableId}` | 每个表独立缓存 |

**优势**：
- 单表字段变化不会导致整个数据源缓存失效
- 可以并发推断不同表的字段
- 更细粒度的错误纠正（只清除特定表的缓存）

### 8.4 样例数据查询

多表场景下，样例数据查询也是按表进行的：

```python
async def sample_value_fetcher(
    fields: List[FieldMetadata],
    datasource_luid: str,
) -> None:
    """
    延迟加载样例数据
    
    注意：这个函数会修改 fields 列表中的字段，添加 sample_values 和 unique_count
    """
    # 获取一个度量字段用于 TOP 过滤
    measure_field = _get_measure_field(datasource_luid)
    
    # 查询样例数据
    samples_dict = await _fetch_dimension_samples_async(
        datasource_luid=datasource_luid,
        dimension_names=[f.name for f in fields],
        measure_field=measure_field,
    )
    
    # 更新字段
    for field in fields:
        if field.name in samples_dict:
            field.sample_values = samples_dict[field.name].get("sample_values", [])
            field.unique_count = samples_dict[field.name].get("unique_count", 0)
```

### 8.5 错误纠正（多表场景）

```python
# 清除单个表的缓存
storage.delete_hierarchy_cache(cache_key=f"{datasource_luid}:{table_id}")

# 清除整个数据源的所有表缓存
for table in data_model.logical_tables:
    storage.delete_hierarchy_cache(cache_key=f"{datasource_luid}:{table.logicalTableId}")

# 强制刷新单个表
result = await inference.infer(
    fields=table_fields,
    datasource_luid=datasource_luid,
    logical_table_id=table_id,
    force_refresh=True,
)
```
