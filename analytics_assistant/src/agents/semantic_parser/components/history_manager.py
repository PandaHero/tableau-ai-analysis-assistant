# -*- coding: utf-8 -*-
"""
HistoryManager - 对话历史管理组件

核心职责：
1. 对话历史 Token 计数
2. 历史截断（保留最近消息）
3. 增量状态更新（多轮对话合并）

设计原则：
- 截断时保留最近的消息
- 支持配置化的 MAX_HISTORY_TOKENS
- 与 SummarizationMiddleware 兼容

配置来源：analytics_assistant/config/app.yaml -> semantic_parser.token_optimization

Requirements: 12.4 - 对话历史管理
Property 17: History Truncation
Property 9: Incremental State Update
"""
import logging
from datetime import datetime
from typing import Any, Optional

from analytics_assistant.src.infra.config import get_config

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════════════════

def _get_token_optimization_config() -> dict[str, Any]:
    """获取 token_optimization 配置。"""
    try:
        return get_config().get_token_optimization_config()
    except Exception as e:
        logger.warning(f"无法加载配置，使用默认值: {e}")
        return {}

# 默认配置（作为 fallback）
_DEFAULT_MAX_HISTORY_TOKENS = 1000
_DEFAULT_USE_SUMMARIZATION = True
_DEFAULT_CHARS_PER_TOKEN = 2  # 中文约 2 字符/token

def get_max_history_tokens() -> int:
    """获取对话历史最大 token 数。"""
    return _get_token_optimization_config().get(
        "max_history_tokens", _DEFAULT_MAX_HISTORY_TOKENS
    )

def get_use_summarization() -> bool:
    """获取是否使用历史摘要。"""
    return _get_token_optimization_config().get(
        "use_summarization", _DEFAULT_USE_SUMMARIZATION
    )

# ═══════════════════════════════════════════════════════════════════════════
# Token 计数工具
# ═══════════════════════════════════════════════════════════════════════════

def estimate_tokens(text: str, chars_per_token: int = _DEFAULT_CHARS_PER_TOKEN) -> int:
    """估算文本的 token 数
    
    对中文和非中文字符分别估算：
    - 中文字符（CJK Unified Ideographs）：约 1.5 字符/token
    - 非中文字符（英文、数字、标点等）：约 4 字符/token
    
    Args:
        text: 输入文本
        chars_per_token: 备用每 token 字符数（当无法区分时使用）
    
    Returns:
        估算的 token 数
    """
    if not text:
        return 0
    cjk_count = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff')
    non_cjk_count = len(text) - cjk_count
    tokens = cjk_count / 1.5 + non_cjk_count / 4
    return max(1, int(tokens))

def estimate_message_tokens(message: dict[str, str]) -> int:
    """估算单条消息的 token 数
    
    包括 role 和 content 的 token 数，
    加上消息格式开销（约 4 tokens）。
    
    Args:
        message: 消息字典，包含 role 和 content
    
    Returns:
        估算的 token 数
    """
    role = message.get("role", "")
    content = message.get("content", "")
    
    # 消息格式开销（role 标签等）
    overhead = 4
    
    return estimate_tokens(role) + estimate_tokens(content) + overhead

def estimate_history_tokens(history: list[dict[str, str]]) -> int:
    """估算对话历史的总 token 数
    
    Args:
        history: 对话历史列表
    
    Returns:
        估算的总 token 数
    """
    if not history:
        return 0
    return sum(estimate_message_tokens(msg) for msg in history)

# ═══════════════════════════════════════════════════════════════════════════
# HistoryManager 类
# ═══════════════════════════════════════════════════════════════════════════

class HistoryManager:
    """对话历史管理器
    
    负责管理对话历史的 token 限制和截断。
    
    核心功能：
    1. 检查历史是否超过 MAX_HISTORY_TOKENS
    2. 截断历史（保留最近消息）
    3. 增量状态更新（合并新信息）
    
    Attributes:
        max_history_tokens: 最大历史 token 数
        use_summarization: 是否使用摘要（预留）
    
    Examples:
        >>> manager = HistoryManager()
        >>> history = [
        ...     {"role": "user", "content": "我想看销售数据"},
        ...     {"role": "assistant", "content": "好的，请问您想看哪个时间段？"},
        ...     {"role": "user", "content": "上个月的"},
        ... ]
        >>> truncated = manager.truncate_history(history)
    """
    
    def __init__(
        self,
        max_history_tokens: Optional[int] = None,
        use_summarization: Optional[bool] = None,
    ):
        """初始化 HistoryManager
        
        Args:
            max_history_tokens: 最大历史 token 数（None 从配置读取）
            use_summarization: 是否使用摘要（None 从配置读取）
        """
        self._max_history_tokens = max_history_tokens or get_max_history_tokens()
        self._use_summarization = use_summarization if use_summarization is not None else get_use_summarization()
    
    @property
    def max_history_tokens(self) -> int:
        """获取最大历史 token 数"""
        return self._max_history_tokens
    
    @property
    def use_summarization(self) -> bool:
        """获取是否使用摘要"""
        return self._use_summarization
    
    def check_history_tokens(
        self,
        history: Optional[list[dict[str, str]]],
    ) -> tuple[int, bool]:
        """检查历史 token 数是否超过限制
        
        Args:
            history: 对话历史列表
        
        Returns:
            (token_count, exceeds_limit) 元组
        """
        if not history:
            return 0, False
        
        token_count = estimate_history_tokens(history)
        exceeds_limit = token_count > self._max_history_tokens
        
        if exceeds_limit:
            logger.debug(
                f"对话历史超过 token 限制: {token_count} > {self._max_history_tokens}"
            )
        
        return token_count, exceeds_limit
    
    def truncate_history(
        self,
        history: Optional[list[dict[str, str]]],
        max_tokens: Optional[int] = None,
    ) -> list[dict[str, str]]:
        """截断对话历史（保留最近消息）
        
        从最新的消息开始保留，直到达到 token 限制。
        这确保了最近的上下文被保留。
        
        Property 17: History Truncation
        *For any* conversation history exceeding MAX_HISTORY_TOKENS, 
        the truncated history SHALL preserve the most recent messages.
        
        Args:
            history: 对话历史列表
            max_tokens: 最大 token 数（None 使用配置值）
        
        Returns:
            截断后的历史列表（保留最近消息）
        """
        if not history:
            return []
        
        max_tokens = max_tokens or self._max_history_tokens
        
        # 检查是否需要截断
        total_tokens = estimate_history_tokens(history)
        if total_tokens <= max_tokens:
            return history
        
        # 从最新消息开始保留
        collected: list[dict[str, str]] = []
        current_tokens = 0
        
        # 反向遍历（从最新到最旧）
        for msg in reversed(history):
            msg_tokens = estimate_message_tokens(msg)
            
            if current_tokens + msg_tokens > max_tokens:
                # 达到限制，停止添加
                break
            
            collected.append(msg)
            current_tokens += msg_tokens
        
        # 反转恢复时间顺序
        truncated = list(reversed(collected))
        
        logger.info(
            f"对话历史已截断: {len(history)} -> {len(truncated)} 条消息, "
            f"{total_tokens} -> {current_tokens} tokens"
        )
        
        return truncated
    
    def merge_state(
        self,
        existing_state: dict[str, Any],
        new_info: dict[str, Any],
    ) -> dict[str, Any]:
        """增量状态更新（合并新信息）
        
        Property 9: Incremental State Update
        *For any* multi-turn conversation, providing new information 
        SHALL merge with existing state without losing previously 
        confirmed information.
        
        合并规则：
        1. 新信息覆盖旧信息（同 key）
        2. 列表类型字段追加（如 confirmed_filters）
        3. 保留已确认的信息
        
        Args:
            existing_state: 现有状态
            new_info: 新信息
        
        Returns:
            合并后的状态
        """
        if not existing_state:
            return new_info.copy() if new_info else {}
        
        if not new_info:
            return existing_state.copy()
        
        merged = existing_state.copy()
        
        # 需要追加而非覆盖的列表字段
        append_fields = {
            "confirmed_filters",  # 多轮筛选值确认累积
            "error_history",      # 错误历史累积
        }
        
        for key, value in new_info.items():
            if key in append_fields and isinstance(value, list):
                # 列表字段：追加
                existing_list = merged.get(key, [])
                if isinstance(existing_list, list):
                    merged[key] = existing_list + value
                else:
                    merged[key] = value
            else:
                # 其他字段：覆盖
                merged[key] = value
        
        return merged
    
    def format_history_for_prompt(
        self,
        history: Optional[list[dict[str, str]]],
        max_tokens: Optional[int] = None,
    ) -> str:
        """格式化对话历史用于 Prompt
        
        先截断历史，再格式化为字符串。
        
        Args:
            history: 对话历史列表
            max_tokens: 最大 token 数（None 使用配置值）
        
        Returns:
            格式化的历史字符串，或空字符串
        """
        if not history:
            return ""
        
        # 先截断
        truncated = self.truncate_history(history, max_tokens)
        
        if not truncated:
            return ""
        
        # 格式化
        lines = ["<conversation_history>"]
        for msg in truncated:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            lines.append(f"[{role}]: {content}")
        lines.append("</conversation_history>")
        
        return "\n".join(lines)

# ═══════════════════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════════════════

# 全局单例
_history_manager: Optional[HistoryManager] = None

def get_history_manager() -> HistoryManager:
    """获取全局 HistoryManager 单例"""
    global _history_manager
    if _history_manager is None:
        _history_manager = HistoryManager()
    return _history_manager

def truncate_history(
    history: Optional[list[dict[str, str]]],
    max_tokens: Optional[int] = None,
) -> list[dict[str, str]]:
    """便捷函数：截断对话历史
    
    Args:
        history: 对话历史列表
        max_tokens: 最大 token 数（None 使用配置值）
    
    Returns:
        截断后的历史列表
    """
    return get_history_manager().truncate_history(history, max_tokens)

def check_history_tokens(
    history: Optional[list[dict[str, str]]],
) -> tuple[int, bool]:
    """便捷函数：检查历史 token 数
    
    Args:
        history: 对话历史列表
    
    Returns:
        (token_count, exceeds_limit) 元组
    """
    return get_history_manager().check_history_tokens(history)

__all__ = [
    "HistoryManager",
    "get_history_manager",
    "truncate_history",
    "check_history_tokens",
    "estimate_tokens",
    "estimate_message_tokens",
    "estimate_history_tokens",
    "get_max_history_tokens",
    "get_use_summarization",
]
