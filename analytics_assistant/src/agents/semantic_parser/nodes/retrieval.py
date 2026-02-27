# -*- coding: utf-8 -*-
"""检索相关节点：字段检索、Few-shot 示例检索"""
import logging
from typing import Any, Optional

from langgraph.types import RunnableConfig

from ..state import SemanticParserState
from ..components import FieldRetriever, FewShotManager
from ..schemas.prefilter import FeatureExtractionOutput
from analytics_assistant.src.agents.base.context import get_context

logger = logging.getLogger(__name__)

async def field_retriever_node(
    state: SemanticParserState,
    config: Optional[RunnableConfig] = None,
) -> dict[str, Any]:
    """字段检索节点

    检索与问题相关的字段，并使用维度层级信息丰富结果。

    输入：
    - state["question"]: 用户问题
    - state["feature_extraction_output"]: 特征提取输出（可选）
    - config["configurable"]["workflow_context"]: WorkflowContext

    输出：
    - field_candidates: FieldCandidate 列表序列化后的 list[dict]
    """
    question = state.get("question", "")

    if not question:
        logger.warning("field_retriever_node: 问题为空")
        return {"field_candidates": []}

    # 从 config 获取 WorkflowContext
    ctx = get_context(config) if config else None
    data_model = ctx.data_model if ctx else None
    datasource_luid = ctx.datasource_luid if ctx else None

    # 获取或创建 FeatureExtractionOutput
    feature_output_raw = state.get("feature_extraction_output")
    if feature_output_raw:
        feature_output = FeatureExtractionOutput.model_validate(feature_output_raw)
    else:
        logger.debug("field_retriever_node: 未找到 feature_extraction_output，使用降级方案")
        feature_output = FeatureExtractionOutput(
            required_measures=[],
            required_dimensions=[],
            is_degraded=True,
        )

    retriever = FieldRetriever()

    # 检索字段
    rag_result = await retriever.retrieve(
        feature_output=feature_output,
        data_model=data_model,
        datasource_luid=datasource_luid,
    )

    # 合并所有候选字段
    candidates = rag_result.measures + rag_result.dimensions + rag_result.time_fields

    # 使用字段语义信息丰富字段候选（Property 28: Hierarchy Enrichment）
    if ctx and ctx.field_semantic:
        candidates = ctx.enrich_field_candidates_with_hierarchy(candidates)

    logger.info(f"field_retriever_node: 检索到 {len(candidates)} 个字段")

    return {
        "field_candidates": [c.model_dump() for c in candidates],
    }

async def few_shot_manager_node(state: SemanticParserState) -> dict[str, Any]:
    """Few-shot 示例检索节点

    输入：
    - state["question"]: 用户问题
    - state["datasource_luid"]: 数据源 ID

    输出：
    - few_shot_examples: FewShotExample 列表序列化后的 list[dict]
    """
    question = state.get("question", "")
    datasource_luid = state.get("datasource_luid", "")

    if not question or not datasource_luid:
        logger.debug("few_shot_manager_node: 缺少必要参数")
        return {"few_shot_examples": []}

    manager = FewShotManager()
    examples = await manager.retrieve(
        question=question,
        datasource_luid=datasource_luid,
        top_k=3,
    )

    logger.info(f"few_shot_manager_node: 检索到 {len(examples)} 个示例")

    return {
        "few_shot_examples": [e.model_dump() for e in examples],
    }
