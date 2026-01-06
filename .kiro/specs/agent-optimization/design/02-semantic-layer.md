# 语义层深度设计

## 1. 设计目标

从 LLM 原理层面深入思考语义层设计，优化数据模型传递策略。

### 核心问题

1. **是否需要传递完整的 Tableau 数据模型给 LLM？**
2. **字段映射如何优化？**
3. **从 LLM 原理层面思考哪些可以工具化？**

## 2. LLM 原理分析

### 2.1 LLM 的能力边界

**LLM 擅长的**：
- 语义理解和意图识别
- 从候选项中选择最佳匹配
- 推理和决策
- 生成自然语言

**LLM 不擅长的**：
- 精确的字符串匹配
- 大量选项中的搜索
- 记忆大量具体信息
- 数值计算

### 2.2 Token 消耗分析

传递完整数据模型的成本：

```
假设数据源有 100 个字段：
- 字段名：平均 10 tokens/字段
- 字段描述：平均 20 tokens/字段
- 总计：100 × 30 = 3000 tokens

每次查询都传递 → 浪费大量 tokens
```

## 3. 优化策略：RAG + Candidate Fields

### 3.1 核心思路

```
用户问题 → 提取实体 → RAG 检索候选字段 → LLM 从候选中选择
```

**优势**：
1. **Token 消耗少**：只传 Top 5-10 个候选字段（~500 tokens）
2. **准确率高**：LLM 从候选中选择，而非生成字段名
3. **可解释**：可以看到 RAG 检索过程

### 3.2 两阶段策略

```
Stage 1: RAG 检索（Embedding + 相似度）
  - 使用 Embedding 模型计算语义相似度
  - 返回 Top 5-10 个候选字段
  - 计算置信度分数

Stage 2: LLM 选择（仅在置信度不足时）
  - 如果 max(confidence) >= 0.9 → 直接返回最佳匹配
  - 如果 max(confidence) < 0.9 → LLM 从候选中选择
```

### 3.3 实现架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    RAG + Candidate Fields 架构                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  用户问题: "各省份的销售额"                                      │
│      ↓                                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  实体提取（LLM 或规则）                                   │   │
│  │  提取: ["省份", "销售额"]                                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│      ↓                                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  RAG 检索（Embedding 相似度）                             │   │
│  │  "省份" → [省份(0.95), 地区(0.82), 城市(0.75), ...]      │   │
│  │  "销售额" → [销售额(0.98), 利润(0.72), 数量(0.65), ...]  │   │
│  └─────────────────────────────────────────────────────────┘   │
│      ↓                                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  置信度判断                                               │   │
│  │  IF max(confidence) >= 0.9 → 直接返回                    │   │
│  │  ELSE → 传递候选字段给 LLM 选择                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│      ↓                                                          │
│  结果: {省份: "省份", 销售额: "销售额"}                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 4. 数据模型传递策略

### 4.1 当前问题

```python
# ❌ 当前做法：传递完整数据模型
system_prompt = f"""
可用字段：
{json.dumps(data_model.fields, indent=2)}  # 可能 3000+ tokens
"""
```

### 4.2 优化方案

```python
# ✅ 优化后：只传递候选字段
candidate_fields = rag_search(user_entities, top_k=10)

system_prompt = f"""
候选字段（从数据源检索）：
{format_candidates(candidate_fields)}  # ~500 tokens
"""
```

### 4.3 字段信息格式

```python
# 候选字段格式（精简）
class CandidateField:
    name: str           # 字段名
    role: str           # dimension/measure
    data_type: str      # STRING/INTEGER/DATE/...
    sample_values: list # 样例值（维度字段）
    confidence: float   # RAG 置信度
```

## 5. 现有实现参考

### 5.1 数据模型服务

参考 `tableau_assistant/src/platforms/tableau/data_model.py`：

```python
# 已实现的功能
- get_data_dictionary()      # 获取数据源元数据
- get_data_dictionary_async() # 异步版本
- get_datasource_metadata()  # 标准化元数据

# 字段信息包含
- name, fieldCaption
- role (dimension/measure)
- dataType
- sample_values (维度样例)
- unique_count (唯一值数量)
```

### 5.2 Embedding 服务

参考 `tableau_assistant/src/infra/ai/embeddings.py`：

```python
# 已实现的功能
- 智谱 Embedding 模型
- 向量化字段名和描述
- 相似度计算
```

### 5.3 模型管理器

参考 `tableau_assistant/src/infra/ai/model_manager.py`：

```python
# 已实现的功能
- 模型配置 CRUD
- 默认模型管理
- 健康检查
- 使用统计
```

## 6. 字段映射工具设计

### 6.1 MapFields 工具

```python
class MapFieldsTool:
    """字段映射工具
    
    使用 RAG + LLM Fallback 策略：
    1. RAG 检索候选字段
    2. 高置信度直接返回
    3. 低置信度让 LLM 从候选中选择
    """
    
    async def execute(
        self,
        entities: List[str],      # 用户提到的实体
        data_model: DataModel,    # 数据模型（用于 RAG 索引）
    ) -> Dict[str, str]:
        """
        Returns:
            {entity: field_name} 映射结果
        """
        results = {}
        
        for entity in entities:
            # Stage 1: RAG 检索
            candidates = await self.rag_search(entity, data_model, top_k=5)
            
            # Stage 2: 置信度判断
            if candidates[0].confidence >= 0.9:
                results[entity] = candidates[0].name
            else:
                # LLM 从候选中选择
                selected = await self.llm_select(entity, candidates)
                results[entity] = selected
        
        return results
```

### 6.2 RAG 索引构建

```python
class FieldIndex:
    """字段 RAG 索引
    
    为每个数据源构建字段索引，支持：
    - 字段名语义搜索
    - 样例值匹配
    - 同义词扩展
    """
    
    def __init__(self, data_model: DataModel):
        self.embeddings = get_embeddings()
        self.index = self._build_index(data_model)
    
    def _build_index(self, data_model: DataModel):
        """构建索引
        
        索引内容：
        - 字段名
        - 字段描述（如有）
        - 样例值（维度字段）
        """
        documents = []
        for field in data_model.fields:
            # 组合字段信息
            text = f"{field.name}"
            if field.sample_values:
                text += f" ({', '.join(field.sample_values[:3])})"
            documents.append({
                "text": text,
                "metadata": field.dict()
            })
        
        # 向量化并构建索引
        return self._vectorize_and_index(documents)
    
    async def search(self, query: str, top_k: int = 5) -> List[CandidateField]:
        """语义搜索"""
        # 向量化查询
        query_vector = await self.embeddings.embed_query(query)
        
        # 相似度搜索
        results = self.index.similarity_search(query_vector, k=top_k)
        
        return [
            CandidateField(
                name=r.metadata["name"],
                role=r.metadata["role"],
                data_type=r.metadata["dataType"],
                sample_values=r.metadata.get("sample_values", []),
                confidence=r.score
            )
            for r in results
        ]
```

## 7. Token 消耗对比

### 7.1 优化前

| 组件 | Token 消耗 |
|------|-----------|
| 完整数据模型 | 3000-5000 |
| System Prompt | 500-1000 |
| 用户问题 | 50-100 |
| **总计** | **3550-6100** |

### 7.2 优化后

| 组件 | Token 消耗 |
|------|-----------|
| 候选字段（10个） | 300-500 |
| System Prompt | 500-1000 |
| 用户问题 | 50-100 |
| **总计** | **850-1600** |

**节省**: 约 70% Token 消耗

## 8. 实现路径

### 8.1 Phase 1: 基础设施

1. 扩展 `embeddings.py` 支持字段索引
2. 实现 `FieldIndex` 类
3. 集成到 `data_model.py`

### 8.2 Phase 2: 工具实现

1. 实现 `MapFieldsTool`
2. 实现 RAG 检索逻辑
3. 实现 LLM Fallback 逻辑

### 8.3 Phase 3: 集成测试

1. 单元测试：RAG 检索准确率
2. 集成测试：端到端字段映射
3. 性能测试：Token 消耗对比

## 9. 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| RAG 检索不准确 | 调整 top_k，增加 LLM Fallback |
| 同义词处理不足 | 扩展索引内容，包含样例值 |
| 新字段未索引 | 数据模型变更时重建索引 |
| Embedding 模型质量 | 使用高质量中文 Embedding 模型 |

