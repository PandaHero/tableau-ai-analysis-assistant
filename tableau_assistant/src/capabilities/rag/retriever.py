"""
检索器抽象层

参考 DB-GPT 的 BaseRetriever 实现模式，提供统一的检索器接口。

主要功能：
- BaseRetriever 抽象基类
- EmbeddingRetriever（向量检索）
- KeywordRetriever（BM25 关键词检索，使用 jieba 分词）
- HybridRetriever（混合检索）
"""
import asyncio
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from tableau_assistant.src.capabilities.rag.models import (
    FieldChunk,
    RetrievalResult,
    RetrievalSource,
)
from tableau_assistant.src.capabilities.rag.field_indexer import FieldIndexer

logger = logging.getLogger(__name__)

# 尝试导入 jieba，如果不可用则使用简单分词
try:
    # 抑制 jieba 内部的 pkg_resources 弃用警告
    import warnings
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning, module="jieba")
        warnings.filterwarnings("ignore", message="pkg_resources is deprecated")
        import jieba
    JIEBA_AVAILABLE = True
    # 关闭 jieba 的日志输出
    jieba.setLogLevel(logging.WARNING)
except ImportError:
    JIEBA_AVAILABLE = False
    logger.warning("jieba 未安装，将使用简单分词。安装命令: pip install jieba")

# 尝试导入 rank_bm25
try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False
    logger.warning("rank_bm25 未安装，将使用简单 BM25 实现。安装命令: pip install rank-bm25")


@dataclass
class RetrievalConfig:
    """
    检索配置
    
    Attributes:
        top_k: 返回结果数量
        score_threshold: 分数阈值（低于此分数的结果将被过滤）
        use_reranker: 是否使用重排序器
    """
    top_k: int = 10
    score_threshold: float = 0.0
    use_reranker: bool = False


@dataclass
class MetadataFilter:
    """
    元数据过滤器
    
    Attributes:
        role: 字段角色过滤（dimension/measure）
        data_type: 数据类型过滤
        datasource_luid: 数据源 LUID 过滤
        category: 维度类别过滤
    """
    role: Optional[str] = None
    data_type: Optional[str] = None
    datasource_luid: Optional[str] = None
    category: Optional[str] = None
    
    def matches(self, chunk: FieldChunk) -> bool:
        """检查字段分块是否匹配过滤条件"""
        if self.role and chunk.role != self.role:
            return False
        if self.data_type and chunk.data_type != self.data_type:
            return False
        if self.category and chunk.category != self.category:
            return False
        return True


class BaseRetriever(ABC):
    """
    检索器抽象基类
    
    参考 DB-GPT 的 BaseRetriever 实现模式。
    提供同步和异步检索方法。
    
    Requirements: 5.2
    """
    
    def __init__(self, config: Optional[RetrievalConfig] = None):
        """
        初始化检索器
        
        Args:
            config: 检索配置
        """
        self.config = config or RetrievalConfig()
    
    @abstractmethod
    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[MetadataFilter] = None,
        score_threshold: float = 0.0
    ) -> List[RetrievalResult]:
        """
        同步检索
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            filters: 元数据过滤器
            score_threshold: 分数阈值
        
        Returns:
            检索结果列表，按分数降序排列
        """
        pass
    
    @abstractmethod
    async def aretrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[MetadataFilter] = None,
        score_threshold: float = 0.0
    ) -> List[RetrievalResult]:
        """
        异步检索
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            filters: 元数据过滤器
            score_threshold: 分数阈值
        
        Returns:
            检索结果列表，按分数降序排列
        """
        pass
    
    def retrieve_with_scores(
        self,
        query: str,
        score_threshold: float,
        filters: Optional[MetadataFilter] = None
    ) -> List[RetrievalResult]:
        """
        带分数阈值的检索
        
        Args:
            query: 查询文本
            score_threshold: 分数阈值
            filters: 元数据过滤器
        
        Returns:
            检索结果列表
        """
        return self.retrieve(
            query=query,
            top_k=self.config.top_k,
            filters=filters,
            score_threshold=score_threshold
        )
    
    async def aretrieve_with_scores(
        self,
        query: str,
        score_threshold: float,
        filters: Optional[MetadataFilter] = None
    ) -> List[RetrievalResult]:
        """
        异步带分数阈值的检索
        
        Args:
            query: 查询文本
            score_threshold: 分数阈值
            filters: 元数据过滤器
        
        Returns:
            检索结果列表
        """
        return await self.aretrieve(
            query=query,
            top_k=self.config.top_k,
            filters=filters,
            score_threshold=score_threshold
        )
    
    def _apply_filters(
        self,
        results: List[RetrievalResult],
        filters: Optional[MetadataFilter],
        score_threshold: float
    ) -> List[RetrievalResult]:
        """应用过滤器和分数阈值"""
        filtered = []
        for result in results:
            if result.score < score_threshold:
                continue
            if filters and not filters.matches(result.field_chunk):
                continue
            filtered.append(result)
        return filtered



class Tokenizer:
    """
    分词器
    
    支持中英文混合分词，优先使用 jieba。
    """
    
    @staticmethod
    def tokenize(text: str) -> List[str]:
        """
        分词
        
        Args:
            text: 输入文本
        
        Returns:
            词列表
        """
        if not text:
            return []
        
        text = text.lower().strip()
        
        if JIEBA_AVAILABLE:
            # 使用 jieba 分词（支持中英文）
            tokens = list(jieba.cut(text))
            # 过滤空白和标点
            tokens = [t.strip() for t in tokens if t.strip() and not Tokenizer._is_punctuation(t)]
            return tokens
        else:
            # 回退到简单分词
            # 对于中文，按字符分割；对于英文，按空格分割
            tokens = []
            # 使用正则分割中英文
            # 匹配连续的中文字符或连续的英文/数字
            pattern = r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+'
            matches = re.findall(pattern, text)
            for match in matches:
                if re.match(r'[\u4e00-\u9fff]+', match):
                    # 中文：按字符分割（简单处理）
                    tokens.extend(list(match))
                else:
                    # 英文/数字：作为整体
                    tokens.append(match)
            return tokens
    
    @staticmethod
    def _is_punctuation(char: str) -> bool:
        """检查是否为标点符号"""
        import unicodedata
        if len(char) != 1:
            return False
        cat = unicodedata.category(char)
        return cat.startswith('P') or cat.startswith('S')


class EmbeddingRetriever(BaseRetriever):
    """
    向量检索器
    
    封装 FAISS 向量检索，使用 FieldIndexer 进行检索。
    
    Requirements: 5.1
    """
    
    def __init__(
        self,
        field_indexer: FieldIndexer,
        config: Optional[RetrievalConfig] = None
    ):
        """
        初始化向量检索器
        
        Args:
            field_indexer: 字段索引器
            config: 检索配置
        """
        super().__init__(config)
        self.field_indexer = field_indexer
    
    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[MetadataFilter] = None,
        score_threshold: Optional[float] = None
    ) -> List[RetrievalResult]:
        """同步向量检索"""
        if not query or not query.strip():
            return []
        
        # 使用配置值或参数值
        k = top_k if top_k is not None else self.config.top_k
        threshold = score_threshold if score_threshold is not None else self.config.score_threshold
        
        # 使用 FieldIndexer 进行搜索
        search_k = k * 2 if filters else k
        
        results = self.field_indexer.search(
            query=query,
            top_k=search_k,
            category_filter=filters.category if filters else None,
            role_filter=filters.role if filters else None
        )
        
        # 应用额外过滤和分数阈值
        filtered = self._apply_filters(results, filters, threshold)
        
        return filtered[:k]
    
    async def aretrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[MetadataFilter] = None,
        score_threshold: Optional[float] = None
    ) -> List[RetrievalResult]:
        """异步向量检索"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.retrieve(query, top_k, filters, score_threshold)
        )


class KeywordRetriever(BaseRetriever):
    """
    关键词检索器（BM25）
    
    使用 jieba 分词 + rank_bm25 库实现 BM25 检索。
    支持中英文混合检索。
    
    Requirements: 5.1
    """
    
    def __init__(
        self,
        field_indexer: FieldIndexer,
        config: Optional[RetrievalConfig] = None
    ):
        """
        初始化关键词检索器
        
        Args:
            field_indexer: 字段索引器
            config: 检索配置
        """
        super().__init__(config)
        self.field_indexer = field_indexer
        
        # BM25 索引
        self._bm25: Optional[Any] = None
        self._tokenized_corpus: List[List[str]] = []
        self._field_names: List[str] = []
        
        # 构建 BM25 索引
        self._build_bm25_index()
    
    def _build_bm25_index(self) -> None:
        """构建 BM25 索引"""
        chunks = self.field_indexer.get_all_chunks()
        if not chunks:
            return
        
        self._field_names = []
        self._tokenized_corpus = []
        
        for chunk in chunks:
            self._field_names.append(chunk.field_name)
            tokens = Tokenizer.tokenize(chunk.index_text)
            self._tokenized_corpus.append(tokens)
        
        if BM25_AVAILABLE and self._tokenized_corpus:
            self._bm25 = BM25Okapi(self._tokenized_corpus)
            logger.debug(f"BM25 索引已构建（rank_bm25）: {len(chunks)} 个文档")
        else:
            logger.debug(f"BM25 索引已构建（简单实现）: {len(chunks)} 个文档")
    
    def _simple_bm25_scores(self, query_tokens: List[str]) -> List[float]:
        """
        简单 BM25 实现（当 rank_bm25 不可用时）
        
        Args:
            query_tokens: 查询词列表
        
        Returns:
            每个文档的 BM25 分数
        """
        import math
        
        k1 = 1.5
        b = 0.75
        
        # 计算文档频率
        doc_freqs: Dict[str, int] = {}
        for tokens in self._tokenized_corpus:
            unique_tokens = set(tokens)
            for token in unique_tokens:
                doc_freqs[token] = doc_freqs.get(token, 0) + 1
        
        # 计算平均文档长度
        avg_doc_len = sum(len(doc) for doc in self._tokenized_corpus) / len(self._tokenized_corpus)
        num_docs = len(self._tokenized_corpus)
        
        scores = []
        for doc_tokens in self._tokenized_corpus:
            score = 0.0
            doc_len = len(doc_tokens)
            
            # 计算词频
            term_freqs: Dict[str, int] = {}
            for token in doc_tokens:
                term_freqs[token] = term_freqs.get(token, 0) + 1
            
            for term in query_tokens:
                if term not in term_freqs:
                    continue
                
                tf = term_freqs[term]
                df = doc_freqs.get(term, 0)
                
                # IDF
                idf = math.log((num_docs - df + 0.5) / (df + 0.5) + 1)
                
                # BM25 公式
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * doc_len / avg_doc_len)
                
                score += idf * numerator / denominator
            
            scores.append(score)
        
        return scores
    
    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[MetadataFilter] = None,
        score_threshold: Optional[float] = None
    ) -> List[RetrievalResult]:
        """同步关键词检索"""
        if not query or not query.strip():
            return []
        
        if not self._tokenized_corpus:
            return []
        
        # 使用配置值或参数值
        k = top_k if top_k is not None else self.config.top_k
        threshold = score_threshold if score_threshold is not None else self.config.score_threshold
        
        # 分词
        query_tokens = Tokenizer.tokenize(query)
        if not query_tokens:
            return []
        
        # 计算 BM25 分数
        if BM25_AVAILABLE and self._bm25 is not None:
            scores = self._bm25.get_scores(query_tokens)
            # 转换 numpy 数组为 list
            scores = list(scores)
        else:
            scores = self._simple_bm25_scores(query_tokens)
        
        # 归一化分数到 [0, 1]
        max_score = max(scores) if scores else 0
        if max_score > 0:
            normalized_scores = [float(s) / float(max_score) for s in scores]
        else:
            normalized_scores = [float(s) for s in scores]
        
        # 构建结果
        results = []
        scored_fields = list(zip(self._field_names, normalized_scores))
        scored_fields.sort(key=lambda x: x[1], reverse=True)
        
        for rank, (field_name, score) in enumerate(scored_fields, 1):
            if score <= 0:
                continue
            
            chunk = self.field_indexer.get_chunk(field_name)
            if chunk:
                results.append(RetrievalResult(
                    field_chunk=chunk,
                    score=max(0.0, min(1.0, score)),
                    source=RetrievalSource.KEYWORD,
                    rank=rank
                ))
        
        # 应用过滤
        filtered = self._apply_filters(results, filters, threshold)
        
        return filtered[:k]
    
    async def aretrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[MetadataFilter] = None,
        score_threshold: Optional[float] = None
    ) -> List[RetrievalResult]:
        """异步关键词检索"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.retrieve(query, top_k, filters, score_threshold)
        )
    
    def rebuild_index(self) -> None:
        """重建 BM25 索引"""
        self._bm25 = None
        self._tokenized_corpus.clear()
        self._field_names.clear()
        self._build_bm25_index()



class HybridRetriever(BaseRetriever):
    """
    混合检索器
    
    组合向量检索和关键词检索，支持 RRF 或加权融合。
    
    Requirements: 5.1
    """
    
    def __init__(
        self,
        embedding_retriever: EmbeddingRetriever,
        keyword_retriever: KeywordRetriever,
        config: Optional[RetrievalConfig] = None,
        embedding_weight: float = 0.7,
        keyword_weight: float = 0.3,
        use_rrf: bool = True,
        rrf_k: int = 60
    ):
        """
        初始化混合检索器
        
        Args:
            embedding_retriever: 向量检索器
            keyword_retriever: 关键词检索器
            config: 检索配置
            embedding_weight: 向量检索权重（仅在 use_rrf=False 时使用）
            keyword_weight: 关键词检索权重（仅在 use_rrf=False 时使用）
            use_rrf: 是否使用 RRF 融合（默认 True）
            rrf_k: RRF 参数 k（默认 60）
        """
        super().__init__(config)
        self.embedding_retriever = embedding_retriever
        self.keyword_retriever = keyword_retriever
        self.embedding_weight = embedding_weight
        self.keyword_weight = keyword_weight
        self.use_rrf = use_rrf
        self.rrf_k = rrf_k
    
    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[MetadataFilter] = None,
        score_threshold: Optional[float] = None
    ) -> List[RetrievalResult]:
        """同步混合检索"""
        if not query or not query.strip():
            return []
        
        # 使用配置值或参数值
        k = top_k if top_k is not None else self.config.top_k
        threshold = score_threshold if score_threshold is not None else self.config.score_threshold
        
        search_k = k * 2
        
        # 执行两种检索
        embedding_results = self.embedding_retriever.retrieve(
            query, top_k=search_k, filters=filters
        )
        keyword_results = self.keyword_retriever.retrieve(
            query, top_k=search_k, filters=filters
        )
        
        # 融合结果
        if self.use_rrf:
            fused_results = self._rrf_fusion(embedding_results, keyword_results)
        else:
            fused_results = self._weighted_fusion(embedding_results, keyword_results)
        
        # 应用分数阈值
        filtered = [r for r in fused_results if r.score >= threshold]
        
        return filtered[:k]
    
    async def aretrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[MetadataFilter] = None,
        score_threshold: Optional[float] = None
    ) -> List[RetrievalResult]:
        """异步混合检索"""
        if not query or not query.strip():
            return []
        
        # 使用配置值或参数值
        k = top_k if top_k is not None else self.config.top_k
        threshold = score_threshold if score_threshold is not None else self.config.score_threshold
        
        search_k = k * 2
        
        # 并行执行两种检索
        embedding_task = self.embedding_retriever.aretrieve(
            query, top_k=search_k, filters=filters
        )
        keyword_task = self.keyword_retriever.aretrieve(
            query, top_k=search_k, filters=filters
        )
        
        embedding_results, keyword_results = await asyncio.gather(
            embedding_task, keyword_task
        )
        
        # 融合结果
        if self.use_rrf:
            fused_results = self._rrf_fusion(embedding_results, keyword_results)
        else:
            fused_results = self._weighted_fusion(embedding_results, keyword_results)
        
        # 应用分数阈值
        filtered = [r for r in fused_results if r.score >= threshold]
        
        return filtered[:k]
    
    def _rrf_fusion(
        self,
        embedding_results: List[RetrievalResult],
        keyword_results: List[RetrievalResult]
    ) -> List[RetrievalResult]:
        """
        RRF (Reciprocal Rank Fusion) 融合
        
        公式: score = Σ(1/(k+rank))
        
        参考: https://www.elastic.co/guide/en/elasticsearch/reference/current/rrf.html
        
        Args:
            embedding_results: 向量检索结果
            keyword_results: 关键词检索结果
        
        Returns:
            融合后的结果
        """
        rrf_scores: Dict[str, float] = {}
        field_chunks: Dict[str, FieldChunk] = {}
        
        # 处理向量检索结果
        for result in embedding_results:
            field_name = result.field_chunk.field_name
            rrf_score = 1.0 / (self.rrf_k + result.rank)
            rrf_scores[field_name] = rrf_scores.get(field_name, 0) + rrf_score
            field_chunks[field_name] = result.field_chunk
        
        # 处理关键词检索结果
        for result in keyword_results:
            field_name = result.field_chunk.field_name
            rrf_score = 1.0 / (self.rrf_k + result.rank)
            rrf_scores[field_name] = rrf_scores.get(field_name, 0) + rrf_score
            field_chunks[field_name] = result.field_chunk
        
        # 按 RRF 分数排序
        sorted_fields = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        
        # 归一化分数到 [0, 1]
        if sorted_fields:
            max_score = sorted_fields[0][1]
            if max_score > 0:
                sorted_fields = [(name, score / max_score) for name, score in sorted_fields]
        
        # 构建结果
        results = []
        for rank, (field_name, score) in enumerate(sorted_fields, 1):
            results.append(RetrievalResult(
                field_chunk=field_chunks[field_name],
                score=score,
                source=RetrievalSource.HYBRID,
                rank=rank
            ))
        
        return results
    
    def _weighted_fusion(
        self,
        embedding_results: List[RetrievalResult],
        keyword_results: List[RetrievalResult]
    ) -> List[RetrievalResult]:
        """
        加权融合
        
        Args:
            embedding_results: 向量检索结果
            keyword_results: 关键词检索结果
        
        Returns:
            融合后的结果
        """
        weighted_scores: Dict[str, float] = {}
        field_chunks: Dict[str, FieldChunk] = {}
        
        # 处理向量检索结果
        for result in embedding_results:
            field_name = result.field_chunk.field_name
            weighted_score = result.score * self.embedding_weight
            weighted_scores[field_name] = weighted_scores.get(field_name, 0) + weighted_score
            field_chunks[field_name] = result.field_chunk
        
        # 处理关键词检索结果
        for result in keyword_results:
            field_name = result.field_chunk.field_name
            weighted_score = result.score * self.keyword_weight
            weighted_scores[field_name] = weighted_scores.get(field_name, 0) + weighted_score
            field_chunks[field_name] = result.field_chunk
        
        # 按加权分数排序
        sorted_fields = sorted(weighted_scores.items(), key=lambda x: x[1], reverse=True)
        
        # 归一化分数到 [0, 1]
        if sorted_fields:
            max_score = sorted_fields[0][1]
            if max_score > 0:
                sorted_fields = [(name, score / max_score) for name, score in sorted_fields]
        
        # 构建结果
        results = []
        for rank, (field_name, score) in enumerate(sorted_fields, 1):
            results.append(RetrievalResult(
                field_chunk=field_chunks[field_name],
                score=score,
                source=RetrievalSource.HYBRID,
                rank=rank
            ))
        
        return results


class RetrievalPipeline:
    """
    检索管道
    
    组合检索器和重排序器，提供完整的检索流程。
    
    Requirements: 5.1, 4.1
    """
    
    def __init__(
        self,
        retriever: BaseRetriever,
        reranker: Optional[Any] = None
    ):
        """
        初始化检索管道
        
        Args:
            retriever: 检索器
            reranker: 重排序器（可选）
        """
        self.retriever = retriever
        self.reranker = reranker
    
    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[MetadataFilter] = None,
        score_threshold: float = 0.0,
        rerank_top_k: Optional[int] = None
    ) -> List[RetrievalResult]:
        """
        执行检索（可选重排序）
        
        Args:
            query: 查询文本
            top_k: 最终返回结果数量
            filters: 元数据过滤器
            score_threshold: 分数阈值
            rerank_top_k: 重排序前的候选数量（默认 top_k * 3）
        
        Returns:
            检索结果列表
        """
        # 如果有重排序器，先获取更多候选
        if self.reranker is not None:
            candidate_k = rerank_top_k or top_k * 3
            candidates = self.retriever.retrieve(
                query=query,
                top_k=candidate_k,
                filters=filters,
                score_threshold=score_threshold
            )
            
            # 重排序
            results = self.reranker.rerank(query, candidates, top_k)
        else:
            results = self.retriever.retrieve(
                query=query,
                top_k=top_k,
                filters=filters,
                score_threshold=score_threshold
            )
        
        return results
    
    async def asearch(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[MetadataFilter] = None,
        score_threshold: float = 0.0,
        rerank_top_k: Optional[int] = None
    ) -> List[RetrievalResult]:
        """
        异步执行检索（可选重排序）
        """
        if self.reranker is not None:
            candidate_k = rerank_top_k or top_k * 3
            candidates = await self.retriever.aretrieve(
                query=query,
                top_k=candidate_k,
                filters=filters,
                score_threshold=score_threshold
            )
            
            results = await self.reranker.arerank(query, candidates, top_k)
        else:
            results = await self.retriever.aretrieve(
                query=query,
                top_k=top_k,
                filters=filters,
                score_threshold=score_threshold
            )
        
        return results
    
    def batch_search(
        self,
        queries: List[str],
        top_k: int = 10,
        filters: Optional[MetadataFilter] = None
    ) -> Dict[str, List[RetrievalResult]]:
        """
        批量检索
        
        Args:
            queries: 查询列表
            top_k: 每个查询返回的结果数量
            filters: 元数据过滤器
        
        Returns:
            查询到结果的映射
        """
        results = {}
        for query in queries:
            results[query] = self.search(query, top_k, filters)
        return results


class RetrieverFactory:
    """
    检索器工厂
    
    创建不同类型的检索器和检索管道。
    
    Requirements: 5.1
    """
    
    @staticmethod
    def create_embedding_retriever(
        field_indexer: FieldIndexer,
        config: Optional[RetrievalConfig] = None
    ) -> EmbeddingRetriever:
        """创建向量检索器"""
        return EmbeddingRetriever(field_indexer, config)
    
    @staticmethod
    def create_keyword_retriever(
        field_indexer: FieldIndexer,
        config: Optional[RetrievalConfig] = None
    ) -> KeywordRetriever:
        """创建关键词检索器"""
        return KeywordRetriever(field_indexer, config)
    
    @staticmethod
    def create_hybrid_retriever(
        field_indexer: FieldIndexer,
        config: Optional[RetrievalConfig] = None,
        embedding_weight: float = 0.7,
        keyword_weight: float = 0.3,
        use_rrf: bool = True
    ) -> HybridRetriever:
        """创建混合检索器"""
        embedding_retriever = EmbeddingRetriever(field_indexer, config)
        keyword_retriever = KeywordRetriever(field_indexer, config)
        return HybridRetriever(
            embedding_retriever=embedding_retriever,
            keyword_retriever=keyword_retriever,
            config=config,
            embedding_weight=embedding_weight,
            keyword_weight=keyword_weight,
            use_rrf=use_rrf
        )
    
    @staticmethod
    def create_pipeline(
        field_indexer: FieldIndexer,
        retriever_type: str = "hybrid",
        reranker_type: Optional[str] = "llm",
        config: Optional[RetrievalConfig] = None,
        **kwargs
    ) -> RetrievalPipeline:
        """
        创建检索管道
        
        Args:
            field_indexer: 字段索引器
            retriever_type: 检索器类型（embedding/keyword/hybrid）
            reranker_type: 重排序器类型（llm/rrf/default，None 表示不重排序）
                - "llm": LLM 重排序（推荐，精度最高）
                - "rrf": RRF 融合（备选，零延迟）
                - "default": 按分数排序
                - None: 不重排序
            config: 检索配置
            **kwargs: 额外参数
                - llm_provider: LLM 提供商（用于 llm 重排序）
                - llm_model: LLM 模型名称（用于 llm 重排序）
                - rrf_k: RRF 参数 k
        
        Returns:
            配置好的检索管道
        
        Examples:
            # 混合检索 + LLM 重排序（推荐）
            pipeline = RetrieverFactory.create_pipeline(
                field_indexer,
                retriever_type="hybrid",
                reranker_type="llm",
                llm_provider="local",
                llm_model="qwen2.5-72b"
            )
            
            # 混合检索 + RRF 重排序（备选，无需 LLM）
            pipeline = RetrieverFactory.create_pipeline(
                field_indexer,
                retriever_type="hybrid",
                reranker_type="rrf"
            )
        """
        # 创建检索器
        if retriever_type == "embedding":
            retriever = RetrieverFactory.create_embedding_retriever(field_indexer, config)
        elif retriever_type == "keyword":
            retriever = RetrieverFactory.create_keyword_retriever(field_indexer, config)
        else:  # hybrid
            retriever = RetrieverFactory.create_hybrid_retriever(
                field_indexer, config,
                embedding_weight=kwargs.get("embedding_weight", 0.7),
                keyword_weight=kwargs.get("keyword_weight", 0.3),
                use_rrf=kwargs.get("use_rrf", True)
            )
        
        # 创建重排序器
        reranker = None
        if reranker_type:
            from tableau_assistant.src.model_manager import select_reranker
            
            reranker = select_reranker(
                reranker_type=reranker_type,
                top_k=kwargs.get("rerank_top_k", 10),
                llm_provider=kwargs.get("llm_provider"),
                llm_model=kwargs.get("llm_model"),
                rrf_k=kwargs.get("rrf_k", 60)
            )
        
        return RetrievalPipeline(retriever, reranker)


__all__ = [
    "RetrievalConfig",
    "MetadataFilter",
    "BaseRetriever",
    "EmbeddingRetriever",
    "KeywordRetriever",
    "HybridRetriever",
    "RetrievalPipeline",
    "RetrieverFactory",
    "Tokenizer",
]
