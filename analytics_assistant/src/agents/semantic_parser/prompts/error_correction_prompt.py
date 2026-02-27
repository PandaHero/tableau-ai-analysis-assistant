# -*- coding: utf-8 -*-
"""
错误修正 Prompt 定义

分为系统提示和用户提示：
- SYSTEM_PROMPT: 定义任务、规则、输出格式
- build_user_prompt(): 构建用户输入（错误信息 + 上下文）
"""
from typing import Optional

# ══════════════════════════════════════════════════════════════
# 系统提示
# ══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """你是一个语义解析修正助手。之前的语义解析结果在执行时出现了错误，请根据错误信息修正输出。

## 任务
根据执行错误信息修正之前的语义解析输出。

## 修正流程
1. 分析错误类型和详情
2. 定位问题字段或计算逻辑
3. 参考可用字段列表进行修正
4. 输出修正后的完整 JSON

## 修正原则
- 只修正有问题的部分，保持其他部分不变
- 优先使用错误信息中提示的正确值
- 如果有可用字段列表，从中选择最匹配的字段
- 确保修正后的输出符合 SemanticOutput 格式

## 输出格式
返回修正后的完整 SemanticOutput JSON。"""

# ══════════════════════════════════════════════════════════════
# 错误类型专用指导
# ══════════════════════════════════════════════════════════════

ERROR_TYPE_GUIDANCE = {
    "field_not_found": """
- 错误原因：使用了不存在的字段
- 请检查 what.measures 和 where.dimensions 中的字段名
- 从可用字段列表中选择最匹配的字段替换""",
    
    "syntax_error": """
- 错误原因：生成的查询语法有误
- 请检查 computations 中的公式是否正确
- 确保字段引用格式正确：[字段名]""",
    
    "invalid_filter_value": """
- 错误原因：筛选值不存在
- 请从有效值列表中选择正确的值
- 修正 where.filters 中的筛选值""",
    
    "type_mismatch": """
- 错误原因：字段类型不匹配
- 检查度量字段是否为数值类型
- 检查维度字段是否用于分组""",
    
    "computation_error": """
- 错误原因：计算表达式有误
- 检查 computations 中的公式语法
- 确保引用的字段存在且类型正确""",
}

# ══════════════════════════════════════════════════════════════
# 用户提示构建
# ══════════════════════════════════════════════════════════════

def build_user_prompt(
    question: str,
    previous_output: str,
    error_type: str,
    error_info: str,
    context: Optional[dict] = None,
) -> str:
    """构建用户提示
    
    Args:
        question: 原始用户问题
        previous_output: 之前的输出（JSON 字符串）
        error_type: 错误类型
        error_info: 错误详情
        context: 额外上下文（如可用字段列表、有效值列表等）
        
    Returns:
        用户提示字符串
    """
    context = context or {}
    
    parts = [
        "## 原始问题",
        question,
        "",
        "## 之前的输出",
        "```json",
        previous_output,
        "```",
        "",
        "## 错误信息",
        f"错误类型: {error_type}",
        f"错误详情: {error_info}",
    ]
    
    # 添加错误类型专用指导
    guidance = ERROR_TYPE_GUIDANCE.get(error_type)
    if guidance:
        parts.append("")
        parts.append("## 修正指南")
        parts.append(guidance.strip())
    
    # 根据错误类型添加上下文信息
    if error_type == "field_not_found" and "available_fields" in context:
        available_fields = context["available_fields"]
        parts.append("")
        parts.append("## 可用字段")
        # 限制显示数量，避免 prompt 过长
        display_fields = available_fields[:30]
        parts.append(str(display_fields))
        if len(available_fields) > 30:
            parts.append(f"... 共 {len(available_fields)} 个字段")
    
    if error_type == "invalid_filter_value" and "valid_values" in context:
        valid_values = context["valid_values"]
        parts.append("")
        parts.append("## 有效值列表")
        display_values = valid_values[:20]
        parts.append(str(display_values))
        if len(valid_values) > 20:
            parts.append(f"... 共 {len(valid_values)} 个有效值")
    
    # 添加错误历史（如果有）
    if "error_history" in context and context["error_history"]:
        parts.append("")
        parts.append("## 之前的修正尝试")
        for i, hist in enumerate(context["error_history"][-3:], 1):
            parts.append(f"{i}. 错误类型: {hist.get('error_type', 'unknown')}")
            if hist.get("correction_applied"):
                parts.append(f"   修正: {hist['correction_applied'][:50]}")
    
    parts.append("")
    parts.append("请输出修正后的完整 SemanticOutput JSON。")
    
    return "\n".join(parts)

def get_system_prompt() -> str:
    """获取系统提示"""
    return SYSTEM_PROMPT

__all__ = [
    "SYSTEM_PROMPT",
    "ERROR_TYPE_GUIDANCE",
    "build_user_prompt",
    "get_system_prompt",
]
