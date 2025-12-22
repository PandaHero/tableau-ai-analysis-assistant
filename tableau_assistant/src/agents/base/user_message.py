# -*- coding: utf-8 -*-
"""
用户友好消息生成器

为每个节点生成用户友好的流式输出消息。
这些消息会通过 LLM 流式输出，让用户知道系统正在做什么。

设计原则：
1. 每个节点都有对应的消息生成函数
2. 消息简洁明了，让用户理解当前进度
3. 支持流式输出（通过 LLM astream_events）
"""

import logging
from typing import Dict, Any, Optional, List, AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


# 节点消息模板
NODE_MESSAGE_TEMPLATES = {
    "semantic_parser": {
        "start": "🔍 正在理解您的问题...",
        "template": """请用简洁的中文（1-2句话）向用户解释你对问题的理解。

用户问题：{question}
重述问题：{restated_question}
分析维度：{dimensions}
分析指标：{measures}

要求：
- 用"我理解您想..."开头
- 说明要分析什么指标、按什么维度
- 不要使用技术术语
- 不要输出JSON""",
    },
    "field_mapper": {
        "start": "🔗 正在匹配数据字段...",
        "template": """请用简洁的中文（1句话）向用户说明字段匹配结果。

业务术语到字段的映射：
{mappings}

要求：
- 用"已将..."开头
- 简单说明映射了哪些字段
- 不要使用技术术语
- 不要输出JSON""",
    },
    "query_builder": {
        "start": "🔨 正在构建查询...",
        "template": """请用简洁的中文（1句话）向用户说明正在构建的查询。

查询包含：
- 维度字段：{dimensions}
- 度量字段：{measures}
- 计算字段：{computations}

要求：
- 用"正在查询..."开头
- 简单说明查询什么数据
- 不要使用技术术语
- 不要输出JSON""",
    },
    "execute": {
        "start": "⚡ 正在执行查询...",
        "success_template": """请用简洁的中文（1句话）向用户说明查询结果。

查询结果：
- 返回 {row_count} 条数据
- 字段：{columns}

要求：
- 用"查询完成，..."开头
- 说明获取了多少数据
- 不要使用技术术语
- 不要输出JSON""",
        "error_template": """请用简洁友好的中文（1句话）向用户解释查询失败的原因。

错误信息：{error}

要求：
- 用"抱歉，..."开头
- 给出简单易懂的解释
- 如果可能，给出建议
- 不要暴露技术细节
- 不要输出JSON""",
    },
    "insight": {
        "start": "💡 正在分析数据...",
        "template": """请根据分析结果，用自然流畅的中文回答用户的问题。

用户问题：{question}
分析结果摘要：{summary}
关键发现：
{findings}

要求：
- 直接回答用户的问题
- 用数据支撑你的回答
- 语言自然流畅，像在和用户对话
- 如果有多个发现，按重要性排序
- 不要使用技术术语
- 不要输出JSON""",
    },
    "replanner": {
        "start": "🤔 正在思考后续分析...",
        "template": """请用简洁的中文向用户推荐可以继续探索的问题。

当前分析的问题：{question}
已分析的维度：{analyzed_dimensions}
推荐的后续问题：
{suggestions}

要求：
- 用"您可能还想了解..."开头
- 列出2-3个推荐问题
- 问题要有价值且相关
- 不要输出JSON""",
    },
}


async def generate_user_message_stream(
    node_name: str,
    data: Dict[str, Any],
    llm: Any,
) -> AsyncIterator[str]:
    """
    为指定节点生成用户友好的流式消息
    
    Args:
        node_name: 节点名称
        data: 节点输出数据
        llm: LLM 实例
        
    Yields:
        流式输出的 token
    """
    template_config = NODE_MESSAGE_TEMPLATES.get(node_name)
    if not template_config:
        logger.warning(f"No message template for node: {node_name}")
        return
    
    # 选择合适的模板
    if node_name == "execute":
        # 检查错误：可能在 data["error"] 或 data["query_result"].error 中
        has_error = bool(data.get("error"))
        if not has_error:
            query_result = data.get("query_result")
            if query_result:
                if hasattr(query_result, "error") and query_result.error:
                    has_error = True
                elif isinstance(query_result, dict) and query_result.get("error"):
                    has_error = True
        
        if has_error:
            template = template_config["error_template"]
        else:
            template = template_config["success_template"]
    else:
        template = template_config.get("template", "")
    
    if not template:
        return
    
    # 格式化模板
    try:
        prompt = _format_template(node_name, template, data)
    except Exception as e:
        logger.error(f"Failed to format template for {node_name}: {e}")
        return
    
    # 流式调用 LLM
    messages = [
        SystemMessage(content="你是一个友好的数据分析助手，正在向用户解释分析过程。请用简洁自然的中文回复。"),
        HumanMessage(content=prompt),
    ]
    
    try:
        async for event in llm.astream_events(messages, version="v2"):
            if event.get("event") == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    yield chunk.content
    except Exception as e:
        logger.error(f"LLM streaming failed for {node_name}: {e}")
        # 回退到静态消息
        yield template_config.get("start", f"正在处理 {node_name}...")


def _format_template(node_name: str, template: str, data: Dict[str, Any]) -> str:
    """格式化消息模板"""
    
    if node_name == "semantic_parser":
        semantic_query = data.get("semantic_query")
        dims = []
        measures = []
        if semantic_query:
            dims = [d.field_name for d in (semantic_query.dimensions or [])]
            measures = [m.field_name for m in (semantic_query.measures or [])]
        
        return template.format(
            question=data.get("question", ""),
            restated_question=data.get("restated_question", ""),
            dimensions=", ".join(dims) if dims else "无",
            measures=", ".join(measures) if measures else "无",
        )
    
    elif node_name == "field_mapper":
        mapped_query = data.get("mapped_query")
        mappings = []
        if mapped_query and hasattr(mapped_query, "field_mappings"):
            for term, mapping in mapped_query.field_mappings.items():
                tech_field = mapping.technical_field if hasattr(mapping, "technical_field") else mapping
                mappings.append(f"'{term}' → '{tech_field}'")
        
        return template.format(
            mappings="\n".join(mappings) if mappings else "无映射",
        )
    
    elif node_name == "query_builder":
        vizql_query = data.get("vizql_query")
        dims = []
        measures = []
        computations = []
        
        if vizql_query and hasattr(vizql_query, "fields"):
            for field in vizql_query.fields:
                if isinstance(field, dict):
                    name = field.get("fieldCaption", "")
                    if field.get("tableCalculation"):
                        computations.append(name)
                    elif field.get("function"):
                        measures.append(name)
                    else:
                        dims.append(name)
        
        return template.format(
            dimensions=", ".join(dims) if dims else "无",
            measures=", ".join(measures) if measures else "无",
            computations=", ".join(computations) if computations else "无",
        )
    
    elif node_name == "execute":
        # 检查错误：可能在 data["error"] 或 data["query_result"].error 中
        error = data.get("error")
        query_result = data.get("query_result")
        
        # 从 query_result 中提取错误
        if not error and query_result:
            if hasattr(query_result, "error") and query_result.error:
                error = query_result.error
            elif isinstance(query_result, dict) and query_result.get("error"):
                error = query_result.get("error")
        
        if error:
            return template.format(error=error)
        else:
            row_count = 0
            columns = []
            if query_result:
                if hasattr(query_result, "data"):
                    row_count = len(query_result.data) if query_result.data else 0
                elif isinstance(query_result, dict):
                    row_count = len(query_result.get("data", [])) if query_result.get("data") else 0
                    
                if hasattr(query_result, "columns"):
                    columns = [c.get("label", c.get("key", "")) for c in (query_result.columns or [])]
                elif isinstance(query_result, dict) and query_result.get("columns"):
                    columns = [c.get("label", c.get("key", "")) for c in (query_result.get("columns") or [])]
            
            return template.format(
                row_count=row_count,
                columns=", ".join(columns[:5]) if columns else "无",
            )
    
    elif node_name == "insight":
        insight_result = data.get("insight_result")
        summary = ""
        findings = []
        
        if insight_result:
            summary = insight_result.summary if hasattr(insight_result, "summary") else ""
            if hasattr(insight_result, "findings"):
                for f in (insight_result.findings or [])[:5]:
                    title = f.title if hasattr(f, "title") else str(f)
                    desc = f.description if hasattr(f, "description") else ""
                    findings.append(f"- {title}: {desc}")
        
        return template.format(
            question=data.get("question", ""),
            summary=summary or "无摘要",
            findings="\n".join(findings) if findings else "- 无显著发现",
        )
    
    elif node_name == "replanner":
        replan_decision = data.get("replan_decision")
        suggestions = []
        analyzed_dims = data.get("current_dimensions", [])
        
        if replan_decision and hasattr(replan_decision, "suggested_questions"):
            suggestions = replan_decision.suggested_questions or []
        
        return template.format(
            question=data.get("question", ""),
            analyzed_dimensions=", ".join(analyzed_dims) if analyzed_dims else "无",
            suggestions="\n".join([f"- {s}" for s in suggestions[:3]]) if suggestions else "- 无推荐",
        )
    
    return template


def get_node_start_message(node_name: str) -> str:
    """获取节点开始时的静态消息"""
    template_config = NODE_MESSAGE_TEMPLATES.get(node_name, {})
    return template_config.get("start", f"正在处理 {node_name}...")
