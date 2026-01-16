"""Schema Linking 组件 - 使用统一 RAG 基础设施。

本模块实现 Schema Linking 的回退机制，确保召回不足时能够自动回退到
FieldMapper 路径，避免"候选过滤掉正确字段"的系统性错误。

设计原则（Requirements 0.13, 17.7.4）：
- Schema Linking 是优化手段，不能牺牲正确性
- 召回不足时必须有回退路径
- 所有降级必须有指标与结构化日志
- 使用统一 RAG 基础设施（infra/rag）

回退触发条件：
- 候选集为空
- 所有候选置信度 < 阈值
- Schema Linking 超时
- Schema Linking 异常
- 低覆盖信号（top1 与 topk 分数差距过小、术语命中率过低、候选分数整体偏低）

Usage:
    from tableau_assistant.src.agents.semantic_parser.components.schema_linking import (
        SchemaLinking,
        SchemaLinkingResult,
        SchemaLinkingFallbackReason,
    )
    
    # 使用配置文件中的默认值
    schema_linking = SchemaLinking()
    
    result = await schema_linking.link(
        question="各地区上月销售额",
        data_model=data_model,
        config=config,
    )
    
    if result.fallback_triggered:
        logger.warning(f"Schema linking fallback: {result.fallback_reason}")
        # 使用 FieldMapper 路径
    else:
        # 使用候选集
        candidates = result.candidates
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional



from pydantic import BaseModel, Field
from langgraph.types import RunnableConfig

# 从统一 RAG 基础设施导入
from ....infra.rag import (
    FieldIndexer,
    FieldChunk,
    RetrievalResult,
    RetrievalSource,
    create_retriever,
    RetrievalMode,
    FAST_RECALL_CONFIG,
    ExactRetriever,
    ExactRetrieverConfig,
    BatchEmbeddingOptimizer,
    BatchEmbeddingConfig,
)
from ....infra.observability import get_metrics_from_config
from ....infra.config.settings import settings

logger = logging.getLogger(__name__)


class SchemaLinkingFallbackReason(str, Enum):
    """Schema Linking 回退原因枚举。
    
    用于指标分类和结构化日志。
    """
    EMPTY_CANDIDATES = "empty_candidates"  # 候选集为空
    LOW_CONFIDENCE = "low_confidence"  # 所有候选置信度过低
    TIMEOUT = "timeout"  # Schema Linking 超时
    ERROR = "error"  # Schema Linking 异常
    LOW_COVERAGE_SCORE_SPREAD = "low_coverage_score_spread"  # top1 与 topk 分数差距过小
    LOW_COVERAGE_TERM_HIT = "low_coverage_term_hit"  # 术语命中率过低
    LOW_COVERAGE_AVG_SCORE = "low_coverage_avg_score"  # 候选分数整体偏低


@dataclass
class ScoringWeights:
    """两阶段打分融合权重配置。
    
    用于融合多路召回的分数：精确匹配 + embedding + reranker。
    
    Attributes:
        exact_match: 精确匹配权重（最高优先级，命中直接置顶）
        embedding: 向量相似度权重
        reranker: Reranker 分数权重（可选）
    """
    exact_match: float = 1.0      # 精确匹配（最高优先级）
    embedding: float = 0.6        # 向量相似度
    reranker: float = 0.4         # Reranker 分数（可选）



class FieldCandidate(BaseModel):


    """字段候选数据类。
    
    表示 Schema Linking 检索到的候选字段，支持两阶段打分融合。
    
    Attributes:
        candidate_id: 候选 ID，格式 "{role}_{index}"，如 "dim_0", "meas_1"
        field_name: 字段名（API 名称）
        field_caption: 字段标题（显示名称）
        canonical_name: 规范化字段名（优先 caption，无则 name）
        field_type: 字段类型（dimension/measure）
        confidence: 最终融合置信度（0-1）
        table_name: 表名（可选，多表场景）
        sample_values: 样例值（可选，用于展示）
        hierarchy_level: 层级级别（可选，维度层级）
        hierarchy_info: 层级信息（可选，维度层级详情）
        
        # 两阶段打分字段
        exact_match: 是否精确匹配命中
        embedding_score: 向量相似度分数（0-1）
        reranker_score: Reranker 分数（0-1，可选）

    """
    # 必填字段
    candidate_id: str  # 格式: "{role}_{index}" 如 "dim_0", "meas_1"
    field_name: str
    field_caption: str
    canonical_name: str  # = caption if caption else name
    field_type: str  # "dimension" or "measure"
    confidence: float = Field(ge=0.0, le=1.0)
    
    # 可选字段
    table_name: Optional[str] = None
    sample_values: Optional[List[str]] = None
    hierarchy_level: Optional[int] = None
    hierarchy_info: Optional[Dict[str, Any]] = None
    
    # 两阶段打分字段
    exact_match: bool = False
    embedding_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    reranker_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    
    # 原始术语（用于追溯）
    original_term: Optional[str] = None
    
    @classmethod
    def compute_final_score(
        cls,
        exact_match: bool,
        embedding_score: Optional[float],
        reranker_score: Optional[float],
        weights: Optional[ScoringWeights] = None,
    ) -> float:
        """计算融合分数。"""
        if weights is None:
            weights = ScoringWeights()
        
        # 精确匹配：直接置顶
        if exact_match:
            return 1.0
        
        # 加权融合
        score = 0.0
        total_weight = 0.0
        
        if embedding_score is not None:
            score += weights.embedding * embedding_score
            total_weight += weights.embedding
        if reranker_score is not None:
            score += weights.reranker * reranker_score
            total_weight += weights.reranker
        
        if total_weight > 0:
            return score / total_weight
        return 0.0

    
    @classmethod
    def from_retrieval_result(
        cls,
        result: RetrievalResult,
        candidate_id: str,
    ) -> "FieldCandidate":
        """从 RetrievalResult 转换为 FieldCandidate。"""
        chunk = result.field_chunk
        return cls(
            candidate_id=candidate_id,
            field_name=chunk.field_name,
            field_caption=chunk.field_caption,
            canonical_name=chunk.field_caption or chunk.field_name,
            field_type=chunk.role or "dimension",
            confidence=result.score,
            table_name=chunk.table_name,
            sample_values=chunk.sample_values,
            exact_match=(result.source == RetrievalSource.EXACT),
            embedding_score=result.score if result.source == RetrievalSource.EMBEDDING else None,
            original_term=result.original_term,
        )


class SchemaCandidates(BaseModel):
    """Schema 候选集容器。
    
    包含维度、度量、过滤值候选，以及元信息。
    """
    dimensions: List[FieldCandidate] = Field(default_factory=list)
    measures: List[FieldCandidate] = Field(default_factory=list)
    filter_value_candidates: Dict[str, List[str]] = Field(default_factory=dict)
    
    # 元信息
    total_fields: int = 0
    is_degraded: bool = False
    search_pool: str = "both"  # dimensions_only/measures_only/both
    
    def to_prompt_summary(
        self,
        max_dims: int = 20,
        max_meas: int = 15,
    ) -> str:
        """生成用于 Step1 prompt 的摘要。"""
        lines = []
        
        if self.dimensions:
            lines.append("## 维度候选")
            for i, dim in enumerate(self.dimensions[:max_dims]):
                score_info = f"(置信度: {dim.confidence:.2f})"
                if dim.exact_match:
                    score_info = "(精确匹配)"
                lines.append(f"- [{dim.candidate_id}] {dim.canonical_name} {score_info}")
            if len(self.dimensions) > max_dims:
                lines.append(f"  ... 还有 {len(self.dimensions) - max_dims} 个维度候选")
        
        if self.measures:
            lines.append("\n## 度量候选")
            for i, meas in enumerate(self.measures[:max_meas]):
                score_info = f"(置信度: {meas.confidence:.2f})"
                if meas.exact_match:
                    score_info = "(精确匹配)"
                lines.append(f"- [{meas.candidate_id}] {meas.canonical_name} {score_info}")
            if len(self.measures) > max_meas:
                lines.append(f"  ... 还有 {len(self.measures) - max_meas} 个度量候选")
        
        if self.is_degraded:
            lines.append(f"\n⚠️ 降级模式：数据源共 {self.total_fields} 个字段")
        
        return "\n".join(lines)
    
    def get_all_candidates(self) -> List[FieldCandidate]:
        """获取所有候选（维度 + 度量）。"""
        return self.dimensions + self.measures
    
    def get_candidate_by_id(self, candidate_id: str) -> Optional[FieldCandidate]:
        """根据 candidate_id 获取候选。"""
        for candidate in self.get_all_candidates():
            if candidate.candidate_id == candidate_id:
                return candidate
        return None
    
    def is_empty(self) -> bool:
        """检查候选集是否为空。"""
        return len(self.dimensions) == 0 and len(self.measures) == 0


# 停用词集合（中英文）
STOPWORDS: set = {
    # 中文停用词
    "的", "是", "在", "有", "和", "与", "或", "了", "吗", "呢", "吧",
    "什么", "怎么", "如何", "多少", "哪些", "哪个", "为什么",
    "请", "帮", "我", "你", "他", "她", "它", "们", "这", "那",
    "一个", "一些", "所有", "每个", "各个",
    # 英文停用词
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would",
    "can", "could", "may", "might", "must", "shall", "should",
    "what", "which", "who", "whom", "whose", "where", "when", "why", "how",
    "this", "that", "these", "those", "all", "each", "every", "some", "any",
}

# 时间相关词汇（不作为业务术语）
TIME_WORDS: set = {
    "今天", "昨天", "明天", "今年", "去年", "明年",
    "本月", "上月", "下月", "本周", "上周", "下周",
    "本季度", "上季度", "下季度", "本年度", "上年度",
    "近", "最近", "过去", "未来", "之前", "之后",
    "日", "周", "月", "季", "年", "天",
    "today", "yesterday", "tomorrow", "year", "month", "week", "day",
    "last", "next", "this", "current", "previous", "recent",
}

# 计算相关词汇（不作为业务术语）
COMPUTATION_WORDS: set = {
    "总", "总计", "合计", "平均", "均值", "最大", "最小", "最高", "最低",
    "排名", "排序", "占比", "比例", "百分比", "增长", "下降",
    "同比", "环比", "累计", "汇总", "统计", "分析",
    "sum", "total", "average", "avg", "max", "min", "count",
    "rank", "ratio", "percent", "percentage", "growth", "decline",
    "yoy", "mom", "cumulative", "running",
}


@dataclass
class TermExtractorConfig:
    """TermExtractor 配置。"""
    min_term_length: int = 2
    max_term_length: int = 10
    max_terms: int = 10
    enable_jieba: bool = True
    enable_ngram: bool = True


class TermExtractor:
    """增强版术语提取器 - 字典驱动。
    
    实现三层术语提取：
    1. 字典匹配（优先级最高）：直接匹配字段名/caption
    2. jieba 分词：使用自定义词典增强分词
    3. N-gram 补充：捕获复合词
    """
    
    def __init__(self, config: Optional[TermExtractorConfig] = None):
        self.config = config or TermExtractorConfig()
        self._field_dict: set = set()
        self._alias_map: Dict[str, str] = {}
        self._jieba_initialized: bool = False
    
    def build_dictionary(self, fields: List[Any]) -> None:
        """构建字段名词典。"""
        self._field_dict.clear()
        self._alias_map.clear()
        
        for field_obj in fields:
            # 支持 FieldChunk 和 FieldMetadata
            if isinstance(field_obj, FieldChunk):
                field_name = field_obj.field_name
                field_caption = field_obj.field_caption or ''
            else:
                field_name = getattr(field_obj, 'name', '') or ''
                field_caption = getattr(field_obj, 'fieldCaption', '') or ''
            
            if field_name:
                self._field_dict.add(field_name.lower())
            if field_caption:
                self._field_dict.add(field_caption.lower())
            
            if self.config.enable_jieba:
                self._add_to_jieba(field_caption)
                self._add_to_jieba(field_name)
            
            aliases = getattr(field_obj, 'aliases', None) or []
            for alias in aliases:
                self._alias_map[alias.lower()] = field_caption or field_name
                if self.config.enable_jieba:
                    self._add_to_jieba(alias)
        
        logger.debug(
            f"TermExtractor dictionary built: {len(self._field_dict)} terms, "
            f"{len(self._alias_map)} aliases"
        )
    
    def _add_to_jieba(self, word: str) -> None:
        """将词加入 jieba 自定义词典。"""
        if not word or len(word) < self.config.min_term_length:
            return
        try:
            import jieba
            jieba.add_word(word, freq=1000)
            self._jieba_initialized = True
        except ImportError:
            pass
    
    def extract(self, question: str) -> List[str]:
        """提取术语。"""
        terms: List[str] = []
        question_lower = question.lower()
        
        # 1. 字典匹配
        for word in self._field_dict:
            if word in question_lower:
                terms.append(word)
        
        # 2. jieba 分词
        if self.config.enable_jieba:
            jieba_terms = self._extract_with_jieba(question)
            terms.extend(jieba_terms)
        
        # 3. N-gram 补充
        if self.config.enable_ngram:
            ngram_terms = self._extract_ngrams(question)
            terms.extend(ngram_terms)
        
        # 去重并归一化
        normalized_terms = []
        seen = set()
        for term in terms:
            normalized = self._alias_map.get(term.lower(), term)
            if normalized.lower() not in seen:
                seen.add(normalized.lower())
                normalized_terms.append(normalized)
        
        return normalized_terms[:self.config.max_terms]
    
    def _extract_with_jieba(self, question: str) -> List[str]:
        """使用 jieba 分词提取术语。"""
        try:
            import jieba
        except ImportError:
            return []
        
        terms = []
        words = jieba.lcut(question)
        for word in words:
            if self._is_valid_term(word):
                terms.append(word)
        return terms
    
    def _extract_ngrams(self, question: str) -> List[str]:
        """使用 N-gram 提取复合词。"""
        terms = []
        try:
            import jieba
            words = jieba.lcut(question)
        except ImportError:
            words = list(question)
        
        for i in range(len(words) - 1):
            bigram = words[i] + words[i+1]
            if (self.config.min_term_length <= len(bigram) <= self.config.max_term_length
                and bigram.lower() in self._field_dict):
                terms.append(bigram)
        
        for i in range(len(words) - 2):
            trigram = words[i] + words[i+1] + words[i+2]
            if (self.config.min_term_length <= len(trigram) <= self.config.max_term_length
                and trigram.lower() in self._field_dict):
                terms.append(trigram)
        
        return terms
    
    def _is_valid_term(self, word: str) -> bool:
        """判断是否为有效术语。"""
        if len(word) < self.config.min_term_length:
            return False
        if len(word) > self.config.max_term_length:
            return False
        
        word_lower = word.lower()
        if word_lower in STOPWORDS:
            return False
        if word_lower in TIME_WORDS:
            return False
        if word_lower in COMPUTATION_WORDS:
            return False
        if word.isdigit():
            return False
        
        return True
    
    def add_alias(self, alias: str, canonical_name: str) -> None:
        """添加别名映射。"""
        self._alias_map[alias.lower()] = canonical_name
        if self.config.enable_jieba:
            self._add_to_jieba(alias)
    
    def get_canonical_name(self, term: str) -> str:
        """获取术语的规范名。"""
        return self._alias_map.get(term.lower(), term)


class SchemaLinkingResult(BaseModel):
    """Schema Linking 结果数据类。"""
    candidates: List[FieldCandidate] = Field(default_factory=list)
    fallback_triggered: bool = False
    fallback_reason: Optional[SchemaLinkingFallbackReason] = None
    fallback_details: Optional[str] = None
    execution_time_ms: int = 0


@dataclass
class SchemaLinkingConfig:
    """Schema Linking 配置。"""
    min_candidates: int = settings.schema_linking_min_candidates
    min_confidence: float = settings.schema_linking_min_confidence
    timeout_ms: int = settings.schema_linking_timeout_ms
    min_term_hit_ratio: float = settings.schema_linking_min_term_hit_ratio
    min_score_spread: float = settings.schema_linking_min_score_spread
    min_avg_score: float = settings.schema_linking_min_avg_score


@dataclass
class SchemaLinkingComponentConfig:
    """SchemaLinkingComponent 配置。"""
    top_k_question: int = 30
    top_k_term: int = 10
    min_score: float = 0.3
    max_terms: int = 10
    dedup_key: str = "field_name"
    fallback_on_empty: bool = True
    degradation_threshold: int = 2000
    dim_meas_threshold: float = 0.2


class SchemaLinkingComponent:
    """Schema Linking 组件 - 使用统一 RAG 基础设施。
    
    实现完整的 Schema Linking 流程：
    1. 使用 ExactRetriever 进行 O(1) 精确匹配
    2. 使用 create_retriever(FAST_RECALL) 进行向量检索
    3. 两阶段打分融合
    4. 合并去重
    
    Requirements: 17.7.4 - 迁移 SchemaLinking 使用统一 RAG
    """
    
    def __init__(
        self,
        field_indexer: FieldIndexer,
        term_extractor: TermExtractor,
        embedding_optimizer: Optional[BatchEmbeddingOptimizer] = None,
        cache: Optional[Any] = None,
        config: Optional[SchemaLinkingComponentConfig] = None,
        scoring_weights: Optional[ScoringWeights] = None,
    ):
        """初始化 Schema Linking 组件。
        
        Args:
            field_indexer: 统一 RAG 字段索引器（infra/rag/FieldIndexer）
            term_extractor: 术语提取器
            embedding_optimizer: 批量 Embedding 优化器（可选，来自 infra/rag）
            cache: 缓存（可选）
            config: 组件配置
            scoring_weights: 打分权重配置
        """
        self.field_indexer = field_indexer
        self.term_extractor = term_extractor
        self.embedding_optimizer = embedding_optimizer
        self.cache = cache
        self.config = config or SchemaLinkingComponentConfig()
        self.scoring_weights = scoring_weights or ScoringWeights()
        
        # 使用统一 RAG 创建检索器
        self._retriever = create_retriever(
            mode=RetrievalMode.FAST_RECALL,
            field_indexer=field_indexer,
            config=FAST_RECALL_CONFIG,
        )
        
        # 创建精确匹配检索器
        self._exact_retriever = ExactRetriever(ExactRetrieverConfig())
        
        # 预计算中心向量（用于判断检索池）
        self._dim_centroid: Optional[List[float]] = None
        self._meas_centroid: Optional[List[float]] = None


    
    def build_index(self, fields: List[Any]) -> None:
        """构建索引。
        
        Args:
            fields: 字段元数据列表
        """
        # 构建统一 RAG 索引
        self.field_indexer.index_fields(fields)
        
        # 构建精确匹配索引
        chunks = self.field_indexer.get_all_chunks()
        self._exact_retriever.build_index(chunks)
        
        # 构建术语词典
        self.term_extractor.build_dictionary(chunks)


        
        logger.debug(f"SchemaLinkingComponent index built: {len(chunks)} fields")
    
    async def execute(
        self,
        canonical_question: str,
        data_model: Any,
        datasource_luid: str,
        extracted_terms: Optional[List[str]] = None,
    ) -> SchemaCandidates:
        """执行 Schema Linking。"""
        import time
        start_time = time.monotonic()
        
        # 1. 检查缓存
        cache_key = self._build_cache_key(canonical_question, datasource_luid)
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                logger.debug(f"Schema linking cache hit: {cache_key[:50]}")
                return cached
        
        # 2. 提取术语
        if extracted_terms is None:
            extracted_terms = self.term_extractor.extract(canonical_question)
        
        # 3. 精确匹配（使用统一 RAG 的 ExactRetriever）
        exact_results: List[RetrievalResult] = []
        for term in extracted_terms[:self.config.max_terms]:
            results = self._exact_retriever.retrieve(term)
            exact_results.extend(results)
        
        # 4. 向量检索（使用统一 RAG 的 create_retriever）
        vector_results: List[RetrievalResult] = []


        try:
            vector_results = await self._retriever.aretrieve(
                canonical_question,
                top_k=self.config.top_k_question,
            )
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")
        
        # 5. 合并去重 + 两阶段打分融合
        candidates = self._merge_results(
            exact_results=exact_results,
            vector_results=vector_results,
            data_model=data_model,
        )


        
        # 6. 设置元信息
        candidates.total_fields = len(data_model.fields) if hasattr(data_model, 'fields') else 0
        candidates.is_degraded = candidates.total_fields > self.config.degradation_threshold
        
        # 7. 缓存结果
        if self.cache:
            self.cache.set(cache_key, candidates)
        
        execution_time_ms = int((time.monotonic() - start_time) * 1000)
        logger.debug(
            f"Schema linking completed in {execution_time_ms}ms: "
            f"{len(candidates.dimensions)} dims, {len(candidates.measures)} meas"
        )
        
        return candidates
    
    def _merge_results(
        self,
        exact_results: List[RetrievalResult],
        vector_results: List[RetrievalResult],
        data_model: Any,
    ) -> SchemaCandidates:
        """合并去重 + 两阶段打分融合。"""
        # 按 field_name 去重
        field_scores: Dict[str, Dict[str, Any]] = {}
        
        # 处理精确匹配（最高优先级）
        for result in exact_results:
            field_name = result.field_chunk.field_name
            if field_name not in field_scores:
                field_scores[field_name] = {
                    "result": result,
                    "exact_match": True,
                    "embedding_score": None,
                }
            else:
                field_scores[field_name]["exact_match"] = True
        
        # 处理向量匹配
        for result in vector_results:
            field_name = result.field_chunk.field_name
            if field_name not in field_scores:
                field_scores[field_name] = {
                    "result": result,
                    "exact_match": False,
                    "embedding_score": result.score,
                }
            else:
                current_score = field_scores[field_name].get("embedding_score")
                if current_score is None or result.score > current_score:
                    field_scores[field_name]["embedding_score"] = result.score
        
        # 构建候选列表
        dimensions: List[FieldCandidate] = []
        measures: List[FieldCandidate] = []
        dim_idx = 0
        meas_idx = 0
        
        for field_name, scores in field_scores.items():
            result = scores["result"]
            chunk = result.field_chunk
            role = chunk.role or "dimension"
            
            # 计算融合分数
            confidence = FieldCandidate.compute_final_score(
                exact_match=scores["exact_match"],
                embedding_score=scores["embedding_score"],
                reranker_score=None,
                weights=self.scoring_weights,
            )
            
            # 过滤低分候选
            if confidence < self.config.min_score and not scores["exact_match"]:
                continue
            
            # 生成 candidate_id
            if role == "dimension":
                candidate_id = f"dim_{dim_idx}"
                dim_idx += 1
            else:
                candidate_id = f"meas_{meas_idx}"
                meas_idx += 1
            
            candidate = FieldCandidate(
                candidate_id=candidate_id,
                field_name=field_name,
                field_caption=chunk.field_caption,
                canonical_name=chunk.field_caption or field_name,
                field_type=role,
                confidence=confidence,
                table_name=chunk.table_name,
                sample_values=chunk.sample_values,
                exact_match=scores["exact_match"],
                embedding_score=scores["embedding_score"],
                original_term=result.original_term,
            )
            
            if role == "dimension":
                dimensions.append(candidate)
            else:
                measures.append(candidate)
        
        # 按置信度排序
        dimensions.sort(key=lambda x: x.confidence, reverse=True)
        measures.sort(key=lambda x: x.confidence, reverse=True)
        
        return SchemaCandidates(dimensions=dimensions, measures=measures)


    
    def _build_cache_key(self, question: str, datasource_luid: str) -> str:
        """构建缓存键。"""
        import hashlib
        content = f"{question}|{datasource_luid}"
        return hashlib.md5(content.encode()).hexdigest()


class SchemaLinking:
    """Schema Linking 组件 - 带回退路径。
    
    实现 Schema Linking 的回退机制，确保召回不足时能够自动回退到
    FieldMapper 路径。
    """
    
    def __init__(
        self,
        min_candidates: int = settings.schema_linking_min_candidates,
        min_confidence: float = settings.schema_linking_min_confidence,
        timeout_ms: int = settings.schema_linking_timeout_ms,
        min_term_hit_ratio: float = settings.schema_linking_min_term_hit_ratio,
        min_score_spread: float = settings.schema_linking_min_score_spread,
        min_avg_score: float = settings.schema_linking_min_avg_score,
    ):
        self.config = SchemaLinkingConfig(
            min_candidates=min_candidates,
            min_confidence=min_confidence,
            timeout_ms=timeout_ms,
            min_term_hit_ratio=min_term_hit_ratio,
            min_score_spread=min_score_spread,
            min_avg_score=min_avg_score,
        )
    
    async def link(
        self,
        question: str,
        data_model: Any,
        config: Optional[RunnableConfig] = None,
    ) -> SchemaLinkingResult:
        """执行 Schema Linking - 带回退路径。"""
        import time
        start_time = time.monotonic()
        
        metrics = get_metrics_from_config(config)
        
        try:
            candidates = await asyncio.wait_for(
                self._do_schema_linking(question, data_model, config),
                timeout=self.config.timeout_ms / 1000,
            )
            execution_time_ms = int((time.monotonic() - start_time) * 1000)
            
        except asyncio.TimeoutError:
            execution_time_ms = int((time.monotonic() - start_time) * 1000)
            logger.warning(
                f"Schema linking timeout after {self.config.timeout_ms}ms",
                extra={"question": question[:100], "timeout_ms": self.config.timeout_ms},
            )
            self._record_fallback_metric(metrics, SchemaLinkingFallbackReason.TIMEOUT)
            return SchemaLinkingResult(
                candidates=[],
                fallback_triggered=True,
                fallback_reason=SchemaLinkingFallbackReason.TIMEOUT,
                fallback_details=f"Timeout after {self.config.timeout_ms}ms",
                execution_time_ms=execution_time_ms,
            )
            
        except Exception as e:
            execution_time_ms = int((time.monotonic() - start_time) * 1000)
            logger.error(f"Schema linking failed: {e}", exc_info=True)
            self._record_fallback_metric(metrics, SchemaLinkingFallbackReason.ERROR)
            return SchemaLinkingResult(
                candidates=[],
                fallback_triggered=True,
                fallback_reason=SchemaLinkingFallbackReason.ERROR,
                fallback_details=f"Error: {str(e)[:100]}",
                execution_time_ms=execution_time_ms,
            )
        
        # 检查候选集质量
        fallback_result = self._check_candidates_quality(candidates, question, metrics)
        if fallback_result:
            fallback_result.execution_time_ms = execution_time_ms
            return fallback_result
        
        return SchemaLinkingResult(
            candidates=candidates,
            fallback_triggered=False,
            execution_time_ms=execution_time_ms,
        )
    
    async def _do_schema_linking(
        self,
        question: str,
        data_model: Any,
        config: Optional[RunnableConfig] = None,
    ) -> List[FieldCandidate]:
        """执行实际的 Schema Linking 逻辑。"""
        fields = getattr(data_model, "fields", []) if data_model is not None else []
        if not fields:
            logger.warning("Schema linking skipped: no fields in data_model")
            return []
        
        # 优先使用 data_model 上的 datasource_luid（如有）
        datasource_luid = getattr(data_model, "datasource_luid", None) or "default"
        
        # 构建索引与组件
        field_indexer = FieldIndexer(datasource_luid=datasource_luid)
        term_extractor = TermExtractor()
        component = SchemaLinkingComponent(
            field_indexer=field_indexer,
            term_extractor=term_extractor,
        )
        component.build_index(fields)
        
        # 执行检索
        schema_candidates = await component.execute(
            canonical_question=question,
            data_model=data_model,
            datasource_luid=datasource_luid,
        )
        
        return schema_candidates.get_all_candidates()

    
    def _check_candidates_quality(
        self,
        candidates: List[FieldCandidate],
        question: str,
        metrics: Any,
    ) -> Optional[SchemaLinkingResult]:
        """检查候选集质量，决定是否触发回退。"""
        # 检查 1: 候选集为空
        if len(candidates) < self.config.min_candidates:
            logger.warning(f"Schema linking returned too few candidates: {len(candidates)}")
            self._record_fallback_metric(metrics, SchemaLinkingFallbackReason.EMPTY_CANDIDATES)
            return SchemaLinkingResult(
                candidates=candidates,
                fallback_triggered=True,
                fallback_reason=SchemaLinkingFallbackReason.EMPTY_CANDIDATES,
                fallback_details=f"Only {len(candidates)} candidates",
            )
        
        # 检查 2: 最高置信度过低
        max_confidence = max(c.confidence for c in candidates)
        if max_confidence < self.config.min_confidence:
            logger.warning(f"Schema linking confidence too low: {max_confidence:.2f}")
            self._record_fallback_metric(metrics, SchemaLinkingFallbackReason.LOW_CONFIDENCE)
            return SchemaLinkingResult(
                candidates=candidates,
                fallback_triggered=True,
                fallback_reason=SchemaLinkingFallbackReason.LOW_CONFIDENCE,
                fallback_details=f"Max confidence {max_confidence:.2f}",
            )
        
        # 检查 3: 低覆盖信号
        return self._check_low_coverage_signal(candidates, question, metrics)
    
    def _check_low_coverage_signal(
        self,
        candidates: List[FieldCandidate],
        question: str,
        metrics: Any,
    ) -> Optional[SchemaLinkingResult]:
        """检测低覆盖信号。"""
        if not candidates:
            return None
        
        # 信号 1: top1 与 topk 分数差距过小
        scores = sorted([c.confidence for c in candidates], reverse=True)
        if len(scores) >= 2:
            score_spread = scores[0] - scores[-1]
            if score_spread < self.config.min_score_spread:
                logger.warning(f"Low coverage: score spread {score_spread:.2f}")
                self._record_fallback_metric(metrics, SchemaLinkingFallbackReason.LOW_COVERAGE_SCORE_SPREAD)
                return SchemaLinkingResult(
                    candidates=candidates,
                    fallback_triggered=True,
                    fallback_reason=SchemaLinkingFallbackReason.LOW_COVERAGE_SCORE_SPREAD,
                    fallback_details=f"Score spread {score_spread:.2f}",
                )
        
        # 信号 2: 术语命中率过低
        terms = self._extract_terms(question)
        if terms:
            hit_count = sum(
                1 for t in terms
                if any(t.lower() in c.field_caption.lower() for c in candidates)
            )
            term_hit_ratio = hit_count / len(terms)
            if term_hit_ratio < self.config.min_term_hit_ratio:
                logger.warning(f"Low coverage: term hit ratio {term_hit_ratio:.2f}")
                self._record_fallback_metric(metrics, SchemaLinkingFallbackReason.LOW_COVERAGE_TERM_HIT)
                return SchemaLinkingResult(
                    candidates=candidates,
                    fallback_triggered=True,
                    fallback_reason=SchemaLinkingFallbackReason.LOW_COVERAGE_TERM_HIT,
                    fallback_details=f"Term hit ratio {term_hit_ratio:.2f}",
                )
        
        # 信号 3: 候选分数整体偏低
        avg_score = sum(c.confidence for c in candidates) / len(candidates)
        if avg_score < self.config.min_avg_score:
            logger.warning(f"Low coverage: avg score {avg_score:.2f}")
            self._record_fallback_metric(metrics, SchemaLinkingFallbackReason.LOW_COVERAGE_AVG_SCORE)
            return SchemaLinkingResult(
                candidates=candidates,
                fallback_triggered=True,
                fallback_reason=SchemaLinkingFallbackReason.LOW_COVERAGE_AVG_SCORE,
                fallback_details=f"Avg score {avg_score:.2f}",
            )
        
        return None
    
    def _extract_terms(self, question: str) -> List[str]:
        """从问题中提取候选业务术语。"""
        chinese_pattern = r'[\u4e00-\u9fa5]{2,4}'
        chinese_terms = re.findall(chinese_pattern, question)
        english_pattern = r'[a-zA-Z]{2,}'
        english_terms = re.findall(english_pattern, question)
        all_terms = chinese_terms + english_terms
        return [t for t in all_terms if t.lower() not in STOPWORDS]
    
    def _record_fallback_metric(
        self,
        metrics: Any,
        reason: SchemaLinkingFallbackReason,
    ) -> None:
        """记录回退指标。"""
        if metrics is None:
            return
        try:
            if hasattr(metrics, 'schema_linking_fallback_count'):
                metrics.schema_linking_fallback_count += 1
            if hasattr(metrics, 'schema_linking_fallback_by_reason'):
                metrics.schema_linking_fallback_by_reason[reason.value] = (
                    metrics.schema_linking_fallback_by_reason.get(reason.value, 0) + 1
                )
        except Exception as e:
            logger.debug(f"Failed to record fallback metric: {e}")

