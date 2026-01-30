# -*- coding: utf-8 -*-
"""
DynamicPromptBuilder - 动态 Prompt 构建器

只负责组装 Prompt 模板，Schema 裁剪由 DynamicSchemaBuilder 完成。

配置来源：analytics_assistant/config/app.yaml -> semantic_parser.prompt_builder

Requirements: 12.1 - 动态 Prompt 生成, 7.1-7.5 - 模块化 Prompt 构建
"""

import logging
from typing import Any, Dict, List, Optional

from .time_hint_generator import TimeHintGenerator
from ..schemas.intermediate import FieldCandidate, FewShotExample
from ..schemas.prefilter import ComplexityType
from ..schemas.config import SemanticConfig
from ..components.history_manager import HistoryManager
from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.seeds import COMPUTATION_SEEDS, ComputationSeed


logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════════════════

def get_low_confidence_threshold() -> float:
    """获取低置信度阈值。"""
    try:
        config = get_config()
        return config.get_semantic_parser_optimization_config().get("low_confidence_threshold", 0.7)
    except Exception as e:
        logger.warning(f"无法加载配置，使用默认值: {e}")
        return 0.7


# ═══════════════════════════════════════════════════════════════════════════
# 计算种子模块模板
# ═══════════════════════════════════════════════════════════════════════════

COMPUTATION_SEEDS_TEMPLATE_ZH = """<computation_hints>
检测到的计算类型（请参考以下公式）:
{seeds_content}
</computation_hints>"""

COMPUTATION_SEEDS_TEMPLATE_EN = """<computation_hints>
Detected computation types (refer to the following formulas):
{seeds_content}
</computation_hints>"""


# ═══════════════════════════════════════════════════════════════════════════
# Prompt 模板
# ═══════════════════════════════════════════════════════════════════════════

# 基础模板头部
BASE_PROMPT_HEADER = '''你是一个数据分析助手，负责理解用户的数据查询需求。

<context>
当前日期: {current_date}
时区: {timezone}
{time_hints}
</context>

<available_fields>
{field_list}
</available_fields>

{few_shot_section}'''

# SIMPLE 类型任务模板
SIMPLE_TASK_TEMPLATE = '''<task>
分析用户问题，提取查询信息并以 JSON 格式输出。

需要提取：
1. restated_question: 完整问题
2. what.measures: 度量字段列表
3. where.dimensions: 分组维度列表
4. where.filters: 筛选条件列表
5. self_check: 自检结果（各项置信度 0-1）
</task>'''

# 复杂计算类型任务模板（带 Schema）
COMPLEX_TASK_TEMPLATE = '''<computation_guide>
检测到 {complexity_name} 计算需求，允许的计算类型：{allowed_calc_types}
</computation_guide>

{schema_section}

<task>
分析用户问题，提取以下信息：
1. restated_question: 完整问题
2. what.measures: 基础度量字段
3. where.dimensions: 分组维度
4. where.filters: 筛选条件
5. computations: 派生计算（使用上述 Schema）
6. self_check: 自检结果
</task>'''

# 问题和历史部分
PROMPT_FOOTER = '''
<user_question>
{question}
</user_question>

{history_section}'''

# ComplexityType 显示名称
COMPLEXITY_NAMES = {
    ComplexityType.SIMPLE: "简单查询",
    ComplexityType.RATIO: "比率/公式",
    ComplexityType.TIME_COMPARE: "同比/环比",
    ComplexityType.RANK: "排名",
    ComplexityType.SHARE: "占比",
    ComplexityType.CUMULATIVE: "累计",
    ComplexityType.SUBQUERY: "子查询",
}


# ═══════════════════════════════════════════════════════════════════════════
# DynamicPromptBuilder 类
# ═══════════════════════════════════════════════════════════════════════════

class DynamicPromptBuilder:
    """动态 Prompt 构建器
    
    只负责组装 Prompt，Schema 裁剪由 DynamicSchemaBuilder 完成。
    
    Examples:
        >>> from ..components.dynamic_schema_builder import DynamicSchemaBuilder
        >>> 
        >>> # 1. 先用 DynamicSchemaBuilder 裁剪 Schema
        >>> schema_builder = DynamicSchemaBuilder()
        >>> schema_result = schema_builder.build(...)
        >>> 
        >>> # 2. 再用 DynamicPromptBuilder 组装 Prompt
        >>> prompt_builder = DynamicPromptBuilder()
        >>> prompt = prompt_builder.build(
        ...     question="上个月各地区的利润率",
        ...     config=config,
        ...     field_candidates=schema_result.field_candidates,
        ...     schema_json=schema_result.schema_json,  # 裁剪好的 Schema
        ...     detected_complexity=schema_result.detected_complexity,
        ...     allowed_calc_types=schema_result.allowed_calc_types,
        ... )
    """
    
    def __init__(self, low_confidence_threshold: Optional[float] = None):
        """初始化。
        
        Args:
            low_confidence_threshold: 低置信度阈值（None 从配置读取）
        """
        self.low_confidence_threshold = (
            low_confidence_threshold or get_low_confidence_threshold()
        )
    
    def build(
        self,
        question: str,
        config: SemanticConfig,
        field_candidates: List[FieldCandidate],
        schema_json: str = "",
        detected_complexity: Optional[List[ComplexityType]] = None,
        allowed_calc_types: Optional[List[str]] = None,
        history: Optional[List[Dict[str, str]]] = None,
        few_shot_examples: Optional[List[FewShotExample]] = None,
        prefilter_result: Optional[Any] = None,
        feature_output: Optional[Any] = None,
    ) -> str:
        """构建 Prompt
        
        Args:
            question: 用户问题
            config: 语义解析配置
            field_candidates: 字段候选列表（已由 DynamicSchemaBuilder 裁剪）
            schema_json: 裁剪后的 Schema JSON（由 DynamicSchemaBuilder 生成）
            detected_complexity: 检测到的复杂度类型
            allowed_calc_types: 允许的 CalcType
            history: 对话历史
            few_shot_examples: Few-shot 示例
            prefilter_result: PrefilterResult（用于计算种子插入）
            feature_output: FeatureExtractionOutput（用于计算种子插入）
        
        Returns:
            构建好的 Prompt 字符串
        """
        complexity_list = detected_complexity or [ComplexityType.SIMPLE]
        primary_complexity = self._get_primary_complexity(complexity_list)
        
        # 1. 生成时间提示
        time_hints = self._generate_time_hints(question, config)
        
        # 2. 格式化字段列表
        field_list = self._format_field_list(field_candidates, config.max_schema_tokens)
        
        # 3. 格式化 Few-shot 示例
        few_shot_section = self._format_few_shot_examples(
            few_shot_examples, config.max_few_shot_examples
        )
        
        # 4. 构建头部
        header = BASE_PROMPT_HEADER.format(
            current_date=config.current_date.isoformat(),
            timezone=config.timezone,
            time_hints=time_hints,
            field_list=field_list,
            few_shot_section=few_shot_section,
        )
        
        # 5. 构建任务部分
        if primary_complexity == ComplexityType.SIMPLE or not schema_json:
            task_section = SIMPLE_TASK_TEMPLATE
        else:
            calc_types_str = ", ".join(allowed_calc_types) if allowed_calc_types else "无"
            task_section = COMPLEX_TASK_TEMPLATE.format(
                complexity_name=COMPLEXITY_NAMES.get(primary_complexity, "复杂"),
                allowed_calc_types=calc_types_str,
                schema_section=f"<computation_schema>\n{schema_json}\n</computation_schema>",
            )
        
        # 6. 格式化历史
        history_section = self._format_history(history)
        
        # 7. 构建尾部
        footer = PROMPT_FOOTER.format(
            question=question,
            history_section=history_section,
        )
        
        # 8. 组装
        base_prompt = header + "\n\n" + task_section + footer
        
        # 9. 插入计算种子（如果高置信度）
        if self._should_insert_computation_seeds(prefilter_result, feature_output):
            seeds = self._collect_computation_seeds(prefilter_result, feature_output)
            if seeds:
                language = self._get_language(prefilter_result)
                seeds_module = self._build_computation_seeds_module(seeds, language)
                base_prompt = self._insert_computation_module(base_prompt, seeds_module)
        
        return base_prompt
    
    def _get_primary_complexity(self, complexity_list: List[ComplexityType]) -> ComplexityType:
        """获取主要复杂度类型（按优先级）"""
        if not complexity_list:
            return ComplexityType.SIMPLE
        
        priority = [
            ComplexityType.SUBQUERY,
            ComplexityType.TIME_COMPARE,
            ComplexityType.RATIO,
            ComplexityType.RANK,
            ComplexityType.SHARE,
            ComplexityType.CUMULATIVE,
            ComplexityType.SIMPLE,
        ]
        
        for c in priority:
            if c in complexity_list:
                return c
        return complexity_list[0]
    
    def _generate_time_hints(self, question: str, config: SemanticConfig) -> str:
        """生成时间提示"""
        generator = TimeHintGenerator(
            current_date=config.current_date,
            fiscal_year_start_month=config.fiscal_year_start_month,
        )
        return generator.format_for_prompt(question)
    
    def _format_field_list(self, field_candidates: List[FieldCandidate], max_tokens: int) -> str:
        """格式化字段列表
        
        显示字段信息和检索置信度，帮助 LLM 理解字段匹配质量。
        """
        if not field_candidates:
            return "（无可用字段）"
        
        sorted_fields = sorted(field_candidates, key=lambda f: f.confidence, reverse=True)
        
        lines = []
        estimated_tokens = 0
        
        for field in sorted_fields:
            line = f"- {field.field_name}"
            if field.field_caption and field.field_caption != field.field_name:
                line += f" ({field.field_caption})"
            line += f" [{field.field_type}, {field.data_type}]"
            
            # 显示置信度（非精确匹配时）
            if field.confidence < 0.95:
                line += f" 匹配度:{int(field.confidence * 100)}%"
            
            if field.description:
                line += f": {field.description}"
            
            # 层级信息
            hierarchy_info = self._format_hierarchy_info(field)
            if hierarchy_info:
                line += f" {hierarchy_info}"
            
            if field.sample_values:
                samples = ", ".join(field.sample_values[:3])
                line += f" 示例值: {samples}"
            
            line_tokens = len(line) // 2
            if estimated_tokens + line_tokens > max_tokens:
                lines.append("... (更多字段已省略)")
                break
            
            lines.append(line)
            estimated_tokens += line_tokens
        
        return "\n".join(lines)
    
    def _format_hierarchy_info(self, field: FieldCandidate) -> str:
        """格式化维度层级信息"""
        parts = []
        
        category = field.hierarchy_category or field.category
        if category:
            category_names = {
                "time": "时间维度", "geography": "地理维度",
                "product": "产品维度", "customer": "客户维度",
                "organization": "组织维度", "financial": "财务维度",
            }
            parts.append(category_names.get(category.lower(), category))
        
        level = field.hierarchy_level or field.level
        if level is not None:
            parts.append(f"L{level}")
        
        if field.drill_down_options:
            drill_str = "→".join(field.drill_down_options[:3])
            parts.append(f"下钻:{drill_str}")
        
        return f"[{', '.join(parts)}]" if parts else ""
    
    def _format_few_shot_examples(
        self, examples: Optional[List[FewShotExample]], max_examples: int
    ) -> str:
        """格式化 Few-shot 示例"""
        if not examples:
            return ""
        
        import json
        examples = examples[:max_examples]
        
        lines = ["<examples>"]
        for i, ex in enumerate(examples, 1):
            lines.append(f"<example_{i}>")
            lines.append(f"问题: {ex.question}")
            lines.append(f"重述: {ex.restated_question}")
            lines.append(f"what: {json.dumps(ex.what, ensure_ascii=False)}")
            lines.append(f"where: {json.dumps(ex.where, ensure_ascii=False)}")
            if ex.computations:
                lines.append(f"computations: {json.dumps(ex.computations, ensure_ascii=False)}")
            lines.append(f"</example_{i}>")
        lines.append("</examples>")
        
        return "\n".join(lines)
    
    def _format_history(self, history: Optional[List[Dict[str, str]]]) -> str:
        """格式化对话历史"""
        if not history:
            return ""
        manager = HistoryManager()
        return manager.format_history_for_prompt(history)

    
    # ═══════════════════════════════════════════════════════════════════════════
    # 计算种子相关方法
    # ═══════════════════════════════════════════════════════════════════════════
    
    def _should_insert_computation_seeds(
        self, prefilter_result: Optional[Any], feature_output: Optional[Any]
    ) -> bool:
        """判断是否应该插入计算种子"""
        if prefilter_result is None and feature_output is None:
            return False
        
        if feature_output:
            confidence = getattr(feature_output, 'confirmation_confidence', 1.0)
            if confidence < self.low_confidence_threshold:
                return False
        
        if prefilter_result:
            if getattr(prefilter_result, 'low_confidence', False):
                return False
        
        has_confirmed = bool(getattr(feature_output, 'confirmed_computations', []) if feature_output else [])
        has_matched = bool(getattr(prefilter_result, 'matched_computations', []) if prefilter_result else [])
        
        return has_confirmed or has_matched
    
    def _get_language(self, prefilter_result: Optional[Any]) -> str:
        """获取检测到的语言"""
        if prefilter_result:
            return getattr(prefilter_result, 'detected_language', 'zh')
        return 'zh'
    
    def _collect_computation_seeds(
        self, prefilter_result: Optional[Any], feature_output: Optional[Any]
    ) -> List[ComputationSeed]:
        """收集计算种子"""
        seed_names = set()
        
        if feature_output:
            for comp in getattr(feature_output, 'confirmed_computations', []):
                if isinstance(comp, dict):
                    seed_names.add(comp.get("seed_name", ""))
                elif isinstance(comp, str):
                    seed_names.add(comp)
                elif hasattr(comp, "seed_name"):
                    seed_names.add(comp.seed_name)
        
        if prefilter_result:
            for comp in getattr(prefilter_result, 'matched_computations', []):
                if hasattr(comp, 'seed_name'):
                    seed_names.add(comp.seed_name)
                elif isinstance(comp, str):
                    seed_names.add(comp)
        
        return [seed for seed in COMPUTATION_SEEDS if seed.name in seed_names]
    
    def _build_computation_seeds_module(self, seeds: List[ComputationSeed], language: str) -> str:
        """构建计算种子模块"""
        type_label = "类型" if language == "zh" else "Type"
        formula_label = "公式" if language == "zh" else "Formula"
        
        lines = []
        for seed in seeds:
            display_name = seed.display_name or seed.name
            lines.append(f"  - {display_name}:")
            lines.append(f"    {type_label}: {seed.calc_type}")
            if seed.formula:
                lines.append(f"    {formula_label}: {seed.formula}")
        
        template = COMPUTATION_SEEDS_TEMPLATE_ZH if language == "zh" else COMPUTATION_SEEDS_TEMPLATE_EN
        return template.format(seeds_content="\n".join(lines))
    
    def _insert_computation_module(self, base_prompt: str, seeds_module: str) -> str:
        """插入计算种子模块到 <task> 之前"""
        task_pos = base_prompt.find("<task>")
        if task_pos == -1:
            return base_prompt + "\n\n" + seeds_module
        return base_prompt[:task_pos] + seeds_module + "\n\n" + base_prompt[task_pos:]


__all__ = [
    "DynamicPromptBuilder",
    "get_low_confidence_threshold",
]
