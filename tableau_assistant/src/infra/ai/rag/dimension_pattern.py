"""
维度层级模式索引和检索

提供维度层级推断的 RAG 增强功能：
- 索引历史推断结果
- 检索相似模式
- 提供 few-shot 示例
- 存储新模式

**Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5**
"""
import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

from tableau_assistant.src.infra.ai.rag.embeddings import EmbeddingProvider, EmbeddingProviderFactory
# VectorCache 已删除，使用 StoreManager 替代
# from tableau_assistant.src.infra.ai.rag.cache import VectorCache

logger = logging.getLogger(__name__)


@dataclass
class DimensionPattern:
    """
    维度模式
    
    存储历史推断结果，用于 few-shot 学习。
    
    Attributes:
        pattern_id: 模式 ID
        field_name: 字段名
        field_caption: 字段显示名
        data_type: 数据类型
        sample_values: 样本值列表
        unique_count: 唯一值数量
        category: 推断的维度类别
        category_detail: 详细类别描述
        level: 层级级别 (1-5)
        granularity: 粒度描述
        reasoning: 推理过程
        confidence: 置信度
        datasource_luid: 数据源 LUID
        created_at: 创建时间戳
    """
    pattern_id: str
    field_name: str
    field_caption: str
    data_type: str
    sample_values: List[str]
    unique_count: int
    category: str
    category_detail: str
    level: int
    granularity: str
    reasoning: str
    confidence: float
    datasource_luid: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "pattern_id": self.pattern_id,
            "field_name": self.field_name,
            "field_caption": self.field_caption,
            "data_type": self.data_type,
            "sample_values": self.sample_values,
            "unique_count": self.unique_count,
            "category": self.category,
            "category_detail": self.category_detail,
            "level": self.level,
            "granularity": self.granularity,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "datasource_luid": self.datasource_luid,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DimensionPattern":
        """从字典创建"""
        return cls(
            pattern_id=data["pattern_id"],
            field_name=data["field_name"],
            field_caption=data["field_caption"],
            data_type=data["data_type"],
            sample_values=data.get("sample_values", []),
            unique_count=data.get("unique_count", 0),
            category=data["category"],
            category_detail=data.get("category_detail", ""),
            level=data["level"],
            granularity=data.get("granularity", ""),
            reasoning=data.get("reasoning", ""),
            confidence=data.get("confidence", 0.0),
            datasource_luid=data.get("datasource_luid"),
            created_at=data.get("created_at", time.time()),
        )
    
    def build_index_text(self) -> str:
        """
        构建索引文本
        
        包含 field name, data type, sample values, unique count, category/level
        
        **Validates: Requirements 9.4**
        """
        parts = [
            f"字段名: {self.field_caption}",
            f"数据类型: {self.data_type}",
            f"唯一值数量: {self.unique_count}",
        ]
        
        if self.sample_values:
            samples = self.sample_values[:5]
            parts.append(f"样本值: {', '.join(str(s) for s in samples)}")
        
        parts.append(f"类别: {self.category}")
        parts.append(f"层级: {self.level}")
        parts.append(f"粒度: {self.granularity}")
        
        return " | ".join(parts)
    
    def to_few_shot_example(self) -> str:
        """
        转换为 few-shot 示例格式
        
        **Validates: Requirements 9.2**
        """
        return f"""字段: {self.field_caption}
数据类型: {self.data_type}
样本值: {', '.join(self.sample_values[:5])}
唯一值数量: {self.unique_count}

推断结果:
- 类别: {self.category} ({self.category_detail})
- 层级: {self.level} ({self.granularity})
- 推理: {self.reasoning}"""


@dataclass
class PatternSearchResult:
    """
    模式搜索结果
    
    Attributes:
        pattern: 维度模式
        similarity: 相似度分数
        rank: 排名
    """
    pattern: DimensionPattern
    similarity: float
    rank: int


class DimensionPatternStore:
    """
    维度模式存储
    
    使用 SQLite 存储维度模式，支持向量检索。
    
    **Validates: Requirements 9.1, 9.3, 9.4**
    """
    
    SIMILARITY_THRESHOLD = 0.8  # 相似度阈值
    
    def __init__(
        self,
        db_path: Optional[str] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
        use_cache: bool = True
    ):
        """
        初始化模式存储
        
        Args:
            db_path: SQLite 数据库路径
            embedding_provider: Embedding 提供者
            use_cache: 是否使用向量缓存
        """
        if db_path is None:
            db_path = "data/dimension_patterns.db"
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化 Embedding 提供者
        self._embedding_provider = embedding_provider or EmbeddingProviderFactory.create("mock")
        
        # 向量缓存（VectorCache 已删除，暂时禁用缓存）
        # TODO: 使用 StoreManager 替代
        self._vector_cache = None
        
        # 内存中的向量索引
        self._patterns: Dict[str, DimensionPattern] = {}
        self._vectors: Dict[str, List[float]] = {}
        self._pattern_ids: List[str] = []
        
        # 初始化数据库
        self._init_db()
        
        # 加载现有模式
        self._load_patterns()
    
    def _init_db(self) -> None:
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dimension_patterns (
                    pattern_id TEXT PRIMARY KEY,
                    field_name TEXT NOT NULL,
                    field_caption TEXT NOT NULL,
                    data_type TEXT NOT NULL,
                    sample_values TEXT,
                    unique_count INTEGER,
                    category TEXT NOT NULL,
                    category_detail TEXT,
                    level INTEGER NOT NULL,
                    granularity TEXT,
                    reasoning TEXT,
                    confidence REAL,
                    datasource_luid TEXT,
                    index_text TEXT,
                    vector TEXT,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_patterns_category 
                ON dimension_patterns(category)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_patterns_datasource 
                ON dimension_patterns(datasource_luid)
            """)
            conn.commit()
    
    def _load_patterns(self) -> None:
        """从数据库加载模式"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT pattern_id, field_name, field_caption, data_type,
                           sample_values, unique_count, category, category_detail,
                           level, granularity, reasoning, confidence,
                           datasource_luid, vector, created_at
                    FROM dimension_patterns
                """)
                
                for row in cursor:
                    pattern = DimensionPattern(
                        pattern_id=row[0],
                        field_name=row[1],
                        field_caption=row[2],
                        data_type=row[3],
                        sample_values=json.loads(row[4]) if row[4] else [],
                        unique_count=row[5] or 0,
                        category=row[6],
                        category_detail=row[7] or "",
                        level=row[8],
                        granularity=row[9] or "",
                        reasoning=row[10] or "",
                        confidence=row[11] or 0.0,
                        datasource_luid=row[12],
                        created_at=row[14] or time.time(),
                    )
                    
                    self._patterns[pattern.pattern_id] = pattern
                    self._pattern_ids.append(pattern.pattern_id)
                    
                    # 加载向量
                    if row[13]:
                        self._vectors[pattern.pattern_id] = json.loads(row[13])
                
                logger.info(f"已加载 {len(self._patterns)} 个维度模式")
                
        except Exception as e:
            logger.error(f"加载维度模式失败: {e}")
    
    @staticmethod
    def _generate_pattern_id(field_name: str, datasource_luid: Optional[str] = None) -> str:
        """生成模式 ID"""
        key = f"{field_name}|{datasource_luid or 'global'}"
        return hashlib.md5(key.encode()).hexdigest()[:16]
    
    def store_pattern(
        self,
        field_name: str,
        field_caption: str,
        data_type: str,
        sample_values: List[str],
        unique_count: int,
        category: str,
        category_detail: str,
        level: int,
        granularity: str,
        reasoning: str,
        confidence: float,
        datasource_luid: Optional[str] = None
    ) -> DimensionPattern:
        """
        存储新的维度模式
        
        成功推断后存储新模式供未来检索。
        
        **Validates: Requirements 9.3**
        
        Args:
            field_name: 字段名
            field_caption: 字段显示名
            data_type: 数据类型
            sample_values: 样本值列表
            unique_count: 唯一值数量
            category: 维度类别
            category_detail: 详细类别描述
            level: 层级级别
            granularity: 粒度描述
            reasoning: 推理过程
            confidence: 置信度
            datasource_luid: 数据源 LUID
        
        Returns:
            存储的维度模式
        """
        pattern_id = self._generate_pattern_id(field_name, datasource_luid)
        
        pattern = DimensionPattern(
            pattern_id=pattern_id,
            field_name=field_name,
            field_caption=field_caption,
            data_type=data_type,
            sample_values=sample_values[:10],  # 最多保存 10 个样本值
            unique_count=unique_count,
            category=category,
            category_detail=category_detail,
            level=level,
            granularity=granularity,
            reasoning=reasoning,
            confidence=confidence,
            datasource_luid=datasource_luid,
            created_at=time.time(),
        )
        
        # 构建索引文本并向量化
        index_text = pattern.build_index_text()
        vector = self._embedding_provider.embed_query(index_text)
        
        # 保存到数据库
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO dimension_patterns
                    (pattern_id, field_name, field_caption, data_type,
                     sample_values, unique_count, category, category_detail,
                     level, granularity, reasoning, confidence,
                     datasource_luid, index_text, vector, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    pattern.pattern_id,
                    pattern.field_name,
                    pattern.field_caption,
                    pattern.data_type,
                    json.dumps(pattern.sample_values),
                    pattern.unique_count,
                    pattern.category,
                    pattern.category_detail,
                    pattern.level,
                    pattern.granularity,
                    pattern.reasoning,
                    pattern.confidence,
                    pattern.datasource_luid,
                    index_text,
                    json.dumps(vector),
                    pattern.created_at,
                ))
                conn.commit()
            
            # 更新内存索引
            self._patterns[pattern_id] = pattern
            self._vectors[pattern_id] = vector
            if pattern_id not in self._pattern_ids:
                self._pattern_ids.append(pattern_id)
            
            logger.info(f"已存储维度模式: {field_caption} -> {category}/{level}")
            return pattern
            
        except Exception as e:
            logger.error(f"存储维度模式失败: {e}")
            raise

    
    def search_similar_patterns(
        self,
        field_caption: str,
        data_type: str,
        sample_values: List[str],
        unique_count: int,
        top_k: int = 3,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
        category_filter: Optional[str] = None,
        weight_by_confidence: bool = True
    ) -> List[PatternSearchResult]:
        """
        检索相似的维度模式
        
        检索相似度 > threshold 的历史模式，支持按 confidence 加权排序。
        
        **Validates: Requirements 9.1**
        
        Args:
            field_caption: 字段显示名
            data_type: 数据类型
            sample_values: 样本值列表
            unique_count: 唯一值数量
            top_k: 返回结果数量
            similarity_threshold: 相似度阈值（默认 0.8）
            category_filter: 类别过滤
            weight_by_confidence: 是否按 confidence 加权排序（默认 True）
        
        Returns:
            相似模式列表
        """
        if not self._patterns:
            return []
        
        # 构建查询文本
        query_parts = [
            f"字段名: {field_caption}",
            f"数据类型: {data_type}",
            f"唯一值数量: {unique_count}",
        ]
        if sample_values:
            query_parts.append(f"样本值: {', '.join(str(s) for s in sample_values[:5])}")
        
        query_text = " | ".join(query_parts)
        
        # 向量化查询
        query_vector = self._embedding_provider.embed_query(query_text)
        
        # 计算相似度
        results = []
        for pattern_id, pattern in self._patterns.items():
            # 应用类别过滤
            if category_filter and pattern.category != category_filter:
                continue
            
            # 获取模式向量
            pattern_vector = self._vectors.get(pattern_id)
            if not pattern_vector:
                continue
            
            # 计算余弦相似度
            similarity = self._cosine_similarity(query_vector, pattern_vector)
            
            if similarity >= similarity_threshold:
                # 计算加权分数：similarity * confidence_weight
                # confidence_weight = 0.5 + 0.5 * confidence (范围 0.5-1.0)
                if weight_by_confidence:
                    confidence_weight = 0.5 + 0.5 * pattern.confidence
                    weighted_score = similarity * confidence_weight
                else:
                    weighted_score = similarity
                
                results.append((pattern, similarity, weighted_score))
        
        # 按加权分数排序
        results.sort(key=lambda x: x[2], reverse=True)
        
        # 返回 top-k
        search_results = []
        for rank, (pattern, similarity, _) in enumerate(results[:top_k], 1):
            search_results.append(PatternSearchResult(
                pattern=pattern,
                similarity=similarity,
                rank=rank
            ))
        
        logger.debug(f"检索到 {len(search_results)} 个相似维度模式 (阈值={similarity_threshold}, 加权={weight_by_confidence})")
        return search_results
    
    def get_few_shot_examples(
        self,
        field_caption: str,
        data_type: str,
        sample_values: List[str],
        unique_count: int,
        top_k: int = 3
    ) -> List[str]:
        """
        获取 few-shot 示例
        
        提供 top-k 模式作为 LLM 示例。
        
        **Validates: Requirements 9.2**
        
        Args:
            field_caption: 字段显示名
            data_type: 数据类型
            sample_values: 样本值列表
            unique_count: 唯一值数量
            top_k: 返回示例数量
        
        Returns:
            few-shot 示例列表
        """
        results = self.search_similar_patterns(
            field_caption=field_caption,
            data_type=data_type,
            sample_values=sample_values,
            unique_count=unique_count,
            top_k=top_k
        )
        
        examples = []
        for result in results:
            examples.append(result.pattern.to_few_shot_example())
        
        return examples
    
    def has_similar_patterns(
        self,
        field_caption: str,
        data_type: str,
        sample_values: List[str],
        unique_count: int,
        similarity_threshold: float = SIMILARITY_THRESHOLD
    ) -> bool:
        """
        检查是否存在相似模式
        
        **Validates: Requirements 9.5**
        
        Args:
            field_caption: 字段显示名
            data_type: 数据类型
            sample_values: 样本值列表
            unique_count: 唯一值数量
            similarity_threshold: 相似度阈值
        
        Returns:
            是否存在相似模式
        """
        results = self.search_similar_patterns(
            field_caption=field_caption,
            data_type=data_type,
            sample_values=sample_values,
            unique_count=unique_count,
            top_k=1,
            similarity_threshold=similarity_threshold
        )
        return len(results) > 0
    
    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        if len(vec1) != len(vec2):
            return 0.0
        
        if NUMPY_AVAILABLE:
            v1 = np.array(vec1)
            v2 = np.array(vec2)
            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return float(np.dot(v1, v2) / (norm1 * norm2))
        else:
            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            norm1 = sum(a * a for a in vec1) ** 0.5
            norm2 = sum(b * b for b in vec2) ** 0.5
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return dot_product / (norm1 * norm2)
    
    def get_pattern(self, pattern_id: str) -> Optional[DimensionPattern]:
        """获取指定模式"""
        return self._patterns.get(pattern_id)
    
    def get_all_patterns(self) -> List[DimensionPattern]:
        """获取所有模式"""
        return list(self._patterns.values())
    
    def delete_pattern(self, pattern_id: str) -> bool:
        """删除模式"""
        if pattern_id not in self._patterns:
            return False
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "DELETE FROM dimension_patterns WHERE pattern_id = ?",
                    (pattern_id,)
                )
                conn.commit()
            
            del self._patterns[pattern_id]
            if pattern_id in self._vectors:
                del self._vectors[pattern_id]
            if pattern_id in self._pattern_ids:
                self._pattern_ids.remove(pattern_id)
            
            return True
            
        except Exception as e:
            logger.error(f"删除维度模式失败: {e}")
            return False
    
    def clear(self, datasource_luid: Optional[str] = None) -> int:
        """
        清除模式
        
        Args:
            datasource_luid: 数据源 LUID（可选，不指定则清除所有）
        
        Returns:
            清除的记录数
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                if datasource_luid:
                    cursor = conn.execute(
                        "DELETE FROM dimension_patterns WHERE datasource_luid = ?",
                        (datasource_luid,)
                    )
                    # 更新内存索引
                    to_delete = [
                        pid for pid, p in self._patterns.items()
                        if p.datasource_luid == datasource_luid
                    ]
                else:
                    cursor = conn.execute("DELETE FROM dimension_patterns")
                    to_delete = list(self._patterns.keys())
                
                conn.commit()
                count = cursor.rowcount
                
                # 清理内存索引
                for pid in to_delete:
                    del self._patterns[pid]
                    if pid in self._vectors:
                        del self._vectors[pid]
                    if pid in self._pattern_ids:
                        self._pattern_ids.remove(pid)
                
                return count
                
        except Exception as e:
            logger.error(f"清除维度模式失败: {e}")
            return 0
    
    def stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        by_category = {}
        for pattern in self._patterns.values():
            by_category[pattern.category] = by_category.get(pattern.category, 0) + 1
        
        return {
            "total": len(self._patterns),
            "by_category": by_category,
            "has_vectors": len(self._vectors),
        }
    
    @property
    def pattern_count(self) -> int:
        """模式数量"""
        return len(self._patterns)


class DimensionHierarchyRAG:
    """
    维度层级推断 RAG 增强
    
    整合模式存储和检索，提供完整的 RAG 增强功能。
    
    **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5**
    """
    
    def __init__(
        self,
        pattern_store: Optional[DimensionPatternStore] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
        similarity_threshold: float = 0.8
    ):
        """
        初始化维度层级 RAG
        
        Args:
            pattern_store: 模式存储（可选，默认创建新的）
            embedding_provider: Embedding 提供者（可选，传递给 DimensionPatternStore）
            similarity_threshold: 相似度阈值
        """
        if pattern_store is not None:
            self.pattern_store = pattern_store
        elif embedding_provider is not None:
            self.pattern_store = DimensionPatternStore(embedding_provider=embedding_provider)
        else:
            self.pattern_store = DimensionPatternStore()
        self.similarity_threshold = similarity_threshold
        
        # 统计信息
        self._total_inferences = 0
        self._rag_assisted = 0
        self._fallback_count = 0
    
    def get_inference_context(
        self,
        field_caption: str,
        data_type: str,
        sample_values: List[str],
        unique_count: int
    ) -> Dict[str, Any]:
        """
        获取推断上下文
        
        检索相似模式并构建 LLM 上下文。当无相似模式时，返回降级标志，
        调用方应使用纯 LLM 推断。
        
        **Validates: Requirements 9.1, 9.2, 9.5**
        
        Args:
            field_caption: 字段显示名
            data_type: 数据类型
            sample_values: 样本值列表
            unique_count: 唯一值数量
        
        Returns:
            推断上下文，包含：
            - has_similar_patterns: 是否有相似模式
            - few_shot_examples: few-shot 示例列表
            - similar_patterns: 相似模式详情
            - fallback_to_llm: 是否降级到纯 LLM 推断
            - fallback_reason: 降级原因（如果降级）
        """
        self._total_inferences += 1
        
        # 检索相似模式（按 confidence 加权）
        results = self.pattern_store.search_similar_patterns(
            field_caption=field_caption,
            data_type=data_type,
            sample_values=sample_values,
            unique_count=unique_count,
            top_k=3,
            similarity_threshold=self.similarity_threshold,
            weight_by_confidence=True
        )
        
        if results:
            self._rag_assisted += 1
            
            # 构建 few-shot 示例
            examples = [r.pattern.to_few_shot_example() for r in results]
            
            # 构建相似模式详情（包含 confidence 信息）
            similar_patterns = [
                {
                    "pattern_id": r.pattern.pattern_id,
                    "field_caption": r.pattern.field_caption,
                    "category": r.pattern.category,
                    "level": r.pattern.level,
                    "similarity": r.similarity,
                    "confidence": r.pattern.confidence,
                }
                for r in results
            ]
            
            return {
                "has_similar_patterns": True,
                "few_shot_examples": examples,
                "similar_patterns": similar_patterns,
                "fallback_to_llm": False,
                "fallback_reason": None,
            }
        else:
            self._fallback_count += 1
            
            # 降级到纯 LLM 推断
            # **Validates: Requirements 9.5**
            fallback_reason = (
                f"无相似模式 (阈值={self.similarity_threshold}, "
                f"索引模式数={self.pattern_store.pattern_count})"
            )
            
            logger.debug(f"RAG 降级: {fallback_reason}")
            
            return {
                "has_similar_patterns": False,
                "few_shot_examples": [],
                "similar_patterns": [],
                "fallback_to_llm": True,
                "fallback_reason": fallback_reason,
            }
    
    def store_inference_result(
        self,
        field_name: str,
        field_caption: str,
        data_type: str,
        sample_values: List[str],
        unique_count: int,
        category: str,
        category_detail: str,
        level: int,
        granularity: str,
        reasoning: str,
        confidence: float,
        datasource_luid: Optional[str] = None
    ) -> DimensionPattern:
        """
        存储推断结果
        
        成功推断后存储新模式供未来检索。
        
        **Validates: Requirements 9.3**
        """
        return self.pattern_store.store_pattern(
            field_name=field_name,
            field_caption=field_caption,
            data_type=data_type,
            sample_values=sample_values,
            unique_count=unique_count,
            category=category,
            category_detail=category_detail,
            level=level,
            granularity=granularity,
            reasoning=reasoning,
            confidence=confidence,
            datasource_luid=datasource_luid,
        )
    
    def should_use_rag(
        self,
        field_caption: str,
        data_type: str,
        sample_values: List[str],
        unique_count: int
    ) -> bool:
        """
        判断是否应该使用 RAG
        
        **Validates: Requirements 9.5**
        
        Returns:
            True 如果有相似模式可用，False 则降级到纯 LLM 推断
        """
        return self.pattern_store.has_similar_patterns(
            field_caption=field_caption,
            data_type=data_type,
            sample_values=sample_values,
            unique_count=unique_count,
            similarity_threshold=self.similarity_threshold
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_inferences": self._total_inferences,
            "rag_assisted": self._rag_assisted,
            "rag_rate": self._rag_assisted / max(1, self._total_inferences),
            "fallback_count": self._fallback_count,
            "fallback_rate": self._fallback_count / max(1, self._total_inferences),
            "pattern_store": self.pattern_store.stats(),
        }
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        self._total_inferences = 0
        self._rag_assisted = 0
        self._fallback_count = 0


__all__ = [
    "DimensionPattern",
    "PatternSearchResult",
    "DimensionPatternStore",
    "DimensionHierarchyRAG",
]
