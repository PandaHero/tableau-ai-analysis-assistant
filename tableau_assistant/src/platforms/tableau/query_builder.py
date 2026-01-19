"""Tableau 查询构建器 - 将 SemanticQuery 转换为 VizQL API 请求。

这是从平台无关的 SemanticQuery 到 Tableau 特定 VizQL API 格式的核心转换层。

关键转换：
- Computation.partition_by → 表计算维度（分区）
- Computation 子类型（RankCalc 等）→ TableCalcType
- CalcParams → VizQL 特定参数
- Filter 类型 → VizQL 过滤器类型
"""

import logging
from typing import Any

from tableau_assistant.src.core.interfaces import BaseQueryBuilder
from tableau_assistant.src.core.models import (

    AggregationType,
    Computation,
    DateRangeFilter,
    DimensionField,
    FilterType,
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
    DateGranularity,
    WindowAggregation,
)
from tableau_assistant.src.platforms.tableau.models import (
    LODExpression,
    LODType,
    VizQLFunction,
    VizQLSortDirection,
    determine_lod_type,
)


logger = logging.getLogger(__name__)


# 核心 AggregationType 到 VizQL Function 的映射
AGGREGATION_TO_VIZQL: dict[AggregationType, VizQLFunction] = {
    AggregationType.SUM: VizQLFunction.SUM,
    AggregationType.AVG: VizQLFunction.AVG,
    AggregationType.COUNT: VizQLFunction.COUNT,
    AggregationType.COUNTD: VizQLFunction.COUNTD,
    AggregationType.MIN: VizQLFunction.MIN,
    AggregationType.MAX: VizQLFunction.MAX,
    AggregationType.MEDIAN: VizQLFunction.MEDIAN,
    AggregationType.STDEV: VizQLFunction.STDEV,
    AggregationType.VAR: VizQLFunction.VAR,
}


class TableauQueryBuilder(BaseQueryBuilder):
    """Tableau 查询构建器 - 将 SemanticQuery 转换为 VizQL 请求。
    
    Tableau 特定的默认值在这里定义，而不是在 CalcParams 中。
    这使 CalcParams 保持平台无关性。
    """
    
    # Tableau 特定的默认值
    DEFAULT_RANK_STYLE = RankStyle.COMPETITION
    DEFAULT_DIRECTION = SortDirection.DESC
    DEFAULT_RELATIVE_TO = RelativeTo.PREVIOUS
    DEFAULT_AGGREGATION = WindowAggregation.SUM
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
                  （用于确定日期处理的字段 dataType）
            
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
        
        # 构建计算字段（表计算或 LOD）
        # 重要：LOD 字段必须在表计算字段之前
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
        
        # 从带有 top_n 参数的计算中构建 Top N 过滤器
        if semantic_query.computations:
            for comp in semantic_query.computations:
                # 检查带有 top_n 属性的 RANK 或 DENSE_RANK
                if comp.calc_type in ("RANK", "DENSE_RANK") and getattr(comp, 'top_n', None):
                    top_n_filter = self._build_top_n_filter_from_computation(comp, semantic_query)
                    if top_n_filter:
                        filters.append(top_n_filter)
        
        # 构建请求
        request = {
            "fields": fields,
        }
        
        if filters:
            request["filters"] = filters
        
        # 构建排序 - 排序嵌入在字段的 sort 属性中，使用 get_sorts() 获取
        sorts_list = semantic_query.get_sorts()
        if sorts_list:
            sorts = self._build_sorts_from_tuples(sorts_list)
            if sorts:
                request["sorts"] = sorts
        
        if semantic_query.row_limit:
            request["rowLimit"] = semantic_query.row_limit
        
        # 注意：datasource 不在这里添加 - 它由 API 层处理
        # VizQLClient.query_datasource() 会将查询包装在：
        # {"datasource": {"datasourceLuid": ...}, "query": <此请求>}
        
        return request
    
    def validate(self, semantic_query: SemanticQuery, **kwargs: Any) -> ValidationResult:
        """验证 SemanticQuery 是否适用于 Tableau 平台。"""
        errors = []
        warnings = []
        auto_fixed = []
        
        # LOD calc_type 值（字符串形式）
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
                # 检查目标是否在度量中（非 LOD）或有效字段
                if comp.calc_type not in lod_calc_types and comp.target not in measures:
                    errors.append(ValidationError(
                        error_type=ValidationErrorType.FIELD_NOT_FOUND,
                        field_path=f"computations[{i}].target",
                        message=f"目标 '{comp.target}' 不在度量中",
                        suggestion=f"将 '{comp.target}' 添加到度量或使用现有度量",
                    ))
                
                # 检查 partition_by 是否是维度的子集
                # partition_by 现在是 list[DimensionField]，从每个中提取 field_name
                for p in comp.partition_by:
                    p_field_name = p.field_name if hasattr(p, 'field_name') else p
                    if p_field_name not in view_dims:
                        errors.append(ValidationError(
                            error_type=ValidationErrorType.FIELD_NOT_FOUND,
                            field_path=f"computations[{i}].partition_by",
                            message=f"分区维度 '{p_field_name}' 不在查询维度中",
                            suggestion=f"将 '{p_field_name}' 添加到维度或从 partition_by 中移除",
                        ))
        
        # 自动修复：为没有聚合的度量填充默认聚合
        # 注意：aggregation=None 对于预聚合的计算字段是有效的
        # 我们只在字段没有显式设置为 None 时自动修复
        # （这由 LLM 处理，它为预聚合字段设置 None）
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            auto_fixed=auto_fixed,
        )
    
    def _build_dimension_field(self, dim: DimensionField, field_metadata: dict[str, dict] | None = None) -> dict:
        """构建 VizQL 维度字段。
        
        对于带有粒度的日期字段：
        - DATE/DATETIME 类型：使用 function: "TRUNC_MONTH" 等
        - STRING 类型：使用 calculation: "DATETRUNC('month', DATEPARSE('yyyy-MM-dd', [Field]))"
        """
        field_metadata = field_metadata or {}
        field = {
            "fieldCaption": dim.field_name,
        }
        
        if dim.alias:
            field["fieldAlias"] = dim.alias
        
        # 处理日期粒度
        if dim.date_granularity:
            meta = field_metadata.get(dim.field_name, {})
            data_type = meta.get("dataType", "").upper()
            
            # 粒度到 TRUNC 函数名的映射
            trunc_map = {
                DateGranularity.YEAR: "TRUNC_YEAR",
                DateGranularity.QUARTER: "TRUNC_QUARTER",
                DateGranularity.MONTH: "TRUNC_MONTH",
                DateGranularity.WEEK: "TRUNC_WEEK",
                DateGranularity.DAY: "TRUNC_DAY",
            }
            
            # 粒度到 DATETRUNC 参数的映射
            datetrunc_map = {
                DateGranularity.YEAR: "year",
                DateGranularity.QUARTER: "quarter",
                DateGranularity.MONTH: "month",
                DateGranularity.WEEK: "week",
                DateGranularity.DAY: "day",
            }
            
            if data_type == "STRING":
                # STRING 类型日期字段 - 使用 DATETRUNC + DATEPARSE 计算
                granularity_str = datetrunc_map.get(dim.date_granularity, "month")
                field["calculation"] = f"DATETRUNC('{granularity_str}', DATEPARSE('yyyy-MM-dd', [{dim.field_name}]))"
            else:
                # DATE/DATETIME 类型 - 使用 TRUNC_* 函数
                trunc_func = trunc_map.get(dim.date_granularity)
                if trunc_func:
                    field["function"] = trunc_func
        
        return field
    
    def _build_measure_field(self, measure: MeasureField) -> dict:
        """构建 VizQL 度量字段。
        
        对于预聚合度量（aggregation=None），不添加函数。
        这用于已包含聚合的计算字段。
        """
        field = {
            "fieldCaption": measure.field_name,
        }
        
        # 仅为非预聚合度量添加函数
        if measure.aggregation is not None:
            vizql_func = AGGREGATION_TO_VIZQL.get(measure.aggregation, VizQLFunction.SUM)
            field["function"] = vizql_func.value
        
        if measure.alias:
            field["fieldAlias"] = measure.alias
        
        return field
    
    def _build_sorts(self, sorts: list[Sort]) -> list[dict]:
        """构建 VizQL 排序规范。
        
        Args:
            sorts: SemanticQuery 中的 Sort 对象列表
            
        Returns:
            VizQL 排序字典列表
        """
        vizql_sorts = []
        
        # 按优先级排序（数值越小优先级越高）
        sorted_sorts = sorted(sorts, key=lambda s: s.priority)
        
        for sort in sorted_sorts:
            vizql_sort = {
                "field": {"fieldCaption": sort.field_name},
                "sortDirection": sort.direction.value,
            }
            vizql_sorts.append(vizql_sort)
        
        return vizql_sorts
    
    def _build_sorts_from_tuples(self, sorts: list[tuple[str, "SortSpec"]]) -> list[dict]:
        """从 (field_name, SortSpec) 元组构建 VizQL 排序规范。
        
        Args:
            sorts: (field_name, SortSpec) 元组列表，已按优先级排序
            
        Returns:
            VizQL 排序字典列表
        """
        vizql_sorts = []
        
        for field_name, sort_spec in sorts:
            vizql_sort = {
                "field": {"fieldCaption": field_name},
                "sortDirection": sort_spec.direction.value,
            }
            vizql_sorts.append(vizql_sort)
        
        return vizql_sorts
    
    def _build_computation_fields(
        self,
        computations: list[Computation],
        view_dimensions: list[str],
        measures: list[MeasureField] | None = None,
    ) -> list[dict]:
        """构建计算字段列表（先 LOD，后表计算）。
        
        重要：LOD 字段必须在表计算字段之前生成，
        因为表计算可能引用 LOD 结果。
        
        Args:
            computations: 计算对象列表
            view_dimensions: 查询中的维度字段名列表
            measures: 度量字段列表（用于表计算聚合查找）
        """
        # LOD calc_type 值（字符串形式，不是 CalcType 枚举）
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
        
        # 先 LOD，后表计算
        return lod_fields + table_calc_fields
    
    def _build_table_calc_field(
        self,
        comp: Computation,
        view_dimensions: list[str],
        measure_agg_map: dict[str, AggregationType] | None = None,
    ) -> dict:
        """构建 VizQL 表计算字段。
        
        注意：Computation 是一个 Union 类型，有不同的子类型。
        每个子类型的属性直接在对象上（不是通过 params）。
        
        VizQL API 要求表计算字段同时具有：
        - function: 聚合函数（SUM、AVG 等）
        - tableCalculation: 表计算规范
        
        Args:
            comp: Computation 对象
            view_dimensions: 查询中的维度字段名列表
            measure_agg_map: 度量字段名到其聚合类型的映射
        """
        # 构建分区维度
        # partition_by 现在是 list[DimensionField]，需要处理 date_granularity
        partition_dims = []
        for p in comp.partition_by:
            if hasattr(p, 'field_name'):
                # 它是 DimensionField 对象
                dim_ref = {"fieldCaption": p.field_name}
                # 如果有 date_granularity，添加 function 以匹配查询字段
                if hasattr(p, 'date_granularity') and p.date_granularity:
                    trunc_map = {
                        DateGranularity.YEAR: "TRUNC_YEAR",
                        DateGranularity.QUARTER: "TRUNC_QUARTER",
                        DateGranularity.MONTH: "TRUNC_MONTH",
                        DateGranularity.WEEK: "TRUNC_WEEK",
                        DateGranularity.DAY: "TRUNC_DAY",
                    }
                    trunc_func = trunc_map.get(p.date_granularity)
                    if trunc_func:
                        dim_ref["function"] = trunc_func
                partition_dims.append(dim_ref)
            else:
                # 字符串回退：直接使用 fieldCaption
                partition_dims.append({"fieldCaption": p})
        
        # 根据 calc_type 构建表计算规范
        table_calc: dict
        calc_type = comp.calc_type  # 这是一个 Literal 字符串，如 "RANK"、"PERCENT_OF_TOTAL" 等
        
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
            # 回退到自定义
            table_calc = {
                "tableCalcType": "CUSTOM",
                "dimensions": partition_dims,
            }
        
        # 获取目标度量的聚合函数
        # 如果在 measure_agg_map 中找不到，默认为 SUM
        agg_type = AggregationType.SUM
        if measure_agg_map and comp.target in measure_agg_map:
            agg_type = measure_agg_map[comp.target]
        
        vizql_func = AGGREGATION_TO_VIZQL.get(agg_type, VizQLFunction.SUM)
        
        # 构建字段 - VizQL API 要求同时有 function 和 tableCalculation
        field = {
            "fieldCaption": comp.target,
            "function": vizql_func.value,
            "tableCalculation": table_calc,
        }
        
        # 安全访问 alias 属性（不是所有 Computation 类型都有 alias）
        alias = getattr(comp, 'alias', None)
        if alias:
            field["fieldAlias"] = alias
        
        return field
    
    def _build_rank_spec(self, comp: Computation, partition_dims: list[dict]) -> dict:
        """构建排名表计算规范。
        
        支持 RankCalc 和 DenseRankCalc 类型。
        """
        # 确定排名类型
        if comp.calc_type == "DENSE_RANK":
            rank_type = "DENSE"
        else:
            # RankCalc 有 rank_style 属性
            rank_style = getattr(comp, 'rank_style', None) or self.DEFAULT_RANK_STYLE
            rank_type = rank_style.value if hasattr(rank_style, 'value') else str(rank_style)
        
        direction = getattr(comp, 'direction', None) or self.DEFAULT_DIRECTION
        
        return {
            "tableCalcType": "RANK",
            "dimensions": partition_dims,
            "rankType": rank_type,
            "direction": direction.value if hasattr(direction, 'value') else str(direction),
        }
    
    def _build_top_n_filter_from_computation(
        self,
        comp: Computation,
        semantic_query: SemanticQuery,
    ) -> dict | None:
        """从带有 top_n 参数的计算构建 Top N 过滤器。
        
        Args:
            comp: 带有 top_n 参数的 Computation（RankCalc 或 DenseRankCalc）
            semantic_query: 完整的语义查询用于上下文
            
        Returns:
            VizQL Top N 过滤器字典或 None
        """
        top_n = getattr(comp, 'top_n', None)
        if not top_n:
            return None
        
        # 确定要过滤的维度（第一个分区维度或第一个查询维度）
        # partition_by 现在是 list[DimensionField]
        filter_dimension = None
        if comp.partition_by:
            first_partition = comp.partition_by[0]
            filter_dimension = first_partition.field_name if hasattr(first_partition, 'field_name') else first_partition
        elif semantic_query.dimensions:
            filter_dimension = semantic_query.dimensions[0].field_name
        
        if not filter_dimension:
            logger.warning(f"无法构建 Top N 过滤器：计算 {comp.target} 没有可用维度")
            return None
        
        # 方向：ASC 表示后 N 个，DESC 表示前 N 个
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
        previous = getattr(comp, 'window_previous', None)
        if previous is None:
            previous = self.DEFAULT_WINDOW_PREVIOUS
        next_val = getattr(comp, 'window_next', None)
        if next_val is None:
            next_val = self.DEFAULT_WINDOW_NEXT
        include_current = getattr(comp, 'include_current', None)
        if include_current is None:
            include_current = self.DEFAULT_INCLUDE_CURRENT
        
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
        spec = {
            "tableCalcType": "PERCENT_OF_TOTAL",
            "dimensions": partition_dims,
        }
        
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
        """构建 VizQL LOD 表达式字段。
        
        支持 LODFixed、LODInclude、LODExclude 类型。
        这些类型直接有 'dimensions' 和 'aggregation' 属性。
        """
        # 从 calc_type 字符串确定 LOD 类型
        lod_type_map = {
            "LOD_FIXED": "FIXED",
            "LOD_INCLUDE": "INCLUDE",
            "LOD_EXCLUDE": "EXCLUDE",
        }
        lod_type = lod_type_map.get(comp.calc_type, "FIXED")
        
        # 构建 LOD 表达式字符串
        # LOD 类型有 'dimensions' 属性（不是 lod_dimensions）
        lod_dims = getattr(comp, 'dimensions', []) or []
        dims_str = ", ".join(f"[{d}]" for d in lod_dims)
        
        # LOD 类型有 'aggregation' 属性（不是 lod_aggregation）
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
        """从核心过滤器模型构建 VizQL 过滤器。
        
        对于日期过滤器（DateRangeFilter）：
        - DATE/DATETIME 类型：QuantitativeDateFilter + fieldCaption
        - STRING 类型：QuantitativeDateFilter + DATEPARSE 计算字段
        
        VizQL API 限制：
        - SetFilter、MatchFilter、RelativeDateFilter 不支持 CalculatedFilterField
        - 但 QuantitativeDateFilter 支持 CalculatedFilterField
        """
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
            
            # 统一使用 QuantitativeDateFilter
            # STRING 类型需要用 DATEPARSE 转换
            if data_type == "STRING":
                # STRING 类型 - 使用 CalculatedFilterField + DATEPARSE
                field_ref = {
                    "calculation": f"DATEPARSE('yyyy-MM-dd', [{f.field_name}])"
                }
            else:
                # DATE/DATETIME 类型 - 直接使用字段名
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
            # 只添加匹配类型对应的字段，避免发送 None 值
            match_type_value = f.match_type.value if hasattr(f.match_type, 'value') else str(f.match_type)
            if match_type_value == "CONTAINS":
                filter_dict["contains"] = f.pattern
            elif match_type_value == "STARTS_WITH":
                filter_dict["startsWith"] = f.pattern
            elif match_type_value == "ENDS_WITH":
                filter_dict["endsWith"] = f.pattern
            elif match_type_value == "EXACT":
                filter_dict["exactMatch"] = f.pattern
            else:
                # 默认使用 contains
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
