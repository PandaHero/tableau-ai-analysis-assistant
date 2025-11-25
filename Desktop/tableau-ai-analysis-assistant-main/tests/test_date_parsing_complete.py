"""
日期解析系统完整测试

测试所有核心功能
"""
import sys
from datetime import datetime
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tableau_assistant.src.models.metadata import Metadata, FieldMetadata
from tableau_assistant.src.models.question import TimeRange, TimeRangeType, RelativeType, PeriodType
from tableau_assistant.src.components.date_parser import DateParser


def test_metadata_reference_date():
    """测试 Metadata.get_reference_date()"""
    print("\n测试 1: Metadata.get_reference_date()")
    
    fields = [
        FieldMetadata(
            name="订单日期", fieldCaption="订单日期", role="dimension",
            dataType="DATE", valid_max_date="2024-12-31"
        ),
        FieldMetadata(
            name="发货日期", fieldCaption="发货日期", role="dimension",
            dataType="DATE", valid_max_date="2024-12-30"
        ),
    ]
    
    metadata = Metadata(
        datasource_luid="test-123", datasource_name="测试",
        fields=fields, field_count=len(fields)
    )
    
    # 测试1: 明确提到字段
    ref = metadata.get_reference_date(mentioned_field="订单日期")
    assert ref == "2024-12-31", f"期望 2024-12-31，实际 {ref}"
    print("  ✅ 明确字段测试通过")
    
    # 测试2: 未提到字段（使用最大）
    ref = metadata.get_reference_date()
    assert ref == "2024-12-31", f"期望 2024-12-31，实际 {ref}"
    print("  ✅ 最大日期测试通过")


def test_date_parser_absolute():
    """测试绝对时间解析"""
    print("\n测试 2: DateParser 绝对时间")
    
    parser = DateParser()
    
    # 年份
    start, end = parser.calculate_date_range(
        TimeRange(type=TimeRangeType.ABSOLUTE, value="2024")
    )
    assert start == "2024-01-01" and end == "2024-12-31"
    print("  ✅ 年份解析通过")
    
    # 季度
    start, end = parser.calculate_date_range(
        TimeRange(type=TimeRangeType.ABSOLUTE, value="2024-Q1")
    )
    assert start == "2024-01-01" and end == "2024-03-31"
    print("  ✅ 季度解析通过")
    
    # 日期范围
    start, end = parser.calculate_date_range(
        TimeRange(
            type=TimeRangeType.ABSOLUTE,
            start_date="2024-01-01",
            end_date="2024-03-31"
        )
    )
    assert start == "2024-01-01" and end == "2024-03-31"
    print("  ✅ 日期范围解析通过")


def test_date_parser_relative():
    """测试相对时间解析"""
    print("\n测试 3: DateParser 相对时间")
    
    parser = DateParser()
    ref_date = datetime(2024, 12, 31)
    
    # 最近3个月
    start, end = parser.calculate_date_range(
        TimeRange(
            type=TimeRangeType.RELATIVE,
            relative_type=RelativeType.LASTN,
            period_type=PeriodType.MONTHS,
            range_n=3
        ),
        ref_date
    )
    assert start <= end
    print(f"  ✅ 最近3个月: {start} to {end}")


def test_boundary_adjustment():
    """测试边界调整"""
    print("\n测试 4: 边界调整")
    
    parser = DateParser()
    
    # 超出边界
    start, end = parser.calculate_date_range(
        TimeRange(type=TimeRangeType.ABSOLUTE, value="2024"),
        max_date="2024-06-30"
    )
    assert end == "2024-06-30", f"应该调整为 2024-06-30，实际 {end}"
    print("  ✅ 边界调整通过")


def run_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("  日期解析系统测试")
    print("=" * 60)
    
    try:
        test_metadata_reference_date()
        test_date_parser_absolute()
        test_date_parser_relative()
        test_boundary_adjustment()
        
        print("\n" + "=" * 60)
        print("  🎉 所有测试通过！")
        print("=" * 60)
        return True
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
