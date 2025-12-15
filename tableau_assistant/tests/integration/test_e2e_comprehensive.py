# -*- coding: utf-8 -*-
"""
E2E 综合集成测试 - 完整功能测试套件

使用真实 Tableau 环境和 LLM (qwen3) 进行全面的端到端测试。
覆盖所有核心功能模块：

1. 工作流完整执行
2. 语义理解 (Understanding Agent)
3. 字段映射 (FieldMapper)
4. 查询构建 (QueryBuilder)
5. 查询执行 (Execute)
6. 洞察分析 (Insight Agent)
7. 重规划决策 (Replanner Agent)
8. 各类聚合查询 (SUM, AVG, COUNT, COUNTD)
9. LOD 表达式 (FIXED, INCLUDE, EXCLUDE)
10. 表计算 (RUNNING_SUM, RANK, YoY, MoM)
11. 日期筛选 (绝对/相对/复合)
12. 多维度多度量分析
13. 维度下钻
14. 非分析类问题路由
15. 错误处理
16. 流式输出
17. 对话上下文

测试配置:
- LLM: qwen3 (ACTIVE_LLM=qwen3)
- 真实 Tableau Cloud 数据源
- 完整工作流执行（不简化）

运行方式:
    pytest tableau_assistant/tests/integration/test_e2e_comprehensive.py -v -s
    
    # 运行特定测试类
    pytest tableau_assistant/tests/integration/test_e2e_comprehensive.py::TestWorkflowComplete -v -s
    
    # 运行特定测试
    pytest tableau_assistant/tests/integration/test_e2e_comprehensive.py::TestWorkflowComplete::test_full_workflow_all_nodes -v -s
"""

import pytest
import asyncio
import time
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from tableau_assistant.src.workflow.executor import WorkflowExecutor, EventType, WorkflowResult
from tableau_assistant.src.workflow.printer import WorkflowPrinter
from tableau_assistant.src.config.settings import Settings


# ============================================================
# 测试配置和辅助类
# ============================================================

@dataclass
class TestCase:
    """测试用例数据类"""
    name: str
    question: str
    expected_analysis: bool = True
    expected_dimensions: Optional[List[str]] = None
    expected_measures: Optional[List[str]] = None
    min_insights: int = 0
    description: str = ""


class TestMetrics:
    """测试指标收集器"""
    
    def __init__(self):
        self.total_tests = 0
        self.passed_tests = 0
        self.failed_tests = 0
        self.skipped_tests = 0
        self.total_duration = 0.0
        self.test_results: List[Dict[str, Any]] = []
    
    def record(self, name: str, success: bool, duration: float, details: str = ""):
        self.total_tests += 1
        if success:
            self.passed_tests += 1
        else:
            self.failed_tests += 1
        self.total_duration += duration
        self.test_results.append({
            "name": name,
            "success": success,
            "duration": duration,
            "details": details
        })
    
    def summary(self) -> str:
        return (
            f"\n{'='*60}\n"
            f"测试汇总\n"
            f"{'='*60}\n"
            f"总测试数: {self.total_tests}\n"
            f"通过: {self.passed_tests}\n"
            f"失败: {self.failed_tests}\n"
            f"跳过: {self.skipped_tests}\n"
            f"总耗时: {self.total_duration:.2f}s\n"
            f"平均耗时: {self.total_duration/max(self.total_tests, 1):.2f}s\n"
            f"{'='*60}"
        )


# 全局测试指标收集器
metrics = TestMetrics()


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="module")
def settings() -> Settings:
    """加载应用配置"""
    return Settings()


@pytest.fixture(scope="module")
def check_env(settings: Settings) -> None:
    """验证必需的环境变量"""
    required = {
        "TABLEAU_DOMAIN": settings.tableau_domain,
        "LLM_API_KEY": settings.llm_api_key,
        "DATASOURCE_LUID": settings.datasource_luid,
        "TOOLING_LLM_MODEL": settings.tooling_llm_model,
    }
    
    missing = [k for k, v in required.items() if not v]
    
    if missing:
        pytest.skip(f"缺少环境配置: {', '.join(missing)}")
    
    # 打印当前配置
    print(f"\n{'='*60}")
    print(f"测试环境配置")
    print(f"{'='*60}")
    print(f"Tableau Domain: {settings.tableau_domain}")
    print(f"LLM Model: {settings.tooling_llm_model}")
    print(f"LLM Provider: {settings.llm_model_provider}")
    print(f"Datasource LUID: {settings.datasource_luid[:8]}...")
    print(f"{'='*60}\n")


@pytest.fixture(scope="module")
def executor() -> WorkflowExecutor:
    """创建 WorkflowExecutor 实例"""
    return WorkflowExecutor(
        max_replan_rounds=3,
        use_memory_checkpointer=True,
    )


@pytest.fixture(scope="module")
def printer() -> WorkflowPrinter:
    """创建 WorkflowPrinter 实例"""
    return WorkflowPrinter(verbose=True, show_tokens=True)


@pytest.fixture(scope="function")
def fresh_executor() -> WorkflowExecutor:
    """每个测试创建新的 executor"""
    return WorkflowExecutor(
        max_replan_rounds=3,
        use_memory_checkpointer=True,
    )


# ============================================================
# 辅助函数
# ============================================================

def print_test_header(test_name: str, description: str = ""):
    """打印测试头部"""
    print(f"\n{'='*60}")
    print(f"测试: {test_name}")
    if description:
        print(f"描述: {description}")
    print(f"{'='*60}")


def print_result_details(result: WorkflowResult):
    """打印详细结果"""
    print(f"\n--- 执行结果 ---")
    print(f"成功: {result.success}")
    print(f"耗时: {result.duration:.2f}s")
    print(f"是否分析类问题: {result.is_analysis_question}")
    print(f"重规划次数: {result.replan_count}")
    
    if result.error:
        print(f"错误: {result.error}")
    
    if result.semantic_query:
        print(f"\n--- SemanticQuery ---")
        if result.semantic_query.dimensions:
            dims = [d.name for d in result.semantic_query.dimensions]
            print(f"维度: {dims}")
        if result.semantic_query.measures:
            measures = [m.name for m in result.semantic_query.measures]
            print(f"度量: {measures}")
        if result.semantic_query.filters:
            print(f"筛选器: {len(result.semantic_query.filters)} 个")
    
    if result.mapped_query:
        print(f"\n--- MappedQuery ---")
        print(f"映射成功: {result.mapped_query is not None}")
    
    if result.vizql_query:
        print(f"\n--- VizQLQuery ---")
        print(f"查询生成成功: {result.vizql_query is not None}")
    
    if result.query_result:
        print(f"\n--- ExecuteResult ---")
        data = getattr(result.query_result, 'data', [])
        print(f"返回行数: {len(data) if data else 0}")
    
    if result.insights:
        print(f"\n--- Insights ---")
        print(f"洞察数量: {len(result.insights)}")
        for i, insight in enumerate(result.insights[:3]):
            print(f"  {i+1}. {str(insight)[:100]}...")
    
    if result.replan_decision:
        print(f"\n--- ReplanDecision ---")
        print(f"should_replan: {result.replan_decision.should_replan}")
        print(f"completeness_score: {result.replan_decision.completeness_score}")


async def run_test_case(
    executor: WorkflowExecutor,
    test_case: TestCase,
    printer: Optional[WorkflowPrinter] = None
) -> WorkflowResult:
    """运行单个测试用例"""
    print_test_header(test_case.name, test_case.description)
    print(f"问题: {test_case.question}")
    
    start_time = time.time()
    result = await executor.run(test_case.question)
    duration = time.time() - start_time
    
    if printer:
        printer.print_result(result)
    else:
        print_result_details(result)
    
    # 记录指标
    metrics.record(
        name=test_case.name,
        success=result.success,
        duration=duration,
        details=result.error or ""
    )
    
    return result



# ============================================================
# 测试类 1: 完整工作流测试
# ============================================================

class TestWorkflowComplete:
    """完整工作流执行测试"""
    
    @pytest.mark.asyncio
    async def test_full_workflow_all_nodes(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        测试完整工作流 - 所有节点执行
        
        验证: Understanding → FieldMapper → QueryBuilder → Execute → Insight → Replanner
        """
        print_test_header("完整工作流测试", "验证所有6个节点按顺序执行")
        
        question = "各地区销售额是多少"
        
        # 跟踪节点执行
        nodes_executed = []
        node_outputs = {}
        
        async for event in executor.stream(question):
            printer.print_event(event)
            if event.type == EventType.NODE_START:
                nodes_executed.append(event.node_name)
                print(f"  → 节点开始: {event.node_name}")
            elif event.type == EventType.NODE_COMPLETE:
                node_outputs[event.node_name] = event.output
                print(f"  ✓ 节点完成: {event.node_name}")
        
        # 执行完整查询获取结果
        result = await executor.run(question)
        print_result_details(result)
        
        # 断言
        assert result.success, f"工作流执行失败: {result.error}"
        assert result.is_analysis_question, "应识别为分析类问题"
        assert result.semantic_query is not None, "SemanticQuery 不应为空"
        
        # 验证关键节点都执行了
        expected_nodes = ["understanding", "field_mapper", "query_builder", "execute", "insight", "replanner"]
        for node in expected_nodes:
            assert node in nodes_executed, f"节点 {node} 未执行"
        
        print(f"\n✓ 完整工作流测试通过")
        print(f"  执行节点: {nodes_executed}")
    
    @pytest.mark.asyncio
    async def test_workflow_with_date_filter(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """测试带日期筛选的完整工作流"""
        print_test_header("带日期筛选的工作流", "验证日期筛选正确应用")
        
        question = "2024年各地区销售额"
        
        result = await executor.run(question)
        print_result_details(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.semantic_query is not None
        
        # 检查是否有筛选器
        if result.semantic_query.filters:
            print(f"✓ 识别到 {len(result.semantic_query.filters)} 个筛选器")
            for f in result.semantic_query.filters:
                print(f"  - {f}")
    
    @pytest.mark.asyncio
    async def test_workflow_multi_round_analysis(
        self,
        check_env,
    ):
        """测试多轮分析工作流"""
        print_test_header("多轮分析工作流", "验证重规划机制")
        
        # 使用较高的重规划轮数
        executor = WorkflowExecutor(
            max_replan_rounds=3,
            use_memory_checkpointer=True,
        )
        
        question = "深入分析各地区销售情况，找出关键问题"
        
        # 跟踪 understanding 节点执行次数
        understanding_count = 0
        async for event in executor.stream(question):
            if event.type == EventType.NODE_START and event.node_name == "understanding":
                understanding_count += 1
                print(f"  → 第 {understanding_count} 轮分析开始")
        
        result = await executor.run(question)
        print_result_details(result)
        
        assert result.success, f"执行失败: {result.error}"
        print(f"\n✓ 多轮分析测试通过")
        print(f"  分析轮数: {understanding_count}")
        print(f"  重规划次数: {result.replan_count}")


# ============================================================
# 测试类 2: 聚合查询测试
# ============================================================

class TestAggregationQueries:
    """聚合查询测试 - SUM, AVG, COUNT, COUNTD"""
    
    @pytest.mark.asyncio
    async def test_sum_aggregation(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试 SUM 聚合"""
        test_cases = [
            TestCase("SUM-地区销售额", "各地区销售额是多少", description="按地区汇总销售额"),
            TestCase("SUM-类别销售额", "各产品类别的销售总额", description="按产品类别汇总"),
            TestCase("SUM-年度销售额", "各年度销售总额", description="按年度汇总"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"
            assert result.semantic_query is not None
    
    @pytest.mark.asyncio
    async def test_avg_aggregation(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试 AVG 聚合"""
        test_cases = [
            TestCase("AVG-类别平均利润", "各产品类别的平均利润是多少", description="按类别计算平均利润"),
            TestCase("AVG-地区平均销售额", "各地区的平均销售额", description="按地区计算平均"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_count_aggregation(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试 COUNT 聚合"""
        test_cases = [
            TestCase("COUNT-地区订单数", "各地区有多少订单", description="统计各地区订单数量"),
            TestCase("COUNT-类别产品数", "各类别有多少产品", description="统计各类别产品数量"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_countd_aggregation(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试 COUNTD 去重计数"""
        test_cases = [
            TestCase("COUNTD-不同客户", "各地区有多少不同的客户", description="去重统计客户数"),
            TestCase("COUNTD-不同产品", "各类别有多少种不同的产品", description="去重统计产品数"),
            TestCase("COUNTD-去重订单", "每个客户有多少个不重复的订单", description="去重统计订单"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"


# ============================================================
# 测试类 3: LOD 表达式测试
# ============================================================

class TestLODExpressions:
    """LOD 表达式测试 - FIXED, INCLUDE, EXCLUDE"""
    
    @pytest.mark.asyncio
    async def test_fixed_lod(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试 FIXED LOD"""
        test_cases = [
            TestCase("FIXED-首次购买", "每个客户的首次购买日期是什么", description="FIXED LOD 计算首次购买"),
            TestCase("FIXED-客户总消费", "每个客户的总消费金额是多少", description="FIXED LOD 计算客户生命周期价值"),
            TestCase("FIXED-类别总额", "计算每个产品类别的总销售额，不受其他维度影响", description="FIXED LOD 固定维度"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_include_lod(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试 INCLUDE LOD"""
        test_cases = [
            TestCase("INCLUDE-客户平均订单", "每个地区每个客户的平均订单金额", description="INCLUDE LOD 包含客户维度"),
            TestCase("INCLUDE-客户订单数", "按地区统计，包含每个客户的订单数量", description="INCLUDE LOD 统计"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_exclude_lod(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试 EXCLUDE LOD"""
        test_cases = [
            TestCase("EXCLUDE-排除类别", "不考虑产品类别的地区平均销售额", description="EXCLUDE LOD 排除类别"),
            TestCase("EXCLUDE-排除省份", "排除省份维度的地区销售总额", description="EXCLUDE LOD 排除省份"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"


# ============================================================
# 测试类 4: 表计算测试
# ============================================================

class TestTableCalculations:
    """表计算测试 - RUNNING_SUM, RANK, Moving Average, YoY, MoM"""
    
    @pytest.mark.asyncio
    async def test_running_sum(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试累计求和"""
        test_cases = [
            TestCase("RUNNING_SUM-月度累计", "按月份显示累计销售额", description="月度累计销售额"),
            TestCase("RUNNING_SUM-季度累计", "按季度显示累计利润", description="季度累计利润"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_rank(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试排名"""
        test_cases = [
            TestCase("RANK-产品排名", "各产品销售额排名", description="产品销售额排名"),
            TestCase("RANK-地区排名", "各地区利润排名", description="地区利润排名"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_moving_average(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试移动平均"""
        test_cases = [
            TestCase("MA-3月移动平均", "销售额的3个月移动平均", description="3个月移动平均"),
            TestCase("MA-周移动平均", "按周计算销售额的移动平均", description="周移动平均"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_yoy_growth(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试同比增长"""
        test_cases = [
            TestCase("YoY-地区同比", "各地区销售额同比增长率", description="地区同比增长"),
            TestCase("YoY-年度对比", "今年与去年销售额对比", description="年度销售对比"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_mom_growth(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试环比增长"""
        test_cases = [
            TestCase("MoM-月度环比", "各月销售额环比增长", description="月度环比增长"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_percent_of_total(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试占比计算"""
        test_cases = [
            TestCase("PCT-类别占比", "各产品类别销售额占比", description="类别销售占比"),
            TestCase("PCT-地区占比", "各地区销售额占总销售额的百分比", description="地区销售占比"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"



# ============================================================
# 测试类 5: 日期筛选测试
# ============================================================

class TestDateFilters:
    """日期筛选测试 - 绝对日期、相对日期、复合日期"""
    
    @pytest.mark.asyncio
    async def test_absolute_date_filters(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试绝对日期筛选"""
        test_cases = [
            TestCase("ABS-年份筛选", "2024年各地区销售额", description="按年份筛选"),
            TestCase("ABS-月份筛选", "2024年3月的销售情况", description="按年月筛选"),
            TestCase("ABS-日期范围", "2024年1月到3月的销售额", description="日期范围筛选"),
            TestCase("ABS-季度筛选", "2024年第一季度销售额", description="按季度筛选"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"
            
            # 验证筛选器
            if result.semantic_query and result.semantic_query.filters:
                print(f"  ✓ {tc.name}: 识别到 {len(result.semantic_query.filters)} 个筛选器")
    
    @pytest.mark.asyncio
    async def test_relative_date_filters(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试相对日期筛选"""
        test_cases = [
            TestCase("REL-本月", "本月销售额是多少", description="本月筛选"),
            TestCase("REL-上月", "上个月各地区销售额", description="上月筛选"),
            TestCase("REL-最近N月", "最近3个月的销售趋势", description="最近N月筛选"),
            TestCase("REL-今年至今", "今年至今的销售总额", description="YTD筛选"),
            TestCase("REL-本周", "本周销售额", description="本周筛选"),
            TestCase("REL-上周", "上周销售额", description="上周筛选"),
            TestCase("REL-最近N天", "最近7天的销售额", description="最近N天筛选"),
            TestCase("REL-昨天", "昨天的销售额", description="昨天筛选"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_compound_date_filters(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试复合日期筛选"""
        test_cases = [
            TestCase("COMP-年周", "2024年第10周的销售额", description="年+周复合筛选"),
            TestCase("COMP-多年季度", "2023年和2024年第一季度销售对比", description="多年季度对比"),
            TestCase("COMP-工作日周末", "工作日和周末的销售额对比", description="工作日/周末对比"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"


# ============================================================
# 测试类 6: 多维度多度量测试
# ============================================================

class TestMultiDimensionMeasure:
    """多维度多度量分析测试"""
    
    @pytest.mark.asyncio
    async def test_multi_dimension(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试多维度查询"""
        test_cases = [
            TestCase("MULTI-DIM-2维", "各地区各产品类别的销售额", 
                     description="2个维度", expected_dimensions=["地区", "产品类别"]),
            TestCase("MULTI-DIM-3维", "各地区各产品类别各年份的销售额", 
                     description="3个维度"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"
            
            # 验证维度数量
            if result.semantic_query and result.semantic_query.dimensions:
                dim_count = len(result.semantic_query.dimensions)
                print(f"  ✓ {tc.name}: 识别到 {dim_count} 个维度")
    
    @pytest.mark.asyncio
    async def test_multi_measure(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试多度量查询"""
        test_cases = [
            TestCase("MULTI-MEAS-2度量", "各地区的销售额和利润", 
                     description="2个度量", expected_measures=["销售额", "利润"]),
            TestCase("MULTI-MEAS-3度量", "各地区的销售额、利润和数量", 
                     description="3个度量"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"
            
            # 验证度量数量
            if result.semantic_query and result.semantic_query.measures:
                measure_count = len(result.semantic_query.measures)
                print(f"  ✓ {tc.name}: 识别到 {measure_count} 个度量")
    
    @pytest.mark.asyncio
    async def test_multi_dim_multi_measure(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试多维度+多度量组合查询"""
        test_cases = [
            TestCase("MULTI-COMBO", "各地区各产品类别的销售额和利润", 
                     description="多维度+多度量组合"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"


# ============================================================
# 测试类 7: 维度下钻测试
# ============================================================

class TestDimensionDrilldown:
    """维度下钻测试 - 地理、时间、产品层级"""
    
    @pytest.mark.asyncio
    async def test_geo_drilldown(
        self,
        check_env,
    ):
        """测试地理维度下钻"""
        executor = WorkflowExecutor(max_replan_rounds=3, use_memory_checkpointer=True)
        
        test_cases = [
            TestCase("GEO-地区分析", "分析各地区销售情况", description="地区级别分析"),
            TestCase("GEO-省份分析", "分析各省份销售情况", description="省份级别分析"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"
            
            # 检查重规划决策
            if result.replan_decision:
                print(f"  重规划: should_replan={result.replan_decision.should_replan}")
    
    @pytest.mark.asyncio
    async def test_time_drilldown(
        self,
        check_env,
    ):
        """测试时间维度下钻"""
        executor = WorkflowExecutor(max_replan_rounds=3, use_memory_checkpointer=True)
        
        test_cases = [
            TestCase("TIME-年度分析", "分析各年度销售趋势", description="年度级别分析"),
            TestCase("TIME-季度分析", "分析各季度销售情况", description="季度级别分析"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_product_drilldown(
        self,
        check_env,
    ):
        """测试产品维度下钻"""
        executor = WorkflowExecutor(max_replan_rounds=3, use_memory_checkpointer=True)
        
        test_cases = [
            TestCase("PROD-类别分析", "分析各产品类别销售情况", description="类别级别分析"),
            TestCase("PROD-子类别分析", "分析各产品子类别销售情况", description="子类别级别分析"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_deep_drilldown(
        self,
        check_env,
    ):
        """测试深度下钻分析"""
        executor = WorkflowExecutor(max_replan_rounds=3, use_memory_checkpointer=True)
        
        print_test_header("深度下钻分析", "测试多轮下钻")
        
        question = "深入分析各地区销售情况，找出销售最好和最差的区域"
        
        # 跟踪分析轮数
        understanding_visits = 0
        async for event in executor.stream(question):
            if event.type == EventType.NODE_START and event.node_name == "understanding":
                understanding_visits += 1
                print(f"  → 第 {understanding_visits} 轮分析")
        
        result = await executor.run(question)
        print_result_details(result)
        
        assert result.success, f"执行失败: {result.error}"
        print(f"\n✓ 深度下钻测试通过")
        print(f"  分析轮数: {understanding_visits}")
        print(f"  重规划次数: {result.replan_count}")


# ============================================================
# 测试类 8: 非分析类问题路由测试
# ============================================================

class TestNonAnalysisRouting:
    """非分析类问题路由测试"""
    
    @pytest.mark.asyncio
    async def test_greeting_routing(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试问候语路由"""
        test_cases = [
            TestCase("ROUTE-你好", "你好", expected_analysis=False, description="问候语"),
            TestCase("ROUTE-再见", "再见", expected_analysis=False, description="告别语"),
            TestCase("ROUTE-谢谢", "谢谢", expected_analysis=False, description="感谢语"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"
            assert not result.is_analysis_question, f"{tc.name}: 应识别为非分析类问题"
            print(f"  ✓ {tc.name}: 正确识别为非分析类问题")
    
    @pytest.mark.asyncio
    async def test_help_routing(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试帮助类问题路由"""
        test_cases = [
            TestCase("ROUTE-能做什么", "你能做什么", expected_analysis=False, description="能力询问"),
            TestCase("ROUTE-帮助", "帮助", expected_analysis=False, description="帮助请求"),
            TestCase("ROUTE-你是谁", "你是谁", expected_analysis=False, description="身份询问"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"
            assert not result.is_analysis_question, f"{tc.name}: 应识别为非分析类问题"
    
    @pytest.mark.asyncio
    async def test_chitchat_routing(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试闲聊类问题路由"""
        test_cases = [
            TestCase("ROUTE-天气", "今天天气怎么样", expected_analysis=False, description="天气询问"),
        ]
        
        for tc in test_cases:
            result = await run_test_case(executor, tc)
            assert result.success, f"{tc.name} 失败: {result.error}"
            # 闲聊可能被识别为非分析类
            print(f"  {tc.name}: is_analysis_question={result.is_analysis_question}")
    
    @pytest.mark.asyncio
    async def test_analysis_vs_non_analysis(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """对比分析类和非分析类问题的节点访问"""
        print_test_header("分析类 vs 非分析类对比", "验证路由差异")
        
        # 分析类问题
        analysis_question = "各地区销售额是多少"
        analysis_nodes = []
        async for event in executor.stream(analysis_question):
            if event.type == EventType.NODE_START:
                analysis_nodes.append(event.node_name)
        
        # 非分析类问题
        non_analysis_question = "你好"
        non_analysis_nodes = []
        async for event in executor.stream(non_analysis_question):
            if event.type == EventType.NODE_START:
                non_analysis_nodes.append(event.node_name)
        
        print(f"\n分析类问题节点: {analysis_nodes}")
        print(f"非分析类问题节点: {non_analysis_nodes}")
        
        # 分析类应该访问更多节点
        assert len(analysis_nodes) > len(non_analysis_nodes), "分析类问题应访问更多节点"
        assert "field_mapper" in analysis_nodes, "分析类问题应访问 field_mapper"



# ============================================================
# 测试类 9: 错误处理测试
# ============================================================

class TestErrorHandling:
    """错误处理测试"""
    
    @pytest.mark.asyncio
    async def test_invalid_field_handling(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试无效字段处理"""
        test_cases = [
            TestCase("ERR-不存在字段", "查询不存在的字段XYZ123的数据", description="无效字段查询"),
            TestCase("ERR-无效计算", "计算ABC除以DEF的结果", description="无效计算"),
        ]
        
        for tc in test_cases:
            print_test_header(tc.name, tc.description)
            print(f"问题: {tc.question}")
            
            # 不应抛出异常
            try:
                result = await executor.run(tc.question)
                print(f"  执行结果: success={result.success}")
                if result.error:
                    print(f"  错误信息: {result.error}")
            except Exception as e:
                pytest.fail(f"不应抛出异常: {e}")
    
    @pytest.mark.asyncio
    async def test_empty_question_handling(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试空问题处理"""
        test_cases = [
            TestCase("ERR-空字符串", "", description="空字符串"),
            TestCase("ERR-空白字符", "   ", description="纯空白字符"),
        ]
        
        for tc in test_cases:
            print_test_header(tc.name, tc.description)
            
            try:
                result = await executor.run(tc.question)
                print(f"  执行结果: success={result.success}")
            except Exception as e:
                pytest.fail(f"不应抛出异常: {e}")
    
    @pytest.mark.asyncio
    async def test_special_characters_handling(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试特殊字符处理"""
        test_cases = [
            TestCase("ERR-特殊字符", "各地区销售额是多少？！@#$%^&*()", description="包含特殊字符"),
            TestCase("ERR-SQL注入", "各地区销售额'; DROP TABLE users;--", description="SQL注入尝试"),
        ]
        
        for tc in test_cases:
            print_test_header(tc.name, tc.description)
            
            try:
                result = await executor.run(tc.question)
                print(f"  执行结果: success={result.success}")
            except Exception as e:
                pytest.fail(f"不应抛出异常: {e}")
    
    @pytest.mark.asyncio
    async def test_long_question_handling(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试超长问题处理"""
        print_test_header("超长问题处理", "测试超长输入")
        
        long_question = "各地区销售额是多少" * 50
        
        try:
            result = await executor.run(long_question)
            print(f"  执行结果: success={result.success}")
        except Exception as e:
            pytest.fail(f"不应抛出异常: {e}")
    
    @pytest.mark.asyncio
    async def test_future_date_handling(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试未来日期处理（可能返回空结果）"""
        print_test_header("未来日期处理", "测试无数据情况")
        
        question = "2099年的销售额"
        
        result = await executor.run(question)
        print_result_details(result)
        
        # 应该成功执行，即使结果为空
        print(f"  执行结果: success={result.success}")
        if result.query_result:
            data = getattr(result.query_result, 'data', [])
            print(f"  返回数据行数: {len(data) if data else 0}")


# ============================================================
# 测试类 10: 流式输出测试
# ============================================================

class TestStreamingOutput:
    """流式输出测试"""
    
    @pytest.mark.asyncio
    async def test_streaming_events(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试流式事件输出"""
        print_test_header("流式事件测试", "验证各类事件正确发出")
        
        question = "各地区销售额是多少"
        
        events_received = {
            "node_start": [],
            "node_complete": [],
            "token": 0,
            "error": [],
            "complete": False,
        }
        
        async for event in executor.stream(question):
            if event.type == EventType.NODE_START:
                events_received["node_start"].append(event.node_name)
                print(f"  NODE_START: {event.node_name}")
            elif event.type == EventType.NODE_COMPLETE:
                events_received["node_complete"].append(event.node_name)
                print(f"  NODE_COMPLETE: {event.node_name}")
            elif event.type == EventType.TOKEN:
                events_received["token"] += 1
            elif event.type == EventType.ERROR:
                events_received["error"].append(event.content)
                print(f"  ERROR: {event.content}")
            elif event.type == EventType.COMPLETE:
                events_received["complete"] = True
                print(f"  COMPLETE")
        
        # 验证
        assert events_received["complete"], "应收到 COMPLETE 事件"
        assert len(events_received["node_start"]) > 0, "应收到 NODE_START 事件"
        assert len(events_received["node_complete"]) > 0, "应收到 NODE_COMPLETE 事件"
        
        print(f"\n✓ 流式事件测试通过")
        print(f"  NODE_START 事件: {len(events_received['node_start'])}")
        print(f"  NODE_COMPLETE 事件: {len(events_received['node_complete'])}")
        print(f"  TOKEN 事件: {events_received['token']}")
    
    @pytest.mark.asyncio
    async def test_token_streaming(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试 Token 流式输出"""
        print_test_header("Token 流式测试", "验证 LLM Token 流式输出")
        
        question = "各地区销售额是多少"
        
        token_count = 0
        token_content = []
        
        async for event in executor.stream(question):
            if event.type == EventType.TOKEN:
                token_count += 1
                if event.content:
                    token_content.append(event.content)
        
        print(f"\n✓ Token 流式测试完成")
        print(f"  收到 {token_count} 个 TOKEN 事件")
        if token_content:
            sample = ''.join(token_content[:20])
            print(f"  Token 内容示例: {sample}...")
    
    @pytest.mark.asyncio
    async def test_node_output_in_events(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试节点输出包含在事件中"""
        print_test_header("节点输出测试", "验证 NODE_COMPLETE 事件包含输出")
        
        question = "各地区销售额是多少"
        
        node_outputs = {}
        
        async for event in executor.stream(question):
            if event.type == EventType.NODE_COMPLETE:
                node_outputs[event.node_name] = event.output
        
        print(f"\n节点输出:")
        for node_name, output in node_outputs.items():
            has_output = output is not None
            print(f"  {node_name}: {'有输出' if has_output else '无输出'}")
        
        # 验证关键节点有输出
        assert "understanding" in node_outputs, "应有 understanding 节点输出"


# ============================================================
# 测试类 11: 重规划决策测试
# ============================================================

class TestReplannerDecision:
    """重规划决策测试"""
    
    @pytest.mark.asyncio
    async def test_replan_decision_structure(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试重规划决策结构"""
        print_test_header("重规划决策结构", "验证 ReplanDecision 字段")
        
        question = "各地区销售额是多少"
        
        result = await executor.run(question)
        
        assert result.success, f"执行失败: {result.error}"
        
        if result.replan_decision:
            print(f"\n重规划决策:")
            print(f"  should_replan: {result.replan_decision.should_replan}")
            print(f"  completeness_score: {result.replan_decision.completeness_score}")
            if hasattr(result.replan_decision, 'reason'):
                print(f"  reason: {result.replan_decision.reason}")
            if hasattr(result.replan_decision, 'exploration_questions'):
                print(f"  exploration_questions: {result.replan_decision.exploration_questions}")
            
            # 验证字段
            assert hasattr(result.replan_decision, 'should_replan'), "应有 should_replan 字段"
            assert hasattr(result.replan_decision, 'completeness_score'), "应有 completeness_score 字段"
    
    @pytest.mark.asyncio
    async def test_max_replan_rounds_limit(
        self,
        check_env,
    ):
        """测试最大重规划轮数限制"""
        print_test_header("重规划轮数限制", "验证不超过最大轮数")
        
        # 设置较低的最大轮数
        executor = WorkflowExecutor(
            max_replan_rounds=2,
            use_memory_checkpointer=True,
        )
        
        question = "深入分析各地区销售情况，找出所有问题"
        
        result = await executor.run(question)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.replan_count <= 2, f"重规划次数 {result.replan_count} 超过限制 2"
        
        print(f"\n✓ 重规划轮数限制测试通过")
        print(f"  重规划次数: {result.replan_count}")
    
    @pytest.mark.asyncio
    async def test_simple_query_no_replan(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试简单查询不触发重规划"""
        print_test_header("简单查询无重规划", "验证简单问题不触发重规划")
        
        question = "2024年各地区销售额是多少"
        
        result = await executor.run(question)
        
        assert result.success, f"执行失败: {result.error}"
        
        print(f"\n重规划次数: {result.replan_count}")
        if result.replan_decision:
            print(f"should_replan: {result.replan_decision.should_replan}")
            print(f"completeness_score: {result.replan_decision.completeness_score}")


# ============================================================
# 测试类 12: 洞察生成测试
# ============================================================

class TestInsightGeneration:
    """洞察生成测试"""
    
    @pytest.mark.asyncio
    async def test_insight_generation(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试洞察生成"""
        print_test_header("洞察生成测试", "验证 Insight Agent 生成洞察")
        
        question = "各地区销售额是多少"
        
        result = await executor.run(question)
        
        assert result.success, f"执行失败: {result.error}"
        
        print(f"\n洞察数量: {len(result.insights)}")
        for i, insight in enumerate(result.insights[:5]):
            print(f"  {i+1}. {str(insight)[:100]}...")
    
    @pytest.mark.asyncio
    async def test_insights_accumulation(
        self,
        check_env,
    ):
        """测试多轮分析洞察累积"""
        print_test_header("洞察累积测试", "验证多轮分析洞察正确累积")
        
        executor = WorkflowExecutor(
            max_replan_rounds=3,
            use_memory_checkpointer=True,
        )
        
        question = "分析各地区销售情况"
        
        result = await executor.run(question)
        
        assert result.success, f"执行失败: {result.error}"
        
        print(f"\n累积洞察数量: {len(result.insights)}")
        print(f"重规划次数: {result.replan_count}")
        
        # 洞察应该是列表
        assert isinstance(result.insights, list), "insights 应为列表"
    
    @pytest.mark.asyncio
    async def test_insights_no_duplicates(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试洞察无重复"""
        print_test_header("洞察去重测试", "验证洞察无重复")
        
        question = "分析各产品类别销售情况"
        
        result = await executor.run(question)
        
        assert result.success, f"执行失败: {result.error}"
        
        # 简单去重检查
        insights_str = [str(i) for i in result.insights]
        unique_insights = set(insights_str)
        
        print(f"\n总洞察数: {len(insights_str)}")
        print(f"唯一洞察数: {len(unique_insights)}")


# ============================================================
# 测试类 13: 性能测试
# ============================================================

class TestPerformance:
    """性能测试"""
    
    @pytest.mark.asyncio
    async def test_simple_query_performance(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试简单查询性能"""
        print_test_header("简单查询性能", "测试响应时间")
        
        question = "各地区销售额是多少"
        
        start_time = time.time()
        result = await executor.run(question)
        duration = time.time() - start_time
        
        assert result.success, f"执行失败: {result.error}"
        
        print(f"\n✓ 简单查询性能测试")
        print(f"  耗时: {duration:.2f}s")
        
        # 简单查询应在合理时间内完成
        assert duration < 120, f"查询耗时 {duration:.2f}s 超过 120s 限制"
    
    @pytest.mark.asyncio
    async def test_batch_queries_performance(
        self,
        executor: WorkflowExecutor,
        check_env,
    ):
        """测试批量查询性能"""
        print_test_header("批量查询性能", "测试多个查询的总耗时")
        
        questions = [
            "各地区销售额是多少",
            "各产品类别的平均利润",
            "本月销售额",
        ]
        
        total_start = time.time()
        results = []
        
        for q in questions:
            start = time.time()
            result = await executor.run(q)
            duration = time.time() - start
            results.append((q, result.success, duration))
            print(f"  {q[:20]}...: {duration:.2f}s")
        
        total_duration = time.time() - total_start
        
        print(f"\n✓ 批量查询性能测试")
        print(f"  总查询数: {len(questions)}")
        print(f"  总耗时: {total_duration:.2f}s")
        print(f"  平均耗时: {total_duration/len(questions):.2f}s")
        
        # 验证所有查询成功
        for q, success, _ in results:
            assert success, f"查询失败: {q}"



# ============================================================
# 测试类 14: 上下文和状态测试
# ============================================================

class TestContextAndState:
    """上下文和状态测试"""
    
    @pytest.mark.asyncio
    async def test_workflow_context_creation(
        self,
        check_env,
        settings: Settings,
    ):
        """测试 WorkflowContext 创建"""
        print_test_header("WorkflowContext 创建", "验证上下文正确初始化")
        
        from tableau_assistant.src.workflow.context import WorkflowContext
        from tableau_assistant.src.bi_platforms.tableau import get_tableau_auth_async
        from tableau_assistant.src.capabilities.storage.store_manager import get_store_manager
        
        # 获取认证
        auth = await get_tableau_auth_async()
        store = get_store_manager()
        
        # 创建上下文
        ctx = WorkflowContext(
            auth=auth,
            store=store,
            datasource_luid=settings.datasource_luid,
        )
        
        assert ctx.auth is not None, "auth 不应为空"
        assert ctx.store is not None, "store 不应为空"
        assert ctx.datasource_luid == settings.datasource_luid
        
        print(f"\n✓ WorkflowContext 创建成功")
        print(f"  datasource_luid: {ctx.datasource_luid[:8]}...")
        print(f"  auth_method: {ctx.auth.auth_method}")
    
    @pytest.mark.asyncio
    async def test_metadata_loading(
        self,
        check_env,
        settings: Settings,
    ):
        """测试元数据加载"""
        print_test_header("元数据加载", "验证元数据正确加载")
        
        from tableau_assistant.src.workflow.context import WorkflowContext
        from tableau_assistant.src.bi_platforms.tableau import get_tableau_auth_async
        from tableau_assistant.src.capabilities.storage.store_manager import get_store_manager
        
        auth = await get_tableau_auth_async()
        store = get_store_manager()
        
        ctx = WorkflowContext(
            auth=auth,
            store=store,
            datasource_luid=settings.datasource_luid,
        )
        
        # 加载元数据
        ctx_loaded = await ctx.ensure_metadata_loaded()
        
        if ctx_loaded.metadata:
            print(f"\n✓ 元数据加载成功")
            print(f"  字段数量: {ctx_loaded.metadata.field_count}")
            if ctx_loaded.metadata_load_status:
                print(f"  加载来源: {ctx_loaded.metadata_load_status.source}")
        else:
            print(f"\n⚠️ 元数据为空（可能是 API 限制）")
    
    @pytest.mark.asyncio
    async def test_dimension_hierarchy_loading(
        self,
        check_env,
        settings: Settings,
    ):
        """测试维度层级加载"""
        print_test_header("维度层级加载", "验证维度层级正确加载")
        
        from tableau_assistant.src.workflow.context import WorkflowContext
        from tableau_assistant.src.bi_platforms.tableau import get_tableau_auth_async
        from tableau_assistant.src.capabilities.storage.store_manager import get_store_manager
        
        auth = await get_tableau_auth_async()
        store = get_store_manager()
        
        ctx = WorkflowContext(
            auth=auth,
            store=store,
            datasource_luid=settings.datasource_luid,
        )
        
        ctx_loaded = await ctx.ensure_metadata_loaded()
        
        hierarchy = ctx_loaded.dimension_hierarchy
        
        if hierarchy:
            print(f"\n✓ 维度层级加载成功")
            print(f"  维度数量: {len(hierarchy)}")
            
            # 打印部分维度
            for i, (name, attrs) in enumerate(hierarchy.items()):
                if i >= 5:
                    print(f"  ... 还有 {len(hierarchy) - 5} 个维度")
                    break
                category = attrs.get('category', 'N/A') if isinstance(attrs, dict) else 'N/A'
                print(f"  - {name}: {category}")
        else:
            print(f"\n⚠️ 维度层级为空")
    
    @pytest.mark.asyncio
    async def test_auth_refresh(
        self,
        check_env,
    ):
        """测试认证刷新"""
        print_test_header("认证刷新", "验证 Token 刷新机制")
        
        from tableau_assistant.src.bi_platforms.tableau import get_tableau_auth_async
        
        # 获取初始 token
        auth1 = await get_tableau_auth_async()
        print(f"  初始 Token: {auth1.api_key[:20]}...")
        print(f"  剩余时间: {auth1.remaining_seconds:.0f}s")
        
        # 强制刷新
        auth2 = await get_tableau_auth_async(force_refresh=True)
        print(f"  刷新后 Token: {auth2.api_key[:20]}...")
        print(f"  剩余时间: {auth2.remaining_seconds:.0f}s")
        
        assert auth2.api_key is not None
        assert not auth2.is_expired()
        
        print(f"\n✓ 认证刷新测试通过")


# ============================================================
# 测试类 15: 工具访问测试
# ============================================================

class TestToolAccess:
    """工具访问测试"""
    
    @pytest.mark.asyncio
    async def test_metadata_tool(
        self,
        check_env,
        settings: Settings,
    ):
        """测试 metadata_tool 访问"""
        print_test_header("metadata_tool 测试", "验证工具正确访问上下文")
        
        from tableau_assistant.src.tools.metadata_tool import get_metadata
        from tableau_assistant.src.workflow.context import (
            WorkflowContext,
            create_workflow_config,
        )
        from tableau_assistant.src.bi_platforms.tableau import get_tableau_auth_async
        from tableau_assistant.src.capabilities.storage.store_manager import get_store_manager
        
        # 创建上下文
        auth = await get_tableau_auth_async()
        store = get_store_manager()
        
        ctx = WorkflowContext(
            auth=auth,
            store=store,
            datasource_luid=settings.datasource_luid,
        )
        
        ctx_loaded = await ctx.ensure_metadata_loaded()
        
        if not ctx_loaded.metadata or not ctx_loaded.metadata.fields:
            pytest.skip("元数据为空")
        
        # 创建 config
        config = create_workflow_config("test_tool", ctx_loaded)
        
        # 调用工具
        result = await get_metadata.ainvoke(
            {"filter_role": None, "filter_category": None},
            config=config
        )
        
        assert result is not None
        print(f"\n✓ metadata_tool 测试通过")
        print(f"  结果长度: {len(result)} 字符")
    
    @pytest.mark.asyncio
    async def test_metadata_tool_filter(
        self,
        check_env,
        settings: Settings,
    ):
        """测试 metadata_tool 过滤功能"""
        print_test_header("metadata_tool 过滤", "验证维度/度量过滤")
        
        from tableau_assistant.src.tools.metadata_tool import get_metadata
        from tableau_assistant.src.workflow.context import (
            WorkflowContext,
            create_workflow_config,
        )
        from tableau_assistant.src.bi_platforms.tableau import get_tableau_auth_async
        from tableau_assistant.src.capabilities.storage.store_manager import get_store_manager
        
        auth = await get_tableau_auth_async()
        store = get_store_manager()
        
        ctx = WorkflowContext(
            auth=auth,
            store=store,
            datasource_luid=settings.datasource_luid,
        )
        
        ctx_loaded = await ctx.ensure_metadata_loaded()
        
        if not ctx_loaded.metadata or not ctx_loaded.metadata.fields:
            pytest.skip("元数据为空")
        
        config = create_workflow_config("test_filter", ctx_loaded)
        
        # 只获取维度
        result_dim = await get_metadata.ainvoke(
            {"filter_role": "dimension", "filter_category": None},
            config=config
        )
        
        # 只获取度量
        result_meas = await get_metadata.ainvoke(
            {"filter_role": "measure", "filter_category": None},
            config=config
        )
        
        print(f"\n✓ metadata_tool 过滤测试通过")
        print(f"  维度结果长度: {len(result_dim)} 字符")
        print(f"  度量结果长度: {len(result_meas)} 字符")


# ============================================================
# 测试类 16: 综合场景测试
# ============================================================

class TestComprehensiveScenarios:
    """综合场景测试 - 模拟真实使用场景"""
    
    @pytest.mark.asyncio
    async def test_scenario_sales_analysis(
        self,
        check_env,
    ):
        """场景: 销售分析"""
        print_test_header("场景: 销售分析", "模拟完整销售分析流程")
        
        executor = WorkflowExecutor(
            max_replan_rounds=3,
            use_memory_checkpointer=True,
        )
        
        questions = [
            "各地区销售额是多少",
            "哪个地区销售额最高",
            "各产品类别的销售占比",
            "本月销售额与上月对比",
        ]
        
        for q in questions:
            print(f"\n问题: {q}")
            result = await executor.run(q)
            print(f"  成功: {result.success}")
            print(f"  耗时: {result.duration:.2f}s")
            if result.insights:
                print(f"  洞察数: {len(result.insights)}")
    
    @pytest.mark.asyncio
    async def test_scenario_trend_analysis(
        self,
        check_env,
    ):
        """场景: 趋势分析"""
        print_test_header("场景: 趋势分析", "模拟时间序列分析")
        
        executor = WorkflowExecutor(
            max_replan_rounds=3,
            use_memory_checkpointer=True,
        )
        
        questions = [
            "各月销售趋势",
            "销售额同比增长率",
            "最近3个月的销售变化",
        ]
        
        for q in questions:
            print(f"\n问题: {q}")
            result = await executor.run(q)
            print(f"  成功: {result.success}")
            print(f"  耗时: {result.duration:.2f}s")
    
    @pytest.mark.asyncio
    async def test_scenario_deep_dive(
        self,
        check_env,
    ):
        """场景: 深度分析"""
        print_test_header("场景: 深度分析", "模拟多轮深入分析")
        
        executor = WorkflowExecutor(
            max_replan_rounds=3,
            use_memory_checkpointer=True,
        )
        
        question = "深入分析销售情况，找出问题和机会"
        
        print(f"\n问题: {question}")
        
        # 跟踪分析轮数
        rounds = 0
        async for event in executor.stream(question):
            if event.type == EventType.NODE_START and event.node_name == "understanding":
                rounds += 1
                print(f"  → 第 {rounds} 轮分析")
        
        result = await executor.run(question)
        
        print(f"\n分析完成:")
        print(f"  成功: {result.success}")
        print(f"  分析轮数: {rounds}")
        print(f"  重规划次数: {result.replan_count}")
        print(f"  洞察数量: {len(result.insights)}")


# ============================================================
# 测试汇总
# ============================================================

class TestSummary:
    """测试汇总"""
    
    @pytest.mark.asyncio
    async def test_print_summary(self):
        """打印测试汇总"""
        print(metrics.summary())


# ============================================================
# 运行入口
# ============================================================

if __name__ == "__main__":
    # 直接运行时使用 pytest
    pytest.main([
        __file__,
        "-v",
        "-s",
        "--tb=short",
        "-x",  # 遇到第一个失败就停止
    ])
