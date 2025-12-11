"""
日期筛选全面测试

对不同数据类型（DATE、STRING）的日期字段进行全场景测试。

测试矩阵：
┌─────────────────┬──────────────────────┬──────────────────────┐
│ TimeFilterMode  │ DATE 类型字段        │ STRING 类型字段      │
├─────────────────┼──────────────────────┼──────────────────────┤
│ ABSOLUTE_RANGE  │ QUANTITATIVE_DATE    │ DATEPARSE + QUANT    │
│ RELATIVE-LASTN  │ DATE (RelativeDate)  │ DATEPARSE + QUANT    │
│ RELATIVE-TODATE │ DATE (RelativeDate)  │ DATEPARSE + QUANT    │
│ RELATIVE-CURRENT│ DATE (RelativeDate)  │ DATEPARSE + QUANT    │
│ SET             │ QUANT (转换为范围)   │ DATEPARSE + QUANT    │
└─────────────────┴──────────────────────┴──────────────────────┘

数据源：
- DATE 类型: 使用 .env 中的 DATASOURCE_LUID
- STRING 类型: b9f0e505-9d74-4f4d-a629-6d1095638eaa
"""

import os
import sys
import json
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

# 设置 stdout 编码
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# 加载环境变量
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# 导入项目模块
from tableau_assistant.src.bi_platforms.tableau.vizql_client import VizQLClient, VizQLClientConfig
from tableau_assistant.src.bi_platforms.tableau.auth import _get_tableau_context_from_env


# ═══════════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════════

DATE_TYPE_DATASOURCE_LUID = os.getenv("DATASOURCE_LUID", "e99f1815-b3b8-4660-9624-946ea028338f")
STRING_TYPE_DATASOURCE_LUID = "b9f0e505-9d74-4f4d-a629-6d1095638eaa"


# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════

def get_client_and_auth() -> Tuple[VizQLClient, str, Optional[str]]:
    """获取 VizQL 客户端和认证信息"""
    ctx = _get_tableau_context_from_env()
    
    if not ctx.get("api_key"):
        raise RuntimeError("认证失败，请检查 .env 配置")
    
    config = VizQLClientConfig(
        base_url=ctx["domain"],
        timeout=60,
        max_retries=3
    )
    
    client = VizQLClient(config=config)
    return client, ctx["api_key"], ctx.get("site")


def execute_query(
    client: VizQLClient, 
    datasource_luid: str, 
    query: Dict, 
    api_key: str, 
    site: str = None
) -> Dict:
    """执行查询并返回结果"""
    try:
        result = client.query_datasource(
            datasource_luid=datasource_luid,
            query=query,
            api_key=api_key,
            site=site
        )
        return {"success": True, "data": result.get("data", []), "row_count": len(result.get("data", []))}
    except Exception as e:
        return {"success": False, "error": str(e)[:500]}


def get_metadata(
    client: VizQLClient, 
    datasource_luid: str, 
    api_key: str, 
    site: str = None
) -> Dict:
    """获取元数据"""
    try:
        result = client.read_metadata(
            datasource_luid=datasource_luid,
            api_key=api_key,
            site=site
        )
        return {"success": True, "data": result.get("data", [])}
    except Exception as e:
        return {"success": False, "error": str(e)[:500]}


def find_date_field(metadata: Dict, data_type: str = "DATE") -> Optional[str]:
    """从元数据中找到指定类型的日期字段"""
    if not metadata.get("success"):
        return None
    
    for field in metadata.get("data", []):
        if field.get("dataType") in (data_type, "DATETIME"):
            return field.get("fieldCaption")
    
    # 如果找不到指定类型，尝试找名称包含 date 的字段
    for field in metadata.get("data", []):
        caption = field.get("fieldCaption", "").lower()
        if "date" in caption or "日期" in caption:
            return field.get("fieldCaption")
    
    return None


def find_measure_field(metadata: Dict) -> Optional[str]:
    """从元数据中找到度量字段"""
    if not metadata.get("success"):
        return None
    
    for field in metadata.get("data", []):
        if field.get("role") == "MEASURE" or field.get("dataType") in ("INTEGER", "REAL"):
            return field.get("fieldCaption")
    
    return None


# ═══════════════════════════════════════════════════════════════════════════
# 测试用例定义
# ═══════════════════════════════════════════════════════════════════════════

class DateFilterTestCase:
    """日期筛选测试用例"""
    
    def __init__(
        self,
        name: str,
        description: str,
        filter_config: Dict[str, Any],
        expected_filter_type: str,
        field_type: str = "DATE",  # DATE or STRING
    ):
        self.name = name
        self.description = description
        self.filter_config = filter_config
        self.expected_filter_type = expected_filter_type
        self.field_type = field_type


# DATE 类型字段测试用例
DATE_TYPE_TEST_CASES = [
    DateFilterTestCase(
        name="DATE_ABSOLUTE_RANGE",
        description="DATE + 绝对日期范围 (2023年)",
        filter_config={
            "filterType": "QUANTITATIVE_DATE",
            "quantitativeFilterType": "RANGE",
            "minDate": "2023-01-01",
            "maxDate": "2023-12-31"
        },
        expected_filter_type="QUANTITATIVE_DATE",
        field_type="DATE"
    ),
    DateFilterTestCase(
        name="DATE_RELATIVE_LASTN_MONTHS",
        description="DATE + 相对日期 (最近3个月)",
        filter_config={
            "filterType": "DATE",
            "periodType": "MONTHS",
            "dateRangeType": "LASTN",
            "rangeN": 3
        },
        expected_filter_type="DATE",
        field_type="DATE"
    ),
    DateFilterTestCase(
        name="DATE_RELATIVE_LASTN_YEARS",
        description="DATE + 相对日期 (最近2年)",
        filter_config={
            "filterType": "DATE",
            "periodType": "YEARS",
            "dateRangeType": "LASTN",
            "rangeN": 2
        },
        expected_filter_type="DATE",
        field_type="DATE"
    ),
    DateFilterTestCase(
        name="DATE_RELATIVE_TODATE_YEAR",
        description="DATE + 年初至今",
        filter_config={
            "filterType": "DATE",
            "periodType": "YEARS",
            "dateRangeType": "TODATE"
        },
        expected_filter_type="DATE",
        field_type="DATE"
    ),
    DateFilterTestCase(
        name="DATE_RELATIVE_TODATE_QUARTER",
        description="DATE + 季初至今",
        filter_config={
            "filterType": "DATE",
            "periodType": "QUARTERS",
            "dateRangeType": "TODATE"
        },
        expected_filter_type="DATE",
        field_type="DATE"
    ),
    DateFilterTestCase(
        name="DATE_RELATIVE_TODATE_MONTH",
        description="DATE + 月初至今",
        filter_config={
            "filterType": "DATE",
            "periodType": "MONTHS",
            "dateRangeType": "TODATE"
        },
        expected_filter_type="DATE",
        field_type="DATE"
    ),
    DateFilterTestCase(
        name="DATE_RELATIVE_CURRENT_MONTH",
        description="DATE + 本月",
        filter_config={
            "filterType": "DATE",
            "periodType": "MONTHS",
            "dateRangeType": "CURRENT"
        },
        expected_filter_type="DATE",
        field_type="DATE"
    ),
    DateFilterTestCase(
        name="DATE_RELATIVE_CURRENT_YEAR",
        description="DATE + 本年",
        filter_config={
            "filterType": "DATE",
            "periodType": "YEARS",
            "dateRangeType": "CURRENT"
        },
        expected_filter_type="DATE",
        field_type="DATE"
    ),
    DateFilterTestCase(
        name="DATE_RELATIVE_LAST_MONTH",
        description="DATE + 上月",
        filter_config={
            "filterType": "DATE",
            "periodType": "MONTHS",
            "dateRangeType": "LAST"
        },
        expected_filter_type="DATE",
        field_type="DATE"
    ),
    DateFilterTestCase(
        name="DATE_RELATIVE_LAST_YEAR",
        description="DATE + 去年",
        filter_config={
            "filterType": "DATE",
            "periodType": "YEARS",
            "dateRangeType": "LAST"
        },
        expected_filter_type="DATE",
        field_type="DATE"
    ),
]

# STRING 类型字段测试用例 (使用 DATEPARSE)
STRING_TYPE_TEST_CASES = [
    DateFilterTestCase(
        name="STRING_DATEPARSE_ABSOLUTE",
        description="STRING + DATEPARSE + 绝对日期范围",
        filter_config={
            "filterType": "QUANTITATIVE_DATE",
            "quantitativeFilterType": "RANGE",
            "minDate": "2023-01-01",
            "maxDate": "2023-12-31"
        },
        expected_filter_type="QUANTITATIVE_DATE",
        field_type="STRING"
    ),
    DateFilterTestCase(
        name="STRING_SET_DIRECT",
        description="STRING + SET 直接匹配",
        filter_config={
            "filterType": "SET",
            "values": ["2023-01-15", "2023-02-15", "2023-03-15"],
            "exclude": False
        },
        expected_filter_type="SET",
        field_type="STRING"
    ),
    DateFilterTestCase(
        name="STRING_MATCH_PREFIX",
        description="STRING + MATCH 前缀匹配 (2023-01开头)",
        filter_config={
            "filterType": "MATCH",
            "startsWith": "2023-01"
        },
        expected_filter_type="MATCH",
        field_type="STRING"
    ),
    DateFilterTestCase(
        name="STRING_MATCH_CONTAINS",
        description="STRING + MATCH 包含匹配",
        filter_config={
            "filterType": "MATCH",
            "contains": "2023"
        },
        expected_filter_type="MATCH",
        field_type="STRING"
    ),
]


# ═══════════════════════════════════════════════════════════════════════════
# 测试执行器
# ═══════════════════════════════════════════════════════════════════════════

class DateFilterTestRunner:
    """日期筛选测试执行器"""
    
    def __init__(self, client: VizQLClient, api_key: str, site: Optional[str]):
        self.client = client
        self.api_key = api_key
        self.site = site
        self.results: List[Dict] = []
    
    def run_test_case(
        self,
        test_case: DateFilterTestCase,
        datasource_luid: str,
        date_field: str,
        measure_field: str,
        use_dateparse: bool = False,
        date_format: str = "yyyy-MM-dd"
    ) -> Dict:
        """运行单个测试用例"""
        
        # 构建字段定义
        if use_dateparse:
            field_def = {"calculation": f"DATEPARSE('{date_format}', [{date_field}])"}
        else:
            field_def = {"fieldCaption": date_field}
        
        # 构建查询 - STRING 类型不使用 function
        if test_case.field_type == "STRING":
            # STRING 类型直接查询，不使用 MONTH 函数
            fields = [
                {"fieldCaption": date_field},
                {"fieldCaption": measure_field, "function": "SUM"}
            ]
        else:
            fields = [
                {"fieldCaption": date_field, "function": "MONTH"},
                {"fieldCaption": measure_field, "function": "SUM"}
            ]
        
        query = {
            "fields": fields,
            "filters": [
                {
                    "field": field_def,
                    **test_case.filter_config
                }
            ]
        }
        
        # 执行查询
        result = execute_query(self.client, datasource_luid, query, self.api_key, self.site)
        
        test_result = {
            "name": test_case.name,
            "description": test_case.description,
            "field_type": test_case.field_type,
            "expected_filter_type": test_case.expected_filter_type,
            "use_dateparse": use_dateparse,
            "query": query,
            "success": result.get("success", False),
            "row_count": result.get("row_count", 0),
            "error": result.get("error"),
        }
        
        self.results.append(test_result)
        return test_result
    
    def run_date_type_tests(self, datasource_luid: str) -> List[Dict]:
        """运行 DATE 类型字段的所有测试"""
        print("\n" + "=" * 70)
        print("DATE 类型字段测试")
        print("=" * 70)
        
        # 获取元数据
        metadata = get_metadata(self.client, datasource_luid, self.api_key, self.site)
        if not metadata.get("success"):
            print(f"[FAIL] 获取元数据失败: {metadata.get('error')}")
            return []
        
        date_field = find_date_field(metadata, "DATE")
        measure_field = find_measure_field(metadata)
        
        if not date_field:
            print("[FAIL] 未找到 DATE 类型字段")
            return []
        
        print(f"  日期字段: {date_field}")
        print(f"  度量字段: {measure_field}")
        print("-" * 70)
        
        results = []
        for test_case in DATE_TYPE_TEST_CASES:
            result = self.run_test_case(
                test_case, 
                datasource_luid, 
                date_field, 
                measure_field,
                use_dateparse=False
            )
            
            status = "[PASS]" if result["success"] else "[FAIL]"
            row_info = f"({result['row_count']} rows)" if result["success"] else ""
            error_info = f" - {result['error'][:100]}..." if result.get("error") else ""
            
            print(f"  {status} {test_case.name}: {test_case.description} {row_info}{error_info}")
            results.append(result)
        
        return results
    
    def run_string_type_tests(self, datasource_luid: str) -> List[Dict]:
        """运行 STRING 类型字段的所有测试"""
        print("\n" + "=" * 70)
        print("STRING 类型字段测试")
        print("=" * 70)
        
        # 获取元数据
        metadata = get_metadata(self.client, datasource_luid, self.api_key, self.site)
        if not metadata.get("success"):
            print(f"[FAIL] 获取元数据失败: {metadata.get('error')}")
            return []
        
        # 找 STRING 类型的日期字段
        string_date_field = None
        for field in metadata.get("data", []):
            if field.get("dataType") == "STRING":
                caption = field.get("fieldCaption", "").lower()
                if "date" in caption or "日期" in caption:
                    string_date_field = field.get("fieldCaption")
                    break
        
        if not string_date_field:
            # 使用第一个 STRING 字段
            for field in metadata.get("data", []):
                if field.get("dataType") == "STRING":
                    string_date_field = field.get("fieldCaption")
                    break
        
        measure_field = find_measure_field(metadata)
        
        if not string_date_field:
            print("[FAIL] 未找到 STRING 类型字段")
            return []
        
        print(f"  日期字段: {string_date_field}")
        print(f"  度量字段: {measure_field}")
        print("-" * 70)
        
        results = []
        
        # 测试 DATEPARSE + QUANTITATIVE_DATE
        print("\n  --- DATEPARSE + QUANTITATIVE_DATE 测试 ---")
        dateparse_test = DateFilterTestCase(
            name="STRING_DATEPARSE_QUANT",
            description="STRING + DATEPARSE + QUANTITATIVE_DATE",
            filter_config={
                "filterType": "QUANTITATIVE_DATE",
                "quantitativeFilterType": "RANGE",
                "minDate": "2023-01-01",
                "maxDate": "2023-12-31"
            },
            expected_filter_type="QUANTITATIVE_DATE",
            field_type="STRING"
        )
        result = self.run_test_case(
            dateparse_test,
            datasource_luid,
            string_date_field,
            measure_field,
            use_dateparse=True
        )
        status = "[PASS]" if result["success"] else "[FAIL]"
        print(f"  {status} {dateparse_test.name}: {dateparse_test.description}")
        results.append(result)
        
        # 测试直接 SET 和 MATCH
        print("\n  --- 直接 SET/MATCH 测试 ---")
        for test_case in STRING_TYPE_TEST_CASES[1:]:  # 跳过第一个 DATEPARSE 测试
            result = self.run_test_case(
                test_case,
                datasource_luid,
                string_date_field,
                measure_field,
                use_dateparse=False
            )
            
            status = "[PASS]" if result["success"] else "[FAIL]"
            row_info = f"({result['row_count']} rows)" if result["success"] else ""
            error_info = f" - {result['error'][:100]}..." if result.get("error") else ""
            
            print(f"  {status} {test_case.name}: {test_case.description} {row_info}{error_info}")
            results.append(result)
        
        return results
    
    def print_summary(self):
        """打印测试摘要"""
        print("\n" + "=" * 70)
        print("测试摘要")
        print("=" * 70)
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r["success"])
        failed = total - passed
        
        print(f"  总计: {total} 个测试")
        print(f"  通过: {passed} 个")
        print(f"  失败: {failed} 个")
        
        if failed > 0:
            print("\n  失败的测试:")
            for r in self.results:
                if not r["success"]:
                    print(f"    - {r['name']}: {r.get('error', 'Unknown error')[:100]}")
        
        print("=" * 70)


# ═══════════════════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════════════════

def main():
    """运行所有日期筛选测试"""
    print("=" * 70)
    print("日期筛选全面测试")
    print("=" * 70)
    print(f"DATE 类型数据源: {DATE_TYPE_DATASOURCE_LUID}")
    print(f"STRING 类型数据源: {STRING_TYPE_DATASOURCE_LUID}")
    
    # 获取客户端和认证
    try:
        client, api_key, site = get_client_and_auth()
        print("[PASS] 认证成功")
    except Exception as e:
        print(f"[FAIL] 认证失败: {e}")
        return
    
    # 创建测试执行器
    runner = DateFilterTestRunner(client, api_key, site)
    
    # 运行测试
    with client:
        # DATE 类型测试
        runner.run_date_type_tests(DATE_TYPE_DATASOURCE_LUID)
        
        # STRING 类型测试
        runner.run_string_type_tests(STRING_TYPE_DATASOURCE_LUID)
        
        # 打印摘要
        runner.print_summary()


if __name__ == "__main__":
    main()
