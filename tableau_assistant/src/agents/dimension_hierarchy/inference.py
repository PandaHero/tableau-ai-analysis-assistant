# -*- coding: utf-8 -*-
"""
维度层级主推断流程

实现 RAG 优先 + LLM 兜底 + 延迟加载样例数据的推断策略。

核心流程：
1. 检查缓存（完全命中直接返回）
2. 计算增量字段（new/changed/deleted/unchanged）
3. RAG 检索（命中直接复用）
4. LLM 推断（RAG 未命中时兜底）
5. 存入 RAG（高置信度结果）
6. 更新缓存

特性：
- 增量推断：只对新增/变更字段进行推断
- 阈值分层：seed/verified=0.92, llm/unverified=0.95
- 并发控制：按 cache_key 粒度加锁
- 自学习：高置信度结果存入 RAG

Requirements: 1.1, 1.2, 1.3, 1.4
"""
from typing import List, Dict, Any, Optional, Tuple, Set, Callable, Awaitable
from dataclasses import dataclass, field
import asyncio
import hashlib
import logging
import time

from .cache_storage import (
    DimensionHierarchyCacheStorage,
    compute_field_hash_metadata_only,
    compute_single_field_hash,
    RAG_STORE_CONFIDENCE_THRESHOLD,
    MAX_LOCKS,
    LOCK_EXPIRE_SECONDS,
)
from .faiss_store import DimensionPatternFAISS
from .rag_retriever import DimensionRAGRetriever
from .seed_data import initialize_seed_patterns, SEED_PATTERNS
from .llm_inference import infer_dimensions_once, MAX_FIELDS_PER_INFERENCE
from .models import DimensionHierarchyResult, DimensionAttributes

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════

def build_cache_key(
    datasource_luid: str,
    logical_table_id: Optional[str] = None,
) -> str:
    """
    构建缓存 key
    
    格式：datasource_luid 或 datasource_luid:logical_table_id
    
    Args:
        datasource_luid: 数据源 LUID
        logical_table_id: 逻辑表 ID（可选，多表数据源时使用）
    
    Returns:
        缓存 key
    """
    if logical_table_id:
        return f"{datasource_luid}:{logical_table_id}"
    return datasource_luid


@dataclass
class IncrementalFieldsResult:
    """
    增量字段计算结果
    
    Attributes:
        new_fields: 新增字段名集合
        changed_fields: 变更字段名集合（caption/dataType 变化）
        deleted_fields: 删除字段名集合
        unchanged_fields: 未变化字段名集合
    """
    new_fields: Set[str]
    changed_fields: Set[str]
    deleted_fields: Set[str]
    unchanged_fields: Set[str]
    
    @property
    def needs_inference(self) -> bool:
        """是否需要推断（有新增或变更字段）"""
        return len(self.new_fields) > 0 or len(self.changed_fields) > 0
    
    @property
    def fields_to_infer(self) -> Set[str]:
        """需要推断的字段（新增 + 变更）"""
        return self.new_fields | self.changed_fields


def compute_incremental_fields(
    current_fields: List[Dict[str, Any]],
    cached_field_hashes: Optional[Dict[str, str]],
    cached_field_names: Optional[Set[str]],
) -> IncrementalFieldsResult:
    """
    计算增量字段（返回 new/changed/deleted/unchanged 四类）
    
    通过比较单字段 hash 检测字段变更（caption/dataType 变化）。
    
    Args:
        current_fields: 当前字段列表，每个字段包含 field_name, field_caption, data_type
        cached_field_hashes: 缓存的字段 hash 字典 {field_name: hash}
        cached_field_names: 缓存的字段名集合
    
    Returns:
        IncrementalFieldsResult 对象
    """
    current_field_names = {f["field_name"] for f in current_fields}
    
    if cached_field_hashes is None or cached_field_names is None:
        # 无缓存，所有字段都是新增
        return IncrementalFieldsResult(
            new_fields=current_field_names,
            changed_fields=set(),
            deleted_fields=set(),
            unchanged_fields=set(),
        )
    
    # 计算当前字段的 hash
    current_field_hashes = {}
    for f in current_fields:
        field_hash = compute_single_field_hash(
            f["field_name"],
            f["field_caption"],
            f["data_type"],
        )
        current_field_hashes[f["field_name"]] = field_hash
    
    # 计算差集
    new_fields = current_field_names - cached_field_names
    deleted_fields = cached_field_names - current_field_names
    
    # 检测变更字段（hash 不同）
    changed_fields = set()
    unchanged_fields = set()
    
    for field_name in current_field_names & cached_field_names:
        current_hash = current_field_hashes.get(field_name)
        cached_hash = cached_field_hashes.get(field_name)
        
        if current_hash != cached_hash:
            changed_fields.add(field_name)
        else:
            unchanged_fields.add(field_name)
    
    logger.debug(
        f"增量计算: 新增={len(new_fields)}, 变更={len(changed_fields)}, "
        f"删除={len(deleted_fields)}, 未变化={len(unchanged_fields)}"
    )
    
    return IncrementalFieldsResult(
        new_fields=new_fields,
        changed_fields=changed_fields,
        deleted_fields=deleted_fields,
        unchanged_fields=unchanged_fields,
    )


# ═══════════════════════════════════════════════════════════
# 统计数据
# ═══════════════════════════════════════════════════════════

@dataclass
class InferenceStats:
    """推断统计数据"""
    total_fields: int = 0
    cache_hits: int = 0
    rag_hits: int = 0
    llm_inferences: int = 0
    rag_stores: int = 0
    total_time_ms: float = 0.0
    
    @property
    def rag_hit_rate(self) -> float:
        """RAG 命中率"""
        total = self.rag_hits + self.llm_inferences
        if total == 0:
            return 0.0
        return self.rag_hits / total
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "total_fields": self.total_fields,
            "cache_hits": self.cache_hits,
            "rag_hits": self.rag_hits,
            "llm_inferences": self.llm_inferences,
            "rag_stores": self.rag_stores,
            "rag_hit_rate": self.rag_hit_rate,
            "total_time_ms": self.total_time_ms,
        }


# ═══════════════════════════════════════════════════════════
# 主推断类
# ═══════════════════════════════════════════════════════════

class DimensionHierarchyInference:
    """
    维度层级主推断类
    
    实现 RAG 优先 + LLM 兜底 + 延迟加载样例数据的推断策略。
    
    使用方式：
        inference = DimensionHierarchyInference(
            faiss_store=faiss_store,
            cache_storage=cache_storage,
        )
        result = await inference.infer(
            datasource_luid="ds-123",
            fields=[...],
        )
    """
    
    def __init__(
        self,
        faiss_store: DimensionPatternFAISS,
        cache_storage: DimensionHierarchyCacheStorage,
        rag_retriever: Optional[DimensionRAGRetriever] = None,
    ):
        """
        Args:
            faiss_store: FAISS 向量存储实例
            cache_storage: 缓存存储实例
            rag_retriever: RAG 检索器实例（可选，不传则自动创建）
        """
        self._faiss_store = faiss_store
        self._cache_storage = cache_storage
        self._rag_retriever = rag_retriever or DimensionRAGRetriever(
            faiss_store=faiss_store,
            cache_storage=cache_storage,
        )
        
        # 并发控制
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock_times: Dict[str, float] = {}
        self._global_lock = asyncio.Lock()
        
        # 统计数据
        self._stats = InferenceStats()
        
        # 种子数据初始化标志
        self._seed_initialized = False

    # ═══════════════════════════════════════════════════════════
    # 并发控制
    # ═══════════════════════════════════════════════════════════
    
    async def _get_lock(self, cache_key: str) -> asyncio.Lock:
        """
        获取指定 cache_key 的锁
        
        按 cache_key 粒度加锁，避免同一数据源的并发推断。
        
        Args:
            cache_key: 缓存 key
        
        Returns:
            asyncio.Lock 实例
        """
        async with self._global_lock:
            # 清理过期锁
            self._cleanup_old_locks()
            
            if cache_key not in self._locks:
                self._locks[cache_key] = asyncio.Lock()
            
            self._lock_times[cache_key] = time.time()
            return self._locks[cache_key]
    
    def _cleanup_old_locks(self) -> None:
        """
        清理过期的锁
        
        防止锁字典无限增长。
        """
        if len(self._locks) <= MAX_LOCKS:
            return
        
        current_time = time.time()
        expired_keys = [
            key for key, lock_time in self._lock_times.items()
            if current_time - lock_time > LOCK_EXPIRE_SECONDS
        ]
        
        for key in expired_keys:
            if key in self._locks and not self._locks[key].locked():
                del self._locks[key]
                del self._lock_times[key]
        
        logger.debug(f"清理过期锁: {len(expired_keys)} 个")
    
    # ═══════════════════════════════════════════════════════════
    # 种子数据初始化
    # ═══════════════════════════════════════════════════════════
    
    def _ensure_seed_data(self) -> None:
        """
        确保种子数据已初始化
        
        首次调用时自动初始化种子数据到 RAG，并检查一致性。
        
        修复场景：
        1. FAISS=0 & metadata=0: 初始化种子数据
        2. FAISS=0 & metadata>0: 从 metadata 重建 FAISS（关键修复）
        3. FAISS>0 & metadata 数量不一致: 一致性修复
        """
        if self._seed_initialized:
            return
        
        faiss_count = self._faiss_store.count
        metadata_count = len(self._cache_storage.get_all_pattern_metadata())
        
        logger.debug(f"一致性检查: FAISS={faiss_count}, metadata={metadata_count}")
        
        if faiss_count == 0 and metadata_count == 0:
            # 场景 1: 全新系统，初始化种子数据
            logger.info("FAISS 和 metadata 均为空，初始化种子数据")
            count = initialize_seed_patterns(self._rag_retriever)
            logger.info(f"种子数据初始化完成: {count} 个模式")
        elif faiss_count == 0 and metadata_count > 0:
            # 场景 2: FAISS 丢失但 metadata 存在（关键修复场景）
            # 这可能是索引目录被清理/损坏导致的
            logger.warning(
                f"FAISS 索引丢失但 metadata 存在 ({metadata_count} 个)，"
                f"从 metadata 重建 FAISS 索引"
            )
            self._rebuild_faiss_from_metadata()
        elif faiss_count != metadata_count:
            # 场景 3: 数量不一致，执行一致性修复
            logger.debug(f"FAISS 索引已有 {faiss_count} 个向量")
            self._auto_repair_consistency()
        else:
            logger.debug(f"FAISS 和 metadata 数量一致: {faiss_count}")
        
        self._seed_initialized = True
    
    def _rebuild_faiss_from_metadata(self) -> bool:
        """
        从 metadata 重建 FAISS 索引
        
        用于 FAISS 索引丢失但 metadata 仍存在的场景。
        
        Returns:
            是否成功重建
        """
        all_metadata = self._cache_storage.get_all_pattern_metadata()
        
        if not all_metadata:
            logger.warning("无 metadata 可用于重建 FAISS")
            return False
        
        # 从 metadata 构建 patterns 列表
        patterns = []
        for metadata in all_metadata:
            pattern_id = metadata.get("pattern_id")
            if not pattern_id:
                continue
            
            query_text = self._rag_retriever._build_query_text_metadata_only(
                metadata["field_caption"],
                metadata["data_type"],
            )
            patterns.append({
                "pattern_id": pattern_id,
                "text": query_text,
                "metadata": {
                    "field_caption": metadata["field_caption"],
                    "data_type": metadata["data_type"],
                },
            })
        
        if not patterns:
            logger.warning("无有效 pattern 可用于重建 FAISS")
            return False
        
        # 重建索引
        self._faiss_store.rebuild_index(patterns)
        logger.info(f"FAISS 索引重建完成: {len(patterns)} 个向量")
        return True
    
    def _auto_repair_consistency(self) -> bool:
        """
        自动修复 FAISS 和 metadata 的一致性
        
        从 metadata 重新构造 query_text，再 rebuild FAISS。
        
        Returns:
            是否执行了修复
        """
        # 获取所有 metadata（返回列表）
        all_metadata = self._cache_storage.get_all_pattern_metadata()
        
        if not all_metadata:
            logger.debug("无 metadata，跳过一致性修复")
            return False
        
        # 检查 FAISS 数量是否匹配
        faiss_count = self._faiss_store.count
        metadata_count = len(all_metadata)
        
        if faiss_count == metadata_count:
            logger.debug(f"FAISS 和 metadata 数量一致: {faiss_count}")
            return False
        
        logger.warning(
            f"FAISS ({faiss_count}) 和 metadata ({metadata_count}) 数量不一致，"
            f"开始自动修复"
        )
        
        # 从 metadata 重建 FAISS（all_metadata 是列表）
        patterns = []
        for metadata in all_metadata:
            pattern_id = metadata.get("pattern_id")
            if not pattern_id:
                continue
            
            query_text = self._rag_retriever._build_query_text_metadata_only(
                metadata["field_caption"],
                metadata["data_type"],
            )
            patterns.append({
                "pattern_id": pattern_id,
                "text": query_text,
                "metadata": {
                    "field_caption": metadata["field_caption"],
                    "data_type": metadata["data_type"],
                },
            })
        
        # 重建索引
        self._faiss_store.rebuild_index(patterns)
        
        logger.info(f"一致性修复完成: 重建 {len(patterns)} 个向量")
        return True
    
    # ═══════════════════════════════════════════════════════════
    # RAG 存储
    # ═══════════════════════════════════════════════════════════
    
    def _store_to_rag(
        self,
        results: Dict[str, DimensionAttributes],
        fields: List[Dict[str, Any]],
        datasource_luid: Optional[str] = None,
    ) -> int:
        """
        将高置信度结果存入 RAG
        
        只存储置信度 >= RAG_STORE_CONFIDENCE_THRESHOLD (0.85) 的结果。
        
        Args:
            results: 推断结果 {field_name: DimensionAttributes}
            fields: 字段列表（用于获取 field_caption, data_type）
            datasource_luid: 数据源 LUID
        
        Returns:
            成功存储到 FAISS 的数量（真正可检索的）
        """
        # 构建字段信息映射
        field_info = {f["field_name"]: f for f in fields}
        
        patterns_to_store = []
        for field_name, attrs in results.items():
            if attrs.level_confidence < RAG_STORE_CONFIDENCE_THRESHOLD:
                continue
            
            field = field_info.get(field_name)
            if not field:
                continue
            
            patterns_to_store.append({
                "field_caption": field["field_caption"],
                "data_type": field["data_type"],
                "category": attrs.category.value,
                "category_detail": attrs.category_detail,
                "level": attrs.level,
                "granularity": attrs.granularity,
                "reasoning": attrs.reasoning,
                "confidence": attrs.level_confidence,
                "datasource_luid": datasource_luid,
                "sample_values": field.get("sample_values"),
                "unique_count": field.get("unique_count", 0),
                "source": "llm",
                "verified": False,
            })
        
        if not patterns_to_store:
            return 0
        
        # batch_store_patterns 现在返回详细统计字典
        store_result = self._rag_retriever.batch_store_patterns(patterns_to_store)
        
        # 使用 FAISS 真正写入数作为统计（这才是可检索的）
        faiss_written = store_result.get("faiss_written", 0)
        self._stats.rag_stores += faiss_written
        
        logger.info(
            f"存入 RAG: faiss={faiss_written}/{len(patterns_to_store)} 个高置信度结果"
            f"（metadata={store_result.get('metadata_written', 0)}）"
        )
        return faiss_written

    # ═══════════════════════════════════════════════════════════
    # LLM 推断
    # ═══════════════════════════════════════════════════════════
    
    async def _infer_with_llm_batched(
        self,
        fields: List[Dict[str, Any]],
        sample_value_fetcher: Optional[Callable[[List[str]], Awaitable[Dict[str, Dict[str, Any]]]]] = None,
    ) -> Dict[str, DimensionAttributes]:
        """
        分批 LLM 推断
        
        每批最多 MAX_FIELDS_PER_INFERENCE (30) 个字段。
        
        Args:
            fields: 要推断的字段列表
            sample_value_fetcher: 样例值获取函数（延迟加载），返回 {field_name: {"sample_values": [...], "unique_count": int}}
        
        Returns:
            推断结果 {field_name: DimensionAttributes}
        """
        if not fields:
            return {}
        
        # 延迟加载样例值和唯一值数量
        if sample_value_fetcher:
            field_names = [f["field_name"] for f in fields]
            try:
                sample_data_map = await sample_value_fetcher(field_names)
                for f in fields:
                    field_name = f["field_name"]
                    if field_name in sample_data_map:
                        data = sample_data_map[field_name]
                        # 同时回填 sample_values 和 unique_count
                        if isinstance(data, dict):
                            f["sample_values"] = data.get("sample_values", [])
                            f["unique_count"] = data.get("unique_count", 0)
                        else:
                            # 兼容旧格式（直接返回 sample_values 列表）
                            f["sample_values"] = data if isinstance(data, list) else []
            except Exception as e:
                logger.warning(f"获取样例值失败: {e}")
        
        # 分批推断
        all_results: Dict[str, DimensionAttributes] = {}
        
        for i in range(0, len(fields), MAX_FIELDS_PER_INFERENCE):
            batch = fields[i:i + MAX_FIELDS_PER_INFERENCE]
            
            try:
                result = await infer_dimensions_once(batch)
                all_results.update(result.dimension_hierarchy)
                self._stats.llm_inferences += len(batch)
            except Exception as e:
                logger.error(f"LLM 推断批次失败: {e}")
        
        return all_results
    
    # ═══════════════════════════════════════════════════════════
    # 主推断逻辑
    # ═══════════════════════════════════════════════════════════
    
    async def _infer_with_lock(
        self,
        cache_key: str,
        datasource_luid: str,
        fields: List[Dict[str, Any]],
        force_refresh: bool = False,
        skip_rag_store: bool = False,
        sample_value_fetcher: Optional[Callable[[List[str]], Awaitable[Dict[str, List[str]]]]] = None,
    ) -> DimensionHierarchyResult:
        """
        带锁的推断逻辑
        
        流程：
        1. 检查缓存（完全命中直接返回）
        2. 计算增量字段
        3. RAG 检索
        4. LLM 推断（RAG 未命中字段）
        5. 存入 RAG（高置信度结果）
        6. 更新缓存
        
        Args:
            cache_key: 缓存 key
            datasource_luid: 数据源 LUID
            fields: 字段列表
            force_refresh: 是否强制刷新（跳过缓存）
            skip_rag_store: 是否跳过 RAG 存储
            sample_value_fetcher: 样例值获取函数
        
        Returns:
            DimensionHierarchyResult 推断结果
        """
        start_time = time.time()
        self._stats.total_fields += len(fields)
        
        # 1. 检查缓存
        cached_data = None
        cached_field_hashes = None
        cached_field_names = None
        
        if not force_refresh:
            cached = self._cache_storage.get_hierarchy_cache(cache_key)
            if cached:
                cached_data = cached.get("hierarchy_data", {})
                cached_field_hashes = cached.get("field_meta_hashes", {})
                cached_field_names = set(cached_data.keys())
                
                # 计算当前字段 hash
                current_hash = compute_field_hash_metadata_only(fields)
                cached_hash = cached.get("field_hash")
                
                if current_hash == cached_hash:
                    # 完全命中
                    self._stats.cache_hits += len(fields)
                    self._stats.total_time_ms += (time.time() - start_time) * 1000
                    
                    logger.info(f"缓存完全命中: {len(cached_data)} 个字段")
                    
                    # 转换为 DimensionAttributes
                    hierarchy = {}
                    for field_name, attrs_dict in cached_data.items():
                        hierarchy[field_name] = DimensionAttributes(**attrs_dict)
                    
                    return DimensionHierarchyResult(dimension_hierarchy=hierarchy)
        
        # 2. 计算增量字段
        incremental = compute_incremental_fields(
            fields,
            cached_field_hashes,
            cached_field_names,
        )
        
        # 3. 准备结果（从缓存复用未变化字段）
        final_results: Dict[str, DimensionAttributes] = {}
        
        if cached_data:
            for field_name in incremental.unchanged_fields:
                if field_name in cached_data:
                    final_results[field_name] = DimensionAttributes(**cached_data[field_name])
        
        # 4. 获取需要推断的字段
        fields_to_infer = [
            f for f in fields
            if f["field_name"] in incremental.fields_to_infer
        ]
        
        if not fields_to_infer:
            # 无需推断，只需删除已删除字段
            self._stats.total_time_ms += (time.time() - start_time) * 1000
            
            # 更新缓存
            self._update_cache(cache_key, fields, final_results)
            
            return DimensionHierarchyResult(dimension_hierarchy=final_results)
        
        logger.info(
            f"增量推断: 新增={len(incremental.new_fields)}, "
            f"变更={len(incremental.changed_fields)}, "
            f"复用={len(incremental.unchanged_fields)}"
        )
        
        # 5. RAG 检索
        rag_results = self._rag_retriever.batch_search_metadata_only(fields_to_infer)
        
        rag_hit_fields = []
        llm_fields = []
        
        for f in fields_to_infer:
            field_name = f["field_name"]
            pattern, similarity = rag_results.get(field_name, (None, 0.0))
            
            if pattern:
                # RAG 命中
                self._stats.rag_hits += 1
                
                # 构建 DimensionAttributes
                # 重要：RAG 命中时 sample_values=None, unique_count=None
                # 表示"未查询"，而不是"没有数据"（符合 design.md 1.9 节要求）
                # level_confidence 使用本次检索的 similarity（而非历史 pattern confidence）
                # 注意：由于浮点数精度问题，similarity 可能略大于 1，需要 clamp 到 [0, 1]
                clamped_similarity = min(1.0, max(0.0, similarity))
                
                attrs = DimensionAttributes(
                    category=pattern["category"],
                    category_detail=pattern["category_detail"],
                    level=pattern["level"],
                    granularity=pattern["granularity"],
                    unique_count=None,  # RAG 命中时设为 None，表示未查询
                    sample_values=None,  # RAG 命中时设为 None，表示未查询
                    level_confidence=clamped_similarity,  # 使用本次检索的相似度作为置信度
                    reasoning=f"RAG 命中 (similarity={similarity:.3f}): {pattern['reasoning']}",
                    parent_dimension=None,
                    child_dimension=None,
                )
                final_results[field_name] = attrs
                rag_hit_fields.append(field_name)
            else:
                # RAG 未命中，需要 LLM 推断
                llm_fields.append(f)
        
        logger.info(f"RAG 检索: 命中 {len(rag_hit_fields)}, 未命中 {len(llm_fields)}")
        
        # 6. LLM 推断（RAG 未命中字段）
        if llm_fields:
            llm_results = await self._infer_with_llm_batched(
                llm_fields,
                sample_value_fetcher,
            )
            final_results.update(llm_results)
            
            # 7. 存入 RAG（高置信度结果）
            if not skip_rag_store:
                self._store_to_rag(llm_results, llm_fields, datasource_luid)
        
        # 8. 更新缓存
        self._update_cache(cache_key, fields, final_results)
        
        self._stats.total_time_ms += (time.time() - start_time) * 1000
        
        return DimensionHierarchyResult(dimension_hierarchy=final_results)
    
    def _update_cache(
        self,
        cache_key: str,
        fields: List[Dict[str, Any]],
        results: Dict[str, DimensionAttributes],
    ) -> None:
        """
        更新缓存
        
        Args:
            cache_key: 缓存 key
            fields: 字段列表
            results: 推断结果
        """
        # 计算字段 hash
        field_hash = compute_field_hash_metadata_only(fields)
        
        # 计算单字段 hash
        field_meta_hashes = {}
        for f in fields:
            field_meta_hashes[f["field_name"]] = compute_single_field_hash(
                f["field_name"],
                f["field_caption"],
                f["data_type"],
            )
        
        # 转换结果为字典
        hierarchy_data = {}
        for field_name, attrs in results.items():
            hierarchy_data[field_name] = attrs.model_dump()
        
        # 存入缓存
        self._cache_storage.put_hierarchy_cache(
            cache_key=cache_key,
            field_hash=field_hash,
            hierarchy_data=hierarchy_data,
            field_meta_hashes=field_meta_hashes,
        )

    # ═══════════════════════════════════════════════════════════
    # 公开接口
    # ═══════════════════════════════════════════════════════════
    
    async def infer(
        self,
        datasource_luid: str,
        fields: List[Dict[str, Any]],
        logical_table_id: Optional[str] = None,
        force_refresh: bool = False,
        skip_rag_store: bool = False,
        sample_value_fetcher: Optional[Callable[[List[str]], Awaitable[Dict[str, List[str]]]]] = None,
    ) -> DimensionHierarchyResult:
        """
        推断维度层级（主入口）
        
        流程：
        1. 确保种子数据已初始化
        2. 获取锁
        3. 执行推断
        
        Args:
            datasource_luid: 数据源 LUID
            fields: 字段列表，每个字段包含：
                - field_name: 字段名
                - field_caption: 字段标题
                - data_type: 数据类型
                - sample_values: 样例值列表（可选）
                - unique_count: 唯一值数量（可选）
            logical_table_id: 逻辑表 ID（可选，多表数据源时使用）
            force_refresh: 是否强制刷新（跳过缓存）
            skip_rag_store: 是否跳过 RAG 存储
            sample_value_fetcher: 样例值获取函数（延迟加载）
        
        Returns:
            DimensionHierarchyResult 推断结果
        
        Example:
            result = await inference.infer(
                datasource_luid="ds-123",
                fields=[
                    {"field_name": "year", "field_caption": "年份", "data_type": "integer"},
                    {"field_name": "city", "field_caption": "城市", "data_type": "string"},
                ],
            )
        """
        if not fields:
            return DimensionHierarchyResult(dimension_hierarchy={})
        
        # 1. 确保种子数据已初始化
        self._ensure_seed_data()
        
        # 2. 构建缓存 key
        cache_key = build_cache_key(datasource_luid, logical_table_id)
        
        # 3. 获取锁
        lock = await self._get_lock(cache_key)
        
        # 4. 执行推断
        async with lock:
            return await self._infer_with_lock(
                cache_key=cache_key,
                datasource_luid=datasource_luid,
                fields=fields,
                force_refresh=force_refresh,
                skip_rag_store=skip_rag_store,
                sample_value_fetcher=sample_value_fetcher,
            )
    
    # ═══════════════════════════════════════════════════════════
    # 统计接口
    # ═══════════════════════════════════════════════════════════
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计数据
        
        Returns:
            统计数据字典，包含：
            - total_fields: 总字段数
            - cache_hits: 缓存命中数
            - rag_hits: RAG 命中数
            - llm_inferences: LLM 推断数
            - rag_stores: RAG 存储数
            - rag_hit_rate: RAG 命中率
            - total_time_ms: 总耗时（毫秒）
        """
        return self._stats.to_dict()
    
    def reset_stats(self) -> None:
        """重置统计数据"""
        self._stats = InferenceStats()


__all__ = [
    "DimensionHierarchyInference",
    "InferenceStats",
    "IncrementalFieldsResult",
    "build_cache_key",
    "compute_incremental_fields",
]
