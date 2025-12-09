# 需求文档

## 简介

本文档定义了 RAG（检索增强生成）系统优化的需求。当前系统存在以下问题：

1. RAG 置信度计算不准确（都是 1.0），原因是 `(score + 1) / 2` 转换公式导致高分集中
2. 已实现的 RAG 组件（HybridRetriever、Reranker、KnowledgeAssembler）未被实际使用
3. 字段映射只使用了向量检索，没有利用 BM25 关键词检索和重排序

本优化旨在充分利用已实现的 RAG 组件，提升字段映射准确性。

## 术语表

- **RAG**: Retrieval-Augmented Generation，检索增强生成
- **FieldIndexer**: 字段索引器，负责构建和管理字段的向量索引
- **SemanticMapper**: 语义映射器，将业务术语映射到技术字段名
- **KnowledgeAssembler**: 知识组装器，负责加载元数据和创建检索器
- **HybridRetriever**: 混合检索器，组合向量检索和 BM25 关键词检索
- **Reranker**: 重排序器，对检索结果进行重新排序
- **RRF**: Reciprocal Rank Fusion，倒数排名融合算法
- **BM25**: Best Matching 25，经典的关键词检索算法
- **Dimension Hierarchy**: 维度层级，描述维度字段的类别、层级和粒度

## 需求

### 需求 1: 修复 RAG 置信度计算

**用户故事:** 作为开发者，我希望 RAG 检索返回准确的置信度分数，以便我能够做出明智的决策，判断何时需要使用 LLM 回退。

#### 验收标准

1. 当系统计算相似度分数时，FieldIndexer 应返回范围在 [0, 1] 的原始余弦相似度值，不进行人为转换
2. 当查询与字段标题完全匹配时，系统应返回 0.85 到 0.95 之间的置信度分数，而不是 1.0
3. 当显示检索结果时，系统应同时包含原始 FAISS 分数和归一化置信度，用于调试目的
4. 当置信度分数低于 0.7 时，系统应触发 LLM 回退进行字段选择

### 需求 2: 启用完整 RAG 流程

**用户故事:** 作为开发者，我希望使用完整的 RAG 流程，包括混合检索和重排序，以提高字段映射的准确性。

#### 验收标准

1. 当初始化字段映射时，系统应使用 KnowledgeAssembler 加载元数据，采用按字段分块策略
2. 当执行字段检索时，系统应使用 HybridRetriever，结合 EmbeddingRetriever 和 KeywordRetriever，并使用 RRF 融合
3. 当 HybridRetriever 返回结果时，系统应在置信度评估之前应用 RRFReranker 对候选项重新排序
4. 当 jieba 分词器不可用时，系统应优雅地回退到简单分词并记录警告日志
5. 当检索流程完成时，系统应记录延迟分解，包括向量化时间、检索时间和重排序时间
6. 当字段映射成功时，系统应将结果缓存到 MappingCache（SQLite 持久化），TTL 为 24 小时
7. 当相同查询再次执行时，系统应优先从 MappingCache 返回缓存结果，避免重复检索


