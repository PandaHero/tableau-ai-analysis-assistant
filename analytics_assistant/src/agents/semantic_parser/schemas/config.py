# -*- coding: utf-8 -*-
"""
Semantic Parser 运行时上下文模型

注意：这不是配置文件！配置参数应放在 app.yaml 中。
此文件定义的是运行时传递的上下文数据结构。

SemanticConfig 用于在调用时传递动态参数（如当前日期），
其默认值从 app.yaml 读取。
"""
from datetime import date

from pydantic import BaseModel, ConfigDict

class SemanticConfig(BaseModel):
    """语义解析运行时上下文
    
    用于 DynamicPromptBuilder 构建 Prompt 时的运行时参数。
    
    注意：这是运行时上下文，不是配置！
    - current_date: 每次调用时的当前日期（动态值）
    - timezone/fiscal_year_start_month: 默认值从 app.yaml 读取
    
    Attributes:
        current_date: 当前日期（必填，每次调用时传入）
        timezone: 时区（默认从 app.yaml 读取）
        fiscal_year_start_month: 财年起始月份（默认从 app.yaml 读取）
        max_schema_tokens: Schema 最大 token 数（默认从 app.yaml 读取）
        max_few_shot_examples: 最大 Few-shot 示例数（默认从 app.yaml 读取）
    """
    model_config = ConfigDict(extra="forbid")
    
    current_date: date
    timezone: str = "Asia/Shanghai"
    fiscal_year_start_month: int = 1
    max_schema_tokens: int = 2000
    max_few_shot_examples: int = 3

__all__ = [
    "SemanticConfig",
]
