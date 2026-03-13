# -*- coding: utf-8 -*-
"""查询适配节点。"""

import logging
from typing import Any, Optional

from langgraph.types import RunnableConfig

from ..query_contract import build_compiler_input_contract
from ..schemas.output import SemanticOutput
from ..state import SemanticParserState

logger = logging.getLogger(__name__)


async def query_adapter_node(
    state: SemanticParserState,
    config: Optional[RunnableConfig] = None,
) -> dict[str, Any]:
    """把结构化语义输出适配成编译器输入契约。"""
    del config
    semantic_output_raw = state.get("semantic_output")

    if not semantic_output_raw:
        logger.warning("query_adapter_node: 缺少 semantic_output")
        return {
            "pipeline_error": {
                "error_type": "missing_input",
                "message": "缺少 semantic_output",
                "is_retryable": False,
            }
        }

    semantic_output = SemanticOutput.model_validate(semantic_output_raw)
    logger.info("query_adapter_node: 返回 compiler_input 契约，查询阶段统一由编译器构建")
    return {
        "semantic_query": build_compiler_input_contract(semantic_output),
    }
