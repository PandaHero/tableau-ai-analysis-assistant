"""
UnderstandingAgent 单元测试

测试 UnderstandingAgent 的核心功能：
- 输入数据准备
- 结果处理
- 错误处理
- 降级策略
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from tableau_assistant.src.deepagents.subagents.understanding_agent import UnderstandingAgent
from tableau_assistant.src.models.question import (
    QuestionUnderstanding,
    QuestionType,
    Complexity,
    QuerySubQuestion,
    SubQuestionExecutionType
)
from tableau_assistant.src.config.model_config import AgentType


class TestUnderstandingAgent:
    """UnderstandingAgent 单元测试"""
    
    def setup_method(self):
        """每个测试前的设置"""
        self.agent = UnderstandingAgent()
    
    def test_initialization(self):
        """测试 Agent 初始化"""
        assert self.agent is not None
        assert self.agent.get_agent_type() == AgentType.UNDERSTANDING
        assert self.agent.prompt is not None
    
    def test_get_agent_type(self):
        """测试 get_agent_type 返回正确的类型"""
        assert self.agent.get_agent_type() == AgentType.UNDERSTANDING
    
    def test_prepare_input_data_with_question(self):
        """测试准备输入数据 - 提供问题"""
        result = self.agent._prepare_input_data(
            question="2024年各地区的销售额"
        )
        
        assert "question" in result
        assert result["question"] == "2024年各地区的销售额"
        assert "max_date" in result
        # 应该自动生成当前日期
        assert result["max_date"] is not None
    
    def test_prepare_input_data_with_max_date(self):
        """测试准备输入数据 - 提供 max_date"""
        result = self.agent._prepare_input_data(
            question="销售额",
            max_date="2024-12-31"
        )
        
        assert result["question"] == "销售额"
        assert result["max_date"] == "2024-12-31"
    
    def test_prepare_input_data_missing_question(self):
        """测试准备输入数据 - 缺少问题"""
        with pytest.raises(ValueError, match="question is required"):
            self.agent._prepare_input_data()
    
    def test_fix_dimension_aggregations_no_fix_needed(self):
        """测试维度聚合修复 - 不需要修复"""
        # 创建一个正常的 QuestionUnderstanding
        sub_question = QuerySubQuestion(
            text="各地区的销售额",
            completed_text="各地区的销售额",
            execution_type=SubQuestionExecutionType.QUERY,
            mentioned_dimensions=["地区"],
            mentioned_measures=["销售额"],
            dimension_aggregations={},  # 维度没有聚合
            time_range=None,
            date_requirements=None
        )
        
        understanding = QuestionUnderstanding(
            original_question="各地区的销售额",
            sub_questions=[sub_question],
            is_valid_question=True,
            question_type=[QuestionType.COMPARISON],
            complexity=Complexity.SIMPLE
        )
        
        result = self.agent._fix_dimension_aggregations(understanding)
        
        # 应该保持不变
        assert result.sub_questions[0].dimension_aggregations == {}
    
    def test_fix_dimension_aggregations_needs_fix(self):
        """测试维度聚合修复 - 需要修复"""
        # 创建一个错误的 QuestionUnderstanding（所有维度都有聚合）
        sub_question = QuerySubQuestion(
            text="各地区和产品的销售额",
            completed_text="各地区和产品的销售额",
            execution_type=SubQuestionExecutionType.QUERY,
            mentioned_dimensions=["地区", "产品"],
            mentioned_measures=["销售额"],
            dimension_aggregations={"地区": "COUNT", "产品": "COUNT"},  # 错误：所有维度都有聚合
            time_range=None,
            date_requirements=None
        )
        
        understanding = QuestionUnderstanding(
            original_question="各地区和产品的销售额",
            sub_questions=[sub_question],
            is_valid_question=True,
            question_type=[QuestionType.COMPARISON],
            complexity=Complexity.SIMPLE
        )
        
        result = self.agent._fix_dimension_aggregations(understanding)
        
        # 应该被清空
        assert result.sub_questions[0].dimension_aggregations == {}
    
    def test_process_result_single_question(self):
        """测试处理结果 - 单个子问题"""
        sub_question = QuerySubQuestion(
            text="2024年的销售额",
            completed_text="2024年的销售额",
            execution_type=SubQuestionExecutionType.QUERY,
            mentioned_dimensions=[],
            mentioned_measures=["销售额"],
            time_range=None,
            date_requirements=None
        )
        
        understanding = QuestionUnderstanding(
            original_question="2024年的销售额",
            sub_questions=[sub_question],
            is_valid_question=True,
            question_type=[QuestionType.TREND],
            complexity=Complexity.SIMPLE
        )
        
        result = self.agent._process_result(understanding)
        
        assert result["understanding"] == understanding
        assert result["question_type"] == [QuestionType.TREND]
        assert result["complexity"] == Complexity.SIMPLE
        assert result["needs_split"] is False  # 只有1个子问题
        assert len(result["sub_questions"]) == 1
        assert result["is_valid_question"] is True
    
    def test_process_result_multiple_questions(self):
        """测试处理结果 - 多个子问题"""
        sub_question1 = QuerySubQuestion(
            text="今年的销售额",
            completed_text="今年的销售额",
            execution_type=SubQuestionExecutionType.QUERY,
            mentioned_dimensions=[],
            mentioned_measures=["销售额"],
            time_range=None,
            date_requirements=None
        )
        
        sub_question2 = QuerySubQuestion(
            text="去年的销售额",
            completed_text="去年的销售额",
            execution_type=SubQuestionExecutionType.QUERY,
            mentioned_dimensions=[],
            mentioned_measures=["销售额"],
            time_range=None,
            date_requirements=None
        )
        
        understanding = QuestionUnderstanding(
            original_question="对比今年和去年的销售额",
            sub_questions=[sub_question1, sub_question2],
            is_valid_question=True,
            question_type=[QuestionType.COMPARISON],
            complexity=Complexity.MEDIUM
        )
        
        result = self.agent._process_result(understanding)
        
        assert result["needs_split"] is True  # 有2个子问题
        assert len(result["sub_questions"]) == 2
    
    @pytest.mark.asyncio
    async def test_execute_with_prompt_success(self):
        """测试执行 Prompt - 成功"""
        # Mock LLM 和 Prompt
        mock_llm = Mock()
        mock_understanding = QuestionUnderstanding(
            original_question="销售额",
            sub_questions=[
                QuerySubQuestion(
                    text="销售额",
                    completed_text="销售额",
                    execution_type=SubQuestionExecutionType.QUERY,
                    mentioned_dimensions=[],
                    mentioned_measures=["销售额"],
                    time_range=None,
                    date_requirements=None
                )
            ],
            is_valid_question=True,
            question_type=[QuestionType.TREND],
            complexity=Complexity.SIMPLE
        )
        
        # Mock _create_llm 和 _ainvoke_prompt
        with patch.object(self.agent, '_create_llm', return_value=mock_llm):
            with patch.object(self.agent, '_ainvoke_prompt', new_callable=AsyncMock, return_value=mock_understanding):
                result = await self.agent._execute_with_prompt(
                    state={},
                    runtime=Mock(),
                    input_data={"question": "销售额", "max_date": "2024-12-31"},
                    config={"temperature": 0.1, "max_output_tokens": 2000}
                )
        
        assert result == mock_understanding
    
    @pytest.mark.asyncio
    async def test_execute_with_prompt_fallback(self):
        """测试执行 Prompt - 降级处理"""
        # Mock LLM
        mock_llm = Mock()
        
        # Mock _create_llm 和 _ainvoke_prompt（抛出异常）
        with patch.object(self.agent, '_create_llm', return_value=mock_llm):
            with patch.object(self.agent, '_ainvoke_prompt', new_callable=AsyncMock, side_effect=Exception("LLM error")):
                result = await self.agent._execute_with_prompt(
                    state={},
                    runtime=Mock(),
                    input_data={"question": "销售额", "max_date": "2024-12-31"},
                    config={"temperature": 0.1, "max_output_tokens": 2000}
                )
        
        # 应该返回降级结果
        assert result is not None
        assert result.original_question == "销售额"
        assert len(result.sub_questions) == 1
        assert result.is_valid_question is True
        assert result.question_type == [QuestionType.COMPARISON]
        assert result.complexity == Complexity.MEDIUM
    
    def test_create_llm_success(self):
        """测试创建 LLM - 成功"""
        with patch.dict('os.environ', {
            'LLM_API_BASE': 'http://localhost:9997/v1',
            'LLM_API_KEY': 'test-key',
            'TOOLING_LLM_MODEL': 'qwen3'
        }):
            config = {
                "temperature": 0.1,
                "max_output_tokens": 2000
            }
            
            llm = self.agent._create_llm(config)
            
            assert llm is not None
            assert llm.model_name == 'qwen3'
            assert llm.temperature == 0.1
            assert llm.max_tokens == 2000
    
    def test_create_llm_missing_env_vars(self):
        """测试创建 LLM - 缺少环境变量"""
        with patch.dict('os.environ', {}, clear=True):
            config = {
                "temperature": 0.1,
                "max_output_tokens": 2000
            }
            
            with pytest.raises(ValueError, match="LLM_API_BASE and LLM_API_KEY must be set"):
                self.agent._create_llm(config)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
