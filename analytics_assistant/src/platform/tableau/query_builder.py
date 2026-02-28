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
import math
import re
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

    # 日期格式检测模式（按优先级排序：长格式优先，避免短格式误匹配）
    _DATE_FORMAT_DETECTORS: list[tuple[re.Pattern, str]] = [
        (re.compile(r'^\d{4}-\d{2}-\d{2}$'), "yyyy-MM-dd"),      # 2024-01-15
        (re.compile(r'^\d{4}/\d{2}/\d{2}$'), "yyyy/MM/dd"),      # 2024/01/15
        (re.compile(r'^\d{4}\d{2}\d{2}$'),   "yyyyMMdd"),         # 20240115
        (re.compile(r'^\d{4}-\d{2}$'),       "yyyy-MM"),          # 2024-01
        (re.compile(r'^\d{4}/\d{2}$'),       "yyyy/MM"),          # 2024/01
        (re.compile(r'^\d{4}\d{2}$'),        "yyyyMM"),           # 202401
        (re.compile(r'^\d{2}-\d{2}-\d{4}$'), "dd-MM-yyyy"),      # 15-01-2024
        (re.compile(r'^\d{2}/\d{2}/\d{4}$'), "dd/MM/yyyy"),      # 15/01/2024
        (re.compile(r'^\d{4}$'),             "yyyy"),             # 2024
    ]

    @staticmethod
    def _detect_date_format(sample_values: list) -> Optional[str]:
        """从样本值自动推断日期格式。

        遍历非空样本值，用正则匹配检测日期格式。
        要求 >= 2 个样本值匹配同一格式才确认（避免误判）。
        """
        if not sample_values:
            return None

        str_values = [str(v).strip() for v in sample_values if v is not None and str(v).strip()]
        if len(str_values) < 2:
            return None

        for pattern, fmt in TableauQueryBuilder._DATE_FORMAT_DETECTORS:
            match_count = sum(1 for v in str_values if pattern.match(v))
            if match_count >= min(2, len(str_values)):
                return fmt

        return None
    

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

            dim_field = self._build_dimension_field(dim, field_metadata)
            fields.append(dim_field)
        

        # 构建度量字段
        for measure in measures:

            fields.append(self._build_measure_field(measure))
        

        # 构建计算字段（从 DerivedComputation 转换）
        # 收集当前 fields 中已有的 fieldCaption，用于后续检查表计算维度
        existing_captions: set[str] = set()
        # 原始字段名 → 实际 fieldCaption 的映射（用于 STRING 日期字段的 caption 重写）
        dim_name_to_caption: dict[str, str] = {}
        for i, dim in enumerate(dimensions):
            caption = fields[i].get("fieldCaption", dim.field_name)
            existing_captions.add(caption)
            dim_name_to_caption[dim.field_name] = caption
        for i, measure in enumerate(measures):
            caption = fields[len(dimensions) + i].get("fieldCaption", measure.field_name)
            existing_captions.add(caption)

        if semantic_output.computations:

            view_dims = [d.field_name for d in dimensions]

            comp_fields = self._build_derived_computation_fields(

                semantic_output.computations, 

                view_dims,

                measures=measures,

            )

            # 检查表计算的 dimensions 中是否引用了不在查询 fields 中的字段
            # 如果有，自动补充为维度字段（VizQL 要求表计算维度必须在查询中）
            for comp_field in comp_fields:
                tc = comp_field.get("tableCalculation")
                if tc and "dimensions" in tc:
                    for tc_dim in tc["dimensions"]:
                        dim_caption = tc_dim.get("fieldCaption", "")
                        if not dim_caption:
                            continue
                        # 先检查是否有原始字段名到实际 caption 的映射
                        # 例如 dim_caption="dt" 但 fields 中实际是 "dt_month"
                        if dim_caption in dim_name_to_caption:
                            actual_caption = dim_name_to_caption[dim_caption]
                            if actual_caption != dim_caption:
                                tc_dim["fieldCaption"] = actual_caption
                                logger.info(f"表计算维度重写: {dim_caption} → {actual_caption}")
                        elif dim_caption not in existing_captions:
                            # 字段不在当前查询中，需要自动补充
                            meta = field_metadata.get(dim_caption, {})
                            dt = meta.get("dataType", "").upper()
                            if dt == "STRING":
                                # STRING 字段在表计算维度中需要 DATEPARSE
                                samples = meta.get("sample_values", [])
                                date_fmt = self._detect_date_format(samples)
                                if not date_fmt:
                                    # 无法推断格式，直接用原始字段
                                    logger.warning(f"表计算维度 {dim_caption}: 无法推断日期格式，使用原始字段")
                                    fields.append({"fieldCaption": dim_caption})
                                    existing_captions.add(dim_caption)
                                    continue
                                parsed_caption = f"{dim_caption}_parsed"
                                fields.append({
                                    "fieldCaption": parsed_caption,
                                    "calculation": f"DATEPARSE('{date_fmt}', [{dim_caption}])",
                                })
                                # 更新表计算维度引用为 parsed 版本
                                tc_dim["fieldCaption"] = parsed_caption
                                existing_captions.add(parsed_caption)
                                logger.info(f"表计算维度自动补充 DATEPARSE: {dim_caption} → {parsed_caption}")
                            else:
                                fields.append({"fieldCaption": dim_caption})
                                existing_captions.add(dim_caption)
                                logger.info(f"表计算维度自动补充: {dim_caption}")

            fields.extend(comp_fields)
        

        # 构建过滤器（从 SemanticOutput.where.filters）
        # STRING 日期字段的过滤器直接用原始字段名 + MATCH，不需要引用计算字段
        filters_list = semantic_output.where.filters if semantic_output.where and semantic_output.where.filters else []

        filters = []

        if filters_list:
            # VizQL 限制：同一字段不能有多个 RANGE 过滤器
            # 合并同字段的 DateRangeFilter 为一个（取最小 start_date 和最大 end_date）
            merged_date_filters: dict[str, DateRangeFilter] = {}
            other_filters: list[Any] = []
            
            for f in filters_list:
                if isinstance(f, DateRangeFilter):
                    if f.field_name in merged_date_filters:
                        existing = merged_date_filters[f.field_name]
                        # 合并：取最小 start_date 和最大 end_date
                        new_start = min(
                            d for d in [existing.start_date, f.start_date] if d is not None
                        ) if existing.start_date or f.start_date else None
                        new_end = max(
                            d for d in [existing.end_date, f.end_date] if d is not None
                        ) if existing.end_date or f.end_date else None
                        merged_date_filters[f.field_name] = DateRangeFilter(
                            field_name=f.field_name,
                            start_date=new_start,
                            end_date=new_end,
                        )
                        logger.info(
                            f"合并同字段日期过滤器: {f.field_name} "
                            f"→ {new_start} ~ {new_end}"
                        )
                    else:
                        merged_date_filters[f.field_name] = f
                else:
                    other_filters.append(f)
            
            # 先构建合并后的日期过滤器
            for date_filter in merged_date_filters.values():
                vizql_filter = self._build_filter(date_filter, field_metadata)
                if vizql_filter:
                    filters.append(vizql_filter)
            
            # 再构建其他过滤器
            for f in other_filters:
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

        """构建 VizQL 维度字段。
        
        对于 DATE/DATETIME 类型字段，使用 VizQL 原生 TRUNC_* 函数。
        对于 STRING 类型字段且语义解析器给出了 date_granularity，
        使用 calculation 内联 DATEPARSE/DATETRUNC 公式。
        
        判断依据是语义解析器的输出（date_granularity），而非猜测字段名。
        """

        field_metadata = field_metadata or {}

        meta = field_metadata.get(dim.field_name, {})
        data_type = meta.get("dataType", "").upper()
        
        # STRING 日期字段 + 有 date_granularity：语义解析器已判定为日期，用 DATEPARSE
        if data_type == "STRING" and dim.date_granularity:
            samples = meta.get("sample_values", [])
            date_fmt = self._detect_date_format(samples)
            if not date_fmt:
                # 无法推断格式，降级为不做 DATEPARSE，直接用原始字段
                logger.warning(f"无法推断 {dim.field_name} 的日期格式，使用原始字段")
                field = {"fieldCaption": dim.field_name}
            else:
                trunc_part = GRANULARITY_TO_DATETRUNC.get(dim.date_granularity, "month")
                caption = f"{dim.field_name}_{trunc_part}"
                field = {
                    "fieldCaption": caption,
                    "calculation": f"DATETRUNC('{trunc_part}', DATEPARSE('{date_fmt}', [{dim.field_name}]))",
                }
                logger.info(f"STRING 日期字段 {dim.field_name}: 使用 calculation, caption={caption}, fmt={date_fmt}")
        else:
            field = {"fieldCaption": dim.field_name}
            # DATE/DATETIME 类型使用原生 TRUNC 函数
            if dim.date_granularity and data_type not in ("STRING", ""):
                trunc_func = GRANULARITY_TO_TRUNC.get(dim.date_granularity)
                if trunc_func:
                    field["function"] = trunc_func
        
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

        """从 DerivedComputation 构建公式计算字段。
        
        LLM 生成的公式可能不包含聚合函数（如 `[netamt] - [sale_cost]`），
        但 VizQL calculation 字段要求度量引用必须包含聚合函数。
        自动将 `[field_name]` 替换为 `SUM([field_name])`（对 base_measures 中的字段）。
        """
        if not comp.formula:

            logger.warning(f"计算 {comp.name} 缺少 formula")

            return None
        
        formula = comp.formula
        
        # 对 base_measures 中的字段，自动添加 SUM 聚合
        # LLM 可能生成两种格式：带方括号 SUM([field]) 或不带 SUM(field)
        for measure_name in comp.base_measures:
            # 检查公式中是否已经有聚合函数包裹该字段
            # 同时匹配 SUM([field_name]) 和 SUM(field_name) 两种格式
            agg_pattern = re.compile(
                r'(SUM|AVG|COUNT|COUNTD|MIN|MAX|MEDIAN)\s*\(\s*\[?' + re.escape(measure_name) + r'\]?\s*\)',
                re.IGNORECASE,
            )
            if agg_pattern.search(formula):
                # 已有聚合 — 只需确保字段名带方括号（VizQL 要求）
                # 将 SUM(field_name) 规范化为 SUM([field_name])
                bare_agg_pattern = re.compile(
                    r'((?:SUM|AVG|COUNT|COUNTD|MIN|MAX|MEDIAN)\s*\(\s*)' + re.escape(measure_name) + r'(\s*\))',
                    re.IGNORECASE,
                )
                formula = bare_agg_pattern.sub(r'\1[' + measure_name + r']\2', formula)
                continue
            
            # 无聚合函数 — 添加 SUM 包裹
            # 先处理带方括号的 [field_name]
            bracket_pattern = re.compile(r'\[' + re.escape(measure_name) + r'\]')
            if bracket_pattern.search(formula):
                formula = bracket_pattern.sub(f'SUM([{measure_name}])', formula)
            else:
                # 裸字段名引用（无方括号）
                bare_pattern = re.compile(r'\b' + re.escape(measure_name) + r'\b')
                formula = bare_pattern.sub(f'SUM([{measure_name}])', formula)
        
        if formula != comp.formula:
            logger.info(f"公式自动聚合: {comp.formula} → {formula}")

        return {

            "fieldCaption": comp.display_name,

            "calculation": formula,

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
        """从核心过滤器模型构建 VizQL 过滤器。
        
        日期过滤策略（按字段 dataType 分路径）：
        - DATE/DATETIME → fieldCaption + QUANTITATIVE_DATE（原生日期范围）
        - STRING → calculation(DATEPARSE) + QUANTITATIVE_DATE（精确范围）
        - dataType 为空 → 语义解析器已给出 DateRangeFilter，走 DATEPARSE 路径
        
        VizQL API 限制：
        - RANGE 过滤器必须同时有 minDate 和 maxDate
        - filter.field 中 CalculatedFilterField 只接受 calculation，不能有 fieldCaption
        
        Args:
            f: 过滤器模型
            field_metadata: 字段元数据映射
        """
        field_metadata = field_metadata or {}

        if isinstance(f, SetFilter):
            # 防御：空值列表的 SetFilter 无意义，跳过
            if not f.values:
                logger.warning(f"SetFilter {f.field_name}: values 为空，跳过")
                return None
            return {
                "field": {"fieldCaption": f.field_name},
                "filterType": "SET",
                "values": f.values,
                "exclude": f.exclude,
            }

        elif isinstance(f, DateRangeFilter):
            return self._build_date_range_filter(f, field_metadata)

        elif isinstance(f, NumericRangeFilter):
            # 防御：min/max 都为 None 时跳过（VizQL RANGE 要求至少有一个边界）
            if f.min_value is None and f.max_value is None:
                logger.warning(f"NumericRangeFilter {f.field_name}: min/max 均为空，跳过")
                return None
            filter_dict = {
                "field": {"fieldCaption": f.field_name},
                "filterType": "QUANTITATIVE_NUMERICAL",
                "quantitativeFilterType": "RANGE",
            }
            # 处理 -inf/inf：JSON 不支持，替换为极大/极小值
            if f.min_value is not None:
                if math.isinf(f.min_value) or math.isnan(f.min_value):
                    logger.warning(f"NumericRangeFilter {f.field_name}: min_value={f.min_value}，替换为 -1e15")
                    filter_dict["min"] = -1e15
                else:
                    filter_dict["min"] = f.min_value
            if f.max_value is not None:
                if math.isinf(f.max_value) or math.isnan(f.max_value):
                    logger.warning(f"NumericRangeFilter {f.field_name}: max_value={f.max_value}，替换为 1e15")
                    filter_dict["max"] = 1e15
                else:
                    filter_dict["max"] = f.max_value
            # VizQL RANGE 要求同时有 min 和 max
            if "min" not in filter_dict:
                filter_dict["min"] = -1e15
                logger.info(f"NumericRangeFilter {f.field_name}: 补全 min=-1e15")
            if "max" not in filter_dict:
                filter_dict["max"] = 1e15
                logger.info(f"NumericRangeFilter {f.field_name}: 补全 max=1e15")
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
            # VizQL TOP 过滤器的 direction 枚举值是 TOP/BOTTOM，不是 DESC/ASC
            vizql_direction = "TOP" if f.direction == SortDirection.DESC else "BOTTOM"
            return {
                "field": {"fieldCaption": f.field_name},
                "filterType": "TOP",
                "howMany": f.n,
                "fieldToMeasure": {"fieldCaption": f.by_field},
                "direction": vizql_direction,
            }

        logger.warning(f"未知过滤器类型: {type(f)}")
        return None

    def _build_date_range_filter(
        self, f: DateRangeFilter, field_metadata: dict[str, dict]
    ) -> Optional[dict]:
        """构建日期范围过滤器。

        统一使用 DATEPARSE + QUANTITATIVE_DATE 策略：
        - DATE/DATETIME → fieldCaption + QUANTITATIVE_DATE（原生日期范围）
        - STRING → 从 sample_values 推断格式 → DATEPARSE calculation + QUANTITATIVE_DATE
        - 无法推断格式 → 降级为 MATCH startsWith

        VizQL RANGE 过滤器要求 minDate 和 maxDate 同时存在，
        缺少时补全为合理的默认值。
        """
        meta = field_metadata.get(f.field_name, {})
        data_type = meta.get("dataType", "").upper()

        if data_type in ("DATE", "DATETIME", "TIMESTAMP"):
            field_ref = {"fieldCaption": f.field_name}
            logger.info(
                f"日期过滤: {f.field_name} (dataType={data_type}) "
                f"→ fieldCaption + QUANTITATIVE_DATE"
            )
        elif data_type == "STRING" or not data_type:
            samples = meta.get("sample_values", [])
            date_fmt = self._detect_date_format(samples)
            if not date_fmt:
                logger.warning(
                    f"日期过滤: {f.field_name} 无法推断日期格式，降级为 MATCH"
                )
                return self._build_date_match_fallback(f)
            field_ref = {
                "calculation": f"DATEPARSE('{date_fmt}', [{f.field_name}])",
            }
            logger.info(
                f"日期过滤: {f.field_name} (dataType={data_type}, fmt={date_fmt}) "
                f"→ DATEPARSE calculation + QUANTITATIVE_DATE"
            )
        else:
            field_ref = {"fieldCaption": f.field_name}

        # 构建 minDate / maxDate
        min_date = self._format_date(f.start_date)
        max_date = self._format_date(f.end_date)

        # VizQL RANGE 过滤器要求 minDate 和 maxDate 同时存在
        if min_date and not max_date:
            max_date = "2099-12-31"
            logger.info(f"日期过滤: 补全 maxDate={max_date}（原始 end_date 为空）")
        elif max_date and not min_date:
            min_date = "1900-01-01"
            logger.info(f"日期过滤: 补全 minDate={min_date}（原始 start_date 为空）")
        elif not min_date and not max_date:
            logger.warning(f"日期过滤: {f.field_name} 无日期范围，跳过过滤")
            return None

        return {
            "field": field_ref,
            "filterType": "QUANTITATIVE_DATE",
            "quantitativeFilterType": "RANGE",
            "minDate": min_date,
            "maxDate": max_date,
        }

    def _build_date_match_fallback(self, f: DateRangeFilter) -> Optional[dict]:
        """无法推断日期格式时，用 MATCH startsWith 做降级过滤。"""
        prefix = None
        if f.start_date:
            prefix = f.start_date.strftime("%Y")
        if not prefix:
            return None
        return {
            "field": {"fieldCaption": f.field_name},
            "filterType": "MATCH",
            "startsWith": prefix,
        }

    @staticmethod
    def _format_date(d: Any) -> Optional[str]:
        """将日期对象格式化为 ISO 字符串。"""
        if d is None:
            return None
        if hasattr(d, 'isoformat'):
            return d.isoformat()
        return str(d)

