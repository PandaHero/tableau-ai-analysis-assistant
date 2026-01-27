# -*- coding: utf-8 -*-
"""
SemanticParserState 测试

验证 SemanticParserState TypedDict 的定义和使用。
"""
import sys
from datetime import datetime
from typing import get_type_hints

# 设置路径
sys.path.insert(0, "..")


def test_state_import():
    """测试导入"""
    from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
    print("✓ SemanticParserState 导入成功")
    return SemanticParserState


def test_state_type_hints(state_class):
    """测试类型提示"""
    hints = get_type_hints(state_class)
    
    expected_fields = [
        # 输入字段
        "question", "chat_history", "datasource_luid", "current_time",
        # 组件输出
        "intent_router_output", "cache_hit", "field_candidates", 
        "few_shot_examples", "semantic_output",
        # 筛选值确认
        "confirmed_filters",
        # 流程控制
        "needs_clarification", "clarification_question", 
        "clarification_options", "clarification_source",
        # 错误处理
        "retry_count", "error_feedback", "pipeline_error",
        "error_history", "correction_abort_reason",
        # 最终输出
        "semantic_query", "parse_result",
        # 调试
        "thinking",
    ]
    
    for field in expected_fields:
        assert field in hints, f"缺少字段: {field}"
    
    print(f"✓ 所有 {len(expected_fields)} 个字段都已定义")
    print(f"  字段列表: {list(hints.keys())}")


def test_state_creation():
    """测试状态创建"""
    from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
    
    # 创建初始状态
    state: SemanticParserState = {
        "question": "上个月各地区的销售额",
        "datasource_luid": "abc-123",
        "current_time": datetime.now().isoformat(),
    }
    
    assert state["question"] == "上个月各地区的销售额"
    assert state["datasource_luid"] == "abc-123"
    print("✓ 状态创建成功")
    
    # 模拟节点更新
    state["intent_router_output"] = {
        "intent_type": "data_query",
        "confidence": 0.95,
        "reason": "包含数据查询关键词",
        "source": "L0_RULE",
    }
    
    assert state["intent_router_output"]["intent_type"] == "data_query"
    print("✓ 状态更新成功")


def test_state_with_schemas():
    """测试与 schemas 模块的集成"""
    from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
    from analytics_assistant.src.agents.semantic_parser.schemas import (
        SemanticOutput,
        SelfCheck,
        What,
        Where,
        FilterConfirmation,
        FieldCandidate,
        FewShotExample,
    )
    from analytics_assistant.src.core.schemas.fields import MeasureField, DimensionField
    from analytics_assistant.src.core.schemas.enums import HowType, AggregationType
    
    # 创建 SemanticOutput
    semantic_output = SemanticOutput(
        restated_question="查询上个月各地区的销售额",
        what=What(measures=[
            MeasureField(field_name="销售额", aggregation=AggregationType.SUM)
        ]),
        where=Where(dimensions=[
            DimensionField(field_name="地区")
        ]),
        how_type=HowType.SIMPLE,
        self_check=SelfCheck(
            field_mapping_confidence=0.95,
            time_range_confidence=0.90,
            computation_confidence=1.0,
            overall_confidence=0.92,
        ),
    )
    
    # 序列化到 state
    state: SemanticParserState = {
        "question": "上个月各地区的销售额",
        "semantic_output": semantic_output.model_dump(),
    }
    
    # 从 state 反序列化
    restored = SemanticOutput.model_validate(state["semantic_output"])
    assert restored.restated_question == "查询上个月各地区的销售额"
    assert len(restored.what.measures) == 1
    assert restored.what.measures[0].field_name == "销售额"
    print("✓ SemanticOutput 序列化/反序列化成功")
    
    # 测试 confirmed_filters
    confirmation = FilterConfirmation(
        field_name="省份",
        original_value="北京",
        confirmed_value="北京市",
    )
    
    state["confirmed_filters"] = [confirmation.model_dump()]
    
    restored_conf = FilterConfirmation.model_validate(state["confirmed_filters"][0])
    assert restored_conf.field_name == "省份"
    assert restored_conf.confirmed_value == "北京市"
    print("✓ FilterConfirmation 序列化/反序列化成功")
    
    # 测试 field_candidates
    candidate = FieldCandidate(
        field_name="销售额",
        field_caption="Sales Amount",
        field_type="measure",
        data_type="float",
        confidence=0.95,
    )
    
    state["field_candidates"] = [candidate.model_dump()]
    
    restored_cand = FieldCandidate.model_validate(state["field_candidates"][0])
    assert restored_cand.field_name == "销售额"
    print("✓ FieldCandidate 序列化/反序列化成功")


def test_error_handling_fields():
    """测试错误处理字段"""
    from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
    
    state: SemanticParserState = {
        "question": "测试问题",
        "retry_count": 0,
        "error_history": [],
    }
    
    # 模拟错误发生
    error = {
        "error_hash": "abc123",
        "error_type": "FieldNotFound",
        "message": "字段 '销售额' 不存在",
        "occurred_at": datetime.now().isoformat(),
    }
    
    state["error_history"].append(error)
    state["retry_count"] = 1
    state["error_feedback"] = "请检查字段名是否正确"
    
    assert len(state["error_history"]) == 1
    assert state["retry_count"] == 1
    print("✓ 错误处理字段测试成功")
    
    # 模拟终止
    state["correction_abort_reason"] = "duplicate_error"
    assert state["correction_abort_reason"] == "duplicate_error"
    print("✓ 错误终止原因字段测试成功")


def test_multi_round_confirmation():
    """测试多轮筛选值确认累积"""
    from analytics_assistant.src.agents.semantic_parser.state import SemanticParserState
    from analytics_assistant.src.agents.semantic_parser.schemas import FilterConfirmation
    
    state: SemanticParserState = {
        "question": "北京和上海的销售额",
        "confirmed_filters": [],
    }
    
    # 第一轮确认
    conf1 = FilterConfirmation(
        field_name="省份",
        original_value="北京",
        confirmed_value="北京市",
    )
    state["confirmed_filters"].append(conf1.model_dump())
    
    # 第二轮确认
    conf2 = FilterConfirmation(
        field_name="省份",
        original_value="上海",
        confirmed_value="上海市",
    )
    state["confirmed_filters"].append(conf2.model_dump())
    
    # 验证累积
    assert len(state["confirmed_filters"]) == 2
    assert state["confirmed_filters"][0]["confirmed_value"] == "北京市"
    assert state["confirmed_filters"][1]["confirmed_value"] == "上海市"
    print("✓ 多轮筛选值确认累积测试成功")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("SemanticParserState 测试")
    print("=" * 60)
    
    state_class = test_state_import()
    test_state_type_hints(state_class)
    test_state_creation()
    test_state_with_schemas()
    test_error_handling_fields()
    test_multi_round_confirmation()
    
    print("=" * 60)
    print("✓ 所有测试通过!")
    print("=" * 60)


if __name__ == "__main__":
    main()
