# -*- coding: utf-8 -*-
"""
维度模式 RAG 检索器

提供维度模式的 RAG 检索功能，结合 FAISS 向量检索和 LangGraph Store 元数据存储。

职责：
- 批量检索相似模式（仅用元数据）
- 从 FAISS 获取向量相似度
- 从 LangGraph Store 获取模式详情
- 存储新模式到 RAG

与存储层配合：
- FAISS: 向量检索，返回 pattern_id + similarity
- LangGraph Store: 根据 pattern_id 获取完整模式信息

阈值分层策略：
- seed/verified: 使用标准阈值 0.92
- llm/unverified: 使用更高阈值 0.95（防止 RAG 污染）

线程安全：
- FAISS 写入操作使用全局锁保护，避免并发写入导致索引损坏
- 读取操作不加锁（FAISS 读取是线程安全的）

Requirements: 1.1, 2.1, 2.2
"""
from typing import List, Dict, Any, Optional, Tuple
import hashlib
import logging
import threading

from .faiss_store import DimensionPatternFAISS
from .cache_storage import (
    DimensionHierarchyCacheStorage,
    RAG_SIMILARITY_THRESHOLD,
    RAG_SIMILARITY_THRESHOLD_UNVERIFIED,
    PatternSource,
)

logger = logging.getLogger(__name__)

# 全局 FAISS 写入锁（跨数据源共享，保证写入的线程安全）
_faiss_write_lock = threading.Lock()


class DimensionRAGRetriever:
    """
    维度模式 RAG 检索器（使用 FAISS）
    
    职责：
    - 批量检索相似模式（仅用元数据）
    - 从 FAISS 获取向量相似度
    - 从 LangGraph Store 获取模式详情
    
    与存储层配合：
    - FAISS: 向量检索，返回 pattern_id + similarity
    - LangGraph Store: 根据 pattern_id 获取完整模式信息
    
    Embedding 说明：
    - FAISS 内部使用 embedding_provider 计算向量
    - 检索时：FAISS 自动将查询文本转为向量进行检索
    - 存储时：FAISS 自动将文本转为向量存入索引
    """
    
    def __init__(
        self,
        faiss_store: DimensionPatternFAISS,
        cache_storage: DimensionHierarchyCacheStorage,
        similarity_threshold: float = RAG_SIMILARITY_THRESHOLD,
        similarity_threshold_unverified: float = RAG_SIMILARITY_THRESHOLD_UNVERIFIED,
    ):
        """
        Args:
            faiss_store: FAISS 向量存储实例
            cache_storage: 缓存存储实例
            similarity_threshold: 标准相似度阈值（seed/verified）
            similarity_threshold_unverified: 未验证结果的相似度阈值（llm/unverified）
        """
        self._faiss_store = faiss_store
        self._cache_storage = cache_storage
        self.similarity_threshold = similarity_threshold
        self.similarity_threshold_unverified = similarity_threshold_unverified

    # ═══════════════════════════════════════════════════════════
    # 阈值管理
    # ═══════════════════════════════════════════════════════════
    
    def _get_effective_threshold(self, pattern: Optional[Dict[str, Any]]) -> float:
        """
        根据 pattern 来源获取有效阈值（污染控制）
        
        阈值分层策略：
        - seed/verified: 使用标准阈值 0.92（可信度高）
        - llm/unverified: 使用更高阈值 0.95（防止错误固化）
        
        Args:
            pattern: 模式元数据，包含 source 和 verified 字段
        
        Returns:
            有效的相似度阈值
        """
        if not pattern:
            return self.similarity_threshold
        
        source = pattern.get("source", "llm")
        verified = pattern.get("verified", False)
        
        if source == "seed" or verified:
            return self.similarity_threshold  # 0.92
        else:
            return self.similarity_threshold_unverified  # 0.95
    
    # ═══════════════════════════════════════════════════════════
    # 查询文本构建
    # ═══════════════════════════════════════════════════════════
    
    @staticmethod
    def _build_query_text_metadata_only(
        field_caption: str,
        data_type: str,
    ) -> str:
        """
        构建查询文本（仅用元数据，不含样例数据）
        
        格式：字段名: {caption} | 数据类型: {data_type}
        
        Args:
            field_caption: 字段标题
            data_type: 数据类型
        
        Returns:
            用于 Embedding 的查询文本
        """
        return f"字段名: {field_caption} | 数据类型: {data_type}"
    
    # ═══════════════════════════════════════════════════════════
    # Pattern ID 生成
    # ═══════════════════════════════════════════════════════════
    
    @staticmethod
    def generate_pattern_id(
        field_caption: str,
        data_type: str,
        datasource_luid: Optional[str] = None,
    ) -> str:
        """
        生成模式 ID
        
        规则：md5(field_caption|data_type|scope)[:16]
        
        包含 data_type 避免同名不同类型字段碰撞：
        - "日期" (date) 和 "日期" (string) 会生成不同的 pattern_id
        
        Args:
            field_caption: 字段标题
            data_type: 数据类型
            datasource_luid: 数据源 LUID（可选，None 表示全局/种子数据）
        
        Returns:
            16 位十六进制字符串
        """
        scope = datasource_luid or "global"
        key = f"{field_caption}|{data_type}|{scope}"
        return hashlib.md5(key.encode()).hexdigest()[:16]

    # ═══════════════════════════════════════════════════════════
    # 批量检索
    # ═══════════════════════════════════════════════════════════
    
    # 检索时的候选数量（top-k），用于处理 metadata 缺失或阈值边缘情况
    DEFAULT_SEARCH_K = 3
    
    def batch_search_metadata_only(
        self,
        fields: List[Dict[str, Any]],
        k: int = DEFAULT_SEARCH_K,
    ) -> Dict[str, Tuple[Optional[Dict[str, Any]], float]]:
        """
        批量检索（仅用元数据，不含样例数据）
        
        流程：
        1. 构建查询文本（仅用 field_caption + data_type）
        2. 批量 FAISS 检索（单次 Embedding API 调用，取 top-k 候选）
        3. 从高到低遍历候选，找第一个"metadata 存在且满足阈值"的结果
        
        Args:
            fields: [{"field_name": str, "field_caption": str, "data_type": str}, ...]
            k: 检索的候选数量（默认 3，用于处理 metadata 缺失情况）
        
        Returns:
            {field_name: (pattern_dict or None, similarity_score)}
            - pattern_dict: 命中时返回完整模式信息，未命中时返回 None
            - similarity_score: 相似度分数（即使未命中也返回最高分数）
            
        注意：
        - 使用阈值分层策略，LLM 推断未验证的结果需要更高相似度才能复用
        - 使用 top-k 检索，跳过 metadata 缺失的候选，提高命中率
        """
        if not fields:
            return {}
        
        results: Dict[str, Tuple[Optional[Dict[str, Any]], float]] = {}
        
        # 1. 构建查询文本（仅用元数据）
        query_texts = []
        field_names = []
        for f in fields:
            query_text = self._build_query_text_metadata_only(
                f["field_caption"],
                f["data_type"],
            )
            query_texts.append(query_text)
            field_names.append(f["field_name"])
        
        # 2. 批量 FAISS 检索（单次 Embedding API 调用，取 top-k 候选）
        search_results = self._faiss_store.batch_search(query_texts, k=k)
        
        # 3. 从高到低遍历候选，找第一个"metadata 存在且满足阈值"的结果
        metadata_miss_count = 0
        
        for i, field_name in enumerate(field_names):
            if not search_results[i]:
                results[field_name] = (None, 0.0)
                continue
            
            # 遍历 top-k 候选
            # 使用负无穷作为初值，避免吞掉负相似度信息
            best_similarity = float("-inf")
            matched_pattern = None
            
            for pattern_id, similarity in search_results[i]:
                # 更新最佳相似度（保留原始值，包括负数）
                if similarity > best_similarity:
                    best_similarity = similarity
                
                # 获取 pattern 详情
                pattern = self._cache_storage.get_pattern_metadata(pattern_id)
                
                if pattern is None:
                    # metadata 缺失（FAISS/metadata 不一致），跳过此候选
                    metadata_miss_count += 1
                    logger.debug(f"metadata 缺失，跳过候选: {pattern_id}")
                    continue
                
                # 根据来源判断阈值
                effective_threshold = self._get_effective_threshold(pattern)
                
                if similarity >= effective_threshold:
                    matched_pattern = pattern
                    best_similarity = similarity
                    break  # 找到第一个满足条件的候选
            
            # 如果没有任何候选，best_similarity 仍为负无穷，转为 0.0 便于下游处理
            if best_similarity == float("-inf"):
                best_similarity = 0.0
            
            if matched_pattern:
                results[field_name] = (matched_pattern, best_similarity)
            else:
                results[field_name] = (None, best_similarity)
        
        # 统计日志
        hit_count = sum(1 for _, (p, _) in results.items() if p is not None)
        log_msg = (
            f"RAG 检索: {len(fields)} 字段, 命中 {hit_count} "
            f"({hit_count/len(fields)*100:.0f}%), "
            f"标准阈值={self.similarity_threshold}, 未验证阈值={self.similarity_threshold_unverified}"
        )
        if metadata_miss_count > 0:
            log_msg += f", metadata 缺失跳过 {metadata_miss_count} 次"
        logger.info(log_msg)
        
        return results

    # ═══════════════════════════════════════════════════════════
    # 模式存储
    # ═══════════════════════════════════════════════════════════
    
    def store_pattern(
        self,
        field_caption: str,
        data_type: str,
        category: str,
        category_detail: str,
        level: int,
        granularity: str,
        reasoning: str,
        confidence: float,
        datasource_luid: Optional[str] = None,
        sample_values: Optional[List[str]] = None,
        unique_count: int = 0,
        source: str = "llm",
        verified: bool = False,
    ) -> bool:
        """
        存入 RAG 模式（FAISS + LangGraph Store）
        
        流程（改进版，先写 metadata 再写 FAISS，减少不一致窗口）：
        1. 生成 pattern_id（包含 data_type 避免碰撞）
        2. 检查是否已存在（避免 FAISS 中重复向量）
        3. 先存储元数据到 LangGraph Store（失败则不写 FAISS）
        4. 再添加到 FAISS 并保存（使用全局锁保护）
        
        Args:
            field_caption: 字段标题
            data_type: 数据类型
            category: 维度类别
            category_detail: 类别详情
            level: 层级
            granularity: 粒度
            reasoning: 推理说明
            confidence: 置信度
            datasource_luid: 数据源 LUID（可选）
            sample_values: 样例值（可选）
            unique_count: 唯一值数量
            source: 来源（seed/llm/manual）
            verified: 是否已验证
        
        Returns:
            是否成功
            
        注意：
        - 此方法是同步的，因为 FAISS 和 LangGraph Store 操作都是同步的
        - 写入顺序：先 metadata 后 FAISS，确保检索时 metadata 一定存在
        - FAISS 写入使用全局锁保护，避免并发写入导致索引损坏
        """
        pattern_id = self.generate_pattern_id(field_caption, data_type, datasource_luid)
        
        # 检查是否已存在（避免 FAISS 中重复向量）
        existing = self._cache_storage.get_pattern_metadata(pattern_id)
        if existing:
            # 检查 FAISS 是否也存在该 pattern（修复不一致）
            # 注意：FAISS 不支持按 ID 查询，这里假设存在
            logger.debug(f"模式已存在，跳过: {pattern_id} ({field_caption})")
            return True
        
        try:
            # 1. 先存储元数据到 LangGraph Store（失败则不写 FAISS）
            source_enum = PatternSource(source) if isinstance(source, str) else source
            
            metadata_stored = self._cache_storage.store_pattern_metadata(
                pattern_id=pattern_id,
                field_caption=field_caption,
                data_type=data_type,
                sample_values=sample_values or [],
                unique_count=unique_count,
                category=category,
                category_detail=category_detail,
                level=level,
                granularity=granularity,
                reasoning=reasoning,
                confidence=confidence,
                datasource_luid=datasource_luid,
                source=source_enum,
                verified=verified,
            )
            
            if not metadata_stored:
                logger.warning(f"存储 metadata 失败，跳过 FAISS: {pattern_id}")
                return False
            
            # 2. 再添加到 FAISS（使用全局锁保护）
            query_text = self._build_query_text_metadata_only(field_caption, data_type)
            
            with _faiss_write_lock:
                success = self._faiss_store.add_pattern(
                    pattern_id=pattern_id,
                    text=query_text,
                    metadata={"field_caption": field_caption, "data_type": data_type},
                )
                
                if not success:
                    logger.warning(f"添加模式到 FAISS 失败: {pattern_id}（metadata 已写入，将在一致性修复时补齐）")
                    # metadata 已写入但 FAISS 失败，返回 False 表示部分失败
                    # 一致性修复会在启动时处理这种情况
                    return False
                
                # 3. 保存 FAISS 索引到磁盘
                self._faiss_store.save()
            
            return True
            
        except Exception as e:
            logger.warning(f"存储模式失败: {e}")
            return False
    
    def batch_store_patterns(
        self,
        patterns: List[Dict[str, Any]],
        save_after_all: bool = True,
    ) -> Dict[str, int]:
        """
        批量存入 RAG 模式
        
        优化：
        - 批量添加后统一保存一次 FAISS 索引，减少磁盘 IO
        - 先写 metadata 再写 FAISS，减少不一致窗口
        - metadata 已存在时直接跳过（不再尝试补齐 FAISS，避免重复写入）
        
        注意：
        - FAISS 不支持按 ID 查询，无法精确判断某个 pattern_id 是否已在 FAISS 中
        - 如果 metadata 存在但 FAISS 缺失，会在启动时的一致性修复中处理
        - 这里不做补齐，避免正常情况下重复写入导致索引膨胀
        
        Args:
            patterns: 模式列表，每个模式包含 store_pattern 所需的所有字段
            save_after_all: 是否在全部添加后统一保存（默认 True）
        
        Returns:
            统计字典：
            - metadata_written: metadata 成功写入数（含已存在跳过的）
            - faiss_written: FAISS 成功写入数（真正新增的）
            - skipped_existing: 已存在跳过数
            - total: 总请求数
        """
        result = {
            "metadata_written": 0,
            "faiss_written": 0,
            "skipped_existing": 0,
            "total": len(patterns),
        }
        
        if not patterns:
            return result
        
        faiss_patterns = []
        
        for p in patterns:
            pattern_id = self.generate_pattern_id(
                p["field_caption"],
                p["data_type"],
                p.get("datasource_luid"),
            )
            
            # 检查 metadata 是否已存在
            existing = self._cache_storage.get_pattern_metadata(pattern_id)
            if existing:
                # metadata 已存在，直接跳过（不再尝试补齐 FAISS）
                # 如果 FAISS 缺失，会在启动时的一致性修复中处理
                logger.debug(f"模式已存在，跳过: {pattern_id}")
                result["metadata_written"] += 1
                result["skipped_existing"] += 1
                continue
            
            # 1. 先存储 metadata
            source = p.get("source", "llm")
            source_enum = PatternSource(source) if isinstance(source, str) else source
            
            stored = self._cache_storage.store_pattern_metadata(
                pattern_id=pattern_id,
                field_caption=p["field_caption"],
                data_type=p["data_type"],
                sample_values=p.get("sample_values") or [],
                unique_count=p.get("unique_count", 0),
                category=p["category"],
                category_detail=p["category_detail"],
                level=p["level"],
                granularity=p["granularity"],
                reasoning=p.get("reasoning", ""),
                confidence=p.get("confidence", 0.0),
                datasource_luid=p.get("datasource_luid"),
                source=source_enum,
                verified=p.get("verified", False),
            )
            
            if not stored:
                logger.warning(f"存储 metadata 失败，跳过 FAISS: {pattern_id}")
                continue
            
            result["metadata_written"] += 1
            
            # 2. 准备 FAISS 数据
            query_text = self._build_query_text_metadata_only(
                p["field_caption"],
                p["data_type"],
            )
            faiss_patterns.append({
                "pattern_id": pattern_id,
                "text": query_text,
                "metadata": {
                    "field_caption": p["field_caption"],
                    "data_type": p["data_type"],
                },
            })
        
        # 3. 批量添加到 FAISS（仅新增的，使用全局锁保护）
        faiss_written = 0
        if faiss_patterns:
            with _faiss_write_lock:
                faiss_written = self._faiss_store.batch_add_patterns(faiss_patterns)
                
                # 统一保存
                if save_after_all:
                    self._faiss_store.save()
        
        result["faiss_written"] = faiss_written
        
        # 检查是否有 metadata-only 模式（metadata 写入但 FAISS 失败）
        metadata_only_count = (result["metadata_written"] - result["skipped_existing"]) - faiss_written
        if metadata_only_count > 0:
            logger.warning(
                f"批量存储存在 metadata-only 模式: {metadata_only_count} 个 "
                f"（metadata 已写入但 FAISS 失败，将在启动时一致性修复）"
            )
        
        logger.info(
            f"批量存储模式: metadata={result['metadata_written']}/{result['total']}, "
            f"faiss={faiss_written}, 已存在跳过={result['skipped_existing']}"
        )
        return result


__all__ = [
    "DimensionRAGRetriever",
]
