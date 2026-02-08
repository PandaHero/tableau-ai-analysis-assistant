# -*- coding: utf-8 -*-
"""
字段语义推断服务

推断策略：缓存 → 增量检测 → 种子匹配 → RAG → LLM → 自学习

特性：
- 统一处理维度和度量字段
- 增量推断：只对新增/变更字段进行推断
- 批量 LLM 调用：一次调用处理所有字段
- 自学习：高置信度结果存入 RAG
- 索引增强：生成包含业务描述和别名的索引文本

重构说明：
- 工具函数和常量提取到 utils.py
- 缓存管理提取到 components/cache_mixin.py
- 种子匹配提取到 components/seed_match_mixin.py
- RAG 检索与自学习提取到 components/rag_mixin.py
- LLM 推断提取到 components/llm_mixin.py
"""
import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from analytics_assistant.src.core.schemas.data_model import Field
from analytics_assistant.src.agents.field_semantic.schemas import (
    FieldSemanticAttributes,
    FieldSemanticResult,
    LLMFieldSemanticOutput,
)
from analytics_assistant.src.infra.seeds import DIMENSION_SEEDS, MEASURE_SEEDS
from analytics_assistant.src.infra.storage import CacheManager

from .components import CacheMixin, SeedMatchMixin, RAGMixin, LLMMixin
from .utils import (
    FIELD_SEMANTIC_PATTERNS_INDEX,
    PatternSource,
    IncrementalFieldsResult,
    MAX_LOCKS,
    LOCK_EXPIRE_SECONDS,
    build_enhanced_index_text,
    build_cache_key,
    compute_fields_hash,
    compute_single_field_hash,
    compute_incremental_fields,
    generate_pattern_id,
    _get_config,
    _get_rag_threshold_seed,
    _get_rag_threshold_unverified,
    _default_attrs,
    _default_dimension_attrs,
    _default_measure_attrs,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# 主推断类
# ══════════════════════════════════════════════════════════════

class FieldSemanticInference(CacheMixin, SeedMatchMixin, RAGMixin, LLMMixin):
    """
    字段语义推断服务

    推断策略：缓存 → 增量检测 → 种子匹配 → RAG → LLM → 自学习

    特性：
    - 统一处理维度和度量字段
    - 并发控制：按 cache_key 粒度加锁
    - 批量 LLM 调用：一次调用处理所有字段
    - 自学习：高置信度结果存入 RAG
    """

    def __init__(
        self,
        enable_rag: bool = True,
        enable_cache: bool = True,
        enable_self_learning: bool = True,
    ):
        config = _get_config()
        self._high_confidence = config.get("high_confidence_threshold", 0.85)
        self._max_retry = config.get("max_retry_attempts", 3)
        cache_ns = config.get("cache_namespace", "field_semantic")
        pattern_ns = config.get("pattern_namespace", "field_semantic_patterns_metadata")
        self._incremental_enabled = config.get("incremental", {}).get("enabled", True)

        self._enable_rag = enable_rag
        self._enable_cache = enable_cache
        self._enable_self_learning = enable_self_learning

        # 种子数据索引（维度 + 度量）
        self._dimension_seed_index = {p["field_caption"].lower(): p for p in DIMENSION_SEEDS}
        self._measure_seed_index = {p["field_caption"].lower(): p for p in MEASURE_SEEDS}

        # 缓存
        self._cache = CacheManager(cache_ns) if enable_cache else None
        self._pattern_store = CacheManager(pattern_ns) if enable_self_learning else None

        # RAG 初始化标志
        self._rag_initialized = False
        self._seed_initialized = False

        # 并发控制
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock_times: Dict[str, float] = {}
        self._global_lock = asyncio.Lock()

        # 结果
        self._last_result: Optional[FieldSemanticResult] = None

    # ─────────────────────────────────────────────────────────
    # 并发控制
    # ─────────────────────────────────────────────────────────

    async def _get_lock(self, cache_key: str) -> asyncio.Lock:
        """获取指定 cache_key 的锁"""
        async with self._global_lock:
            self._cleanup_old_locks()

            if cache_key not in self._locks:
                self._locks[cache_key] = asyncio.Lock()

            self._lock_times[cache_key] = time.time()
            return self._locks[cache_key]

    def _cleanup_old_locks(self) -> None:
        """清理过期的锁"""
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

    # ─────────────────────────────────────────────────────────
    # 主推断方法
    # ─────────────────────────────────────────────────────────

    async def infer(
        self,
        datasource_luid: str,
        fields: List[Field],
        table_id: Optional[str] = None,
        skip_cache: bool = False,
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
        on_thinking: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> FieldSemanticResult:
        """
        推断字段语义属性

        Args:
            datasource_luid: 数据源 LUID
            fields: Field 模型列表（包含维度和度量）
            table_id: 逻辑表 ID（多表数据源时使用）
            skip_cache: 是否跳过缓存
            on_token: Token 回调（用于流式输出展示 - 结果内容）
            on_thinking: Thinking 回调（用于流式输出展示 - 思考过程）

        Returns:
            FieldSemanticResult 推断结果
        """
        if not fields:
            self._last_result = FieldSemanticResult(field_semantic={})
            return self._last_result

        cache_key = build_cache_key(datasource_luid, table_id)

        # 确保种子数据已初始化
        self._ensure_seed_data()

        # 获取锁，避免同一数据源的并发推断
        lock = await self._get_lock(cache_key)
        async with lock:
            return await self._infer_with_lock(
                datasource_luid, fields, table_id, cache_key, skip_cache, on_token, on_thinking
            )

    async def _infer_with_lock(
        self,
        datasource_luid: str,
        fields: List[Field],
        table_id: Optional[str],
        cache_key: str,
        skip_cache: bool,
        on_token: Optional[Callable[[str], Awaitable[None]]],
        on_thinking: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> FieldSemanticResult:
        """在锁保护下执行推断

        优化策略：
        1. 种子匹配且有 aliases → 直接使用种子数据
        2. 种子匹配但没有 aliases → 走 LLM 生成 aliases
        3. RAG 匹配 → 走 LLM 验证并生成 aliases
        4. 未匹配 → 走 LLM 推断
        """
        results: Dict[str, FieldSemanticAttributes] = {}

        # 1. 缓存检查
        cached_data, cached_hashes, cached_names = None, None, None
        if not skip_cache and self._incremental_enabled:
            cached = self._get_cache(cache_key)
            if cached:
                cached_data = cached.get("data", {})
                cached_hashes = cached.get("field_hashes", {})
                cached_names = set(cached_data.keys())

                if compute_fields_hash(fields) == cached.get("field_hash"):
                    logger.info(f"缓存完全命中: {len(cached_data)} 个字段")
                    for name, data in cached_data.items():
                        results[name] = self._deserialize_attrs(data)
                    self._last_result = FieldSemanticResult(field_semantic=results)
                    return self._last_result

        # 2. 增量计算
        incremental = compute_incremental_fields(fields, cached_hashes, cached_names)

        if cached_data:
            for name in incremental.unchanged_fields:
                if name in cached_data:
                    results[name] = self._deserialize_attrs(cached_data[name])

        fields_to_infer = [f for f in fields if (f.caption or f.name) in incremental.fields_to_infer]

        if not fields_to_infer:
            logger.info(f"增量检测: 无需推断，复用 {len(results)} 个缓存")
            self._update_cache(cache_key, fields, results)
            self._last_result = FieldSemanticResult(field_semantic=results)
            return self._last_result

        logger.info(f"增量推断: 新增={len(incremental.new_fields)}, 变更={len(incremental.changed_fields)}")

        # 3. 种子匹配：有 aliases 的直接使用，没有的需要 LLM 补充
        fields_need_llm: List[Field] = []
        seed_hit_count = 0

        for f in fields_to_infer:
            name = f.caption or f.name
            role = f.role or "dimension"
            seed = self._match_seed(name, role)
            if seed and seed.get("aliases"):
                results[name] = self._seed_to_attrs(seed, role)
                seed_hit_count += 1
            else:
                fields_need_llm.append(f)

        logger.info(f"种子匹配: {seed_hit_count} 个字段直接使用，{len(fields_need_llm)} 个需要 LLM")

        # 4. RAG 检索（作为 LLM 参考，但不直接使用）
        if self._enable_rag and fields_need_llm:
            self._init_rag()

        # 5. LLM 推断（生成 aliases）
        if fields_need_llm:
            await self._llm_infer(fields_need_llm, results, on_token, on_thinking)

        # 6. 自学习
        if self._enable_self_learning:
            self._store_to_rag(results, fields, datasource_luid)

        # 7. 更新缓存
        self._update_cache(cache_key, fields, results)

        logger.info(f"推断完成: 种子={seed_hit_count}, LLM={len(fields_need_llm)}, 总计={len(results)}")

        self._last_result = FieldSemanticResult(field_semantic=results)
        return self._last_result

    # ─────────────────────────────────────────────────────────
    # 公开接口
    # ─────────────────────────────────────────────────────────

    def get_result(self) -> Optional[FieldSemanticResult]:
        """获取推断结果"""
        return self._last_result

    def enrich_fields(self, fields: List[Field]) -> List[Field]:
        """使用推断结果更新 Field 对象"""
        if not self._last_result:
            return fields

        for f in fields:
            name = f.caption or f.name
            attrs = self._last_result.field_semantic.get(name)
            if attrs:
                f.business_description = attrs.business_description
                f.aliases = attrs.aliases

                if attrs.role == "dimension":
                    f.category = attrs.category.value if attrs.category else "other"
                    f.category_detail = attrs.category_detail
                    f.hierarchy_level = attrs.level
                    f.granularity = attrs.granularity
                    f.level_confidence = attrs.confidence
                elif attrs.role == "measure":
                    f.measure_category = attrs.measure_category.value if attrs.measure_category else "other"

        return fields

    def clear_cache(self, cache_key: Optional[str] = None) -> bool:
        """清除缓存"""
        if not self._cache:
            return False
        return self._cache.delete(cache_key) if cache_key else False


# ══════════════════════════════════════════════════════════════
# 便捷函数
# ══════════════════════════════════════════════════════════════

async def infer_field_semantic(
    datasource_luid: str,
    fields: List[Field],
    table_id: Optional[str] = None,
    on_token: Optional[Callable[[str], Awaitable[None]]] = None,
) -> FieldSemanticResult:
    """便捷函数：推断字段语义属性"""
    inference = FieldSemanticInference()
    return await inference.infer(datasource_luid, fields, table_id, on_token=on_token)


__all__ = [
    "FieldSemanticInference",
    "FieldSemanticResult",
    "FieldSemanticAttributes",
    "IncrementalFieldsResult",
    "PatternSource",
    "build_cache_key",
    "build_enhanced_index_text",
    "compute_fields_hash",
    "compute_incremental_fields",
    "infer_field_semantic",
]
