# -*- coding: utf-8 -*-
"""
RAG 检索与自学习 Mixin

负责 RAG 索引初始化、检索匹配、自学习存储。
从 inference.py 拆分而来。
"""
import logging
from typing import Any, Awaitable, Callable, Optional

from analytics_assistant.src.core.schemas.data_model import Field
from analytics_assistant.src.core.schemas.enums import DimensionCategory, MeasureCategory
from analytics_assistant.src.agents.field_semantic.schemas import (
    FieldSemanticAttributes,
)
from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.rag import (
    get_rag_service,
    IndexConfig,
    IndexDocument,
    IndexBackend,
)
from analytics_assistant.src.agents.field_semantic.utils import (
    FIELD_SEMANTIC_PATTERNS_INDEX,
    PatternSource,
    build_enhanced_index_text,
    generate_pattern_id,
    _get_rag_threshold_seed,
    _get_rag_threshold_unverified,
)

logger = logging.getLogger(__name__)

class RAGMixin:
    """RAG 检索与自学习 Mixin

    提供 RAG 索引初始化、批量检索、自学习存储功能。
    需要宿主类提供:
    - self._enable_rag
    - self._rag_initialized
    - self._pattern_store
    - self._enable_self_learning
    - self._high_confidence
    """

    def _get_index_count(self) -> int:
        """获取向量索引中的模式数量"""
        try:
            rag_service = get_rag_service()
            index_info = rag_service.index.get_index_info(FIELD_SEMANTIC_PATTERNS_INDEX)
            if index_info:
                return index_info.document_count
        except Exception as e:
            logger.warning(f"获取索引模式数量失败: {e}")
        return 0

    def _init_rag(self) -> None:
        """初始化 RAG 检索器"""
        if self._rag_initialized:
            return

        if not self._enable_rag:
            self._rag_initialized = True
            return

        try:
            rag_service = get_rag_service()

            patterns = self._load_patterns()
            if not patterns:
                patterns = self._init_seed_patterns()

            if not patterns:
                self._rag_initialized = True
                return

            existing_index = rag_service.index.get_index(FIELD_SEMANTIC_PATTERNS_INDEX)
            if existing_index is not None:
                logger.info(f"RAG 索引已存在: {FIELD_SEMANTIC_PATTERNS_INDEX}")
                self._rag_initialized = True
                return

            app_config = get_config()
            vector_cfg = app_config.config.get("vector_storage", {})
            index_dir = vector_cfg.get("index_dir", "data/indexes")

            documents = []
            for p in patterns:
                p_role = p.get("role", "dimension")
                index_text = build_enhanced_index_text(
                    caption=p["field_caption"],
                    business_description=p.get("business_description", p["field_caption"]),
                    aliases=p.get("aliases", []),
                    role=p_role,
                    data_type=p["data_type"],
                    category=p.get("category") if p_role == "dimension" else None,
                    measure_category=p.get("measure_category") if p_role == "measure" else None,
                )

                metadata = {
                    "field_caption": p["field_caption"],
                    "data_type": p["data_type"],
                    "role": p.get("role", "dimension"),
                    "source": p.get("source", ""),
                    "verified": p.get("verified", False),
                }

                if p.get("role") == "measure":
                    metadata["measure_category"] = p.get("measure_category", "other")
                else:
                    metadata["category"] = p.get("category", "other")
                    metadata["category_detail"] = p.get("category_detail", "")

                doc = IndexDocument(
                    id=p["pattern_id"],
                    content=index_text,
                    metadata=metadata,
                )
                documents.append(doc)

            config = IndexConfig(
                backend=IndexBackend.FAISS,
                persist_directory=index_dir,
                default_top_k=5,
                score_threshold=_get_rag_threshold_seed(),
            )

            rag_service.index.create_index(
                name=FIELD_SEMANTIC_PATTERNS_INDEX,
                config=config,
                documents=documents,
            )
            logger.info(f"RAG 索引创建完成: {len(patterns)} 个模式")

        except Exception as e:
            logger.warning(f"RAG 初始化失败: {e}")

        self._rag_initialized = True

    async def _rag_search(
        self,
        fields: list[Field],
        field_samples: Optional[dict[str, dict[str, Any]]] = None,
    ) -> tuple[dict[str, FieldSemanticAttributes], list[Field]]:
        """
        RAG 批量检索，返回 (命中结果, 未命中字段)

        优化：使用 batch_search_async 批量检索，避免逐个字段调用 embedding API
        冲突检测：当 RAG 匹配的种子类别与 sample_values 暗示的含义矛盾时，降级给 LLM

        Args:
            fields: 待检索字段列表
            field_samples: 字段样例数据 {field_caption: {sample_values: [...], unique_count: int}}
        """
        if not fields:
            return {}, []

        results: dict[str, FieldSemanticAttributes] = {}
        misses: list[Field] = []

        rag_threshold_seed = _get_rag_threshold_seed()
        rag_threshold_unverified = _get_rag_threshold_unverified()

        try:
            rag_service = get_rag_service()

            if rag_service.index.get_index(FIELD_SEMANTIC_PATTERNS_INDEX) is None:
                logger.warning(f"RAG 索引不存在: {FIELD_SEMANTIC_PATTERNS_INDEX}")
                return {}, fields

            field_map: dict[str, Field] = {}
            queries: list[str] = []
            # 维护 query → field_name 的映射，因为增强查询后键会变化
            query_to_name: dict[str, str] = {}
            for f in fields:
                name = f.caption or f.name
                field_map[name] = f
                # 将样例值加入查询文本，提升 embedding 匹配准确性
                query = name
                if field_samples and name in field_samples:
                    sv = field_samples[name].get("sample_values", [])
                    if sv:
                        query = f"{name} {' '.join(str(v) for v in sv[:5])}"
                queries.append(query)
                query_to_name[query] = name

            logger.info(f"RAG 批量检索: {len(queries)} 个字段")

            batch_results = await rag_service.retrieval.batch_search_async(
                index_name=FIELD_SEMANTIC_PATTERNS_INDEX,
                queries=queries,
                top_k=3,
            )

            for query_key, search_results in batch_results.items():
                # 通过 query → name 映射找到原始字段名
                name = query_to_name.get(query_key)
                if not name:
                    continue
                f = field_map.get(name)
                if not f:
                    continue

                if not search_results:
                    misses.append(f)
                    continue

                best = search_results[0]

                if best.score < rag_threshold_seed:
                    misses.append(f)
                    continue

                pattern = self._pattern_store.get(best.doc_id) if self._pattern_store else None

                if not pattern:
                    misses.append(f)
                    continue

                source = pattern.get("source", "llm")
                verified = pattern.get("verified", False)
                threshold = rag_threshold_seed if source == PatternSource.SEED.value or verified else rag_threshold_unverified

                if best.score < threshold:
                    misses.append(f)
                    continue

                # 冲突检测：sample_values 与种子类别矛盾时降级给 LLM
                if field_samples and name in field_samples:
                    sv = field_samples[name].get("sample_values", [])
                    if sv and self._sample_conflicts_with_pattern(sv, pattern):
                        logger.info(
                            f"RAG 冲突检测: '{name}' 匹配种子 '{pattern['field_caption']}' "
                            f"(类别={pattern.get('category', pattern.get('measure_category', '?'))}), "
                            f"但样例值 {sv[:3]} 与种子类别矛盾，降级给 LLM"
                        )
                        misses.append(f)
                        continue

                pattern_role = pattern.get("role", "dimension")
                if pattern_role == "measure":
                    try:
                        measure_cat = MeasureCategory(pattern.get("measure_category", "other"))
                    except ValueError:
                        measure_cat = MeasureCategory.OTHER

                    pattern_caption = pattern.get("field_caption", "")
                    inherit_aliases = pattern.get("aliases", []) if pattern_caption.lower() == name.lower() else []

                    results[name] = FieldSemanticAttributes(
                        role="measure",
                        measure_category=measure_cat,
                        business_description=pattern.get("business_description", name),
                        aliases=inherit_aliases,
                        confidence=best.score,
                        reasoning=f"RAG 匹配: {pattern['field_caption']} ({best.score:.2f})",
                    )
                else:
                    try:
                        category = DimensionCategory(pattern.get("category", "other"))
                    except ValueError:
                        category = DimensionCategory.OTHER

                    pattern_caption = pattern.get("field_caption", "")
                    inherit_aliases = pattern.get("aliases", []) if pattern_caption.lower() == name.lower() else []

                    results[name] = FieldSemanticAttributes(
                        role="dimension",
                        category=category,
                        category_detail=pattern.get("category_detail", "other-unknown"),
                        level=pattern.get("level", 3),
                        granularity=pattern.get("granularity", "medium"),
                        business_description=pattern.get("business_description", name),
                        aliases=inherit_aliases,
                        confidence=best.score,
                        reasoning=f"RAG 匹配: {pattern['field_caption']} ({best.score:.2f})",
                    )

            logger.info(f"RAG 批量检索完成: 命中 {len(results)} 个, 未命中 {len(misses)} 个")

        except Exception as e:
            logger.warning(f"RAG 批量检索失败: {e}")
            return {}, fields

        return results, misses

    @staticmethod
    def _sample_conflicts_with_pattern(
        sample_values: list[Any],
        pattern: dict[str, Any],
    ) -> bool:
        """检测样例值是否与种子模式的类别矛盾。

        当字段名匹配到某个种子（如"部门"→organization），但样例值明显属于
        另一个类别（如食品名称→product）时，返回 True 表示冲突。

        检测逻辑：
        - 将样例值与各类别的特征词进行匹配
        - 如果样例值暗示的类别与种子类别不同，判定为冲突

        Args:
            sample_values: 字段的样例值列表
            pattern: 匹配到的种子模式

        Returns:
            True 表示存在冲突，应降级给 LLM
        """
        pattern_category = pattern.get("category", pattern.get("measure_category", ""))
        if not pattern_category or pattern_category == "other":
            return False

        # 样例值特征词 → 暗示的类别
        # 只检测高置信度的特征，避免误判
        _CATEGORY_INDICATORS: dict[str, list[str]] = {
            "geography": ["省", "市", "区", "县", "镇", "北京", "上海", "广州", "深圳", "杭州",
                          "南京", "成都", "武汉", "重庆", "天津", "苏州", "西安"],
            "product": ["水果", "蔬菜", "猪肉", "牛肉", "鸡肉", "海鲜", "冷冻", "调味", "饮料",
                        "零食", "日用", "家电", "服装", "鞋", "包", "手机", "电脑", "食品",
                        "生鲜", "粮油", "乳制品", "酒", "茶"],
            "time": ["2020", "2021", "2022", "2023", "2024", "2025", "Q1", "Q2", "Q3", "Q4",
                     "一月", "二月", "三月", "四月", "五月", "六月",
                     "七月", "八月", "九月", "十月", "十一月", "十二月"],
            "customer": ["先生", "女士", "公司", "集团", "有限", "股份"],
        }

        # 统计样例值暗示的类别
        sample_str = " ".join(str(v) for v in sample_values[:10]).lower()
        category_hits: dict[str, int] = {}

        for cat, indicators in _CATEGORY_INDICATORS.items():
            hits = sum(1 for ind in indicators if ind.lower() in sample_str)
            if hits > 0:
                category_hits[cat] = hits

        if not category_hits:
            return False

        # 找到命中最多的类别
        best_category = max(category_hits, key=lambda k: category_hits[k])
        best_hits = category_hits[best_category]

        # 至少命中 2 个特征词才判定冲突（避免单个词误判）
        if best_hits < 2:
            return False

        # 如果暗示的类别与种子类别不同，判定为冲突
        return best_category != pattern_category

    def _store_to_rag(
        self,
        results: dict[str, FieldSemanticAttributes],
        fields: list[Field],
        datasource_luid: str,
    ) -> int:
        """将高置信度结果存入 RAG"""
        if not self._pattern_store or not self._enable_self_learning:
            return 0

        field_map = {f.caption or f.name: f for f in fields}
        pattern_ids = self._pattern_store.get("_pattern_index") or []
        new_patterns = []

        for name, attrs in results.items():
            if attrs.confidence < self._high_confidence:
                continue
            if "种子匹配" in attrs.reasoning or "RAG 匹配" in attrs.reasoning:
                continue

            f = field_map.get(name)
            if not f:
                continue

            pid = generate_pattern_id(name, f.data_type, datasource_luid)
            if self._pattern_store.get(pid):
                continue

            pattern = {
                "pattern_id": pid,
                "field_caption": name,
                "data_type": f.data_type,
                "role": attrs.role,
                "business_description": attrs.business_description,
                "aliases": attrs.aliases,
                "reasoning": attrs.reasoning,
                "confidence": attrs.confidence,
                "source": PatternSource.LLM.value,
                "verified": False,
                "datasource_luid": datasource_luid,
            }

            if attrs.role == "measure":
                pattern["measure_category"] = attrs.measure_category.value if attrs.measure_category else "other"
            else:
                pattern["category"] = attrs.category.value if attrs.category else "other"
                pattern["category_detail"] = attrs.category_detail or "other-unknown"
                pattern["level"] = attrs.level or 3
                pattern["granularity"] = attrs.granularity or "medium"

            self._pattern_store.set(pid, pattern)
            pattern_ids.append(pid)
            new_patterns.append(pattern)

        if new_patterns:
            self._pattern_store.set("_pattern_index", pattern_ids)
            self._add_patterns_to_index(new_patterns)
            logger.info(f"自学习: 存储 {len(new_patterns)} 个新模式")

        return len(new_patterns)

    def _add_patterns_to_index(self, patterns: list[dict[str, Any]]) -> None:
        """增量添加 patterns 到索引"""
        if not patterns:
            return

        try:
            rag_service = get_rag_service()

            if rag_service.index.get_index(FIELD_SEMANTIC_PATTERNS_INDEX) is None:
                logger.warning(f"RAG 索引不存在，跳过增量更新: {FIELD_SEMANTIC_PATTERNS_INDEX}")
                return

            documents = []
            for p in patterns:
                p_role = p.get("role", "dimension")
                index_text = build_enhanced_index_text(
                    caption=p["field_caption"],
                    business_description=p.get("business_description", p["field_caption"]),
                    aliases=p.get("aliases", []),
                    role=p_role,
                    data_type=p["data_type"],
                    category=p.get("category") if p_role == "dimension" else None,
                    measure_category=p.get("measure_category") if p_role == "measure" else None,
                )

                metadata = {
                    "field_caption": p["field_caption"],
                    "data_type": p["data_type"],
                    "role": p.get("role", "dimension"),
                    "source": p.get("source", ""),
                    "verified": p.get("verified", False),
                }

                if p.get("role") == "measure":
                    metadata["measure_category"] = p.get("measure_category", "other")
                else:
                    metadata["category"] = p.get("category", "other")
                    metadata["category_detail"] = p.get("category_detail", "")

                doc = IndexDocument(
                    id=p["pattern_id"],
                    content=index_text,
                    metadata=metadata,
                )
                documents.append(doc)

            added_count = rag_service.index.add_documents(
                index_name=FIELD_SEMANTIC_PATTERNS_INDEX,
                documents=documents,
            )

            logger.debug(f"RAG 索引增量更新: +{added_count} 条")

        except Exception as e:
            logger.warning(f"更新 RAG 索引失败: {e}")
