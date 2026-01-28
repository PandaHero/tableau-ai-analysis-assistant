# -*- coding: utf-8 -*-
"""
SemanticUnderstanding 单元测试

测试语义理解核心组件的功能：
- 基本语义理解
- 流式输出
- 自检结果处理
- 澄清来源追踪

注意：使用真实 LLM (DeepSeek)，不使用 Mock
"""
import pytest
from datetime import date
from typing import List

from analytics_assistant.src.agents.semantic_parser.components.semantic_understanding import (
    SemanticUnderstanding,
    get_low_confidence_threshold,
)
from analytics_assistant.src.agents.semantic_parser.schemas.intermediate import (
    FieldCandidate,
    FewShotExample,
)
from analytics_assistant.src.agents.semantic_parser.schemas.output import (
    SemanticOutput,
    ClarificationSource,
)


# ═══════════════════════════════════════════════════════════════════════════
# 测试数据
# ═══════════════════════════════════════════════════════════════════════════

def create_sample_field_candidates() -> List[FieldCandidate]:
    """创建示例字段候选列表"""
    return [
        FieldCandidate(
            field_name="Sales",
            field_caption="销售额",
            field_type="measure",
            data_type="number",
            description="销售金额",
            sample_values=["1000", "2000", "3000"],
            confidence=0.95,
            match_type="exact",
        ),
        FieldCandidate(
            field_name="Profit",
            field_caption="利润",
            field_type="measure",
            data_type="number",
            description="利润金额",
            sample_values=["100", "200", "300"],
            confidence=0.90,
            match_type="semantic",
        ),
        FieldCandidate(
            field_name="Region",
            field_caption="地区",
            field_type="dimension",
            data_type="string",
            description="销售地区",
            sample_values=["华东", "华北", "华南"],
            confidence=0.92,
            match_type="exact",
        ),
        FieldCandidate(
            field_name="Order_Date",
            field_caption="订单日期",
            field_type="dimension",
            data_type="date",
            description="订单日期",
            sample_values=["2024-01-01", "2024-02-01"],
            confidence=0.88,
            match_type="semantic",
            category="time",
        ),
    ]


# ═══════════════════════════════════════════════════════════════════════════
# 测试类
# ═══════════════════════════════════════════════════════════════════════════

class TestSemanticUnderstanding:
    """SemanticUnderstanding 测试类"""
    
    @pytest.fixture
    def understanding(self):
        """创建 SemanticUnderstanding 实例"""
        return SemanticUnderstanding()
    
    @pytest.fixture
    def field_candidates(self):
        """创建字段候选列表"""
        return create_sample_field_candidates()
    
    @pytest.mark.asyncio
    async def test_simple_query(self, understanding, field_candidates):
        """测试简单查询"""
        result = await understanding.understand(
            question="各地区的销售额是多少？",
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
        )
        
        # 验证基本结构
        assert isinstance(result, SemanticOutput)
        assert result.query_id is not None
        assert result.restated_question is not None
        assert len(result.restated_question) > 0
        
        # 验证自检结果
        assert result.self_check is not None
        assert 0 <= result.self_check.overall_confidence <= 1
    
    @pytest.mark.asyncio
    async def test_complex_query_with_ratio(self, understanding, field_candidates):
        """测试包含比率计算的复杂查询"""
        result = await understanding.understand(
            question="各地区的利润率是多少？",
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
        )
        
        # 验证基本结构
        assert isinstance(result, SemanticOutput)
        assert result.restated_question is not None
        
        # 复杂查询应该有计算逻辑
        # 注意：LLM 可能不总是识别为复杂查询，这里只验证结构
        assert result.self_check is not None
    
    @pytest.mark.asyncio
    async def test_query_with_time_expression(self, understanding, field_candidates):
        """测试包含时间表达式的查询"""
        result = await understanding.understand(
            question="上个月各地区的销售额是多少？",
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
        )
        
        # 验证基本结构
        assert isinstance(result, SemanticOutput)
        assert result.restated_question is not None
        
        # 时间表达式应该被解析
        # 注意：具体的时间范围取决于 LLM 的理解
        assert result.self_check is not None
        assert result.self_check.time_range_confidence >= 0
    
    @pytest.mark.asyncio
    async def test_clarification_source_tracking(self, understanding, field_candidates):
        """测试澄清来源追踪"""
        # 使用模糊的问题，可能触发澄清
        result = await understanding.understand(
            question="数据",  # 非常模糊的问题
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
        )
        
        # 如果需要澄清，来源应该是 SEMANTIC_UNDERSTANDING
        if result.needs_clarification:
            assert result.clarification_source == ClarificationSource.SEMANTIC_UNDERSTANDING
            assert result.clarification_question is not None
    
    @pytest.mark.asyncio
    async def test_self_check_low_confidence_flagging(self, understanding, field_candidates):
        """测试低置信度标记"""
        result = await understanding.understand(
            question="各地区的销售额是多少？",
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
        )
        
        # 验证自检结果
        self_check = result.self_check
        low_confidence_threshold = get_low_confidence_threshold()
        
        # 如果有低置信度字段，potential_issues 应该非空
        has_low_confidence = (
            self_check.field_mapping_confidence < low_confidence_threshold or
            self_check.time_range_confidence < low_confidence_threshold or
            self_check.computation_confidence < low_confidence_threshold or
            self_check.overall_confidence < low_confidence_threshold
        )
        
        if has_low_confidence:
            assert len(self_check.potential_issues) > 0
    
    @pytest.mark.asyncio
    async def test_streaming_output(self, understanding, field_candidates):
        """测试流式输出"""
        tokens_received = []
        
        async def on_token(token: str):
            tokens_received.append(token)
        
        result = await understanding.understand(
            question="各地区的销售额是多少？",
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
            on_token=on_token,
        )
        
        # 验证收到了 token
        assert len(tokens_received) > 0
        
        # 验证结果
        assert isinstance(result, SemanticOutput)
    
    @pytest.mark.asyncio
    async def test_with_history(self, understanding, field_candidates):
        """测试带对话历史的查询"""
        history = [
            {"role": "user", "content": "我想看销售数据"},
            {"role": "assistant", "content": "好的，请问您想看哪个时间段的销售数据？"},
        ]
        
        result = await understanding.understand(
            question="上个月的",
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
            history=history,
        )
        
        # 验证基本结构
        assert isinstance(result, SemanticOutput)
        assert result.restated_question is not None
        
        # 重述的问题应该包含完整上下文
        # 注意：具体内容取决于 LLM 的理解


class TestSemanticUnderstandingEdgeCases:
    """边界条件测试"""
    
    @pytest.fixture
    def understanding(self):
        """创建 SemanticUnderstanding 实例"""
        return SemanticUnderstanding()
    
    @pytest.mark.asyncio
    async def test_empty_field_candidates(self, understanding):
        """测试空字段候选列表"""
        result = await understanding.understand(
            question="销售额是多少？",
            field_candidates=[],
            current_date=date(2025, 1, 28),
        )
        
        # 应该仍然返回结果，但可能需要澄清
        assert isinstance(result, SemanticOutput)
    
    @pytest.mark.asyncio
    async def test_very_long_question(self, understanding):
        """测试很长的问题"""
        long_question = "我想查看" + "销售额" * 50 + "的数据"
        
        field_candidates = create_sample_field_candidates()
        
        result = await understanding.understand(
            question=long_question,
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
        )
        
        # 应该仍然返回结果
        assert isinstance(result, SemanticOutput)
    
    @pytest.mark.asyncio
    async def test_special_characters_in_question(self, understanding):
        """测试问题中包含特殊字符"""
        field_candidates = create_sample_field_candidates()
        
        result = await understanding.understand(
            question="销售额 > 1000 的地区有哪些？",
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
        )
        
        # 应该仍然返回结果
        assert isinstance(result, SemanticOutput)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
