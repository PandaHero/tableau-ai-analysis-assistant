# -*- coding: utf-8 -*-

"""Tableau 查询构建器 - 将 SemanticOutput 转换为 VizQL API 请求。

这是从语义解析器输出（SemanticOutput）到 Tableau 特定 VizQL API 格式的核心转换层。

关键转换：

- SemanticOutput.what.measures → VizQL 度量字段

- SemanticOutput.where.dimensions → VizQL 维度字段

- SemanticOutput.where.filters → VizQL 过滤器

- SemanticOutput.computations (DerivedComputation) → VizQL 计算字段/表计算
"""

import logging

from typing import Any, Optional

from analytics_assistant.src.core.interfaces import BaseQueryBuilder

from analytics_assistant.src.core.schemas import (

    AggregationType,

    DateGranularity,

    DateRangeFilter,

    DimensionField,

    MeasureField,

    NumericRangeFilter,

    RankStyle,

    RelativeTo,

    SetFilter,

    SortDirection,

    TextMatchFilter,

    TopNFilter,

    ValidationErrorDetail,

    ValidationErrorType,

    ValidationResult,

)

from analytics_assistant.src.core.schemas.semantic_output import (

    SemanticOutput,

    DerivedComputation,

    CalcType,

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

    """Tableau 查询构建器 - 将 SemanticOutput 转换为 VizQL 请求。
    

    输入：SemanticOutput（语义解析器输出）

    输出：VizQL API 请求字典
    

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
    

    def build(self, semantic_output: SemanticOutput, **kwargs: Any) -> dict:

        """从 SemanticOutput 构建 VizQL API 请求。
        

        Args:

            semantic_output: 语义解析器的输出

            **kwargs: 额外参数：

                - field_metadata: dict[str, dict] 字段名到元数据的映射
            

        Returns:

            VizQL API 请求字典
        """

        field_metadata = kwargs.get("field_metadata", {})

        fields = []
        

        # 从 SemanticOutput.where 获取维度

        dimensions = semantic_output.where.dimensions if semantic_output.where else []

        measures = semantic_output.what.measures if semantic_output.what else []
        

        # 构建维度字段
        for dim in dimensions:

            fields.append(self._build_dimension_field(dim, field_metadata))
        

        # 构建度量字段
        for measure in measures:

            fields.append(self._build_measure_field(measure))
        

        # 构建计算字段（从 DerivedComputation 转换）
        if semantic_output.computations:

            view_dims = [d.field_name for d in dimensions]

            comp_fields = self._build_derived_computation_fields(

                semantic_output.computations, 

                view_dims,

                measures=measures,

            )

            fields.extend(comp_fields)
        

        # 构建过滤器（从 SemanticOutput.where.filters）

        filters = []

        if semantic_output.where and semantic_output.where.filters:

            for f in semantic_output.where.filters:

                vizql_filter = self._build_filter(f, field_metadata)

                if vizql_filter:

                    filters.append(vizql_filter)
        

        # 构建请求

        request = {"fields": fields}
        
        if filters:

            request["filters"] = filters
        

        # 从维度和度量收集排序

        sorts = self._collect_sorts(dimensions, measures)
        if sorts:

            request["sorts"] = sorts
        

        return request
    

    def validate(self, semantic_output: SemanticOutput, **kwargs: Any) -> ValidationResult:

        """验证 SemanticOutput 是否适用于 Tableau 平台。"""

        errors = []

        warnings = []

        auto_fixed = []
        

        # 获取维度和度量

        dimensions = semantic_output.where.dimensions if semantic_output.where else []

        measures = semantic_output.what.measures if semantic_output.what else []
        

        # 检查空查询
        if not dimensions and not measures:

            errors.append(ValidationErrorDetail(

                error_type=ValidationErrorType.MISSING_REQUIRED,

                field_path="what/where",

                message="查询必须至少有一个维度或度量",

            ))
        

        # 验证计算
        if semantic_output.computations:

            view_dims = set(d.field_name for d in dimensions)

            measure_names = set(m.field_name for m in measures)
            

            for i, comp in enumerate(semantic_output.computations):

                # 检查基础度量是否存在

                for base_measure in comp.base_measures:

                    if base_measure not in measure_names:

                        # 基础度量可能是数据源中的字段，不一定在当前查询的度量中

                        # 这里只记录警告，不作为错误
                        pass
                

                # 检查子查询维度是否有效（如果有）

                if comp.subquery_dimensions:

                    for dim in comp.subquery_dimensions:

                        if dim not in view_dims:

                            # 子查询维度可以是数据源中的任意维度
                            pass
        

        return ValidationResult(

            is_valid=len(errors) == 0,

            errors=errors,

            warnings=warnings,

            auto_fixed=auto_fixed,

        )
    

    def _collect_sorts(

        self, 

        dimensions: list[DimensionField], 

        measures: list[MeasureField]

    ) -> list[dict]:

        """从维度和度量收集排序规范。"""

        sorts = []
        

        # 收集维度排序
        for dim in dimensions:
            if dim.sort:

                sorts.append((dim.field_name, dim.sort))
        

        # 收集度量排序
        for measure in measures:
            if measure.sort:

                sorts.append((measure.field_name, measure.sort))
        

        # 按 priority 排序

        sorts.sort(key=lambda x: x[1].priority)
        

        # 转换为 VizQL 格式

        vizql_sorts = []

        for field_name, sort_spec in sorts:

            vizql_sorts.append({

                "field": {"fieldCaption": field_name},

                "sortDirection": sort_spec.direction.value,

            })

        return vizql_sorts

    

    def _build_dimension_field(self, dim: DimensionField, field_metadata: Optional[dict[str, dict]] = None) -> dict:

        """构建 VizQL 维度字段。"""

        field_metadata = field_metadata or {}

        # 获取字段元数据
        meta = field_metadata.get(dim.field_name, {})
        data_type = meta.get("dataType", "").upper()
        
        # 检查是否是 STRING 类型的日期字段
        is_string_date = data_type == "STRING" and self._is_date_field(dim.field_name, meta)
        
        # 处理日期粒度
        if dim.date_granularity:
            if data_type == "STRING":
                # STRING 类型 - 使用 DATETRUNC + DATEPARSE
                granularity_str = GRANULARITY_TO_DATETRUNC.get(dim.date_granularity, "month")
                field = {
                    "fieldCaption": dim.field_name,
                    "calculation": f"DATETRUNC('{granularity_str}', DATEPARSE('yyyy-MM-dd', [{dim.field_name}]))"
                }
            else:
                # DATE/DATETIME 类型 - 使用 TRUNC_* 函数
                field = {"fieldCaption": dim.field_name}
                trunc_func = GRANULARITY_TO_TRUNC.get(dim.date_granularity)
                if trunc_func:
                    field["function"] = trunc_func
        elif is_string_date:
            # STRING 类型的日期字段,即使没有粒度也要转换
            field = {
                "fieldCaption": dim.field_name,
                "calculation": f"DATEPARSE('yyyy-MM-dd', [{dim.field_name}])"
            }
        else:
            # 普通维度字段
            field = {"fieldCaption": dim.field_name}
        
        if dim.alias:
            field["fieldAlias"] = dim.alias
        
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
    
    def _is_date_field(self, field_name: str, metadata: dict) -> bool:
        """判断字段是否是日期字段。
        
        根据字段名和元数据判断是否是日期字段。
        
        Args:
            field_name: 字段名
            metadata: 字段元数据
            
        Returns:
            是否是日期字段
        """
        # 检查数据类型
        data_type = metadata.get("dataType", "").lower()
        if data_type in {"date", "datetime", "timestamp"}:
            return True
        
        # 检查字段名中的关键词
        time_keywords = {
            "date", "time", "year", "month", "day", "week", "quarter",
            "日期", "时间", "年", "月", "日", "周", "季度",
            "dt", "yyyymm", "yyyymmdd", "yyyy", "mm", "dd"
        }
        field_name_lower = field_name.lower()
        if any(kw in field_name_lower for kw in time_keywords):
            return True
        
        # 检查 caption 中的关键词
        caption = metadata.get("caption", "").lower()
        if caption and any(kw in caption for kw in time_keywords):
            return True
        
        return False
    

    def _build_derived_computation_fields(

        self,

        computations: list[DerivedComputation],

        view_dimensions: list[str],

        measures: Optional[list[MeasureField]] = None,

    ) -> list[dict]:

        """从 DerivedComputation 构建 VizQL 计算字段。
        

        DerivedComputation 是语义解析器的输出格式，需要转换为 VizQL 格式。
        

        转换规则：

        - RATIO/SUM/DIFFERENCE/PRODUCT/FORMULA → 计算字段（使用 formula）

        - SUBQUERY → LOD 表达式

        - TABLE_CALC_* → 表计算
        """

        fields = []
        

        # 构建度量聚合查找表

        measure_agg_map: dict[str, AggregationType] = {}
        if measures:
            for m in measures:

                measure_agg_map[m.field_name] = m.aggregation or AggregationType.SUM
        
        for comp in computations:

            calc_type = comp.calc_type
            

            # 简单计算（公式）

            if calc_type in (CalcType.RATIO, CalcType.SUM, CalcType.DIFFERENCE, 

                            CalcType.PRODUCT, CalcType.FORMULA):

                field = self._build_formula_field(comp)
                if field:

                    fields.append(field)
            

            # 子查询 → LOD 表达式

            elif calc_type == CalcType.SUBQUERY:

                field = self._build_lod_from_derived(comp)
                if field:

                    fields.append(field)
            

            # 表计算

            elif calc_type.value.startswith("TABLE_CALC_"):

                field = self._build_table_calc_from_derived(comp, view_dimensions, measure_agg_map)
                if field:

                    fields.append(field)
        
        return fields
    

    def _build_formula_field(self, comp: DerivedComputation) -> Optional[dict]:

        """从 DerivedComputation 构建公式计算字段。"""
        if not comp.formula:

            logger.warning(f"计算 {comp.name} 缺少 formula")

            return None
        

        return {

            "fieldCaption": comp.display_name,

            "calculation": comp.formula,

        }
    

    def _build_lod_from_derived(self, comp: DerivedComputation) -> Optional[dict]:

        """从 DerivedComputation (SUBQUERY) 构建 LOD 表达式。
        

        SUBQUERY 类型转换为 Tableau LOD 表达式。

        LOD 类型由 subquery_dimensions 与视图维度的关系决定：

        - 独立于视图维度 → FIXED

        - 视图维度的超集 → INCLUDE

        - 视图维度的子集 → EXCLUDE
        

        由于在构建时不知道完整的视图上下文，默认使用 FIXED。
        """

        if not comp.subquery_dimensions:

            logger.warning(f"SUBQUERY 计算 {comp.name} 缺少 subquery_dimensions")

            return None
        

        # 默认使用 FIXED LOD

        dims_str = ", ".join(f"[{d}]" for d in comp.subquery_dimensions)

        agg = comp.subquery_aggregation or "SUM"
        

        # 获取目标度量（从 base_measures 中取第一个）

        target = comp.base_measures[0] if comp.base_measures else comp.name
        

        calculation = f"{{FIXED {dims_str} : {agg}([{target}])}}"
        

        return {

            "fieldCaption": comp.display_name,

            "calculation": calculation,

        }
    

    def _build_table_calc_from_derived(
        self,
        comp: DerivedComputation,
        view_dimensions: list[str],
        measure_agg_map: Optional[dict[str, AggregationType]] = None,
    ) -> Optional[dict]:
        """从 DerivedComputation (TABLE_CALC_*) 构建表计算字段。

        使用 Tableau Cloud 原生 TableCalcField 格式（基于 OpenAPI 规范）。
        表计算字段必须引用一个已存在的度量字段（通过 fieldCaption）。
        """
        calc_type = comp.calc_type

        # 获取目标度量
        target = comp.base_measures[0] if comp.base_measures else None
        if not target:
            logger.warning(f"表计算 {comp.name} 缺少 base_measures")
            return None

        # 获取聚合函数字符串
        agg_type = AggregationType.SUM
        if measure_agg_map and target in measure_agg_map:
            agg_type = measure_agg_map[target]
        agg_func = AGGREGATION_TO_VIZQL.get(agg_type, "SUM")

        # 构建 dimensions 数组（表计算的计算维度）
        # 使用 partition_by 或 view_dimensions
        calc_dimensions = []
        if comp.partition_by:
            calc_dimensions = [{"fieldCaption": dim} for dim in comp.partition_by]
        elif view_dimensions:
            calc_dimensions = [{"fieldCaption": dim} for dim in view_dimensions]

        # 根据 calc_type 构建表计算配置
        table_calc: dict[str, Any] = {
            "dimensions": calc_dimensions,
        }

        if calc_type == CalcType.TABLE_CALC_RANK:
            table_calc["tableCalcType"] = "RANK"
            table_calc["rankType"] = self.DEFAULT_RANK_STYLE.value
            table_calc["direction"] = self.DEFAULT_DIRECTION.value

        elif calc_type == CalcType.TABLE_CALC_PERCENTILE:
            table_calc["tableCalcType"] = "PERCENTILE"
            table_calc["direction"] = self.DEFAULT_DIRECTION.value

        elif calc_type == CalcType.TABLE_CALC_DIFFERENCE:
            table_calc["tableCalcType"] = "DIFFERENCE_FROM"
            table_calc["relativeTo"] = (comp.relative_to or "PREVIOUS").upper()

        elif calc_type == CalcType.TABLE_CALC_PERCENT_DIFF:
            table_calc["tableCalcType"] = "PERCENT_DIFFERENCE_FROM"
            table_calc["relativeTo"] = (comp.relative_to or "PREVIOUS").upper()

        elif calc_type == CalcType.TABLE_CALC_PERCENT_OF_TOTAL:
            table_calc["tableCalcType"] = "PERCENT_OF_TOTAL"

        elif calc_type == CalcType.TABLE_CALC_RUNNING:
            table_calc["tableCalcType"] = "RUNNING_TOTAL"
            table_calc["aggregation"] = agg_func

        elif calc_type == CalcType.TABLE_CALC_MOVING:
            table_calc["tableCalcType"] = "MOVING_CALCULATION"
            table_calc["aggregation"] = "AVG"
            table_calc["previous"] = self.DEFAULT_WINDOW_PREVIOUS
            table_calc["next"] = self.DEFAULT_WINDOW_NEXT
            table_calc["includeCurrent"] = self.DEFAULT_INCLUDE_CURRENT

        else:
            logger.warning(f"未知的表计算类型: {calc_type}")
            return None

        # 表计算字段引用基础度量字段
        # fieldCaption 是基础度量字段名，fieldAlias 是显示名称
        return {
            "fieldCaption": target,
            "function": agg_func,
            "fieldAlias": comp.display_name,
            "tableCalculation": table_calc,
        }



    def _build_filter(self, f: Any, field_metadata: Optional[dict[str, dict]] = None) -> Optional[dict]:

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
            
            logger.debug(f"DateRangeFilter: field_name={f.field_name}, meta={meta}, data_type={data_type}")
            

            if data_type == "STRING":

                field_ref = {"calculation": f"DATEPARSE('yyyy-MM-dd', [{f.field_name}])"}
                logger.info(f"使用 DATEPARSE 处理 STRING 日期字段: {f.field_name}")
            else:

                field_ref = {"fieldCaption": f.field_name}
                logger.info(f"使用 fieldCaption 处理日期字段: {f.field_name} (data_type={data_type})")
            

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

