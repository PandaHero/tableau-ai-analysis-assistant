# -*- coding: utf-8 -*-
"""
LLM 推断 Mixin

负责 LLM 批量推断、Prompt 构建、响应解析。
从 inference.py 拆分而来。
"""
import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

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
        fields: list[Field],
        role_filter: str,
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
        on_thinking: Optional[Callable[[str], Awaitable[None]]] = None,
        field_samples: Optional[dict[str, dict[str, Any]]] = None,
    ) -> dict[str, FieldSemanticAttributes]:
        """
        LLM 推断单个批次（维度或度量）

        Args:
            fields: 待推断字段列表
            role_filter: 字段角色（dimension/measure）
            on_token: Token 回调
            on_thinking: Thinking 回调
            field_samples: 字段样例数据 {field_caption: {sample_values: [...], unique_count: int}}
        """
        batch_results: dict[str, FieldSemanticAttributes] = {}

        if not fields:
            return batch_results

        config = _get_config()
        llm_batch_config = config.get("llm_batch", {})
        batch_size = llm_batch_config.get("batch_size", 30)
        max_parallel = llm_batch_config.get("max_parallel_batches", 3)

        field_batches = [fields[i:i + batch_size] for i in range(0, len(fields), batch_size)]

        logger.info(f"LLM 推断 ({role_filter}): {len(fields)} 个字段，分 {len(field_batches)} 批处理，最大并行 {max_parallel}")

        async def process_single_batch(batch_idx: int, field_batch: list[Field]) -> dict[str, FieldSemanticAttributes]:
            """处理单个批次"""
            result = {}

            fields_input = []
            for f in field_batch:
                caption = f.caption or f.name
                info: dict[str, Any] = {
                    "field_caption": caption,
                    "data_type": f.data_type,
                    "role": role_filter,
                }
                # 传入样例值，帮助 LLM 准确推断字段语义
                if field_samples and caption in field_samples:
                    sample_info = field_samples[caption]
                    sv = sample_info.get("sample_values", [])
                    if sv:
                        info["sample_values"] = sv[:5]
                fields_input.append(info)

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

        async def process_with_semaphore(batch_idx: int, field_batch: list[Field]) -> dict[str, FieldSemanticAttributes]:
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
        fields: list[Field],
        results: dict[str, FieldSemanticAttributes],
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
        on_thinking: Optional[Callable[[str], Awaitable[None]]] = None,
        field_samples: Optional[dict[str, dict[str, Any]]] = None,
    ) -> None:
        """
        LLM 推断（维度和度量并行执行）

        将字段按角色分组，维度和度量分别调用 LLM，并行执行以提高效率。

        Args:
            fields: 待推断字段列表
            results: 推断结果字典（会被原地更新）
            on_token: Token 回调
            on_thinking: Thinking 回调
            field_samples: 字段样例数据 {field_caption: {sample_values: [...], unique_count: int}}
        """
        if not fields:
            return

        dimension_fields = [f for f in fields if (f.role or "").upper() != "MEASURE"]
        measure_fields = [f for f in fields if (f.role or "").upper() == "MEASURE"]

        logger.info(f"LLM 推断: 维度 {len(dimension_fields)} 个, 度量 {len(measure_fields)} 个（并行执行）")

        tasks = []
        if dimension_fields:
            tasks.append(self._llm_infer_batch(
                dimension_fields, "dimension", on_token, on_thinking,
                field_samples=field_samples,
            ))
        if measure_fields:
            tasks.append(self._llm_infer_batch(
                measure_fields, "measure", on_token, on_thinking,
                field_samples=field_samples,
            ))

        if tasks:
            batch_results_list = await asyncio.gather(*tasks, return_exceptions=True)

            for batch_result in batch_results_list:
                if isinstance(batch_result, Exception):
                    logger.error(f"LLM 推断批次失败: {batch_result}")
                    continue
                results.update(batch_result)
