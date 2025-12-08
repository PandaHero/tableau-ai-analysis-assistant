"""
Metadata Tool - 元数据获取工具

薄封装 MetadataManager，提供 LLM 友好的元数据获取接口。

特性：
- 支持按角色过滤（dimension/measure）
- 支持按类别过滤
- 返回 LLM 友好格式的字段列表
- 大结果由 FilesystemMiddleware 自动处理

Requirements:
- R5.1: 提供 get_metadata 工具，委托给 MetadataManager
- R5.2: 使用 @tool 装饰器，定义清晰的输入参数和返回类型
- R5.3: 将 Metadata 对象转换为 LLM 友好格式
- R5.4: 返回字段关键信息
- R5.5: 支持 filter_role 和 filter_category 参数
- R5.6: 大结果由 FilesystemMiddleware 处理
"""
from typing import Optional, List, Any
from pydantic import BaseModel, Field
from langchain_core.tools import tool
import logging

from tableau_assistant.src.tools.base import (
    ToolResponse,
    ToolErrorCode,
    format_tool_response,
)

logger = logging.getLogger(__name__)


class GetMetadataInput(BaseModel):
    """get_metadata 工具输入参数"""
    use_cache: bool = Field(
        default=True,
        description="是否使用缓存（默认 True）"
    )
    enhance: bool = Field(
        default=True,
        description="是否增强元数据，包括维度层级推断（默认 True）"
    )
    filter_role: Optional[str] = Field(
        default=None,
        description="按角色过滤：'dimension' 或 'measure'"
    )
    filter_category: Optional[str] = Field(
        default=None,
        description="按类别过滤，如 'time', 'geography', 'product' 等"
    )


def _format_field_for_llm(field: Any) -> str:
    """
    格式化单个字段为 LLM 友好格式
    
    包含关键信息：name, fieldCaption, role, dataType, category, level, 
    granularity, sample_values (前5个)
    
    **Validates: Requirements 5.4**
    """
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
    
    # 维度层级信息
    if hasattr(field, 'category') and field.category:
        lines.append(f"    category: {field.category}")
    
    if hasattr(field, 'level') and field.level:
        lines.append(f"    level: {field.level}")
    
    if hasattr(field, 'granularity') and field.granularity:
        lines.append(f"    granularity: {field.granularity}")
    
    # 样本值（前5个）
    if hasattr(field, 'sample_values') and field.sample_values:
        samples = field.sample_values[:5]
        lines.append(f"    sample_values: {samples}")
    
    return "\n".join(lines)


def _format_metadata_for_llm(fields: List[Any], datasource_name: str = "") -> str:
    """
    格式化元数据为 LLM 友好格式
    
    **Validates: Requirements 5.3**
    
    Args:
        fields: 字段列表
        datasource_name: 数据源名称
    
    Returns:
        格式化的字符串
    """
    lines = []
    
    # 头部信息
    if datasource_name:
        lines.append(f"# 数据源: {datasource_name}")
        lines.append("")
    
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


# 全局 MetadataManager 引用（由依赖注入设置）
_metadata_manager = None


def set_metadata_manager(manager: Any) -> None:
    """
    设置 MetadataManager 实例（依赖注入）
    
    Args:
        manager: MetadataManager 实例
    """
    global _metadata_manager
    _metadata_manager = manager
    logger.info("MetadataManager injected into metadata_tool")


def get_metadata_manager() -> Any:
    """获取 MetadataManager 实例"""
    return _metadata_manager


@tool
async def get_metadata(
    use_cache: bool = True,
    enhance: bool = True,
    filter_role: Optional[str] = None,
    filter_category: Optional[str] = None
) -> str:
    """
    获取数据源元数据
    
    返回数据源的字段元数据，包括字段名称、类型、角色、维度层级等信息。
    这是理解数据结构的第一步，在构建查询之前应该先调用此工具。
    
    Args:
        use_cache: 是否使用缓存（默认 True，建议保持）
        enhance: 是否增强元数据，包括维度层级推断（默认 True）
        filter_role: 按角色过滤，可选值：'dimension'（维度）或 'measure'（度量）
        filter_category: 按类别过滤，如 'time'（时间）, 'geography'（地理）, 'product'（产品）等
    
    Returns:
        LLM 友好的元数据信息，包含字段列表及其属性。
        如果结果过大，会自动保存到文件并返回文件路径。
    
    Examples:
        获取完整元数据：
        >>> get_metadata()
        
        只获取维度字段：
        >>> get_metadata(filter_role="dimension")
        
        只获取时间类别字段：
        >>> get_metadata(filter_category="time")
    """
    global _metadata_manager
    
    # 检查依赖
    if _metadata_manager is None:
        response = ToolResponse.fail(
            code=ToolErrorCode.DEPENDENCY_ERROR,
            message="MetadataManager 未初始化",
            recoverable=False,
            suggestion="请确保在调用工具前已正确初始化 MetadataManager"
        )
        return format_tool_response(response)
    
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
        
        # 获取元数据
        # **Validates: Requirements 5.1**
        metadata = await _metadata_manager.get_metadata_async(
            use_cache=use_cache,
            enhance=enhance
        )
        
        # 应用过滤
        # **Validates: Requirements 5.5**
        fields = metadata.fields
        
        if filter_role:
            filter_role_upper = filter_role.upper()
            fields = [f for f in fields if f.role.upper() == filter_role_upper]
        
        if filter_category:
            filter_category_lower = filter_category.lower()
            fields = [
                f for f in fields 
                if hasattr(f, 'category') and f.category and f.category.lower() == filter_category_lower
            ]
        
        # 格式化输出
        # **Validates: Requirements 5.3, 5.4**
        result = _format_metadata_for_llm(
            fields=fields,
            datasource_name=metadata.datasource_name
        )
        
        logger.info(f"get_metadata returned {len(fields)} fields")
        
        # 大结果由 FilesystemMiddleware 自动处理
        # **Validates: Requirements 5.6**
        return result
        
    except Exception as e:
        logger.error(f"get_metadata failed: {e}")
        response = ToolResponse.fail(
            code=ToolErrorCode.EXECUTION_ERROR,
            message=f"获取元数据失败: {str(e)}",
            recoverable=True,
            suggestion="请检查数据源连接是否正常"
        )
        return format_tool_response(response)


__all__ = [
    "get_metadata",
    "set_metadata_manager",
    "get_metadata_manager",
    "GetMetadataInput",
]
