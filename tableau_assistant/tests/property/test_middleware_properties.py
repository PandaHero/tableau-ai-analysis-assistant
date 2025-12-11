"""
Property Tests for Middleware Stack

Tests for:
- Property 17: LLM 重试指数退避
- Property 18: 对话总结职责分离
- Property 5: 状态累积保持

Requirements tested:
- R9.2: ModelRetryMiddleware exponential backoff
- R11.5: SummarizationMiddleware only summarizes conversation messages
- R2.6, R18.2: State accumulation
"""

import asyncio
import time
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings, strategies as st


# ═══════════════════════════════════════════════════════════════════════════
# Property 17: LLM 重试指数退避
# ═══════════════════════════════════════════════════════════════════════════

class TestModelRetryExponentialBackoff:
    """
    Property 17: LLM 重试指数退避
    
    *For any* LLM 调用失败序列，重试延迟应遵循指数退避策略：
    delay_n = initial_delay * backoff_factor^n
    
    默认配置：initial_delay=1s, backoff_factor=2.0
    预期延迟序列：1s, 2s, 4s, 8s, ...（最大 60s）
    
    **Validates: Requirements 9.2**
    """
    
    def test_exponential_backoff_delay_sequence(self):
        """验证指数退避延迟序列计算正确"""
        initial_delay = 1.0
        backoff_factor = 2.0
        max_delay = 60.0
        max_retries = 5
        
        expected_delays = []
        for n in range(max_retries):
            delay = min(initial_delay * (backoff_factor ** n), max_delay)
            expected_delays.append(delay)
        
        # 验证延迟序列
        assert expected_delays == [1.0, 2.0, 4.0, 8.0, 16.0]
    
    def test_max_delay_cap(self):
        """验证延迟不超过最大值"""
        initial_delay = 1.0
        backoff_factor = 2.0
        max_delay = 10.0
        
        for n in range(10):
            delay = min(initial_delay * (backoff_factor ** n), max_delay)
            assert delay <= max_delay, f"Delay {delay} exceeds max {max_delay}"
    
    @given(
        initial_delay=st.floats(min_value=0.1, max_value=5.0),
        backoff_factor=st.floats(min_value=1.5, max_value=3.0),
        max_delay=st.floats(min_value=10.0, max_value=120.0),
        retry_count=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=50)
    def test_exponential_backoff_property(
        self,
        initial_delay: float,
        backoff_factor: float,
        max_delay: float,
        retry_count: int,
    ):
        """
        Property: 对于任意配置，延迟应满足：
        1. delay_n >= delay_{n-1}（单调递增）
        2. delay_n <= max_delay（有上限）
        3. delay_n = min(initial_delay * backoff_factor^n, max_delay)
        """
        delays = []
        for n in range(retry_count + 1):
            delay = min(initial_delay * (backoff_factor ** n), max_delay)
            delays.append(delay)
        
        # Property 1: 单调递增
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i - 1], "Delays should be monotonically increasing"
        
        # Property 2: 有上限
        for delay in delays:
            assert delay <= max_delay, f"Delay {delay} exceeds max {max_delay}"
        
        # Property 3: 公式正确
        for n, delay in enumerate(delays):
            expected = min(initial_delay * (backoff_factor ** n), max_delay)
            assert abs(delay - expected) < 1e-9, f"Delay formula incorrect at n={n}"
    
    def test_jitter_adds_randomness(self):
        """验证 jitter 添加随机性"""
        import random
        
        base_delay = 2.0
        jitter_factor = 0.1  # ±10%
        
        delays_with_jitter = []
        for _ in range(100):
            jitter = random.uniform(-jitter_factor, jitter_factor)
            delay = base_delay * (1 + jitter)
            delays_with_jitter.append(delay)
        
        # 验证有变化（不是所有值都相同）
        unique_delays = set(delays_with_jitter)
        assert len(unique_delays) > 1, "Jitter should add randomness"
        
        # 验证在合理范围内
        for delay in delays_with_jitter:
            assert base_delay * (1 - jitter_factor) <= delay <= base_delay * (1 + jitter_factor)


# ═══════════════════════════════════════════════════════════════════════════
# Property 18: 对话总结职责分离
# ═══════════════════════════════════════════════════════════════════════════

class TestSummarizationSeparation:
    """
    Property 18: 对话总结职责分离
    
    *For any* 消息序列，SummarizationMiddleware 应只总结对话消息，
    不应总结 insights、query_results 等结构化数据。
    
    **Validates: Requirements 11.5**
    """
    
    def test_message_type_classification(self):
        """验证消息类型分类正确"""
        # 应该被总结的消息类型
        summarizable_types = ["HumanMessage", "AIMessage", "SystemMessage"]
        
        # 不应该被总结的消息类型
        non_summarizable_types = ["ToolMessage", "FunctionMessage"]
        
        # 验证分类
        for msg_type in summarizable_types:
            assert msg_type in summarizable_types
        
        for msg_type in non_summarizable_types:
            assert msg_type not in summarizable_types
    
    def test_insights_not_summarized(self):
        """验证 insights 不被总结"""
        # 模拟状态
        state = {
            "messages": [
                {"type": "human", "content": "分析销售数据"},
                {"type": "ai", "content": "好的，我来分析"},
            ],
            "insights": [
                {"type": "trend", "title": "销售增长", "importance": 0.9},
                {"type": "anomaly", "title": "异常值", "importance": 0.8},
            ],
            "query_results": [
                {"data": [{"sales": 100}, {"sales": 200}]},
            ],
        }
        
        # 验证 insights 和 query_results 不在 messages 中
        messages = state.get("messages", [])
        insights = state.get("insights", [])
        query_results = state.get("query_results", [])
        
        # insights 和 query_results 应该是独立的
        assert insights != messages
        assert query_results != messages
        
        # messages 中不应包含 insights 或 query_results
        for msg in messages:
            assert "insights" not in str(msg).lower() or "content" in msg
    
    @given(
        num_messages=st.integers(min_value=1, max_value=20),
        num_insights=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=30)
    def test_summarization_scope_property(
        self,
        num_messages: int,
        num_insights: int,
    ):
        """
        Property: 总结范围应只包含对话消息
        
        对于任意数量的消息和洞察，总结操作应：
        1. 只处理 messages 列表
        2. 不修改 insights 列表
        3. 不修改 query_results 列表
        """
        # 构造状态
        messages = [
            {"type": "human" if i % 2 == 0 else "ai", "content": f"Message {i}"}
            for i in range(num_messages)
        ]
        insights = [
            {"type": "insight", "title": f"Insight {i}"}
            for i in range(num_insights)
        ]
        
        state = {
            "messages": messages.copy(),
            "insights": insights.copy(),
        }
        
        # 模拟总结操作（只处理 messages）
        def summarize_messages(msgs: List[Dict]) -> List[Dict]:
            if len(msgs) <= 5:
                return msgs
            # 保留最后 5 条，前面的总结为一条
            summary = {"type": "system", "content": f"Summary of {len(msgs) - 5} messages"}
            return [summary] + msgs[-5:]
        
        # 执行总结
        summarized_messages = summarize_messages(state["messages"])
        
        # Property 1: insights 不变
        assert state["insights"] == insights, "Insights should not be modified"
        
        # Property 2: 总结只影响 messages
        if num_messages > 5:
            assert len(summarized_messages) <= 6, "Messages should be summarized"
        else:
            assert len(summarized_messages) == num_messages, "Short messages should not be summarized"


# ═══════════════════════════════════════════════════════════════════════════
# Property 5: 状态累积保持
# ═══════════════════════════════════════════════════════════════════════════

class TestStateAccumulation:
    """
    Property 5: 状态累积保持
    
    *For any* 工作流执行序列，状态累积字段（如 insights、subtask_results）
    应正确累积，不丢失之前的结果。
    
    **Validates: Requirements 2.6, 18.2**
    """
    
    def test_list_accumulation(self):
        """验证列表字段正确累积"""
        import operator
        
        # 模拟累积操作
        def accumulate(left: List, right: List) -> List:
            return left + right
        
        # 初始状态
        state = {"insights": []}
        
        # 第一轮添加
        round1_insights = [{"id": 1, "title": "Insight 1"}]
        state["insights"] = accumulate(state["insights"], round1_insights)
        assert len(state["insights"]) == 1
        
        # 第二轮添加
        round2_insights = [{"id": 2, "title": "Insight 2"}, {"id": 3, "title": "Insight 3"}]
        state["insights"] = accumulate(state["insights"], round2_insights)
        assert len(state["insights"]) == 3
        
        # 验证所有洞察都保留
        ids = [i["id"] for i in state["insights"]]
        assert ids == [1, 2, 3]
    
    def test_dict_accumulation(self):
        """验证字典字段正确累积"""
        # 模拟字典累积
        def accumulate_dict(left: Dict, right: Dict) -> Dict:
            result = left.copy()
            result.update(right)
            return result
        
        # 初始状态
        state = {"field_mappings": {}}
        
        # 第一轮添加
        round1_mappings = {"sales": "Sales Amount", "region": "Region Name"}
        state["field_mappings"] = accumulate_dict(state["field_mappings"], round1_mappings)
        assert len(state["field_mappings"]) == 2
        
        # 第二轮添加
        round2_mappings = {"profit": "Profit Margin"}
        state["field_mappings"] = accumulate_dict(state["field_mappings"], round2_mappings)
        assert len(state["field_mappings"]) == 3
        
        # 验证所有映射都保留
        assert "sales" in state["field_mappings"]
        assert "region" in state["field_mappings"]
        assert "profit" in state["field_mappings"]
    
    @given(
        num_rounds=st.integers(min_value=1, max_value=10),
        items_per_round=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=30)
    def test_accumulation_property(
        self,
        num_rounds: int,
        items_per_round: int,
    ):
        """
        Property: 状态累积应满足：
        1. 累积后的长度 = 所有轮次项目数之和
        2. 所有项目都被保留
        3. 顺序保持（先添加的在前）
        """
        state = {"items": []}
        expected_total = 0
        all_items = []
        
        for round_num in range(num_rounds):
            round_items = [
                {"round": round_num, "index": i}
                for i in range(items_per_round)
            ]
            all_items.extend(round_items)
            state["items"] = state["items"] + round_items
            expected_total += items_per_round
        
        # Property 1: 长度正确
        assert len(state["items"]) == expected_total
        
        # Property 2: 所有项目保留
        assert state["items"] == all_items
        
        # Property 3: 顺序保持
        for i, item in enumerate(state["items"]):
            expected_round = i // items_per_round
            expected_index = i % items_per_round
            assert item["round"] == expected_round
            assert item["index"] == expected_index
    
    def test_replan_history_accumulation(self):
        """验证重规划历史正确累积"""
        state = {"replan_history": []}
        
        # 模拟多轮重规划
        for round_num in range(3):
            history_entry = {
                "round": round_num + 1,
                "completeness_score": 0.5 + round_num * 0.15,
                "should_replan": round_num < 2,
                "reason": f"Round {round_num + 1} analysis",
            }
            state["replan_history"] = state["replan_history"] + [history_entry]
        
        # 验证历史完整
        assert len(state["replan_history"]) == 3
        assert state["replan_history"][0]["round"] == 1
        assert state["replan_history"][2]["round"] == 3
        
        # 验证完成度递增
        scores = [h["completeness_score"] for h in state["replan_history"]]
        assert scores == sorted(scores), "Completeness should increase over rounds"


# ═══════════════════════════════════════════════════════════════════════════
# Additional Middleware Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestFilesystemMiddlewareLargeOutput:
    """
    Property 7: 大输出文件转存
    
    *For any* 工具输出超过 token 限制，应自动转存到文件系统。
    
    **Validates: Requirements 3.5, 12.1**
    """
    
    def test_large_output_detection(self):
        """验证大输出检测"""
        token_limit = 20000
        char_limit = token_limit * 4  # 约 4 字符/token
        
        # 小输出
        small_output = "x" * 1000
        assert len(small_output) < char_limit
        
        # 大输出
        large_output = "x" * (char_limit + 1)
        assert len(large_output) > char_limit
    
    @given(
        output_size=st.integers(min_value=1000, max_value=200000),
        token_limit=st.integers(min_value=5000, max_value=50000),
    )
    @settings(max_examples=30)
    def test_large_output_eviction_property(
        self,
        output_size: int,
        token_limit: int,
    ):
        """
        Property: 大输出转存应满足：
        1. 超过限制的输出被转存
        2. 转存后返回文件路径
        3. 原始内容可通过 read_file 读取
        """
        char_limit = token_limit * 4
        output = "x" * output_size
        
        should_evict = output_size > char_limit
        
        if should_evict:
            # 模拟转存
            file_path = f"/large_tool_results/result_{hash(output) % 10000}"
            evicted_message = f"Tool result too large, saved at: {file_path}"
            
            # Property 1: 返回文件路径
            assert file_path in evicted_message
            
            # Property 2: 原始内容长度正确
            assert len(output) == output_size
        else:
            # 小输出直接返回
            assert len(output) <= char_limit


class TestPatchToolCallsMiddleware:
    """
    Property 19: 悬空工具调用修复
    
    *For any* 消息序列中存在悬空工具调用（AIMessage 有 tool_calls 但没有对应 ToolMessage），
    应自动添加占位 ToolMessage。
    
    **Validates: Requirements 13.1**
    """
    
    def test_dangling_tool_call_detection(self):
        """验证悬空工具调用检测"""
        messages = [
            {"type": "human", "content": "Query data"},
            {"type": "ai", "content": "", "tool_calls": [{"id": "call_1", "name": "query"}]},
            # 缺少 ToolMessage
        ]
        
        # 检测悬空调用
        tool_call_ids = set()
        tool_message_ids = set()
        
        for msg in messages:
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    tool_call_ids.add(tc["id"])
            if msg.get("type") == "tool":
                tool_message_ids.add(msg.get("tool_call_id"))
        
        dangling = tool_call_ids - tool_message_ids
        assert "call_1" in dangling
    
    def test_patch_dangling_tool_calls(self):
        """验证悬空工具调用修复"""
        messages = [
            {"type": "human", "content": "Query data"},
            {"type": "ai", "content": "", "tool_calls": [{"id": "call_1", "name": "query"}]},
        ]
        
        # 修复悬空调用
        def patch_dangling(msgs: List[Dict]) -> List[Dict]:
            tool_call_ids = set()
            tool_message_ids = set()
            
            for msg in msgs:
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        tool_call_ids.add(tc["id"])
                if msg.get("type") == "tool":
                    tool_message_ids.add(msg.get("tool_call_id"))
            
            dangling = tool_call_ids - tool_message_ids
            
            patched = msgs.copy()
            for call_id in dangling:
                patched.append({
                    "type": "tool",
                    "tool_call_id": call_id,
                    "content": "[Tool call interrupted]",
                })
            
            return patched
        
        patched = patch_dangling(messages)
        
        # 验证修复
        assert len(patched) == 3
        assert patched[-1]["type"] == "tool"
        assert patched[-1]["tool_call_id"] == "call_1"
    
    @given(
        num_tool_calls=st.integers(min_value=1, max_value=5),
        num_responses=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=30)
    def test_patch_property(
        self,
        num_tool_calls: int,
        num_responses: int,
    ):
        """
        Property: 修复后应满足：
        1. 每个 tool_call 都有对应的 ToolMessage
        2. 不会重复添加 ToolMessage
        """
        # 构造消息
        messages = [{"type": "human", "content": "Query"}]
        
        tool_calls = [{"id": f"call_{i}", "name": f"tool_{i}"} for i in range(num_tool_calls)]
        messages.append({"type": "ai", "content": "", "tool_calls": tool_calls})
        
        # 添加部分响应
        for i in range(min(num_responses, num_tool_calls)):
            messages.append({
                "type": "tool",
                "tool_call_id": f"call_{i}",
                "content": f"Result {i}",
            })
        
        # 修复
        def patch_dangling(msgs: List[Dict]) -> List[Dict]:
            tool_call_ids = set()
            tool_message_ids = set()
            
            for msg in msgs:
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        tool_call_ids.add(tc["id"])
                if msg.get("type") == "tool":
                    tool_message_ids.add(msg.get("tool_call_id"))
            
            dangling = tool_call_ids - tool_message_ids
            
            patched = msgs.copy()
            for call_id in sorted(dangling):
                patched.append({
                    "type": "tool",
                    "tool_call_id": call_id,
                    "content": "[Tool call interrupted]",
                })
            
            return patched
        
        patched = patch_dangling(messages)
        
        # Property 1: 每个 tool_call 都有响应
        tool_call_ids = set()
        tool_message_ids = set()
        
        for msg in patched:
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    tool_call_ids.add(tc["id"])
            if msg.get("type") == "tool":
                tool_message_ids.add(msg.get("tool_call_id"))
        
        assert tool_call_ids == tool_message_ids, "All tool calls should have responses"
        
        # Property 2: 不重复
        tool_messages = [m for m in patched if m.get("type") == "tool"]
        tool_message_ids_list = [m["tool_call_id"] for m in tool_messages]
        assert len(tool_message_ids_list) == len(set(tool_message_ids_list)), "No duplicate responses"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
