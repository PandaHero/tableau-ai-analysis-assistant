"""
任务规划 Agent (支持双模板: Query + Processing)

功能：
1. 将用户问题转换为VizQL查询规格或数据处理指令
2. 字段选择（基于元数据和维度层级）
3. 任务拆分决策（基于VizQL能力）
4. 依赖关系识别（Stage分配）
5. 智能补全（聚合、排序、筛选、时间粒度）
6. 支持post_processing类型的子任务生成

设计原则：
- 使用 BaseVizQLAgent 提供的统一架构
- 根据execution_type选择不同的prompt模板
- 统一使用流式输出
- AI 做规划，代码做执行
- 输出技术级别的查询规格（可直接用于查询构建）
"""
from typing import Dict, Any, Optional, List
from langgraph.runtime import Runtime

from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.src.models.state import VizQLState
from tableau_assistant.src.models.query_plan import (
    QueryPlanningResult,
    QuerySubTask,
    ProcessingSubTask,
    ProcessingInstruction,
    SubTask
)
from tableau_assistant.src.models.question import SubQuestion, SubQuestionExecutionType
from tableau_assistant.src.agents.base_agent import BaseVizQLAgent
from tableau_assistant.prompts.task_planner import (
    TASK_PLANNER_PROMPT,
    PROCESSING_TASK_PROMPT
)


class TaskPlannerAgent(BaseVizQLAgent):
    """
    Task Planner Agent using BaseVizQLAgent architecture
    
    Converts business questions into technical VizQL query specifications or processing instructions:
    - Field selection based on metadata and dimension hierarchy
    - Task decomposition based on VizQL capabilities
    - Dependency identification and stage assignment
    - Smart completion (aggregation, sorting, filtering, time granularity)
    - Support for post_processing subtasks (yoy, mom, growth_rate, percentage, custom)
    """
    
    def __init__(self):
        """Initialize with Task Planner Prompt (for query tasks)"""
        super().__init__(TASK_PLANNER_PROMPT)
        # Store processing prompt for later use
        self.processing_prompt = PROCESSING_TASK_PROMPT
    
    async def execute(
        self,
        state: VizQLState,
        runtime: Runtime[VizQLContext],
        model_config: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute task planner with dual-template support
        
        根据sub_questions的execution_type选择不同的处理策略:
        - query类型: 使用LLM生成QuerySubTask
        - post_processing类型: 直接生成ProcessingSubTask(不需要LLM)
        
        Args:
            state: Current VizQL state
            runtime: Runtime context
            model_config: Optional model configuration
            **kwargs: Additional arguments
        
        Returns:
            Dict with query_plan for state update
        """
        understanding = state.get("understanding")
        if not understanding or not hasattr(understanding, 'sub_questions'):
            raise ValueError("缺少问题理解结果或sub_questions")
        
        # 分离query和post_processing类型的子问题
        query_sub_questions = []
        processing_sub_questions = []
        
        for i, sq in enumerate(understanding.sub_questions):
            if sq.execution_type == SubQuestionExecutionType.QUERY:
                query_sub_questions.append((i, sq))
            else:  # POST_PROCESSING
                processing_sub_questions.append((i, sq))
        
        # 生成所有subtasks
        all_subtasks: List[SubTask] = [None] * len(understanding.sub_questions)
        
        # 1. 为query类型的子问题生成QuerySubTask (使用LLM)
        if query_sub_questions:
            # 准备只包含query类型子问题的understanding
            query_result = await self._generate_query_subtasks(
                understanding,
                query_sub_questions,
                state,
                runtime,
                model_config
            )
            
            # 将生成的QuerySubTask放到正确的位置
            for (original_index, _), subtask in zip(query_sub_questions, query_result.subtasks):
                all_subtasks[original_index] = subtask
        
        # 2. 为post_processing类型的子问题生成ProcessingSubTask (不使用LLM)
        for original_index, sq in processing_sub_questions:
            processing_subtask = self._generate_processing_subtask(sq, original_index)
            all_subtasks[original_index] = processing_subtask
        
        # 3. 构建最终的QueryPlanningResult
        final_result = QueryPlanningResult(
            subtasks=all_subtasks,
            reasoning=f"Generated {len(query_sub_questions)} query subtasks and {len(processing_sub_questions)} processing subtasks",
            complexity=None,  # 将在_process_result中填充
            estimated_rows=None  # 将在_process_result中填充
        )
        
        # 4. 处理结果
        return self._process_result(final_result, state)
    
    async def _generate_query_subtasks(
        self,
        understanding,
        query_sub_questions: List[tuple],
        state: VizQLState,
        runtime: Runtime[VizQLContext],
        model_config: Optional[Dict[str, Any]] = None
    ) -> QueryPlanningResult:
        """
        为query类型的子问题生成QuerySubTask
        
        直接调用LLM生成QuerySubTask,返回Pydantic模型对象
        
        Args:
            understanding: 问题理解结果
            query_sub_questions: query类型的子问题列表 [(index, SubQuestion), ...]
            state: 当前状态
            runtime: 运行时上下文
            model_config: 模型配置
        
        Returns:
            QueryPlanningResult (只包含QuerySubTask)
        """
        # 准备输入数据 - 只包含 query 类型的子问题
        input_data = self._prepare_input_data(state, query_sub_questions=query_sub_questions)
        
        # 直接调用 _execute_with_prompt,返回 Pydantic 模型对象
        query_result = await self._execute_with_prompt(input_data, runtime, model_config)
        
        return query_result
    
    def _format_metadata_by_category(self, metadata) -> str:
        """
        Format metadata grouped by category for LLM input.
        
        Returns formatted string organized by 7 categories:
        - geographic, temporal, product, customer, organizational, financial, other
        
        Args:
            metadata: Metadata object
        
        Returns:
            Formatted string with category-grouped fields
        """
        if not hasattr(metadata, 'fields'):
            return "No metadata available"
        
        # Group fields by category
        category_groups = {
            'geographic': [],
            'temporal': [],
            'product': [],
            'customer': [],
            'organizational': [],
            'financial': [],
            'other': []
        }
        
        for field in metadata.fields:
            category = field.category if hasattr(field, 'category') and field.category else 'other'
            # Normalize category name
            category_lower = category.lower()
            if category_lower not in category_groups:
                category_lower = 'other'
            
            # Build field info
            field_parts = [field.name]
            
            if hasattr(field, 'level') and field.level:
                field_parts.append(f"level: {field.level}")
            
            if hasattr(field, 'sample_values') and field.sample_values:
                samples = field.sample_values[:3]
                field_parts.append(f"samples: {samples}")
            
            category_groups[category_lower].append(f"  - {', '.join(field_parts)}")
        
        # Format output
        lines = []
        for category, fields in category_groups.items():
            if fields:
                lines.append(f"{category.capitalize()} Fields:")
                lines.extend(fields)
                lines.append("")
        
        return "\n".join(lines)
    
    def _prepare_input_data(
        self,
        state: VizQLState,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Prepare input data for task planner prompt
        
        Args:
            state: Current VizQL state
            **kwargs: Additional arguments
                query_sub_questions: Optional list of (index, SubQuestion) tuples to filter
        
        Returns:
            Dict with understanding, metadata, dimension_hierarchy, and num_sub_questions
        """
        # Get understanding result
        understanding = state.get("understanding")
        if not understanding:
            raise ValueError("缺少问题理解结果")
        
        # Get metadata
        metadata = state.get("metadata")
        if not metadata:
            raise ValueError("缺少元数据")
        
        # Get dimension hierarchy
        dimension_hierarchy = state.get("dimension_hierarchy") or {}
        if hasattr(metadata, 'dimension_hierarchy') and metadata.dimension_hierarchy:
            dimension_hierarchy = metadata.dimension_hierarchy
        
        # Filter sub-questions if query_sub_questions is provided
        query_sub_questions = kwargs.get('query_sub_questions')
        
        if query_sub_questions is not None:
            # Only include query-type sub-questions
            num_sub_questions = len(query_sub_questions)
            sub_questions_list = "\n".join([
                f"{i+1}. {sq.text} (execution_type: {sq.execution_type})"
                for i, (_, sq) in enumerate(query_sub_questions)
            ])
        elif hasattr(understanding, 'sub_questions'):
            # Include all sub-questions
            num_sub_questions = len(understanding.sub_questions)
            sub_questions_list = "\n".join([
                f"{i+1}. {sq.text} (execution_type: {sq.execution_type})"
                for i, sq in enumerate(understanding.sub_questions)
            ])
        else:
            num_sub_questions = 1
            sub_questions_list = "1. " + str(understanding.original_question if hasattr(understanding, 'original_question') else "Unknown")
        
        # Extract max_date from metadata for date filter generation
        max_date = "Unknown"
        if metadata and hasattr(metadata, 'max_date_by_field'):
            # Get the maximum date from all date fields
            max_dates = metadata.max_date_by_field
            if max_dates:
                # Use the first available max date
                max_date = next(iter(max_dates.values()), "Unknown")
        
        # Get original question
        original_question = understanding.original_question if hasattr(understanding, 'original_question') else state.get("question", "")
        
        # Format sub-questions with detailed field information for LLM
        sub_questions_detailed = []
        if query_sub_questions is not None:
            # Only include query-type sub-questions with details
            for i, (original_idx, sq) in enumerate(query_sub_questions):
                sq_info = {
                    "index": i + 1,
                    "original_index": original_idx,
                    "text": sq.text,
                    "execution_type": sq.execution_type,
                    "mentioned_dimensions": sq.mentioned_dimensions if hasattr(sq, 'mentioned_dimensions') else [],
                    "mentioned_measures": sq.mentioned_measures if hasattr(sq, 'mentioned_measures') else [],
                    "mentioned_date_fields": sq.mentioned_date_fields if hasattr(sq, 'mentioned_date_fields') else [],
                    "dimension_aggregations": sq.dimension_aggregations if hasattr(sq, 'dimension_aggregations') else None,
                    "measure_aggregations": sq.measure_aggregations if hasattr(sq, 'measure_aggregations') else None,
                    "date_field_functions": sq.date_field_functions if hasattr(sq, 'date_field_functions') else None,
                    "filter_date_field": sq.filter_date_field if hasattr(sq, 'filter_date_field') else None,
                    "time_range": sq.time_range.model_dump() if hasattr(sq, 'time_range') and sq.time_range else None,
                    "depends_on_indices": sq.depends_on_indices if hasattr(sq, 'depends_on_indices') else []
                }
                sub_questions_detailed.append(sq_info)
        elif hasattr(understanding, 'sub_questions'):
            # Include all sub-questions with details
            for i, sq in enumerate(understanding.sub_questions):
                if sq.execution_type == "query":
                    sq_info = {
                        "index": i + 1,
                        "original_index": i,
                        "text": sq.text,
                        "execution_type": sq.execution_type,
                        "mentioned_dimensions": sq.mentioned_dimensions if hasattr(sq, 'mentioned_dimensions') else [],
                        "mentioned_measures": sq.mentioned_measures if hasattr(sq, 'mentioned_measures') else [],
                        "mentioned_date_fields": sq.mentioned_date_fields if hasattr(sq, 'mentioned_date_fields') else [],
                        "dimension_aggregations": sq.dimension_aggregations if hasattr(sq, 'dimension_aggregations') else None,
                        "measure_aggregations": sq.measure_aggregations if hasattr(sq, 'measure_aggregations') else None,
                        "date_field_functions": sq.date_field_functions if hasattr(sq, 'date_field_functions') else None,
                        "filter_date_field": sq.filter_date_field if hasattr(sq, 'filter_date_field') else None,
                        "time_range": sq.time_range.model_dump() if hasattr(sq, 'time_range') and sq.time_range else None,
                        "depends_on_indices": sq.depends_on_indices if hasattr(sq, 'depends_on_indices') else []
                    }
                    sub_questions_detailed.append(sq_info)
        
        # Format sub_questions as JSON string for better LLM parsing
        import json
        sub_questions_json = json.dumps(sub_questions_detailed, ensure_ascii=False, indent=2)
        
        # # Debug: Print sub_questions_detailed
        # print(f"\n=== Task Planner input - sub_questions ===")
        # print(sub_questions_json)
        # print(f"=== End ===\n")
        
        # Format metadata by category for better field mapping
        formatted_metadata = self._format_metadata_by_category(metadata)
        
        return {
            "original_question": original_question,
            "sub_questions": sub_questions_json,
            "metadata": formatted_metadata,
            "dimension_hierarchy": dimension_hierarchy,
            "num_sub_questions": num_sub_questions,
            "sub_questions_list": sub_questions_list,
            "max_date": max_date
        }
    
    def _generate_processing_subtask(
        self,
        sub_question: SubQuestion,
        index: int
    ) -> ProcessingSubTask:
        """
        生成数据处理子任务
        
        直接生成ProcessingInstruction,不需要LLM。
        输出字段名将由DataProcessor根据processing_type和实际数据自动生成。
        
        Args:
            sub_question: 子问题对象
            index: 子问题索引(从0开始)
        
        Returns:
            ProcessingSubTask实例
        """
        # 生成ProcessingInstruction
        instruction = ProcessingInstruction(
            processing_type=sub_question.processing_type,
            source_tasks=[f"q{i+1}" for i in sub_question.depends_on_indices],
            calculation_formula=self._generate_formula_if_needed(sub_question)
        )
        
        # 计算stage: 依赖任务的最大stage + 1
        stage = max([i + 1 for i in sub_question.depends_on_indices], default=0) + 1
        
        return ProcessingSubTask(
            task_type="post_processing",
            question_id=f"q{index+1}",
            question_text=sub_question.text,
            stage=stage,
            depends_on=[f"q{i+1}" for i in sub_question.depends_on_indices],
            rationale=f"Generate {sub_question.processing_type} processing instruction for: {sub_question.text}",
            processing_instruction=instruction
        )
    
    def _generate_formula_if_needed(self, sub_question: SubQuestion) -> Optional[str]:
        """
        为custom类型生成计算公式
        
        Args:
            sub_question: 子问题对象
        
        Returns:
            计算公式(仅custom类型)
        """
        if sub_question.processing_type == "custom":
            # 对于custom类型,从文本中提取或生成公式描述
            return f"Custom calculation based on: {sub_question.text}"
        return None
    
    def _process_result(
        self,
        result: QueryPlanningResult,
        state: VizQLState
    ) -> Dict[str, Any]:
        """
        Process task planning result
        
        自动填充可选字段（如果LLM没有生成）：
        - complexity: 从understanding中复用
        - estimated_rows: 根据subtasks数量估算
        
        Args:
            result: QueryPlanningResult model instance
            state: Current VizQL state
        
        Returns:
            Dict with query_plan for state update
        """
        understanding = state.get("understanding")
        
        # 自动填充complexity（如果LLM没生成）
        if result.complexity is None and understanding:
            if hasattr(understanding, 'complexity'):
                complexity_value = understanding.complexity
                # 处理Enum类型
                if hasattr(complexity_value, 'value'):
                    result.complexity = complexity_value.value
                else:
                    result.complexity = str(complexity_value)
        
        # 自动填充estimated_rows（如果LLM没生成）
        if result.estimated_rows is None:
            # 简单估算：每个subtask约50行
            result.estimated_rows = len(result.subtasks) * 50
        
        return {
            "query_plan": result,
            "current_stage": "execution"
        }


# Create agent instance for easy import
task_planner_agent = TaskPlannerAgent()


async def query_planner_agent_node(
    state: VizQLState,
    runtime: Runtime[VizQLContext],
    model_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    任务规划 Agent 节点（使用 BaseVizQLAgent 架构）
    
    职责：
    - 字段选择（精确匹配元数据）
    - 任务拆分决策（基于VizQL能力）
    - 生成完整的VizQL查询规格
    - Stage分配和依赖关系识别
    
    注意：
    - 使用 BaseVizQLAgent 提供的统一执行流程
    - 需要元数据和维度层级
    - 支持前端模型配置（model_config）
    - 统一使用流式输出
    - 输出技术级别的查询规格
    
    Args:
        state: 当前状态
        runtime: 运行时上下文
        model_config: 可选的模型配置（来自前端）
    
    Returns:
        状态更新（包含 query_plan 字段）
    """
    try:
        return await task_planner_agent.execute(
            state=state,
            runtime=runtime,
            model_config=model_config
        )
    except Exception as e:
        return {
            "query_plan": None,
            "error": f"查询规划失败: {str(e)}",
            "current_stage": "error"
        }


# ============= 导出 =============

__all__ = [
    "query_planner_agent_node",
]
