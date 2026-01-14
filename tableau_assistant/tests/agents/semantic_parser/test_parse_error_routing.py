"""测试 Step1/Step2 解析失败的路由逻辑

验证解析失败时能够正确路由到 ReAct 错误处理器。
"""

import pytest
from tableau_assistant.src.agents.semantic_parser.subgraph import (
    route_after_step1,
    route_after_step2,
)
from tableau_assistant.src.agents.semantic_parser.state import SemanticParserState
from tableau_assistant.src.agents.semantic_parser.models.pipeline import QueryError, QueryErrorType


def test_route_after_step1_with_parse_error():
    """测试 Step1 解析失败时路由到 react_error_handler（方案 A）"""
    state = SemanticParserState(
        question="test question",
        step1_parse_error="JSON parse error",
        pipeline_error={
            "type": "step1_parse_error",
            "message": "Step1 输出解析失败",
            "step": "step1",
            "can_retry": True,
        }
    )
    
    result = route_after_step1(state)
    assert result == "react_error_handler", "解析失败应该路由到 react_error_handler（方案 A）"


def test_route_after_step1_with_execution_error():
    """测试 Step1 执行错误时路由到 react_error_handler"""
    state = SemanticParserState(
        question="test question",
        pipeline_error={
            "type": "step1_failed",
            "message": "Step1 execution failed",
            "step": "step1",
            "can_retry": True,
        }
    )
    
    result = route_after_step1(state)
    assert result == "react_error_handler", "执行错误应该路由到 react_error_handler"


def test_route_after_step1_success():
    """测试 Step1 成功时的正常路由"""
    from tableau_assistant.src.core.models import IntentType, HowType
    from tableau_assistant.src.agents.semantic_parser.models import Step1Output, Intent, What, Where
    
    step1_output = Step1Output(
        intent=Intent(type=IntentType.DATA_QUERY, reasoning="test reasoning"),
        how_type=HowType.SIMPLE,
        restated_question="test",
        what=What(measures=[]),
        where=Where(dimensions=[], filters=[]),
    )
    
    state = SemanticParserState(
        question="test question",
        step1_output=step1_output.model_dump(),
    )
    
    result = route_after_step1(state)
    assert result == "pipeline", "SIMPLE 查询应该路由到 pipeline"


def test_route_after_step2_with_parse_error():
    """测试 Step2 解析失败时路由到 react_error_handler（方案 A）"""
    state = SemanticParserState(
        question="test question",
        step2_parse_error="JSON parse error",
        pipeline_error={
            "type": "step2_parse_error",
            "message": "Step2 输出解析失败",
            "step": "step2",
            "can_retry": True,
        }
    )
    
    result = route_after_step2(state)
    assert result == "react_error_handler", "解析失败应该路由到 react_error_handler（方案 A）"


def test_route_after_step2_with_execution_error():
    """测试 Step2 执行错误时路由到 react_error_handler"""
    state = SemanticParserState(
        question="test question",
        pipeline_error={
            "type": "step2_failed",
            "message": "Step2 execution failed",
            "step": "step2",
            "can_retry": True,
        }
    )
    
    result = route_after_step2(state)
    assert result == "react_error_handler", "执行错误应该路由到 react_error_handler"


def test_route_after_step2_success():
    """测试 Step2 成功时的正常路由"""
    state = SemanticParserState(
        question="test question",
        step2_output={"computations": []},
    )
    
    result = route_after_step2(state)
    assert result == "pipeline", "成功时应该路由到 pipeline"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
