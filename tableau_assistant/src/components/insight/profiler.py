"""
DataProfiler Component

Generates data profiles including statistics and semantic groups.

Requirements:
- R8.1: Generate data profile (row_count, density, statistics)

Design Principles:
- 直接使用 metadata.dimension_hierarchy 中的维度层级信息
- 不重复造轮子，不使用硬编码关键词规则匹配
"""

import logging
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np

from .models import DataProfile, ColumnStats, SemanticGroup

logger = logging.getLogger(__name__)


class DataProfiler:
    """
    Data Profiler - generates comprehensive data profiles.
    
    Analyzes:
    - Basic statistics (count, density)
    - Column statistics (mean, median, std, quartiles)
    - Semantic groups (from dimension_hierarchy)
    
    Design Note:
    语义分组直接从 dimension_hierarchy 获取，不重新推断。
    dimension_hierarchy 由 DimensionHierarchyAgent 在工作流早期阶段生成。
    """
    
    def __init__(self, dimension_hierarchy: Optional[Dict[str, Any]] = None):
        """
        Initialize profiler.
        
        Args:
            dimension_hierarchy: 维度层级信息（来自 metadata.dimension_hierarchy）
                格式: {field_name: DimensionAttributes}
        """
        self._dimension_hierarchy = dimension_hierarchy or {}
    
    def set_dimension_hierarchy(self, hierarchy: Dict[str, Any]):
        """
        设置维度层级信息。
        
        Args:
            hierarchy: 来自 metadata.dimension_hierarchy
        """
        self._dimension_hierarchy = hierarchy or {}
    
    def profile(self, data: Any) -> DataProfile:
        """
        Generate a comprehensive profile of the data.
        
        Args:
            data: Input data (DataFrame, list of dicts, or dict)
            
        Returns:
            DataProfile with statistics and semantic groups
        """
        # Convert to DataFrame if needed
        df = self._to_dataframe(data)
        
        if df.empty:
            return DataProfile(
                row_count=0,
                column_count=0,
                density=0.0,
                statistics={},
                semantic_groups=[],
            )
        
        return DataProfile(
            row_count=len(df),
            column_count=len(df.columns),
            density=self._calculate_density(df),
            statistics=self._calculate_statistics(df),
            semantic_groups=self._build_semantic_groups_from_hierarchy(df),
        )
    
    def _to_dataframe(self, data: Any) -> pd.DataFrame:
        """Convert various data formats to DataFrame."""
        if isinstance(data, pd.DataFrame):
            return data
        elif isinstance(data, list):
            if not data:
                return pd.DataFrame()
            if isinstance(data[0], dict):
                return pd.DataFrame(data)
            return pd.DataFrame(data)
        elif isinstance(data, dict):
            return pd.DataFrame([data])
        else:
            logger.warning(f"Unknown data type: {type(data)}, returning empty DataFrame")
            return pd.DataFrame()
    
    def _calculate_density(self, df: pd.DataFrame) -> float:
        """Calculate data density (non-null ratio)."""
        if df.empty:
            return 0.0
        total_cells = df.shape[0] * df.shape[1]
        if total_cells == 0:
            return 0.0
        non_null_cells = df.notna().sum().sum()
        return float(non_null_cells / total_cells)
    
    def _calculate_statistics(self, df: pd.DataFrame) -> Dict[str, ColumnStats]:
        """Calculate statistics for numeric columns."""
        stats = {}
        
        # Select numeric columns
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        for col in numeric_cols:
            try:
                col_data = df[col].dropna()
                if len(col_data) == 0:
                    continue
                
                stats[col] = ColumnStats(
                    mean=float(col_data.mean()),
                    median=float(col_data.median()),
                    std=float(col_data.std()) if len(col_data) > 1 else 0.0,
                    min=float(col_data.min()),
                    max=float(col_data.max()),
                    q25=float(col_data.quantile(0.25)),
                    q75=float(col_data.quantile(0.75)),
                )
            except Exception as e:
                logger.warning(f"Failed to calculate stats for column {col}: {e}")
        
        return stats
    
    def _build_semantic_groups_from_hierarchy(self, df: pd.DataFrame) -> List[SemanticGroup]:
        """
        Build semantic groups from dimension_hierarchy.
        
        直接使用 DimensionHierarchyAgent 推断的结果，不重新推断。
        """
        groups_by_type: Dict[str, List[str]] = {
            "time": [],
            "geographic": [],
            "category": [],
            "numeric": [],
        }
        
        # 从 dimension_hierarchy 获取语义分组
        for col in df.columns:
            if col in self._dimension_hierarchy:
                attrs = self._dimension_hierarchy[col]
                # attrs 可能是 dict 或 DimensionAttributes 对象
                category = attrs.get("category") if isinstance(attrs, dict) else getattr(attrs, "category", None)
                
                if category == "time":
                    groups_by_type["time"].append(col)
                elif category == "geographic":
                    groups_by_type["geographic"].append(col)
                elif category in ("product", "customer", "organization", "financial", "other"):
                    # 这些都归类为 category（分类维度）
                    groups_by_type["category"].append(col)
            elif pd.api.types.is_numeric_dtype(df[col]):
                # 数值列（度量）
                groups_by_type["numeric"].append(col)
            else:
                # 未在 hierarchy 中的非数值列，作为 category
                groups_by_type["category"].append(col)
        
        # 构建 SemanticGroup 列表
        result = []
        for group_type, columns in groups_by_type.items():
            if columns:
                result.append(SemanticGroup(type=group_type, columns=columns))
        
        return result
    
    def get_columns_by_category(self, category: str) -> List[str]:
        """
        获取指定类别的列。
        
        Args:
            category: 类别名称（geographic, time, product 等）
            
        Returns:
            该类别的列名列表
        """
        columns = []
        for col, attrs in self._dimension_hierarchy.items():
            col_category = attrs.get("category") if isinstance(attrs, dict) else getattr(attrs, "category", None)
            if col_category == category:
                columns.append(col)
        return columns
    
    def get_hierarchy_level(self, column: str) -> Optional[int]:
        """
        获取列的层级级别。
        
        Args:
            column: 列名
            
        Returns:
            层级级别 (1-5)，如果不在 hierarchy 中返回 None
        """
        if column in self._dimension_hierarchy:
            attrs = self._dimension_hierarchy[column]
            return attrs.get("level") if isinstance(attrs, dict) else getattr(attrs, "level", None)
        return None
