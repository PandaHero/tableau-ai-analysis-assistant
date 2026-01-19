"""
字段值索引器

管理字段唯一值的向量索引，支持持久化缓存。
用于 SetFilter 值的语义匹配。

主要功能：
- 从 DataModel 的 sample_values 获取字段值（不查询 VizQL API）
- 为字段值建立向量索引（复用 Embedding 架构）
- 持久化缓存（LangGraph SqliteStore）
- RAG 语义匹配

重要：字段值来源于 DataModel.fields[].sample_values，不需要额外查询 VizQL API。
"""
import logging
import math
import time
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple

from langgraph.types import RunnableConfig

logger = logging.getLogger(__name__)

# 缓存 TTL（7 天）
FIELD_VALUE_CACHE_TTL = 7 * 24 * 60 * 60

# 唯一值数量上限
MAX_DISTINCT_VALUES = 10000


@dataclass
class ValueMatchResult:
    """值匹配结果"""
    matched_value: Optional[str]  # 匹配到的真实值
    match_type: str  # exact, rag, none
    confidence: float  # 匹配置信度
    suggestions: List[Tuple[str, float]] = None  # [(value, confidence), ...]
    
    def __post_init__(self):
        if self.suggestions is None:
            self.suggestions = []


@dataclass
class DistinctValuesResult:
    """唯一值查询结果"""
    values: List[str]  # 唯一值列表
    unique_count: int  # 唯一值总数
    is_truncated: bool  # 是否被截断
    from_cache: bool  # 是否来自缓存


class FieldValueIndexer:
    """
    字段值索引器
    
    管理字段唯一值的向量索引，支持持久化缓存。
    与 DataModel 一样使用 LangGraph SqliteStore 持久化。
    
    重要：字段值来源于 DataModel.fields[].sample_values，
    不需要额外查询 VizQL API。
    
    缓存结构：
    - namespace: ("field_values", datasource_luid)
    - key: field_name
    - value: {
        "distinct_values": [...],
        "unique_count": int,
        "updated_at": timestamp
      }
    
    向量索引缓存：
    - namespace: ("field_value_vectors", datasource_luid, field_name)
    - key: value_hash
    - value: {"vector": [...], "value": "..."}
    """
    
    def __init__(
        self,
        datasource_luid: str,
        store_manager: Optional[Any] = None,
        embedding_provider: Optional[Any] = None,
    ):
        """
        初始化字段值索引器
        
        Args:
            datasource_luid: 数据源 LUID
            store_manager: LangGraph SqliteStore 实例
            embedding_provider: Embedding 提供者
        """
        self.datasource_luid = datasource_luid
        
        # 获取 LangGraph SqliteStore
        if store_manager is not None:
            self._store_manager = store_manager
        else:
            try:
                from tableau_assistant.src.infra.storage import get_langgraph_store
                self._store_manager = get_langgraph_store()
            except Exception as e:
                logger.warning(f"无法获取 LangGraph Store，缓存将不可用: {e}")
                self._store_manager = None
        
        # 初始化 Embedding 提供者
        if embedding_provider is not None:
            self._embedding_provider = embedding_provider
        else:
            self._embedding_provider = self._create_embedding_provider()
        
        # 内存缓存（避免重复查询）
        self._value_cache: Dict[str, List[str]] = {}
        self._vector_cache: Dict[str, Dict[str, List[float]]] = {}
    
    def _create_embedding_provider(self) -> Optional[Any]:
        """创建 Embedding 提供者"""
        try:
            from tableau_assistant.src.infra.rag import EmbeddingProviderFactory
            from tableau_assistant.src.infra.rag.cache import CachedEmbeddingProvider
            
            base_provider = EmbeddingProviderFactory.get_default()

            if base_provider:
                return CachedEmbeddingProvider(base_provider)
            return None
        except Exception as e:
            logger.warning(f"创建 Embedding 提供者失败: {e}")
            return None
    
    def _get_values_namespace(self) -> Tuple[str, ...]:
        """获取唯一值缓存命名空间"""
        return ("field_values", self.datasource_luid)
    
    def _get_vectors_namespace(self, field_name: str) -> Tuple[str, ...]:
        """获取向量缓存命名空间"""
        return ("field_value_vectors", self.datasource_luid, field_name)
    
    def load_values_from_data_model(
        self,
        field_name: str,
        data_model: Any,
    ) -> DistinctValuesResult:
        """
        从 DataModel 加载字段的 sample_values
        
        DataModel.fields 是字段列表，每个字段有 sample_values 属性。
        
        Args:
            field_name: 字段名
            data_model: DataModel 实例
        
        Returns:
            DistinctValuesResult
        """
        # 检查内存缓存
        if field_name in self._value_cache:
            values = self._value_cache[field_name]
            return DistinctValuesResult(
                values=values,
                unique_count=len(values),
                is_truncated=False,
                from_cache=True,
            )
        
        # 从DataModel 获取 sample_values
        values = []
        
        if data_model and hasattr(data_model, 'fields'):
            fields = data_model.fields or []
            for field in fields:
                # 支持 dict和object 两种格式
                if isinstance(field, dict):
                    fname = field.get('name') or field.get('field_name') or field.get('fieldCaption')
                    sample_values = field.get('sample_values') or field.get('sampleValues') or []
                else:
                    fname = getattr(field, 'name', None) or getattr(field, 'field_name', None) or getattr(field, 'fieldCaption', None)
                    sample_values = getattr(field, 'sample_values', None) or getattr(field, 'sampleValues', None) or []
                
                if fname == field_name:
                    # 转换为字符串列表
                    values = [str(v).strip() for v in sample_values if v is not None]
                    # 去重
                    values = list(dict.fromkeys(values))
                    break
        
        # 保存到内存缓存
        self._value_cache[field_name] = values
        
        # 保存到持久化缓存
        self._save_to_store(field_name, values, len(values))
        
        logger.info(f"从 DataModel 加载字段 '{field_name}' 的 sample_values: {len(values)} 个值")
        
        return DistinctValuesResult(
            values=values,
            unique_count=len(values),
            is_truncated=False,
            from_cache=False,
        )
    
    def get_cached_values(
        self,
        field_name: str,
    ) -> Optional[List[str]]:
        """
        获取缓存的字段值（内存或持久化）
        
        Args:
            field_name: 字段名
        
        Returns:
            值列表，如果没有缓存返回 None
        """
        # 检查内存缓存
        if field_name in self._value_cache:
            return self._value_cache[field_name]
        
        # 检查持久化缓存
        cached = self._get_from_store(field_name)
        if cached:
            values = cached.get("distinct_values", [])
            self._value_cache[field_name] = values
            return values
        
        return None
    
    def _get_from_store(self, field_name: str) -> Optional[Dict[str, Any]]:
        """从持久化存储获取"""
        if not self._store_manager:
            return None
        
        try:
            item = self._store_manager.get(
                namespace=self._get_values_namespace(),
                key=field_name,
            )
            if item:
                return item.value
            return None
        except Exception as e:
            logger.warning(f"从缓存获取字段值失败: {e}")
            return None
    
    def _save_to_store(
        self,
        field_name: str,
        values: List[str],
        unique_count: int,
    ) -> bool:
        """保存到持久化存储"""
        if not self._store_manager:
            return False
        
        try:
            self._store_manager.put(
                namespace=self._get_values_namespace(),
                key=field_name,
                value={
                    "distinct_values": values,
                    "unique_count": unique_count,
                    "updated_at": time.time(),
                },
                ttl=FIELD_VALUE_CACHE_TTL,
            )
            return True
        except Exception as e:
            logger.warning(f"保存字段值到缓存失败: {e}")
            return False
    
    async def build_value_index(
        self,
        field_name: str,
        values: List[str],
    ) -> bool:
        """
        为字段值建立向量索引
        
        Args:
            field_name: 字段名
            values: 唯一值列表
        
        Returns:
            是否成功
        """
        if not self._embedding_provider:
            logger.warning("Embedding 提供者不可用，无法建立向量索引")
            return False
        
        if not values:
            return True
        
        try:
            # 向量化所有值
            vectors = self._embedding_provider.embed_documents(values)
            
            # 保存到内存缓存
            self._vector_cache[field_name] = {
                value: vector
                for value, vector in zip(values, vectors)
            }
            
            logger.info(f"为字段 '{field_name}' 建立向量索引: {len(values)} 个值")
            return True
            
        except Exception as e:
            logger.error(f"建立向量索引失败: {e}", exc_info=True)
            return False
    
    async def search_value(
        self,
        user_value: str,
        field_name: str,
        top_k: int = 5,
    ) -> List[Tuple[str, float]]:
        """
        在字段值索引中搜索匹配
        
        Args:
            user_value: 用户输入的值
            field_name: 字段名
            top_k: 返回结果数量
        
        Returns:
            [(value, confidence), ...] 按置信度降序排列
        """
        if not self._embedding_provider:
            return []
        
        # 检查是否有向量索引
        if field_name not in self._vector_cache:
            # 尝试从缓存加载值并建立索引
            if field_name in self._value_cache:
                await self.build_value_index(field_name, self._value_cache[field_name])
            else:
                return []
        
        value_vectors = self._vector_cache.get(field_name, {})
        if not value_vectors:
            return []
        
        try:
            # 向量化用户输入
            query_vector = self._embedding_provider.embed_query(user_value)
            
            # 计算相似度
            scores = []
            for value, vector in value_vectors.items():
                similarity = self._cosine_similarity(query_vector, vector)
                scores.append((value, similarity))
            
            # 按相似度排序
            scores.sort(key=lambda x: x[1], reverse=True)
            
            return scores[:top_k]
            
        except Exception as e:
            logger.error(f"搜索值失败: {e}", exc_info=True)
            return []
    
    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    async def match_value(
        self,
        user_value: str,
        field_name: str,
        data_model: Optional[Any] = None,
    ) -> ValueMatchResult:
        """
        匹配单个筛选值
        
        匹配策略：
        1. 精确匹配（大小写不敏感）→ confidence = 1.0
        2. RAG 语义匹配 → confidence = RAG 返回的分数
        
        Args:
            user_value: 用户输入的值
            field_name: 字段名
            data_model: DataModel 实例（用于获取 sample_values）
        
        Returns:
            ValueMatchResult
        """
        # 获取唯一值（优先从缓存，否则从 DataModel）
        distinct_values = self.get_cached_values(field_name)
        
        if distinct_values is None and data_model:
            result = self.load_values_from_data_model(field_name, data_model)
            distinct_values = result.values
        
        if not distinct_values:
            return ValueMatchResult(
                matched_value=None,
                match_type="none",
                confidence=0.0,
            )
        
        # 1. 精确匹配（大小写不敏感）
        user_lower = user_value.lower().strip()
        for dv in distinct_values:
            if dv.lower().strip() == user_lower:
                return ValueMatchResult(
                    matched_value=dv,
                    match_type="exact",
                    confidence=1.0,
                )
        
        # 2. 建立向量索引（如果还没有）
        if field_name not in self._vector_cache:
            await self.build_value_index(field_name, distinct_values)
        
        # 3. RAG 语义匹配
        rag_results = await self.search_value(
            user_value=user_value,
            field_name=field_name,
            top_k=5,
        )
        
        if rag_results:
            best_match, best_confidence = rag_results[0]
            
            if best_confidence >= 0.9:
                return ValueMatchResult(
                    matched_value=best_match,
                    match_type="rag",
                    confidence=best_confidence,
                    suggestions=rag_results[1:],
                )
            else:
                # 置信度不够，返回建议
                return ValueMatchResult(
                    matched_value=None,
                    match_type="none",
                    confidence=best_confidence,
                    suggestions=rag_results,
                )
        
        # 4. 无匹配
        return ValueMatchResult(
            matched_value=None,
            match_type="none",
            confidence=0.0,
        )


__all__ = [
    "FieldValueIndexer",
    "ValueMatchResult",
    "DistinctValuesResult",
    "MAX_DISTINCT_VALUES",
    "FIELD_VALUE_CACHE_TTL",
]
