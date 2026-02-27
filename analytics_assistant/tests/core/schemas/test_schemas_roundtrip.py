# -*- coding: utf-8 -*-
"""
Pydantic 模型序列化 round-trip 属性测试（Property 11）

验证 model_validate(m.model_dump()) == m 对核心模型成立。
覆盖模型：Field、DataModel、ExecuteResult、FieldCandidate、ValidationResult
"""

from hypothesis import given, settings, strategies as st

from analytics_assistant.src.core.schemas.data_model import Field, DataModel, LogicalTable
from analytics_assistant.src.core.schemas.execute_result import ExecuteResult, ColumnInfo
from analytics_assistant.src.core.schemas.field_candidate import FieldCandidate
from analytics_assistant.src.core.schemas.validation import (
    ValidationResult,
    ValidationErrorDetail,
    ValidationErrorType,
)


# ---- Hypothesis 策略 ----

# 非空文本策略
_non_empty_text = st.text(min_size=1, max_size=30, alphabet=st.characters(
    categories=("L", "N", "P"),
    exclude_characters="\x00",
))

_role_st = st.sampled_from(["DIMENSION", "MEASURE"])
_data_type_st = st.sampled_from(["STRING", "INTEGER", "REAL", "DATE", "DATETIME", "BOOLEAN"])

# Field 策略
field_strategy = st.builds(
    Field,
    name=_non_empty_text,
    caption=_non_empty_text,
    data_type=_data_type_st,
    role=_role_st,
    hidden=st.booleans(),
    description=st.one_of(st.none(), _non_empty_text),
)

# ColumnInfo 策略
column_info_strategy = st.builds(
    ColumnInfo,
    name=_non_empty_text,
    data_type=_data_type_st,
    is_dimension=st.booleans(),
    is_measure=st.booleans(),
    is_computation=st.booleans(),
)

# ExecuteResult 策略（使用固定 timestamp 避免 default_factory 干扰）
execute_result_strategy = st.builds(
    ExecuteResult,
    data=st.just([]),
    columns=st.lists(column_info_strategy, max_size=5),
    row_count=st.integers(min_value=0, max_value=1000),
    execution_time_ms=st.integers(min_value=0, max_value=10000),
    error=st.one_of(st.none(), _non_empty_text),
    query_id=st.one_of(st.none(), _non_empty_text),
    timestamp=_non_empty_text,
)

# FieldCandidate 策略
_confidence_st = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
field_candidate_strategy = st.builds(
    FieldCandidate,
    field_name=_non_empty_text,
    field_caption=_non_empty_text,
    role=st.sampled_from(["dimension", "measure", ""]),
    data_type=st.sampled_from(["string", "number", "date", ""]),
    confidence=_confidence_st,
    source=st.sampled_from(["full_schema", "rule_match", "embedding"]),
    rank=st.integers(min_value=1, max_value=100),
    match_type=st.sampled_from(["exact", "semantic"]),
)

# ValidationErrorDetail 策略
error_detail_strategy = st.builds(
    ValidationErrorDetail,
    error_type=st.sampled_from(list(ValidationErrorType)),
    field_path=_non_empty_text,
    message=_non_empty_text,
    suggestion=st.one_of(st.none(), _non_empty_text),
)

# ValidationResult 策略
validation_result_strategy = st.builds(
    ValidationResult,
    is_valid=st.booleans(),
    errors=st.lists(error_detail_strategy, max_size=3),
    warnings=st.lists(error_detail_strategy, max_size=3),
    auto_fixed=st.lists(_non_empty_text, max_size=3),
)

# DataModel 策略（简化版，不含 raw_metadata 避免复杂嵌套）
logical_table_strategy = st.builds(
    LogicalTable,
    id=_non_empty_text,
    name=_non_empty_text,
    field_count=st.integers(min_value=0, max_value=100),
)

data_model_strategy = st.builds(
    DataModel,
    datasource_id=_non_empty_text,
    datasource_name=st.one_of(st.none(), _non_empty_text),
    tables=st.lists(logical_table_strategy, max_size=3),
    fields=st.lists(field_strategy, max_size=5),
    raw_metadata=st.none(),
)


# ---- 属性测试 ----

class TestSchemaRoundTrip:
    """Pydantic 模型序列化 round-trip 属性测试。"""

    @given(field=field_strategy)
    @settings(max_examples=50)
    def test_field_roundtrip(self, field: Field):
        """Field 模型 dump → validate 后等价。"""
        dumped = field.model_dump()
        restored = Field.model_validate(dumped)
        assert restored == field

    @given(result=execute_result_strategy)
    @settings(max_examples=50)
    def test_execute_result_roundtrip(self, result: ExecuteResult):
        """ExecuteResult 模型 dump → validate 后等价。"""
        dumped = result.model_dump()
        restored = ExecuteResult.model_validate(dumped)
        assert restored == result

    @given(candidate=field_candidate_strategy)
    @settings(max_examples=50)
    def test_field_candidate_roundtrip(self, candidate: FieldCandidate):
        """FieldCandidate 模型 dump → validate 后等价。"""
        dumped = candidate.model_dump()
        restored = FieldCandidate.model_validate(dumped)
        assert restored == candidate

    @given(result=validation_result_strategy)
    @settings(max_examples=50)
    def test_validation_result_roundtrip(self, result: ValidationResult):
        """ValidationResult 模型 dump → validate 后等价。"""
        dumped = result.model_dump()
        restored = ValidationResult.model_validate(dumped)
        assert restored == result

    @given(model=data_model_strategy)
    @settings(max_examples=30)
    def test_data_model_roundtrip(self, model: DataModel):
        """DataModel 模型 dump → validate 后等价。"""
        dumped = model.model_dump()
        restored = DataModel.model_validate(dumped)
        # DataModel 有 _cached_schema_hash 私有属性，不参与序列化
        # 比较公开字段
        assert restored.datasource_id == model.datasource_id
        assert restored.fields == model.fields
        assert restored.tables == model.tables
        assert restored.datasource_name == model.datasource_name
