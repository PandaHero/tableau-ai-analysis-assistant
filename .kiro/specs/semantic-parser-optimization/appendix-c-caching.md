# 附录 C: 缓存策略

## 概述

vNext 架构采用两级缓存策略，显著减少重复计算和 LLM 调用。

## 缓存层级

```
┌─────────────────────────────────────────────────────────────────┐
│  L1 缓存: 请求内 Memo                                           │
│  - 作用域: 单次请求/会话                                         │
│  - 存储: 内存 dict                                              │
│  - 用途: 同一轮重试复用、避免重复 embedding                      │
│  - TTL: 请求结束自动清理                                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  L2 缓存: SqliteStore                                           │
│  - 作用域: 跨请求/跨会话                                         │
│  - 存储: LangGraph SqliteStore (data/langgraph_store.db)        │
│  - 用途: 相同问题跨请求复用                                      │
│  - TTL: 可配置，默认 24 小时                                     │
└─────────────────────────────────────────────────────────────────┘
```

## 缓存键设计

### 核心原则

1. **使用 canonical_question**: 规范化后的问题，时间表达已标准化
2. **包含 current_date**: 相对时间跨天失效
3. **包含 datasource_luid**: 不同数据源隔离

### 缓存键生成

```python
import hashlib
from datetime import date

def build_cache_key(
    canonical_question: str,
    current_date: date,
    datasource_luid: str,
    cache_type: str,  # "schema_linking" | "step1" | "field_mapping"
) -> str:
    """
    构建缓存键
    
    格式: {cache_type}:{hash}
    hash = sha256(canonical_question + current_date + datasource_luid)
    """
    content = f"{canonical_question}|{current_date.isoformat()}|{datasource_luid}"
    hash_value = hashlib.sha256(content.encode()).hexdigest()[:16]
    return f"{cache_type}:{hash_value}"
```

### 示例

| 问题 | canonical_question | current_date | 缓存键 |
|------|-------------------|--------------|--------|
| "上月各地区销售额" | "time:last_month 各地区销售额" | 2024-01-15 | `schema_linking:a1b2c3d4...` |
| "上月各地区销售额" | "time:last_month 各地区销售额" | 2024-01-16 | `schema_linking:e5f6g7h8...` (不同) |
| "2024年1月各地区销售额" | "time:2024-01 各地区销售额" | 2024-01-15 | `schema_linking:i9j0k1l2...` |
| "2024年1月各地区销售额" | "time:2024-01 各地区销售额" | 2024-01-16 | `schema_linking:i9j0k1l2...` (相同) |

## 缓存内容

### 1. Schema Linking 缓存

```python
@dataclass
class SchemaLinkingCacheEntry:
    """Schema Linking 缓存条目"""
    schema_candidates: SchemaCandidates
    created_at: datetime
    ttl_seconds: int = 86400  # 24 小时
    
    def is_expired(self) -> bool:
        return (datetime.now() - self.created_at).total_seconds() > self.ttl_seconds
```

**缓存内容**:
- `dimensions`: 候选维度列表
- `measures`: 候选度量列表
- `filter_value_candidates`: 候选过滤值

**命中条件**:
- 相同 canonical_question
- 相同 current_date（相对时间）
- 相同 datasource_luid

### 2. Step1 缓存

```python
@dataclass
class Step1CacheEntry:
    """Step1 缓存条目"""
    step1_output: Step1Output
    created_at: datetime
    ttl_seconds: int = 3600  # 1 小时（更短，因为 LLM 输出可能需要更新）
    
    def is_expired(self) -> bool:
        return (datetime.now() - self.created_at).total_seconds() > self.ttl_seconds
```

**缓存内容**:
- `intent_type`: 意图类型
- `what`: 度量/维度选择
- `where`: 过滤条件
- `how_type`: 计算类型

**命中条件**:
- 相同 canonical_question
- 相同 current_date
- 相同 schema_candidates hash（确保候选集一致）

### 3. 字段映射缓存

```python
@dataclass
class FieldMappingCacheEntry:
    """字段映射缓存条目"""
    term: str
    matched_field: str
    confidence: float
    created_at: datetime
    ttl_seconds: int = 86400  # 24 小时
```

**缓存键**: `field_mapping:{hash(term + datasource_luid)}`

**命中条件**:
- 相同 term
- 相同 datasource_luid

## 缓存失效策略

### 1. 时间失效

| 缓存类型 | 默认 TTL | 说明 |
|----------|----------|------|
| Schema Linking | 24 小时 | 数据模型变化不频繁 |
| Step1 | 1 小时 | LLM 输出可能需要更新 |
| 字段映射 | 24 小时 | 字段映射稳定 |

### 2. 相对时间跨天失效

```python
def should_invalidate_for_relative_time(
    cache_entry: CacheEntry,
    current_date: date,
) -> bool:
    """检查相对时间缓存是否应该失效"""
    if not cache_entry.time_context:
        return False
    
    if not cache_entry.time_context.is_relative:
        return False  # 绝对时间不受影响
    
    # 相对时间：检查日期是否变化
    cached_date = cache_entry.created_at.date()
    return cached_date != current_date
```

### 3. 数据模型变更失效

```python
def invalidate_on_schema_change(
    datasource_luid: str,
    schema_version: str,
    cache: CandidateCache,
) -> None:
    """数据模型变更时清理缓存
    
    注意：SqliteStore 不支持 pattern delete（如 delete_pattern），
    因此采用 namespace 隔离策略，按 datasource_luid 整体失效。
    """
    # 方案：使用 invalidate_by_datasource 方法
    # 该方法内部通过 namespace 隔离实现按数据源清理
    cache.invalidate_by_datasource(datasource_luid)
```

## L1 缓存实现

```python
class RequestMemoCache:
    """请求内 Memo 缓存"""
    
    def __init__(self):
        self._cache: dict[str, Any] = {}
    
    def get(self, key: str) -> Any | None:
        return self._cache.get(key)
    
    def set(self, key: str, value: Any) -> None:
        self._cache[key] = value
    
    def clear(self) -> None:
        self._cache.clear()
    
    # 用于 embedding 缓存
    def get_embedding(self, text: str) -> list[float] | None:
        return self.get(f"embedding:{hash(text)}")
    
    def set_embedding(self, text: str, embedding: list[float]) -> None:
        self.set(f"embedding:{hash(text)}", embedding)
```

**使用场景**:
- 同一请求内多次 embedding 相同文本
- 重试时复用之前的 Schema Linking 结果
- 避免重复的字段映射查询

## L2 缓存实现

### 与现有 SqliteStore API 对齐

```python
from langgraph.store.base import BaseStore
from tableau_assistant.src.infra.storage.langgraph_store import get_langgraph_store

class CandidateCache:
    """候选集缓存 - 基于现有 LangGraph SqliteStore"""
    
    def __init__(
        self,
        store: BaseStore | None = None,
        namespace: str = "semantic_parser",
    ):
        # 复用现有全局单例
        self.store = store or get_langgraph_store()
        self.namespace = namespace
    
    def get(self, key: str) -> Any | None:
        """
        同步获取缓存
        
        注意：使用同步 API（与现有代码一致）
        """
        try:
            items = self.store.get(
                namespace=(self.namespace,),
                key=key,
            )
            if items and not self._is_expired(items):
                return items.value.get("data")
        except Exception as e:
            logger.warning(f"缓存读取失败: {e}")
        return None
    
    def set(
        self,
        key: str,
        value: Any,
        ttl_minutes: int = 1440,  # 注意：单位是分钟，与 SqliteStore 一致
    ) -> None:
        """
        同步设置缓存
        
        注意：TTL 单位是分钟（与 langgraph_store.py DEFAULT_TTL_MINUTES 一致）
        """
        try:
            self.store.put(
                namespace=(self.namespace,),
                key=key,
                value={
                    "data": value,
                    "created_at": datetime.now().isoformat(),
                    "ttl_minutes": ttl_minutes,
                },
                ttl=ttl_minutes,  # SqliteStore 原生 TTL 支持
            )
        except Exception as e:
            logger.warning(f"缓存写入失败: {e}")
    
    def invalidate_by_datasource(self, datasource_luid: str) -> None:
        """
        按数据源失效缓存
        
        注意：SqliteStore 不支持 pattern delete，
        改为按 namespace + datasource_luid 组合键失效
        """
        # 方案：使用复合 namespace
        # namespace = ("semantic_parser", datasource_luid)
        # 这样可以整体删除该数据源的缓存
        try:
            # 获取该 namespace 下所有 key 并逐个删除
            # 或者：在 set 时使用 (namespace, datasource_luid) 作为 namespace
            pass  # 具体实现依赖 SqliteStore 能力
        except Exception as e:
            logger.warning(f"缓存失效失败: {e}")
    
    def _is_expired(self, item: Any) -> bool:
        """检查是否过期（应用层 TTL 检查）"""
        if not item or not item.value:
            return True
        
        created_at_str = item.value.get("created_at")
        if not created_at_str:
            return True
            
        created_at = datetime.fromisoformat(created_at_str)
        ttl_minutes = item.value.get("ttl_minutes", 1440)
        
        return (datetime.now() - created_at).total_seconds() > ttl_minutes * 60
```

### TTL 配置（单位：分钟）

| 缓存类型 | TTL（分钟） | 说明 |
|----------|-------------|------|
| Schema Linking | 1440 (24h) | 数据模型变化不频繁 |
| Step1 | 60 (1h) | LLM 输出可能需要更新 |
| 字段映射 | 1440 (24h) | 字段映射稳定 |

**注意**：与 `langgraph_store.py` 中 `DEFAULT_TTL_MINUTES = 1440` 保持一致。

## 缓存隔离与数据最小化

### 缓存键隔离维度

```python
def build_cache_key(
    canonical_question: str,
    current_date: date,
    datasource_luid: str,
    cache_type: str,
) -> str:
    """
    构建缓存键
    
    隔离维度：
    - datasource_luid: 不同数据源隔离（必须）
    - current_date: 相对时间跨天失效（必须）
    - canonical_question: 问题语义（必须）
    
    不包含的维度（及原因）：
    - site_id: 同一数据源跨 site 共享是安全的
    - user_id: 字段元数据不含用户敏感数据
    - session_id: 跨会话复用是缓存的核心价值
    """
    content = f"{canonical_question}|{current_date.isoformat()}|{datasource_luid}"
    hash_value = hashlib.sha256(content.encode()).hexdigest()[:16]
    return f"{cache_type}:{hash_value}"
```

### sample_values 处理策略

```python
@dataclass
class FieldCandidate:
    """字段候选 - 缓存时的数据最小化"""
    
    # 必须缓存
    field_name: str
    field_caption: str
    role: str
    score: float
    
    # 可选缓存（需评估）
    hierarchy_info: dict | None = None  # 缓存：不含敏感数据
    
    # 不缓存（每次实时获取）
    sample_values: list[str] | None = None  # 不缓存：可能含业务敏感数据
```

**sample_values 策略**：
1. **Schema Linking 缓存不包含 sample_values**
2. **需要 sample_values 时实时从 DataModel 获取**
3. **原因**：sample_values 可能包含客户业务数据，跨请求缓存有合规风险

### Namespace 设计

```python
# 推荐的 namespace 结构
CACHE_NAMESPACES = {
    "schema_linking": ("semantic_parser", "schema_linking"),
    "step1": ("semantic_parser", "step1"),
    "field_mapping": ("field_mapper",),  # 复用现有
}

# 按数据源隔离时的 namespace
def get_namespace_for_datasource(cache_type: str, datasource_luid: str) -> tuple:
    """获取按数据源隔离的 namespace"""
    base = CACHE_NAMESPACES.get(cache_type, ("semantic_parser",))
    return (*base, datasource_luid)
```

## 缓存预热

### 启动时预热

```python
async def warmup_cache(
    datasource_luid: str,
    common_questions: list[str],
    cache: CandidateCache,
) -> None:
    """预热常见问题的缓存"""
    for question in common_questions:
        # 预处理
        preprocess_result = preprocess(question)
        
        # Schema Linking
        candidates = await schema_linking(
            preprocess_result.canonical_question,
            datasource_luid,
        )
        
        # 缓存
        cache_key = build_cache_key(
            preprocess_result.canonical_question,
            date.today(),
            datasource_luid,
            "schema_linking",
        )
        await cache.set(cache_key, candidates)
```

### 常见问题列表

```python
COMMON_QUESTION_PATTERNS = [
    "各{dimension}的{measure}",
    "{time}的{measure}",
    "{measure}排名",
    "{measure}占比",
    "{measure}同比",
    "{measure}环比",
    "{measure}趋势",
]
```

## 缓存监控指标

```python
@dataclass
class CacheMetrics:
    """缓存监控指标"""
    l1_hits: int = 0
    l1_misses: int = 0
    l2_hits: int = 0
    l2_misses: int = 0
    l2_expired: int = 0
    
    @property
    def l1_hit_rate(self) -> float:
        total = self.l1_hits + self.l1_misses
        return self.l1_hits / total if total > 0 else 0.0
    
    @property
    def l2_hit_rate(self) -> float:
        total = self.l2_hits + self.l2_misses
        return self.l2_hits / total if total > 0 else 0.0
    
    @property
    def overall_hit_rate(self) -> float:
        """整体命中率（L1 或 L2 命中）"""
        total = self.l1_hits + self.l2_hits + self.l2_misses
        return (self.l1_hits + self.l2_hits) / total if total > 0 else 0.0
```

## 配置项

```python
@dataclass
class CacheConfig:
    """缓存配置"""
    # L1 配置
    l1_enabled: bool = True
    l1_max_size: int = 1000  # 最大条目数
    
    # L2 配置
    l2_enabled: bool = True
    l2_schema_linking_ttl: int = 86400  # 24 小时
    l2_step1_ttl: int = 3600  # 1 小时
    l2_field_mapping_ttl: int = 86400  # 24 小时
    
    # 预热配置
    warmup_enabled: bool = False
    warmup_questions: list[str] = field(default_factory=list)
```

## 缓存命中率目标

| 场景 | 目标命中率 | 说明 |
|------|------------|------|
| 同一会话重试 | 100% (L1) | 完全复用 |
| 相同问题跨请求 | ≥ 50% (L2) | 取决于问题分布 |
| 整体 | ≥ 30% | 综合 L1 + L2 |

## 与现有实现的集成

项目已有全局 LangGraph Store 实例（`get_langgraph_store()`），vNext 直接复用：

```python
# 现有实现位置: tableau_assistant/src/infra/storage/langgraph_store.py
from tableau_assistant.src.infra.storage.langgraph_store import get_langgraph_store

# vNext 使用方式 - 与现有代码一致
store = get_langgraph_store()  # 获取全局单例，存储在 data/langgraph_store.db
```

**集成方式**:

1. **直接使用 `get_langgraph_store()`**: 不新建存储，复用现有全局单例
2. **新增 namespace 隔离**: `semantic_parser` 用于 Schema Linking 和 Step1 缓存
3. **保持现有 namespace**: `field_mapper`、`metadata` 等继续使用现有实现

**现有 namespace 使用情况**:
- `metadata`: DataModelCache 使用
- `field_mapper`: FieldMapperNode 使用  
- `large_results`: StateBackend 大数据存储
- `dimension_hierarchy`: 维度层级缓存

**vNext 新增 namespace**:
- `semantic_parser`: Schema Linking + Step1 缓存
