# -*- coding: utf-8 -*-
"""LLM 调用相关方法。依赖主类初始化 self.config 和 CacheMixin。"""
import logging
import time
from typing import Any, Optional

from analytics_assistant.src.agents.base import get_llm, stream_llm_structured

from ..schemas import (
    SingleSelectionResult,
    FieldMapping,
    FieldCandidate,
)
from ..prompts import FIELD_MAPPER_PROMPT, format_candidates

logger = logging.getLogger(__name__)

class LLMMixin:
    """LLM 调用相关方法 Mixin"""

    async def _llm_select(
        self,
        term: str,
        candidates: list[FieldCandidate],
        context: Optional[str] = None,
    ) -> SingleSelectionResult:
        """使用 LLM 从候选中选择最佳匹配"""
        if not candidates:
            return SingleSelectionResult(
                business_term=term,
                selected_field=None,
                confidence=0.0,
                reasoning="没有提供候选"
            )

        candidates_text = format_candidates(candidates)
        messages = FIELD_MAPPER_PROMPT.format_messages(
            term=term,
            context=context or "没有额外上下文",
            candidates=candidates_text
        )

        llm = get_llm(agent_name="field_mapper", enable_json_mode=True)
        result = await stream_llm_structured(llm, messages, SingleSelectionResult)

        # 验证选择的字段是否在候选列表中
        if result.selected_field:
            valid_fields = {c.field_name for c in candidates}
            if result.selected_field not in valid_fields:
                logger.warning(
                    f"LLM 选择了无效字段 '{result.selected_field}' for '{term}', "
                    f"回退到第一候选 '{candidates[0].field_name}'"
                )
                return SingleSelectionResult(
                    business_term=term,
                    selected_field=candidates[0].field_name,
                    confidence=candidates[0].confidence * 0.9,
                    reasoning=f"LLM 选择了无效字段，使用第一候选: {candidates[0].field_name}"
                )

        return result

    async def _llm_select_from_candidates(
        self,
        term: str,
        candidates: list[FieldCandidate],
        datasource_luid: str,
        context: Optional[str] = None,
        role_filter: Optional[str] = None,
        start_time: Optional[float] = None,
        mapping_source: str = "llm_only",
    ) -> FieldMapping:
        """公共的 LLM 候选选择逻辑。

        消除 _map_field_with_llm_only 和 _map_field_with_llm_fallback 的重复。

        Args:
            term: 业务术语
            candidates: 候选字段列表
            datasource_luid: 数据源标识
            context: 问题上下文
            role_filter: 角色过滤
            start_time: 开始时间（用于计算延迟）
            mapping_source: 映射来源标识

        Returns:
            FieldMapping 结果
        """
        if start_time is None:
            start_time = time.time()

        self._llm_fallback_count += 1

        try:
            selection = await self._llm_select(
                term=term,
                candidates=candidates,
                context=context,
            )

            latency = int((time.time() - start_time) * 1000)

            # 查找选中的候选
            selected_candidate = next(
                (c for c in candidates if c.field_name == selection.selected_field),
                None
            )

            category = selected_candidate.category if selected_candidate else None
            level = selected_candidate.level if selected_candidate else None
            granularity = selected_candidate.granularity if selected_candidate else None

            # 缓存结果
            if self.config.enable_cache and selection.selected_field:
                self._put_to_cache(
                    term=term,
                    datasource_luid=datasource_luid,
                    technical_field=selection.selected_field,
                    confidence=selection.confidence,
                    role_filter=role_filter,
                    category=category,
                    level=level,
                    granularity=granularity,
                )

            # 构建备选列表
            alternatives = [
                {
                    "technical_field": c.field_name,
                    "confidence": c.confidence,
                    "reason": c.field_caption or ""
                }
                for c in candidates[:self.config.max_alternatives]
                if c.field_name != selection.selected_field
            ] if selection.confidence < self.config.low_confidence_threshold else []

            logger.debug(
                f"{mapping_source}: {term} -> {selection.selected_field} "
                f"(confidence={selection.confidence:.2f})"
            )

            return FieldMapping(
                business_term=term,
                technical_field=selection.selected_field,
                confidence=selection.confidence,
                mapping_source=mapping_source,
                reasoning=selection.reasoning,
                alternatives=alternatives,
                category=category,
                level=level,
                granularity=granularity,
                latency_ms=latency,
            )

        except Exception as e:
            logger.error(f"LLM 选择失败 '{term}': {e}")
            latency = int((time.time() - start_time) * 1000)
            return FieldMapping(
                business_term=term,
                technical_field=None,
                confidence=0.0,
                mapping_source="error",
                reasoning=f"LLM 选择失败: {e}",
                latency_ms=latency,
            )
