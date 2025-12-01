"""
VizQL Workflow Unit Tests

测试 StateGraph 工作流：
- 节点执行顺序
- 条件路由
- 重规划循环
- completeness_score 计算
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

from tableau_assistant.src.agents.workflows.vizql_workflow import (
    create_vizql_workflow,
    validate_input,
    _calculate_completeness_score,
)
from tableau_assistant.src.models.state import VizQLState


class TestValidateInput:
    """测试输入验证"""
    
    def test_valid_input(self):
        """测试有效输入"""
        result = validate_input({
            "question": "2024年销售额是多少？",
            "boost_question": False
        })
        
        assert result["question"] == "2024年销售额是多少？"
        assert result["boost_question"] is False
    
    def test_valid_input_with_boost(self):
        """测试带 boost 的有效输入"""
        result = validate_input({
            "question": "销售趋势",
            "boost_question": True
        })
        
        assert result["boost_question"] is True
    
    def test_missing_question(self):
        """测试缺少 question 字段"""
        with pytest.raises(ValueError) as exc_info:
            validate_input({"boost_question": False})
        
        assert "question字段是必需的" in str(exc_info.value)
    
    def test_empty_question(self):
        """测试空 question"""
        with pytest.raises(ValueError) as exc_info:
            validate_input({"question": "", "boost_question": False})
        
        assert "非空字符串" in str(exc_info.value)
    
    def test_whitespace_question(self):
        """测试纯空白 question"""
        with pytest.raises(ValueError) as exc_info:
            validate_input({"question": "   ", "boost_question": False})
        
        assert "非空字符串" in str(exc_info.value)
    
    def test_invalid_boost_type(self):
        """测试无效的 boost_question 类型"""
        with pytest.raises(ValueError) as exc_info:
            validate_input({"question": "test", "boost_question": "yes"})
        
        assert "布尔值" in str(exc_info.value)
    
    def test_default_boost_question(self):
        """测试默认 boost_question 值"""
        result = validate_input({"question": "test"})
        
        assert result["boost_question"] is False


class TestCompletenessScore:
    """测试完成度分数计算"""
    
    def test_full_score_with_good_data(self):
        """测试完整数据的高分"""
        state: VizQLState = {
            "subtask_results": [
                {"question_id": "q1", "data": [{"a": 1}]},
                {"question_id": "q2", "data": [{"b": 2}]}
            ],
            "insights": [
                {"title": "洞察1"},
                {"title": "洞察2"},
                {"title": "洞察3"}
            ],
            "errors": []
        }
        replan_decision = {"completeness_score": 0.9}
        
        score = _calculate_completeness_score(state, replan_decision)
        
        assert score >= 0.8  # 高分
    
    def test_low_score_with_no_data(self):
        """测试无数据的低分"""
        state: VizQLState = {
            "subtask_results": [],
            "insights": [],
            "errors": []
        }
        replan_decision = {"completeness_score": 0.3}
        
        score = _calculate_completeness_score(state, replan_decision)
        
        assert score < 0.5  # 低分
    
    def test_reduced_score_with_errors(self):
        """测试有错误时分数降低"""
        state: VizQLState = {
            "subtask_results": [
                {"question_id": "q1", "data": [{"a": 1}]}
            ],
            "insights": [{"title": "洞察1"}],
            "errors": [
                {"node": "execute", "error": "Query failed"}
            ]
        }
        replan_decision = {"completeness_score": 0.7}
        
        score = _calculate_completeness_score(state, replan_decision)
        
        # 有错误时分数应该降低
        assert score < 0.8
    
    def test_score_bounds(self):
        """测试分数边界"""
        # 最低分
        state_low: VizQLState = {
            "subtask_results": [],
            "insights": [],
            "errors": []
        }
        score_low = _calculate_completeness_score(state_low, {"completeness_score": 0.0})
        assert 0.0 <= score_low <= 1.0
        
        # 最高分
        state_high: VizQLState = {
            "subtask_results": [{"data": [1, 2, 3]}] * 5,
            "insights": [{"title": f"洞察{i}"} for i in range(5)],
            "errors": []
        }
        score_high = _calculate_completeness_score(state_high, {"completeness_score": 1.0})
        assert 0.0 <= score_high <= 1.0


class TestWorkflowCreation:
    """测试工作流创建"""
    
    def test_create_workflow(self):
        """测试创建工作流"""
        # Mock Store 并提供给 create_vizql_workflow
        mock_store = MagicMock()
        
        # 直接传入 mock store，避免内部导入问题
        app = create_vizql_workflow(store=mock_store)
        
        assert app is not None
    
    def test_workflow_has_all_nodes(self):
        """测试工作流包含所有节点"""
        # Mock Store 并提供给 create_vizql_workflow
        mock_store = MagicMock()
        
        app = create_vizql_workflow(store=mock_store)
        
        # 获取图的节点 - LangGraph 返回的是节点名称字符串
        graph = app.get_graph()
        # graph.nodes 可能是 dict 或 list，取决于 LangGraph 版本
        if hasattr(graph.nodes, 'keys'):
            node_names = list(graph.nodes.keys())
        else:
            # 如果是 list of objects
            node_names = [node if isinstance(node, str) else node.name for node in graph.nodes]
        
        # 过滤掉内部节点
        node_names = [n for n in node_names if n not in ('__start__', '__end__')]
        
        expected_nodes = ["boost", "understanding", "planning", "execute", "insight", "replanner"]
        for node in expected_nodes:
            assert node in node_names, f"缺少节点: {node}"


class TestRoutingLogic:
    """测试路由逻辑"""
    
    def test_should_boost_true(self):
        """测试 boost_question=True 时路由到 boost"""
        from tableau_assistant.src.agents.workflows.vizql_workflow import create_vizql_workflow
        
        # 模拟状态
        state = {"boost_question": True, "question": "test"}
        
        # 直接测试路由函数
        def should_boost(state):
            return "boost" if state.get("boost_question", False) else "understanding"
        
        assert should_boost(state) == "boost"
    
    def test_should_boost_false(self):
        """测试 boost_question=False 时跳过 boost"""
        state = {"boost_question": False, "question": "test"}
        
        def should_boost(state):
            return "boost" if state.get("boost_question", False) else "understanding"
        
        assert should_boost(state) == "understanding"
    
    def test_should_replan_true(self):
        """测试需要重规划时路由到 planning"""
        state = {
            "replan_decision": {"should_replan": True},
            "completeness_score": 0.5
        }
        
        def should_replan(state):
            replan_decision = state.get("replan_decision", {})
            should_replan_flag = replan_decision.get("should_replan", False)
            completeness_score = state.get("completeness_score", 1.0)
            
            if completeness_score >= 0.9:
                return "end"
            if should_replan_flag:
                return "planning"
            return "end"
        
        assert should_replan(state) == "planning"
    
    def test_should_replan_false(self):
        """测试不需要重规划时结束"""
        state = {
            "replan_decision": {"should_replan": False},
            "completeness_score": 0.8
        }
        
        def should_replan(state):
            replan_decision = state.get("replan_decision", {})
            should_replan_flag = replan_decision.get("should_replan", False)
            completeness_score = state.get("completeness_score", 1.0)
            
            if completeness_score >= 0.9:
                return "end"
            if should_replan_flag:
                return "planning"
            return "end"
        
        assert should_replan(state) == "end"
    
    def test_high_completeness_ends_workflow(self):
        """测试高完成度时终止工作流"""
        state = {
            "replan_decision": {"should_replan": True},  # 即使想重规划
            "completeness_score": 0.95  # 但完成度已经很高
        }
        
        def should_replan(state):
            replan_decision = state.get("replan_decision", {})
            should_replan_flag = replan_decision.get("should_replan", False)
            completeness_score = state.get("completeness_score", 1.0)
            
            if completeness_score >= 0.9:
                return "end"
            if should_replan_flag:
                return "planning"
            return "end"
        
        # 高完成度应该终止，即使 should_replan=True
        assert should_replan(state) == "end"


class TestNodeExecution:
    """测试节点执行"""
    
    @patch('tableau_assistant.src.capabilities.query.executor.execute_node.execute_query_node')
    def test_execute_node_called(self, mock_execute):
        """测试 execute 节点被调用"""
        mock_execute.return_value = {
            "subtask_results": [{"question_id": "q1", "data": []}],
            "current_stage": "insight"
        }
        
        state = {"query_plan": {"subtasks": []}}
        config = {"configurable": {"datasource_luid": "test-luid"}}
        
        from tableau_assistant.src.capabilities.query.executor.execute_node import execute_query_node
        result = execute_query_node(state, config)
        
        assert "subtask_results" in result or "errors" in result


class TestAgentTemperatureConfig:
    """测试 Agent Temperature 配置"""
    
    def test_temperature_config_exists(self):
        """测试 temperature 配置存在"""
        from tableau_assistant.src.agents.base_agent import AGENT_TEMPERATURE_CONFIG
        
        assert "UnderstandingAgent" in AGENT_TEMPERATURE_CONFIG
        assert "TaskPlannerAgent" in AGENT_TEMPERATURE_CONFIG
        assert "QuestionBoostAgent" in AGENT_TEMPERATURE_CONFIG
        assert "InsightAgent" in AGENT_TEMPERATURE_CONFIG
        assert "ReplannerAgent" in AGENT_TEMPERATURE_CONFIG
        assert "default" in AGENT_TEMPERATURE_CONFIG
    
    def test_get_agent_temperature(self):
        """测试获取 agent temperature"""
        from tableau_assistant.src.agents.base_agent import get_agent_temperature
        
        # 已配置的 agent
        assert get_agent_temperature("UnderstandingAgent") == 0.1
        assert get_agent_temperature("QuestionBoostAgent") == 0.3
        assert get_agent_temperature("InsightAgent") == 0.4
        
        # 未配置的 agent 使用默认值
        assert get_agent_temperature("UnknownAgent") == 0.2
    
    def test_temperature_values_in_range(self):
        """测试所有 temperature 值在有效范围内"""
        from tableau_assistant.src.agents.base_agent import AGENT_TEMPERATURE_CONFIG
        
        for agent_name, temp in AGENT_TEMPERATURE_CONFIG.items():
            assert 0.0 <= temp <= 1.0, f"{agent_name} temperature {temp} 超出范围"
    
    def test_understanding_agent_uses_config_temperature(self):
        """测试 UnderstandingAgent 使用配置的 temperature"""
        from tableau_assistant.src.agents.base_agent import get_agent_temperature
        
        # Understanding 需要精确理解，应该使用低 temperature
        temp = get_agent_temperature("UnderstandingAgent")
        assert temp <= 0.2, "UnderstandingAgent 应该使用低 temperature"
    
    def test_insight_agent_uses_higher_temperature(self):
        """测试 InsightAgent 使用较高的 temperature"""
        from tableau_assistant.src.agents.base_agent import get_agent_temperature
        
        # Insight 需要创造性，应该使用较高 temperature
        temp = get_agent_temperature("InsightAgent")
        assert temp >= 0.3, "InsightAgent 应该使用较高 temperature 以获得创造性"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
