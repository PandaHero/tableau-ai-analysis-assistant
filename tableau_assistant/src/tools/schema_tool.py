"""
Schema Tool - Schema 模块选择工具

直接从 SemanticQuery 模型获取填写规则，减少 token 消耗。

设计原则：
- 规则来源于 SemanticQuery 模型的 docstring 和 field description
- 直接拼接返回，不做复杂解析
- 按需加载，减少 token 消耗
"""
from typing import List, Dict, Optional, Type
from pydantic import BaseModel, Field
from langchain_core.tools import tool
import logging

logger = logging.getLogger(__name__)


# 模块名称到模型类的映射
_MODULE_MAPPING: Dict[str, str] = {
    "measures": "MeasureSpec",
    "dimensions": "DimensionSpec",
    "filters": "FilterSpec",
    "time_filters": "TimeFilterSpec",
    "analyses": "AnalysisSpec",
    "output_control": "OutputControl",
    "semantic_query": "SemanticQuery",
}

# 模块描述
_MODULE_DESCRIPTIONS: Dict[str, str] = {
    "measures": "度量字段（销售额、利润等数值概念）",
    "dimensions": "维度字段（分组、分类概念）",
    "filters": "筛选条件（时间筛选、枚举筛选、数值范围筛选）",
    "time_filters": "时间筛选条件（2024年、最近3个月、年初至今）",
    "analyses": "分析计算（累计、排名、占比、同比环比）",
    "output_control": "输出控制（TopN、排序）",
    "semantic_query": "完整的语义查询结构",
}


def _get_model_class(module_name: str) -> Optional[Type[BaseModel]]:
    """获取模块对应的模型类"""
    class_name = _MODULE_MAPPING.get(module_name)
    if not class_name:
        return None

    from tableau_assistant.src.models.semantic import query

    return getattr(query, class_name, None)


def _format_model_schema(model_class: Type[BaseModel], module_name: str) -> str:
    """
    格式化模型的 schema 信息

    直接拼接 docstring 和 field descriptions
    """
    lines = []

    # 模块标题
    desc = _MODULE_DESCRIPTIONS.get(module_name, "")
    lines.append(f"# {module_name}")
    lines.append(f"**{desc}**")
    lines.append("")

    # 模型 docstring（包含 decision_tree、fill_order、examples 等）
    if model_class.__doc__:
        lines.append(model_class.__doc__.strip())
        lines.append("")

    # 字段信息
    lines.append("## 字段定义")
    lines.append("")

    for field_name, field_info in model_class.model_fields.items():
        if field_name.startswith("_"):
            continue

        # 字段标题
        is_required = field_info.is_required()
        req_marker = "必填" if is_required else "可选"
        lines.append(f"### {field_name} ({req_marker})")

        # 默认值（跳过 PydanticUndefined）
        if field_info.default is not None and str(field_info.default) != "PydanticUndefined":
            lines.append(f"默认值: `{field_info.default}`")

        # 字段描述（包含 decision_rule、examples 等）
        if field_info.description:
            lines.append("")
            lines.append(field_info.description)

        lines.append("")

    return "\n".join(lines)


class GetSchemaModuleInput(BaseModel):
    """get_schema_module 工具输入参数"""

    module_names: List[str] = Field(description="需要的模块列表")


@tool
def get_schema_module(module_names: List[str]) -> str:
    """
    获取指定数据模型模块的详细填写规则

    在生成结构化输出之前调用此工具，只获取你需要的模块！
    规则直接从 SemanticQuery 模型定义中获取。

    Args:
        module_names: 需要的模块列表，可选值：
            - measures: 度量字段（销售额、利润等数值）
            - dimensions: 维度字段（分组、分类）
            - filters: 筛选条件（时间、枚举、数值范围）
            - time_filters: 时间筛选条件（2024年、最近3个月）
            - analyses: 分析计算（累计、排名、占比）
            - output_control: 输出控制（TopN、排序）
            - semantic_query: 完整语义查询结构

    Returns:
        所选模块的详细填写规则
    """
    valid_modules = list(_MODULE_MAPPING.keys())
    invalid_modules = [m for m in module_names if m not in valid_modules]

    if invalid_modules:
        return f"<error>无效的模块名称: {invalid_modules}。可用模块: {valid_modules}</error>"

    if not module_names:
        return f"<error>请指定至少一个模块。可用模块: {valid_modules}</error>"

    contents = []
    for name in module_names:
        model_class = _get_model_class(name)
        if model_class:
            contents.append(_format_model_schema(model_class, name))

    logger.info(f"get_schema_module: loaded {len(module_names)} modules: {module_names}")

    return "\n\n---\n\n".join(contents)


__all__ = [
    "get_schema_module",
    "GetSchemaModuleInput",
]
