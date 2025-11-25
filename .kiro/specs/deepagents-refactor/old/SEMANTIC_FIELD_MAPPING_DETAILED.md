# 语义字段映射详细设计

## 🎯 核心问题

**如何让 LLM 准确找到用户想要的字段？**

用户可能会说：
- "销售额" → 应该映射到 `[Sales].[Sales Amount]`
- "收入" → 应该映射到 `[Sales].[Sales Amount]`（同义词）
- "去年的销售" → 应该映射到 `[Sales].[Sales Amount]` + 时间过滤
- "Sales" → 应该映射到 `[Sales].[Sales Amount]`（多语言）
- "销售" → 应该映射到 `[Sales].[Sales Amount]` 还是 `[Sales].[Sales Count]`？（模糊）

---

## 🏗️ 完整架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    用户输入："销售额"                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              Step 1: 向量检索（快速筛选）                        │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  Embedding Model (text-embedding-3-large)              │    │
│  │  ├─ 用户输入 → Vector                                  │    │
│  │  └─ 字段库 → Vectors                                   │    │
│  └────────────────────────────────────────────────────────┘    │
│                              ↓                                   │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  Vector Database (FAISS/Chroma)                        │    │
│  │  ├─ Similarity Search (Top-K=5)                        │    │
│  │  └─ 返回候选字段                                       │    │
│  └────────────────────────────────────────────────────────┘    │
│                              ↓                                   │
│  候选字段：                                                      │
│  1. [Sales].[Sales Amount] (0.92)                               │
│  2. [Sales].[Sales Count] (0.78)                                │
│  3. [Revenue].[Total Revenue] (0.75)                            │
│  4. [Orders].[Order Amount] (0.68)                              │
│  5. [Finance].[Income] (0.65)                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              Step 2: LLM 语义判断（精确选择）                   │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  LLM Prompt:                                           │    │
│  │                                                         │    │
│  │  用户问题：2016年各地区的销售额                        │    │
│  │  用户输入：销售额                                       │    │
│  │                                                         │    │
│  │  候选字段：                                             │    │
│  │  1. [Sales].[Sales Amount]                             │    │
│  │     - 类型：度量                                        │    │
│  │     - 描述：销售金额总和                                │    │
│  │     - 示例值：1000000, 500000, 250000                  │    │
│  │                                                         │    │
│  │  2. [Sales].[Sales Count]                              │    │
│  │     - 类型：度量                                        │    │
│  │     - 描述：销售订单数量                                │    │
│  │     - 示例值：100, 50, 25                              │    │
│  │                                                         │    │
│  │  3. [Revenue].[Total Revenue]                          │    │
│  │     - 类型：度量                                        │    │
│  │     - 描述：总收入                                      │    │
│  │     - 示例值：1200000, 600000, 300000                  │    │
│  │                                                         │    │
│  │  请选择最匹配的字段，并说明理由。                       │    │
│  │  返回格式：                                             │    │
│  │  {                                                      │    │
│  │    "selected_field": "[Sales].[Sales Amount]",         │    │
│  │    "confidence": 0.95,                                 │    │
│  │    "reasoning": "用户明确说'销售额'，指的是金额...",   │    │
│  │    "alternatives": [...]                               │    │
│  │  }                                                      │    │
│  └────────────────────────────────────────────────────────┘    │
│                              ↓                                   │
│  LLM 返回：                                                      │
│  {                                                               │
│    "selected_field": "[Sales].[Sales Amount]",                  │
│    "confidence": 0.95,                                          │
│    "reasoning": "用户明确说'销售额'，指的是金额而不是数量。     │
│                 [Sales].[Sales Amount] 是最准确的匹配。",       │
│    "alternatives": [                                            │
│      {"field": "[Revenue].[Total Revenue]", "confidence": 0.7}, │
│      {"field": "[Sales].[Sales Count]", "confidence": 0.3}      │
│    ]                                                             │
│  }                                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              Step 3: 置信度判断（决策）                          │
│                                                                  │
│  IF confidence > 0.8:                                            │
│    → 直接使用该字段                                              │
│                                                                  │
│  ELSE IF confidence > 0.5:                                       │
│    → 使用该字段，但记录警告                                      │
│    → 在结果中提示用户："我理解您说的是 [Sales].[Sales Amount]" │
│                                                                  │
│  ELSE:                                                           │
│    → 返回多个候选字段                                            │
│    → 请求用户确认："您说的'销售'是指：                          │
│       1. 销售金额 ([Sales].[Sales Amount])                      │
│       2. 销售数量 ([Sales].[Sales Count])                       │
│       请选择一个。"                                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              Step 4: 学习和优化（可选）                          │
│                                                                  │
│  WHEN 用户确认字段映射:                                          │
│    → 保存映射关系到 Store                                        │
│    → 格式：{"user_term": "销售额", "field": "[Sales].[...]"}   │
│                                                                  │
│  WHEN 下次遇到相同术语:                                          │
│    → 优先使用历史映射                                            │
│    → 提升置信度                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 字段向量索引构建

### 1. 字段信息收集

```python
# 从 Tableau 元数据收集字段信息
field_info = {
    "field_name": "[Sales].[Sales Amount]",
    "display_name": "销售额",
    "data_type": "measure",
    "aggregation": "SUM",
    "description": "销售金额总和",
    "folder": "Sales",
    "sample_values": [1000000, 500000, 250000],
    "related_fields": ["[Sales].[Sales Count]", "[Sales].[Discount]"],
    "usage_frequency": 150  # 该字段被使用的次数
}
```

### 2. 构建富文本描述

```python
def build_field_text(field_info):
    """
    构建用于向量化的富文本描述
    """
    text_parts = []
    
    # 1. 字段名（多种形式）
    text_parts.append(f"字段名: {field_info['field_name']}")
    text_parts.append(f"显示名: {field_info['display_name']}")
    
    # 2. 类型信息
    text_parts.append(f"类型: {field_info['data_type']}")
    if field_info.get('aggregation'):
        text_parts.append(f"聚合: {field_info['aggregation']}")
    
    # 3. 业务描述
    if field_info.get('description'):
        text_parts.append(f"描述: {field_info['description']}")
    
    # 4. 文件夹/分类
    if field_info.get('folder'):
        text_parts.append(f"分类: {field_info['folder']}")
    
    # 5. 示例值（帮助理解数据规模）
    if field_info.get('sample_values'):
        samples = ', '.join(str(v) for v in field_info['sample_values'][:3])
        text_parts.append(f"示例值: {samples}")
    
    # 6. 相关字段（帮助理解上下文）
    if field_info.get('related_fields'):
        related = ', '.join(field_info['related_fields'][:3])
        text_parts.append(f"相关字段: {related}")
    
    # 7. 同义词（如果有）
    if field_info.get('synonyms'):
        synonyms = ', '.join(field_info['synonyms'])
        text_parts.append(f"同义词: {synonyms}")
    
    return "\n".join(text_parts)

# 示例输出：
"""
字段名: [Sales].[Sales Amount]
显示名: 销售额
类型: measure
聚合: SUM
描述: 销售金额总和
分类: Sales
示例值: 1000000, 500000, 250000
相关字段: [Sales].[Sales Count], [Sales].[Discount]
同义词: 收入, 营收, Sales
"""
```

### 3. 向量化和索引

```python
from langchain_openai import OpenAIEmbeddings
import faiss
import numpy as np

class FieldVectorStore:
    def __init__(self, datasource_luid):
        self.datasource_luid = datasource_luid
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
        self.index = None
        self.field_metadata = []
    
    def build_index(self, fields):
        """
        构建向量索引
        """
        # 1. 构建富文本描述
        texts = [build_field_text(field) for field in fields]
        
        # 2. 生成向量
        vectors = self.embeddings.embed_documents(texts)
        vectors = np.array(vectors).astype('float32')
        
        # 3. 构建 FAISS 索引
        dimension = vectors.shape[1]
        self.index = faiss.IndexFlatIP(dimension)  # 使用点积相似度
        faiss.normalize_L2(vectors)  # 归一化，使点积等价于余弦相似度
        self.index.add(vectors)
        
        # 4. 保存元数据
        self.field_metadata = fields
        
        # 5. 持久化
        self.save()
    
    def search(self, query, k=5, threshold=0.5):
        """
        搜索候选字段
        """
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
                    "field": self.field_metadata[idx],
                    "score": float(score)
                })
        
        return results
    
    def save(self):
        """
        持久化索引
        """
        import pickle
        
        # 保存 FAISS 索引
        faiss.write_index(self.index, f"vector_store/{self.datasource_luid}.index")
        
        # 保存元数据
        with open(f"vector_store/{self.datasource_luid}.metadata", "wb") as f:
            pickle.dump(self.field_metadata, f)
    
    def load(self):
        """
        加载索引
        """
        import pickle
        
        # 加载 FAISS 索引
        self.index = faiss.read_index(f"vector_store/{self.datasource_luid}.index")
        
        # 加载元数据
        with open(f"vector_store/{self.datasource_luid}.metadata", "rb") as f:
            self.field_metadata = pickle.load(f)
```

---

## 🧠 LLM 语义判断

### Prompt 设计

```python
SEMANTIC_MAPPING_PROMPT = """
你是一个 Tableau 数据分析专家，负责将用户的业务术语映射到正确的技术字段名。

## 用户问题
{question}

## 用户输入的术语
{user_term}

## 候选字段
{candidates}

## 任务
请分析用户的问题和术语，从候选字段中选择最匹配的字段。

## 分析要点
1. **字段类型**：用户想要的是维度还是度量？
2. **业务含义**：用户说的"销售额"是指金额还是数量？
3. **上下文**：问题中的其他字段是什么？它们之间的关系是什么？
4. **数据规模**：示例值是否符合用户的预期？
5. **同义词**：用户的术语是否是某个字段的同义词？

## 返回格式
请以 JSON 格式返回：
{{
    "selected_field": "字段的完整路径",
    "confidence": 0.0-1.0 之间的置信度,
    "reasoning": "详细的推理过程",
    "alternatives": [
        {{"field": "备选字段1", "confidence": 0.0-1.0}},
        {{"field": "备选字段2", "confidence": 0.0-1.0}}
    ]
}}

## 示例
用户问题：2016年各地区的销售额
用户术语：销售额
候选字段：
1. [Sales].[Sales Amount] - 度量 - 销售金额总和 - 示例：1000000
2. [Sales].[Sales Count] - 度量 - 销售订单数量 - 示例：100

分析：
- 用户说"销售额"，明确指的是金额而不是数量
- [Sales].[Sales Amount] 的示例值（1000000）符合金额的规模
- [Sales].[Sales Count] 的示例值（100）是订单数量

返回：
{{
    "selected_field": "[Sales].[Sales Amount]",
    "confidence": 0.95,
    "reasoning": "用户明确说'销售额'，指的是金额而不是数量。[Sales].[Sales Amount] 是最准确的匹配。",
    "alternatives": [
        {{"field": "[Revenue].[Total Revenue]", "confidence": 0.7}},
        {{"field": "[Sales].[Sales Count]", "confidence": 0.3}}
    ]
}}
"""

def semantic_map_field(question, user_term, candidates, llm):
    """
    使用 LLM 进行语义映射
    """
    # 1. 格式化候选字段
    candidates_text = []
    for i, candidate in enumerate(candidates, 1):
        field = candidate['field']
        score = candidate['score']
        text = f"{i}. {field['field_name']}\n"
        text += f"   - 类型: {field['data_type']}\n"
        text += f"   - 描述: {field.get('description', 'N/A')}\n"
        text += f"   - 示例值: {', '.join(str(v) for v in field.get('sample_values', [])[:3])}\n"
        text += f"   - 向量相似度: {score:.2f}\n"
        candidates_text.append(text)
    
    # 2. 构建 Prompt
    prompt = SEMANTIC_MAPPING_PROMPT.format(
        question=question,
        user_term=user_term,
        candidates="\n".join(candidates_text)
    )
    
    # 3. 调用 LLM
    response = llm.invoke(prompt)
    
    # 4. 解析结果
    import json
    result = json.loads(response.content)
    
    return result
```

---

## 🎯 完整流程示例

### 场景 1：高置信度映射

```python
# 用户输入
question = "2016年各地区的销售额"
user_term = "销售额"

# Step 1: 向量检索
vector_store = FieldVectorStore(datasource_luid)
candidates = vector_store.search(user_term, k=5)
# 返回：
# [
#   {"field": {"field_name": "[Sales].[Sales Amount]", ...}, "score": 0.92},
#   {"field": {"field_name": "[Sales].[Sales Count]", ...}, "score": 0.78},
#   ...
# ]

# Step 2: LLM 语义判断
result = semantic_map_field(question, user_term, candidates, llm)
# 返回：
# {
#   "selected_field": "[Sales].[Sales Amount]",
#   "confidence": 0.95,
#   "reasoning": "用户明确说'销售额'，指的是金额...",
#   "alternatives": [...]
# }

# Step 3: 置信度判断
if result['confidence'] > 0.8:
    # 直接使用
    mapped_field = result['selected_field']
    print(f"✅ 映射成功: {user_term} → {mapped_field}")
```

### 场景 2：中等置信度映射

```python
# 用户输入
question = "各地区的销售情况"
user_term = "销售"  # 模糊

# Step 1: 向量检索
candidates = vector_store.search(user_term, k=5)

# Step 2: LLM 语义判断
result = semantic_map_field(question, user_term, candidates, llm)
# 返回：
# {
#   "selected_field": "[Sales].[Sales Amount]",
#   "confidence": 0.65,  # 中等置信度
#   "reasoning": "'销售'可能指金额或数量，但根据上下文...",
#   "alternatives": [
#     {"field": "[Sales].[Sales Count]", "confidence": 0.6}
#   ]
# }

# Step 3: 置信度判断
if 0.5 < result['confidence'] <= 0.8:
    # 使用但记录警告
    mapped_field = result['selected_field']
    print(f"⚠️ 映射成功（中等置信度）: {user_term} → {mapped_field}")
    print(f"💡 提示：我理解您说的'{user_term}'是指 {mapped_field}")
```

### 场景 3：低置信度映射

```python
# 用户输入
question = "各地区的数据"
user_term = "数据"  # 非常模糊

# Step 1: 向量检索
candidates = vector_store.search(user_term, k=5)

# Step 2: LLM 语义判断
result = semantic_map_field(question, user_term, candidates, llm)
# 返回：
# {
#   "selected_field": "[Sales].[Sales Amount]",
#   "confidence": 0.3,  # 低置信度
#   "reasoning": "'数据'太模糊，无法确定...",
#   "alternatives": [
#     {"field": "[Sales].[Sales Count]", "confidence": 0.3},
#     {"field": "[Orders].[Order Count]", "confidence": 0.25}
#   ]
# }

# Step 3: 置信度判断
if result['confidence'] <= 0.5:
    # 请求用户确认
    print(f"❓ 无法确定'{user_term}'的含义，请选择：")
    print(f"1. 销售金额 ({result['selected_field']})")
    for i, alt in enumerate(result['alternatives'], 2):
        print(f"{i}. {alt['field']}")
    
    # 等待用户选择...
```

---

## 📈 优化策略

### 1. 历史学习

```python
class FieldMappingLearner:
    def __init__(self, store):
        self.store = store
    
    def save_mapping(self, user_term, field, datasource_luid):
        """
        保存用户确认的映射
        """
        key = f"field_mapping/{datasource_luid}/{user_term}"
        self.store.put(key, {
            "field": field,
            "timestamp": datetime.now().isoformat(),
            "count": self.store.get(key, {}).get("count", 0) + 1
        })
    
    def get_historical_mapping(self, user_term, datasource_luid):
        """
        获取历史映射
        """
        key = f"field_mapping/{datasource_luid}/{user_term}"
        return self.store.get(key)
    
    def boost_confidence(self, result, historical_mapping):
        """
        基于历史提升置信度
        """
        if historical_mapping and result['selected_field'] == historical_mapping['field']:
            # 历史映射匹配，提升置信度
            result['confidence'] = min(result['confidence'] + 0.2, 1.0)
            result['reasoning'] += f"\n（历史记录显示用户之前选择了这个字段）"
        
        return result
```

### 2. 上下文增强

```python
def enhance_with_context(question, user_term, candidates):
    """
    使用问题上下文增强候选字段
    """
    # 提取问题中的其他字段
    other_fields = extract_fields_from_question(question)
    
    # 为每个候选字段计算上下文相关性
    for candidate in candidates:
        field = candidate['field']
        
        # 检查是否有相关字段
        related_score = 0
        for other_field in other_fields:
            if other_field in field.get('related_fields', []):
                related_score += 0.1
        
        # 调整分数
        candidate['score'] += related_score
    
    # 重新排序
    candidates.sort(key=lambda x: x['score'], reverse=True)
    
    return candidates
```

### 3. 多语言支持

```python
def build_multilingual_index(field_info):
    """
    构建多语言索引
    """
    texts = []
    
    # 中文
    texts.append(build_field_text(field_info))
    
    # 英文
    if field_info.get('english_name'):
        texts.append(f"Field name: {field_info['english_name']}")
    
    # 同义词
    if field_info.get('synonyms'):
        for synonym in field_info['synonyms']:
            texts.append(f"Synonym: {synonym}")
    
    # 合并所有文本
    return "\n".join(texts)
```

---

## ✅ 总结

### 核心思路

1. **向量检索**：快速筛选候选字段（Top-K）
2. **LLM 判断**：精确选择最佳匹配
3. **置信度决策**：根据置信度决定是否需要用户确认
4. **历史学习**：保存用户确认的映射，提升未来准确率

### 关键优势

- ✅ **快速**：向量检索 < 100ms
- ✅ **准确**：LLM 语义理解 > 90% 准确率
- ✅ **智能**：考虑上下文、类型、示例值
- ✅ **学习**：历史映射提升准确率
- ✅ **多语言**：支持中英文和同义词

### 实施优先级

1. **Phase 1**：基础向量检索 + LLM 判断
2. **Phase 2**：置信度决策 + 用户确认
3. **Phase 3**：历史学习 + 上下文增强
4. **Phase 4**：多语言支持 + 高级优化

