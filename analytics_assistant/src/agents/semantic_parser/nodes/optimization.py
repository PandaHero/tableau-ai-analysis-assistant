# -*- coding: utf-8 -*-
"""优化相关节点：规则预处理、特征提取、动态 Schema 构建、模块化 Prompt 构建"""
import logging
import time
from datetime import datetime
from typing import Any

from ..state import SemanticParserState
from ..components import RulePrefilter, FeatureExtractor, DynamicSchemaBuilder
from ..schemas.prefilter import (
    FeatureExtractionOutput,
    PrefilterResult,
    FieldRAGResult,
    ComplexityType,
)
from ..schemas.config import SemanticConfig
from ..schemas.intermediate import FewShotExample
from ..prompts import DynamicPromptBuilder
from ..node_utils import parse_field_candidates, classify_fields, merge_metrics

logger = logging.getLogger(__name__)

async def rule_prefilter_node(state: SemanticParserState) -> dict[str, Any]:
    """规则预处理节点

    执行规则预处理，提取时间提示、计算种子、复杂度类型。
    不调用 LLM，目标 50ms 内完成。

    输入：
    - state["question"]: 用户问题
    - state["current_time"]: 当前时间（可选）

    输出：
    - prefilter_result: PrefilterResult 序列化后的 dict
    """
    start_time = time.time()

    question = state.get("question", "")

    if not question:
        logger.warning("rule_prefilter_node: 问题为空")
        return {
            "prefilter_result": PrefilterResult().model_dump(),
        }

    current_time_str = state.get("current_time")
    current_date = None
    if current_time_str:
        try:
            current_date = datetime.fromisoformat(current_time_str).date()
        except (ValueError, TypeError):
            pass

    prefilter = RulePrefilter(current_date=current_date)
    result = prefilter.prefilter(question)

    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        f"rule_prefilter_node: 完成, "
        f"time_hints={len(result.time_hints)}, "
        f"computations={len(result.matched_computations)}, "
        f"confidence={result.match_confidence:.2f}, "
        f"elapsed={elapsed_ms:.1f}ms"
    )

    return {
        "prefilter_result": result.model_dump(),
        "optimization_metrics": {
            "rule_prefilter_ms": elapsed_ms,
        },
    }

async def feature_extractor_node(state: SemanticParserState) -> dict[str, Any]:
    """特征提取节点

    使用快速 LLM 验证规则预处理结果，提取字段需求。
    500ms 超时后降级到规则结果。

    输入：
    - state["question"]: 用户问题
    - state["prefilter_result"]: 规则预处理结果

    输出：
    - feature_extraction_output: FeatureExtractionOutput 序列化后的 dict
    - is_degraded: 是否为降级模式
    """
    start_time = time.time()

    question = state.get("question", "")
    prefilter_result_raw = state.get("prefilter_result")

    if not question:
        logger.warning("feature_extractor_node: 问题为空")
        return {
            "feature_extraction_output": FeatureExtractionOutput(is_degraded=True).model_dump(),
            "is_degraded": True,
        }

    if prefilter_result_raw:
        prefilter_result = PrefilterResult.model_validate(prefilter_result_raw)
    else:
        prefilter_result = PrefilterResult()

    extractor = FeatureExtractor()
    result = await extractor.extract(question, prefilter_result)

    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        f"feature_extractor_node: 完成, "
        f"measures={len(result.required_measures)}, "
        f"dimensions={len(result.required_dimensions)}, "
        f"is_degraded={result.is_degraded}, "
        f"elapsed={elapsed_ms:.1f}ms"
    )

    return {
        "feature_extraction_output": result.model_dump(),
        "is_degraded": result.is_degraded,
        "optimization_metrics": merge_metrics(state, feature_extractor_ms=elapsed_ms),
    }

async def dynamic_schema_builder_node(state: SemanticParserState) -> dict[str, Any]:
    """动态 Schema 构建节点

    根据 ComplexityType 精确裁剪 Schema，生成 schema_text。

    输入：
    - state["feature_extraction_output"]: 特征提取输出
    - state["field_candidates"]: 字段候选列表
    - state["prefilter_result"]: 规则预处理结果

    输出：
    - dynamic_schema_result: DynamicSchemaResult 序列化后的 dict
    - field_candidates: 更新后的字段候选列表（已裁剪）
    """
    start_time = time.time()

    feature_output_raw = state.get("feature_extraction_output")
    field_candidates_raw = state.get("field_candidates", [])
    prefilter_result_raw = state.get("prefilter_result")

    feature_output = None
    if feature_output_raw:
        feature_output = FeatureExtractionOutput.model_validate(feature_output_raw)

    prefilter_result = None
    if prefilter_result_raw:
        prefilter_result = PrefilterResult.model_validate(prefilter_result_raw)

    field_candidates = parse_field_candidates(field_candidates_raw)
    classified = classify_fields(field_candidates)

    field_rag_result = FieldRAGResult(
        measures=classified["measures"],
        dimensions=classified["dimensions"],
        time_fields=classified["time_fields"],
    )

    builder = DynamicSchemaBuilder()
    result = builder.build(
        feature_output=feature_output,
        field_rag_result=field_rag_result,
        prefilter_result=prefilter_result,
    )

    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        f"dynamic_schema_builder_node: 完成, "
        f"complexity={[c.value for c in result.detected_complexity]}, "
        f"schema_json_len={len(result.schema_text)}, "
        f"field_count={len(result.field_candidates)}, "
        f"elapsed={elapsed_ms:.1f}ms"
    )

    return {
        "dynamic_schema_result": {
            "field_candidates": [c.model_dump() for c in result.field_candidates],
            "schema_text": result.schema_text,
            "modules": list(result.modules),
            "detected_complexity": [c.value for c in result.detected_complexity],
            "allowed_calc_types": result.allowed_calc_types,
            "time_expressions": result.time_expressions,
        },
        "field_candidates": [c.model_dump() for c in result.field_candidates],
        "optimization_metrics": merge_metrics(state, dynamic_schema_builder_ms=elapsed_ms),
    }

async def modular_prompt_builder_node(state: SemanticParserState) -> dict[str, Any]:
    """模块化 Prompt 构建节点

    使用 DynamicSchemaBuilder 输出的 schema_text 构建 Prompt。

    输入：
    - state["question"]: 用户问题
    - state["dynamic_schema_result"]: DynamicSchemaBuilder 的输出
    - state["field_candidates"]: 字段候选列表（已裁剪）
    - state["prefilter_result"]: 规则预处理结果
    - state["feature_extraction_output"]: 特征提取输出
    - state["few_shot_examples"]: Few-shot 示例
    - state["current_time"]: 当前时间
    - state["chat_history"]: 对话历史

    输出：
    - modular_prompt: 构建好的 Prompt 字符串
    """
    start_time = time.time()

    question = state.get("question", "")
    dynamic_schema_result_raw = state.get("dynamic_schema_result")
    field_candidates_raw = state.get("field_candidates", [])
    prefilter_result_raw = state.get("prefilter_result")
    feature_output_raw = state.get("feature_extraction_output")
    few_shot_examples_raw = state.get("few_shot_examples", [])
    current_time_str = state.get("current_time")
    chat_history = state.get("chat_history")

    field_candidates = parse_field_candidates(field_candidates_raw)

    few_shot_examples = [
        FewShotExample.model_validate(e) for e in few_shot_examples_raw
    ] if few_shot_examples_raw else None

    current_date = None
    if current_time_str:
        try:
            current_date = datetime.fromisoformat(current_time_str).date()
        except (ValueError, TypeError):
            pass

    config = SemanticConfig(
        current_date=current_date or datetime.now().date(),
    )

    prefilter_result = None
    if prefilter_result_raw:
        prefilter_result = PrefilterResult.model_validate(prefilter_result_raw)

    feature_output = None
    if feature_output_raw:
        feature_output = FeatureExtractionOutput.model_validate(feature_output_raw)

    schema_text = ""
    detected_complexity = [ComplexityType.SIMPLE]
    allowed_calc_types = []

    if dynamic_schema_result_raw:
        schema_text = dynamic_schema_result_raw.get("schema_text", "")
        detected_complexity = [
            ComplexityType(c) for c in dynamic_schema_result_raw.get("detected_complexity", ["simple"])
        ]
        allowed_calc_types = dynamic_schema_result_raw.get("allowed_calc_types", [])

    prompt_builder = DynamicPromptBuilder()
    prompt = prompt_builder.build(
        question=question,
        config=config,
        field_candidates=field_candidates,
        schema_json=schema_text,
        detected_complexity=detected_complexity,
        allowed_calc_types=allowed_calc_types,
        history=chat_history,
        few_shot_examples=few_shot_examples,
        prefilter_result=prefilter_result,
        feature_output=feature_output,
    )

    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        f"modular_prompt_builder_node: 完成, "
        f"complexity={[c.value for c in detected_complexity]}, "
        f"prompt_length={len(prompt)}, "
        f"elapsed={elapsed_ms:.1f}ms"
    )

    return {
        "modular_prompt": prompt,
        "optimization_metrics": merge_metrics(state, modular_prompt_builder_ms=elapsed_ms),
    }
