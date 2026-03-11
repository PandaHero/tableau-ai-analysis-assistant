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
from typing import Any, Awaitable, Callable, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.agents.base.node import (
    get_llm,
    stream_llm_structured,
)

from ..schemas.output import SemanticOutput, ClarificationSource
from ..schemas.intermediate import FieldCandidate, FewShotExample
from ..schemas.config import SemanticConfig
from ..prompts.prompt_builder import DynamicPromptBuilder

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════════════════

def _get_config() -> dict[str, Any]:
    """获取 semantic_understanding 配置。"""
    try:
        return get_config().get_semantic_understanding_config()
    except Exception as e:
        logger.warning(f"无法加载配置，使用默认值: {e}")
        return {}

# 默认配置（作为 fallback）
_DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.7
_DEFAULT_TIMEZONE = "Asia/Shanghai"
_DEFAULT_FISCAL_YEAR_START_MONTH = 1
_DEFAULT_MAX_SCHEMA_TOKENS = 2000
_DEFAULT_MAX_FEW_SHOT_EXAMPLES = 3
_DEFAULT_SIMPLE_QUERY_MODEL_ID = "custom-deepseek-r1"

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

def get_confidence_blend_weights() -> dict[str, float]:
    """获取置信度融合权重。

    Returns:
        dict with keys: llm_weight, upstream_weight, divergence_threshold
    """
    defaults = {
        "llm_weight": 0.6,
        "upstream_weight": 0.4,
        "divergence_threshold": 0.3,
    }
    configured = _get_config().get("confidence_blend", {})
    return {k: configured.get(k, v) for k, v in defaults.items()}


def get_simple_query_model_id() -> str:
    """获取简单查询优先使用的模型 ID。"""
    model_id = _get_config().get("simple_query_model_id", _DEFAULT_SIMPLE_QUERY_MODEL_ID)
    return str(model_id or _DEFAULT_SIMPLE_QUERY_MODEL_ID)

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
        field_candidates: list[FieldCandidate],
        current_date: Optional[date] = None,
        timezone: Optional[str] = None,
        fiscal_year_start_month: Optional[int] = None,
        history: Optional[list[dict[str, str]]] = None,
        few_shot_examples: Optional[list[FewShotExample]] = None,
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
        on_partial: Optional[Callable[[dict[str, Any]], Awaitable[None]]] = None,
        on_thinking: Optional[Callable[[str], Awaitable[None]]] = None,
        return_thinking: bool = False,
    ) -> "SemanticOutput | tuple[SemanticOutput, str]":
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
            return_thinking=False 时返回 SemanticOutput 实例；
            return_thinking=True 时返回 (SemanticOutput, thinking_text) 元组。
        
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
        
        # 2. 构建 Prompt
        prompt = self._prompt_builder.build(
            question=question,
            field_candidates=field_candidates,
            config=config,
            history=history,
            few_shot_examples=few_shot_examples,
        )
        
        # 3. 构建消息
        messages: list[BaseMessage] = [
            HumanMessage(content=prompt),
        ]
        
        # 4. 调用 LLM
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
        
        # 5. 后处理由 semantic_understanding_node 统一执行（_post_process_semantic_output）
        
        # 6. 设置澄清来源
        if result.needs_clarification:
            result.clarification_source = ClarificationSource.SEMANTIC_UNDERSTANDING
        
        logger.debug(f"语义理解完成，query_id: {result.query_id}")
        
        if return_thinking:
            return result, thinking
        return result
    
    
__all__ = [
    "SemanticUnderstanding",
    "get_low_confidence_threshold",
    "get_default_timezone",
    "get_fiscal_year_start_month",
    "get_max_schema_tokens",
    "get_max_few_shot_examples",
    "get_simple_query_model_id",
]
