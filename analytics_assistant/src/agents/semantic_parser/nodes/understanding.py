# -*- coding: utf-8 -*-
"""语义理解节点"""
import logging
from datetime import datetime
from typing import Any, Optional

from langchain_core.messages import HumanMessage
from langgraph.types import RunnableConfig

from analytics_assistant.src.agents.base.node import get_llm, stream_llm_structured

from ..state import SemanticParserState
from ..components.semantic_understanding import SemanticUnderstanding, get_low_confidence_threshold
from ..schemas.output import SemanticOutput, ClarificationSource
from ..schemas.intermediate import FieldCandidate, FewShotExample

logger = logging.getLogger(__name__)

def _post_process_semantic_output(result: SemanticOutput) -> SemanticOutput:
    """后处理：检查自检结果

    如果任一置信度低于阈值，确保 potential_issues 非空。
    """
    self_check = result.self_check
    low_confidence_threshold = get_low_confidence_threshold()

    low_confidence_fields = []

    if self_check.field_mapping_confidence < low_confidence_threshold:
        low_confidence_fields.append(
            f"字段映射置信度较低 ({self_check.field_mapping_confidence:.2f})"
        )

    if self_check.time_range_confidence < low_confidence_threshold:
        low_confidence_fields.append(
            f"时间范围置信度较低 ({self_check.time_range_confidence:.2f})"
        )

    if self_check.computation_confidence < low_confidence_threshold:
        low_confidence_fields.append(
            f"计算逻辑置信度较低 ({self_check.computation_confidence:.2f})"
        )

    if self_check.overall_confidence < low_confidence_threshold:
        low_confidence_fields.append(
            f"整体置信度较低 ({self_check.overall_confidence:.2f})"
        )

    if low_confidence_fields and not self_check.potential_issues:
        self_check.potential_issues = low_confidence_fields
        result.parsing_warnings.append(
            "检测到低置信度但 LLM 未报告问题，已自动添加警告"
        )

    return result

async def semantic_understanding_node(
    state: SemanticParserState,
    config: Optional[RunnableConfig] = None,
) -> dict[str, Any]:
    """语义理解节点

    使用 modular_prompt_builder_node 构建的 Prompt 调用 LLM 进行语义理解。

    输入：
    - state["question"]: 用户问题
    - state["modular_prompt"]: 由 modular_prompt_builder_node 构建的 Prompt
    - state["chat_history"]: 对话历史（可选）

    输出：
    - semantic_output: SemanticOutput 序列化后的 dict
    - needs_clarification: 是否需要澄清
    - clarification_question: 澄清问题
    - clarification_options: 澄清选项
    - clarification_source: 澄清来源
    - thinking: LLM 思考过程
    """
    question = state.get("question", "")

    if not question:
        logger.warning("semantic_understanding_node: 问题为空")
        return {
            "needs_clarification": True,
            "clarification_question": "请输入您的问题",
            "clarification_source": ClarificationSource.SEMANTIC_UNDERSTANDING.value,
        }

    # 获取 modular_prompt_builder_node 构建的 Prompt
    modular_prompt = state.get("modular_prompt")

    if not modular_prompt:
        # 降级：如果没有 modular_prompt，使用旧的方式构建
        logger.warning(
            "semantic_understanding_node: 未找到 modular_prompt，使用降级模式"
        )
        field_candidates_raw = state.get("field_candidates", [])
        field_candidates = [
            FieldCandidate.model_validate(c) for c in field_candidates_raw
        ]

        few_shot_examples_raw = state.get("few_shot_examples", [])
        few_shot_examples = [
            FewShotExample.model_validate(e) for e in few_shot_examples_raw
        ] if few_shot_examples_raw else None

        history = state.get("chat_history")

        current_time_str = state.get("current_time")
        current_date = None
        if current_time_str:
            try:
                current_date = datetime.fromisoformat(current_time_str).date()
            except (ValueError, TypeError):
                pass

        understanding = SemanticUnderstanding()
        result = await understanding.understand(
            question=question,
            field_candidates=field_candidates,
            current_date=current_date,
            history=history,
            few_shot_examples=few_shot_examples,
            return_thinking=True,
        )
    else:
        # 正常流程：直接使用 modular_prompt 调用 LLM
        logger.info(
            f"semantic_understanding_node: 使用 modular_prompt, "
            f"prompt_length={len(modular_prompt)}"
        )

        llm = get_llm(
            agent_name="semantic_parser",
            enable_json_mode=True,
        )

        messages = [HumanMessage(content=modular_prompt)]

        on_token = None
        on_thinking = None
        if config:
            configurable = config.get("configurable", {})
            on_token = configurable.get("on_token")
            on_thinking = configurable.get("on_thinking")

        result, thinking = await stream_llm_structured(
            llm=llm,
            messages=messages,
            output_model=SemanticOutput,
            on_token=on_token,
            on_thinking=on_thinking,
            return_thinking=True,
        )

        result = _post_process_semantic_output(result)

        if result.needs_clarification:
            result.clarification_source = ClarificationSource.SEMANTIC_UNDERSTANDING

    logger.info(
        f"semantic_understanding_node: query_id={result.query_id}, "
        f"needs_clarification={result.needs_clarification}"
    )

    output = {
        "semantic_output": result.model_dump(),
        "needs_clarification": result.needs_clarification,
    }

    if result.needs_clarification:
        output["clarification_question"] = result.clarification_question
        output["clarification_options"] = result.clarification_options
        output["clarification_source"] = (
            result.clarification_source.value
            if result.clarification_source
            else ClarificationSource.SEMANTIC_UNDERSTANDING.value
        )

    return output
