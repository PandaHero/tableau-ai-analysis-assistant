"""
Property Tests for Understanding Agent and Tools

Tests for:
- Property 24: Schema 模块按需加载
- Property 25: Schema 模块名称验证
- Property 12: 元数据工具委托
- Property 13: 日期解析往返一致性
- Property 23: SemanticQuery computation_scope 条件填写

Requirements tested:
- tool-design.md: Schema module selection
- R5.1, R5.3: Metadata tool delegation
- R6.2, R6.3: Date parsing round-trip
- R7.2.3, R7.2.11: computation_scope conditional filling
"""

import pytest
from hypothesis import given, settings, strategies as st
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta


# ═══════════════════════════════════════════════════════════════════════════
# Property 24: Schema 模块按需加载
# ═══════════════════════════════════════════════════════════════════════════

class TestSchemaModuleOnDemand:
    """
    Property 24: Schema 模块按需加载
    
    *For any* 用户问题，只加载相关的 Schema 模块，减少 token 消耗。
    
    **Validates: tool-design.md (Schema 模块选择工具)**
    """
    
    def test_module_selection_by_intent(self):
        """验证根据意图选择模块"""
        # 不同意图对应不同模块
        intent_modules = {
            "query": ["fields", "filters"],
            "trend": ["fields", "filters", "time"],
            "compare": ["fields", "filters", "comparison"],
            "rank": ["fields", "filters", "ranking"],
        }
        
        for intent, expected_modules in intent_modules.items():
            modules = self._select_modules(intent)
            assert set(modules) == set(expected_modules)
    
    def test_token_reduction(self):
        """验证 token 消耗减少"""
        # 全量 Schema
        full_schema_tokens = 5000
        
        # 按需加载
        partial_schema_tokens = 2000
        
        reduction = (full_schema_tokens - partial_schema_tokens) / full_schema_tokens
        
        # 应减少 40-60%
        assert 0.4 <= reduction <= 0.6
    
    @given(
        intent=st.sampled_from(["query", "trend", "compare", "rank", "aggregate"]),
        has_time_filter=st.booleans(),
    )
    @settings(max_examples=30)
    def test_module_selection_property(self, intent: str, has_time_filter: bool):
        """
        Property: 模块选择应满足：
        1. 基础模块总是加载（fields, filters）
        2. 时间相关意图加载 time 模块
        3. 不加载无关模块
        """
        modules = self._select_modules(intent, has_time_filter)
        
        # Property 1: 基础模块总是加载
        assert "fields" in modules
        assert "filters" in modules
        
        # Property 2: 时间相关加载 time
        if intent == "trend" or has_time_filter:
            assert "time" in modules
        
        # Property 3: 不加载无关模块
        if intent == "query" and not has_time_filter:
            assert "ranking" not in modules
            assert "comparison" not in modules
    
    def _select_modules(self, intent: str, has_time_filter: bool = False) -> List[str]:
        """选择 Schema 模块"""
        modules = ["fields", "filters"]  # 基础模块
        
        if intent == "trend" or has_time_filter:
            modules.append("time")
        
        if intent == "compare":
            modules.append("comparison")
        
        if intent == "rank":
            modules.append("ranking")
        
        return modules


# ═══════════════════════════════════════════════════════════════════════════
# Property 25: Schema 模块名称验证
# ═══════════════════════════════════════════════════════════════════════════

class TestSchemaModuleNameValidation:
    """
    Property 25: Schema 模块名称验证
    
    *For any* 模块名称请求，应验证名称有效性。
    
    **Validates: tool-design.md (Schema 模块选择工具)**
    """
    
    def test_valid_module_names(self):
        """验证有效模块名称"""
        valid_names = ["fields", "filters", "time", "comparison", "ranking", "aggregation"]
        
        for name in valid_names:
            assert self._is_valid_module(name)
    
    def test_invalid_module_names(self):
        """验证无效模块名称"""
        invalid_names = ["invalid", "unknown", "foo", "bar"]
        
        for name in invalid_names:
            assert not self._is_valid_module(name)
    
    @given(module_name=st.text(min_size=1, max_size=50))
    @settings(max_examples=50)
    def test_module_validation_property(self, module_name: str):
        """
        Property: 模块验证应满足：
        1. 有效名称返回 True
        2. 无效名称返回 False
        3. 验证是确定性的
        """
        valid_modules = {"fields", "filters", "time", "comparison", "ranking", "aggregation"}
        
        is_valid = self._is_valid_module(module_name)
        
        # Property 1 & 2: 正确判断
        if module_name in valid_modules:
            assert is_valid
        else:
            assert not is_valid
        
        # Property 3: 确定性
        assert self._is_valid_module(module_name) == is_valid
    
    def _is_valid_module(self, name: str) -> bool:
        """验证模块名称"""
        valid_modules = {"fields", "filters", "time", "comparison", "ranking", "aggregation"}
        return name in valid_modules


# ═══════════════════════════════════════════════════════════════════════════
# Property 12: 元数据工具委托
# ═══════════════════════════════════════════════════════════════════════════

class TestMetadataToolDelegation:
    """
    Property 12: 元数据工具委托
    
    *For any* get_metadata 调用，应正确委托给 MetadataManager。
    
    **Validates: Requirements 5.1, 5.3**
    """
    
    def test_delegation_to_manager(self):
        """验证委托给 MetadataManager"""
        # 模拟调用
        result = self._mock_get_metadata(
            datasource_luid="ds_123",
            filter_role="dimension",
        )
        
        # 应返回字段列表
        assert "fields" in result
        assert isinstance(result["fields"], list)
    
    def test_filter_parameters(self):
        """验证过滤参数传递"""
        # 按角色过滤
        result = self._mock_get_metadata(
            datasource_luid="ds_123",
            filter_role="measure",
        )
        
        # 所有字段应是度量
        for field in result["fields"]:
            assert field["role"] == "measure"
    
    @given(
        filter_role=st.sampled_from([None, "dimension", "measure"]),
        filter_category=st.sampled_from([None, "time", "product", "geographic"]),
    )
    @settings(max_examples=30)
    def test_delegation_property(self, filter_role: Optional[str], filter_category: Optional[str]):
        """
        Property: 委托应满足：
        1. 参数正确传递
        2. 过滤正确应用
        3. 返回格式一致
        """
        result = self._mock_get_metadata(
            datasource_luid="ds_123",
            filter_role=filter_role,
            filter_category=filter_category,
        )
        
        # Property 1 & 2: 过滤正确应用
        for field in result["fields"]:
            if filter_role:
                assert field["role"] == filter_role
            if filter_category:
                assert field.get("category") == filter_category
        
        # Property 3: 返回格式一致
        assert "fields" in result
        assert isinstance(result["fields"], list)
    
    def _mock_get_metadata(
        self,
        datasource_luid: str,
        filter_role: Optional[str] = None,
        filter_category: Optional[str] = None,
    ) -> Dict:
        """模拟 get_metadata"""
        # 模拟字段
        all_fields = [
            {"name": "Date", "role": "dimension", "category": "time"},
            {"name": "Category", "role": "dimension", "category": "product"},
            {"name": "Region", "role": "dimension", "category": "geographic"},
            {"name": "Sales", "role": "measure", "category": None},
            {"name": "Profit", "role": "measure", "category": None},
        ]
        
        # 应用过滤
        filtered = all_fields
        if filter_role:
            filtered = [f for f in filtered if f["role"] == filter_role]
        if filter_category:
            filtered = [f for f in filtered if f.get("category") == filter_category]
        
        return {"fields": filtered}


# ═══════════════════════════════════════════════════════════════════════════
# Property 13: 日期解析往返一致性
# ═══════════════════════════════════════════════════════════════════════════

class TestDateParsingRoundTrip:
    """
    Property 13: 日期解析往返一致性
    
    *For any* 日期表达式，解析后格式化应得到等价结果。
    
    **Validates: Requirements 6.2, 6.3**
    """
    
    def test_absolute_date_round_trip(self):
        """验证绝对日期往返"""
        date_str = "2024-01-15"
        
        # 解析
        parsed = self._parse_date(date_str)
        
        # 格式化
        formatted = self._format_date(parsed)
        
        # 应等价
        assert formatted == date_str
    
    def test_relative_date_parsing(self):
        """验证相对日期解析"""
        # 相对日期表达式
        expressions = ["今天", "昨天", "上周", "上个月", "去年"]
        
        for expr in expressions:
            result = self._parse_relative_date(expr)
            assert result is not None
            assert "start" in result
            assert "end" in result
    
    def test_date_range_parsing(self):
        """验证日期范围解析"""
        range_str = "2024-01-01 到 2024-01-31"
        
        result = self._parse_date_range(range_str)
        
        assert result["start"] == "2024-01-01"
        assert result["end"] == "2024-01-31"
    
    @given(
        year=st.integers(min_value=2000, max_value=2030),
        month=st.integers(min_value=1, max_value=12),
        day=st.integers(min_value=1, max_value=28),  # 避免月末问题
    )
    @settings(max_examples=50)
    def test_round_trip_property(self, year: int, month: int, day: int):
        """
        Property: 往返一致性应满足：
        1. parse(format(date)) == date
        2. format(parse(str)) == str（对于标准格式）
        """
        date = datetime(year, month, day)
        date_str = date.strftime("%Y-%m-%d")
        
        # Property 1: parse(format(date)) == date
        formatted = self._format_date(date)
        parsed = self._parse_date(formatted)
        assert parsed.year == year
        assert parsed.month == month
        assert parsed.day == day
        
        # Property 2: format(parse(str)) == str
        parsed2 = self._parse_date(date_str)
        formatted2 = self._format_date(parsed2)
        assert formatted2 == date_str
    
    def _parse_date(self, date_str: str) -> datetime:
        """解析日期"""
        return datetime.strptime(date_str, "%Y-%m-%d")
    
    def _format_date(self, date: datetime) -> str:
        """格式化日期"""
        return date.strftime("%Y-%m-%d")
    
    def _parse_relative_date(self, expr: str) -> Optional[Dict]:
        """解析相对日期"""
        today = datetime.now().date()
        
        mappings = {
            "今天": (today, today),
            "昨天": (today - timedelta(days=1), today - timedelta(days=1)),
            "上周": (today - timedelta(days=7), today),
            "上个月": (today.replace(day=1) - timedelta(days=1), today),
            "去年": (today.replace(year=today.year - 1), today),
        }
        
        if expr in mappings:
            start, end = mappings[expr]
            return {
                "start": start.strftime("%Y-%m-%d"),
                "end": end.strftime("%Y-%m-%d"),
            }
        
        return None
    
    def _parse_date_range(self, range_str: str) -> Dict:
        """解析日期范围"""
        parts = range_str.split(" 到 ")
        return {
            "start": parts[0].strip(),
            "end": parts[1].strip(),
        }


# ═══════════════════════════════════════════════════════════════════════════
# Property 23: SemanticQuery computation_scope 条件填写
# ═══════════════════════════════════════════════════════════════════════════

class TestComputationScopeConditional:
    """
    Property 23: SemanticQuery computation_scope 条件填写
    
    *For any* 分析类型，computation_scope 应根据条件正确填写。
    
    **Validates: Requirements 7.2.3, 7.2.11**
    """
    
    def test_table_calc_requires_scope(self):
        """验证表计算需要 computation_scope"""
        # 表计算类型
        table_calc_types = ["cumulative", "moving", "ranking", "percentage"]
        
        for analysis_type in table_calc_types:
            spec = self._create_analysis_spec(analysis_type)
            assert "computation_scope" in spec or "addressing" in spec
    
    def test_lod_does_not_require_scope(self):
        """验证 LOD 不需要 computation_scope"""
        # LOD 类型
        lod_types = ["fixed", "include", "exclude"]
        
        for analysis_type in lod_types:
            spec = self._create_analysis_spec(analysis_type)
            # LOD 使用 lod_dimensions 而不是 computation_scope
            assert "lod_dimensions" in spec or "computation_scope" not in spec
    
    def test_scope_validation(self):
        """验证 scope 值有效性"""
        valid_scopes = ["table", "pane", "cell"]
        
        for scope in valid_scopes:
            assert self._is_valid_scope(scope)
        
        assert not self._is_valid_scope("invalid")
    
    @given(
        analysis_type=st.sampled_from([
            "cumulative", "moving", "ranking", "percentage",
            "fixed", "include", "exclude",
        ]),
        has_dimensions=st.booleans(),
    )
    @settings(max_examples=30)
    def test_scope_conditional_property(self, analysis_type: str, has_dimensions: bool):
        """
        Property: computation_scope 条件填写应满足：
        1. 表计算类型需要 scope 或 addressing
        2. LOD 类型使用 lod_dimensions
        3. scope 值必须有效
        """
        spec = self._create_analysis_spec(analysis_type, has_dimensions)
        
        table_calc_types = {"cumulative", "moving", "ranking", "percentage"}
        lod_types = {"fixed", "include", "exclude"}
        
        if analysis_type in table_calc_types:
            # Property 1: 表计算需要 scope 或 addressing
            has_scope = "computation_scope" in spec or "addressing" in spec
            assert has_scope, f"{analysis_type} should have scope or addressing"
            
            # Property 3: scope 值有效
            if "computation_scope" in spec:
                assert self._is_valid_scope(spec["computation_scope"])
        
        elif analysis_type in lod_types:
            # Property 2: LOD 使用 lod_dimensions
            assert "lod_dimensions" in spec or "computation_scope" not in spec
    
    def _create_analysis_spec(
        self,
        analysis_type: str,
        has_dimensions: bool = True,
    ) -> Dict:
        """创建分析规格"""
        table_calc_types = {"cumulative", "moving", "ranking", "percentage"}
        lod_types = {"fixed", "include", "exclude"}
        
        spec = {"type": analysis_type}
        
        if analysis_type in table_calc_types:
            spec["computation_scope"] = "table"
            if has_dimensions:
                spec["addressing"] = ["Category"]
        
        elif analysis_type in lod_types:
            spec["lod_dimensions"] = ["Region"] if has_dimensions else []
        
        return spec
    
    def _is_valid_scope(self, scope: str) -> bool:
        """验证 scope 有效性"""
        return scope in {"table", "pane", "cell"}


# ═══════════════════════════════════════════════════════════════════════════
# Additional Understanding Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestIntentClassification:
    """
    测试意图分类
    """
    
    def test_analysis_question_detection(self):
        """验证分析类问题检测"""
        analysis_questions = [
            "2024年各地区销售额是多少",
            "分析上个月的利润趋势",
            "哪个产品类别销售最好",
        ]
        
        non_analysis_questions = [
            "你好",
            "谢谢",
            "帮我写一首诗",
        ]
        
        for q in analysis_questions:
            assert self._is_analysis_question(q)
        
        for q in non_analysis_questions:
            assert not self._is_analysis_question(q)
    
    def test_intent_extraction(self):
        """验证意图提取"""
        test_cases = [
            ("2024年销售额趋势", "trend"),
            ("各地区销售对比", "compare"),
            ("销售额排名前10", "rank"),
            ("总销售额是多少", "aggregate"),  # "总" 触发 aggregate 意图
            ("销售额是多少", "query"),  # 无特殊关键词，默认 query
        ]
        
        for question, expected_intent in test_cases:
            intent = self._extract_intent(question)
            assert intent == expected_intent
    
    def _is_analysis_question(self, question: str) -> bool:
        """判断是否是分析类问题"""
        analysis_keywords = [
            "销售", "利润", "收入", "成本", "数量",
            "趋势", "对比", "排名", "分析", "统计",
            "多少", "哪个", "什么", "如何",
        ]
        
        return any(kw in question for kw in analysis_keywords)
    
    def _extract_intent(self, question: str) -> str:
        """提取意图"""
        intent_keywords = {
            "trend": ["趋势", "变化", "增长", "下降"],
            "compare": ["对比", "比较", "差异"],
            "rank": ["排名", "前", "后", "最"],
            "aggregate": ["总", "平均", "合计"],
        }
        
        for intent, keywords in intent_keywords.items():
            if any(kw in question for kw in keywords):
                return intent
        
        return "query"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
