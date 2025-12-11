# -*- coding: utf-8 -*-
"""
日期筛选端到端集成测试

使用已实现的组件进行完整流程测试�?
- DateParser: 日期解析
- QueryBuilderNode: 查询构建
- VizQLClient: 查询执行

测试覆盖�?
1. DATE 类型字段 - 所有日期筛选场�?
2. STRING 类型字段 - DATEPARSE 转换场景
3. 完整工作�?- �?SemanticQuery �?VizQL 执行

注意�?
- 所有测试使用真实的 Tableau 环境
- 需要配�?.env 文件中的 Tableau 配置
"""

import pytest
import asyncio
import os
import sys
from typing import Dict, Any, List, Optional
from datetime import datetime

# Windows 终端编码修复
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 确保从项目根目录加载 .env
from dotenv import load_dotenv
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# 导入已实现的组件
from tableau_assistant.src.capabilities.date_processing.parser import DateParser
from tableau_assistant.src.models.semantic.query import (
    SemanticQuery,
    MappedQuery,
    MeasureSpec,
    DimensionSpec,
    FilterSpec,
    TimeFilterSpec,
    FieldMapping,
)
from tableau_assistant.src.models.semantic.enums import (
    FilterType,
    TimeFilterMode,
    PeriodType,
    DateRangeType,
    AggregationType,
    TimeGranularity,
    MappingSource,
)
from tableau_assistant.src.nodes.query_builder.node import QueryBuilderNode, VizQLQuery
from tableau_assistant.src.bi_platforms.tableau.vizql_client import VizQLClient, VizQLClientConfig
from tableau_assistant.src.bi_platforms.tableau.auth import _get_tableau_context_from_env


# ============================================================================
# 测试配置
# ============================================================================

# DATE 类型数据�?(Superstore)
DATE_DATASOURCE_LUID = "e99f1815-b3b8-4660-9624-946ea028338f"
DATE_FIELD = "Ship Date"
DATE_MEASURE = "Discount"

# STRING 类型数据�?
STRING_DATASOURCE_LUID = "b9f0e505-9d74-4f4d-a629-6d1095638eaa"
STRING_DATE_FIELD = "first_receive_dt"
STRING_MEASURE = "first_receive_sale_num"
STRING_DATE_FORMAT = "yyyy-MM-dd"


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def settings():
    """加载配置"""
    from tableau_assistant.src.config.settings import Settings
    return Settings()


@pytest.fixture(scope="module")
def check_env(settings):
    """检查环境配"""
    if not settings.tableau_domain:
        pytest.skip("需要配TABLEAU_DOMAIN")


@pytest.fixture
def date_parser():
    """创建DateParser 实例"""
    return DateParser()


@pytest.fixture
def query_builder():
    """创建 QueryBuilderNode 实例"""
    return QueryBuilderNode()


@pytest.fixture(scope="module")
def vizql_client(settings, check_env):
    """创建 VizQLClient 实例"""
    ctx = _get_tableau_context_from_env()
    
    if not ctx.get("api_key"):
        pytest.skip("认证失败，请检�?.env 配置")
    
    config = VizQLClientConfig(
        base_url=ctx["domain"],
        timeout=60,
        max_retries=3
    )
    
    client = VizQLClient(config=config)
    # 将认证信息附加到 client 上供测试使用
    client._api_key = ctx["api_key"]
    client._site = ctx.get("site")
    yield client
    client.close()


# ============================================================================
# 1. DateParser 单元测试
# ============================================================================

class TestDateParser:
    """DateParser 组件测试"""
    
    def test_absolute_range(self, date_parser):
        """测试绝对日期范围"""
        time_filter = TimeFilterSpec(
            mode=TimeFilterMode.ABSOLUTE_RANGE,
            start_date="2023-01-01",
            end_date="2023-12-31"
        )
        
        result = date_parser.process_time_filter(time_filter)
        
        assert result["filter_type"] == "QUANTITATIVE_DATE"
        assert result["quantitative_filter_type"] == "RANGE"
        assert result["min_date"] == "2023-01-01"
        assert result["max_date"] == "2023-12-31"
    
    def test_relative_lastn_months(self, date_parser):
        """测试相对日期 - 最近N个月"""
        time_filter = TimeFilterSpec(
            mode=TimeFilterMode.RELATIVE,
            period_type=PeriodType.MONTHS,
            date_range_type=DateRangeType.LASTN,
            range_n=3
        )
        
        result = date_parser.process_time_filter(time_filter)
        
        assert result["filter_type"] == "DATE"
        assert result["period_type"] == "MONTHS"
        assert result["date_range_type"] == "LASTN"
        assert result["range_n"] == 3
    
    def test_relative_todate_year(self, date_parser):
        """测试相对日期 - 年初至今"""
        time_filter = TimeFilterSpec(
            mode=TimeFilterMode.RELATIVE,
            period_type=PeriodType.YEARS,
            date_range_type=DateRangeType.TODATE
        )
        
        result = date_parser.process_time_filter(time_filter)
        
        assert result["filter_type"] == "DATE"
        assert result["period_type"] == "YEARS"
        assert result["date_range_type"] == "TODATE"
    
    def test_relative_current_month(self, date_parser):
        """测试相对日期 - 本月"""
        time_filter = TimeFilterSpec(
            mode=TimeFilterMode.RELATIVE,
            period_type=PeriodType.MONTHS,
            date_range_type=DateRangeType.CURRENT
        )
        
        result = date_parser.process_time_filter(time_filter)
        
        assert result["filter_type"] == "DATE"
        assert result["period_type"] == "MONTHS"
        assert result["date_range_type"] == "CURRENT"
    
    def test_calculate_relative_dates(self, date_parser):
        """测试计算相对日期的具体范"""
        time_filter = TimeFilterSpec(
            mode=TimeFilterMode.RELATIVE,
            period_type=PeriodType.YEARS,
            date_range_type=DateRangeType.TODATE
        )
        
        ref_date = datetime(2024, 12, 11)
        start, end = date_parser.calculate_relative_dates(time_filter, ref_date)
        
        assert start == "2024-01-01"
        assert end == "2024-12-11"
    
    def test_set_filter(self, date_parser):
        """测试离散日期集合"""
        time_filter = TimeFilterSpec(
            mode=TimeFilterMode.SET,
            date_values=["2024-01", "2024-02", "2024-03"]
        )
        
        result = date_parser.process_time_filter(time_filter)
        
        assert result["filter_type"] == "SET"
        assert result["values"] == ["2024-01", "2024-02", "2024-03"]
        assert result["exclude"] == False
    
    def test_set_filter_quarter_expansion(self, date_parser):
        """测试季度展开"""
        time_filter = TimeFilterSpec(
            mode=TimeFilterMode.SET,
            date_values=["2024-Q1"]
        )
        
        result = date_parser.process_time_filter(time_filter)
        
        assert result["filter_type"] == "SET"
        assert result["values"] == ["2024-01", "2024-02", "2024-03"]


# ============================================================================
# 2. QueryBuilderNode 集成测试
# ============================================================================

class TestQueryBuilderNode:
    """QueryBuilderNode 组件测试"""
    
    @pytest.mark.asyncio
    async def test_build_date_filter_absolute(self, query_builder):
        """测试构建绝对日期"""
        semantic_query = SemanticQuery(
            dimensions=[DimensionSpec(
                name="Ship Date",
                time_granularity=TimeGranularity.MONTH
            )],
            measures=[MeasureSpec(
                name="Discount",
                aggregation=AggregationType.SUM
            )],
            filters=[FilterSpec(
                field="Ship Date",
                filter_type=FilterType.TIME_RANGE,
                time_filter=TimeFilterSpec(
                    mode=TimeFilterMode.ABSOLUTE_RANGE,
                    start_date="2023-01-01",
                    end_date="2023-12-31"
                )
            )]
        )
        
        # 创建字段映射
        field_mappings = {
            "Ship Date": FieldMapping(
                business_term="Ship Date",
                technical_field="Ship Date",
                confidence=1.0,
                mapping_source=MappingSource.EXACT_MATCH,
                data_type="DATE"
            ),
            "Discount": FieldMapping(
                business_term="Discount",
                technical_field="Discount",
                confidence=1.0,
                mapping_source=MappingSource.EXACT_MATCH,
                data_type="REAL"
            )
        }
        
        mapped_query = MappedQuery(
            semantic_query=semantic_query,
            field_mappings=field_mappings
        )
        
        vizql_query = await query_builder.build(mapped_query)
        
        # 验证查询结构
        assert len(vizql_query.fields) == 2
        assert len(vizql_query.filters) == 1
        
        # 验证筛选器
        filter_dict = vizql_query.filters[0]
        assert filter_dict["filterType"] == "QUANTITATIVE_DATE"
        assert filter_dict["minDate"] == "2023-01-01"
        assert filter_dict["maxDate"] == "2023-12-31"
    
    @pytest.mark.asyncio
    async def test_build_date_filter_relative(self, query_builder):
        """测试构建相对日期"""
        semantic_query = SemanticQuery(
            dimensions=[DimensionSpec(
                name="Ship Date",
                time_granularity=TimeGranularity.MONTH
            )],
            measures=[MeasureSpec(
                name="Discount",
                aggregation=AggregationType.SUM
            )],
            filters=[FilterSpec(
                field="Ship Date",
                filter_type=FilterType.TIME_RANGE,
                time_filter=TimeFilterSpec(
                    mode=TimeFilterMode.RELATIVE,
                    period_type=PeriodType.MONTHS,
                    date_range_type=DateRangeType.LASTN,
                    range_n=3
                )
            )]
        )
        
        field_mappings = {
            "Ship Date": FieldMapping(
                business_term="Ship Date",
                technical_field="Ship Date",
                confidence=1.0,
                mapping_source=MappingSource.EXACT_MATCH,
                data_type="DATE"
            ),
            "Discount": FieldMapping(
                business_term="Discount",
                technical_field="Discount",
                confidence=1.0,
                mapping_source=MappingSource.EXACT_MATCH,
                data_type="REAL"
            )
        }
        
        mapped_query = MappedQuery(
            semantic_query=semantic_query,
            field_mappings=field_mappings
        )
        
        vizql_query = await query_builder.build(mapped_query)
        
        # 验证筛选器
        filter_dict = vizql_query.filters[0]
        assert filter_dict["filterType"] == "DATE"
        assert filter_dict["periodType"] == "MONTHS"
        assert filter_dict["dateRangeType"] == "LASTN"
        assert filter_dict["rangeN"] == 3
    
    @pytest.mark.asyncio
    async def test_build_string_date_filter(self, query_builder):
        """测试构建 STRING 类型日期筛选（使用 DATEPARSE"""
        semantic_query = SemanticQuery(
            dimensions=[DimensionSpec(name="first_receive_dt")],
            measures=[MeasureSpec(
                name="first_receive_sale_num",
                aggregation=AggregationType.SUM
            )],
            filters=[FilterSpec(
                field="first_receive_dt",
                filter_type=FilterType.TIME_RANGE,
                time_filter=TimeFilterSpec(
                    mode=TimeFilterMode.ABSOLUTE_RANGE,
                    start_date="2023-01-01",
                    end_date="2023-12-31"
                )
            )]
        )
        
        field_mappings = {
            "first_receive_dt": FieldMapping(
                business_term="first_receive_dt",
                technical_field="first_receive_dt",
                confidence=1.0,
                mapping_source=MappingSource.EXACT_MATCH,
                data_type="STRING",
                date_format="yyyy-MM-dd"
            ),
            "first_receive_sale_num": FieldMapping(
                business_term="first_receive_sale_num",
                technical_field="first_receive_sale_num",
                confidence=1.0,
                mapping_source=MappingSource.EXACT_MATCH,
                data_type="REAL"
            )
        }
        
        mapped_query = MappedQuery(
            semantic_query=semantic_query,
            field_mappings=field_mappings
        )
        
        vizql_query = await query_builder.build(mapped_query)
        
        # 验证筛选器使用 DATEPARSE
        filter_dict = vizql_query.filters[0]
        assert filter_dict["filterType"] == "QUANTITATIVE_DATE"
        assert "calculation" in filter_dict["field"]
        assert "DATEPARSE" in filter_dict["field"]["calculation"]


# ============================================================================
# 3. VizQL 执行端到端测�?
# ============================================================================

class TestVizQLExecution:
    """VizQL 执行端到端测"""
    
    @pytest.mark.asyncio
    async def test_date_absolute_range(self, vizql_client, query_builder):
        """DATE 类型 + 绝对日期范围"""
        semantic_query = SemanticQuery(
            dimensions=[DimensionSpec(
                name="Ship Date",
                time_granularity=TimeGranularity.MONTH
            )],
            measures=[MeasureSpec(
                name="Discount",
                aggregation=AggregationType.SUM
            )],
            filters=[FilterSpec(
                field="Ship Date",
                filter_type=FilterType.TIME_RANGE,
                time_filter=TimeFilterSpec(
                    mode=TimeFilterMode.ABSOLUTE_RANGE,
                    start_date="2023-01-01",
                    end_date="2023-12-31"
                )
            )]
        )
        
        field_mappings = {
            "Ship Date": FieldMapping(
                business_term="Ship Date",
                technical_field="Ship Date",
                confidence=1.0,
                mapping_source=MappingSource.EXACT_MATCH,
                data_type="DATE"
            ),
            "Discount": FieldMapping(
                business_term="Discount",
                technical_field="Discount",
                confidence=1.0,
                mapping_source=MappingSource.EXACT_MATCH,
                data_type="REAL"
            )
        }
        
        mapped_query = MappedQuery(
            semantic_query=semantic_query,
            field_mappings=field_mappings
        )
        
        # 构建查询
        vizql_query = await query_builder.build(mapped_query)
        query_dict = vizql_query.to_dict()
        
        # 执行查询
        result = vizql_client.query_datasource(
            datasource_luid=DATE_DATASOURCE_LUID,
            query=query_dict,
            api_key=vizql_client._api_key,
            site=vizql_client._site
        )
        
        assert result is not None
        assert "data" in result
        print(f"[PASS] DATE + ABSOLUTE_RANGE: {len(result['data'])} rows")
    
    @pytest.mark.asyncio
    async def test_date_relative_lastn(self, vizql_client, query_builder):
        """DATE 类型 + 相对日期 (最近N个月)"""
        semantic_query = SemanticQuery(
            dimensions=[DimensionSpec(
                name="Ship Date",
                time_granularity=TimeGranularity.MONTH
            )],
            measures=[MeasureSpec(
                name="Discount",
                aggregation=AggregationType.SUM
            )],
            filters=[FilterSpec(
                field="Ship Date",
                filter_type=FilterType.TIME_RANGE,
                time_filter=TimeFilterSpec(
                    mode=TimeFilterMode.RELATIVE,
                    period_type=PeriodType.MONTHS,
                    date_range_type=DateRangeType.LASTN,
                    range_n=3
                )
            )]
        )
        
        field_mappings = {
            "Ship Date": FieldMapping(
                business_term="Ship Date",
                technical_field="Ship Date",
                confidence=1.0,
                mapping_source=MappingSource.EXACT_MATCH,
                data_type="DATE"
            ),
            "Discount": FieldMapping(
                business_term="Discount",
                technical_field="Discount",
                confidence=1.0,
                mapping_source=MappingSource.EXACT_MATCH,
                data_type="REAL"
            )
        }
        
        mapped_query = MappedQuery(
            semantic_query=semantic_query,
            field_mappings=field_mappings
        )
        
        vizql_query = await query_builder.build(mapped_query)
        query_dict = vizql_query.to_dict()
        
        result = vizql_client.query_datasource(
            datasource_luid=DATE_DATASOURCE_LUID,
            query=query_dict,
            api_key=vizql_client._api_key,
            site=vizql_client._site
        )
        
        assert result is not None
        print(f"[PASS] DATE + RELATIVE_LASTN: {len(result.get('data', []))} rows")
    
    @pytest.mark.asyncio
    async def test_date_relative_todate(self, vizql_client, query_builder):
        """DATE 类型 + 年初至今"""
        semantic_query = SemanticQuery(
            dimensions=[DimensionSpec(
                name="Ship Date",
                time_granularity=TimeGranularity.MONTH
            )],
            measures=[MeasureSpec(
                name="Discount",
                aggregation=AggregationType.SUM
            )],
            filters=[FilterSpec(
                field="Ship Date",
                filter_type=FilterType.TIME_RANGE,
                time_filter=TimeFilterSpec(
                    mode=TimeFilterMode.RELATIVE,
                    period_type=PeriodType.YEARS,
                    date_range_type=DateRangeType.TODATE
                )
            )]
        )
        
        field_mappings = {
            "Ship Date": FieldMapping(
                business_term="Ship Date",
                technical_field="Ship Date",
                confidence=1.0,
                mapping_source=MappingSource.EXACT_MATCH,
                data_type="DATE"
            ),
            "Discount": FieldMapping(
                business_term="Discount",
                technical_field="Discount",
                confidence=1.0,
                mapping_source=MappingSource.EXACT_MATCH,
                data_type="REAL"
            )
        }
        
        mapped_query = MappedQuery(
            semantic_query=semantic_query,
            field_mappings=field_mappings
        )
        
        vizql_query = await query_builder.build(mapped_query)
        query_dict = vizql_query.to_dict()
        
        result = vizql_client.query_datasource(
            datasource_luid=DATE_DATASOURCE_LUID,
            query=query_dict,
            api_key=vizql_client._api_key,
            site=vizql_client._site
        )
        
        assert result is not None
        print(f"[PASS] DATE + TODATE_YEAR: {len(result.get('data', []))} rows")
    
    @pytest.mark.asyncio
    async def test_string_dateparse_absolute(self, vizql_client, query_builder):
        """STRING 类型 + DATEPARSE + 绝对日期范围"""
        semantic_query = SemanticQuery(
            dimensions=[DimensionSpec(name="first_receive_dt")],
            measures=[MeasureSpec(
                name="first_receive_sale_num",
                aggregation=AggregationType.SUM
            )],
            filters=[FilterSpec(
                field="first_receive_dt",
                filter_type=FilterType.TIME_RANGE,
                time_filter=TimeFilterSpec(
                    mode=TimeFilterMode.ABSOLUTE_RANGE,
                    start_date="2023-01-01",
                    end_date="2023-12-31"
                )
            )]
        )
        
        field_mappings = {
            "first_receive_dt": FieldMapping(
                business_term="first_receive_dt",
                technical_field="first_receive_dt",
                confidence=1.0,
                mapping_source=MappingSource.EXACT_MATCH,
                data_type="STRING",
                date_format="yyyy-MM-dd"
            ),
            "first_receive_sale_num": FieldMapping(
                business_term="first_receive_sale_num",
                technical_field="first_receive_sale_num",
                confidence=1.0,
                mapping_source=MappingSource.EXACT_MATCH,
                data_type="REAL"
            )
        }
        
        mapped_query = MappedQuery(
            semantic_query=semantic_query,
            field_mappings=field_mappings
        )
        
        vizql_query = await query_builder.build(mapped_query)
        query_dict = vizql_query.to_dict()
        
        print(f"STRING DATEPARSE Query: {query_dict}")
        
        result = vizql_client.query_datasource(
            datasource_luid=STRING_DATASOURCE_LUID,
            query=query_dict,
            api_key=vizql_client._api_key,
            site=vizql_client._site
        )
        
        assert result is not None
        print(f"[PASS] STRING + DATEPARSE: {len(result.get('data', []))} rows")


# ============================================================================
# 4. 完整场景测试矩阵
# ============================================================================

class TestDateFilterScenarioMatrix:
    """日期筛选场景测试矩"""
    
    # DATE 类型测试场景
    DATE_SCENARIOS = [
        {
            "name": "ABSOLUTE_RANGE",
            "desc": "绝对日期范围 (2023�?",
            "time_filter": TimeFilterSpec(
                mode=TimeFilterMode.ABSOLUTE_RANGE,
                start_date="2023-01-01",
                end_date="2023-12-31"
            )
        },
        {
            "name": "RELATIVE_LASTN_MONTHS",
            "desc": "相对日期 (最�?个月)",
            "time_filter": TimeFilterSpec(
                mode=TimeFilterMode.RELATIVE,
                period_type=PeriodType.MONTHS,
                date_range_type=DateRangeType.LASTN,
                range_n=3
            )
        },
        {
            "name": "RELATIVE_LASTN_YEARS",
            "desc": "相对日期 (最�?�?",
            "time_filter": TimeFilterSpec(
                mode=TimeFilterMode.RELATIVE,
                period_type=PeriodType.YEARS,
                date_range_type=DateRangeType.LASTN,
                range_n=2
            )
        },
        {
            "name": "RELATIVE_TODATE_YEAR",
            "desc": "年初至今",
            "time_filter": TimeFilterSpec(
                mode=TimeFilterMode.RELATIVE,
                period_type=PeriodType.YEARS,
                date_range_type=DateRangeType.TODATE
            )
        },
        {
            "name": "RELATIVE_TODATE_QUARTER",
            "desc": "季初至今",
            "time_filter": TimeFilterSpec(
                mode=TimeFilterMode.RELATIVE,
                period_type=PeriodType.QUARTERS,
                date_range_type=DateRangeType.TODATE
            )
        },
        {
            "name": "RELATIVE_TODATE_MONTH",
            "desc": "月初至今",
            "time_filter": TimeFilterSpec(
                mode=TimeFilterMode.RELATIVE,
                period_type=PeriodType.MONTHS,
                date_range_type=DateRangeType.TODATE
            )
        },
        {
            "name": "RELATIVE_CURRENT_MONTH",
            "desc": "本月",
            "time_filter": TimeFilterSpec(
                mode=TimeFilterMode.RELATIVE,
                period_type=PeriodType.MONTHS,
                date_range_type=DateRangeType.CURRENT
            )
        },
        {
            "name": "RELATIVE_CURRENT_YEAR",
            "desc": "本年",
            "time_filter": TimeFilterSpec(
                mode=TimeFilterMode.RELATIVE,
                period_type=PeriodType.YEARS,
                date_range_type=DateRangeType.CURRENT
            )
        },
        {
            "name": "RELATIVE_LAST_MONTH",
            "desc": "上月",
            "time_filter": TimeFilterSpec(
                mode=TimeFilterMode.RELATIVE,
                period_type=PeriodType.MONTHS,
                date_range_type=DateRangeType.LAST
            )
        },
        {
            "name": "RELATIVE_LAST_YEAR",
            "desc": "去年",
            "time_filter": TimeFilterSpec(
                mode=TimeFilterMode.RELATIVE,
                period_type=PeriodType.YEARS,
                date_range_type=DateRangeType.LAST
            )
        },
    ]
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("scenario", DATE_SCENARIOS, ids=[s["name"] for s in DATE_SCENARIOS])
    async def test_date_type_scenarios(self, vizql_client, query_builder, scenario):
        """DATE 类型字段 - 参数化测试所有场"""
        semantic_query = SemanticQuery(
            dimensions=[DimensionSpec(
                name="Ship Date",
                time_granularity=TimeGranularity.MONTH
            )],
            measures=[MeasureSpec(
                name="Discount",
                aggregation=AggregationType.SUM
            )],
            filters=[FilterSpec(
                field="Ship Date",
                filter_type=FilterType.TIME_RANGE,
                time_filter=scenario["time_filter"]
            )]
        )
        
        field_mappings = {
            "Ship Date": FieldMapping(
                business_term="Ship Date",
                technical_field="Ship Date",
                confidence=1.0,
                mapping_source=MappingSource.EXACT_MATCH,
                data_type="DATE"
            ),
            "Discount": FieldMapping(
                business_term="Discount",
                technical_field="Discount",
                confidence=1.0,
                mapping_source=MappingSource.EXACT_MATCH,
                data_type="REAL"
            )
        }
        
        mapped_query = MappedQuery(
            semantic_query=semantic_query,
            field_mappings=field_mappings
        )
        
        vizql_query = await query_builder.build(mapped_query)
        query_dict = vizql_query.to_dict()
        
        result = vizql_client.query_datasource(
            datasource_luid=DATE_DATASOURCE_LUID,
            query=query_dict,
            api_key=vizql_client._api_key,
            site=vizql_client._site
        )
        
        assert result is not None
        row_count = len(result.get("data", []))
        print(f"[PASS] {scenario['name']}: {scenario['desc']} ({row_count} rows)")


# ============================================================================
# 运行入口
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
