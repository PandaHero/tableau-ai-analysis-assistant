# Design Document: Agent Architecture Optimization

## Overview

本设计文档描述两个关键优化：
1. **维度层级推断性能优化** - 通过增量推断 + 缓存 + 分批推断 + RAG 增强，将推断时间从 51 秒优化到 5 秒内
2. **FieldMapper 架构重构** - 将 FieldMapper 从 `nodes` 包移动到 `agents` 包，统一 Prompt 规范

## Architecture

### 当前架构问题

```
┌─────────────────────────────────────────────────────────────┐
│                    当前架构                                  │
├─────────────────────────────────────────────────────────────┤
│  agents/                                                     │
│  ├── dimension_hierarchy/  ← 每次推断所有维度（慢）          │
│  └── understanding/                                          │
│                                                              │
│  nodes/                                                      │
│  └── field_mapper/         ← 使用 LLM，不应该在 nodes 包    │
└─────────────────────────────────────────────────────────────┘
```

### 目标架构

```
┌─────────────────────────────────────────────────────────────┐
│                    目标架构                                  │
├─────────────────────────────────────────────────────────────┤
│  agents/                                                     │
│  ├── dimension_hierarchy/  ← 增量推断 + 缓存                │
│  ├── understanding/                                          │
│  └── field_mapper/         ← 从 nodes 移动过来              │
│      ├── __init__.py                                        │
│      ├── prompt.py         ← 新增：LLM 选择 Prompt          │
│      ├── node.py           ← 重构：主入口函数               │
│      └── llm_selector.py   ← 保留：LLM 候选选择器           │
│                                                              │
│  nodes/                                                      │
│  ├── execute/                                                │
│  └── query_builder/                                          │
└─────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. DimensionHierarchyAgent 优化

#### 1.1 缓存结构

```python
# 缓存 namespace
CACHE_NAMESPACE = ("dimension_hierarchy", "{datasource_luid}")

# 缓存 key
CACHE_KEY = "hierarchy_result"

# 缓存 value 结构
{
    "version": 1,
    "timestamp": 1702123456.789,
    "field_hash": "md5_of_field_names",  # 用于检测字段变更
    "hierarchy": {
        "field_name": {
            "category": "time",
            "category_detail": "time-date",
            "level": 5,
            "granularity": "finest",
            ...
        }
    }
}
```

#### 1.2 增量推断流程

```
┌─────────────────────────────────────────────────────────────┐
│                  增量推断流程                                │
├─────────────────────────────────────────────────────────────┤
│  1. 计算当前字段 hash                                        │
│  2. 从 StoreManager 读取缓存                                 │
│     ├── 缓存不存在 → 分批推断（首次优化）                   │
│     ├── 缓存过期（>7天） → 分批推断                         │
│     └── 缓存有效                                            │
│         ├── field_hash 相同 → 直接返回缓存                  │
│         └── field_hash 不同 → 增量推断                      │
│  3. 增量推断                                                 │
│     ├── 计算新增字段 = 当前字段 - 缓存字段                  │
│     ├── 计算删除字段 = 缓存字段 - 当前字段                  │
│     ├── 仅对新增字段调用 LLM                                │
│     └── 合并结果（删除已删除字段）                          │
│  4. 更新缓存                                                 │
└─────────────────────────────────────────────────────────────┘
```

#### 1.3 首次推断优化（分批 + RAG 增强）

**问题**：首次推断 20 个维度需要 51 秒（一次 LLM 调用处理所有字段）

**优化策略**：
1. **分批推断**：将 20 个字段分成 4 批，每批 5 个字段
2. **RAG 增强**：利用 `DimensionHierarchyRAG` 检索相似历史模式作为 few-shot 示例
3. **并行处理**：多批次可以并行调用 LLM（受限于 API 并发）

```
┌─────────────────────────────────────────────────────────────┐
│                  首次推断优化流程                            │
├─────────────────────────────────────────────────────────────┤
│  1. 将 N 个字段分成 ceil(N/5) 批                            │
│  2. 对每批字段：                                            │
│     ├── 使用 DimensionHierarchyRAG 获取 few-shot 示例       │
│     ├── 构建带 few-shot 的 Prompt                           │
│     └── 调用 LLM 推断该批字段                               │
│  3. 合并所有批次结果                                        │
│  4. 存储结果到 RAG（供未来检索）                            │
│  5. 存储结果到缓存                                          │
└─────────────────────────────────────────────────────────────┘

预期效果：
- 原始：1 次 LLM 调用，51 秒
- 优化后：4 次 LLM 调用（可并行），每次约 10-15 秒
- 总耗时：约 15-20 秒（并行）或 40-60 秒（串行）
- 后续调用：直接返回缓存，< 100ms
```

**关键组件**：
- `DimensionHierarchyRAG`：已存在于 `capabilities/rag/dimension_pattern.py`
- `DimensionPatternStore`：存储历史推断结果
- `get_inference_context()`：获取 few-shot 示例

#### 1.3 接口定义

```python
async def dimension_hierarchy_node(
    metadata: Metadata,
    datasource_luid: str,
    store_manager: StoreManager,
    force_refresh: bool = False,  # 新增：强制刷新
    stream: bool = True
) -> DimensionHierarchyResult:
    """
    维度层级推断节点（带缓存和增量推断）
    
    Args:
        metadata: 元数据对象
        datasource_luid: 数据源 LUID
        store_manager: 存储管理器
        force_refresh: 是否强制刷新（忽略缓存）
        stream: 是否流式输出
    
    Returns:
        DimensionHierarchyResult
    """
```

### 2. FieldMapperAgent 重构

#### 2.1 目录结构

```
agents/field_mapper/
├── __init__.py           # 导出 field_mapper_node, FieldMapperAgent
├── prompt.py             # FieldMapperPrompt (VizQLPrompt 子类)
├── node.py               # field_mapper_node 入口函数 + FieldMapperAgent 类
├── llm_selector.py       # LLMCandidateSelector (从 nodes 移动)
└── hierarchy_inferrer.py # HierarchyInferrer (从 nodes 移动)
```

#### 2.2 Prompt 对比（迁移前 vs 迁移后）

**迁移前**（硬编码在 `llm_selector.py` 中）：
```python
# _build_selection_prompt 方法中的硬编码 Prompt
prompt = f"""You are a data analyst expert. Select the best matching field...
## Business Term
"{term}"
## Candidate Fields
{candidates_text}
...
"""
```

**迁移后**（遵循 VizQLPrompt 规范）：
```python
class FieldMapperPrompt(VizQLPrompt):
    """字段映射 Agent 的 Prompt"""
    
    def get_role(self) -> str:
        return """Field mapping expert who matches business terms to technical field names.
        
Expertise: semantic matching, field disambiguation, context-aware selection"""
    
    def get_task(self) -> str:
        return """Select the best matching technical field for each business term.

Process: Analyze term semantics → Compare candidates → Consider context → Select best match"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """**Think step by step:**

Step 1: Analyze business term semantics
- What does the term mean in business context?
- Is it a dimension (categorical) or measure (numeric)?

Step 2: Compare with candidates
- Match field name and caption
- Consider sample values
- Check data type compatibility

Step 3: Consider context
- Use question context for disambiguation
- Consider related fields already mapped

Step 4: Select best match
- Choose highest semantic similarity
- Set confidence based on match quality"""
    
    def get_constraints(self) -> str:
        return """MUST: Only select from provided candidates
MUST: Set selected_field to null if no candidate is a good match
MUST NOT: Invent field names not in candidates"""
    
    def get_user_template(self) -> str:
        return """Select the best matching field for this business term:

Business Term: {term}
Context: {context}

Candidate Fields:
{candidates}

Output JSON with selected_field, confidence, and reasoning."""
    
    def get_output_model(self) -> Type[BaseModel]:
        return SingleSelectionResult  # 已有的 Pydantic 模型
```

#### 2.3 输出数据模型（已存在，保持不变）

```python
# 已存在于 llm_selector.py
class SingleSelectionResult(BaseModel):
    """LLM output for single field selection"""
    business_term: str = Field(description="The business term being mapped")
    selected_field: Optional[str] = Field(
        default=None,
        description="Selected field name, or null if no suitable match"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence in the selection (0-1)"
    )
    reasoning: str = Field(description="Explanation for the selection")

class BatchSelectionResult(BaseModel):
    """LLM output for batch field selection"""
    selections: List[SingleSelectionResult]
```

#### 2.4 接口保持不变

```python
async def field_mapper_node(
    terms: List[str],
    datasource_luid: str,
    context: Optional[str] = None,
    role_filters: Optional[Dict[str, str]] = None
) -> Dict[str, MappingResult]:
    """
    字段映射节点
    
    接口与原 FieldMapperNode.map_fields_batch() 保持一致
    """
```

#### 2.5 Embedding 说明

**Embedding 不涉及 Prompt**。Embedding 是向量化过程：
- 输入：文本字符串（字段名、描述、样本值等）
- 输出：向量（float 数组）
- 用途：RAG 检索时计算相似度

```python
# Embedding 流程（在 FieldIndexer 中）
text = f"{field_name} {field_caption} {description}"
vector = embedding_provider.embed_query(text)  # 无 Prompt
```

## Data Models

### 缓存数据模型

```python
@dataclass
class HierarchyCacheEntry:
    """维度层级缓存条目"""
    version: int = 1
    timestamp: float = 0.0
    field_hash: str = ""
    hierarchy: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    @property
    def is_expired(self) -> bool:
        """检查是否过期（7天）"""
        return time.time() - self.timestamp > 7 * 24 * 60 * 60
    
    def compute_field_hash(self, field_names: List[str]) -> str:
        """计算字段名 hash"""
        sorted_names = sorted(field_names)
        return hashlib.md5(",".join(sorted_names).encode()).hexdigest()
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: 缓存 Round-Trip 一致性

*For any* 维度层级推断结果，写入缓存后再读取，应返回等价的数据结构

**Validates: Requirements 1.1, 1.2**

### Property 2: 增量推断完整性

*For any* 两个版本的元数据（V1 和 V2），增量推断后的结果应包含 V2 中所有字段的层级信息，且不包含 V1 中已删除字段

**Validates: Requirements 1.3, 1.4**

### Property 3: 缓存过期检测

*For any* 缓存条目，当 timestamp 距今超过 7 天时，is_expired 应返回 True

**Validates: Requirements 1.5**

### Property 4: FieldMapper 功能等价性

*For any* 业务术语和候选字段列表，重构后的 FieldMapperAgent 应返回与原 FieldMapperNode 相同的映射结果

**Validates: Requirements 2.3**

## Error Handling

1. **缓存读取失败** - 降级为全量推断
2. **缓存写入失败** - 记录警告，不影响返回结果
3. **增量推断失败** - 降级为全量推断
4. **LLM 调用失败** - 使用 RAG 结果作为 fallback

## Testing Strategy

### 单元测试

1. 缓存读写测试
2. 字段 hash 计算测试
3. 增量字段检测测试
4. 缓存过期检测测试

### 属性测试

使用 Hypothesis 库进行属性测试：

1. **Property 1**: 生成随机 DimensionHierarchyResult，验证缓存 round-trip
2. **Property 2**: 生成两个随机字段列表，验证增量推断完整性
3. **Property 3**: 生成随机时间戳，验证过期检测
4. **Property 4**: 生成随机业务术语和候选列表，验证功能等价性

### 集成测试

1. E2E 测试验证完整流程
2. 性能测试验证优化效果
