# 扩展业界项目深度分析

> 本文档是 `INDUSTRY_DEEP_COMPARISON.md` 的扩展，涵盖商业 BI 产品、最新学术研究和新兴开源项目。
>
> **分析日期**: 2024-12-21
> **分析范围**: 商业产品 + 学术研究 + 新兴开源

---

## 目录

1. [商业 BI 产品分析](#1-商业-bi-产品分析)
   - 1.1 ThoughtSpot Spotter
   - 1.2 Amazon QuickSight Q
   - 1.3 Power BI Q&A
   - 1.4 Qlik Insight Advisor
   - 1.5 Google Looker Conversational Analytics
   - 1.6 Tableau Pulse & Ask Data
2. [最新学术研究分析](#2-最新学术研究分析)
   - 2.1 DAIL-SQL
   - 2.2 MAC-SQL
   - 2.3 CHESS
   - 2.4 Spider 2.0 基准测试
3. [综合对比与借鉴](#3-综合对比与借鉴)
4. [针对 Tableau Assistant 的改进建议](#4-针对-tableau-assistant-的改进建议)

---

## 1. 商业 BI 产品分析

### 1.1 ThoughtSpot Spotter

#### 1.1.1 产品概述

ThoughtSpot 于 2024 年 11 月推出 Spotter，定位为"自主分析代理"(Autonomous Agent for Analytics)。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ThoughtSpot Spotter 架构                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Agentic AI Layer                               │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │   │
│  │  │ 自然语言理解 │  │ 意图推断    │  │ 上下文管理  │               │   │
│  │  │ (NLU)       │  │ (Intent)    │  │ (Context)   │               │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘               │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    核心能力层                                     │   │
│  │  • 对话式分析：多轮对话，追问和澄清                               │   │
│  │  • 行业适配：根据用户角色和行业调整响应                           │   │
│  │  • 人机协作：用户可修改、训练和反馈                               │   │
│  │  • 嵌入式部署：集成到现有业务应用                                 │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Coaching & Feedback                            │   │
│  │  • 添加参考问题和业务术语                                         │   │
│  │  • 用户反馈（点赞/点踩）                                          │   │
│  │  • 管理员审核评论                                                 │   │
│  │  • 持续改进机制                                                   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 1.1.2 核心特性分析

**1. Agentic Analytics（代理式分析）**

```python
# ThoughtSpot Spotter 的核心理念
class SpotterAgent:
    """
    Spotter 不仅仅是查询工具，而是一个自主代理：
    1. 理解用户意图，而非仅解析查询
    2. 主动建议下一步分析
    3. 解释数据背后的原因
    4. 推荐可执行的行动
    """
    
    def analyze(self, question: str, context: ConversationContext):
        # 1. 理解问题
        intent = self.understand_intent(question, context)
        
        # 2. 生成分析
        analysis = self.generate_analysis(intent)
        
        # 3. 建议后续问题
        suggestions = self.suggest_next_questions(analysis)
        
        # 4. 推荐行动
        actions = self.recommend_actions(analysis)
        
        return SpotterResponse(
            answer=analysis,
            suggestions=suggestions,
            actions=actions
        )
```

**2. Coaching 机制（训练机制）**

```python
# Spotter 的 Coaching 机制
class SpotterCoaching:
    """
    用户和管理员可以训练 Spotter：
    1. 添加参考问题（Reference Questions）
    2. 定义业务术语（Business Terms）
    3. 提供反馈（Feedback）
    """
    
    def add_reference_question(
        self,
        question: str,
        expected_answer: dict,
        context: str = None
    ):
        """添加参考问题 - 类似 Golden Query"""
        pass
    
    def add_business_term(
        self,
        term: str,
        definition: str,
        synonyms: List[str],
        related_fields: List[str]
    ):
        """添加业务术语 - 增强语义理解"""
        pass
    
    def record_feedback(
        self,
        question: str,
        answer: dict,
        is_helpful: bool,
        comment: str = None
    ):
        """记录用户反馈 - 持续改进"""
        pass
```

#### 1.1.3 我们可以借鉴的设计

| ThoughtSpot 特性 | 我们的现状 | 借鉴方案 |
|-----------------|-----------|---------|
| Coaching 机制 | 无 | 实现 Reference Question + Business Term 管理 |
| 建议后续问题 | 无 | 在 Insight 节点添加建议生成 |
| 行业/角色适配 | 无 | 添加用户画像和行业配置 |
| 嵌入式部署 | 有 API | 增强 API 和 SDK |
| 反馈循环 | 无 | 实现反馈收集和自动学习 |

---

### 1.2 Amazon QuickSight Q

#### 1.2.1 产品概述

Amazon QuickSight Q 是 AWS 的自然语言 BI 查询工具，使用 ML 算法理解数据关系并构建索引。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Amazon QuickSight Q 架构                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Topic Layer（主题层）                          │   │
│  │  • Topic = 语义层，定义业务术语和指标                             │   │
│  │  • 自动索引数据定义                                               │   │
│  │  • 提供自动补全建议                                               │   │
│  │  • 术语到列/值的映射                                              │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    NLP + ML Engine                                │   │
│  │  • 解析自然语言问题                                               │   │
│  │  • 理解用户意图                                                   │   │
│  │  • 检索相关数据                                                   │   │
│  │  • 生成可视化答案                                                 │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Response Types                                 │   │
│  │  • 数字答案                                                       │   │
│  │  • 图表可视化                                                     │   │
│  │  • 表格数据                                                       │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 1.2.2 核心特性分析

**1. Topic（主题）- 语义层**

```python
# QuickSight Q 的 Topic 概念
class QuickSightTopic:
    """
    Topic 是 QuickSight Q 的核心概念：
    - 定义业务术语和指标
    - 建立术语到数据的映射
    - 提供自动补全和建议
    """
    
    def __init__(self, name: str, datasets: List[str]):
        self.name = name
        self.datasets = datasets
        self.synonyms = {}  # 同义词映射
        self.metrics = {}   # 业务指标定义
        self.filters = {}   # 预定义过滤器
    
    def add_synonym(
        self,
        term: str,
        column: str,
        values: List[str] = None
    ):
        """
        添加同义词映射
        例如: "revenue" -> "sales_amount" 列
        """
        self.synonyms[term] = {
            "column": column,
            "values": values
        }
    
    def define_metric(
        self,
        name: str,
        calculation: str,
        description: str
    ):
        """
        定义业务指标
        例如: "profit margin" = (revenue - cost) / revenue
        """
        self.metrics[name] = {
            "calculation": calculation,
            "description": description
        }
```

**2. 自动索引和建议**

```python
# QuickSight Q 的索引机制
class QIndexer:
    """
    Q 自动为 Topic 中的数据建立索引：
    1. 列名和描述
    2. 数据值（用于过滤建议）
    3. 同义词映射
    4. 指标定义
    """
    
    def build_index(self, topic: QuickSightTopic):
        # 1. 索引列定义
        for dataset in topic.datasets:
            for column in dataset.columns:
                self.index_column(column)
        
        # 2. 索引数据值（用于自动补全）
        for column in self._get_categorical_columns():
            values = self._sample_values(column, limit=1000)
            self.index_values(column, values)
        
        # 3. 索引同义词
        for term, mapping in topic.synonyms.items():
            self.index_synonym(term, mapping)
        
        # 4. 索引指标
        for name, metric in topic.metrics.items():
            self.index_metric(name, metric)
    
    def suggest_completions(
        self,
        partial_query: str,
        context: dict
    ) -> List[str]:
        """提供自动补全建议"""
        # 基于索引提供建议
        pass
```

#### 1.2.3 我们可以借鉴的设计

| QuickSight Q 特性 | 我们的现状 | 借鉴方案 |
|------------------|-----------|---------|
| Topic 语义层 | 无 | 实现 SemanticLayer 配置 |
| 同义词映射 | 无 | 添加 Synonym Store |
| 自动索引 | 部分（字段索引） | 扩展到值级别索引 |
| 自动补全 | 无 | 添加 Query Autocomplete |
| 指标定义 | 无 | 实现 Metric Definition |

---

### 1.3 Power BI Q&A

#### 1.3.1 产品概述

Power BI Q&A 是 Microsoft 的自然语言查询功能，深度集成于 Power BI 生态系统。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Power BI Q&A 架构                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Linguistic Schema                              │   │
│  │  • 同义词定义（Synonyms）                                         │   │
│  │  • 措辞建议（Phrasing）                                           │   │
│  │  • 关系定义（Relationships）                                      │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    NLP Engine                                     │   │
│  │  • 问题解析                                                       │   │
│  │  • 意图识别                                                       │   │
│  │  • 字段映射                                                       │   │
│  │  • 可视化类型推断                                                 │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Q&A Visual                                     │   │
│  │  • 嵌入式问答组件                                                 │   │
│  │  • 实时可视化生成                                                 │   │
│  │  • 问题历史追踪                                                   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 1.3.2 核心特性分析

**1. Linguistic Schema（语言模式）**

```python
# Power BI Q&A 的语言模式
class LinguisticSchema:
    """
    Power BI Q&A 的核心是 Linguistic Schema：
    - 定义同义词
    - 定义措辞模式
    - 定义关系
    """
    
    def __init__(self):
        self.synonyms = {}
        self.phrasings = []
        self.relationships = []
    
    def add_synonym(
        self,
        table: str,
        column: str,
        synonyms: List[str]
    ):
        """
        添加同义词
        例如: "Product"."Category" 的同义词: ["type", "kind", "group"]
        """
        key = f"{table}.{column}"
        self.synonyms[key] = synonyms
    
    def add_phrasing(
        self,
        phrasing_type: str,  # "attribute", "name", "adjective"
        definition: dict
    ):
        """
        添加措辞模式
        
        Attribute Phrasing: "the <attribute> of <subject>"
        例如: "the color of the product"
        
        Name Phrasing: "<subject> called <name>"
        例如: "products called iPhone"
        
        Adjective Phrasing: "<adjective> <subject>"
        例如: "expensive products"
        """
        self.phrasings.append({
            "type": phrasing_type,
            "definition": definition
        })
```

**2. 同义词的重要性**

```python
# Power BI Q&A 同义词策略
class SynonymStrategy:
    """
    同义词是 Q&A 准确性的关键：
    
    1. 表名同义词
       - "Sales" -> ["revenue", "orders", "transactions"]
    
    2. 列名同义词
       - "ProductName" -> ["product", "item", "sku"]
    
    3. 值同义词
       - "USA" -> ["United States", "US", "America"]
    
    4. 度量同义词
       - "Total Sales" -> ["revenue", "sales amount", "total revenue"]
    """
    
    def suggest_synonyms(
        self,
        column_name: str,
        sample_values: List[str]
    ) -> List[str]:
        """自动建议同义词"""
        suggestions = []
        
        # 1. 基于列名的常见变体
        suggestions.extend(self._name_variants(column_name))
        
        # 2. 基于业务术语库
        suggestions.extend(self._business_terms(column_name))
        
        # 3. 基于值的推断
        if sample_values:
            suggestions.extend(self._value_based_suggestions(sample_values))
        
        return suggestions
```

#### 1.3.3 我们可以借鉴的设计

| Power BI Q&A 特性 | 我们的现状 | 借鉴方案 |
|------------------|-----------|---------|
| Linguistic Schema | 无 | 实现语言模式配置 |
| 同义词系统 | 无 | 实现 Synonym Store |
| 措辞模式 | 无 | 添加 Phrasing Templates |
| Q&A Visual | 有前端 | 增强交互体验 |
| 问题历史 | 有 | 利用历史改进建议 |

---

### 1.4 Qlik Insight Advisor

#### 1.4.1 产品概述

Qlik Insight Advisor 是 Qlik Sense 的 AI 驱动分析功能，包含 Insight Advisor Chat 对话式分析。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Qlik Insight Advisor 架构                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Business Logic Layer                           │   │
│  │  • Vocabulary（词汇表）                                           │   │
│  │  • Logical Model（逻辑模型）                                      │   │
│  │  • Calendar Periods（日历周期）                                   │   │
│  │  • Behaviors（行为规则）                                          │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Insight Advisor Engine                         │   │
│  │  • NLP + NLG（自然语言处理和生成）                                │   │
│  │  • 意图理解                                                       │   │
│  │  • 跨应用搜索                                                     │   │
│  │  • 可视化推荐                                                     │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Response Types                                 │   │
│  │  • 叙述性回答（Narrative）                                        │   │
│  │  • 可视化回答（Visual）                                           │   │
│  │  • 建议分析（Suggested Analysis）                                 │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 1.4.2 核心特性分析

**1. Business Logic（业务逻辑）**

```python
# Qlik Insight Advisor 的业务逻辑层
class QlikBusinessLogic:
    """
    Qlik 的业务逻辑层是其核心差异化：
    - Vocabulary: 定义业务术语和同义词
    - Logical Model: 定义字段角色和关系
    - Behaviors: 定义分析行为规则
    """
    
    def __init__(self):
        self.vocabulary = Vocabulary()
        self.logical_model = LogicalModel()
        self.behaviors = []
    
    def add_vocabulary_term(
        self,
        term: str,
        synonyms: List[str],
        field_mapping: str
    ):
        """添加词汇表术语"""
        self.vocabulary.add_term(term, synonyms, field_mapping)
    
    def define_field_role(
        self,
        field: str,
        role: str  # "dimension", "measure", "temporal", "geographical"
    ):
        """定义字段角色"""
        self.logical_model.set_role(field, role)
    
    def add_behavior(
        self,
        behavior_type: str,  # "default_aggregation", "calendar_period"
        config: dict
    ):
        """添加行为规则"""
        self.behaviors.append({
            "type": behavior_type,
            "config": config
        })
```

**2. 跨应用搜索**

```python
# Qlik Insight Advisor Chat 的跨应用搜索
class CrossAppSearch:
    """
    Insight Advisor Chat 可以跨多个 Qlik Sense 应用搜索：
    - 在 Hub 中搜索所有可访问的应用
    - 找到最相关的数据源
    - 允许用户切换应用进行深入分析
    """
    
    def search_across_apps(
        self,
        question: str,
        user_context: UserContext
    ) -> List[AppSearchResult]:
        """跨应用搜索"""
        results = []
        
        for app in user_context.accessible_apps:
            relevance = self._calculate_relevance(question, app)
            if relevance > self.threshold:
                results.append(AppSearchResult(
                    app=app,
                    relevance=relevance,
                    suggested_fields=self._suggest_fields(question, app)
                ))
        
        return sorted(results, key=lambda x: x.relevance, reverse=True)
```

#### 1.4.3 我们可以借鉴的设计

| Qlik Insight Advisor 特性 | 我们的现状 | 借鉴方案 |
|--------------------------|-----------|---------|
| Vocabulary 词汇表 | 无 | 实现业务词汇表 |
| Logical Model | 有数据模型 | 增强字段角色定义 |
| Behaviors 行为规则 | 无 | 添加分析行为配置 |
| 跨应用搜索 | 单数据源 | 扩展多数据源支持 |
| NLG 叙述生成 | 有 Insight | 增强叙述质量 |

---

### 1.5 Google Looker Conversational Analytics

#### 1.5.1 产品概述

Google Looker 于 2024 年推出 Conversational Analytics，基于 Gemini 模型提供对话式数据分析。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Looker Conversational Analytics 架构                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Gemini Integration                             │   │
│  │  • Gemini 模型驱动                                                │   │
│  │  • 自然语言理解                                                   │   │
│  │  • 代码生成（LookML）                                             │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Semantic Layer (LookML)                        │   │
│  │  • 统一数据定义                                                   │   │
│  │  • 业务指标                                                       │   │
│  │  • 数据关系                                                       │   │
│  │  • 访问控制                                                       │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Conversational Features                        │   │
│  │  • 无代码可视化生成                                               │   │
│  │  • 公式创建辅助                                                   │   │
│  │  • 幻灯片生成                                                     │   │
│  │  • 持续对话                                                       │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 1.5.2 核心特性分析

**1. Semantic Layer 的重要性**

```python
# Looker 的语义层 (LookML)
class LookMLSemanticLayer:
    """
    Looker 的核心优势是其语义层 LookML：
    - 统一的数据定义
    - 可重用的业务逻辑
    - 版本控制
    - 数据治理
    """
    
    def __init__(self):
        self.views = {}      # 数据视图
        self.explores = {}   # 探索定义
        self.models = {}     # 数据模型
    
    def define_view(
        self,
        name: str,
        sql_table: str,
        dimensions: List[dict],
        measures: List[dict]
    ):
        """定义数据视图"""
        self.views[name] = {
            "sql_table": sql_table,
            "dimensions": dimensions,
            "measures": measures
        }
    
    def define_explore(
        self,
        name: str,
        base_view: str,
        joins: List[dict],
        access_filters: List[dict] = None
    ):
        """定义探索（可查询的数据集）"""
        self.explores[name] = {
            "base_view": base_view,
            "joins": joins,
            "access_filters": access_filters
        }
```

**2. Gemini 驱动的对话分析**

```python
# Looker Conversational Analytics
class LookerConversationalAnalytics:
    """
    基于 Gemini 的对话式分析：
    - 自然语言问答
    - 无需了解 LookML 或 SQL
    - 即时可视化
    """
    
    async def analyze(
        self,
        question: str,
        explore: str,
        conversation_history: List[dict] = None
    ):
        # 1. 使用 Gemini 理解问题
        intent = await self.gemini.understand(
            question,
            context={
                "explore": explore,
                "history": conversation_history
            }
        )
        
        # 2. 生成 LookML 查询
        lookml_query = await self.gemini.generate_query(
            intent,
            explore_schema=self.get_explore_schema(explore)
        )
        
        # 3. 执行查询
        result = await self.execute_query(lookml_query)
        
        # 4. 生成可视化
        visualization = self.recommend_visualization(result)
        
        # 5. 生成叙述
        narrative = await self.gemini.generate_narrative(result)
        
        return ConversationalResponse(
            data=result,
            visualization=visualization,
            narrative=narrative
        )
```

#### 1.5.3 我们可以借鉴的设计

| Looker 特性 | 我们的现状 | 借鉴方案 |
|------------|-----------|---------|
| 语义层 (LookML) | 无 | 实现 Semantic Layer 配置 |
| Gemini 集成 | 使用 OpenAI/Claude | 可扩展 LLM 支持 |
| 无代码可视化 | 有 | 增强可视化推荐 |
| 公式辅助 | 无 | 添加计算字段辅助 |
| 数据治理 | 无 | 添加访问控制 |

---

### 1.6 Tableau Pulse & Ask Data

#### 1.6.1 产品概述

Tableau 自身的 AI 功能包括 Ask Data（自然语言查询）和 Pulse（AI 驱动的洞察）。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Tableau AI 功能架构                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Ask Data (即将演进)                            │   │
│  │  • 自然语言问答                                                   │   │
│  │  • 基于数据源                                                     │   │
│  │  • 支持计算字段、列字段、分组字段、分箱字段                       │   │
│  │  • 不支持：集合、参数、组合字段、层次结构                         │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Tableau Pulse (2024 GA)                        │   │
│  │  • 基于 Einstein GPT                                              │   │
│  │  • 个性化指标洞察                                                 │   │
│  │  • 自然语言摘要                                                   │   │
│  │  • 异常检测和预警                                                 │   │
│  │  • 多指标探索                                                     │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Tableau AI (未来方向)                          │   │
│  │  • 统一的 AI 体验                                                 │   │
│  │  • 增强的自然语言能力                                             │   │
│  │  • 与 Salesforce Einstein 深度集成                                │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 1.6.2 核心特性分析

**1. Ask Data 的设计**

```python
# Tableau Ask Data 的核心设计
class TableauAskData:
    """
    Ask Data 的核心特点：
    - 锚定到数据源
    - 支持特定字段类型
    - 处理自然语言歧义
    """
    
    SUPPORTED_FIELD_TYPES = [
        "calculated_field",
        "column_field",
        "group_field",
        "bin_field"
    ]
    
    UNSUPPORTED_FIELD_TYPES = [
        "set",
        "parameter",
        "combined_field",
        "combined_set",
        "hierarchy"
    ]
    
    def process_question(
        self,
        question: str,
        datasource: DataSource
    ):
        # 1. 解析问题
        parsed = self.parse_question(question)
        
        # 2. 映射到字段
        fields = self.map_to_fields(parsed, datasource)
        
        # 3. 处理歧义
        if self.has_ambiguity(fields):
            return self.request_clarification(fields)
        
        # 4. 生成可视化规范
        viz_spec = self.generate_viz_spec(fields)
        
        return viz_spec
```

**2. Tableau Pulse 的洞察生成**

```python
# Tableau Pulse 的洞察生成
class TableauPulse:
    """
    Tableau Pulse 使用 Einstein GPT 生成洞察：
    - 自动检测指标变化
    - 生成自然语言摘要
    - 个性化推送
    """
    
    async def generate_insight_summary(
        self,
        metric: Metric,
        time_period: str,
        user_context: UserContext
    ):
        # 1. 分析指标趋势
        trend = self.analyze_trend(metric, time_period)
        
        # 2. 检测异常
        anomalies = self.detect_anomalies(metric)
        
        # 3. 使用 Einstein GPT 生成摘要
        summary = await self.einstein_gpt.generate_summary(
            metric=metric,
            trend=trend,
            anomalies=anomalies,
            user_context=user_context
        )
        
        # 4. 个性化调整
        personalized = self.personalize(summary, user_context)
        
        return personalized
```

#### 1.6.3 与我们项目的关系

| Tableau 官方功能 | 我们的实现 | 差异和优势 |
|-----------------|-----------|-----------|
| Ask Data | SemanticParser + FieldMapper | 我们支持更复杂的查询 |
| Pulse 洞察 | Insight 节点 | 我们可定制化更强 |
| Einstein GPT | 可配置 LLM | 我们支持多种 LLM |
| 数据源锚定 | 支持 | 一致 |
| 字段类型限制 | 更灵活 | 我们支持更多类型 |

---

## 2. 最新学术研究分析

### 2.1 DAIL-SQL

#### 2.1.1 研究概述

DAIL-SQL 是一种高效的 Few-Shot Text-to-SQL 方法，在 Spider 排行榜上使用 GPT-4 达到 86.6% 的执行准确率。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    DAIL-SQL 架构                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Example Selection                              │   │
│  │                                                                   │   │
│  │  问题 ──▶ [Masked Question Similarity] ──▶ 候选示例              │   │
│  │                        +                                          │   │
│  │        [Query Similarity (SQL Skeleton)] ──▶ 最终示例            │   │
│  │                                                                   │   │
│  │  关键创新：同时考虑问题相似度和 SQL 骨架相似度                    │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Example Organization                           │   │
│  │                                                                   │   │
│  │  DAIL Organization:                                               │   │
│  │  • 只展示 Question + SQL 对                                       │   │
│  │  • 移除跨域 Schema 信息                                           │   │
│  │  • 大幅减少 Token 消耗                                            │   │
│  │                                                                   │   │
│  │  对比：                                                           │   │
│  │  • Full-Information: 包含完整 Schema（Token 多）                  │   │
│  │  • SQL-Only: 只有 SQL（缺少问题上下文）                           │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Question Representation                        │   │
│  │                                                                   │   │
│  │  推荐表示：                                                       │   │
│  │  • Code Representation Prompt                                     │   │
│  │  • OpenAI Demonstration Prompt                                    │   │
│  │                                                                   │   │
│  │  关键发现：                                                       │   │
│  │  • 外键信息有帮助                                                 │   │
│  │  • "with no explanation" 规则有帮助                               │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 2.1.2 核心技术分析

**1. DAIL Selection（示例选择策略）**

```python
# DAIL-SQL 的示例选择策略
class DAILSelection:
    """
    DAIL Selection 的核心创新：
    同时考虑问题相似度和 SQL 骨架相似度
    """
    
    def select_examples(
        self,
        question: str,
        candidate_pool: List[Example],
        k: int = 5
    ) -> List[Example]:
        # 1. Masked Question Similarity
        # 将问题中的具体值替换为占位符，计算相似度
        masked_question = self.mask_values(question)
        question_scores = {}
        
        for example in candidate_pool:
            masked_example = self.mask_values(example.question)
            score = self.calculate_similarity(masked_question, masked_example)
            question_scores[example.id] = score
        
        # 2. Query Similarity (SQL Skeleton)
        # 使用预训练模型预测 SQL 骨架，计算骨架相似度
        predicted_skeleton = self.predict_skeleton(question)
        query_scores = {}
        
        for example in candidate_pool:
            example_skeleton = self.extract_skeleton(example.sql)
            score = self.calculate_skeleton_similarity(
                predicted_skeleton, example_skeleton
            )
            query_scores[example.id] = score
        
        # 3. 融合分数
        final_scores = {}
        for example in candidate_pool:
            # DAIL 的关键：高问题相似度 + 高骨架相似度
            final_scores[example.id] = (
                question_scores[example.id] * query_scores[example.id]
            )
        
        # 4. 选择 top-k
        sorted_examples = sorted(
            candidate_pool,
            key=lambda x: final_scores[x.id],
            reverse=True
        )
        
        return sorted_examples[:k]
    
    def mask_values(self, text: str) -> str:
        """
        将具体值替换为占位符
        "sales in 2023" -> "sales in [VALUE]"
        """
        # 使用 NER 或规则识别值
        pass
    
    def extract_skeleton(self, sql: str) -> str:
        """
        提取 SQL 骨架
        "SELECT name FROM users WHERE age > 18" 
        -> "SELECT _ FROM _ WHERE _ > _"
        """
        pass
```

**2. DAIL Organization（示例组织策略）**

```python
# DAIL-SQL 的示例组织策略
class DAILOrganization:
    """
    DAIL Organization 的核心：
    - 只展示 Question + SQL 对
    - 移除跨域 Schema 信息
    - 大幅减少 Token 消耗（约 1600 tokens/问题）
    """
    
    def organize_examples(
        self,
        examples: List[Example],
        target_question: str,
        target_schema: str
    ) -> str:
        prompt_parts = []
        
        # 1. 目标 Schema（只包含一次）
        prompt_parts.append(f"### Database Schema\n{target_schema}")
        
        # 2. 示例（只有 Question + SQL，无 Schema）
        prompt_parts.append("### Examples")
        for i, example in enumerate(examples):
            prompt_parts.append(f"""
Example {i+1}:
Question: {example.question}
SQL: {example.sql}
""")
        
        # 3. 目标问题
        prompt_parts.append(f"""
### Task
Question: {target_question}
SQL:
""")
        
        return "\n".join(prompt_parts)
```

#### 2.1.3 实验结果

| 方法 | Spider Dev EX | Spider Test EX | Token/问题 |
|------|--------------|----------------|-----------|
| Zero-shot GPT-4 | 72.3% | - | ~800 |
| Random 5-shot | 79.5% | - | ~3000 |
| DAIL-SQL 5-shot | 82.4% | 86.2% | ~1600 |
| DAIL-SQL + SC | 83.6% | 86.6% | ~1600 |

#### 2.1.4 我们可以借鉴的设计

| DAIL-SQL 特性 | 我们的现状 | 借鉴方案 |
|--------------|-----------|---------|
| Masked Question Similarity | 无 | 实现值掩码的相似度计算 |
| SQL Skeleton Similarity | 无 | 添加骨架相似度 |
| DAIL Organization | 静态示例 | 优化 Prompt 组织 |
| Token 效率 | 未优化 | 减少冗余 Schema |

---

### 2.2 MAC-SQL

#### 2.2.1 研究概述

MAC-SQL 是一个多代理协作框架，在 BIRD 测试集上达到 59.59% 的执行准确率。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    MAC-SQL 架构                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Selector Agent                                 │   │
│  │  • 从大型数据库中选择相关子数据库                                 │   │
│  │  • 减少 Schema 复杂度                                             │   │
│  │  • 使用外部工具或模型                                             │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Decomposer Agent                               │   │
│  │  • 核心 Text-to-SQL 生成                                          │   │
│  │  • Few-shot Chain-of-Thought 推理                                 │   │
│  │  • 分解复杂问题                                                   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Refiner Agent                                  │   │
│  │  • 检测和修复 SQL 错误                                            │   │
│  │  • 使用执行反馈                                                   │   │
│  │  • 迭代优化                                                       │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 2.2.2 核心技术分析

**1. 三代理协作架构**

```python
# MAC-SQL 的三代理架构
class MACSQLFramework:
    """
    MAC-SQL 的核心是三个专门化的代理：
    1. Selector: 选择相关子数据库
    2. Decomposer: 生成 SQL
    3. Refiner: 修复错误
    """
    
    def __init__(self):
        self.selector = SelectorAgent()
        self.decomposer = DecomposerAgent()
        self.refiner = RefinerAgent()
    
    async def generate_sql(
        self,
        question: str,
        database: Database
    ) -> str:
        # 1. Selector: 选择相关子数据库
        sub_database = await self.selector.select(question, database)
        
        # 2. Decomposer: 生成 SQL
        sql = await self.decomposer.generate(question, sub_database)
        
        # 3. Refiner: 检查和修复
        refined_sql = await self.refiner.refine(sql, sub_database)
        
        return refined_sql


class SelectorAgent:
    """
    Selector Agent: 从大型数据库中选择相关部分
    
    解决问题：企业数据库通常有数百个表，
    直接使用完整 Schema 会超出 LLM 上下文限制
    """
    
    async def select(
        self,
        question: str,
        database: Database
    ) -> SubDatabase:
        # 1. 使用 embedding 找相关表
        relevant_tables = await self.find_relevant_tables(
            question, database.tables
        )
        
        # 2. 添加关联表（外键）
        expanded_tables = self.expand_with_foreign_keys(
            relevant_tables, database
        )
        
        # 3. 选择相关列
        relevant_columns = await self.find_relevant_columns(
            question, expanded_tables
        )
        
        return SubDatabase(
            tables=expanded_tables,
            columns=relevant_columns
        )


class DecomposerAgent:
    """
    Decomposer Agent: 核心 SQL 生成
    
    使用 Few-shot Chain-of-Thought 推理
    """
    
    async def generate(
        self,
        question: str,
        sub_database: SubDatabase
    ) -> str:
        # 构建 CoT Prompt
        prompt = self.build_cot_prompt(question, sub_database)
        
        # 生成 SQL
        response = await self.llm.generate(prompt)
        
        # 解析 SQL
        sql = self.extract_sql(response)
        
        return sql
    
    def build_cot_prompt(
        self,
        question: str,
        sub_database: SubDatabase
    ) -> str:
        """
        Chain-of-Thought Prompt 结构：
        1. Schema 信息
        2. Few-shot 示例（带推理过程）
        3. 目标问题
        """
        return f"""
### Database Schema
{sub_database.to_schema_string()}

### Examples
{self.format_cot_examples()}

### Task
Question: {question}

Let's think step by step:
1. Identify the relevant tables and columns
2. Determine the required operations (SELECT, JOIN, WHERE, etc.)
3. Write the SQL query

SQL:
"""


class RefinerAgent:
    """
    Refiner Agent: 检测和修复 SQL 错误
    
    使用执行反馈进行迭代优化
    """
    
    async def refine(
        self,
        sql: str,
        sub_database: SubDatabase,
        max_iterations: int = 3
    ) -> str:
        for i in range(max_iterations):
            # 1. 尝试执行
            try:
                result = await self.execute(sql, sub_database)
                return sql  # 执行成功
            except Exception as e:
                error = str(e)
            
            # 2. 使用 LLM 修复
            sql = await self.fix_sql(sql, error, sub_database)
        
        return sql
    
    async def fix_sql(
        self,
        sql: str,
        error: str,
        sub_database: SubDatabase
    ) -> str:
        prompt = f"""
The following SQL query has an error:

SQL: {sql}
Error: {error}

Database Schema:
{sub_database.to_schema_string()}

Please fix the SQL query:
"""
        response = await self.llm.generate(prompt)
        return self.extract_sql(response)
```

#### 2.2.3 实验结果

| 方法 | BIRD Dev EX | BIRD Test EX | Spider Dev EX |
|------|------------|--------------|---------------|
| GPT-4 Zero-shot | 46.35% | - | 72.3% |
| DIN-SQL | 50.72% | - | 74.2% |
| MAC-SQL | 57.56% | 59.59% | 82.8% |

#### 2.2.4 我们可以借鉴的设计

| MAC-SQL 特性 | 我们的现状 | 借鉴方案 |
|-------------|-----------|---------|
| Selector Agent | FieldMapper (部分) | 增强表级选择 |
| Decomposer Agent | SemanticParser | 添加 CoT 推理 |
| Refiner Agent | 无 | 实现 SelfCorrector |
| 多代理协作 | 单流程 | 可选的多代理模式 |

---

### 2.3 CHESS

#### 2.3.1 研究概述

CHESS (Contextual Harnessing for Efficient SQL Synthesis) 是斯坦福大学提出的多代理框架，
在 BIRD 数据集上达到 SOTA 性能。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CHESS 架构                                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Information Retriever (IR)                     │   │
│  │  • 提取相关数据目录信息                                           │   │
│  │  • 检索数据库值                                                   │   │
│  │  • 层次化检索策略                                                 │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Schema Selector (SS)                           │   │
│  │  • 自适应 Schema 剪枝                                             │   │
│  │  • 处理大型复杂 Schema                                            │   │
│  │  • 保留关键表和列                                                 │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Candidate Generator (CG)                       │   │
│  │  • 生成高质量 SQL 候选                                            │   │
│  │  • 迭代优化查询                                                   │   │
│  │  • 多候选策略                                                     │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Unit Tester (UT)                               │   │
│  │  • LLM 驱动的自然语言单元测试                                     │   │
│  │  • 验证查询正确性                                                 │   │
│  │  • 无需执行即可验证                                               │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 2.3.2 核心技术分析

**1. 四代理协作架构**

```python
# CHESS 的四代理架构
class CHESSFramework:
    """
    CHESS 的核心是四个专门化的代理：
    1. Information Retriever (IR): 提取相关信息
    2. Schema Selector (SS): 剪枝 Schema
    3. Candidate Generator (CG): 生成 SQL
    4. Unit Tester (UT): 验证 SQL
    """
    
    def __init__(self):
        self.ir = InformationRetriever()
        self.ss = SchemaSelector()
        self.cg = CandidateGenerator()
        self.ut = UnitTester()
    
    async def generate_sql(
        self,
        question: str,
        database: Database
    ) -> str:
        # 1. IR: 提取相关信息
        context = await self.ir.retrieve(question, database)
        
        # 2. SS: 剪枝 Schema
        pruned_schema = await self.ss.select(question, database, context)
        
        # 3. CG: 生成 SQL 候选
        candidates = await self.cg.generate(question, pruned_schema, context)
        
        # 4. UT: 验证并选择最佳
        best_sql = await self.ut.test_and_select(candidates, question)
        
        return best_sql


class InformationRetriever:
    """
    Information Retriever: 层次化信息检索
    
    关键创新：
    - 使用数据目录（Data Catalog）
    - 检索数据库中的实际值
    - MinHash + LSH 高效检索
    """
    
    def __init__(self):
        self.minhash_index = None
        self.lsh_index = None
        self.vector_db = None
    
    async def retrieve(
        self,
        question: str,
        database: Database
    ) -> RetrievalContext:
        # 1. 检索相关表描述
        table_descriptions = await self.retrieve_table_descriptions(
            question, database
        )
        
        # 2. 检索相关列描述
        column_descriptions = await self.retrieve_column_descriptions(
            question, database
        )
        
        # 3. 检索相关数据值（关键！）
        relevant_values = await self.retrieve_values(
            question, database
        )
        
        return RetrievalContext(
            table_descriptions=table_descriptions,
            column_descriptions=column_descriptions,
            relevant_values=relevant_values
        )
    
    async def retrieve_values(
        self,
        question: str,
        database: Database
    ) -> Dict[str, List[str]]:
        """
        检索与问题相关的数据库值
        
        例如：问题 "sales in California"
        -> 检索到 state 列中有 "California" 值
        """
        # 使用 MinHash + LSH 进行高效检索
        question_tokens = self.tokenize(question)
        
        relevant_values = {}
        for column in database.get_categorical_columns():
            # 检索相似值
            similar_values = self.lsh_index.query(
                question_tokens,
                column_id=column.id
            )
            if similar_values:
                relevant_values[column.name] = similar_values
        
        return relevant_values


class SchemaSelector:
    """
    Schema Selector: 自适应 Schema 剪枝
    
    解决问题：企业数据库可能有 1000+ 列
    """
    
    async def select(
        self,
        question: str,
        database: Database,
        context: RetrievalContext
    ) -> PrunedSchema:
        # 1. 基于检索上下文选择表
        relevant_tables = self.select_tables(
            question, database, context
        )
        
        # 2. 基于检索上下文选择列
        relevant_columns = self.select_columns(
            question, relevant_tables, context
        )
        
        # 3. 自适应剪枝（根据 LLM 上下文限制）
        pruned = self.adaptive_prune(
            relevant_tables,
            relevant_columns,
            max_tokens=self.max_schema_tokens
        )
        
        return pruned


class UnitTester:
    """
    Unit Tester: LLM 驱动的自然语言单元测试
    
    关键创新：
    - 无需执行 SQL 即可验证
    - 使用自然语言描述预期行为
    - LLM 判断 SQL 是否满足预期
    """
    
    async def test_and_select(
        self,
        candidates: List[str],
        question: str
    ) -> str:
        # 1. 生成单元测试
        unit_tests = await self.generate_unit_tests(question)
        
        # 2. 对每个候选进行测试
        scores = {}
        for sql in candidates:
            score = await self.run_tests(sql, unit_tests)
            scores[sql] = score
        
        # 3. 选择得分最高的
        best_sql = max(scores, key=scores.get)
        
        return best_sql
    
    async def generate_unit_tests(
        self,
        question: str
    ) -> List[UnitTest]:
        """
        生成自然语言单元测试
        
        例如：问题 "total sales by region"
        测试：
        - SQL 应该包含 SUM 聚合
        - SQL 应该按 region 分组
        - SQL 应该返回多行结果
        """
        prompt = f"""
Given the question: "{question}"

Generate unit tests to verify if a SQL query correctly answers this question.
Each test should describe an expected property of the correct SQL.

Tests:
"""
        response = await self.llm.generate(prompt)
        return self.parse_tests(response)
    
    async def run_tests(
        self,
        sql: str,
        unit_tests: List[UnitTest]
    ) -> float:
        """
        运行单元测试
        
        使用 LLM 判断 SQL 是否满足每个测试
        """
        passed = 0
        for test in unit_tests:
            prompt = f"""
SQL: {sql}
Test: {test.description}

Does this SQL satisfy the test? Answer YES or NO.
"""
            response = await self.llm.generate(prompt)
            if "YES" in response.upper():
                passed += 1
        
        return passed / len(unit_tests)
```

#### 2.3.3 实验结果

| 方法 | BIRD Dev EX | BIRD Test EX |
|------|------------|--------------|
| GPT-4 Zero-shot | 46.35% | - |
| DIN-SQL | 50.72% | - |
| MAC-SQL | 57.56% | 59.59% |
| CHESS | 65.0% | 66.69% |

#### 2.3.4 我们可以借鉴的设计

| CHESS 特性 | 我们的现状 | 借鉴方案 |
|-----------|-----------|---------|
| Information Retriever | FieldMapper (部分) | 添加值级别检索 |
| Schema Selector | 无 | 实现自适应 Schema 剪枝 |
| Candidate Generator | QueryBuilder | 添加多候选策略 |
| Unit Tester | 无 | 实现 LLM 单元测试 |
| MinHash + LSH | FAISS | 添加值检索索引 |

---

### 2.4 Spider 2.0 基准测试

#### 2.4.1 研究概述

Spider 2.0 是最新的企业级 Text-to-SQL 基准测试，包含 632 个真实世界的工作流问题。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Spider 2.0 特点                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  数据规模：                                                              │
│  • 632 个真实世界问题                                                    │
│  • 平均 812 列/数据库                                                    │
│  • 复杂嵌套结构                                                          │
│  • 来自 BigQuery、Snowflake 等企业数据库                                 │
│                                                                          │
│  挑战：                                                                  │
│  • 理解复杂数据库元数据                                                  │
│  • 生成复杂嵌套 SQL                                                      │
│  • 处理企业级数据规模                                                    │
│  • 跨多个表的复杂查询                                                    │
│                                                                          │
│  当前 SOTA 性能：                                                        │
│  • Spider 2.0-Snow: 59.05% (最高)                                        │
│  • Spider 2.0-BQ: ~50%                                                   │
│  • Spider 2.0-Lite: ~45%                                                 │
│                                                                          │
│  关键发现：                                                              │
│  • 当前 LLM 在企业级场景仍有很大提升空间                                 │
│  • Schema 理解是主要瓶颈                                                 │
│  • 需要更好的上下文管理策略                                              │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 2.4.2 对我们的启示

```python
# Spider 2.0 揭示的企业级挑战
class EnterpriseTextToSQLChallenges:
    """
    Spider 2.0 揭示的企业级 Text-to-SQL 挑战：
    
    1. Schema 规模：平均 812 列，远超 LLM 上下文
    2. 复杂查询：多表 JOIN、嵌套子查询、窗口函数
    3. 业务逻辑：需要理解业务规则和约定
    4. 数据质量：处理 NULL、异常值、数据类型
    """
    
    # 我们的 Tableau 场景类似：
    # - 数据源可能有数百个字段
    # - 需要理解 Tableau 特有的概念（维度、度量、计算字段）
    # - 需要处理复杂的过滤和聚合
    
    RECOMMENDED_STRATEGIES = [
        "Schema 剪枝：只保留相关表和列",
        "层次化检索：先表后列",
        "值级别检索：帮助理解过滤条件",
        "多候选策略：生成多个 SQL 并选择最佳",
        "自我纠错：使用执行反馈修复错误",
    ]
```

---

## 3. 综合对比与借鉴

### 3.1 商业产品 vs 学术研究 vs 我们的项目

| 维度 | 商业产品 | 学术研究 | Tableau Assistant |
|------|---------|---------|-------------------|
| **目标** | 用户体验、易用性 | 准确率、基准测试 | 准确率 + 可用性 |
| **Schema 处理** | 语义层、同义词 | Schema Linking、剪枝 | RAG 字段检索 |
| **训练数据** | Coaching、反馈 | Few-Shot 示例 | 无 |
| **错误处理** | 用户澄清 | 自我纠错 | 重规划 |
| **可解释性** | 高（面向用户） | 低（面向研究） | 中 |
| **部署复杂度** | 高（企业级） | 低（研究原型） | 中 |

### 3.2 核心能力对比矩阵

| 能力 | ThoughtSpot | QuickSight Q | Power BI | Qlik | Looker | DAIL-SQL | MAC-SQL | CHESS | 我们 |
|------|-------------|--------------|----------|------|--------|----------|---------|-------|------|
| 语义层 | ✅ | ✅ (Topic) | ✅ | ✅ | ✅ (LookML) | ❌ | ❌ | ❌ | ❌ |
| 同义词 | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| 训练/Coaching | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ (Few-Shot) | ✅ | ✅ | ❌ |
| Schema 剪枝 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| 值检索 | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| 自我纠错 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| 多代理 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| 置信度 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |

### 3.3 技术栈对比

| 项目 | LLM | 向量数据库 | 检索策略 | 部署方式 |
|------|-----|-----------|---------|---------|
| ThoughtSpot | 自研 | 未公开 | 未公开 | SaaS |
| QuickSight Q | AWS ML | 未公开 | 索引 | SaaS |
| Power BI | Azure AI | 未公开 | 语言模式 | SaaS/本地 |
| Qlik | 未公开 | 未公开 | 业务逻辑 | SaaS/本地 |
| Looker | Gemini | 未公开 | LookML | SaaS |
| DAIL-SQL | GPT-4 | 无 | 相似度 | 脚本 |
| MAC-SQL | GPT-4 | 无 | Embedding | 脚本 |
| CHESS | GPT-4 | MinHash+LSH | 层次化 | 脚本 |
| **我们** | 可配置 | FAISS | RAG | API |

---

## 4. 针对 Tableau Assistant 的改进建议

### 4.1 优先级排序

基于以上分析，我建议以下改进优先级：

#### P0 - 立即实施（1-2周）

| 改进项 | 借鉴来源 | 预期收益 | 工作量 |
|--------|---------|---------|--------|
| 训练数据管理 | Vanna, ThoughtSpot | +15% 准确率 | 中 |
| 自我纠错机制 | MAC-SQL, CHESS | +10% 准确率 | 中 |
| 动态 Few-Shot | DAIL-SQL | +10% 准确率 | 低 |

#### P1 - 短期实施（2-4周）

| 改进项 | 借鉴来源 | 预期收益 | 工作量 |
|--------|---------|---------|--------|
| 同义词系统 | Power BI, QuickSight | +5% 准确率 | 中 |
| 值级别检索 | CHESS | +5% 准确率 | 中 |
| 置信度评分 | Dataherald | 用户体验提升 | 低 |
| Schema 剪枝 | MAC-SQL, CHESS | 性能提升 | 中 |

#### P2 - 中期实施（1-2月）

| 改进项 | 借鉴来源 | 预期收益 | 工作量 |
|--------|---------|---------|--------|
| 语义层配置 | Looker, QuickSight | 可维护性提升 | 高 |
| LLM 单元测试 | CHESS | +5% 准确率 | 中 |
| 多候选策略 | CHESS | +3% 准确率 | 中 |
| 建议后续问题 | ThoughtSpot | 用户体验提升 | 低 |

### 4.2 具体实施方案

#### 4.2.1 同义词系统实现

```python
# tableau_assistant/src/semantic/synonym_store.py
"""
同义词系统 - 借鉴 Power BI Q&A 和 QuickSight Q

核心功能：
1. 字段同义词管理
2. 值同义词管理
3. 自动同义词建议
"""

from typing import Dict, List, Optional
from pydantic import BaseModel


class SynonymEntry(BaseModel):
    """同义词条目"""
    canonical: str  # 标准名称
    synonyms: List[str]  # 同义词列表
    field_type: str  # "table", "column", "value"
    datasource_luid: Optional[str] = None


class SynonymStore:
    """同义词存储"""
    
    def __init__(self, store, embedding_provider):
        self.store = store
        self.embedding_provider = embedding_provider
        self._cache = {}
    
    async def add_synonym(
        self,
        canonical: str,
        synonyms: List[str],
        field_type: str,
        datasource_luid: str = None
    ):
        """添加同义词"""
        entry = SynonymEntry(
            canonical=canonical,
            synonyms=synonyms,
            field_type=field_type,
            datasource_luid=datasource_luid
        )
        
        # 存储到数据库
        await self.store.aput(
            namespace=("synonyms", datasource_luid or "global"),
            key=canonical,
            value=entry.model_dump()
        )
        
        # 更新缓存
        self._update_cache(entry)
    
    async def resolve_synonym(
        self,
        term: str,
        datasource_luid: str = None
    ) -> Optional[str]:
        """解析同义词，返回标准名称"""
        # 1. 精确匹配
        if term in self._cache:
            return self._cache[term]
        
        # 2. 模糊匹配
        best_match = await self._fuzzy_match(term, datasource_luid)
        if best_match:
            return best_match
        
        return None
    
    async def suggest_synonyms(
        self,
        field_name: str,
        sample_values: List[str] = None
    ) -> List[str]:
        """自动建议同义词"""
        suggestions = []
        
        # 1. 基于命名规则
        suggestions.extend(self._name_based_suggestions(field_name))
        
        # 2. 基于常见业务术语
        suggestions.extend(self._business_term_suggestions(field_name))
        
        # 3. 基于值推断（如果有样本值）
        if sample_values:
            suggestions.extend(self._value_based_suggestions(sample_values))
        
        return list(set(suggestions))
    
    def _name_based_suggestions(self, field_name: str) -> List[str]:
        """基于命名规则的建议"""
        suggestions = []
        
        # 驼峰转空格
        # "productName" -> "product name"
        import re
        spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', field_name).lower()
        if spaced != field_name.lower():
            suggestions.append(spaced)
        
        # 下划线转空格
        # "product_name" -> "product name"
        if '_' in field_name:
            suggestions.append(field_name.replace('_', ' ').lower())
        
        # 常见缩写展开
        abbreviations = {
            'qty': 'quantity',
            'amt': 'amount',
            'dt': 'date',
            'num': 'number',
            'desc': 'description',
            'cat': 'category',
            'prod': 'product',
            'cust': 'customer',
        }
        for abbr, full in abbreviations.items():
            if abbr in field_name.lower():
                suggestions.append(field_name.lower().replace(abbr, full))
        
        return suggestions
```

#### 4.2.2 值级别检索实现

```python
# tableau_assistant/src/retrieval/value_retriever.py
"""
值级别检索 - 借鉴 CHESS

核心功能：
1. 建立值索引（MinHash + LSH）
2. 检索与问题相关的数据库值
3. 帮助理解过滤条件
"""

from typing import Dict, List, Set
from datasketch import MinHash, MinHashLSH


class ValueRetriever:
    """值级别检索器"""
    
    def __init__(
        self,
        num_perm: int = 128,
        threshold: float = 0.5
    ):
        self.num_perm = num_perm
        self.threshold = threshold
        self.lsh_indexes: Dict[str, MinHashLSH] = {}
        self.value_to_column: Dict[str, Set[str]] = {}
    
    def build_index(
        self,
        datasource_luid: str,
        column_values: Dict[str, List[str]]
    ):
        """
        为数据源建立值索引
        
        Args:
            datasource_luid: 数据源 ID
            column_values: {列名: [值列表]}
        """
        lsh = MinHashLSH(
            threshold=self.threshold,
            num_perm=self.num_perm
        )
        
        for column, values in column_values.items():
            for value in values:
                if not value or len(str(value)) < 2:
                    continue
                
                # 创建 MinHash
                minhash = self._create_minhash(str(value))
                
                # 添加到 LSH
                key = f"{column}:{value}"
                lsh.insert(key, minhash)
                
                # 记录值到列的映射
                if value not in self.value_to_column:
                    self.value_to_column[value] = set()
                self.value_to_column[value].add(column)
        
        self.lsh_indexes[datasource_luid] = lsh
    
    def retrieve_values(
        self,
        question: str,
        datasource_luid: str,
        top_k: int = 10
    ) -> Dict[str, List[str]]:
        """
        检索与问题相关的值
        
        Returns:
            {列名: [相关值列表]}
        """
        if datasource_luid not in self.lsh_indexes:
            return {}
        
        lsh = self.lsh_indexes[datasource_luid]
        
        # 1. 提取问题中的潜在值（n-gram）
        potential_values = self._extract_potential_values(question)
        
        # 2. 对每个潜在值进行检索
        results: Dict[str, List[str]] = {}
        
        for pv in potential_values:
            minhash = self._create_minhash(pv)
            matches = lsh.query(minhash)
            
            for match in matches[:top_k]:
                column, value = match.split(':', 1)
                if column not in results:
                    results[column] = []
                if value not in results[column]:
                    results[column].append(value)
        
        return results
    
    def _create_minhash(self, text: str) -> MinHash:
        """创建 MinHash"""
        minhash = MinHash(num_perm=self.num_perm)
        
        # 使用字符 n-gram
        text_lower = text.lower()
        for i in range(len(text_lower) - 2):
            ngram = text_lower[i:i+3]
            minhash.update(ngram.encode('utf-8'))
        
        return minhash
    
    def _extract_potential_values(self, question: str) -> List[str]:
        """从问题中提取潜在值"""
        import re
        
        potential = []
        
        # 1. 引号内的内容
        quoted = re.findall(r'"([^"]+)"', question)
        potential.extend(quoted)
        quoted = re.findall(r"'([^']+)'", question)
        potential.extend(quoted)
        
        # 2. 大写开头的词（可能是专有名词）
        capitalized = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', question)
        potential.extend(capitalized)
        
        # 3. 数字
        numbers = re.findall(r'\b(\d+(?:\.\d+)?)\b', question)
        potential.extend(numbers)
        
        # 4. 日期
        dates = re.findall(r'\b(\d{4}[-/]\d{2}[-/]\d{2})\b', question)
        potential.extend(dates)
        
        return list(set(potential))
```

#### 4.2.3 LLM 单元测试实现

```python
# tableau_assistant/src/validation/llm_unit_tester.py
"""
LLM 单元测试 - 借鉴 CHESS

核心功能：
1. 生成自然语言单元测试
2. 使用 LLM 验证查询
3. 无需执行即可验证
"""

from typing import List, Tuple
from pydantic import BaseModel


class UnitTest(BaseModel):
    """单元测试"""
    description: str
    expected: str  # "yes" or "no"
    weight: float = 1.0


class LLMUnitTester:
    """LLM 单元测试器"""
    
    def __init__(self, llm):
        self.llm = llm
    
    async def generate_tests(
        self,
        question: str,
        data_model_summary: str
    ) -> List[UnitTest]:
        """生成单元测试"""
        prompt = f"""
Given the question and data model, generate unit tests to verify if a VizQL query correctly answers this question.

Question: {question}

Data Model Summary:
{data_model_summary}

Generate 3-5 unit tests. Each test should describe an expected property of the correct query.

Format:
1. [Test description] - Expected: YES/NO
2. [Test description] - Expected: YES/NO
...

Tests:
"""
        response = await self.llm.agenerate(prompt)
        return self._parse_tests(response)
    
    async def run_tests(
        self,
        query: dict,
        tests: List[UnitTest]
    ) -> Tuple[float, List[dict]]:
        """
        运行单元测试
        
        Returns:
            (score, test_results)
        """
        results = []
        total_weight = sum(t.weight for t in tests)
        passed_weight = 0
        
        for test in tests:
            passed = await self._run_single_test(query, test)
            results.append({
                "test": test.description,
                "expected": test.expected,
                "passed": passed
            })
            if passed:
                passed_weight += test.weight
        
        score = passed_weight / total_weight if total_weight > 0 else 0
        return score, results
    
    async def _run_single_test(
        self,
        query: dict,
        test: UnitTest
    ) -> bool:
        """运行单个测试"""
        import json
        
        prompt = f"""
VizQL Query:
{json.dumps(query, indent=2, ensure_ascii=False)}

Test: {test.description}

Does this query satisfy the test? Answer only YES or NO.
"""
        response = await self.llm.agenerate(prompt)
        answer = response.strip().upper()
        
        expected = test.expected.upper()
        return answer == expected
    
    def _parse_tests(self, response: str) -> List[UnitTest]:
        """解析测试"""
        import re
        
        tests = []
        lines = response.strip().split('\n')
        
        for line in lines:
            # 匹配格式: "1. [描述] - Expected: YES/NO"
            match = re.match(
                r'\d+\.\s*(.+?)\s*-\s*Expected:\s*(YES|NO)',
                line,
                re.IGNORECASE
            )
            if match:
                tests.append(UnitTest(
                    description=match.group(1).strip(),
                    expected=match.group(2).upper()
                ))
        
        return tests
```

### 4.3 集成到现有架构

```python
# 修改 SemanticParser 集成新功能
# tableau_assistant/src/agents/semantic_parser/components/step1.py

class EnhancedStep1Component:
    """增强的 Step1 组件"""
    
    def __init__(
        self,
        llm,
        training_store,      # 新增：训练数据存储
        synonym_store,       # 新增：同义词存储
        value_retriever,     # 新增：值检索器
    ):
        self.llm = llm
        self.training_store = training_store
        self.synonym_store = synonym_store
        self.value_retriever = value_retriever
    
    async def execute(self, state: VizQLState, config: dict) -> Step1Output:
        question = state["question"]
        datasource_luid = state["datasource"]
        data_model = state["data_model"]
        
        # 1. 解析同义词
        resolved_question = await self._resolve_synonyms(
            question, datasource_luid
        )
        
        # 2. 检索相关值
        relevant_values = self.value_retriever.retrieve_values(
            question, datasource_luid
        )
        
        # 3. 检索相似的 Golden Query（动态 Few-Shot）
        similar_queries = await self.training_store.get_similar_queries(
            question, datasource_luid, top_k=3
        )
        
        # 4. 构建增强的 Prompt
        prompt = self._build_enhanced_prompt(
            question=resolved_question,
            data_model=data_model,
            similar_queries=similar_queries,
            relevant_values=relevant_values,
            history=state.get("messages", [])
        )
        
        # 5. 调用 LLM
        response = await self.llm.agenerate(prompt)
        
        # 6. 解析输出
        return self._parse_output(response)
    
    async def _resolve_synonyms(
        self,
        question: str,
        datasource_luid: str
    ) -> str:
        """解析问题中的同义词"""
        words = question.split()
        resolved_words = []
        
        for word in words:
            canonical = await self.synonym_store.resolve_synonym(
                word, datasource_luid
            )
            resolved_words.append(canonical or word)
        
        return ' '.join(resolved_words)
    
    def _build_enhanced_prompt(
        self,
        question: str,
        data_model,
        similar_queries: List,
        relevant_values: Dict,
        history: List
    ) -> str:
        """构建增强的 Prompt"""
        prompt_parts = []
        
        # 1. 系统指令
        prompt_parts.append(self.SYSTEM_PROMPT)
        
        # 2. 数据模型（精简版）
        prompt_parts.append(f"### Data Model\n{self._format_data_model(data_model)}")
        
        # 3. 相关值（帮助理解过滤条件）
        if relevant_values:
            prompt_parts.append(f"### Relevant Values\n{self._format_values(relevant_values)}")
        
        # 4. 相似查询（动态 Few-Shot）
        if similar_queries:
            prompt_parts.append("### Similar Examples")
            for i, (query, score) in enumerate(similar_queries):
                prompt_parts.append(f"""
Example {i+1} (similarity: {score:.2f}):
Question: {query.question}
Query: {json.dumps(query.vizql_query, ensure_ascii=False)}
""")
        
        # 5. 对话历史
        if history:
            prompt_parts.append(f"### Conversation History\n{self._format_history(history)}")
        
        # 6. 当前问题
        prompt_parts.append(f"### Current Question\n{question}")
        
        return "\n\n".join(prompt_parts)
```

---

## 5. 总结

### 5.1 关键发现

1. **商业产品的核心优势**：语义层、同义词系统、用户反馈机制
2. **学术研究的核心创新**：Schema 剪枝、值检索、自我纠错、多代理协作
3. **我们的差距**：缺少训练数据管理、同义词系统、自我纠错、值检索

### 5.2 推荐实施路线图

```
Week 1-2: P0 改进
├── 训练数据管理（Golden Query Store）
├── 自我纠错机制（SelfCorrector）
└── 动态 Few-Shot（基于 DAIL-SQL）

Week 3-4: P1 改进
├── 同义词系统（SynonymStore）
├── 值级别检索（ValueRetriever）
├── 置信度评分（ConfidenceCalculator）
└── Schema 剪枝（SchemaSelector）

Month 2: P2 改进
├── 语义层配置
├── LLM 单元测试
├── 多候选策略
└── 建议后续问题
```

### 5.3 预期收益

| 改进阶段 | 预期准确率提升 | 预期用户体验提升 |
|---------|---------------|-----------------|
| P0 完成 | +25-35% | 中 |
| P1 完成 | +10-15% | 高 |
| P2 完成 | +5-10% | 高 |

---

## 附录：参考资源

### 商业产品文档
- [ThoughtSpot Spotter Documentation](https://docs.thoughtspot.com/cloud/latest/spotter-agent.html)
- [Amazon QuickSight Q](https://aws.amazon.com/blogs/aws/amazon-quicksight-q-business-intelligence-using-natural-language-questions/)
- [Power BI Q&A](https://learn.microsoft.com/en-us/power-bi/natural-language/q-and-a-data-sources)
- [Qlik Insight Advisor](https://help.qlik.com/en-US/cloud-services/Insights/insight-advisor-natural-language.htm)
- [Looker Conversational Analytics](https://cloud.google.com/blog/products/business-intelligence/looker-conversational-analytics-now-ga)
- [Tableau Pulse](https://www.tableau.com/blog/tableau-pulse-enhanced-qa)

### 学术论文
- [DAIL-SQL: Text-to-SQL Empowered by Large Language Models](https://arxiv.org/abs/2308.15363)
- [MAC-SQL: A Multi-Agent Collaborative Framework for Text-to-SQL](https://arxiv.org/abs/2312.11242)
- [CHESS: Contextual Harnessing for Efficient SQL Synthesis](https://arxiv.org/abs/2405.16755)
- [Spider 2.0: Evaluating Language Models on Real-World Enterprise Text-to-SQL Workflows](https://arxiv.org/abs/2411.07763)

### 开源实现
- [DAIL-SQL GitHub](https://github.com/BeachWang/DAIL-SQL)
- [MAC-SQL GitHub](https://github.com/wbbeyourself/MAC-SQL)
- [CHESS GitHub](https://github.com/ShayanTalaei/CHESS)
