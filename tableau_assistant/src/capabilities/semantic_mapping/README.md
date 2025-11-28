# Semantic Mapping 模块

## 概述

语义映射模块实现了 **RAG+LLM 混合模型**，用于将业务术语智能映射到技术字段名。

## 架构

```
semantic_mapping/
├── embeddings_provider.py    # Embedding 提供者（支持本地/OpenAI）
├── vector_store_manager.py   # FAISS 向量存储管理
├── field_indexer.py           # 字段索引构建器
├── semantic_mapper.py         # 语义映射器（RAG+LLM）
└── README.md                  # 本文档
```

## 工作流程

### 1. 索引构建阶段（一次性）

```python
# 1. 创建 Embeddings Provider
embeddings_provider = EmbeddingsProvider(provider="openai")

# 2. 创建 Field Indexer
field_indexer = FieldIndexer(metadata, embeddings_provider)

# 3. 构建向量索引
field_indexer.build_index()
```

### 2. 映射查询阶段（每次查询）

```python
# 创建 Semantic Mapper
mapper = SemanticMapper(metadata, llm, embeddings_provider)

# 执行映射
result = mapper.map_field(
    business_term="销售额",
    question_context="2024年各地区的销售额",
    top_k=5,
    threshold=0.3,
    use_llm=True
)
```

## RAG+LLM 混合模型

### 为什么需要混合模型？

| 方法 | 优势 | 劣势 |
|------|------|------|
| **纯向量检索** | 快速、可扩展 | 无法理解语义、易受字面相似度误导 |
| **纯LLM判断** | 理解语义、考虑上下文 | 慢、成本高、可能幻觉 |
| **RAG+LLM混合** | 结合两者优势 | 需要两阶段处理 |

### 混合模型流程

```
用户输入: "销售额"
  ↓
【阶段1：RAG 向量检索】
  - 使用 FAISS 进行语义相似度搜索
  - 快速检索 Top-K 候选字段（K=5-10）
  - 过滤低相似度候选（threshold=0.3）
  ↓
候选字段:
  1. [Sales].[Sales Amount] (similarity: 0.95)
  2. [Sales].[Revenue] (similarity: 0.92)
  3. [Sales].[Quantity] (similarity: 0.65)
  ↓
【阶段2：LLM 语义判断】
  - 理解业务术语和问题上下文
  - 分析候选字段的元数据
  - 考虑字段角色（dimension vs measure）
  - 生成推理过程和置信度
  ↓
最终结果:
  - matched_field: "Sales Amount"
  - confidence: 0.95
  - reasoning: "根据上下文，用户询问的是销售金额"
```

## 标准化改进（2025-01-15）

### 改进内容

1. **标准化数据模型** (`models/field_mapping.py`)
   - `FieldMappingCandidate` - 候选字段
   - `FieldMappingResult` - 单个映射结果
   - `BatchFieldMappingRequest` - 批量映射请求
   - `BatchFieldMappingResult` - 批量映射结果

2. **结构化Prompt模板** (`prompts/field_mapping.py`)
   - 继承自 `VizQLPrompt` 基类
   - 4段式结构：Role + Task + Domain Knowledge + Constraints
   - 统一的输出模型

3. **LangChain版本更新**
   - 从 `langchain.schema` 迁移到 `langchain_core.documents`
   - 从 `langchain.embeddings.base` 迁移到 `langchain_core.embeddings`
   - 从 `langchain.chat_models.base` 迁移到 `langchain_core.language_models.chat_models`

### 为什么需要这些改进？

#### 1. 标准化数据模型的好处

**之前的问题**：
```python
# 返回普通字典，缺少类型检查
result = {
    "matched_field": "Sales Amount",
    "confidence": 0.95,
    "reasoning": "...",
    "alternatives": [...]
}
```

**改进后**：
```python
# 使用 Pydantic 模型，类型安全
result = FieldMappingResult(
    business_term="销售额",
    matched_field="Sales Amount",
    matched_field_caption="Sales Amount",
    confidence=0.95,
    reasoning="...",
    alternatives=[...]
)
```

**优势**：
- ✅ 类型检查和验证
- ✅ 自动生成 JSON Schema
- ✅ 与其他模块保持一致
- ✅ 更好的IDE支持

#### 2. 结构化Prompt模板的好处

**之前的问题**：
```python
# Prompt 硬编码在代码中，难以维护
prompt = f"""你是一个数据字段映射专家...
用户问题：{question_context}
业务术语：{business_term}
候选字段：{candidates_text}
..."""
```

**改进后**：
```python
# 使用结构化模板，易于维护和测试
class FieldMappingPrompt(VizQLPrompt):
    def get_role(self) -> str:
        return "You are a data field mapping expert..."
    
    def get_task(self) -> str:
        return "Map business terms to technical fields..."
    
    # ...
```

**优势**：
- ✅ 4段式结构清晰
- ✅ 易于测试和调试
- ✅ 与其他Agent保持一致
- ✅ 支持Prompt版本管理

#### 3. LangChain版本更新的原因

**LangChain 架构演进**：

```
LangChain 0.0.x (旧版本)
├── langchain.schema          # 所有核心类型
├── langchain.embeddings      # Embedding相关
└── langchain.chat_models     # Chat模型相关

LangChain 0.1.0+ (新版本)
├── langchain-core            # 核心抽象（轻量）
│   ├── documents             # Document类型
│   ├── embeddings            # Embedding接口
│   └── language_models       # LLM接口
├── langchain-community       # 社区集成
└── langchain                 # 高级功能
```

**为什么更新**：
- ✅ 项目使用新版LangChain（从错误信息可知）
- ✅ 更模块化的架构
- ✅ 更小的依赖包
- ✅ 向前兼容

## 使用示例

### 基础用法

```python
from tableau_assistant.src.semantic_mapping.semantic_mapper import SemanticMapper
from tableau_assistant.src.semantic_mapping.embeddings_provider import EmbeddingsProvider
from tableau_assistant.src.utils.tableau.models import select_model

# 创建组件
embeddings_provider = EmbeddingsProvider(provider="openai")
llm = select_model(provider="openai", model_name="gpt-4o-mini")

# 创建映射器
mapper = SemanticMapper(metadata, llm, embeddings_provider)

# 执行映射
result = mapper.map_field(
    business_term="销售额",
    question_context="2024年各地区的销售额"
)

print(f"匹配字段: {result['matched_field']}")
print(f"置信度: {result['confidence']}")
print(f"推理: {result['reasoning']}")
```

### 作为工具使用

```python
from tableau_assistant.src.deepagents.tools.semantic_map_fields import semantic_map_fields

# 在 LangChain Agent 中使用
result = await semantic_map_fields.ainvoke({
    "business_term": "销售额",
    "question_context": "2024年各地区的销售额",
    "use_cache": True
})
```

## 性能优化

### 1. 向量索引缓存

```python
# 索引只构建一次，后续从磁盘加载
vector_store_manager.load_index()  # 快速加载
```

### 2. 映射结果缓存

```python
# 使用 Store 缓存映射结果（TTL: 1小时）
await store.put(
    namespace=("semantic_mapping", cache_key),
    value=result
)
```

### 3. 批量映射

```python
# 一次映射多个业务术语
results = mapper.batch_map_fields(
    business_terms=["销售额", "地区", "日期"],
    question_context="..."
)
```

## 测试

```bash
# 运行单元测试
python -m pytest tests/test_semantic_map_fields.py -v

# 运行特定测试
python -m pytest tests/test_semantic_map_fields.py::TestSemanticMapFields::test_basic_mapping -v
```

## 未来改进

1. **支持多语言** - 中英文混合查询
2. **历史学习** - 从用户反馈中学习
3. **字段语义增强** - 自动推断字段语义信息
4. **相似度阈值自适应** - 根据数据源动态调整

## 参考文档

- [字段语义推断设计](../../.kiro/specs/deepagents-refactor/design-appendix/field-semantics.md)
- [工具设计文档](../../.kiro/specs/deepagents-refactor/design-appendix/tools-design.md)
- [Task Planner与RAG集成](../../.kiro/specs/deepagents-refactor/design-appendix/task-planner-rag-integration.md)
