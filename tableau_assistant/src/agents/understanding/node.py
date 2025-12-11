"""
Understanding Agent Node（含原 Boost 功能）

职责：
- 问题分类：判断是否为分析类问题（is_analysis_question）
- 元数据获取：调用 get_metadata 工具获取字段信息（原 Boost 功能）
- 语义理解：理解用户问题的语义
- 输出 SemanticQuery：纯语义，无 VizQL 概念

使用 base 包提供的基础能力：
- get_llm(): 获取 LLM 实例
- call_llm_with_tools(): 带工具调用的 LLM 调用
- parse_json_response(): 解析 JSON 响应

Requirements:
- R2.9: Understanding Agent 调用 get_metadata 工具获取字段信息
- R7.2.1: 输出 SemanticQuery（纯语义）
- R7.2.2: 使用 XML 格式的字段描述
- R7.2.3: 实现决策树和填写顺序
- R7.2.4: 实现 model_validator 验证依赖关系
"""
import logging
from datetime import datetime
from typing import Dict, Any

from langgraph.types import RunnableConfig

from tableau_assistant.src.models.semantic.query import SemanticQuery
from tableau_assistant.src.tools.metadata_tool import get_metadata
from tableau_assistant.src.tools.date_tool import process_time_filter, calculate_relative_dates, detect_date_format
from tableau_assistant.src.tools.schema_tool import get_schema_module
from tableau_assistant.src.agents.base import (
    get_llm,
    call_llm_with_tools,
    parse_json_response,
)
from .prompt import UNDERSTANDING_PROMPT

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════════

def _is_analysis_question(question: str) -> bool:
    """
    判断是否为分析类问题
    
    分析类问题：关于数据、趋势、比较、聚合的查询
    非分析类问题：问候、帮助请求、系统问题
    
    Args:
        question: 用户问题
    
    Returns:
        是否为分析类问题
    """
    # 非分析类关键词
    non_analysis_keywords = [
        "你好", "您好", "hi", "hello", "帮助", "help",
        "怎么用", "如何使用", "使用方法", "功能",
        "谢谢", "感谢", "再见", "bye",
        "你是谁", "你能做什么", "介绍一下",
    ]
    
    question_lower = question.lower().strip()
    
    # 检查是否包含非分析类关键词
    for keyword in non_analysis_keywords:
        if keyword in question_lower:
            return False
    
    # 分析类关键词
    analysis_keywords = [
        "销售", "利润", "收入", "数量", "金额", "成本",
        "趋势", "对比", "比较", "排名", "占比", "累计",
        "多少", "几个", "平均", "总", "最高", "最低",
        "按", "各", "每", "分", "统计", "分析",
        "年", "月", "季度", "周", "日",
        "地区", "省份", "城市", "产品", "类别", "客户",
    ]
    
    # 检查是否包含分析类关键词
    for keyword in analysis_keywords:
        if keyword in question_lower:
            return True
    
    # 默认认为是分析类问题（保守策略）
    return True


def _format_metadata_summary(metadata: Any) -> str:
    """
    格式化元数据摘要
    
    Args:
        metadata: 元数据对象
    
    Returns:
        格式化的元数据摘要字符串
    """
    if metadata is None:
        return "No metadata available"
    
    if isinstance(metadata, str):
        return metadata
    
    if hasattr(metadata, 'fields'):
        fields = metadata.fields
        dimensions = [f for f in fields if getattr(f, 'role', '').upper() == 'DIMENSION']
        measures = [f for f in fields if getattr(f, 'role', '').upper() == 'MEASURE']
        
        lines = []
        lines.append(f"Dimensions ({len(dimensions)}): " + ", ".join(
            getattr(f, 'fieldCaption', getattr(f, 'name', str(f))) for f in dimensions[:10]
        ))
        if len(dimensions) > 10:
            lines.append(f"  ... and {len(dimensions) - 10} more")
        
        lines.append(f"Measures ({len(measures)}): " + ", ".join(
            getattr(f, 'fieldCaption', getattr(f, 'name', str(f))) for f in measures[:10]
        ))
        if len(measures) > 10:
            lines.append(f"  ... and {len(measures) - 10} more")
        
        return "\n".join(lines)
    
    return str(metadata)


# ═══════════════════════════════════════════════════════════════════════════
# Understanding Node
# ═══════════════════════════════════════════════════════════════════════════

async def understanding_node(
    state: Dict[str, Any],
    config: RunnableConfig | None = None
) -> Dict[str, Any]:
    """
    Understanding Agent 节点（含原 Boost 功能）
    
    流程：
    1. 调用 get_metadata 获取元数据（原 Boost 功能）
    2. 判断是否为分析类问题（is_analysis_question）
    3. 如果不是分析类问题，直接返回
    4. 构建 Prompt（包含思考步骤）
    5. LLM 分析问题，调用工具获取需要的信息
    6. LLM 根据 Schema 的 <decision_rule> 生成 SemanticQuery
    
    Args:
        state: 当前状态，包含 question 等字段
        config: 运行时配置
    
    Returns:
        状态更新，包含：
        - semantic_query: SemanticQuery 对象（如果是分析类问题）
        - is_analysis_question: 是否为分析类问题
        - understanding_complete: 理解是否完成
        - current_question: 当前问题
    
    **Validates: Requirements 2.9, 7.2.1, 7.2.2, 7.2.3, 7.2.4**
    """
    logger.info("Understanding node started")
    
    # 获取当前问题
    current_question = state.get("question", "")
    if not current_question:
        logger.warning("No question provided")
        return {
            "semantic_query": None,
            "is_analysis_question": False,
            "understanding_complete": True,
            "current_question": "",
            "error": "No question provided",
        }
    
    # Step 0: 问题分类（快速判断）
    is_analysis = _is_analysis_question(current_question)
    
    if not is_analysis:
        logger.info(f"Non-analysis question detected: {current_question[:50]}...")
        return {
            "semantic_query": None,
            "is_analysis_question": False,
            "understanding_complete": True,
            "current_question": current_question,
            "non_analysis_response": "您好！我是数据分析助手，可以帮您分析数据、查看趋势、对比指标等。请问您想了解什么数据？",
        }
    
    # Step 1: 获取元数据（原 Boost 功能）
    # **Validates: Requirements 2.9**
    metadata = state.get("metadata")
    metadata_summary = _format_metadata_summary(metadata)
    
    # Step 2: 构建 Prompt
    prompt = UNDERSTANDING_PROMPT
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    messages = prompt.format_messages(
        question=current_question,
        metadata_summary=metadata_summary,
        current_date=current_date,
    )
    
    # Step 3: 调用 LLM（带工具）
    # 使用 base 包的 get_llm 和 call_llm_with_tools
    llm = get_llm(agent_name="understanding")
    tools = [get_metadata, get_schema_module, process_time_filter, calculate_relative_dates, detect_date_format]
    
    try:
        response_content = await call_llm_with_tools(llm, messages, tools)
        
        # Step 4: 解析 SemanticQuery
        # 使用 base 包的 parse_json_response
        # **Validates: Requirements 7.2.1, 7.2.2, 7.2.3, 7.2.4**
        try:
            semantic_query = parse_json_response(response_content, SemanticQuery)
        except ValueError as e:
            logger.error(f"Failed to parse SemanticQuery: {e}")
            return {
                "semantic_query": None,
                "is_analysis_question": True,
                "understanding_complete": False,
                "current_question": current_question,
                "error": str(e),
            }
        
        logger.info(f"Understanding complete: {len(semantic_query.measures)} measures, "
                   f"{len(semantic_query.dimensions)} dimensions, "
                   f"{len(semantic_query.analyses)} analyses")
        
        return {
            "semantic_query": semantic_query,
            "is_analysis_question": True,
            "understanding_complete": True,
            "current_question": current_question,
        }
        
    except Exception as e:
        logger.error(f"Understanding node failed: {e}", exc_info=True)
        return {
            "semantic_query": None,
            "is_analysis_question": True,
            "understanding_complete": False,
            "current_question": current_question,
            "error": str(e),
        }


__all__ = [
    "understanding_node",
]
