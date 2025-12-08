"""
维度层级推断 Agent

功能：
1. 根据字段元数据推断维度层级
2. 识别维度的 category、level、granularity
3. 识别父子关系
4. RAG 增强：复用历史推断结果作为 few-shot 示例

使用 base 包提供的基础能力：
- get_llm(): 获取 LLM 实例
- stream_llm_call(): 流式调用 LLM
- invoke_llm(): 非流式调用 LLM
- parse_json_response(): 解析 JSON 响应

输出：DimensionHierarchyResult 模型
"""
import json
import logging
from typing import Dict, Any, List, Optional

from tableau_assistant.src.models.metadata import Metadata
from tableau_assistant.src.models.dimension_hierarchy import (
    DimensionHierarchyResult,
    DimensionAttributes,
)
from tableau_assistant.src.agents.base import (
    get_llm,
    stream_llm_call,
    invoke_llm,
    parse_json_response,
)
from .prompt import DIMENSION_HIERARCHY_PROMPT

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# RAG 辅助函数
# ═══════════════════════════════════════════════════════════════════════════

def _get_dimension_rag():
    """延迟加载 DimensionHierarchyRAG 组件"""
    try:
        from tableau_assistant.src.capabilities.rag.dimension_pattern import (
            DimensionHierarchyRAG,
        )
        return DimensionHierarchyRAG()
    except Exception as e:
        logger.warning(f"无法加载 DimensionHierarchyRAG: {e}")
        return None


def _build_few_shot_section(few_shot_examples: List[str]) -> str:
    """构建 few-shot 示例部分"""
    if not few_shot_examples:
        return ""

    section = """**Historical Reference Examples (from similar fields):**

The following are inference results from similar fields in the past. Use them as reference:

"""
    for i, example in enumerate(few_shot_examples[:3], 1):
        section += f"Example {i}:\n{example}\n\n"

    return section


def _prepare_dimensions_info(
    metadata: Metadata, rag=None
) -> tuple[List[Dict[str, Any]], str]:
    """
    准备维度字段信息，并获取 RAG few-shot 示例
    
    Returns:
        (维度信息列表, few_shot_section)
    """
    dimension_fields = metadata.get_dimensions()

    if not dimension_fields:
        return [], ""

    dimension_info = []
    all_few_shot_examples = []

    for field in dimension_fields:
        info = {
            "name": field.name,
            "caption": field.fieldCaption,
            "dataType": field.dataType,
            "description": field.description or "",
            "unique_count": field.unique_count or 0,
            "sample_values": (field.sample_values or [])[:5],
        }
        dimension_info.append(info)

        # RAG: 获取相似历史模式
        if rag:
            try:
                rag_context = rag.get_inference_context(
                    field_caption=field.fieldCaption,
                    data_type=field.dataType,
                    sample_values=field.sample_values or [],
                    unique_count=field.unique_count or 0,
                )

                if rag_context.get("has_similar_patterns"):
                    examples = rag_context.get("few_shot_examples", [])[:2]
                    all_few_shot_examples.extend(examples)
                    logger.debug(
                        f"RAG: 字段 '{field.fieldCaption}' 找到 {len(examples)} 个相似模式"
                    )
            except Exception as e:
                logger.warning(f"RAG 检索失败: {e}")

    # 构建 few-shot section（最多 5 个示例）
    few_shot_section = _build_few_shot_section(all_few_shot_examples[:5])

    return dimension_info, few_shot_section


def _store_inference_results(
    result: DimensionHierarchyResult,
    metadata: Metadata,
    rag,
    datasource_luid: Optional[str] = None,
) -> None:
    """存储推断结果到 RAG（用于未来检索）"""
    if not rag:
        return

    try:
        stored_count = 0
        skipped_count = 0

        for field_name, attrs in result.dimension_hierarchy.items():
            confidence = attrs.level_confidence

            # 跳过置信度为 0 的结果
            if confidence <= 0:
                skipped_count += 1
                continue

            # 查找字段元数据
            field = None
            for f in metadata.get_dimensions():
                if f.name == field_name:
                    field = f
                    break

            if not field:
                skipped_count += 1
                continue

            try:
                rag.store_inference_result(
                    field_name=field_name,
                    field_caption=field.fieldCaption,
                    data_type=field.dataType,
                    sample_values=field.sample_values or [],
                    unique_count=field.unique_count or 0,
                    category=attrs.category,
                    category_detail=attrs.category_detail,
                    level=attrs.level,
                    granularity=attrs.granularity,
                    reasoning=attrs.reasoning,
                    confidence=confidence,
                    datasource_luid=datasource_luid,
                )
                stored_count += 1
            except Exception as e:
                logger.debug(f"存储推断结果失败: {field_name}, {e}")
                skipped_count += 1

        if stored_count > 0:
            logger.info(f"RAG: 存储了 {stored_count} 个推断结果 (跳过 {skipped_count} 个)")

    except Exception as e:
        logger.warning(f"存储推断结果到 RAG 失败: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# 主节点函数
# ═══════════════════════════════════════════════════════════════════════════

async def dimension_hierarchy_node(
    metadata: Metadata,
    datasource_luid: Optional[str] = None,
    stream: bool = True
) -> DimensionHierarchyResult:
    """
    维度层级推断节点
    
    使用统一的 execute_agent() API 执行推断。
    
    Args:
        metadata: Metadata 对象（包含字段元数据）
        datasource_luid: 数据源 LUID（可选，用于 RAG 存储）
        stream: 是否流式输出（默认 True）
    
    Returns:
        DimensionHierarchyResult 模型对象
    
    流程：
        1. 加载 RAG 组件
        2. 准备维度信息 + RAG few-shot 示例
        3. 调用 execute_agent() 执行推断
        4. 存储结果到 RAG
        5. 返回结果
    """
    logger.info("维度层级推断开始")

    # 1. 加载 RAG 组件
    rag = _get_dimension_rag()
    if rag:
        logger.info("RAG 组件已加载")

    # 2. 准备维度信息 + RAG few-shot 示例
    dimensions_info, few_shot_section = _prepare_dimensions_info(metadata, rag)

    if not dimensions_info:
        logger.warning("未找到维度字段")
        return DimensionHierarchyResult(dimension_hierarchy={})

    logger.info(
        f"推断 {len(dimensions_info)} 个维度的层级, "
        f"RAG 示例: {'有' if few_shot_section else '无'}"
    )

    # 3. 构建输入数据
    dimensions_str = json.dumps(dimensions_info, ensure_ascii=False, indent=2)
    if few_shot_section:
        dimensions_str = few_shot_section + "\n" + dimensions_str

    input_data = {"dimensions": dimensions_str}

    # 4. 调用 LLM 执行推断
    try:
        # 获取 LLM
        llm = get_llm(agent_name="dimension_hierarchy")
        
        # 格式化消息
        messages = DIMENSION_HIERARCHY_PROMPT.format_messages(**input_data)
        
        # 流式调用 LLM
        if stream:
            response = await stream_llm_call(llm, messages, print_output=True)
        else:
            response = await invoke_llm(llm, messages)
        
        # 解析结果
        from tableau_assistant.src.models.dimension_hierarchy import DimensionHierarchyResult
        result = parse_json_response(response, DimensionHierarchyResult)

        # 计算平均置信度
        confidences = [
            attrs.level_confidence for attrs in result.dimension_hierarchy.values()
        ]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        logger.info(
            f"维度层级推断完成: "
            f"{len(result.dimension_hierarchy)} 个维度, "
            f"平均置信度: {avg_confidence:.2f}"
        )

        # 输出每个维度的推断结果
        for field_name, attrs in result.dimension_hierarchy.items():
            logger.info(
                f"  → {field_name}: {attrs.category_detail} "
                f"L{attrs.level}({attrs.granularity}) "
                f"conf={attrs.level_confidence:.2f}"
            )

        # 5. 存储结果到 RAG
        _store_inference_results(result, metadata, rag, datasource_luid)

        return result

    except Exception as e:
        logger.error(f"维度层级推断失败: {e}", exc_info=True)
        return DimensionHierarchyResult(dimension_hierarchy={})


__all__ = ["dimension_hierarchy_node"]
