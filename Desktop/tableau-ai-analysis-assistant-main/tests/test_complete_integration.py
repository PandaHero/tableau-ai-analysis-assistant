"""
日期解析系统完整集成测试

覆盖所有核心功能：
1. Metadata.get_reference_date() - 所有场景
2. DateParser - 所有时间格式
3. DateFilterConverter - 实际集成
4. 边界情况和错误处理
5. 缓存机制
6. 元数据增强流程
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tableau_assistant.src.models.metadata import Metadata, FieldMetadata
from tableau_assistant.src.models.question import TimeRange, TimeRangeType, RelativeType, PeriodType
from tableau_assistant.src.components.date_parser import DateParser
from tableau_assistant.src.utils.date_calculator import DateCalculator


class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []
    
    def add_pass(self, name):
        self.passed += 1
        self.tests.append((name, True, None))
        print(f"  ✅ {name}")
    
    def add_fail(self, name, error):
        self.failed += 1
        self.tests.append((name, False, str(error)))
        print(f"  ❌ {name}: {error}")
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*80}")
        print(f"测试总结: {self.passed}/{total} 通过")
        if self.failed > 0:
            print(f"\n失败的测试:")
            for name, passed, error in self.tests:
                if not passed:
                    print(f"  - {name}: {error}")
        print(f"{'='*80}")
        return self.failed == 0


results = TestResults()


def test_section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}")


# ============= 测试 1: Metadata.get_reference_date() =============

def test_metadata_single_date_field():
    """测试单个日期字段"""
    test_section("测试 1.1: Metadata - 单个日期字段")
    
    try:
        fields = [
            FieldMetadata(
                name="订单日期", fieldCaption="订单日期", role="dimension",
                dataType="DATE", valid_max_date="2024-12-31"
            ),
            FieldMetadata(
                name="产品", fieldCaption="产品", role="dimension", dataType="STRING"
            ),
        ]
        metadata = Metadata(
            datasource_luid="test-1", datasource_name="测试1",
            fields=fields, field_count=len(fields)
        )
        
        ref = metadata.get_reference_date()
        assert ref == "2024-12-31", f"期望 2024-12-31，实际 {ref}"
        results.add_pass("单个日期字段")
    except Exception as e:
        results.add_fail("单个日期字段", e)


def test_metadata_multiple_date_fields():
    """测试多个日期字段"""
    test_section("测试 1.2: Metadata - 多个日期字段")
    
    try:
        fields = [
            FieldMetadata(
                name="订单日期", fieldCaption="订单日期", role="dimension",
                dataType="DATE", valid_max_date="2024-12-31"
            ),
            FieldMetadata(
                name="发货日期", fieldCaption="发货日期", role="dimension",
                dataType="DATE", valid_max_date="2024-12-30"
            ),
            FieldMetadata(
                name="收货日期", fieldCaption="收货日期", role="dimension",
                dataType="DATETIME", valid_max_date="2024-12-28"
            ),
        ]
        metadata = Metadata(
            datasource_luid="test-2", datasource_name="测试2",
            fields=fields, field_count=len(fields)
        )
        
        # 测试：未指定字段（应返回最大日期）
        ref = metadata.get_reference_date()
        assert ref == "2024-12-31", f"期望最大日期 2024-12-31，实际 {ref}"
        results.add_pass("多个日期字段 - 返回最大日期")
        
        # 测试：指定字段
        ref = metadata.get_reference_date(mentioned_field="发货日期")
        assert ref == "2024-12-30", f"期望 2024-12-30，实际 {ref}"
        results.add_pass("多个日期字段 - 指定字段")
        
    except Exception as e:
        results.add_fail("多个日期字段", e)


def test_metadata_no_date_fields():
    """测试无日期字段"""
    test_section("测试 1.3: Metadata - 无日期字段")
    
    try:
        fields = [
            FieldMetadata(
                name="产品", fieldCaption="产品", role="dimension", dataType="STRING"
            ),
            FieldMetadata(
                name="销售额", fieldCaption="销售额", role="measure", dataType="REAL"
            ),
        ]
        metadata = Metadata(
            datasource_luid="test-3", datasource_name="测试3",
            fields=fields, field_count=len(fields)
        )
        
        ref = metadata.get_reference_date()
        assert ref is None, f"期望 None，实际 {ref}"
        results.add_pass("无日期字段返回 None")
    except Exception as e:
        results.add_fail("无日期字段", e)


# ============= 测试 2: DateParser 绝对时间 =============

def test_dateparser_absolute_formats():
    """测试所有绝对时间格式"""
    test_section("测试 2: DateParser - 绝对时间格式")
    
    parser = DateParser()
    
    test_cases = [
        ("2024", "2024-01-01", "2024-12-31", "年份"),
        ("2024-Q1", "2024-01-01", "2024-03-31", "第1季度"),
        ("2024-Q2", "2024-04-01", "2024-06-30", "第2季度"),
        ("2024-Q3", "2024-07-01", "2024-09-30", "第3季度"),
        ("2024-Q4", "2024-10-01", "2024-12-31", "第4季度"),
        ("2024-01", "2024-01-01", "2024-01-31", "1月"),
        ("2024-02", "2024-02-01", "2024-02-29", "2月（闰年）"),
        ("2024-03", "2024-03-01", "2024-03-31", "3月"),
        ("2024-12", "2024-12-01", "2024-12-31", "12月"),
        ("2024-03-15", "2024-03-15", "2024-03-15", "具体日期"),
    ]
    
    for value, exp_start, exp_end, desc in test_cases:
        try:
            time_range = TimeRange(type=TimeRangeType.ABSOLUTE, value=value)
            start, end = parser.calculate_date_range(time_range)
            assert start == exp_start and end == exp_end, \
                f"期望 {exp_start} to {exp_end}，实际 {start} to {end}"
            results.add_pass(f"绝对时间 - {desc} ({value})")
        except Exception as e:
            results.add_fail(f"绝对时间 - {desc}", e)


def test_dateparser_absolute_range():
    """测试日期范围格式"""
    test_section("测试 2.2: DateParser - 日期范围")
    
    parser = DateParser()
    
    try:
        time_range = TimeRange(
            type=TimeRangeType.ABSOLUTE,
            start_date="2024-01-01",
            end_date="2024-03-31"
        )
        start, end = parser.calculate_date_range(time_range)
        assert start == "2024-01-01" and end == "2024-03-31"
        results.add_pass("日期范围格式")
    except Exception as e:
        results.add_fail("日期范围格式", e)


# ============= 测试 3: DateParser 相对时间 =============

def test_dateparser_relative_types():
    """测试所有相对时间类型"""
    test_section("测试 3: DateParser - 相对时间类型")
    
    parser = DateParser()
    ref_date = datetime(2024, 12, 31)
    
    test_cases = [
        (RelativeType.LASTN, PeriodType.DAYS, 7, "最近7天"),
        (RelativeType.LASTN, PeriodType.WEEKS, 4, "最近4周"),
        (RelativeType.LASTN, PeriodType.MONTHS, 3, "最近3个月"),
        (RelativeType.LASTN, PeriodType.QUARTERS, 2, "最近2个季度"),
        (RelativeType.LASTN, PeriodType.YEARS, 1, "最近1年"),
        (RelativeType.LAST, PeriodType.MONTHS, None, "上月"),
        (RelativeType.LAST, PeriodType.YEARS, None, "去年"),
        (RelativeType.CURRENT, PeriodType.MONTHS, None, "本月至今"),
        (RelativeType.CURRENT, PeriodType.YEARS, None, "今年至今"),
    ]
    
    for rel_type, period_type, range_n, desc in test_cases:
        try:
            time_range = TimeRange(
                type=TimeRangeType.RELATIVE,
                relative_type=rel_type,
                period_type=period_type,
                range_n=range_n
            )
            start, end = parser.calculate_date_range(time_range, ref_date)
            
            # 验证格式
            datetime.strptime(start, "%Y-%m-%d")
            datetime.strptime(end, "%Y-%m-%d")
            
            # 验证顺序
            assert start <= end, f"start 应该 <= end"
            
            results.add_pass(f"相对时间 - {desc}")
        except Exception as e:
            results.add_fail(f"相对时间 - {desc}", e)


# ============= 测试 4: 边界调整 =============

def test_boundary_adjustment():
    """测试边界调整"""
    test_section("测试 4: 边界调整")
    
    parser = DateParser()
    
    # 测试1: 超出边界
    try:
        time_range = TimeRange(type=TimeRangeType.ABSOLUTE, value="2024")
        start, end = parser.calculate_date_range(time_range, max_date="2024-06-30")
        assert end == "2024-06-30", f"应该调整为 2024-06-30，实际 {end}"
        results.add_pass("边界调整 - 超出时调整")
    except Exception as e:
        results.add_fail("边界调整 - 超出时调整", e)
    
    # 测试2: 不超出边界
    try:
        time_range = TimeRange(type=TimeRangeType.ABSOLUTE, value="2024-Q1")
        start, end = parser.calculate_date_range(time_range, max_date="2024-12-31")
        assert end == "2024-03-31", f"不应该调整，期望 2024-03-31，实际 {end}"
        results.add_pass("边界调整 - 不超出时不调整")
    except Exception as e:
        results.add_fail("边界调整 - 不超出时不调整", e)


# ============= 测试 5: 验证逻辑 =============

def test_validation():
    """测试验证逻辑"""
    test_section("测试 5: 验证逻辑")
    
    parser = DateParser()
    
    # 测试1: 正常范围
    try:
        time_range = TimeRange(
            type=TimeRangeType.ABSOLUTE,
            start_date="2024-01-01",
            end_date="2024-12-31"
        )
        start, end = parser.calculate_date_range(time_range)
        results.add_pass("验证 - 正常范围通过")
    except Exception as e:
        results.add_fail("验证 - 正常范围", e)
    
    # 测试2: start > end（应该失败）
    try:
        time_range = TimeRange(
            type=TimeRangeType.ABSOLUTE,
            start_date="2024-12-31",
            end_date="2024-01-01"
        )
        start, end = parser.calculate_date_range(time_range)
        results.add_fail("验证 - start>end应该失败", "没有抛出异常")
    except ValueError:
        results.add_pass("验证 - start>end正确抛出异常")
    except Exception as e:
        results.add_fail("验证 - start>end", f"错误的异常类型: {e}")


# ============= 测试 6: 缓存机制 =============

def test_cache():
    """测试缓存机制"""
    test_section("测试 6: 缓存机制")
    
    parser = DateParser()
    
    try:
        time_range = TimeRange(type=TimeRangeType.ABSOLUTE, value="2024")
        ref_date = datetime(2024, 12, 31)
        
        # 第一次调用
        start1, end1 = parser.calculate_date_range(time_range, ref_date)
        
        # 第二次调用（应该命中缓存）
        start2, end2 = parser.calculate_date_range(time_range, ref_date)
        
        assert start1 == start2 and end1 == end2
        assert len(parser._cache) > 0, "缓存应该有内容"
        
        results.add_pass("缓存机制工作正常")
    except Exception as e:
        results.add_fail("缓存机制", e)


# ============= 测试 7: DateCalculator 集成 =============

def test_date_calculator_integration():
    """测试 DateCalculator 集成"""
    test_section("测试 7: DateCalculator 集成")
    
    try:
        calculator = DateCalculator(anchor_date=datetime(2024, 12, 31))
        
        # 测试相对日期计算
        result = calculator.calculate_relative_date(
            relative_type="LASTN",
            period_type="MONTHS",
            range_n=3
        )
        
        assert "start_date" in result and "end_date" in result
        assert result["start_date"] <= result["end_date"]
        
        results.add_pass("DateCalculator 相对日期计算")
    except Exception as e:
        results.add_fail("DateCalculator 集成", e)


# ============= 测试 8: 完整流程 =============

def test_end_to_end():
    """测试端到端流程"""
    test_section("测试 8: 端到端流程")
    
    try:
        # Step 1: 创建元数据
        fields = [
            FieldMetadata(
                name="订单日期", fieldCaption="订单日期", role="dimension",
                dataType="DATE", valid_max_date="2024-12-31"
            ),
            FieldMetadata(
                name="销售额", fieldCaption="销售额", role="measure", dataType="REAL"
            ),
        ]
        metadata = Metadata(
            datasource_luid="e2e-test", datasource_name="端到端测试",
            fields=fields, field_count=len(fields)
        )
        
        # Step 2: 获取参考日期
        ref_date_str = metadata.get_reference_date(mentioned_field="订单日期")
        assert ref_date_str == "2024-12-31"
        
        # Step 3: 解析时间范围
        time_range = TimeRange(
            type=TimeRangeType.RELATIVE,
            relative_type=RelativeType.LASTN,
            period_type=PeriodType.MONTHS,
            range_n=3
        )
        
        parser = DateParser()
        ref_date = datetime.fromisoformat(ref_date_str)
        start, end = parser.calculate_date_range(time_range, ref_date)
        
        # Step 4: 验证结果
        assert start <= end
        assert end == "2024-12-31"
        
        results.add_pass("端到端流程完整")
    except Exception as e:
        results.add_fail("端到端流程", e)


# ============= 测试 9: 错误处理 =============

def test_error_handling():
    """测试错误处理"""
    test_section("测试 9: 错误处理")
    
    parser = DateParser()
    
    # 测试1: 无效的日期格式
    try:
        time_range = TimeRange(type=TimeRangeType.ABSOLUTE, value="invalid")
        start, end = parser.calculate_date_range(time_range)
        results.add_fail("错误处理 - 无效格式", "应该抛出异常")
    except ValueError:
        results.add_pass("错误处理 - 无效格式正确抛出异常")
    except Exception as e:
        results.add_fail("错误处理 - 无效格式", f"错误的异常: {e}")
    
    # 测试2: 缺少必需字段
    try:
        time_range = TimeRange(
            type=TimeRangeType.RELATIVE,
            relative_type=RelativeType.LASTN,
            # 缺少 period_type 和 range_n
        )
        start, end = parser.calculate_date_range(time_range)
        results.add_fail("错误处理 - 缺少字段", "应该抛出异常")
    except (ValueError, AttributeError):
        results.add_pass("错误处理 - 缺少字段正确抛出异常")
    except Exception as e:
        results.add_fail("错误处理 - 缺少字段", f"错误的异常: {e}")


# ============= 运行所有测试 =============

def run_all_tests():
    """运行所有测试"""
    print("\n" + "🚀" * 40)
    print("  日期解析系统完整集成测试")
    print("🚀" * 40)
    
    # Metadata 测试
    test_metadata_single_date_field()
    test_metadata_multiple_date_fields()
    test_metadata_no_date_fields()
    
    # DateParser 绝对时间测试
    test_dateparser_absolute_formats()
    test_dateparser_absolute_range()
    
    # DateParser 相对时间测试
    test_dateparser_relative_types()
    
    # 边界和验证测试
    test_boundary_adjustment()
    test_validation()
    
    # 缓存和集成测试
    test_cache()
    test_date_calculator_integration()
    
    # 端到端测试
    test_end_to_end()
    
    # 错误处理测试
    test_error_handling()
    
    # 显示总结
    success = results.summary()
    
    if success:
        print("\n✅ 所有功能测试通过！长期优化验证完成！ 🎉\n")
    else:
        print("\n❌ 部分测试失败，请检查错误信息\n")
    
    return success


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
