# -*- coding: utf-8 -*-
"""
DynamicPromptBuilder - 动态 Prompt 构建器

根据查询复杂度动态生成 Prompt：
- 简单查询：使用精简模板，减少 token 消耗
- 复杂查询：使用完整模板，包含计算逻辑示例

设计原则：
- 根据问题特征自动选择模板
- 集成 TimeHintGenerator 提供时间上下文
- 动态裁剪字段列表以控制 token 消耗

配置来源：analytics_assistant/config/app.yaml -> semantic_parser.prompt_builder

Requirements: 12.1 - 动态 Prompt 生成
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from .time_hint_generator import TimeHintGenerator
from ..schemas.intermediate import FieldCandidate, FewShotExample
from ..schemas.enums import PromptComplexity
from ..schemas.config import SemanticConfig
from ..keywords_data import (
    get_derived_metric_keywords,
    get_time_calc_keywords,
    get_subquery_keywords,
    get_table_calc_keywords,
)
from ..components.history_manager import HistoryManager


logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Prompt 模板
# ═══════════════════════════════════════════════════════════════════════════

SIMPLE_PROMPT_TEMPLATE = '''你是一个数据分析助手，负责理解用户的数据查询需求。

<context>
当前日期: {current_date}
时区: {timezone}
{time_hints}
</context>

<available_fields>
{field_list}
</available_fields>

{few_shot_section}

<task>
分析用户问题，提取查询信息并以 JSON 格式输出。

需要提取：
1. restated_question: 完整独立的问题描述（不依赖对话历史）
2. what.measures: 需要查询的度量字段列表
3. where.dimensions: 分组维度列表
4. where.filters: 筛选条件列表
5. self_check: 自检结果（各项置信度 0-1）

如果问题信息不完整，设置 needs_clarification=true 并提供澄清问题。
</task>

<user_question>
{question}
</user_question>

{history_section}'''


COMPLEX_PROMPT_TEMPLATE = '''你是一个数据分析助手，负责理解用户的数据查询需求，包括复杂的派生度量计算。

<context>
当前日期: {current_date}
时区: {timezone}
财年起始月份: {fiscal_year_start_month}月
{time_hints}
</context>

<available_fields>
{field_list}
</available_fields>

{few_shot_section}

<computation_guide>
派生度量计算类型说明：

1. 简单计算（多个度量间的公式）：
   - RATIO: 比率计算，如 利润率 = [利润]/[销售额]
   - SUM: 求和计算，如 总成本 = [固定成本]+[可变成本]
   - DIFFERENCE: 差值计算，如 净利润 = [收入]-[成本]
   - FORMULA: 自定义公式

2. 表计算（单个度量 + 维度上下文）：
   - TABLE_CALC_PERCENT_DIFF: 增长率（同比/环比）
   - TABLE_CALC_PERCENT_OF_TOTAL: 占比（市场份额）
   - TABLE_CALC_RANK: 排名
   - TABLE_CALC_RUNNING: 累计（YTD）

3. 子查询（固定粒度计算）：
   - SUBQUERY: 子查询聚合，如每个客户的首次购买日期

示例：
- "利润率" → RATIO, formula="[利润]/[销售额]", base_measures=["利润", "销售额"]
- "销售额同比增长" → TABLE_CALC_PERCENT_DIFF, base_measures=["销售额"], relative_to="PREVIOUS"
- "各地区销售额占比" → TABLE_CALC_PERCENT_OF_TOTAL, base_measures=["销售额"], partition_by=["地区"]
</computation_guide>

<task>
分析用户问题，提取以下信息：
1. restated_question: 完整独立的问题描述
2. what.measures: 基础度量字段
3. where.dimensions: 分组维度
4. where.filters: 筛选条件
5. computations: 派生计算逻辑（如有）
6. self_check: 自检结果

如果问题信息不完整，设置 needs_clarification=true 并提供澄清问题。
</task>

<user_question>
{question}
</user_question>

{history_section}'''


# ═══════════════════════════════════════════════════════════════════════════
# DynamicPromptBuilder 类
# ═══════════════════════════════════════════════════════════════════════════

class DynamicPromptBuilder:
    """动态 Prompt 构建器
    
    根据查询复杂度动态生成 Prompt：
    - 检测问题中的派生度量关键词
    - 选择简单或复杂模板
    - 集成时间提示
    - 裁剪字段列表以控制 token
    
    Attributes:
        simple_template: 简单查询模板
        complex_template: 复杂查询模板
    
    Examples:
        >>> builder = DynamicPromptBuilder()
        >>> config = SemanticConfig(current_date=date(2025, 1, 28))
        >>> prompt = builder.build(
        ...     question="上个月各地区的销售额",
        ...     field_candidates=[...],
        ...     config=config,
        ... )
    """
    
    def __init__(
        self,
        simple_template: Optional[str] = None,
        complex_template: Optional[str] = None,
    ):
        """初始化 DynamicPromptBuilder
        
        Args:
            simple_template: 简单查询模板（None 则使用默认）
            complex_template: 复杂查询模板（None 则使用默认）
        """
        self._simple_template = simple_template or SIMPLE_PROMPT_TEMPLATE
        self._complex_template = complex_template or COMPLEX_PROMPT_TEMPLATE
    
    def build(
        self,
        question: str,
        field_candidates: List[FieldCandidate],
        config: SemanticConfig,
        history: Optional[List[Dict[str, str]]] = None,
        few_shot_examples: Optional[List[FewShotExample]] = None,
        complexity_hint: Optional[PromptComplexity] = None,
    ) -> str:
        """构建 Prompt
        
        流程：
        1. 检测查询复杂度（或使用提示）
        2. 选择对应模板
        3. 生成时间提示
        4. 格式化字段列表
        5. 格式化 Few-shot 示例
        6. 组装最终 Prompt
        
        Args:
            question: 用户问题
            field_candidates: 字段候选列表
            config: 语义解析配置
            history: 对话历史
            few_shot_examples: Few-shot 示例
            complexity_hint: 复杂度提示（覆盖自动检测）
        
        Returns:
            构建好的 Prompt 字符串
        """
        # 1. 检测复杂度
        complexity = complexity_hint or self._detect_complexity(question)
        logger.debug(f"检测到查询复杂度: {complexity.value}")
        
        # 2. 选择模板
        template = (
            self._complex_template 
            if complexity == PromptComplexity.COMPLEX 
            else self._simple_template
        )
        
        # 3. 生成时间提示
        time_hints = self._generate_time_hints(question, config)
        
        # 4. 格式化字段列表
        field_list = self._format_field_list(
            field_candidates, 
            config.max_schema_tokens
        )
        
        # 5. 格式化 Few-shot 示例
        few_shot_section = self._format_few_shot_examples(
            few_shot_examples,
            config.max_few_shot_examples,
        )
        
        # 6. 格式化对话历史
        history_section = self._format_history(history)
        
        # 7. 组装 Prompt
        prompt = template.format(
            current_date=config.current_date.isoformat(),
            timezone=config.timezone,
            fiscal_year_start_month=config.fiscal_year_start_month,
            time_hints=time_hints,
            field_list=field_list,
            few_shot_section=few_shot_section,
            history_section=history_section,
            question=question,
        )
        
        return prompt
    
    def _detect_complexity(self, question: str) -> PromptComplexity:
        """检测查询复杂度
        
        检测问题中是否包含复杂计算关键词：
        - 派生度量关键词（率、比、占比等）
        - 时间计算关键词（同比、环比等）
        - 子查询关键词（每个、不考虑、首次等）
        - 表计算关键词（排名、累计等）
        
        关键词从 keywords_data.py 读取。
        
        Args:
            question: 用户问题
        
        Returns:
            PromptComplexity.SIMPLE 或 PromptComplexity.COMPLEX
        """
        question_lower = question.lower()
        
        # 从 keywords_data.py 读取关键词
        all_complex_keywords = (
            get_derived_metric_keywords() +
            get_time_calc_keywords() +
            get_subquery_keywords() +
            get_table_calc_keywords()
        )
        
        for keyword in all_complex_keywords:
            if keyword.lower() in question_lower:
                logger.debug(f"检测到复杂度关键词: {keyword}")
                return PromptComplexity.COMPLEX
        
        return PromptComplexity.SIMPLE
    
    def _generate_time_hints(
        self, 
        question: str, 
        config: SemanticConfig,
    ) -> str:
        """生成时间提示
        
        使用 TimeHintGenerator 从问题中提取时间表达式，
        生成参考日期范围提示。
        
        Args:
            question: 用户问题
            config: 语义解析配置
        
        Returns:
            时间提示 XML 字符串，或空字符串
        """
        generator = TimeHintGenerator(
            current_date=config.current_date,
            fiscal_year_start_month=config.fiscal_year_start_month,
        )
        return generator.format_for_prompt(question)
    
    def _format_field_list(
        self,
        field_candidates: List[FieldCandidate],
        max_tokens: int,
    ) -> str:
        """格式化字段列表
        
        将字段候选列表格式化为 Prompt 中的字段描述。
        按置信度排序，优先保留高置信度字段。
        包含维度层级信息（如有）。
        
        Property 28: Hierarchy Enrichment
        *For any* dimension field with hierarchy information,
        the prompt SHALL include drill-down options.
        
        Args:
            field_candidates: 字段候选列表
            max_tokens: 最大 token 数（粗略估计）
        
        Returns:
            格式化的字段列表字符串
        """
        if not field_candidates:
            return "（无可用字段）"
        
        # 按置信度排序
        sorted_fields = sorted(
            field_candidates, 
            key=lambda f: f.confidence, 
            reverse=True
        )
        
        lines = []
        estimated_tokens = 0
        
        for field in sorted_fields:
            # 构建字段描述行
            line = f"- {field.field_name}"
            if field.field_caption and field.field_caption != field.field_name:
                line += f" ({field.field_caption})"
            line += f" [{field.field_type}, {field.data_type}]"
            
            if field.description:
                line += f": {field.description}"
            
            # 添加维度层级信息（Property 28: Hierarchy Enrichment）
            hierarchy_info = self._format_hierarchy_info(field)
            if hierarchy_info:
                line += f" {hierarchy_info}"
            
            if field.sample_values:
                samples = ", ".join(field.sample_values[:3])
                line += f" 示例值: {samples}"
            
            # 粗略估计 token 数（中文约 1.5 字符/token）
            line_tokens = len(line) // 2
            
            if estimated_tokens + line_tokens > max_tokens:
                lines.append("... (更多字段已省略)")
                break
            
            lines.append(line)
            estimated_tokens += line_tokens
        
        return "\n".join(lines)
    
    def _format_hierarchy_info(self, field: FieldCandidate) -> str:
        """格式化维度层级信息
        
        为维度字段生成层级描述，包括：
        - 维度类别（时间/地理/产品等）
        - 层级级别（1-5）
        - 下钻选项
        
        Property 28: Hierarchy Enrichment
        *For any* dimension field with hierarchy information,
        the prompt SHALL include drill-down options.
        
        Args:
            field: 字段候选
        
        Returns:
            层级信息字符串，如 "[时间维度 L2, 下钻: 月→日]"
        """
        parts = []
        
        # 维度类别
        category = field.hierarchy_category or field.category
        if category:
            category_names = {
                "time": "时间维度",
                "geography": "地理维度",
                "product": "产品维度",
                "customer": "客户维度",
                "organization": "组织维度",
                "financial": "财务维度",
                "other": "其他维度",
            }
            category_name = category_names.get(category.lower(), category)
            parts.append(category_name)
        
        # 层级级别
        level = field.hierarchy_level or field.level
        if level is not None:
            parts.append(f"L{level}")
        
        # 粒度
        if field.granularity:
            parts.append(f"粒度:{field.granularity}")
        
        # 下钻选项（Property 28 核心要求）
        if field.drill_down_options:
            drill_str = "→".join(field.drill_down_options[:3])
            parts.append(f"下钻:{drill_str}")
        elif field.child_dimension:
            parts.append(f"下钻:{field.child_dimension}")
        
        if not parts:
            return ""
        
        return f"[{', '.join(parts)}]"
    
    def _format_few_shot_examples(
        self,
        examples: Optional[List[FewShotExample]],
        max_examples: int,
    ) -> str:
        """格式化 Few-shot 示例
        
        Args:
            examples: Few-shot 示例列表
            max_examples: 最大示例数
        
        Returns:
            格式化的示例字符串，或空字符串
        """
        if not examples:
            return ""
        
        # 限制示例数量
        examples = examples[:max_examples]
        
        lines = ["<examples>"]
        for i, ex in enumerate(examples, 1):
            lines.append(f"<example_{i}>")
            lines.append(f"问题: {ex.question}")
            lines.append(f"重述: {ex.restated_question}")
            lines.append(f"度量: {ex.what}")
            lines.append(f"维度/筛选: {ex.where}")
            if ex.computations:
                lines.append(f"计算: {ex.computations}")
            lines.append(f"</example_{i}>")
        lines.append("</examples>")
        
        return "\n".join(lines)
    
    def _format_history(
        self,
        history: Optional[List[Dict[str, str]]],
        max_tokens: Optional[int] = None,
    ) -> str:
        """格式化对话历史（带 token 截断）
        
        使用 HistoryManager 进行截断，确保不超过 MAX_HISTORY_TOKENS。
        截断时保留最近的消息。
        
        Property 17: History Truncation
        *For any* conversation history exceeding MAX_HISTORY_TOKENS, 
        the truncated history SHALL preserve the most recent messages.
        
        Args:
            history: 对话历史列表，每项包含 role 和 content
            max_tokens: 最大 token 数（None 使用配置值）
        
        Returns:
            格式化的历史字符串，或空字符串
        """
        if not history:
            return ""
        
        manager = HistoryManager()
        return manager.format_history_for_prompt(history, max_tokens)
    
    def get_complexity(self, question: str) -> PromptComplexity:
        """获取问题的复杂度（公开方法，用于测试）
        
        Args:
            question: 用户问题
        
        Returns:
            PromptComplexity
        """
        return self._detect_complexity(question)


__all__ = [
    "DynamicPromptBuilder",
]
