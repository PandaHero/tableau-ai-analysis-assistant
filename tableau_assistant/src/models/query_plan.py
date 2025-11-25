"""
查询规划数据模型

定义查询规划Agent的输出结构

设计理念：
- Task Planning Agent 输出中间层模型（Intent 模型）
- Query Builder 负责将 Intent 模型转换为 VizQL 模型
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal, Dict, Any, Union, Annotated
from tableau_assistant.src.models.question import ProcessingType
from tableau_assistant.src.models.intent import (
    DimensionIntent,
    MeasureIntent,
    DateFieldIntent,
    DateFilterIntent,
    FilterIntent,
    TopNIntent,
)


class ProcessingInstruction(BaseModel):
    """
    数据处理指令
    
    描述如何处理查询结果以得到最终数据。
    
    设计说明:
    - processing_type: 指定计算类型,DataProcessor根据此类型执行相应的计算逻辑
    - source_tasks: 指定依赖的查询任务,DataProcessor从这些任务的结果中获取数据
    - calculation_formula: 仅用于custom类型,描述自定义计算逻辑
    - 输出字段名由DataProcessor根据processing_type和实际数据自动生成,避免字段名冲突
    """
    model_config = ConfigDict(extra="forbid")
    
    processing_type: ProcessingType = Field(
        description="""Type of data processing operation.

Usage:
- Specify the calculation type for DataProcessor
- Use value from sub-question's processing_type

Values: Enum value from ProcessingType"""
    )
    
    source_tasks: List[str] = Field(
        description="""List of source task IDs.

Usage:
- Include all prerequisite task IDs
- Convert from sub-question's depends_on_indices (index 0 → 'q1', index 1 → 'q2')
- Minimum 1 element required

Values: List of task ID strings (e.g., ['q1', 'q2'])""",
        min_length=1
    )
    
    calculation_formula: Optional[str] = Field(
        default=None,
        description="""Custom calculation formula.

Usage:
- Include only when processing_type is 'custom'
- null for other processing types

Values: Formula description string or null"""
    )
    
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="""Additional processing metadata.

Usage:
- Include if additional context is needed
- Empty dict if no extra metadata

Values: Dictionary of metadata key-value pairs"""
    )


class SubTaskBase(BaseModel):
    """
    SubTask基础模型
    
    包含所有SubTask共有的字段
    """
    model_config = ConfigDict(extra="forbid")
    
    question_id: str = Field(
        description="子任务ID（如q1, q2）",
        pattern=r"^q\d+$",
        examples=["q1", "q2", "q3"]
    )
    
    question_text: str = Field(
        description="子任务描述",
        examples=["获取2024年的销售额", "获取2023年的销售额"]
    )
    
    stage: int = Field(
        ge=1,
        description="执行阶段（1=独立任务，2+=依赖前序任务）"
    )
    
    depends_on: List[str] = Field(
        default_factory=list,
        description="依赖的子任务ID列表"
    )
    
    rationale: str = Field(
        description="子任务规划理由"
    )


class QuerySubTask(SubTaskBase):
    """
    VizQL查询任务（中间层模型）
    
    由 Task Planning Agent 输出，包含 Intent 模型。
    Query Builder 负责将 Intent 模型转换为 VizQL 模型。
    
    设计理念：
    - 不包含 VizQL 模型（BasicField、FunctionField、VizQLFilter 等）
    - 使用 Intent 模型表示查询意图
    - 维度、度量、日期字段分开定义
    - 字段映射和查询细节识别由 Task Planning Agent 完成
    """
    task_type: Literal["query"] = "query"
    
    dimension_intents: List[DimensionIntent] = Field(
        default_factory=list,
        description="""List of dimension intents.

Usage:
- Include one DimensionIntent for each dimension in sub-question
- Map business terms to technical fields
- Use aggregation from sub-question's dimension_aggregations dict

Values: List of DimensionIntent objects"""
    )
    
    measure_intents: List[MeasureIntent] = Field(
        default_factory=list,
        description="""List of measure intents.

Usage:
- Include one MeasureIntent for each measure in sub-question
- Map business terms to technical fields
- Use aggregation from sub-question's measure_aggregations dict

Values: List of MeasureIntent objects"""
    )
    
    date_field_intents: List[DateFieldIntent] = Field(
        default_factory=list,
        description="""List of date field intents for grouping.

Usage:
- Include one DateFieldIntent for each date field in sub-question
- Map business terms to technical fields
- Use date_function from sub-question's date_field_functions dict

Values: List of DateFieldIntent objects"""
    )
    
    date_filter_intent: Optional[DateFilterIntent] = Field(
        default=None,
        description="""Date filter intent.

Usage:
- Include if sub-question has date filtering requirement
- null if no date filtering

Values: DateFilterIntent object or null"""
    )
    
    filter_intents: Optional[List[FilterIntent]] = Field(
        default=None,
        description="""List of non-date filter intents.

Usage:
- Include if sub-question has non-date filtering requirements
- null if no non-date filtering

Values: List of FilterIntent objects or null"""
    )
    
    topn_intent: Optional[TopNIntent] = Field(
        default=None,
        description="""TopN intent.

Usage:
- Include only if original question explicitly requests TopN (e.g., 'top 5', 'bottom 10')
- null if no TopN requirement

Values: TopNIntent object or null"""
    )


class ProcessingSubTask(SubTaskBase):
    """
    数据处理任务
    
    用于执行数据计算和处理
    """
    task_type: Literal["post_processing"] = "post_processing"
    
    processing_instruction: ProcessingInstruction = Field(
        description="数据处理指令"
    )


# 使用discriminator确保正确的类型识别
SubTask = Annotated[
    Union[QuerySubTask, ProcessingSubTask],
    Field(discriminator='task_type')
]


class QueryPlanningResult(BaseModel):
    """
    查询规划结果
    
    包含所有子任务和规划元信息
    
    注意：complexity和estimated_rows是可选的
    - 如果LLM生成了就使用LLM的值
    - 如果没生成，会在_process_result中自动填充
    """
    model_config = ConfigDict(extra="forbid")
    
    subtasks: List[SubTask] = Field(
        min_length=1,
        description="""List of subtasks for execution.

Usage:
- MUST contain EXACTLY one subtask for EACH sub-question
- If understanding has N sub-questions, this array MUST have N subtasks

Values: List of SubTask objects (QuerySubTask or ProcessingSubTask)"""
    )
    
    reasoning: str = Field(
        description="""Planning reasoning process.

Usage:
- Explain the planning decisions and approach
- Document why subtasks were structured this way

Values: Reasoning explanation string"""
    )
    
    complexity: Optional[Literal["Simple", "Medium", "Complex"]] = Field(
        default=None,
        description="""Query complexity assessment.

Usage:
- Include if assessing complexity
- null to reuse from understanding result

Values: null (reuse from understanding) or complexity level"""
    )
    
    estimated_rows: Optional[int] = Field(
        default=None,
        ge=0,
        description="""Estimated number of rows to return.

Usage:
- Include if estimating result size
- null for automatic estimation

Values: Positive integer or null"""
    )


# ============= 导出 =============

__all__ = [
    "ProcessingInstruction",
    "SubTaskBase",
    "QuerySubTask",
    "ProcessingSubTask",
    "SubTask",
    "QueryPlanningResult",
]
