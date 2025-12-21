"""
Data Model Tool - 数据模型获取工具

提供 LLM 友好的数据模型获取接口。

数据模型包含：
- 字段元数据（名称、类型、角色、维度层级等）
- 逻辑表（表名、表ID）
- 表关系（表之间的关联）

特性：
- 支持按角色过滤（dimension/measure）
- 支持按类别过滤
- 返回全量字段，大结果由 FilesystemMiddleware 处理
- 从 WorkflowContext 获取数据模型
"""
from typing import Optional, List, Annotated
from pydantic import BaseModel, Field
from langchain_core.tools import tool, InjectedToolArg
from langchain_core.runnables import RunnableConfig
import logging

from tableau_assistant.src.orchestration.tools.base import (
    ToolResponse,
    ToolErrorCode,
    format_tool_response,
)

logger = logging.getLogger(__name__)


class GetDataModelInput(BaseModel):
    """get_data_model 工具输入参数"""
    filter_role: Optional[str] = Field(
        default=None,
        description="按角色过滤：'dimension' 或 'measure'"
    )
    filter_category: Optional[str] = Field(
        default=None,
        description="按类别过滤，如 'time', 'geography', 'product' 等"
    )


def _format_field_for_llm(field: object) -> str:
    """格式化单个字段为 LLM 友好格式"""
    lines = []
    
    # 基本信息
    name = getattr(field, 'name', str(field))
    caption = getattr(field, 'fieldCaption', name)
    role = getattr(field, 'role', 'unknown')
    data_type = getattr(field, 'dataType', 'unknown')
    
    lines.append(f"- {caption}")
    lines.append(f"    name: {name}")
    lines.append(f"    role: {role}")
    lines.append(f"    dataType: {data_type}")
    
    # 所属逻辑表（数据模型信息）
    if hasattr(field, 'logicalTableCaption') and field.logicalTableCaption:
        lines.append(f"    table: {field.logicalTableCaption}")
    
    # 可选信息
    if hasattr(field, 'description') and field.description:
        lines.append(f"    description: {field.description}")
    
    if hasattr(field, 'category') and field.category:
        lines.append(f"    category: {field.category}")
    
    if hasattr(field, 'level') and field.level:
        lines.append(f"    level: {field.level}")
    
    if hasattr(field, 'granularity') and field.granularity:
        lines.append(f"    granularity: {field.granularity}")
    
    if hasattr(field, 'aggregation') and field.aggregation:
        lines.append(f"    aggregation: {field.aggregation}")
    
    if hasattr(field, 'formula') and field.formula:
        lines.append(f"    formula: {field.formula}")
    
    if hasattr(field, 'sample_values') and field.sample_values:
        samples = field.sample_values[:5]  # 最多显示5个样本
        lines.append(f"    sample_values: {samples}")
    
    return "\n".join(lines)


def _format_data_model_for_llm(data_model: object) -> str:
    """
    格式化数据模型为 LLM 友好格式
    
    Args:
        data_model: DataModel 对象
    
    Returns:
        格式化的字符串
    """
    if not data_model:
        return ""
    
    lines = []
    lines.append("## 数据模型")
    lines.append("")
    
    # 逻辑表
    logical_tables = getattr(data_model, 'logicalTables', [])
    if logical_tables:
        lines.append(f"### 逻辑表 ({len(logical_tables)} 个)")
        lines.append("")
        for table in logical_tables:
            table_id = getattr(table, 'logicalTableId', 'unknown')
            caption = getattr(table, 'caption', 'unknown')
            lines.append(f"- {caption} (ID: {table_id})")
        lines.append("")
    
    # 表关系
    relationships = getattr(data_model, 'logicalTableRelationships', [])
    if relationships:
        lines.append(f"### 表关系 ({len(relationships)} 个)")
        lines.append("")
        for rel in relationships:
            from_id = getattr(rel, 'fromLogicalTableId', 'unknown')
            to_id = getattr(rel, 'toLogicalTableId', 'unknown')
            # 尝试获取表名
            from_caption = data_model.get_table_caption(from_id) if hasattr(data_model, 'get_table_caption') else from_id
            to_caption = data_model.get_table_caption(to_id) if hasattr(data_model, 'get_table_caption') else to_id
            lines.append(f"- {from_caption} → {to_caption}")
        lines.append("")
    
    return "\n".join(lines)


def _format_data_model_output(
    fields: List[object],
    datasource_name: str = "",
    data_model: Optional[object] = None
) -> str:
    """
    格式化数据模型输出为 LLM 友好格式
    
    Args:
        fields: 字段列表
        datasource_name: 数据源名称
        data_model: 数据模型（可选）
    
    Returns:
        格式化的字符串
    """
    lines = []
    
    # 头部信息
    if datasource_name:
        lines.append(f"# 数据源: {datasource_name}")
        lines.append("")
    
    # 数据模型信息
    if data_model:
        data_model_str = _format_data_model_for_llm(data_model)
        if data_model_str:
            lines.append(data_model_str)
    
    lines.append(f"## 字段列表 (共 {len(fields)} 个)")
    lines.append("")
    
    # 分组：维度和度量
    dimensions = [f for f in fields if getattr(f, 'role', '').upper() == 'DIMENSION']
    measures = [f for f in fields if getattr(f, 'role', '').upper() == 'MEASURE']
    
    if dimensions:
        lines.append(f"### 维度 ({len(dimensions)} 个)")
        lines.append("")
        for field in dimensions:
            lines.append(_format_field_for_llm(field))
            lines.append("")
    
    if measures:
        lines.append(f"### 度量 ({len(measures)} 个)")
        lines.append("")
        for field in measures:
            lines.append(_format_field_for_llm(field))
            lines.append("")
    
    return "\n".join(lines)


@tool
async def get_data_model(
    filter_role: Optional[str] = None,
    filter_category: Optional[str] = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,  # type: ignore[assignment]
) -> str:
    """
    获取数据源数据模型
    
    返回数据源的完整数据模型，包括：
    - 字段信息（名称、类型、角色、维度层级等）
    - 逻辑表（表名、表ID）
    - 表关系（表之间的关联）
    
    这是理解数据结构的第一步，在构建查询之前应该先调用此工具。
    
    Args:
        filter_role: 按角色过滤，可选值：'dimension'（维度）或 'measure'（度量）
        filter_category: 按类别过滤，如 'time'（时间）, 'geography'（地理）, 'product'（产品）等
    
    Returns:
        LLM 友好的数据模型信息，包含逻辑表、表关系、字段列表等。
        如果结果过大，会自动保存到文件并返回文件路径。
    
    Examples:
        获取完整数据模型：
        >>> get_data_model()
        
        只获取维度字段：
        >>> get_data_model(filter_role="dimension")
        
        只获取时间类别字段：
        >>> get_data_model(filter_category="time")
    """
    try:
        # 验证 filter_role 参数
        if filter_role and filter_role.lower() not in ['dimension', 'measure']:
            response = ToolResponse.fail(
                code=ToolErrorCode.VALIDATION_ERROR,
                message=f"无效的 filter_role 值: {filter_role}",
                details={"valid_values": ["dimension", "measure"]},
                recoverable=True,
                suggestion="请使用 'dimension' 或 'measure'"
            )
            return format_tool_response(response)
        
        # 从 WorkflowContext 获取数据模型
        data_model = None
        
        if config is not None:
            from tableau_assistant.src.orchestration.workflow.context import get_context
            ctx = get_context(config)
            if ctx is not None and ctx.data_model is not None:
                data_model = ctx.data_model
                logger.debug("get_data_model: using data_model from WorkflowContext")
        
        # 检查是否获取到数据模型
        if data_model is None:
            response = ToolResponse.fail(
                code=ToolErrorCode.DEPENDENCY_ERROR,
                message="无法获取数据模型：WorkflowContext 中没有 data_model",
                recoverable=False,
                suggestion="请确保工作流已正确初始化，并调用了 ensure_metadata_loaded()"
            )
            return format_tool_response(response)
        
        # 应用过滤
        fields = data_model.fields
        
        if filter_role:
            filter_role_upper = filter_role.upper()
            fields = [f for f in fields if f.role.upper() == filter_role_upper]
        
        if filter_category:
            filter_category_lower = filter_category.lower()
            fields = [
                f for f in fields 
                if hasattr(f, 'category') and f.category and f.category.lower() == filter_category_lower
            ]
        
        # 格式化输出（包含数据模型）
        result = _format_data_model_output(
            fields=fields,
            datasource_name=metadata.datasource_name,
            data_model=metadata.data_model
        )
        
        logger.info(f"get_data_model returned {len(fields)} fields, data_model={'yes' if metadata.data_model else 'no'}")
        return result
        
    except Exception as e:
        logger.error(f"get_data_model failed: {e}")
        response = ToolResponse.fail(
            code=ToolErrorCode.EXECUTION_ERROR,
            message=f"获取数据模型失败: {str(e)}",
            recoverable=True,
            suggestion="请检查数据源连接是否正常"
        )
        return format_tool_response(response)


__all__ = [
    "get_data_model",
    "GetDataModelInput",
]
