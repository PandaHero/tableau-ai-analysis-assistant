# -*- coding: utf-8 -*-
"""
LLM 推断 Mixin

负责 LLM 批量推断、Prompt 构建、响应解析。
从 inference.py 拆分而来。
"""
import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from langchain_core.messages import SystemMessage, HumanMessage

from analytics_assistant.src.core.schemas.data_model import Field
from analytics_assistant.src.agents.field_semantic.schemas import (
    FieldSemanticAttributes,
    LLMFieldSemanticOutput,
)
from analytics_assistant.src.agents.field_semantic.prompts import (
    SYSTEM_PROMPT,
    build_user_prompt,
)
from analytics_assistant.src.agents.base import get_llm, stream_llm_structured
from analytics_assistant.src.agents.field_semantic.utils import (
    _get_config,
    _default_attrs,
)

logger = logging.getLogger(__name__)


class LLMMixin:
    """LLM 推断 Mixin

    提供 LLM 批量推断功能（维度/度量并行）。
    需要宿主类提供:
    - self._max_retry
    """

    async def _llm_infer_batch(
        self,
        fields: List[Field],
        role_filter: str,
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
        on_thinking: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> Dict[str, FieldSemanticAttributes]:
        """
        LLM 推断单个批次（维度或度量）
        """
        batch_results: Dict[str, FieldSemanticAttributes] = {}

        if not fields:
            return batch_results

        config = _get_config()
        llm_batch_config = config.get("llm_batch", {})
        batch_size = llm_batch_config.get("batch_size", 30)
        max_parallel = llm_batch_config.get("max_parallel_batches", 3)

        field_batches = [fields[i:i + batch_size] for i in range(0, len(fields), batch_size)]

        logger.info(f"LLM 推断 ({role_filter}): {len(fields)} 个字段，分 {len(field_batches)} 批处理，最大并行 {max_parallel}")

        async def process_single_batch(batch_idx: int, field_batch: List[Field]) -> Dict[str, FieldSemanticAttributes]:
            """处理单个批次"""
            result = {}

            fields_input = [
                {
                    "field_caption": f.caption or f.name,
                    "data_type": f.data_type,
                    "role": role_filter,
                }
                for f in field_batch
            ]

            user_prompt = build_user_prompt(fields_input, include_few_shot=True)
            messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_prompt)]

            llm = get_llm(agent_name="field_semantic", enable_json_mode=True, max_tokens=8192)

            for attempt in range(self._max_retry):
                try:
                    llm_output: LLMFieldSemanticOutput = await stream_llm_structured(
                        llm, messages, LLMFieldSemanticOutput,
                        on_token=on_token,
                        on_thinking=on_thinking,
                    )

                    semantic_result = llm_output.to_field_semantic_result()
                    for name, attrs in semantic_result.field_semantic.items():
                        result[name] = attrs

                    logger.info(f"LLM 推断批次 {batch_idx + 1}/{len(field_batches)} ({role_filter}): {len(field_batch)} 个字段")
                    return result

                except Exception as e:
                    logger.warning(f"LLM 推断失败 ({role_filter}, 批次 {batch_idx + 1}, 尝试 {attempt + 1}/{self._max_retry}): {e}")
                    if attempt == self._max_retry - 1:
                        logger.error(f"LLM 推断批次 {batch_idx + 1} 失败，使用默认值")

            return result

        semaphore = asyncio.Semaphore(max_parallel)

        async def process_with_semaphore(batch_idx: int, field_batch: List[Field]) -> Dict[str, FieldSemanticAttributes]:
            async with semaphore:
                return await process_single_batch(batch_idx, field_batch)

        tasks = [
            process_with_semaphore(idx, batch)
            for idx, batch in enumerate(field_batches)
        ]

        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results_list:
            if isinstance(result, Exception):
                logger.error(f"LLM 推断批次失败: {result}")
                continue
            batch_results.update(result)

        for f in fields:
            name = f.caption or f.name
            if name not in batch_results:
                batch_results[name] = _default_attrs(name, role_filter)

        logger.info(f"LLM 推断完成 ({role_filter}): {len(batch_results)} 个字段")
        return batch_results

    async def _llm_infer(
        self,
        fields: List[Field],
        results: Dict[str, FieldSemanticAttributes],
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
        on_thinking: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> None:
        """
        LLM 推断（维度和度量并行执行）

        将字段按角色分组，维度和度量分别调用 LLM，并行执行以提高效率。
        """
        if not fields:
            return

        dimension_fields = [f for f in fields if (f.role or "").upper() != "MEASURE"]
        measure_fields = [f for f in fields if (f.role or "").upper() == "MEASURE"]

        logger.info(f"LLM 推断: 维度 {len(dimension_fields)} 个, 度量 {len(measure_fields)} 个（并行执行）")

        tasks = []
        if dimension_fields:
            tasks.append(self._llm_infer_batch(dimension_fields, "dimension", on_token, on_thinking))
        if measure_fields:
            tasks.append(self._llm_infer_batch(measure_fields, "measure", on_token, on_thinking))

        if tasks:
            batch_results_list = await asyncio.gather(*tasks, return_exceptions=True)

            for batch_result in batch_results_list:
                if isinstance(batch_result, Exception):
                    logger.error(f"LLM 推断批次失败: {batch_result}")
                    continue
                results.update(batch_result)
