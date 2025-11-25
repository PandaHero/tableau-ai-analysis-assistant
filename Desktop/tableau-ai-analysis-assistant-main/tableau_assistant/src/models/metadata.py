"""
元数据数据模型

定义数据源和字段的元数据Pydantic模型，提供类型安全和验证。

模型：
- FieldMetadata: 单个字段的元数据
- Metadata: 数据源的完整元数据
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any, Literal


class FieldMetadata(BaseModel):
    """
    字段元数据模型
    
    描述单个字段的详细信息，包括基本属性、统计信息、维度层级推断结果等。
    """
    
    # 基本信息
    name: str = Field(..., description="字段名称")
    fieldCaption: str = Field(..., description="字段显示名称")
    role: Literal["dimension", "measure"] = Field(..., description="字段角色")
    dataType: str = Field(..., description="数据类型：DATE/DATETIME/STRING/INTEGER/REAL等")
    
    # 可选信息
    dataCategory: Optional[str] = Field(None, description="数据类别")
    aggregation: Optional[str] = Field(None, description="聚合方式")
    formula: Optional[str] = Field(None, description="计算公式")
    description: Optional[str] = Field(None, description="字段描述")
    
    # 统计信息
    sample_values: Optional[List[str]] = Field(None, description="样本值")
    unique_count: Optional[int] = Field(None, description="唯一值数量")
    
    # 维度层级推断结果（由dimension_hierarchy_agent添加）
    category: Optional[str] = Field(None, description="维度类别（地理/时间/产品/客户/组织/财务/其他）")
    category_detail: Optional[str] = Field(None, description="详细类别描述")
    level: Optional[int] = Field(None, description="层级级别（1-5）")
    granularity: Optional[str] = Field(None, description="粒度描述")
    parent_dimension: Optional[str] = Field(None, description="父维度字段名")
    child_dimension: Optional[str] = Field(None, description="子维度字段名")
    
    # 日期字段特有
    valid_max_date: Optional[str] = Field(None, description="有效最大日期（用于日期筛选）")
    
    model_config = ConfigDict(
        frozen=False,  # 允许修改（用于添加维度层级推断结果和valid_max_date）
        extra="allow"  # 允许额外字段
    )



class Metadata(BaseModel):
    """
    数据源元数据模型
    
    包含数据源的完整元数据信息，包括所有字段、维度层级等。
    提供便捷的查询方法。
    """
    
    # 数据源信息
    datasource_luid: str = Field(..., description="数据源LUID")
    datasource_name: str = Field(..., description="数据源名称")
    datasource_description: Optional[str] = Field(None, description="数据源描述")
    datasource_owner: Optional[str] = Field(None, description="数据源所有者")
    
    # 字段信息
    fields: List[FieldMetadata] = Field(..., description="字段列表")
    field_count: int = Field(..., description="字段数量")
    
    # 维度层级（可选）
    dimension_hierarchy: Optional[Dict[str, Any]] = Field(None, description="维度层级推断结果")
    
    # 原始响应（调试用）
    raw_response: Optional[Dict[str, Any]] = Field(None, description="原始GraphQL响应")
    
    model_config = ConfigDict(
        frozen=False,  # 允许修改（用于添加dimension_hierarchy）
        extra="allow"  # 允许额外字段
    )
    
    def get_field(self, field_name: str) -> Optional[FieldMetadata]:
        """
        根据字段名查询字段元数据
        
        Args:
            field_name: 字段名称（name或fieldCaption）
        
        Returns:
            FieldMetadata对象，如果不存在则返回None
        """
        for field in self.fields:
            if field.name == field_name or field.fieldCaption == field_name:
                return field
        return None
    
    def get_date_fields(self) -> List[FieldMetadata]:
        """
        获取所有日期字段（包括STRING类型的日期字段）
        
        识别策略：
        1. 原生DATE/DATETIME类型
        2. 通过维度推断识别的时间类别（STRING类型但category为时间）
        
        Returns:
            日期字段列表
        """
        date_fields = []
        for field in self.fields:
            # 1. 原生DATE/DATETIME类型
            if field.dataType in ("DATE", "DATETIME"):
                date_fields.append(field)
            # 2. 通过维度推断识别的时间类别（STRING类型但category为时间）
            elif field.category and "时间" in field.category:
                date_fields.append(field)
        return date_fields
    
    def get_dimensions(self) -> List[FieldMetadata]:
        """
        获取所有维度字段
        
        Returns:
            维度字段列表
        """
        return [field for field in self.fields if field.role == "dimension"]
    
    def get_measures(self) -> List[FieldMetadata]:
        """
        获取所有度量字段
        
        Returns:
            度量字段列表
        """
        return [field for field in self.fields if field.role == "measure"]
    
    def get_reference_date(self, mentioned_field: Optional[str] = None) -> Optional[str]:
        """
        获取参考日期（用于相对时间计算）
        
        实现智能参考日期选择逻辑，支持多日期字段场景。
        
        优先级：
        1. 用户明确提到的日期字段的 valid_max_date（精确）
        2. 所有日期字段中最大的 valid_max_date（保守）
        3. None（无可用日期）
        
        Args:
            mentioned_field: 用户提到的日期字段名（可选）
                           通常来自 QuerySubQuestion.filter_date_field
        
        Returns:
            参考日期字符串（ISO格式 YYYY-MM-DD），如果无可用日期则返回 None
        
        Examples:
            # 场景1: 用户明确提到 "订单日期最近3个月"
            >>> metadata.get_reference_date("订单日期")
            "2024-12-31"  # 使用订单日期的 valid_max_date
            
            # 场景2: 用户只说 "最近3个月"
            >>> metadata.get_reference_date(None)
            "2024-12-31"  # 使用所有日期字段中最大的 valid_max_date
            
            # 场景3: 无日期字段
            >>> metadata.get_reference_date(None)
            None
        """
        # 优先级1: 用户明确提到的日期字段
        if mentioned_field:
            field = self.get_field(mentioned_field)
            if field and field.valid_max_date:
                return field.valid_max_date
        
        # 优先级2: 所有日期字段中最大的日期（保守策略）
        max_dates = []
        for field in self.fields:
            if field.valid_max_date:
                max_dates.append(field.valid_max_date)
        
        if max_dates:
            # 返回最大的日期
            return max(max_dates)
        
        # 优先级3: 无可用日期
        return None


# ============= 导出 =============

__all__ = [
    "FieldMetadata",
    "Metadata",
]
