# -*- coding: utf-8 -*-
"""Tableau 查询构建器 - 将 SemanticQuery 转换为 VizQL API 请求。

这是从平台无关的 SemanticQuery 到 Tableau 特定 VizQL API 格式的核心转换层。

关键转换：
- Computation.partition_by → 表计算维度（分区）
- Computation 子类型（RankCalc 等）→ TableCalcType
- Filter 类型 → VizQL 过滤器类型
"""

import logging
from typing import Any

from analytics_assistant.src.core.interfaces import BaseQueryBuilder
from analytics_assistant.src.core.models import (
    AggregationType,
    Computation,
    DateGranularity,
    DateRangeFilter,
    DimensionField,
    MeasureField,
    NumericRangeFilter,
    RankStyle,
    RelativeTo,
    SemanticQuery,
    SetFilter,
    SortDirection,
    TextMatchFilter,
    TopNFilter,
    ValidationError,
    ValidationErrorType,
    ValidationResult,
)


logger = logging.getLogger(__name__)


# AggregationType 到 VizQL function 字符串的映射
AGGREGATION_TO_VIZQL: dict[AggregationType, str] = {
    AggregationType.SUM: "SUM",
    AggregationType.AVG: "AVG",
    AggregationType.COUNT: "COUNT",
    AggregationType.COUNTD: "COUNTD",
    AggregationType.MIN: "MIN",
    AggregationType.MAX: "MAX",
    AggregationType.MEDIAN: "MEDIAN",
    AggregationType.STDEV: "STDEV",
    AggregationType.VAR: "VAR",
}

# DateGranularity 到 VizQL TRUNC 函数的映射
GRANULARITY_TO_TRUNC: dict[DateGranularity, str] = {
    DateGranularity.YEAR: "TRUNC_YEAR",
    DateGranularity.QUARTER: "TRUNC_QUARTER",
    DateGranularity.MONTH: "TRUNC_MONTH",
    DateGranularity.WEEK: "TRUNC_WEEK",
    DateGranularity.DAY: "TRUNC_DAY",
}

# DateGranularity 到 DATETRUNC 参数的映射
GRANULARITY_TO_DATETRUNC: dict[DateGranularity, str] = {
    DateGranularity.YEAR: "year",
    DateGranularity.QUARTER: "quarter",
    DateGranularity.MONTH: "month",
    DateGranularity.WEEK: "week",
    DateGranularity.DAY: "day",
}


class TableauQueryBuilder(BaseQueryBuilder):
    """Tableau 查询构建器 - 将 SemanticQuery 转换为 VizQL 请求。
    
    Tableau 特定的默认值在这里定义。
    """
    
    # Tableau 特定的默认值
    DEFAULT_RANK_STYLE = RankStyle.COMPETITION
    DEFAULT_DIRECTION = SortDirection.DESC
    DEFAULT_RELATIVE_TO = RelativeTo.PREVIOUS
    DEFAULT_AGGREGATION = AggregationType.SUM
    DEFAULT_WINDOW_PREVIOUS = 2
    DEFAULT_WINDOW_NEXT = 0
    DEFAULT_INCLUDE_CURRENT = True
    
    def build(self, semantic_query: SemanticQuery, **kwargs: Any) -> dict:
        """从 SemanticQuery 构建 VizQL API 请求。
        
        Args:
            semantic_query: 平台无关的语义查询
            **kwargs: 额外参数：
                - datasource_id: 数据源 LUID
                - field_metadata: dict[str, dict] 字段名到元数据的映射
            
        Returns:
            VizQL API 请求字典
        """
        field_metadata = kwargs.get("field_metadata", {})
        fields = []
        
        # 构建维度字段
        if semantic_query.dimensions:
            for dim in semantic_query.dimensions:
                fields.append(self._build_dimension_field(dim, field_metadata))
        
        # 构建度量字段
        if semantic_query.measures:
            for measure in semantic_query.measures:
                fields.append(self._build_measure_field(measure))
        
        # 构建计算字段（LOD 必须在表计算之前）
        if semantic_query.computations:
            view_dims = [d.field_name for d in (semantic_query.dimensions or [])]
            comp_fields = self._build_computation_fields(
                semantic_query.computations, 
                view_dims,
                measures=semantic_query.measures,
            )
            fields.extend(comp_fields)
        
        # 构建过滤器
        filters = []
        if semantic_query.filters:
            for f in semantic_query.filters:
                vizql_filter = self._build_filter(f, field_metadata)
                if vizql_filter:
                    filters.append(vizql_filter)
        
        # 从带有 top_n 的计算构建 Top N 过滤器
        if semantic_query.computations:
            for comp in semantic_query.computations:
                if comp.calc_type in ("RANK", "DENSE_RANK") and getattr(comp, 'top_n', None):
                    top_n_filter = self._build_top_n_filter_from_computation(comp, semantic_query)
                    if top_n_filter:
                        filters.append(top_n_filter)
        
        # 构建请求
        request = {"fields": fields}
        
        if filters:
            request["filters"] = filters
        
        # 构建排序
        sorts_list = semantic_query.get_sorts()
        if sorts_list:
            sorts = self._build_sorts_from_tuples(sorts_list)
            if sorts:
                request["sorts"] = sorts
        
        if semantic_query.row_limit:
            request["rowLimit"] = semantic_query.row_limit
        
        return request
    
    def validate(self, semantic_query: SemanticQuery, **kwargs: Any) -> ValidationResult:
        """验证 SemanticQuery 是否适用于 Tableau 平台。"""
        errors = []
        warnings = []
        auto_fixed = []
        
        lod_calc_types = {"LOD_FIXED", "LOD_INCLUDE", "LOD_EXCLUDE"}
        
        # 检查空查询
        if not semantic_query.dimensions and not semantic_query.measures:
            errors.append(ValidationError(
                error_type=ValidationErrorType.MISSING_REQUIRED,
                field_path="dimensions/measures",
                message="查询必须至少有一个维度或度量",
            ))
        
        # 验证计算
        if semantic_query.computations:
            view_dims = set(d.field_name for d in (semantic_query.dimensions or []))
            measures = set(m.field_name for m in (semantic_query.measures or []))
            
            for i, comp in enumerate(semantic_query.computations):
                # 检查目标是否在度量中（非 LOD）
                if comp.calc_type not in lod_calc_types and comp.target not in measures:
                    errors.append(ValidationError(
                        error_type=ValidationErrorType.FIELD_NOT_FOUND,
                        field_path=f"computations[{i}].target",
                        message=f"目标 '{comp.target}' 不在度量中",
                        suggestion=f"将 '{comp.target}' 添加到度量或使用现有度量",
                    ))
                
                # 检查 partition_by 是否是维度的子集
                for p in comp.partition_by:
                    p_name = p.field_name if hasattr(p, 'field_name') else p
                    if p_name not in view_dims:
                        errors.append(ValidationError(
                            error_type=ValidationErrorType.FIELD_NOT_FOUND,
                            field_path=f"computations[{i}].partition_by",
                            message=f"分区维度 '{p_name}' 不在查询维度中",
                            suggestion=f"将 '{p_name}' 添加到维度或从 partition_by 中移除",
                        ))
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            auto_fixed=auto_fixed,
        )

    
    def _build_dimension_field(self, dim: DimensionField, field_metadata: dict[str, dict] | None = None) -> dict:
        """构建 VizQL 维度字段。"""
        field_metadata = field_metadata or {}
        field = {"fieldCaption": dim.field_name}
        
        if dim.alias:
            field["fieldAlias"] = dim.alias
        
        # 处理日期粒度
        if dim.date_granularity:
            meta = field_metadata.get(dim.field_name, {})
            data_type = meta.get("dataType", "").upper()
            
            if data_type == "STRING":
                # STRING 类型 - 使用 DATETRUNC + DATEPARSE
                granularity_str = GRANULARITY_TO_DATETRUNC.get(dim.date_granularity, "month")
                field["calculation"] = f"DATETRUNC('{granularity_str}', DATEPARSE('yyyy-MM-dd', [{dim.field_name}]))"
            else:
                # DATE/DATETIME 类型 - 使用 TRUNC_* 函数
                trunc_func = GRANULARITY_TO_TRUNC.get(dim.date_granularity)
                if trunc_func:
                    field["function"] = trunc_func
        
        return field
    
    def _build_measure_field(self, measure: MeasureField) -> dict:
        """构建 VizQL 度量字段。"""
        field = {"fieldCaption": measure.field_name}
        
        # 仅为非预聚合度量添加函数
        if measure.aggregation is not None:
            vizql_func = AGGREGATION_TO_VIZQL.get(measure.aggregation, "SUM")
            field["function"] = vizql_func
        
        if measure.alias:
            field["fieldAlias"] = measure.alias
        
        return field
    
    def _build_sorts_from_tuples(self, sorts: list[tuple[str, Any]]) -> list[dict]:
        """从 (field_name, SortSpec) 元组构建 VizQL 排序规范。"""
        vizql_sorts = []
        for field_name, sort_spec in sorts:
            vizql_sorts.append({
                "field": {"fieldCaption": field_name},
                "sortDirection": sort_spec.direction.value,
            })
        return vizql_sorts
    
    def _build_computation_fields(
        self,
        computations: list[Computation],
        view_dimensions: list[str],
        measures: list[MeasureField] | None = None,
    ) -> list[dict]:
        """构建计算字段列表（先 LOD，后表计算）。"""
        lod_calc_types = {"LOD_FIXED", "LOD_INCLUDE", "LOD_EXCLUDE"}
        
        # 构建度量聚合查找表
        measure_agg_map: dict[str, AggregationType] = {}
        if measures:
            for m in measures:
                measure_agg_map[m.field_name] = m.aggregation or AggregationType.SUM
        
        lod_fields = []
        table_calc_fields = []
        
        for comp in computations:
            if comp.calc_type in lod_calc_types:
                lod_fields.append(self._build_lod_field(comp))
            else:
                table_calc_fields.append(
                    self._build_table_calc_field(comp, view_dimensions, measure_agg_map)
                )
        
        return lod_fields + table_calc_fields
    
    def _build_table_calc_field(
        self,
        comp: Computation,
        view_dimensions: list[str],
        measure_agg_map: dict[str, AggregationType] | None = None,
    ) -> dict:
        """构建 VizQL 表计算字段。"""
        # 构建分区维度
        partition_dims = []
        for p in comp.partition_by:
            if hasattr(p, 'field_name'):
                dim_ref = {"fieldCaption": p.field_name}
                if hasattr(p, 'date_granularity') and p.date_granularity:
                    trunc_func = GRANULARITY_TO_TRUNC.get(p.date_granularity)
                    if trunc_func:
                        dim_ref["function"] = trunc_func
                partition_dims.append(dim_ref)
            else:
                partition_dims.append({"fieldCaption": p})
        
        # 根据 calc_type 构建表计算规范
        calc_type = comp.calc_type
        
        if calc_type in ("RANK", "DENSE_RANK"):
            table_calc = self._build_rank_spec(comp, partition_dims)
        elif calc_type == "PERCENTILE":
            table_calc = self._build_percentile_spec(comp, partition_dims)
        elif calc_type == "RUNNING_TOTAL":
            table_calc = self._build_running_total_spec(comp, partition_dims)
        elif calc_type == "MOVING_CALC":
            table_calc = self._build_moving_calc_spec(comp, partition_dims)
        elif calc_type == "PERCENT_OF_TOTAL":
            table_calc = self._build_percent_of_total_spec(comp, partition_dims)
        elif calc_type == "DIFFERENCE":
            table_calc = self._build_difference_spec(comp, partition_dims)
        elif calc_type == "PERCENT_DIFFERENCE":
            table_calc = self._build_percent_difference_spec(comp, partition_dims)
        else:
            table_calc = {"tableCalcType": "CUSTOM", "dimensions": partition_dims}
        
        # 获取聚合函数
        agg_type = AggregationType.SUM
        if measure_agg_map and comp.target in measure_agg_map:
            agg_type = measure_agg_map[comp.target]
        
        field = {
            "fieldCaption": comp.target,
            "function": AGGREGATION_TO_VIZQL.get(agg_type, "SUM"),
            "tableCalculation": table_calc,
        }
        
        alias = getattr(comp, 'alias', None)
        if alias:
            field["fieldAlias"] = alias
        
        return field

    
    def _build_rank_spec(self, comp: Computation, partition_dims: list[dict]) -> dict:
        """构建排名表计算规范。"""
        if comp.calc_type == "DENSE_RANK":
            rank_type = "DENSE"
        else:
            rank_style = getattr(comp, 'rank_style', None) or self.DEFAULT_RANK_STYLE
            rank_type = rank_style.value if hasattr(rank_style, 'value') else str(rank_style)
        
        direction = getattr(comp, 'direction', None) or self.DEFAULT_DIRECTION
        
        return {
            "tableCalcType": "RANK",
            "dimensions": partition_dims,
            "rankType": rank_type,
            "direction": direction.value if hasattr(direction, 'value') else str(direction),
        }
    
    def _build_top_n_filter_from_computation(self, comp: Computation, semantic_query: SemanticQuery) -> dict | None:
        """从带有 top_n 的计算构建 Top N 过滤器。"""
        top_n = getattr(comp, 'top_n', None)
        if not top_n:
            return None
        
        filter_dimension = None
        if comp.partition_by:
            first = comp.partition_by[0]
            filter_dimension = first.field_name if hasattr(first, 'field_name') else first
        elif semantic_query.dimensions:
            filter_dimension = semantic_query.dimensions[0].field_name
        
        if not filter_dimension:
            logger.warning(f"无法构建 Top N 过滤器：计算 {comp.target} 没有可用维度")
            return None
        
        direction = getattr(comp, 'direction', None) or self.DEFAULT_DIRECTION
        
        return {
            "field": {"fieldCaption": filter_dimension},
            "filterType": "TOP",
            "howMany": top_n,
            "fieldToMeasure": {"fieldCaption": comp.target},
            "direction": direction.value if hasattr(direction, 'value') else str(direction),
        }
    
    def _build_percentile_spec(self, comp: Computation, partition_dims: list[dict]) -> dict:
        """构建百分位表计算规范。"""
        direction = getattr(comp, 'direction', None) or self.DEFAULT_DIRECTION
        return {
            "tableCalcType": "PERCENTILE",
            "dimensions": partition_dims,
            "direction": direction.value if hasattr(direction, 'value') else str(direction),
        }
    
    def _build_running_total_spec(self, comp: Computation, partition_dims: list[dict]) -> dict:
        """构建累计表计算规范。"""
        aggregation = getattr(comp, 'aggregation', None) or self.DEFAULT_AGGREGATION
        spec = {
            "tableCalcType": "RUNNING_TOTAL",
            "dimensions": partition_dims,
            "aggregation": aggregation.value if hasattr(aggregation, 'value') else str(aggregation),
        }
        restart_every = getattr(comp, 'restart_every', None)
        if restart_every:
            spec["restartEvery"] = {"fieldCaption": restart_every}
        return spec
    
    def _build_moving_calc_spec(self, comp: Computation, partition_dims: list[dict]) -> dict:
        """构建移动计算规范。"""
        aggregation = getattr(comp, 'aggregation', None) or self.DEFAULT_AGGREGATION
        previous = getattr(comp, 'window_previous', self.DEFAULT_WINDOW_PREVIOUS)
        next_val = getattr(comp, 'window_next', self.DEFAULT_WINDOW_NEXT)
        include_current = getattr(comp, 'include_current', self.DEFAULT_INCLUDE_CURRENT)
        
        return {
            "tableCalcType": "MOVING_CALCULATION",
            "dimensions": partition_dims,
            "aggregation": aggregation.value if hasattr(aggregation, 'value') else str(aggregation),
            "previous": previous,
            "next": next_val,
            "includeCurrent": include_current,
        }
    
    def _build_percent_of_total_spec(self, comp: Computation, partition_dims: list[dict]) -> dict:
        """构建占比表计算规范。"""
        spec = {"tableCalcType": "PERCENT_OF_TOTAL", "dimensions": partition_dims}
        level_of = getattr(comp, 'level_of', None)
        if level_of:
            spec["levelAddress"] = {"fieldCaption": level_of}
        return spec
    
    def _build_difference_spec(self, comp: Computation, partition_dims: list[dict]) -> dict:
        """构建差异表计算规范。"""
        relative_to = getattr(comp, 'relative_to', None) or self.DEFAULT_RELATIVE_TO
        return {
            "tableCalcType": "DIFFERENCE_FROM",
            "dimensions": partition_dims,
            "relativeTo": relative_to.value if hasattr(relative_to, 'value') else str(relative_to),
        }
    
    def _build_percent_difference_spec(self, comp: Computation, partition_dims: list[dict]) -> dict:
        """构建百分比差异表计算规范。"""
        relative_to = getattr(comp, 'relative_to', None) or self.DEFAULT_RELATIVE_TO
        return {
            "tableCalcType": "PERCENT_DIFFERENCE_FROM",
            "dimensions": partition_dims,
            "relativeTo": relative_to.value if hasattr(relative_to, 'value') else str(relative_to),
        }
    
    def _build_lod_field(self, comp: Computation) -> dict:
        """构建 VizQL LOD 表达式字段。"""
        lod_type_map = {"LOD_FIXED": "FIXED", "LOD_INCLUDE": "INCLUDE", "LOD_EXCLUDE": "EXCLUDE"}
        lod_type = lod_type_map.get(comp.calc_type, "FIXED")
        
        lod_dims = getattr(comp, 'dimensions', []) or []
        dims_str = ", ".join(f"[{d}]" for d in lod_dims)
        
        aggregation = getattr(comp, 'aggregation', None) or AggregationType.SUM
        agg = aggregation.value if hasattr(aggregation, 'value') else str(aggregation)
        
        if dims_str:
            calculation = f"{{{lod_type} {dims_str} : {agg}([{comp.target}])}}"
        else:
            calculation = f"{{{agg}([{comp.target}])}}"
        
        return {
            "fieldCaption": comp.alias or f"LOD_{comp.target}",
            "calculation": calculation,
        }

    
    def _build_filter(self, f: Any, field_metadata: dict[str, dict] | None = None) -> dict | None:
        """从核心过滤器模型构建 VizQL 过滤器。"""
        field_metadata = field_metadata or {}
        
        if isinstance(f, SetFilter):
            return {
                "field": {"fieldCaption": f.field_name},
                "filterType": "SET",
                "values": f.values,
                "exclude": f.exclude,
            }
        
        elif isinstance(f, DateRangeFilter):
            meta = field_metadata.get(f.field_name, {})
            data_type = meta.get("dataType", "").upper()
            
            if data_type == "STRING":
                field_ref = {"calculation": f"DATEPARSE('yyyy-MM-dd', [{f.field_name}])"}
            else:
                field_ref = {"fieldCaption": f.field_name}
            
            filter_dict = {
                "field": field_ref,
                "filterType": "QUANTITATIVE_DATE",
                "quantitativeFilterType": "RANGE",
            }
            
            if f.start_date:
                filter_dict["minDate"] = f.start_date.isoformat() if hasattr(f.start_date, 'isoformat') else str(f.start_date)
            if f.end_date:
                filter_dict["maxDate"] = f.end_date.isoformat() if hasattr(f.end_date, 'isoformat') else str(f.end_date)
            
            return filter_dict
        
        elif isinstance(f, NumericRangeFilter):
            filter_dict = {
                "field": {"fieldCaption": f.field_name},
                "filterType": "QUANTITATIVE_NUMERICAL",
                "quantitativeFilterType": "RANGE",
            }
            if f.min_value is not None:
                filter_dict["min"] = f.min_value
            if f.max_value is not None:
                filter_dict["max"] = f.max_value
            return filter_dict
        
        elif isinstance(f, TextMatchFilter):
            filter_dict = {
                "field": {"fieldCaption": f.field_name},
                "filterType": "MATCH",
            }
            match_type = f.match_type.value if hasattr(f.match_type, 'value') else str(f.match_type)
            if match_type == "CONTAINS":
                filter_dict["contains"] = f.pattern
            elif match_type == "STARTS_WITH":
                filter_dict["startsWith"] = f.pattern
            elif match_type == "ENDS_WITH":
                filter_dict["endsWith"] = f.pattern
            elif match_type == "EXACT":
                filter_dict["exactMatch"] = f.pattern
            else:
                filter_dict["contains"] = f.pattern
            return filter_dict
        
        elif isinstance(f, TopNFilter):
            return {
                "field": {"fieldCaption": f.field_name},
                "filterType": "TOP",
                "howMany": f.n,
                "fieldToMeasure": {"fieldCaption": f.by_field},
                "direction": f.direction.value,
            }
        
        logger.warning(f"未知过滤器类型: {type(f)}")
        return None
