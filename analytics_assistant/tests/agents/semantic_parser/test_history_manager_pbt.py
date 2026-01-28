# -*- coding: utf-8 -*-
"""
Property-Based Tests for HistoryManager

Property 17: History Truncation
Property 9: Incremental State Update

使用 Hypothesis 进行属性测试。
"""
import pytest
from datetime import datetime
from typing import Any, Dict, List

from hypothesis import given, strategies as st, settings, assume


# ═══════════════════════════════════════════════════════════════════════════
# 测试策略
# ═══════════════════════════════════════════════════════════════════════════

# 消息角色策略
role_strategy = st.sampled_from(["user", "assistant"])

# 消息内容策略（中英文混合）
content_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S", "Z"),
        whitelist_characters="，。？！、；：""''（）【】《》"
    ),
    min_size=1,
    max_size=500,
)

# 单条消息策略
message_strategy = st.fixed_dictionaries({
    "role": role_strategy,
    "content": content_strategy,
})

# 对话历史策略
history_strategy = st.lists(message_strategy, min_size=0, max_size=50)

# 状态字段策略
state_value_strategy = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(min_size=0, max_size=100),
    st.lists(st.text(min_size=0, max_size=50), max_size=10),
)

# 状态字典策略
state_strategy = st.dictionaries(
    keys=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_")),
    values=state_value_strategy,
    min_size=0,
    max_size=20,
)


# ═══════════════════════════════════════════════════════════════════════════
# Property 17: History Truncation
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty17HistoryTruncation:
    """
    Property 17: History Truncation
    
    **Validates: Requirements 12.4 (Req 12)**
    
    *For any* conversation history exceeding MAX_HISTORY_TOKENS, 
    the truncated history SHALL preserve the most recent messages.
    """
    
    @given(history=history_strategy, max_tokens=st.integers(min_value=10, max_value=5000))
    @settings(max_examples=100, deadline=None)
    def test_truncation_preserves_most_recent_messages(
        self,
        history: List[Dict[str, str]],
        max_tokens: int,
    ):
        """截断后应保留最近的消息
        
        Property: 截断后的历史应该是原历史的后缀（最近消息）
        """
        from analytics_assistant.src.agents.semantic_parser.components.history_manager import (
            HistoryManager,
            estimate_history_tokens,
        )
        
        manager = HistoryManager(max_history_tokens=max_tokens)
        truncated = manager.truncate_history(history)
        
        # 属性 1: 截断后的历史应该是原历史的后缀
        if truncated and history:
            # 找到截断后历史在原历史中的起始位置
            start_idx = len(history) - len(truncated)
            assert start_idx >= 0, "截断后的历史长度不应超过原历史"
            
            # 验证截断后的历史是原历史的后缀
            for i, msg in enumerate(truncated):
                original_msg = history[start_idx + i]
                assert msg["role"] == original_msg["role"], "消息角色应保持一致"
                assert msg["content"] == original_msg["content"], "消息内容应保持一致"
    
    @given(history=history_strategy, max_tokens=st.integers(min_value=10, max_value=5000))
    @settings(max_examples=100, deadline=None)
    def test_truncation_respects_token_limit(
        self,
        history: List[Dict[str, str]],
        max_tokens: int,
    ):
        """截断后的历史不应超过 token 限制
        
        Property: estimate_history_tokens(truncated) <= max_tokens
        """
        from analytics_assistant.src.agents.semantic_parser.components.history_manager import (
            HistoryManager,
            estimate_history_tokens,
        )
        
        manager = HistoryManager(max_history_tokens=max_tokens)
        truncated = manager.truncate_history(history)
        
        # 属性 2: 截断后的 token 数不应超过限制
        truncated_tokens = estimate_history_tokens(truncated)
        assert truncated_tokens <= max_tokens, (
            f"截断后 token 数 ({truncated_tokens}) 超过限制 ({max_tokens})"
        )
    
    @given(history=history_strategy)
    @settings(max_examples=100, deadline=None)
    def test_no_truncation_when_under_limit(
        self,
        history: List[Dict[str, str]],
    ):
        """当历史未超过限制时不应截断
        
        Property: 如果 estimate_history_tokens(history) <= max_tokens，
                  则 truncated == history
        """
        from analytics_assistant.src.agents.semantic_parser.components.history_manager import (
            HistoryManager,
            estimate_history_tokens,
        )
        
        # 使用足够大的限制
        max_tokens = 100000
        manager = HistoryManager(max_history_tokens=max_tokens)
        
        original_tokens = estimate_history_tokens(history)
        assume(original_tokens <= max_tokens)
        
        truncated = manager.truncate_history(history)
        
        # 属性 3: 未超限时不应截断
        assert len(truncated) == len(history), "未超限时不应截断"
        for i, msg in enumerate(truncated):
            assert msg["role"] == history[i]["role"]
            assert msg["content"] == history[i]["content"]
    
    @given(history=history_strategy)
    @settings(max_examples=50, deadline=None)
    def test_empty_history_returns_empty(
        self,
        history: List[Dict[str, str]],
    ):
        """空历史应返回空列表"""
        from analytics_assistant.src.agents.semantic_parser.components.history_manager import (
            HistoryManager,
        )
        
        manager = HistoryManager()
        
        # 测试空列表
        truncated = manager.truncate_history([])
        assert truncated == [], "空历史应返回空列表"
        
        # 测试 None
        truncated = manager.truncate_history(None)
        assert truncated == [], "None 应返回空列表"
    
    @given(max_tokens=st.integers(min_value=10, max_value=100))
    @settings(max_examples=50, deadline=None)
    def test_at_least_one_message_when_possible(
        self,
        max_tokens: int,
    ):
        """当有消息且 token 限制允许时，至少保留一条消息
        
        Property: 如果 history 非空且第一条消息的 token 数 <= max_tokens，
                  则 truncated 至少有一条消息
        """
        from analytics_assistant.src.agents.semantic_parser.components.history_manager import (
            HistoryManager,
            estimate_message_tokens,
        )
        
        # 创建一条短消息
        short_message = {"role": "user", "content": "hi"}
        history = [short_message]
        
        msg_tokens = estimate_message_tokens(short_message)
        assume(msg_tokens <= max_tokens)
        
        manager = HistoryManager(max_history_tokens=max_tokens)
        truncated = manager.truncate_history(history)
        
        # 属性 4: 至少保留一条消息
        assert len(truncated) >= 1, "应至少保留一条消息"


# ═══════════════════════════════════════════════════════════════════════════
# Property 9: Incremental State Update
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty9IncrementalStateUpdate:
    """
    Property 9: Incremental State Update
    
    **Validates: Requirements 5.5 (Req 6)**
    
    *For any* multi-turn conversation, providing new information 
    SHALL merge with existing state without losing previously 
    confirmed information.
    """
    
    @given(
        existing_state=state_strategy,
        new_info=state_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_merge_preserves_existing_keys(
        self,
        existing_state: Dict[str, Any],
        new_info: Dict[str, Any],
    ):
        """合并后应保留现有状态的所有键
        
        Property: 对于 existing_state 中的每个键，
                  如果 new_info 中没有该键，则 merged 中应保留原值
        """
        from analytics_assistant.src.agents.semantic_parser.components.history_manager import (
            HistoryManager,
        )
        
        manager = HistoryManager()
        merged = manager.merge_state(existing_state, new_info)
        
        # 属性 1: 保留现有键
        for key in existing_state:
            if key not in new_info:
                assert key in merged, f"键 '{key}' 应被保留"
                assert merged[key] == existing_state[key], f"键 '{key}' 的值应保持不变"
    
    @given(
        existing_state=state_strategy,
        new_info=state_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_merge_includes_new_keys(
        self,
        existing_state: Dict[str, Any],
        new_info: Dict[str, Any],
    ):
        """合并后应包含新信息的所有键
        
        Property: 对于 new_info 中的每个键，merged 中应包含该键
        """
        from analytics_assistant.src.agents.semantic_parser.components.history_manager import (
            HistoryManager,
        )
        
        manager = HistoryManager()
        merged = manager.merge_state(existing_state, new_info)
        
        # 属性 2: 包含新键
        for key in new_info:
            assert key in merged, f"新键 '{key}' 应被包含"
    
    @given(
        existing_state=state_strategy,
        new_info=state_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_new_info_overrides_existing(
        self,
        existing_state: Dict[str, Any],
        new_info: Dict[str, Any],
    ):
        """新信息应覆盖现有状态（非追加字段）
        
        Property: 对于非追加字段，new_info 的值应覆盖 existing_state
        """
        from analytics_assistant.src.agents.semantic_parser.components.history_manager import (
            HistoryManager,
        )
        
        manager = HistoryManager()
        merged = manager.merge_state(existing_state, new_info)
        
        # 追加字段列表
        append_fields = {"confirmed_filters", "error_history"}
        
        # 属性 3: 非追加字段应被覆盖
        for key, value in new_info.items():
            if key not in append_fields:
                assert merged[key] == value, f"键 '{key}' 应被新值覆盖"
    
    @given(
        existing_filters=st.lists(
            st.fixed_dictionaries({
                "field_name": st.text(min_size=1, max_size=20),
                "original_value": st.text(min_size=1, max_size=20),
                "confirmed_value": st.text(min_size=1, max_size=20),
            }),
            min_size=0,
            max_size=5,
        ),
        new_filters=st.lists(
            st.fixed_dictionaries({
                "field_name": st.text(min_size=1, max_size=20),
                "original_value": st.text(min_size=1, max_size=20),
                "confirmed_value": st.text(min_size=1, max_size=20),
            }),
            min_size=0,
            max_size=5,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_confirmed_filters_accumulate(
        self,
        existing_filters: List[Dict[str, str]],
        new_filters: List[Dict[str, str]],
    ):
        """confirmed_filters 应累积而非覆盖
        
        Property: merged["confirmed_filters"] 应包含 existing + new 的所有元素
        """
        from analytics_assistant.src.agents.semantic_parser.components.history_manager import (
            HistoryManager,
        )
        
        manager = HistoryManager()
        
        existing_state = {"confirmed_filters": existing_filters}
        new_info = {"confirmed_filters": new_filters}
        
        merged = manager.merge_state(existing_state, new_info)
        
        # 属性 4: confirmed_filters 应累积
        merged_filters = merged.get("confirmed_filters", [])
        expected_count = len(existing_filters) + len(new_filters)
        
        assert len(merged_filters) == expected_count, (
            f"confirmed_filters 应累积: {len(existing_filters)} + {len(new_filters)} = {expected_count}, "
            f"实际: {len(merged_filters)}"
        )
    
    @given(
        existing_errors=st.lists(
            st.fixed_dictionaries({
                "error_hash": st.text(min_size=1, max_size=32),
                "error_type": st.text(min_size=1, max_size=20),
                "message": st.text(min_size=1, max_size=100),
            }),
            min_size=0,
            max_size=5,
        ),
        new_errors=st.lists(
            st.fixed_dictionaries({
                "error_hash": st.text(min_size=1, max_size=32),
                "error_type": st.text(min_size=1, max_size=20),
                "message": st.text(min_size=1, max_size=100),
            }),
            min_size=0,
            max_size=5,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_error_history_accumulates(
        self,
        existing_errors: List[Dict[str, str]],
        new_errors: List[Dict[str, str]],
    ):
        """error_history 应累积而非覆盖
        
        Property: merged["error_history"] 应包含 existing + new 的所有元素
        """
        from analytics_assistant.src.agents.semantic_parser.components.history_manager import (
            HistoryManager,
        )
        
        manager = HistoryManager()
        
        existing_state = {"error_history": existing_errors}
        new_info = {"error_history": new_errors}
        
        merged = manager.merge_state(existing_state, new_info)
        
        # 属性 5: error_history 应累积
        merged_errors = merged.get("error_history", [])
        expected_count = len(existing_errors) + len(new_errors)
        
        assert len(merged_errors) == expected_count, (
            f"error_history 应累积: {len(existing_errors)} + {len(new_errors)} = {expected_count}, "
            f"实际: {len(merged_errors)}"
        )
    
    def test_empty_states_merge(self):
        """空状态合并测试"""
        from analytics_assistant.src.agents.semantic_parser.components.history_manager import (
            HistoryManager,
        )
        
        manager = HistoryManager()
        
        # 空 + 空 = 空
        merged = manager.merge_state({}, {})
        assert merged == {}
        
        # 空 + 非空 = 非空
        merged = manager.merge_state({}, {"key": "value"})
        assert merged == {"key": "value"}
        
        # 非空 + 空 = 非空
        merged = manager.merge_state({"key": "value"}, {})
        assert merged == {"key": "value"}
        
        # None 处理
        merged = manager.merge_state(None, {"key": "value"})
        assert merged == {"key": "value"}
        
        merged = manager.merge_state({"key": "value"}, None)
        assert merged == {"key": "value"}


# ═══════════════════════════════════════════════════════════════════════════
# 单元测试补充
# ═══════════════════════════════════════════════════════════════════════════

class TestHistoryManagerUnit:
    """HistoryManager 单元测试"""
    
    def test_estimate_tokens(self):
        """测试 token 估算"""
        from analytics_assistant.src.agents.semantic_parser.components.history_manager import (
            estimate_tokens,
        )
        
        # 空字符串
        assert estimate_tokens("") == 0
        
        # 短字符串
        assert estimate_tokens("hi") >= 1
        
        # 中文字符串
        tokens = estimate_tokens("你好世界")
        assert tokens >= 1
    
    def test_estimate_message_tokens(self):
        """测试消息 token 估算"""
        from analytics_assistant.src.agents.semantic_parser.components.history_manager import (
            estimate_message_tokens,
        )
        
        msg = {"role": "user", "content": "你好"}
        tokens = estimate_message_tokens(msg)
        
        # 应该包含 role + content + overhead
        assert tokens >= 4  # 至少有 overhead
    
    def test_check_history_tokens(self):
        """测试历史 token 检查"""
        from analytics_assistant.src.agents.semantic_parser.components.history_manager import (
            HistoryManager,
        )
        
        manager = HistoryManager(max_history_tokens=100)
        
        # 空历史
        count, exceeds = manager.check_history_tokens([])
        assert count == 0
        assert exceeds is False
        
        # None
        count, exceeds = manager.check_history_tokens(None)
        assert count == 0
        assert exceeds is False
        
        # 短历史
        short_history = [{"role": "user", "content": "hi"}]
        count, exceeds = manager.check_history_tokens(short_history)
        assert count > 0
        assert exceeds is False
    
    def test_format_history_for_prompt(self):
        """测试历史格式化"""
        from analytics_assistant.src.agents.semantic_parser.components.history_manager import (
            HistoryManager,
        )
        
        manager = HistoryManager()
        
        # 空历史
        formatted = manager.format_history_for_prompt([])
        assert formatted == ""
        
        # None
        formatted = manager.format_history_for_prompt(None)
        assert formatted == ""
        
        # 有内容的历史
        history = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮助你的？"},
        ]
        formatted = manager.format_history_for_prompt(history)
        
        assert "<conversation_history>" in formatted
        assert "</conversation_history>" in formatted
        assert "[user]: 你好" in formatted
        assert "[assistant]: 你好！有什么可以帮助你的？" in formatted
    
    def test_config_loading(self):
        """测试配置加载"""
        from analytics_assistant.src.agents.semantic_parser.components.history_manager import (
            get_max_history_tokens,
            get_use_summarization,
        )
        
        # 应该能获取配置值
        max_tokens = get_max_history_tokens()
        assert isinstance(max_tokens, int)
        assert max_tokens > 0
        
        use_summarization = get_use_summarization()
        assert isinstance(use_summarization, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
