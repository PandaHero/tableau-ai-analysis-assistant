# -*- coding: utf-8 -*-
"""Tableau QueryBuilder 单元测试。

测试任务 2.2.5：
- 测试 VizQL 查询构建
- 测试查询验证

注意：测试使用 SemanticOutput 作为输入，这是语义解析器的输出格式。
"""

import pytest

from analytics_assistant.src.core.schemas import (
    AggregationType,
    DateGranularity,
    DimensionField,
    MeasureField,
    SortDirection,
    SortSpec,
    SetFilter,
    DateRangeFilter,
    NumericRangeFilter,
    TextMatchFilter,
    TopNFilter,
    TextMatchType,
    ValidationErrorType,
)
from analytics_assistant.src.agents.semantic_parser.schemas.output import (
    SemanticOutput,
    What,
    Where,
    SelfCheck,
    DerivedComputation,
    CalcType,
)
from analytics_assistant.src.platform.tableau.query_builder import TableauQueryBuilder


@pytest.fixture
def builder():
    """创建 QueryBuilder 实例。"""
    return TableauQueryBuilder()


def make_semantic_output(
    dimensions: list[DimensionField] | None = None,
    measures: list[MeasureField] | None = None,
    filters: list | None = None,
    computations: list[DerivedComputation] | None = None,
) -> SemanticOutput:
    """创建 SemanticOutput 测试对象的辅助函数。"""
    return SemanticOutput(
        restated_question="测试查询",
        what=What(measures=measures or []),
        where=Where(
            dimensions=dimensions or [],
            filters=filters or [],
        ),
        computations=computations or [],
        self_check=SelfCheck(
            field_mapping_confidence=1.0,
            time_range_confidence=1.0,
            computation_confidence=1.0,
            overall_confidence=1.0,
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 基本构建测试
# ═══════════════════════════════════════════════════════════════════════════

class TestBasicBuild:
    """基本查询构建测试。"""
    
    def test_simple_dimension_measure(self, builder):
        """测试简单维度+度量查询。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="省份")],
            measures=[MeasureField(field_name="销售额")],
        )
        result = builder.build(query)
        
        assert "fields" in result
        assert len(result["fields"]) == 2
        
        # 检查维度字段
        dim_field = result["fields"][0]
        assert dim_field["fieldCaption"] == "省份"
        
        # 检查度量字段
        measure_field = result["fields"][1]
        assert measure_field["fieldCaption"] == "销售额"
        assert measure_field["function"] == "SUM"
    
    def test_dimension_with_date_granularity(self, builder):
        """测试带日期粒度的维度。"""
        query = make_semantic_output(
            dimensions=[
                DimensionField(
                    field_name="订单日期",
                    date_granularity=DateGranularity.MONTH,
                ),
            ],
        )
        result = builder.build(query)
        
        dim_field = result["fields"][0]
        assert dim_field["fieldCaption"] == "订单日期"
        assert dim_field["function"] == "TRUNC_MONTH"
    
    def test_dimension_with_string_date(self, builder):
        """测试字符串类型日期维度。"""
        query = make_semantic_output(
            dimensions=[
                DimensionField(
                    field_name="订单日期",
                    date_granularity=DateGranularity.YEAR,
                ),
            ],
        )
        # 提供字段元数据表明是 STRING 类型
        result = builder.build(
            query,
            field_metadata={"订单日期": {"dataType": "STRING"}},
        )
        
        dim_field = result["fields"][0]
        assert "calculation" in dim_field
        assert "DATETRUNC" in dim_field["calculation"]
        assert "DATEPARSE" in dim_field["calculation"]
    
    def test_measure_with_different_aggregations(self, builder):
        """测试不同聚合函数的度量。"""
        query = make_semantic_output(
            measures=[
                MeasureField(field_name="销售额", aggregation=AggregationType.SUM),
                MeasureField(field_name="订单数", aggregation=AggregationType.COUNT),
                MeasureField(field_name="平均单价", aggregation=AggregationType.AVG),
                MeasureField(field_name="客户数", aggregation=AggregationType.COUNTD),
            ],
        )
        result = builder.build(query)
        
        assert result["fields"][0]["function"] == "SUM"
        assert result["fields"][1]["function"] == "COUNT"
        assert result["fields"][2]["function"] == "AVG"
        assert result["fields"][3]["function"] == "COUNTD"
    
    def test_pre_aggregated_measure(self, builder):
        """测试预聚合度量（无聚合函数）。"""
        query = make_semantic_output(
            measures=[
                MeasureField(field_name="利润率", aggregation=None),
            ],
        )
        result = builder.build(query)
        
        measure_field = result["fields"][0]
        assert "function" not in measure_field
    
    def test_with_alias(self, builder):
        """测试带别名的字段。"""
        query = make_semantic_output(
            dimensions=[
                DimensionField(field_name="省份", alias="省份名称"),
            ],
            measures=[
                MeasureField(field_name="销售额", alias="总销售额"),
            ],
        )
        result = builder.build(query)
        
        assert result["fields"][0]["fieldAlias"] == "省份名称"
        assert result["fields"][1]["fieldAlias"] == "总销售额"


# ═══════════════════════════════════════════════════════════════════════════
# 排序测试
# ═══════════════════════════════════════════════════════════════════════════

class TestSortBuild:
    """排序构建测试。"""
    
    def test_dimension_sort(self, builder):
        """测试维度排序。"""
        query = make_semantic_output(
            dimensions=[
                DimensionField(
                    field_name="省份",
                    sort=SortSpec(direction=SortDirection.ASC, priority=0),
                ),
            ],
        )
        result = builder.build(query)
        
        assert "sorts" in result
        assert len(result["sorts"]) == 1
        assert result["sorts"][0]["field"]["fieldCaption"] == "省份"
        assert result["sorts"][0]["sortDirection"] == "ASC"
    
    def test_measure_sort(self, builder):
        """测试度量排序。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="省份")],
            measures=[
                MeasureField(
                    field_name="销售额",
                    sort=SortSpec(direction=SortDirection.DESC, priority=0),
                ),
            ],
        )
        result = builder.build(query)
        
        assert "sorts" in result
        assert result["sorts"][0]["field"]["fieldCaption"] == "销售额"
        assert result["sorts"][0]["sortDirection"] == "DESC"
    
    def test_multiple_sorts_priority(self, builder):
        """测试多字段排序优先级。"""
        query = make_semantic_output(
            dimensions=[
                DimensionField(
                    field_name="省份",
                    sort=SortSpec(direction=SortDirection.ASC, priority=1),
                ),
            ],
            measures=[
                MeasureField(
                    field_name="销售额",
                    sort=SortSpec(direction=SortDirection.DESC, priority=0),
                ),
            ],
        )
        result = builder.build(query)
        
        assert len(result["sorts"]) == 2
        # 按优先级排序
        assert result["sorts"][0]["field"]["fieldCaption"] == "销售额"
        assert result["sorts"][1]["field"]["fieldCaption"] == "省份"


# ═══════════════════════════════════════════════════════════════════════════
# 派生计算测试（DerivedComputation）
# ═══════════════════════════════════════════════════════════════════════════

class TestDerivedComputationBuild:
    """派生计算构建测试。"""
    
    def test_ratio_computation(self, builder):
        """测试比率计算。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="省份")],
            measures=[
                MeasureField(field_name="利润"),
                MeasureField(field_name="销售额"),
            ],
            computations=[
                DerivedComputation(
                    name="profit_rate",
                    display_name="利润率",
                    formula="[利润]/[销售额]",
                    calc_type=CalcType.RATIO,
                    base_measures=["利润", "销售额"],
                ),
            ],
        )
        result = builder.build(query)
        
        # 找到计算字段
        calc_field = None
        for f in result["fields"]:
            if "calculation" in f and "[利润]/[销售额]" in f.get("calculation", ""):
                calc_field = f
                break
        
        assert calc_field is not None
        assert calc_field["fieldCaption"] == "利润率"
    
    def test_subquery_computation_to_lod(self, builder):
        """测试子查询计算转换为 LOD。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="省份")],
            measures=[MeasureField(field_name="销售额")],
            computations=[
                DerivedComputation(
                    name="customer_first_purchase",
                    display_name="客户首购日期",
                    calc_type=CalcType.SUBQUERY,
                    base_measures=["订单日期"],
                    subquery_dimensions=["客户ID"],
                    subquery_aggregation="MIN",
                ),
            ],
        )
        result = builder.build(query)
        
        # 找到 LOD 字段
        lod_field = None
        for f in result["fields"]:
            if "calculation" in f and "FIXED" in f.get("calculation", ""):
                lod_field = f
                break
        
        assert lod_field is not None
        assert "[客户ID]" in lod_field["calculation"]
        assert "MIN" in lod_field["calculation"]
    
    def test_table_calc_rank(self, builder):
        """测试排名表计算。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="省份")],
            measures=[MeasureField(field_name="销售额")],
            computations=[
                DerivedComputation(
                    name="sales_rank",
                    display_name="销售排名",
                    calc_type=CalcType.TABLE_CALC_RANK,
                    base_measures=["销售额"],
                ),
            ],
        )
        result = builder.build(query)
        
        # 找到表计算字段
        calc_field = None
        for f in result["fields"]:
            if "tableCalculation" in f:
                calc_field = f
                break
        
        assert calc_field is not None
        assert calc_field["tableCalculation"]["tableCalcType"] == "RANK"
    
    def test_table_calc_percent_diff(self, builder):
        """测试百分比差异表计算（增长率）。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="月份")],
            measures=[MeasureField(field_name="销售额")],
            computations=[
                DerivedComputation(
                    name="sales_growth",
                    display_name="销售增长率",
                    calc_type=CalcType.TABLE_CALC_PERCENT_DIFF,
                    base_measures=["销售额"],
                    relative_to="PREVIOUS",
                ),
            ],
        )
        result = builder.build(query)
        
        calc_field = [f for f in result["fields"] if "tableCalculation" in f][0]
        assert calc_field["tableCalculation"]["tableCalcType"] == "PERCENT_DIFFERENCE_FROM"
    
    def test_table_calc_percent_of_total(self, builder):
        """测试占比表计算。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="省份")],
            measures=[MeasureField(field_name="销售额")],
            computations=[
                DerivedComputation(
                    name="market_share",
                    display_name="市场份额",
                    calc_type=CalcType.TABLE_CALC_PERCENT_OF_TOTAL,
                    base_measures=["销售额"],
                ),
            ],
        )
        result = builder.build(query)
        
        calc_field = [f for f in result["fields"] if "tableCalculation" in f][0]
        assert calc_field["tableCalculation"]["tableCalcType"] == "PERCENT_OF_TOTAL"
    
    def test_table_calc_running(self, builder):
        """测试累计表计算。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="月份")],
            measures=[MeasureField(field_name="销售额")],
            computations=[
                DerivedComputation(
                    name="ytd_sales",
                    display_name="年累计销售额",
                    calc_type=CalcType.TABLE_CALC_RUNNING,
                    base_measures=["销售额"],
                ),
            ],
        )
        result = builder.build(query)
        
        calc_field = [f for f in result["fields"] if "tableCalculation" in f][0]
        assert calc_field["tableCalculation"]["tableCalcType"] == "RUNNING_TOTAL"
    
    def test_table_calc_moving(self, builder):
        """测试移动计算。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="月份")],
            measures=[MeasureField(field_name="销售额")],
            computations=[
                DerivedComputation(
                    name="moving_avg",
                    display_name="移动平均",
                    calc_type=CalcType.TABLE_CALC_MOVING,
                    base_measures=["销售额"],
                ),
            ],
        )
        result = builder.build(query)
        
        calc_field = [f for f in result["fields"] if "tableCalculation" in f][0]
        assert calc_field["tableCalculation"]["tableCalcType"] == "MOVING_CALCULATION"


# ═══════════════════════════════════════════════════════════════════════════
# 过滤器测试
# ═══════════════════════════════════════════════════════════════════════════

class TestFilterBuild:
    """过滤器构建测试。"""
    
    def test_set_filter(self, builder):
        """测试集合过滤器。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="省份")],
            filters=[
                SetFilter(field_name="省份", values=["北京", "上海"]),
            ],
        )
        result = builder.build(query)
        
        assert "filters" in result
        assert len(result["filters"]) == 1
        assert result["filters"][0]["filterType"] == "SET"
        assert result["filters"][0]["values"] == ["北京", "上海"]
    
    def test_set_filter_exclude(self, builder):
        """测试排除集合过滤器。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="省份")],
            filters=[
                SetFilter(field_name="省份", values=["西藏"], exclude=True),
            ],
        )
        result = builder.build(query)
        
        assert result["filters"][0]["exclude"] is True
    
    def test_date_range_filter(self, builder):
        """测试日期范围过滤器。"""
        from datetime import date
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="订单日期")],
            filters=[
                DateRangeFilter(
                    field_name="订单日期",
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 12, 31),
                ),
            ],
        )
        result = builder.build(query)
        
        assert result["filters"][0]["filterType"] == "QUANTITATIVE_DATE"
        assert "minDate" in result["filters"][0]
        assert "maxDate" in result["filters"][0]
    
    def test_date_range_filter_string_type(self, builder):
        """测试字符串类型日期过滤器。"""
        from datetime import date
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="订单日期")],
            filters=[
                DateRangeFilter(
                    field_name="订单日期",
                    start_date=date(2024, 1, 1),
                ),
            ],
        )
        result = builder.build(
            query,
            field_metadata={"订单日期": {"dataType": "STRING"}},
        )
        
        # STRING 类型应该使用 DATEPARSE
        assert "calculation" in result["filters"][0]["field"]
        assert "DATEPARSE" in result["filters"][0]["field"]["calculation"]
    
    def test_numeric_range_filter(self, builder):
        """测试数值范围过滤器。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="省份")],
            measures=[MeasureField(field_name="销售额")],
            filters=[
                NumericRangeFilter(
                    field_name="销售额",
                    min_value=1000,
                    max_value=10000,
                ),
            ],
        )
        result = builder.build(query)
        
        assert result["filters"][0]["filterType"] == "QUANTITATIVE_NUMERICAL"
        assert result["filters"][0]["min"] == 1000
        assert result["filters"][0]["max"] == 10000
    
    def test_text_match_filter_contains(self, builder):
        """测试文本包含过滤器。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="产品名称")],
            filters=[
                TextMatchFilter(
                    field_name="产品名称",
                    pattern="手机",
                    match_type=TextMatchType.CONTAINS,
                ),
            ],
        )
        result = builder.build(query)
        
        assert result["filters"][0]["filterType"] == "MATCH"
        assert result["filters"][0]["contains"] == "手机"
    
    def test_text_match_filter_starts_with(self, builder):
        """测试文本开头过滤器。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="产品名称")],
            filters=[
                TextMatchFilter(
                    field_name="产品名称",
                    pattern="Apple",
                    match_type=TextMatchType.STARTS_WITH,
                ),
            ],
        )
        result = builder.build(query)
        
        assert result["filters"][0]["startsWith"] == "Apple"
    
    def test_top_n_filter(self, builder):
        """测试 Top N 过滤器。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="省份")],
            measures=[MeasureField(field_name="销售额")],
            filters=[
                TopNFilter(
                    field_name="省份",
                    n=10,
                    by_field="销售额",
                    direction=SortDirection.DESC,
                ),
            ],
        )
        result = builder.build(query)
        
        assert result["filters"][0]["filterType"] == "TOP"
        assert result["filters"][0]["howMany"] == 10
        assert result["filters"][0]["fieldToMeasure"]["fieldCaption"] == "销售额"


# ═══════════════════════════════════════════════════════════════════════════
# 验证测试
# ═══════════════════════════════════════════════════════════════════════════

class TestValidation:
    """查询验证测试。"""
    
    def test_valid_query(self, builder):
        """测试有效查询。"""
        query = make_semantic_output(
            dimensions=[DimensionField(field_name="省份")],
            measures=[MeasureField(field_name="销售额")],
        )
        result = builder.validate(query)
        
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    def test_empty_query_invalid(self, builder):
        """测试空查询无效。"""
        query = make_semantic_output()
        result = builder.validate(query)
        
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert result.errors[0].error_type == ValidationErrorType.MISSING_REQUIRED
