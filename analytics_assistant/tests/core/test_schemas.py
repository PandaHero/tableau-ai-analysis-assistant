# -*- coding: utf-8 -*-
"""Core 层 Schema 模型单元测试。

测试任务 2.1.6：
- 测试模型验证（Pydantic field_validator）
- 测试序列化（Pydantic model_dump）
"""

import pytest
from pydantic import ValidationError

from analytics_assistant.src.core.schemas import (
    # Enums
    AggregationType,
    DateGranularity,
    SortDirection,
    RankStyle,
    RelativeTo,
    FilterType,
    TextMatchType,
    # Fields
    DimensionField,
    MeasureField,
    SortSpec,
    # Computations - LOD
    LODFixed,
    LODInclude,
    LODExclude,
    # Computations - Table Calc
    RankCalc,
    DenseRankCalc,
    PercentileCalc,
    DifferenceCalc,
    PercentDifferenceCalc,
    RunningTotalCalc,
    MovingCalc,
    PercentOfTotalCalc,
    # Filters
    SetFilter,
    DateRangeFilter,
    NumericRangeFilter,
    TextMatchFilter,
    TopNFilter,
    # Query
    SemanticQuery,
    # Validation
    ValidationResult,
    ValidationError as VError,
    ValidationErrorType,
)


# ═══════════════════════════════════════════════════════════════════════════
# 字段模型测试
# ═══════════════════════════════════════════════════════════════════════════

class TestDimensionField:
    """DimensionField 模型测试。"""
    
    def test_basic_creation(self):
        """测试基本创建。"""
        dim = DimensionField(field_name="省份")
        assert dim.field_name == "省份"
        assert dim.date_granularity is None
        assert dim.alias is None
        assert dim.sort is None
    
    def test_with_date_granularity(self):
        """测试带日期粒度的维度。"""
        dim = DimensionField(
            field_name="订单日期",
            date_granularity=DateGranularity.MONTH,
        )
        assert dim.date_granularity == DateGranularity.MONTH
    
    def test_with_sort(self):
        """测试带排序的维度。"""
        dim = DimensionField(
            field_name="省份",
            sort=SortSpec(direction=SortDirection.ASC, priority=0),
        )
        assert dim.sort is not None
        assert dim.sort.direction == SortDirection.ASC
    
    def test_serialization(self):
        """测试序列化。"""
        dim = DimensionField(
            field_name="省份",
            date_granularity=DateGranularity.YEAR,
            alias="省份名称",
        )
        data = dim.model_dump()
        assert data["field_name"] == "省份"
        assert data["date_granularity"] == DateGranularity.YEAR
        assert data["alias"] == "省份名称"
    
    def test_extra_fields_forbidden(self):
        """测试禁止额外字段。"""
        with pytest.raises(ValidationError):
            DimensionField(field_name="省份", unknown_field="value")


class TestMeasureField:
    """MeasureField 模型测试。"""
    
    def test_basic_creation(self):
        """测试基本创建。"""
        measure = MeasureField(field_name="销售额")
        assert measure.field_name == "销售额"
        assert measure.aggregation == AggregationType.SUM  # 默认值
    
    def test_with_aggregation(self):
        """测试带聚合函数的度量。"""
        measure = MeasureField(
            field_name="订单数",
            aggregation=AggregationType.COUNT,
        )
        assert measure.aggregation == AggregationType.COUNT
    
    def test_pre_aggregated_measure(self):
        """测试预聚合度量（aggregation=None）。"""
        measure = MeasureField(
            field_name="利润率",
            aggregation=None,
        )
        assert measure.aggregation is None
    
    def test_serialization(self):
        """测试序列化。"""
        measure = MeasureField(
            field_name="销售额",
            aggregation=AggregationType.AVG,
            alias="平均销售额",
        )
        data = measure.model_dump()
        assert data["field_name"] == "销售额"
        assert data["aggregation"] == AggregationType.AVG


class TestSortSpec:
    """SortSpec 模型测试。"""
    
    def test_default_values(self):
        """测试默认值。"""
        sort = SortSpec()
        assert sort.direction == SortDirection.DESC
        assert sort.priority == 0
    
    def test_custom_values(self):
        """测试自定义值。"""
        sort = SortSpec(direction=SortDirection.ASC, priority=1)
        assert sort.direction == SortDirection.ASC
        assert sort.priority == 1


# ═══════════════════════════════════════════════════════════════════════════
# LOD 表达式测试
# ═══════════════════════════════════════════════════════════════════════════

class TestLODFixed:
    """LODFixed 模型测试。"""
    
    def test_basic_creation(self):
        """测试基本创建。"""
        lod = LODFixed(
            target="销售额",
            dimensions=["客户ID"],
            aggregation=AggregationType.SUM,
        )
        assert lod.calc_type == "LOD_FIXED"
        assert lod.target == "销售额"
        assert lod.dimensions == ["客户ID"]
    
    def test_global_aggregation(self):
        """测试全局聚合（空维度）。"""
        lod = LODFixed(
            target="销售额",
            dimensions=[],
            aggregation=AggregationType.SUM,
        )
        assert lod.dimensions == []
    
    def test_target_validation(self):
        """测试 target 不能为空。"""
        with pytest.raises(ValidationError) as exc_info:
            LODFixed(target="", dimensions=[], aggregation=AggregationType.SUM)
        assert "target 不能为空" in str(exc_info.value)
    
    def test_target_whitespace_stripped(self):
        """测试 target 空白被去除。"""
        lod = LODFixed(
            target="  销售额  ",
            dimensions=[],
            aggregation=AggregationType.SUM,
        )
        assert lod.target == "销售额"


class TestLODInclude:
    """LODInclude 模型测试。"""
    
    def test_basic_creation(self):
        """测试基本创建。"""
        lod = LODInclude(
            target="订单金额",
            dimensions=["订单ID"],
            aggregation=AggregationType.AVG,
        )
        assert lod.calc_type == "LOD_INCLUDE"
        assert lod.dimensions == ["订单ID"]
    
    def test_dimensions_required(self):
        """测试 dimensions 不能为空。"""
        with pytest.raises(ValidationError) as exc_info:
            LODInclude(target="销售额", dimensions=[], aggregation=AggregationType.SUM)
        assert "dimensions 不能为空" in str(exc_info.value)


class TestLODExclude:
    """LODExclude 模型测试。"""
    
    def test_basic_creation(self):
        """测试基本创建。"""
        lod = LODExclude(
            target="销售额",
            dimensions=["子类别"],
            aggregation=AggregationType.SUM,
        )
        assert lod.calc_type == "LOD_EXCLUDE"
    
    def test_dimensions_required(self):
        """测试 dimensions 不能为空。"""
        with pytest.raises(ValidationError) as exc_info:
            LODExclude(target="销售额", dimensions=[], aggregation=AggregationType.SUM)
        assert "dimensions 不能为空" in str(exc_info.value)


# ═══════════════════════════════════════════════════════════════════════════
# 表计算测试
# ═══════════════════════════════════════════════════════════════════════════

class TestRankCalc:
    """RankCalc 模型测试。"""
    
    def test_basic_creation(self):
        """测试基本创建。"""
        rank = RankCalc(target="销售额")
        assert rank.calc_type == "RANK"
        assert rank.target == "销售额"
        assert rank.direction == SortDirection.DESC  # 默认值
        assert rank.partition_by == []
    
    def test_with_partition(self):
        """测试带分区的排名。"""
        rank = RankCalc(
            target="销售额",
            partition_by=[DimensionField(field_name="类别")],
        )
        assert len(rank.partition_by) == 1
        assert rank.partition_by[0].field_name == "类别"
    
    def test_with_top_n(self):
        """测试带 Top N 的排名。"""
        rank = RankCalc(
            target="销售额",
            top_n=10,
        )
        assert rank.top_n == 10
    
    def test_target_validation(self):
        """测试 target 不能为空。"""
        with pytest.raises(ValidationError):
            RankCalc(target="")


class TestDenseRankCalc:
    """DenseRankCalc 模型测试。"""
    
    def test_basic_creation(self):
        """测试基本创建。"""
        rank = DenseRankCalc(target="销售额")
        assert rank.calc_type == "DENSE_RANK"


class TestRunningTotalCalc:
    """RunningTotalCalc 模型测试。"""
    
    def test_basic_creation(self):
        """测试基本创建。"""
        running = RunningTotalCalc(target="销售额")
        assert running.calc_type == "RUNNING_TOTAL"
        assert running.aggregation == AggregationType.SUM  # 默认值
    
    def test_with_restart(self):
        """测试带重启的累计（YTD）。"""
        running = RunningTotalCalc(
            target="销售额",
            restart_every="Year",
        )
        assert running.restart_every == "Year"


class TestMovingCalc:
    """MovingCalc 模型测试。"""
    
    def test_default_values(self):
        """测试默认值。"""
        moving = MovingCalc(target="销售额")
        assert moving.aggregation == AggregationType.AVG
        assert moving.window_previous == 2
        assert moving.window_next == 0
        assert moving.include_current is True
    
    def test_custom_window(self):
        """测试自定义窗口。"""
        moving = MovingCalc(
            target="销售额",
            window_previous=6,
            window_next=0,
            include_current=True,
        )
        assert moving.window_previous == 6


class TestPercentOfTotalCalc:
    """PercentOfTotalCalc 模型测试。"""
    
    def test_basic_creation(self):
        """测试基本创建。"""
        pct = PercentOfTotalCalc(target="销售额")
        assert pct.calc_type == "PERCENT_OF_TOTAL"
        assert pct.partition_by == []
    
    def test_with_level_of(self):
        """测试带 level_of 的占比。"""
        pct = PercentOfTotalCalc(
            target="销售额",
            level_of="类别",
        )
        assert pct.level_of == "类别"


class TestDifferenceCalc:
    """DifferenceCalc 模型测试。"""
    
    def test_basic_creation(self):
        """测试基本创建。"""
        diff = DifferenceCalc(
            target="销售额",
            relative_to=RelativeTo.PREVIOUS,
        )
        assert diff.calc_type == "DIFFERENCE"
        assert diff.relative_to == RelativeTo.PREVIOUS


class TestPercentDifferenceCalc:
    """PercentDifferenceCalc 模型测试。"""
    
    def test_basic_creation(self):
        """测试基本创建。"""
        pct_diff = PercentDifferenceCalc(
            target="销售额",
            relative_to=RelativeTo.FIRST,
        )
        assert pct_diff.calc_type == "PERCENT_DIFFERENCE"
        assert pct_diff.relative_to == RelativeTo.FIRST


# ═══════════════════════════════════════════════════════════════════════════
# 过滤器测试
# ═══════════════════════════════════════════════════════════════════════════

class TestSetFilter:
    """SetFilter 模型测试。"""
    
    def test_basic_creation(self):
        """测试基本创建。"""
        f = SetFilter(
            field_name="省份",
            values=["北京", "上海"],
        )
        assert f.field_name == "省份"
        assert f.values == ["北京", "上海"]
        assert f.exclude is False  # 默认值
    
    def test_exclude_filter(self):
        """测试排除过滤器。"""
        f = SetFilter(
            field_name="省份",
            values=["西藏"],
            exclude=True,
        )
        assert f.exclude is True


class TestDateRangeFilter:
    """DateRangeFilter 模型测试。"""
    
    def test_basic_creation(self):
        """测试基本创建。"""
        from datetime import date
        f = DateRangeFilter(
            field_name="订单日期",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        assert f.field_name == "订单日期"
        assert f.start_date == date(2024, 1, 1)
    
    def test_open_ended_range(self):
        """测试开放范围。"""
        from datetime import date
        f = DateRangeFilter(
            field_name="订单日期",
            start_date=date(2024, 1, 1),
        )
        assert f.end_date is None


class TestNumericRangeFilter:
    """NumericRangeFilter 模型测试。"""
    
    def test_basic_creation(self):
        """测试基本创建。"""
        f = NumericRangeFilter(
            field_name="销售额",
            min_value=1000,
            max_value=10000,
        )
        assert f.min_value == 1000
        assert f.max_value == 10000


class TestTextMatchFilter:
    """TextMatchFilter 模型测试。"""
    
    def test_contains_filter(self):
        """测试包含过滤器。"""
        f = TextMatchFilter(
            field_name="产品名称",
            pattern="手机",
            match_type=TextMatchType.CONTAINS,
        )
        assert f.match_type == TextMatchType.CONTAINS


class TestTopNFilter:
    """TopNFilter 模型测试。"""
    
    def test_basic_creation(self):
        """测试基本创建。"""
        f = TopNFilter(
            field_name="省份",
            n=10,
            by_field="销售额",
            direction=SortDirection.DESC,
        )
        assert f.n == 10
        assert f.by_field == "销售额"


# ═══════════════════════════════════════════════════════════════════════════
# SemanticQuery 测试
# ═══════════════════════════════════════════════════════════════════════════

class TestSemanticQuery:
    """SemanticQuery 模型测试。"""
    
    def test_basic_creation(self):
        """测试基本创建。"""
        query = SemanticQuery(
            dimensions=[DimensionField(field_name="省份")],
            measures=[MeasureField(field_name="销售额")],
        )
        assert len(query.dimensions) == 1
        assert len(query.measures) == 1
    
    def test_empty_query(self):
        """测试空查询。"""
        query = SemanticQuery()
        assert query.dimensions is None
        assert query.measures is None
    
    def test_with_computations(self):
        """测试带计算的查询。"""
        query = SemanticQuery(
            dimensions=[DimensionField(field_name="省份")],
            measures=[MeasureField(field_name="销售额")],
            computations=[
                RankCalc(target="销售额"),
            ],
        )
        assert len(query.computations) == 1
    
    def test_with_filters(self):
        """测试带过滤器的查询。"""
        query = SemanticQuery(
            dimensions=[DimensionField(field_name="省份")],
            measures=[MeasureField(field_name="销售额")],
            filters=[
                SetFilter(field_name="省份", values=["北京"]),
            ],
        )
        assert len(query.filters) == 1
    
    def test_get_sorts_empty(self):
        """测试 get_sorts 空结果。"""
        query = SemanticQuery(
            dimensions=[DimensionField(field_name="省份")],
        )
        sorts = query.get_sorts()
        assert sorts == []
    
    def test_get_sorts_with_dimension_sort(self):
        """测试 get_sorts 带维度排序。"""
        query = SemanticQuery(
            dimensions=[
                DimensionField(
                    field_name="省份",
                    sort=SortSpec(direction=SortDirection.ASC, priority=0),
                ),
            ],
        )
        sorts = query.get_sorts()
        assert len(sorts) == 1
        assert sorts[0][0] == "省份"
        assert sorts[0][1].direction == SortDirection.ASC
    
    def test_get_sorts_with_measure_sort(self):
        """测试 get_sorts 带度量排序。"""
        query = SemanticQuery(
            dimensions=[DimensionField(field_name="省份")],
            measures=[
                MeasureField(
                    field_name="销售额",
                    sort=SortSpec(direction=SortDirection.DESC, priority=0),
                ),
            ],
        )
        sorts = query.get_sorts()
        assert len(sorts) == 1
        assert sorts[0][0] == "销售额"
    
    def test_get_sorts_priority_order(self):
        """测试 get_sorts 按优先级排序。"""
        query = SemanticQuery(
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
        sorts = query.get_sorts()
        assert len(sorts) == 2
        # 按优先级排序：销售额(0) 在前，省份(1) 在后
        assert sorts[0][0] == "销售额"
        assert sorts[1][0] == "省份"
    
    def test_serialization(self):
        """测试序列化。"""
        query = SemanticQuery(
            dimensions=[DimensionField(field_name="省份")],
            measures=[MeasureField(field_name="销售额")],
            row_limit=100,
        )
        data = query.model_dump()
        assert data["row_limit"] == 100
        assert len(data["dimensions"]) == 1
    
    def test_extra_fields_forbidden(self):
        """测试禁止额外字段。"""
        with pytest.raises(ValidationError):
            SemanticQuery(unknown_field="value")


# ═══════════════════════════════════════════════════════════════════════════
# ValidationResult 测试
# ═══════════════════════════════════════════════════════════════════════════

class TestValidationResult:
    """ValidationResult 模型测试。"""
    
    def test_valid_result(self):
        """测试有效结果。"""
        result = ValidationResult(is_valid=True)
        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []
    
    def test_invalid_result_with_errors(self):
        """测试带错误的无效结果。"""
        result = ValidationResult(
            is_valid=False,
            errors=[
                VError(
                    error_type=ValidationErrorType.MISSING_REQUIRED,
                    field_path="dimensions",
                    message="缺少维度",
                ),
            ],
        )
        assert result.is_valid is False
        assert len(result.errors) == 1
    
    def test_with_auto_fixed(self):
        """测试带自动修复的结果。"""
        result = ValidationResult(
            is_valid=True,
            auto_fixed=["measures[0].aggregation"],
        )
        assert len(result.auto_fixed) == 1
