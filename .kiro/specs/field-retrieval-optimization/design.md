# Agentic RAG 字段检索优化设计文档

## 概述

本设计基于 2025-2026 年最新的 Agentic RAG 架构，将字段检索从固定流水线升级为自主决策、自我纠正的智能系统。

### 核心理念

传统 RAG：`Query → Retrieve → Return`（固定流程，失败即失败）

Agentic RAG：`Query → Agent 决策 → 检索 → 评估 → [重试/返回]`（闭环自纠正）

### 技术栈

| 技术 | 来源 | 作用 |
|------|------|------|
| Contextual Retrieval | Anthropic 2024 | 索引时增强上下文，降低 67% 检索失败 |
| Hybrid Search + RRF | LlamaIndex 2025 | BM25 + Vector 融合，兼顾精确和语义 |
| Retrieval Grading | LangGraph Agentic RAG | 评估检索质量，决定是否重试 |
| Query Rewriting | Haystack 2025 | 失败时重写查询，扩展同义词 |
| Self-Correction Loop | Agentic RAG 2026 | 检索-评估-重试闭环 |

---

## 架构

### 整体流程图

```
┌─────────────────────────────────────────────────────────────────┐
│                    INDEXING PHASE (离线)                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Field Metadata ──► Contextual Enrichment ──► Hybrid Index      │
│       │                    │                       │            │
│       │              LLM 生成上下文              Vector + BM25   │
│       │              业务别名推断                               │
│       ▼                    ▼                       ▼            │
│  ┌─────────┐      ┌──────────────┐        ┌─────────────┐      │
│  │ caption │  +   │ 上下文描述    │   =    │ 富文本索引   │      │
│  │ role    │      │ 业务别名      │        │ + metadata  │      │
│  │ type    │      │ 类别推断      │        │             │      │
│  └─────────┘      └──────────────┘        └─────────────┘      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    RETRIEVAL PHASE (在线)                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  User Query: "销售额"                                            │
│       │                                                         │
│       ▼                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   AGENTIC RETRIEVAL LOOP                 │   │
│  │  ┌─────────────────────────────────────────────────────┐│   │
│  │  │ 1. Query Router                                     ││   │
│  │  │    - 判断是否需要检索                                ││   │
│  │  │    - 推断 role (measure/dimension)                  ││   │
│  │  │    - 提取结构化过滤条件                              ││   │
│  │  └─────────────────────────────────────────────────────┘│   │
│  │                         │                                │   │
│  │                         ▼                                │   │
│  │  ┌─────────────────────────────────────────────────────┐│   │
│  │  │ 2. Hybrid Retriever                                 ││   │
│  │  │    - BM25 关键词检索 (精确匹配别名)                   ││   │
│  │  │    - Vector 语义检索 (语义相似)                      ││   │
│  │  │    - RRF 融合排序                                   ││   │
│  │  └─────────────────────────────────────────────────────┘│   │
│  │                         │                                │   │
│  │                         ▼                                │   │
│  │  ┌─────────────────────────────────────────────────────┐│   │
│  │  │ 3. Retrieval Grader                                 ││   │
│  │  │    - 评估检索结果质量                                ││   │
│  │  │    - 判断是否相关 (relevant/not_relevant)           ││   │
│  │  │    - 计算置信度分数                                  ││   │
│  │  └─────────────────────────────────────────────────────┘│   │
│  │                         │                                │   │
│  │            ┌────────────┴────────────┐                   │   │
│  │            ▼                         ▼                   │   │
│  │     [relevant]                [not_relevant]             │   │
│  │         │                          │                     │   │
│  │         ▼                          ▼                     │   │
│  │  ┌─────────────┐          ┌─────────────────┐           │   │
│  │  │ 4. Reranker │          │ 5. Query Rewriter│           │   │
│  │  │  - 精排     │          │  - 扩展同义词    │           │   │
│  │  │  - 返回结果 │          │  - 重写查询      │           │   │
│  │  └─────────────┘          │  - 回到步骤 2    │           │   │
│  │                           └─────────────────┘           │   │
│  │                                  │                       │   │
│  │                                  ▼                       │   │
│  │                           [max_retries?]                 │   │
│  │                           ┌─────┴─────┐                  │   │
│  │                           ▼           ▼                  │   │
│  │                        [yes]        [no]                 │   │
│  │                           │           │                  │   │
│  │                           ▼           └──► 回到步骤 2    │   │
│  │                    ┌─────────────┐                       │   │
│  │                    │ 6. Fallback │                       │   │
│  │                    │  - LLM 直接 │                       │   │
│  │                    │    推断映射 │                       │   │
│  │                    └─────────────┘                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```


---

## 组件详细设计

### 1. Contextual Field Enricher（上下文增强器）

**目的**：索引前为每个字段生成丰富的上下文描述，解决"模糊 chunk"问题。

**文件**：`analytics_assistant/src/agents/field_semantic/contextual_enricher.py`

```python
class ContextualFieldEnricher:
    """
    基于 Anthropic Contextual Retrieval 思想
    为每个字段生成上下文增强的索引文本
    """
    
    async def enrich(
        self,
        field: Field,
        datasource_context: str,  # 数据源描述
        sample_values: List[str],  # 示例值
    ) -> EnrichedField:
        """
        输入: Field(caption="netamt_1", role="measure", data_type="real")
        输出: EnrichedField(
            index_text="netamt_1 是一个销售收入类的度量字段，用于统计净销售金额。
                        该字段来自零售销售数据源，通常用于计算销售业绩。
                        也称为：销售额、净额、收入、金额、sales、revenue。",
            business_aliases=["销售额", "净额", "收入", "金额", "sales", "revenue"],
            category="revenue-sales",
            reasoning="字段名包含 amt(amount)，推断为金额类指标"
        )
        """
        pass
    
    async def _generate_context(self, field: Field, context: str) -> str:
        """使用 LLM 生成上下文描述"""
        prompt = f"""
        你是一个数据字段分析专家。请为以下字段生成一段自然语言描述。

        数据源背景: {context}
        字段名称: {field.caption}
        字段角色: {field.role}
        数据类型: {field.data_type}
        示例值: {sample_values}

        要求:
        1. 用一句话描述这个字段的业务含义
        2. 推断这个字段可能的业务用途
        3. 列出用户可能使用的 5-10 个业务别名（中英文）

        输出格式:
        {{
            "description": "...",
            "business_purpose": "...",
            "aliases": ["...", "..."]
        }}
        """
        return await self._llm.ainvoke(prompt)
```

### 2. Query Router（查询路由器）

**目的**：分析用户查询，决定检索策略，提取结构化过滤条件。

**文件**：`analytics_assistant/src/agents/semantic_parser/components/query_router.py`

```python
class QueryRouter:
    """
    基于 LangChain Self-Query Retriever 思想
    从用户查询中提取结构化信息
    """
    
    async def route(self, query: str, available_fields: List[Field]) -> RouteDecision:
        """
        输入: "销售额"
        输出: RouteDecision(
            needs_retrieval=True,
            inferred_role="measure",
            filters={"role": "measure", "category": "revenue"},
            expanded_queries=["销售额", "收入", "营收", "金额"]
        )
        """
        pass
    
    async def _infer_role(self, query: str) -> str:
        """推断查询目标的角色（度量/维度）"""
        # 使用关键词规则 + LLM 推断
        measure_keywords = ["额", "量", "数", "率", "金额", "成本", "利润"]
        dimension_keywords = ["名", "类", "区", "省", "市", "时间", "日期"]
        
        for kw in measure_keywords:
            if kw in query:
                return "measure"
        for kw in dimension_keywords:
            if kw in query:
                return "dimension"
        
        # 无法确定时使用 LLM
        return await self._llm_infer_role(query)
    
    async def _expand_query(self, query: str) -> List[str]:
        """查询扩展：生成同义词"""
        prompt = f"""
        请为以下业务术语生成 5 个同义词或相关词（中英文混合）:
        术语: {query}
        
        输出格式: ["词1", "词2", ...]
        """
        return await self._llm.ainvoke(prompt)
```

### 3. Hybrid Retriever（混合检索器）

**目的**：结合 BM25 和向量检索，使用 RRF 融合结果。

**文件**：`analytics_assistant/src/agents/semantic_parser/components/hybrid_retriever.py`

```python
class HybridRetriever:
    """
    基于 LlamaIndex QueryFusionRetriever 思想
    BM25 + Vector + RRF 融合
    """
    
    def __init__(self, rag_service: RAGService):
        self._rag_service = rag_service
        self._rrf_k = 60  # RRF 常数
    
    async def retrieve(
        self,
        queries: List[str],  # 扩展后的多个查询
        filters: Dict[str, Any],
        top_k: int = 10,
    ) -> List[RetrievalResult]:
        """
        对每个查询分别执行 BM25 和 Vector 检索
        然后使用 RRF 融合所有结果
        """
        all_results = []
        
        for query in queries:
            # BM25 检索（精确匹配别名）
            bm25_results = await self._bm25_search(query, filters, top_k)
            all_results.extend(bm25_results)
            
            # Vector 检索（语义相似）
            vector_results = await self._vector_search(query, filters, top_k)
            all_results.extend(vector_results)
        
        # RRF 融合
        fused = self._reciprocal_rank_fusion(all_results)
        return fused[:top_k]
    
    def _reciprocal_rank_fusion(
        self, 
        results: List[RetrievalResult]
    ) -> List[RetrievalResult]:
        """
        RRF 算法：score = Σ (1 / (k + rank_i))
        """
        scores = defaultdict(float)
        docs = {}
        
        # 按来源分组，计算每个文档在各来源中的排名
        for i, result in enumerate(results):
            doc_id = result.field_name
            rank = i + 1
            scores[doc_id] += 1.0 / (self._rrf_k + rank)
            docs[doc_id] = result
        
        # 按融合分数排序
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        
        return [
            RetrievalResult(
                field_name=doc_id,
                confidence=scores[doc_id],
                source=docs[doc_id].source,
            )
            for doc_id in sorted_ids
        ]
```


### 4. Retrieval Grader（检索评估器）

**目的**：评估检索结果质量，决定是否需要重试。这是 Agentic RAG 的核心组件。

**文件**：`analytics_assistant/src/agents/semantic_parser/components/retrieval_grader.py`

```python
class RetrievalGrader:
    """
    基于 LangGraph Agentic RAG 的 Retrieval Grader
    评估检索结果是否与查询相关
    """
    
    async def grade(
        self,
        query: str,
        results: List[RetrievalResult],
        threshold: float = 0.6,
    ) -> GradeResult:
        """
        输入: query="销售额", results=[{field: "netamt_1", conf: 0.3}, ...]
        输出: GradeResult(
            is_relevant=False,
            confidence=0.3,
            reason="最高置信度 0.3 低于阈值 0.6，且字段名与查询无明显关联",
            suggestion="expand_query"  # 建议扩展查询
        )
        """
        if not results:
            return GradeResult(
                is_relevant=False,
                confidence=0.0,
                reason="无检索结果",
                suggestion="expand_query"
            )
        
        top_result = results[0]
        
        # 规则 1: 置信度检查
        if top_result.confidence < threshold:
            return GradeResult(
                is_relevant=False,
                confidence=top_result.confidence,
                reason=f"置信度 {top_result.confidence:.2f} 低于阈值 {threshold}",
                suggestion="expand_query"
            )
        
        # 规则 2: 别名精确匹配检查
        if self._exact_alias_match(query, top_result):
            return GradeResult(
                is_relevant=True,
                confidence=min(top_result.confidence + 0.2, 1.0),
                reason="别名精确匹配",
                suggestion=None
            )
        
        # 规则 3: LLM 语义相关性判断
        llm_grade = await self._llm_grade(query, top_result)
        return llm_grade
    
    async def _llm_grade(
        self, 
        query: str, 
        result: RetrievalResult
    ) -> GradeResult:
        """使用 LLM 判断语义相关性"""
        prompt = f"""
        判断以下检索结果是否与用户查询相关。

        用户查询: {query}
        检索到的字段: {result.field_name}
        字段描述: {result.description}
        字段别名: {result.aliases}

        请判断:
        1. 这个字段是否是用户想要的？
        2. 如果不是，用户可能想要什么？

        输出格式:
        {{
            "is_relevant": true/false,
            "confidence": 0.0-1.0,
            "reason": "...",
            "suggestion": "expand_query" / "try_category" / "fallback_llm" / null
        }}
        """
        return await self._llm.ainvoke(prompt)
```

### 5. Query Rewriter（查询重写器）

**目的**：当检索失败时，重写查询以提高召回率。

**文件**：`analytics_assistant/src/agents/semantic_parser/components/query_rewriter.py`

```python
class QueryRewriter:
    """
    基于 Haystack Query Expansion 思想
    重写失败的查询
    """
    
    async def rewrite(
        self,
        original_query: str,
        failed_results: List[RetrievalResult],
        suggestion: str,
        attempt: int,
    ) -> RewriteResult:
        """
        根据失败原因重写查询
        
        策略:
        1. expand_query: 扩展同义词
        2. try_category: 按类别检索
        3. decompose: 分解复合查询
        """
        if suggestion == "expand_query":
            return await self._expand_synonyms(original_query, attempt)
        elif suggestion == "try_category":
            return await self._category_based_rewrite(original_query)
        elif suggestion == "decompose":
            return await self._decompose_query(original_query)
        else:
            return await self._llm_rewrite(original_query, failed_results)
    
    async def _expand_synonyms(
        self, 
        query: str, 
        attempt: int
    ) -> RewriteResult:
        """
        第 1 次: 扩展常见同义词
        第 2 次: 扩展英文翻译
        第 3 次: 扩展领域术语
        """
        if attempt == 1:
            # 常见同义词
            synonyms = await self._get_synonyms(query)
            return RewriteResult(
                queries=[query] + synonyms,
                strategy="synonym_expansion"
            )
        elif attempt == 2:
            # 英文翻译
            translations = await self._translate(query)
            return RewriteResult(
                queries=[query] + translations,
                strategy="translation"
            )
        else:
            # 领域术语
            domain_terms = await self._get_domain_terms(query)
            return RewriteResult(
                queries=[query] + domain_terms,
                strategy="domain_expansion"
            )
    
    async def _get_synonyms(self, query: str) -> List[str]:
        """获取同义词"""
        prompt = f"""
        请为"{query}"生成 5 个业务同义词。
        要求：
        1. 包含口语化表达
        2. 包含正式表达
        3. 包含缩写
        
        输出格式: ["词1", "词2", ...]
        """
        return await self._llm.ainvoke(prompt)
```

### 6. Agentic Field Retriever（智能体字段检索器）

**目的**：整合所有组件，实现自主决策、自我纠正的检索闭环。

**文件**：`analytics_assistant/src/agents/semantic_parser/components/agentic_field_retriever.py`

```python
class AgenticFieldRetriever:
    """
    Agentic RAG 字段检索器
    实现 检索-评估-重试 闭环
    """
    
    def __init__(
        self,
        query_router: QueryRouter,
        hybrid_retriever: HybridRetriever,
        retrieval_grader: RetrievalGrader,
        query_rewriter: QueryRewriter,
        fallback_mapper: FallbackMapper,
        max_retries: int = 3,
    ):
        self._router = query_router
        self._retriever = hybrid_retriever
        self._grader = retrieval_grader
        self._rewriter = query_rewriter
        self._fallback = fallback_mapper
        self._max_retries = max_retries
    
    async def retrieve(
        self,
        query: str,
        available_fields: List[Field],
        index_name: str,
    ) -> AgenticRetrievalResult:
        """
        Agentic 检索主流程
        """
        # Step 1: 路由决策
        route = await self._router.route(query, available_fields)
        
        if not route.needs_retrieval:
            # 不需要检索，直接返回
            return AgenticRetrievalResult(
                fields=[],
                strategy="no_retrieval",
                attempts=0
            )
        
        # Step 2: 检索-评估-重试循环
        current_queries = route.expanded_queries
        filters = route.filters
        
        for attempt in range(1, self._max_retries + 1):
            # 2.1 混合检索
            results = await self._retriever.retrieve(
                queries=current_queries,
                filters=filters,
                top_k=10
            )
            
            # 2.2 评估检索质量
            grade = await self._grader.grade(query, results)
            
            if grade.is_relevant:
                # 检索成功，精排后返回
                reranked = self._rerank(results, query)
                return AgenticRetrievalResult(
                    fields=reranked,
                    strategy="hybrid_retrieval",
                    attempts=attempt,
                    confidence=grade.confidence
                )
            
            # 2.3 检索失败，重写查询
            if attempt < self._max_retries:
                rewrite = await self._rewriter.rewrite(
                    original_query=query,
                    failed_results=results,
                    suggestion=grade.suggestion,
                    attempt=attempt
                )
                current_queries = rewrite.queries
                logger.info(f"检索失败，第 {attempt} 次重试，新查询: {current_queries}")
        
        # Step 3: 所有重试失败，使用 Fallback
        logger.warning(f"检索 {self._max_retries} 次失败，使用 LLM Fallback")
        fallback_result = await self._fallback.map(query, available_fields)
        
        return AgenticRetrievalResult(
            fields=fallback_result.fields,
            strategy="llm_fallback",
            attempts=self._max_retries,
            confidence=fallback_result.confidence
        )
    
    def _rerank(
        self, 
        results: List[RetrievalResult], 
        query: str
    ) -> List[RetrievalResult]:
        """精排：别名命中加分"""
        for result in results:
            # 别名精确匹配 +0.3
            if query in result.aliases:
                result.confidence = min(result.confidence + 0.3, 1.0)
            # Caption 包含 +0.2
            elif query in result.field_name:
                result.confidence = min(result.confidence + 0.2, 1.0)
        
        return sorted(results, key=lambda x: x.confidence, reverse=True)
```


### 7. Fallback Mapper（降级映射器）

**目的**：当所有检索策略失败时，使用 LLM 直接推断字段映射。

**文件**：`analytics_assistant/src/agents/semantic_parser/components/fallback_mapper.py`

```python
class FallbackMapper:
    """
    最后的降级策略：LLM 直接推断
    """
    
    async def map(
        self,
        query: str,
        available_fields: List[Field],
    ) -> FallbackResult:
        """
        将所有可用字段提供给 LLM，让其直接选择最匹配的
        """
        # 构建字段列表
        field_list = "\n".join([
            f"- {f.caption} (角色: {f.role}, 类型: {f.data_type})"
            for f in available_fields
        ])
        
        prompt = f"""
        用户想要查找的字段: "{query}"
        
        可用字段列表:
        {field_list}
        
        请从上述列表中选择最匹配的字段（最多 3 个）。
        如果没有匹配的字段，返回空列表。
        
        输出格式:
        {{
            "matches": [
                {{"field": "字段名", "confidence": 0.0-1.0, "reason": "..."}}
            ]
        }}
        """
        
        result = await self._llm.ainvoke(prompt)
        return FallbackResult(
            fields=[m["field"] for m in result["matches"]],
            confidence=result["matches"][0]["confidence"] if result["matches"] else 0.0,
            reasoning=[m["reason"] for m in result["matches"]]
        )
```

---

## 数据模型

### 索引文档结构

```python
class EnrichedFieldDocument(BaseModel):
    """增强后的字段索引文档"""
    
    # 主文本（用于向量检索）
    index_text: str  # "netamt_1 是一个销售收入类的度量字段..."
    
    # 元数据（用于过滤和 BM25）
    metadata: Dict[str, Any] = {
        "field_name": "netamt_1",
        "caption": "netamt_1",
        "role": "measure",
        "data_type": "real",
        "category": "revenue-sales",
        "aliases": ["销售额", "净额", "收入", "金额", "sales", "revenue"],
        "description": "净销售金额，用于统计销售业绩",
        "sample_values": ["1000.00", "2500.50", "3200.00"],
    }
```

### 索引文本示例

**度量字段**：
```
netamt_1 是一个销售收入类的度量字段，用于统计净销售金额。
该字段来自零售销售数据源，通常用于计算销售业绩和收入分析。
也称为：销售额、净额、收入、金额、sales、revenue、net amount。
```

**维度字段**：
```
province 是一个地理位置类的维度字段，表示省级行政区划。
该字段用于按地区分析数据，支持地理下钻到城市和区县。
示例值：北京、上海、广东、浙江。
也称为：省份、省、地区、region、province。
```

---

## 配置

### app.yaml 新增配置

```yaml
field_retrieval:
  # Agentic RAG 配置
  agentic:
    max_retries: 3                    # 最大重试次数
    grading_threshold: 0.6            # 检索质量阈值
    enable_query_expansion: true      # 启用查询扩展
    enable_llm_grading: true          # 启用 LLM 评估
  
  # 混合检索配置
  hybrid:
    bm25_weight: 0.4                  # BM25 权重
    vector_weight: 0.6                # 向量权重
    rrf_k: 60                         # RRF 常数
    top_k: 10                         # 检索数量
  
  # 上下文增强配置
  contextual:
    enable_enrichment: true           # 启用上下文增强
    max_aliases: 10                   # 最大别名数量
    include_sample_values: true       # 包含示例值
  
  # 精排配置
  rerank:
    alias_match_boost: 0.3            # 别名匹配加分
    caption_match_boost: 0.2          # Caption 匹配加分
    max_boost: 1.0                    # 最大分数
  
  # Fallback 配置
  fallback:
    enable_llm_fallback: true         # 启用 LLM 降级
    fallback_confidence_threshold: 0.3 # 降级置信度阈值
```

---

## Correctness Properties

### Property 1: 检索闭环完整性

*For any* 查询，系统必须经过 路由→检索→评估→[重试/返回] 完整流程。

**Validates: Requirements 1.1, 1.2, 1.3**

### Property 2: 重试次数限制

*For any* 检索请求，重试次数不超过 max_retries 配置值。

**Validates: Requirements 4.1**

### Property 3: 评估决策一致性

*For any* 检索结果，置信度 >= threshold 时判定为 relevant，< threshold 时判定为 not_relevant。

**Validates: Requirements 4.2**

### Property 4: RRF 融合正确性

*For any* 多源检索结果，RRF 融合后分数 = Σ(1/(k+rank))，且最终分数在 [0, 1] 范围内。

**Validates: Requirements 3.1, 3.2**

### Property 5: 查询扩展幂等性

*For any* 相同查询，多次扩展返回相同的同义词集合（缓存命中时）。

**Validates: Requirements 3.3**

### Property 6: Fallback 触发条件

*For any* 检索请求，仅当所有重试失败后才触发 Fallback。

**Validates: Requirements 4.3**

### Property 7: 上下文增强格式

*For any* 字段索引文本，必须包含：字段名、角色描述、业务用途、别名列表。

**Validates: Requirements 5.1, 5.2**

---

## 测试策略

### 单元测试

1. **QueryRouter 测试**
   - 角色推断准确性
   - 过滤条件提取
   - 查询扩展

2. **HybridRetriever 测试**
   - BM25 检索
   - Vector 检索
   - RRF 融合

3. **RetrievalGrader 测试**
   - 置信度阈值判断
   - 别名匹配检测
   - LLM 评估

4. **QueryRewriter 测试**
   - 同义词扩展
   - 翻译扩展
   - 领域术语扩展

### 属性测试 (Hypothesis)

```python
from hypothesis import given, strategies as st

@given(st.text(min_size=1, max_size=20))
def test_query_router_always_returns_decision(query: str):
    """任何查询都应返回路由决策"""
    router = QueryRouter()
    result = router.route(query, [])
    assert isinstance(result, RouteDecision)
    assert result.needs_retrieval in [True, False]

@given(st.lists(st.floats(min_value=0, max_value=1), min_size=1, max_size=100))
def test_rrf_fusion_score_in_range(scores: List[float]):
    """RRF 融合后分数应在 [0, 1] 范围内"""
    retriever = HybridRetriever()
    results = [RetrievalResult(confidence=s) for s in scores]
    fused = retriever._reciprocal_rank_fusion(results)
    for r in fused:
        assert 0 <= r.confidence <= 1

@given(st.integers(min_value=1, max_value=10))
def test_max_retries_respected(max_retries: int):
    """重试次数不应超过配置值"""
    retriever = AgenticFieldRetriever(max_retries=max_retries)
    result = retriever.retrieve("不存在的字段", [])
    assert result.attempts <= max_retries
```

### 集成测试

1. **端到端检索测试**
   - 输入: "销售额"
   - 期望: 返回 revenue 类字段，置信度 > 0.6

2. **重试机制测试**
   - 输入: 模糊查询
   - 期望: 触发重试，最终返回结果

3. **Fallback 测试**
   - 输入: 完全不匹配的查询
   - 期望: 触发 LLM Fallback

---

## 错误处理

### LLM 调用失败

1. 重试最多 3 次
2. 失败后跳过 LLM 评估，使用规则评估
3. 记录错误日志

### 检索服务不可用

1. 直接触发 Fallback
2. 记录警告日志

### 配置加载失败

1. 使用默认配置值
2. 继续正常运行

---

## 性能考虑

### 延迟优化

| 组件 | 预期延迟 | 优化策略 |
|------|----------|----------|
| Query Router | < 50ms | 规则优先，LLM 兜底 |
| Hybrid Retriever | < 100ms | 并行执行 BM25 和 Vector |
| Retrieval Grader | < 50ms | 规则优先，LLM 兜底 |
| Query Rewriter | < 100ms | 缓存同义词 |
| Fallback Mapper | < 500ms | 仅在失败时调用 |

### 缓存策略

1. **查询扩展缓存**：相同查询的同义词缓存 1 小时
2. **字段索引缓存**：数据源字段索引缓存直到元数据变更
3. **LLM 结果缓存**：相同输入的 LLM 结果缓存 24 小时

---

## 总结

本设计采用 Agentic RAG 架构，核心改进：

1. **Contextual Retrieval**：索引时增强上下文，解决"模糊 chunk"问题
2. **Hybrid Search + RRF**：BM25 + Vector 融合，兼顾精确和语义
3. **Retrieval Grading**：评估检索质量，决定是否重试
4. **Self-Correction Loop**：检索-评估-重试闭环，提高成功率
5. **Graceful Fallback**：所有策略失败时，LLM 直接推断

预期效果：
- 检索成功率从 ~30% 提升到 ~90%
- 支持业务术语到技术字段的智能映射
- 自动处理模糊查询和同义词 
