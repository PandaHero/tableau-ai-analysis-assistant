# -*- coding: utf-8 -*-
"""
历史截断正确性属性测试

Property 14: 历史截断正确性
- 截断结果总 token 不超限
- 保留最新消息
- 顺序一致
"""
from hypothesis import given, strategies as st, assume

from analytics_assistant.src.agents.semantic_parser.components.history_manager import (
    HistoryManager,
    estimate_history_tokens,
    estimate_message_tokens,
)

# 消息策略
_message_strategy = st.fixed_dictionaries({
    "role": st.sampled_from(["user", "assistant"]),
    "content": st.text(min_size=1, max_size=200),
})

_history_strategy = st.lists(_message_strategy, min_size=1, max_size=30)


class TestHistoryTruncation:
    """Property 14: 历史截断正确性"""

    @given(history=_history_strategy, max_tokens=st.integers(min_value=10, max_value=5000))
    def test_truncated_tokens_within_limit(self, history: list, max_tokens: int) -> None:
        """截断后总 token 不超过限制"""
        manager = HistoryManager()
        truncated = manager.truncate_history(history, max_tokens=max_tokens)
        total = estimate_history_tokens(truncated)
        assert total <= max_tokens, (
            f"截断后 token 数 {total} 超过限制 {max_tokens}"
        )

    @given(history=_history_strategy, max_tokens=st.integers(min_value=10, max_value=5000))
    def test_preserves_most_recent_messages(self, history: list, max_tokens: int) -> None:
        """截断结果是原始历史的尾部子序列"""
        manager = HistoryManager()
        truncated = manager.truncate_history(history, max_tokens=max_tokens)
        if not truncated:
            return
        # 截断结果应该是 history 的尾部连续子序列
        n = len(truncated)
        assert truncated == history[-n:], "截断结果应为原始历史的尾部子序列"

    @given(history=_history_strategy)
    def test_no_truncation_when_within_limit(self, history: list) -> None:
        """总 token 未超限时不截断"""
        total = estimate_history_tokens(history)
        manager = HistoryManager()
        truncated = manager.truncate_history(history, max_tokens=total + 100)
        assert truncated == history, "未超限时应返回完整历史"

    @given(history=_history_strategy, max_tokens=st.integers(min_value=10, max_value=5000))
    def test_order_preserved(self, history: list, max_tokens: int) -> None:
        """截断后消息顺序与原始一致"""
        manager = HistoryManager()
        truncated = manager.truncate_history(history, max_tokens=max_tokens)
        if len(truncated) < 2:
            return
        # 检查截断结果中的消息在原始历史中的相对顺序
        indices = []
        for msg in truncated:
            for i, orig in enumerate(history):
                if orig is msg:
                    indices.append(i)
                    break
        assert indices == sorted(indices), "消息顺序应保持一致"
