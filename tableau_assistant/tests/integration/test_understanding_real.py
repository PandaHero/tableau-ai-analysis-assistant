"""
Understanding Agent 真实环境集成测试

使用真实的 Tableau 元数据和 LLM 模型进行测试。

运行方式：
    pytest tableau_assistant/tests/integration/test_understanding_real.py -v -s

注意：
    - 需要配置 .env 文件中的 LLM 和 Tableau 相关配置
    - 测试会调用真实的 LLM API，可能产生费用
"""
import pytest
import asyncio
import logging
import os
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def real_metadata():
    """
    获取真实的 Tableau 元数据
    
    从 Tableau 数据源获取字段信息。
    """
    from tableau_assistant.src.metadata.manager import MetadataManager
    
    datasource_luid = os.environ.get("DATASOURCE_LUID")
    if not datasource_luid:
        pytest.skip("DATASOURCE_LUID not configured")
    
    manager = MetadataManager()
    
    # 同步获取元数据
    loop = asyncio.get_event_loop()
    metadata = loop.run_until_complete(manager.get_metadata(datasource_luid))
    
    logger.info(f"Loaded metadata with {len(metadata.fields)} fields")
    return metadata


@pytest.fixture(scope="module")
def metadata_summary(real_metadata):
    """
    格式化元数据摘要
    """
    fields = real_metadata.fields
    dimensions = [f for f in fields if getattr(f, 'role', '').upper() == 'DIMENSION']
    measures = [f for f in fields if getattr(f, 'role', '').upper() == 'MEASURE']
    
    lines = []
    lines.append(f"Dimensions ({len(dimensions)}):")
    for f in dimensions[:15]:
        caption = getattr(f, 'fieldCaption', getattr(f, 'name', str(f)))
        lines.append(f"  - {caption}")
    if len(dimensions) > 15:
        lines.append(f"  ... and {len(dimensions) - 15} more")
    
    lines.append(f"\nMeasures ({len(measures)}):")
    for f in measures[:15]:
        caption = getattr(f, 'fieldCaption', getattr(f, 'name', str(f)))
        lines.append(f"  - {caption}")
    if len(measures) > 15:
        lines.append(f"  ... and {len(measures) - 15} more")
    
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Test Cases
# ═══════════════════════════════════════════════════════════════════════════

class TestUnderstandingNodeReal:
    """Understanding Node 真实环境测试"""
    
    @pytest.mark.asyncio
    async def test_simple_aggregation(self, real_metadata, metadata_summary):
        """
        测试简单聚合查询
        
        问题：各省份的销售额
        预期：
        - measures: [销售额]
        - dimensions: [省份]
        - analyses: []
        """
        from tableau_assistant.src.agents.understanding.node import understanding_node
        
        state = {
            "question": "各省份的销售额",
            "metadata": real_metadata,
        }
        
        result = await understanding_node(state)
        
        # 验证结果
        assert result["is_analysis_question"] is True
        assert result["understanding_complete"] is True
        assert result.get("error") is None
        
        semantic_query = result["semantic_query"]
        assert semantic_query is not None
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Question: {state['question']}")
        logger.info(f"Result: {semantic_query.model_dump_json(indent=2)}")
        logger.info(f"{'='*60}")
        
        # 验证结构
        assert len(semantic_query.measures) >= 1
        assert len(semantic_query.dimensions) >= 1
    
    @pytest.mark.asyncio
    async def test_cumulative_single_dimension(self, real_metadata, metadata_summary):
        """
        测试单维度累计计算
        
        问题：按月累计销售额
        预期：
        - measures: [销售额]
        - dimensions: [日期/月]
        - analyses: [type=cumulative, computation_scope=null]
        """
        from tableau_assistant.src.agents.understanding.node import understanding_node
        
        state = {
            "question": "按月累计销售额",
            "metadata": real_metadata,
        }
        
        result = await understanding_node(state)
        
        assert result["is_analysis_question"] is True
        assert result["understanding_complete"] is True
        
        semantic_query = result["semantic_query"]
        assert semantic_query is not None
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Question: {state['question']}")
        logger.info(f"Result: {semantic_query.model_dump_json(indent=2)}")
        logger.info(f"{'='*60}")
        
        # 验证累计分析
        assert len(semantic_query.analyses) >= 1
        analysis = semantic_query.analyses[0]
        assert analysis.type.value == "cumulative"
        
        # 单维度不应该有 computation_scope
        # 注意：这是一个关键验证点
        if len(semantic_query.dimensions) == 1:
            assert analysis.computation_scope is None, \
                "Single dimension query should not have computation_scope"
    
    @pytest.mark.asyncio
    async def test_cumulative_multi_dimension(self, real_metadata, metadata_summary):
        """
        测试多维度累计计算
        
        问题：各省份按月累计销售额
        预期：
        - measures: [销售额]
        - dimensions: [省份, 日期/月]
        - analyses: [type=cumulative, computation_scope=per_group]
        """
        from tableau_assistant.src.agents.understanding.node import understanding_node
        
        state = {
            "question": "各省份按月累计销售额",
            "metadata": real_metadata,
        }
        
        result = await understanding_node(state)
        
        assert result["is_analysis_question"] is True
        assert result["understanding_complete"] is True
        
        semantic_query = result["semantic_query"]
        assert semantic_query is not None
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Question: {state['question']}")
        logger.info(f"Result: {semantic_query.model_dump_json(indent=2)}")
        logger.info(f"{'='*60}")
        
        # 验证多维度
        assert len(semantic_query.dimensions) >= 2
        
        # 验证累计分析
        assert len(semantic_query.analyses) >= 1
        analysis = semantic_query.analyses[0]
        assert analysis.type.value == "cumulative"
        
        # 多维度应该有 computation_scope
        assert analysis.computation_scope is not None, \
            "Multi-dimension query should have computation_scope"
    
    @pytest.mark.asyncio
    async def test_ranking(self, real_metadata, metadata_summary):
        """
        测试排名计算
        
        问题：销售额排名前10的产品
        预期：
        - measures: [销售额]
        - dimensions: [产品]
        - analyses: [type=ranking]
        - output_control: [limit=10]
        """
        from tableau_assistant.src.agents.understanding.node import understanding_node
        
        state = {
            "question": "销售额排名前10的产品",
            "metadata": real_metadata,
        }
        
        result = await understanding_node(state)
        
        assert result["is_analysis_question"] is True
        assert result["understanding_complete"] is True
        
        semantic_query = result["semantic_query"]
        assert semantic_query is not None
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Question: {state['question']}")
        logger.info(f"Result: {semantic_query.model_dump_json(indent=2)}")
        logger.info(f"{'='*60}")
        
        # 验证排名分析
        assert len(semantic_query.analyses) >= 1
        analysis = semantic_query.analyses[0]
        assert analysis.type.value == "ranking"
    
    @pytest.mark.asyncio
    async def test_percentage(self, real_metadata, metadata_summary):
        """
        测试占比计算
        
        问题：各省份销售额占比
        预期：
        - measures: [销售额]
        - dimensions: [省份]
        - analyses: [type=percentage]
        """
        from tableau_assistant.src.agents.understanding.node import understanding_node
        
        state = {
            "question": "各省份销售额占比",
            "metadata": real_metadata,
        }
        
        result = await understanding_node(state)
        
        assert result["is_analysis_question"] is True
        assert result["understanding_complete"] is True
        
        semantic_query = result["semantic_query"]
        assert semantic_query is not None
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Question: {state['question']}")
        logger.info(f"Result: {semantic_query.model_dump_json(indent=2)}")
        logger.info(f"{'='*60}")
        
        # 验证占比分析
        assert len(semantic_query.analyses) >= 1
        analysis = semantic_query.analyses[0]
        assert analysis.type.value == "percentage"
    
    @pytest.mark.asyncio
    async def test_time_filter(self, real_metadata, metadata_summary):
        """
        测试时间筛选
        
        问题：2024年各省份的销售额
        预期：
        - measures: [销售额]
        - dimensions: [省份]
        - filters: [time_range for 2024]
        """
        from tableau_assistant.src.agents.understanding.node import understanding_node
        
        state = {
            "question": "2024年各省份的销售额",
            "metadata": real_metadata,
        }
        
        result = await understanding_node(state)
        
        assert result["is_analysis_question"] is True
        assert result["understanding_complete"] is True
        
        semantic_query = result["semantic_query"]
        assert semantic_query is not None
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Question: {state['question']}")
        logger.info(f"Result: {semantic_query.model_dump_json(indent=2)}")
        logger.info(f"{'='*60}")
        
        # 验证时间筛选
        assert len(semantic_query.filters) >= 1
    
    @pytest.mark.asyncio
    async def test_non_analysis_question(self, real_metadata, metadata_summary):
        """
        测试非分析类问题
        
        问题：你好
        预期：
        - is_analysis_question: False
        - semantic_query: None
        """
        from tableau_assistant.src.agents.understanding.node import understanding_node
        
        state = {
            "question": "你好",
            "metadata": real_metadata,
        }
        
        result = await understanding_node(state)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Question: {state['question']}")
        logger.info(f"is_analysis_question: {result['is_analysis_question']}")
        logger.info(f"non_analysis_response: {result.get('non_analysis_response', 'N/A')}")
        logger.info(f"{'='*60}")
        
        assert result["is_analysis_question"] is False
        assert result["semantic_query"] is None


class TestUnderstandingPromptReal:
    """Understanding Prompt 真实环境测试（直接测试 LLM 输出）"""
    
    @pytest.mark.asyncio
    async def test_prompt_output_format(self, metadata_summary):
        """
        测试 Prompt 输出格式
        
        验证 LLM 能够按照 Schema 的 <decision_rule> 正确输出 JSON。
        """
        from tableau_assistant.src.agents.understanding.prompt import UNDERSTANDING_PROMPT
        from tableau_assistant.src.agents.understanding.node import _get_llm
        from tableau_assistant.src.models.semantic.query import SemanticQuery
        import json
        
        # 构建消息
        messages = UNDERSTANDING_PROMPT.format_messages(
            question="各省份按月累计销售额",
            metadata_summary=metadata_summary,
            current_date=datetime.now().strftime("%Y-%m-%d"),
        )
        
        # 调用 LLM
        llm = _get_llm()
        
        # 使用 structured output
        structured_llm = llm.with_structured_output(SemanticQuery)
        
        result = await structured_llm.ainvoke(messages)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Structured Output Test")
        logger.info(f"Result type: {type(result)}")
        logger.info(f"Result: {result.model_dump_json(indent=2) if result else 'None'}")
        logger.info(f"{'='*60}")
        
        assert result is not None
        assert isinstance(result, SemanticQuery)


# ═══════════════════════════════════════════════════════════════════════════
# Interactive Test (for manual testing)
# ═══════════════════════════════════════════════════════════════════════════

async def interactive_test():
    """
    交互式测试
    
    运行方式：
        python -c "import asyncio; from tableau_assistant.tests.integration.test_understanding_real import interactive_test; asyncio.run(interactive_test())"
    """
    import os
    from pathlib import Path
    
    # 加载环境变量
    env_file = Path(__file__).parent.parent.parent.parent / ".env"
    if env_file.exists():
        from conftest import load_dotenv
        load_dotenv(env_file)
    
    from tableau_assistant.src.metadata.manager import MetadataManager
    from tableau_assistant.src.agents.understanding.node import understanding_node
    
    # 获取元数据
    datasource_luid = os.environ.get("DATASOURCE_LUID")
    if not datasource_luid:
        print("Error: DATASOURCE_LUID not configured")
        return
    
    manager = MetadataManager()
    metadata = await manager.get_metadata(datasource_luid)
    print(f"Loaded metadata with {len(metadata.fields)} fields")
    
    # 测试问题列表
    test_questions = [
        "各省份的销售额",
        "按月累计销售额",
        "各省份按月累计销售额",
        "销售额排名前10的产品",
        "各省份销售额占比",
        "2024年各省份的销售额",
        "最近3个月的销售趋势",
    ]
    
    for question in test_questions:
        print(f"\n{'='*60}")
        print(f"Question: {question}")
        print(f"{'='*60}")
        
        state = {
            "question": question,
            "metadata": metadata,
        }
        
        try:
            result = await understanding_node(state)
            
            if result["is_analysis_question"]:
                semantic_query = result["semantic_query"]
                if semantic_query:
                    print(f"SemanticQuery:")
                    print(semantic_query.model_dump_json(indent=2))
                else:
                    print(f"Error: {result.get('error', 'Unknown error')}")
            else:
                print(f"Non-analysis question")
                print(f"Response: {result.get('non_analysis_response', 'N/A')}")
        except Exception as e:
            print(f"Error: {e}")
        
        print()


if __name__ == "__main__":
    asyncio.run(interactive_test())
