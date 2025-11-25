# Prompt 系统重构实施指南

## 已完成任务（1-5）✅

### 基础架构
- ✅ BasePrompt 和 VizQLPrompt 基类
- ✅ BaseVizQLAgent 基类
- ✅ 自动 Schema 注入
- ✅ 动态模型选择

### 重构后的 Prompt
- ✅ QuestionBoostPrompt (v2)
- ✅ UnderstandingPrompt (v2)
- ✅ TaskPlannerPrompt (v2)

## 剩余任务实施指南（6-12）

### 任务 6-8：更新 Agent

#### 通用模式

所有 Agent 更新遵循相同的模式：

```python
# 旧模式（当前）
async def agent_node(state, runtime, **kwargs):
    # 手动获取 LLM
    llm = select_model(...)
    
    # 手动准备数据
    input_data = {...}
    
    # 调用 invoke_with_streaming
    result = await invoke_with_streaming(
        prompt=OLD_PROMPT,
        llm=llm,
        input_data=input_data,
        output_model=OutputModel
    )
    
    # 返回结果
    return {"result": result}

# 新模式（目标）
class NewAgent(BaseVizQLAgent):
    def __init__(self):
        super().__init__(NEW_PROMPT_V2())
    
    def _prepare_input_data(self, state, **kwargs):
        return {
            "question": state['question'],
            "metadata": state['metadata']
        }
    
    def _process_result(self, result, state):
        return {"result": result}

# Node 函数
async def agent_node_v2(state, runtime, model_config=None, **kwargs):
    agent = NewAgent()
    return await agent.execute(state, runtime, model_config, **kwargs)
```

#### 任务 6：更新 Question Boost Agent

**文件：** `tableau_assistant/src/agents/question_boost_agent_v2.py`

```python
"""
Question Boost Agent (v2 - Refactored)
"""
from typing import Dict, Any
from langgraph.runtime import Runtime
from tableau_assistant.src.models.state import VizQLState
from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.src.models.boost import QuestionBoost
from tableau_assistant.src.agents.base_agent import BaseVizQLAgent
from tableau_assistant.prompts import QUESTION_BOOST_PROMPT_V2


class QuestionBoostAgentV2(BaseVizQLAgent):
    """Question Boost Agent using v2 architecture"""
    
    def __init__(self):
        super().__init__(QUESTION_BOOST_PROMPT_V2)
    
    def _prepare_input_data(self, state: VizQLState, **kwargs) -> Dict[str, Any]:
        """Prepare input data for Question Boost prompt"""
        # Get question
        question = state.get('question', state.get('original_question', ''))
        
        # Get metadata (optional)
        metadata = kwargs.get('metadata', state.get('metadata', {}))
        
        # Format metadata for prompt
        if metadata:
            metadata_summary = self._format_metadata(metadata)
        else:
            metadata_summary = "No metadata available"
        
        return {
            "question": question,
            "metadata": metadata_summary
        }
    
    def _format_metadata(self, metadata: Any) -> str:
        """Format metadata for prompt"""
        from tableau_assistant.src.models.metadata import Metadata
        
        if isinstance(metadata, Metadata):
            dimensions = [d.name for d in metadata.get_dimensions()]
            measures = [m.name for m in metadata.get_measures()]
            return f"Dimensions: {', '.join(dimensions)}\nMeasures: {', '.join(measures)}"
        elif isinstance(metadata, dict):
            return f"Fields: {len(metadata.get('fields', []))}"
        else:
            return str(metadata)
    
    def _process_result(self, result: QuestionBoost, state: VizQLState) -> Dict[str, Any]:
        """Process Question Boost result"""
        return {
            "boost_result": result,
            "boosted_question": result.boosted_question,
            "is_data_analysis_question": result.is_data_analysis_question
        }


# Node function for LangGraph
async def question_boost_agent_node_v2(
    state: VizQLState,
    runtime: Runtime[VizQLContext],
    model_config: Dict[str, Any] = None,
    **kwargs
) -> Dict[str, Any]:
    """Question Boost Agent node (v2)"""
    agent = QuestionBoostAgentV2()
    return await agent.execute(state, runtime, model_config, **kwargs)
```

#### 任务 7：更新 Understanding Agent

**文件：** `tableau_assistant/src/agents/understanding_agent_v2.py`

```python
"""
Understanding Agent (v2 - Refactored)
"""
from typing import Dict, Any
from langgraph.runtime import Runtime
from tableau_assistant.src.models.state import VizQLState
from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.src.models.question import QuestionUnderstanding
from tableau_assistant.src.agents.base_agent import BaseVizQLAgent
from tableau_assistant.prompts import UNDERSTANDING_PROMPT_V2


class UnderstandingAgentV2(BaseVizQLAgent):
    """Understanding Agent using v2 architecture"""
    
    def __init__(self):
        super().__init__(UNDERSTANDING_PROMPT_V2)
    
    def _prepare_input_data(self, state: VizQLState, **kwargs) -> Dict[str, Any]:
        """Prepare input data for Understanding prompt"""
        # Get question (prefer boosted question)
        question = state.get('boosted_question', state.get('question', ''))
        
        # Get metadata
        metadata = state.get('metadata', {})
        
        return {
            "question": question,
            "metadata": metadata
        }
    
    def _process_result(self, result: QuestionUnderstanding, state: VizQLState) -> Dict[str, Any]:
        """Process Understanding result with validation"""
        # Validate relationships
        if len(result.sub_questions) > 1:
            if not result.sub_question_relationships:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Multiple sub-questions but no relationships defined: "
                    f"{result.sub_questions}"
                )
        
        return {
            "understanding": result,
            "sub_questions": result.sub_questions,
            "question_type": result.question_type,
            "complexity": result.complexity
        }


# Node function for LangGraph
async def understanding_agent_node_v2(
    state: VizQLState,
    runtime: Runtime[VizQLContext],
    model_config: Dict[str, Any] = None,
    **kwargs
) -> Dict[str, Any]:
    """Understanding Agent node (v2)"""
    agent = UnderstandingAgentV2()
    return await agent.execute(state, runtime, model_config, **kwargs)
```

#### 任务 8：更新 Task Planner Agent

**文件：** `tableau_assistant/src/agents/task_planner_agent_v2.py`

```python
"""
Task Planner Agent (v2 - Refactored)
"""
from typing import Dict, Any
from langgraph.runtime import Runtime
from tableau_assistant.src.models.state import VizQLState
from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.src.models.query_plan import QueryPlanningResult
from tableau_assistant.src.agents.base_agent import BaseVizQLAgent
from tableau_assistant.prompts import TASK_PLANNER_PROMPT_V2


class TaskPlannerAgentV2(BaseVizQLAgent):
    """Task Planner Agent using v2 architecture"""
    
    def __init__(self):
        super().__init__(TASK_PLANNER_PROMPT_V2)
    
    def _prepare_input_data(self, state: VizQLState, **kwargs) -> Dict[str, Any]:
        """Prepare input data for Task Planner prompt"""
        # Get understanding result
        understanding = state.get('understanding')
        if not understanding:
            raise ValueError("Understanding result not found in state")
        
        # Get metadata and dimension hierarchy
        metadata = state.get('metadata', {})
        dimension_hierarchy = state.get('dimension_hierarchy', {})
        
        return {
            "understanding": understanding.model_dump() if hasattr(understanding, 'model_dump') else understanding,
            "metadata": metadata,
            "dimension_hierarchy": dimension_hierarchy
        }
    
    def _process_result(self, result: QueryPlanningResult, state: VizQLState) -> Dict[str, Any]:
        """Process Task Planning result with validation"""
        # Validate field names against metadata
        metadata = state.get('metadata', {})
        if metadata:
            self._validate_fields(result, metadata)
        
        return {
            "query_plan": result,
            "subtasks": result.subtasks,
            "complexity": result.complexity
        }
    
    def _validate_fields(self, plan: QueryPlanningResult, metadata: dict):
        """Validate that all field names exist in metadata"""
        valid_fields = {f.get('fieldCaption') for f in metadata.get('fields', [])}
        
        for subtask in plan.subtasks:
            for field in subtask.fields:
                if hasattr(field, 'fieldCaption') and field.fieldCaption not in valid_fields:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(
                        f"Unknown field in subtask {subtask.question_id}: "
                        f"{field.fieldCaption}"
                    )


# Node function for LangGraph
async def task_planner_agent_node_v2(
    state: VizQLState,
    runtime: Runtime[VizQLContext],
    model_config: Dict[str, Any] = None,
    **kwargs
) -> Dict[str, Any]:
    """Task Planner Agent node (v2)"""
    agent = TaskPlannerAgentV2()
    return await agent.execute(state, runtime, model_config, **kwargs)
```

### 任务 9：实现元数据预加载

**修改文件：** `tableau_assistant/tests/test_boost_understanding_planning.py`

```python
async def test_boost_understanding_planning():
    """测试完整流程（使用 v2 架构）"""
    # 创建测试环境
    env = create_test_environment()
    runtime = env.runtime
    
    # ===== 预处理：获取元数据和维度层级 =====
    print("\n--- 预处理: 获取元数据和维度层级 ---")
    metadata = await env.metadata_manager.get_metadata_async(
        use_cache=True,
        enhance=True  # 包含维度层级推断
    )
    print(f"✓ 元数据获取完成，包含 {len(metadata.get('fields', []))} 个字段")
    print(f"✓ 维度层级推断完成，包含 {len(metadata.get('dimension_hierarchy', {}))} 个维度")
    
    # 测试问题
    test_questions = [
        "显示各地区各产品类别的销售额和利润",
    ]
    
    for question in test_questions:
        print(f"\n{'='*80}")
        print(f"测试问题: {question}")
        print(f"{'='*80}")
        
        # 初始化状态（包含预加载的元数据）
        state = VizQLState()
        state['original_question'] = question
        state['question'] = question
        state['metadata'] = metadata
        state['dimension_hierarchy'] = metadata.get('dimension_hierarchy', {})
        
        # 阶段1: Question Boost (v2)
        print("\n--- 阶段1: Question Boost (v2) ---")
        from tableau_assistant.src.agents.question_boost_agent_v2 import question_boost_agent_node_v2
        boost_result = await question_boost_agent_node_v2(state, runtime)
        state.update(boost_result)
        print(f"✓ Boosted: {boost_result['boosted_question']}")
        
        # 阶段2: Understanding (v2)
        print("\n--- 阶段2: Understanding (v2) ---")
        from tableau_assistant.src.agents.understanding_agent_v2 import understanding_agent_node_v2
        understanding_result = await understanding_agent_node_v2(state, runtime)
        state.update(understanding_result)
        print(f"✓ Sub-questions: {len(understanding_result['sub_questions'])}")
        
        # 阶段3: Task Planning (v2)
        print("\n--- 阶段3: Task Planning (v2) ---")
        from tableau_assistant.src.agents.task_planner_agent_v2 import task_planner_agent_node_v2
        planning_result = await task_planner_agent_node_v2(state, runtime)
        state.update(planning_result)
        print(f"✓ Subtasks: {len(planning_result['subtasks'])}")
```

### 任务 10：添加验证工具

**文件：** `tableau_assistant/src/utils/validation.py`

```python
"""
Validation utilities for v2 architecture
"""
from typing import Dict, Any
from tableau_assistant.src.models.question import QuestionUnderstanding
from tableau_assistant.src.models.query_plan import QueryPlanningResult


def validate_understanding(understanding: QuestionUnderstanding) -> None:
    """Validate Understanding result"""
    # Check sub-question relationships
    if len(understanding.sub_questions) > 1:
        if not understanding.sub_question_relationships:
            raise ValueError(
                "Multiple sub-questions must have relationships defined"
            )
    
    # Check relationship indices
    for rel in understanding.sub_question_relationships:
        for idx in rel.question_indices:
            if idx >= len(understanding.sub_questions):
                raise ValueError(
                    f"Invalid question index {idx} in relationship. "
                    f"Only {len(understanding.sub_questions)} sub-questions exist."
                )
    
    # Check comparison dimension
    for rel in understanding.sub_question_relationships:
        if rel.relation_type == "comparison" and not rel.comparison_dimension:
            raise ValueError(
                "Comparison relationship must specify comparison_dimension"
            )


def validate_query_plan(plan: QueryPlanningResult, metadata: Dict[str, Any]) -> None:
    """Validate Query Plan against metadata"""
    valid_fields = {f.get('fieldCaption') for f in metadata.get('fields', [])}
    
    errors = []
    for subtask in plan.subtasks:
        for field in subtask.fields:
            if hasattr(field, 'fieldCaption'):
                if field.fieldCaption not in valid_fields:
                    errors.append(
                        f"Unknown field in {subtask.question_id}: {field.fieldCaption}"
                    )
    
    if errors:
        raise ValueError(
            f"Field validation failed:\n" + "\n".join(errors)
        )


def validate_relationships(understanding: QuestionUnderstanding) -> None:
    """Validate sub-question relationships"""
    if not understanding.sub_question_relationships:
        return
    
    for rel in understanding.sub_question_relationships:
        # Check indices are valid
        for idx in rel.question_indices:
            if idx < 0 or idx >= len(understanding.sub_questions):
                raise ValueError(
                    f"Invalid question index: {idx}"
                )
        
        # Check comparison has dimension
        if rel.relation_type == "comparison":
            if not rel.comparison_dimension:
                raise ValueError(
                    "Comparison relationship must specify comparison_dimension"
                )
            if rel.comparison_dimension not in ["time", "dimension"]:
                raise ValueError(
                    f"Invalid comparison_dimension: {rel.comparison_dimension}"
                )
```

### 任务 11-12：测试和文档

这些任务在实际实施任务 6-10 后进行。

## 实施步骤

1. **创建 v2 Agent 文件**（任务 6-8）
2. **更新测试文件**（任务 9）
3. **添加验证工具**（任务 10）
4. **运行测试验证**（任务 11）
5. **更新文档**（任务 12）

## 注意事项

1. **向后兼容**：保留旧的 Agent，新旧可以共存
2. **逐步迁移**：一次迁移一个 Agent
3. **充分测试**：每个 Agent 都要有对应的测试
4. **文档更新**：及时更新使用文档

## 使用示例

```python
# 使用 v2 架构
from tableau_assistant.src.agents.question_boost_agent_v2 import question_boost_agent_node_v2

# 使用默认模型
result = await question_boost_agent_node_v2(state, runtime)

# 使用前端指定的模型
result = await question_boost_agent_node_v2(
    state, runtime,
    model_config={
        "provider": "openai",
        "model_name": "gpt-4o",
        "temperature": 0.3
    }
)
```
