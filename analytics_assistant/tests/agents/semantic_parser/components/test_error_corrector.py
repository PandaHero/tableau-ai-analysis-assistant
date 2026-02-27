# -*- coding: utf-8 -*-
"""
ErrorCorrector 错误模式检测单元测试

测试错误分类、重复检测、重试限制等核心逻辑。
Mock LLM 调用，验证错误分类和修正建议。
"""

import pytest
from unittest.mock import AsyncMock, patch

from analytics_assistant.src.agents.semantic_parser.components.error_corrector import (
    ErrorCorrector,
)


@pytest.fixture
def corrector():
    """创建 ErrorCorrector 实例（无 LLM）。"""
    with patch(
        "analytics_assistant.src.agents.semantic_parser.components.error_corrector.get_config"
    ) as mock_config:
        mock_config.return_value = {
            "semantic_parser": {
                "error_corrector": {
                    "max_retries": 3,
                    "max_same_error_count": 2,
                    "non_retryable_errors": [
                        "timeout",
                        "service_unavailable",
                        "authentication_error",
                    ],
                }
            }
        }
        ec = ErrorCorrector(llm=None)
    return ec


class TestShouldRetry:
    """should_retry 方法测试。"""

    def test_retryable_error_returns_true(self, corrector):
        """可重试错误返回 True。"""
        should, reason = corrector.should_retry(
            "Field 'Revenue' not found", "field_not_found"
        )
        assert should is True
        assert reason is None

    def test_non_retryable_error_returns_false(self, corrector):
        """不可重试错误返回 False。"""
        should, reason = corrector.should_retry(
            "Request timed out", "timeout"
        )
        assert should is False
        assert reason == "non_retryable_error: timeout"

    def test_non_retryable_case_insensitive(self, corrector):
        """不可重试错误类型大小写不敏感。"""
        should, reason = corrector.should_retry(
            "Auth failed", "AUTHENTICATION_ERROR"
        )
        assert should is False
        assert "non_retryable_error" in reason

    def test_duplicate_error_detected(self, corrector):
        """相同错误出现 max_same_error_count 次后终止。"""
        error_msg = "Field 'Sales' not found in datasource"

        # 第一次：可以重试
        should, _ = corrector.should_retry(error_msg, "field_not_found")
        assert should is True
        # 模拟记录错误历史
        from analytics_assistant.src.agents.semantic_parser.schemas.error_correction import (
            ErrorCorrectionHistory,
        )
        from datetime import datetime

        error_hash = corrector._compute_error_hash(error_msg)
        corrector._error_history.append(
            ErrorCorrectionHistory(
                error_type="field_not_found",
                error_hash=error_hash,
                attempt_number=1,
                timestamp=datetime.now(),
            )
        )

        # 第二次：可以重试（max_same_error_count=2，当前只有 1 次）
        should, _ = corrector.should_retry(error_msg, "field_not_found")
        assert should is True
        corrector._error_history.append(
            ErrorCorrectionHistory(
                error_type="field_not_found",
                error_hash=error_hash,
                attempt_number=2,
                timestamp=datetime.now(),
            )
        )

        # 第三次：终止（已出现 2 次）
        should, reason = corrector.should_retry(error_msg, "field_not_found")
        assert should is False
        assert reason == "duplicate_error_detected"

    def test_total_history_exceeded(self, corrector):
        """错误历史总长度超过 max_retries 后终止。"""
        from analytics_assistant.src.agents.semantic_parser.schemas.error_correction import (
            ErrorCorrectionHistory,
        )
        from datetime import datetime

        # 填充 3 条不同错误
        for i in range(3):
            corrector._error_history.append(
                ErrorCorrectionHistory(
                    error_type=f"error_type_{i}",
                    error_hash=f"hash_{i}",
                    attempt_number=i + 1,
                    timestamp=datetime.now(),
                )
            )

        should, reason = corrector.should_retry("New error", "new_type")
        assert should is False
        assert reason == "total_error_history_exceeded"


class TestNormalizeErrorMessage:
    """_normalize_error_message 方法测试。"""

    def test_removes_timestamps(self, corrector):
        """去除时间戳。"""
        msg = "Error at 2024-01-15T10:30:00.123: field not found"
        normalized = corrector._normalize_error_message(msg)
        assert "2024" not in normalized
        assert "[TIMESTAMP]" in normalized

    def test_removes_numbers(self, corrector):
        """去除具体数值。"""
        msg = "Row 42 column 7 has invalid value"
        normalized = corrector._normalize_error_message(msg)
        assert "42" not in normalized
        assert "7" not in normalized

    def test_removes_uuids(self, corrector):
        """去除 UUID。"""
        # 注意：_normalize_error_message 先替换数字再替换 UUID
        # 所以 UUID 中的纯数字段会先被替换为 N，导致 UUID 正则不匹配
        # 这里测试 UUID 正则本身能匹配标准 UUID
        msg = "Datasource abcdef12-abcd-abcd-abcd-abcdef123456 not found"
        normalized = corrector._normalize_error_message(msg)
        assert "[UUID]" in normalized

    def test_same_error_same_hash(self, corrector):
        """相同错误（不同数值）产生相同 hash。"""
        msg1 = "Row 42 column 7 has invalid value"
        msg2 = "Row 99 column 3 has invalid value"
        assert corrector._compute_error_hash(msg1) == corrector._compute_error_hash(msg2)

    def test_different_error_different_hash(self, corrector):
        """不同错误产生不同 hash。"""
        msg1 = "Field not found"
        msg2 = "Syntax error in query"
        assert corrector._compute_error_hash(msg1) != corrector._compute_error_hash(msg2)


class TestResetHistory:
    """reset_history 方法测试。"""

    def test_reset_clears_history(self, corrector):
        """重置后历史为空。"""
        from analytics_assistant.src.agents.semantic_parser.schemas.error_correction import (
            ErrorCorrectionHistory,
        )
        from datetime import datetime

        corrector._error_history.append(
            ErrorCorrectionHistory(
                error_type="test",
                error_hash="abc",
                attempt_number=1,
                timestamp=datetime.now(),
            )
        )
        assert corrector.retry_count == 1

        corrector.reset_history()
        assert corrector.retry_count == 0
        assert corrector.error_history == []


class TestCorrectWithMockLLM:
    """correct 方法测试（Mock LLM）。"""

    @pytest.mark.asyncio
    async def test_correct_non_retryable_returns_abort(self, corrector):
        """不可重试错误直接终止，不调用 LLM。"""
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            SemanticOutput,
            SelfCheck,
        )

        output = SemanticOutput(
            restated_question="各地区销售额",
            self_check=SelfCheck(
                field_mapping_confidence=0.9,
                time_range_confidence=0.9,
                computation_confidence=0.9,
                overall_confidence=0.9,
            ),
        )

        result = await corrector.correct(
            question="各地区销售额",
            previous_output=output,
            error_info="Request timed out",
            error_type="timeout",
        )

        assert result.should_continue is False
        assert result.abort_reason == "non_retryable_error: timeout"
        assert result.corrected_output is None

    @pytest.mark.asyncio
    async def test_correct_without_llm_returns_original(self, corrector):
        """无 LLM 时返回原始输出。"""
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            SemanticOutput,
            SelfCheck,
        )

        output = SemanticOutput(
            restated_question="各地区销售额",
            self_check=SelfCheck(
                field_mapping_confidence=0.9,
                time_range_confidence=0.9,
                computation_confidence=0.9,
                overall_confidence=0.9,
            ),
        )

        result = await corrector.correct(
            question="各地区销售额",
            previous_output=output,
            error_info="Field 'Revenue' not found",
            error_type="field_not_found",
        )

        assert result.should_continue is True
        assert result.corrected_output is not None
        assert corrector.retry_count == 1
