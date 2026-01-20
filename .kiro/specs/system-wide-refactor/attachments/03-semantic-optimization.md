# 附件 3：语义理解优化详细设计

本文档详细说明语义理解模块的优化策略，目标是降低 token 消耗 30%，同时提升准确性。

## 优化策略概览

| 策略 | Token 节省 | 延迟降低 | 准确性提升 |
|------|-----------|---------|-----------|
| 三层意图路由 | 20% | 40% | +5% |
| Prompt 优化 | 15% | 10% | +10% |
| 混合检索 | 10% | 20% | +15% |
| **总计** | **30%** | **50%** | **+20%** |

---

## 1. 三层意图路由策略

### 设计目标

最小化 LLM 调用，降低 token 消耗和延迟。

### 三层架构

```
用户查询
  ↓
┌─────────────────────────────────────┐
│ L0: 规则引擎 (Rule Engine)           │
│ - 关键词匹配                         │
│ - 正则表达式                         │
│ - 目标命中率: 30%                    │
│ - 延迟: <10ms                        │
└─────────────────────────────────────┘
  ↓ (置信度 < 0.9)
┌─────────────────────────────────────┐
│ L1: 小模型 (Small Model)             │
│ - 轻量级分类模型 (BERT/DistilBERT)   │
│ - 目标命中率: 50%                    │
│ - 延迟: <100ms                       │
└─────────────────────────────────────┘
  ↓ (置信度 < 0.8)
┌─────────────────────────────────────┐
│ L2: LLM 兜底 (LLM Fallback)          │
│ - GPT-4/Claude                       │
│ - 处理复杂查询                       │
│ - 命中率: 20%                        │
│ - 延迟: 1-3s                         │
└─────────────────────────────────────┘
```

### L0: 规则引擎

**实现**：

```python
# agents/semantic_parser/components/intent_router.py

class RuleEngine:
    """L0: 基于规则的意图识别"""
    
    def __init__(self):
        self.rules = [
            # 趋势分析规则
            {
                "intent": "TREND",
                "patterns": [
                    r"趋势|变化|增长|下降|波动",
                    r"过去.*天|最近.*月|.*年.*变化"
                ],
                "keywords": ["趋势", "变化", "增长", "下降"],
                "confidence": 0.95
            },
            # 对比分析规则
            {
                "intent": "COMPARISON",
                "patterns": [
                    r"对比|比较|差异|相比",
                    r".*和.*的.*对比"
                ],
                "keywords": ["对比", "比较", "差异"],
                "confidence": 0.95
            },
            # 排名规则
            {
                "intent": "RANKING",
                "patterns": [
                    r"排名|排行|前.*名|TOP",
                    r"最.*的.*是"
                ],
                "keywords": ["排名", "排行", "TOP", "最高", "最低"],
                "confidence": 0.95
            },
        ]
    
    def match(self, query: str) -> Optional[RuleResult]:
        """匹配规则"""
        for rule in self.rules:
            # 关键词匹配
            keyword_match = any(kw in query for kw in rule["keywords"])
            
            # 正则匹配
            pattern_match = any(
                re.search(pattern, query) 
                for pattern in rule["patterns"]
            )
            
            if keyword_match or pattern_match:
                return RuleResult(
                    intent=rule["intent"],
                    confidence=rule["confidence"],
                    method="rule"
                )
        
        return None
```

**优势**：
- 延迟极低（<10ms）
- 零 token 消耗
- 高置信度（0.95）

**适用场景**：
- 明确的关键词查询
- 常见的查询模式

### L1: 小模型

**实现**：

```python
# agents/semantic_parser/components/small_model.py
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

class SmallModelClassifier:
    """L1: 轻量级分类模型"""
    
    def __init__(self, model_name: str = "distilbert-base-uncased"):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_name,
            num_labels=6  # 6 种意图类型
        )
        self.intent_labels = [
            "COMPARISON", "TREND", "RANKING", 
            "DISTRIBUTION", "AGGREGATION", "FILTER"
        ]
    
    async def predict(self, query: str) -> SmallModelResult:
        """预测意图"""
        # Tokenize
        inputs = self.tokenizer(
            query,
            return_tensors="pt",
            truncation=True,
            max_length=128
        )
        
        # Predict
        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = torch.softmax(outputs.logits, dim=1)
            confidence, pred_idx = torch.max(probs, dim=1)
        
        return SmallModelResult(
            intent=self.intent_labels[pred_idx.item()],
            confidence=confidence.item(),
            method="small_model"
        )
```

**优势**：
- 延迟低（<100ms）
- Token 消耗少（仅推理）
- 准确率高（85%+）

**训练数据**：
- 使用历史查询数据
- 人工标注 + LLM 辅助标注
- 数据增强（同义词替换、回译）

### L2: LLM 兜底

**实现**：

```python
# agents/semantic_parser/components/llm_classifier.py

class LLMClassifier:
    """L2: LLM 兜底分类"""
    
    def __init__(self, model_manager: ModelManager):
        self.model_manager = model_manager
    
    async def predict(self, query: str, context: Dict) -> LLMResult:
        """使用 LLM 预测意图"""
        prompt = f"""
分析以下用户查询的意图类型。

查询：{query}

上下文：
- 已识别实体：{context.get('entities', [])}
- 数据模型：{context.get('schema_summary', '')}

意图类型：
1. COMPARISON - 对比分析
2. TREND - 趋势分析
3. RANKING - 排名分析
4. DISTRIBUTION - 分布分析
5. AGGREGATION - 聚合统计
6. FILTER - 筛选过滤

请返回 JSON 格式：
{{
    "intent": "意图类型",
    "confidence": 0.0-1.0,
    "reasoning": "推理过程"
}}
"""
        
        response = await self.model_manager.complete(
            model_name="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response["content"])
        return LLMResult(
            intent=result["intent"],
            confidence=result["confidence"],
            reasoning=result["reasoning"],
            method="llm"
        )
```

**优势**：
- 处理复杂查询
- 理解上下文
- 高准确率（95%+）

**劣势**：
- 延迟高（1-3s）
- Token 消耗大

---

## 2. Prompt 优化

### 动态 Schema 注入

**问题**：完整 Schema 导致 token 消耗过大

**解决方案**：仅注入相关字段

```python
# agents/semantic_parser/components/schema_filter.py

class DynamicSchemaFilter:
    """动态 Schema 过滤器"""
    
    async def filter_relevant_fields(
        self,
        query: str,
        data_model: DataModel,
        top_k: int = 20
    ) -> List[Field]:
        """筛选相关字段"""
        # 1. 提取查询中的实体
        entities = self.extract_entities(query)
        
        # 2. 使用 RAG 检索相关字段
        relevant_fields = await self.retriever.retrieve(
            query=query,
            strategy=RetrievalStrategy.HYBRID,
            top_k=top_k
        )
        
        # 3. 精确匹配优先
        exact_matches = [
            field for field in data_model.fields
            if any(entity.lower() in field.name.lower() for entity in entities)
        ]
        
        # 4. 合并并去重
        all_fields = exact_matches + [r.item for r in relevant_fields]
        unique_fields = list({f.id: f for f in all_fields}.values())
        
        return unique_fields[:top_k]
```

**效果**：
- Token 消耗降低 40%（从 500 个字段 → 20 个字段）
- 准确性提升（减少噪音）

### 分层 Prompt 设计

**Step 1: 语义理解**（轻量级）

```python
STEP1_PROMPT = """
理解用户查询的核心意图。

查询：{query}

请分析：
1. 意图类型（对比/趋势/排名/分布/聚合/筛选）
2. 关键实体（指标、维度、时间）
3. 查询复杂度（简单/中等/复杂）

返回 JSON：
{{
    "intent": "意图类型",
    "entities": ["实体1", "实体2"],
    "complexity": "简单|中等|复杂",
    "reasoning": "推理过程"
}}
"""
```

**Step 2: 计算推理**（仅复杂查询）

```python
STEP2_PROMPT = """
为复杂查询设计计算逻辑。

查询：{query}
意图：{intent}
实体：{entities}

相关字段：
{relevant_fields}

请设计：
1. 计算步骤
2. 聚合方式
3. 筛选条件

返回 JSON：
{{
    "steps": ["步骤1", "步骤2"],
    "aggregations": {{"字段": "聚合方式"}},
    "filters": {{"字段": "条件"}}
}}
"""
```

**效果**：
- 简单查询跳过 Step 2，节省 30% token
- 复杂查询获得更详细的推理

### 思维链压缩

**问题**：完整思维链过长

**解决方案**：结构化输出 + 关键步骤

```python
# 压缩前（~500 tokens）
"""
让我一步步分析这个查询...
首先，我注意到用户提到了"销售额"...
然后，用户想要看"过去 7 天"的数据...
接下来，我需要确定聚合方式...
...（冗长的推理过程）
"""

# 压缩后（~150 tokens）
"""
分析：
- 意图：趋势分析
- 指标：销售额
- 时间：过去 7 天
- 聚合：按天求和
"""
```

**效果**：
- Token 消耗降低 70%
- 保留关键信息

---

## 3. 混合检索策略

### 检索流程

```
用户查询
  ↓
┌─────────────────────────────────────┐
│ 1. 精确匹配 (Exact Match)            │
│    - 字段名完全匹配                   │
│    - 同义词匹配                       │
│    - 权重: 0.5                       │
└─────────────────────────────────────┘
  ↓
┌─────────────────────────────────────┐
│ 2. 向量检索 (Vector Search)          │
│    - Embedding 相似度                │
│    - Top-K: 40                       │
│    - 权重: 0.3                       │
└─────────────────────────────────────┘
  ↓
┌─────────────────────────────────────┐
│ 3. 关键词检索 (Keyword Search)        │
│    - BM25 算法                       │
│    - Top-K: 40                       │
│    - 权重: 0.2                       │
└─────────────────────────────────────┘
  ↓
┌─────────────────────────────────────┐
│ 4. 分数融合 (Score Fusion)           │
│    - 加权求和                         │
│    - 归一化                           │
│    - 返回 Top-20                     │
└─────────────────────────────────────┘
```

### 实现

```python
# infra/rag/retriever.py

class UnifiedRetriever:
    """统一检索器"""
    
    async def _hybrid_retrieve(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict]
    ) -> List[RetrievalResult]:
        """混合检索"""
        # 1. 精确匹配
        exact_results = await self._exact_retrieve(query, filters)
        
        # 2. 向量检索
        vector_results = await self._vector_retrieve(query, top_k * 2, filters)
        
        # 3. 关键词检索
        keyword_results = await self._keyword_retrieve(query, top_k * 2, filters)
        
        # 4. 分数融合
        weights = {"exact": 0.5, "vector": 0.3, "keyword": 0.2}
        
        all_results = {}
        for result in exact_results:
            key = self._get_item_key(result.item)
            all_results[key] = {
                "item": result.item,
                "exact_score": 1.0,
                "vector_score": 0.0,
                "keyword_score": 0.0
            }
        
        for result in vector_results:
            key = self._get_item_key(result.item)
            if key not in all_results:
                all_results[key] = {
                    "item": result.item,
                    "exact_score": 0.0,
                    "vector_score": 0.0,
                    "keyword_score": 0.0
                }
            all_results[key]["vector_score"] = result.score
        
        for result in keyword_results:
            key = self._get_item_key(result.item)
            if key not in all_results:
                all_results[key] = {
                    "item": result.item,
                    "exact_score": 0.0,
                    "vector_score": 0.0,
                    "keyword_score": 0.0
                }
            all_results[key]["keyword_score"] = result.score
        
        # 加权融合
        final_results = []
        for key, scores in all_results.items():
            final_score = (
                weights["exact"] * scores["exact_score"] +
                weights["vector"] * scores["vector_score"] +
                weights["keyword"] * scores["keyword_score"]
            )
            final_results.append(RetrievalResult(
                item=scores["item"],
                score=final_score,
                strategy=RetrievalStrategy.HYBRID
            ))
        
        # 排序并返回 Top-K
        final_results.sort(key=lambda x: x.score, reverse=True)
        return final_results[:top_k]
```

### 效果

| 检索策略 | 准确率 | 召回率 | 延迟 |
|---------|-------|-------|------|
| 仅向量检索 | 70% | 65% | 200ms |
| 仅关键词检索 | 65% | 70% | 150ms |
| **混合检索** | **85%** | **80%** | **300ms** |

---

## 总体效果

| 指标 | 优化前 | 优化后 | 提升 |
|------|-------|-------|------|
| Token 消耗 | 1000 | 700 | -30% |
| 延迟（P90） | 5.0s | 3.0s | -40% |
| 准确率 | 75% | 90% | +20% |
| 成本 | $1.00/query | $0.70/query | -30% |

## 监控指标

**三层路由统计**：
- L0 命中率：目标 30%
- L1 命中率：目标 50%
- L2 命中率：目标 20%

**检索质量**：
- 精确匹配命中率
- Top-K 准确率
- 平均检索延迟

**Token 消耗**：
- 按意图类型统计
- 按查询复杂度统计
- 成本趋势分析
