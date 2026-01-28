# -*- coding: utf-8 -*-
"""
SemanticUnderstanding - 语义理解核心组件

核心职责：
1. 调用 LLM 理解用户问题
2. 输出结构化的 SemanticOutput
3. 支持流式输出
4. 集成 DynamicPromptBuilder

设计原则：
- 信任 LLM 的推理能力
- 通过 Prompt 和 Few-shot 提升准确性
- 支持渐进式查询构建

配置来源：analytics_assistant/config/app.yaml -> semantic_parser.semantic_understanding

Requirements: 5.1 - 语义理解核心
"""
import logging
from datetime import date, datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.agents.base.node import (
    get_llm,
    stream_llm_structured,
)

from ..schemas.output import SemanticOutput, ClarificationSource
from ..schemas.intermediate import FieldCandidate, FewShotExample
from ..schemas.enums import PromptComplexity
from ..schemas.config import SemanticConfig
from ..prompts.prompt_builder import DynamicPromptBuilder


logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════════════════

def _get_config() -> Dict[str, Any]:
    """获取 semantic_understanding 配置。"""
    try:
        config = get_config()
        return config.config.get("semantic_parser", {}).get("semantic_understanding", {})
    except Exception as e:
        logger.warning(f"无法加载配置，使用默认值: {e}")
        return {}


# 默认配置（作为 fallback）
_DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.7
_DEFAULT_TIMEZONE = "Asia/Shanghai"
_DEFAULT_FISCAL_YEAR_START_MONTH = 1
_DEFAULT_MAX_SCHEMA_TOKENS = 2000
_DEFAULT_MAX_FEW_SHOT_EXAMPLES = 3


def get_low_confidence_threshold() -> float:
    """获取低置信度阈值。"""
    return _get_config().get("low_confidence_threshold", _DEFAULT_LOW_CONFIDENCE_THRESHOLD)


def get_default_timezone() -> str:
    """获取默认时区。"""
    return _get_config().get("default_timezone", _DEFAULT_TIMEZONE)


def get_fiscal_year_start_month() -> int:
    """获取财年起始月份。"""
    return _get_config().get("fiscal_year_start_month", _DEFAULT_FISCAL_YEAR_START_MONTH)


def get_max_schema_tokens() -> int:
    """获取 Schema 最大 token 数。"""
    return _get_config().get("max_schema_tokens", _DEFAULT_MAX_SCHEMA_TOKENS)


def get_max_few_shot_examples() -> int:
    """获取最大 Few-shot 示例数。"""
    return _get_config().get("max_few_shot_examples", _DEFAULT_MAX_FEW_SHOT_EXAMPLES)


# ═══════════════════════════════════════════════════════════════════════════
# SemanticUnderstanding 类
# ═══════════════════════════════════════════════════════════════════════════

class SemanticUnderstanding:
    """语义理解核心组件
    
    负责调用 LLM 理解用户问题，输出结构化的 SemanticOutput。
    
    流程：
    1. 使用 DynamicPromptBuilder 构建 Prompt
    2. 调用 LLM（支持流式输出）
    3. 解析 JSON 并验证为 Pydantic 对象
    4. 检查自检结果，标记低置信度问题
    
    Attributes:
        prompt_builder: Prompt 构建器
        llm: LLM 实例（可选，不提供则自动获取）
    
    Examples:
        >>> understanding = SemanticUnderstanding()
        >>> result = await understanding.understand(
        ...     question="上个月各地区的销售额",
        ...     field_candidates=[...],
        ...     current_date=date(2025, 1, 28),
        ... )
        >>> print(result.restated_question)
        "查询2024年12月各地区的销售额"
    """
    
    def __init__(
        self,
        prompt_builder: Optional[DynamicPromptBuilder] = None,
        llm: Optional[BaseChatModel] = None,
    ):
        """初始化 SemanticUnderstanding
        
        Args:
            prompt_builder: Prompt 构建器（None 则使用默认）
            llm: LLM 实例（None 则自动获取）
        """
        self._prompt_builder = prompt_builder or DynamicPromptBuilder()
        self._llm = llm
    
    def _get_llm(self) -> BaseChatModel:
        """获取 LLM 实例"""
        if self._llm is not None:
            return self._llm
        return get_llm(
            agent_name="semantic_parser",
            enable_json_mode=True,
        )
    
    async def understand(
        self,
        question: str,
        field_candidates: List[FieldCandidate],
        current_date: Optional[date] = None,
        timezone: Optional[str] = None,
        fiscal_year_start_month: Optional[int] = None,
        history: Optional[List[Dict[str, str]]] = None,
        few_shot_examples: Optional[List[FewShotExample]] = None,
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
        on_partial: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        on_thinking: Optional[Callable[[str], Awaitable[None]]] = None,
        return_thinking: bool = False,
    ) -> SemanticOutput:
        """执行语义理解
        
        流程：
        1. 构建 SemanticConfig
        2. 转换字段候选和示例格式
        3. 使用 DynamicPromptBuilder 构建 Prompt
        4. 调用 LLM（流式）
        5. 解析并验证输出
        6. 检查自检结果
        
        Args:
            question: 用户问题
            field_candidates: 字段候选列表
            current_date: 当前日期（None 则使用今天）
            timezone: 时区（None 从配置读取）
            fiscal_year_start_month: 财年起始月份（None 从配置读取）
            history: 对话历史
            few_shot_examples: Few-shot 示例
            on_token: Token 回调（用于 UI 展示）
            on_partial: 部分 JSON 回调
            on_thinking: Thinking 回调（R1 模型）
            return_thinking: 是否返回 thinking
        
        Returns:
            SemanticOutput 实例
        
        Raises:
            ValueError: 如果 LLM 输出无法解析
        """
        # 1. 构建配置
        config = SemanticConfig(
            current_date=current_date or date.today(),
            timezone=timezone or get_default_timezone(),
            fiscal_year_start_month=fiscal_year_start_month or get_fiscal_year_start_month(),
            max_schema_tokens=get_max_schema_tokens(),
            max_few_shot_examples=get_max_few_shot_examples(),
        )
        
        # 2. 转换字段候选格式
        prompt_fields = self._convert_field_candidates(field_candidates)
        
        # 3. 转换 Few-shot 示例格式
        prompt_examples = self._convert_few_shot_examples(few_shot_examples)
        
        # 4. 构建 Prompt
        prompt = self._prompt_builder.build(
            question=question,
            field_candidates=prompt_fields,
            config=config,
            history=history,
            few_shot_examples=prompt_examples,
        )
        
        # 5. 构建消息
        messages: List[BaseMessage] = [
            HumanMessage(content=prompt),
        ]
        
        # 6. 调用 LLM
        llm = self._get_llm()
        
        logger.debug(f"调用 LLM 进行语义理解，问题: {question[:50]}...")
        
        if return_thinking:
            result, thinking = await stream_llm_structured(
                llm=llm,
                messages=messages,
                output_model=SemanticOutput,
                on_token=on_token,
                on_partial=on_partial,
                on_thinking=on_thinking,
                return_thinking=True,
            )
        else:
            result = await stream_llm_structured(
                llm=llm,
                messages=messages,
                output_model=SemanticOutput,
                on_token=on_token,
                on_partial=on_partial,
                on_thinking=on_thinking,
                return_thinking=False,
            )
        
        # 7. 后处理：检查自检结果
        result = self._post_process(result)
        
        # 8. 设置澄清来源
        if result.needs_clarification:
            result.clarification_source = ClarificationSource.SEMANTIC_UNDERSTANDING
        
        logger.debug(f"语义理解完成，query_id: {result.query_id}")
        
        return result
    
    def _convert_field_candidates(
        self,
        candidates: List[FieldCandidate],
    ) -> List[FieldCandidate]:
        """转换字段候选格式
        
        由于现在使用统一的 FieldCandidate，直接返回即可。
        保留此方法以便未来扩展。
        """
        return candidates
    
    def _convert_few_shot_examples(
        self,
        examples: Optional[List[FewShotExample]],
    ) -> Optional[List[FewShotExample]]:
        """转换 Few-shot 示例格式
        
        由于现在使用统一的 FewShotExample，直接返回即可。
        保留此方法以便未来扩展。
        """
        return examples
    
    def _post_process(self, result: SemanticOutput) -> SemanticOutput:
        """后处理：检查自检结果
        
        如果任一置信度低于阈值，确保 potential_issues 非空。
        """
        self_check = result.self_check
        low_confidence_threshold = get_low_confidence_threshold()
        
        # 检查各项置信度
        low_confidence_fields = []
        
        if self_check.field_mapping_confidence < low_confidence_threshold:
            low_confidence_fields.append(
                f"字段映射置信度较低 ({self_check.field_mapping_confidence:.2f})"
            )
        
        if self_check.time_range_confidence < low_confidence_threshold:
            low_confidence_fields.append(
                f"时间范围置信度较低 ({self_check.time_range_confidence:.2f})"
            )
        
        if self_check.computation_confidence < low_confidence_threshold:
            low_confidence_fields.append(
                f"计算逻辑置信度较低 ({self_check.computation_confidence:.2f})"
            )
        
        if self_check.overall_confidence < low_confidence_threshold:
            low_confidence_fields.append(
                f"整体置信度较低 ({self_check.overall_confidence:.2f})"
            )
        
        # 如果有低置信度字段但 potential_issues 为空，添加警告
        if low_confidence_fields and not self_check.potential_issues:
            self_check.potential_issues = low_confidence_fields
            result.parsing_warnings.append(
                "检测到低置信度但 LLM 未报告问题，已自动添加警告"
            )
        
        return result


__all__ = [
    "SemanticUnderstanding",
    "get_low_confidence_threshold",
    "get_default_timezone",
    "get_fiscal_year_start_month",
    "get_max_schema_tokens",
    "get_max_few_shot_examples",
]
