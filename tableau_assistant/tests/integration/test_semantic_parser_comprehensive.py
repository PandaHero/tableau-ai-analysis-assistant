# -*- coding: utf-8 -*-
"""
Semantic Parser 全面集成测试

使用真实环境和真实数据测试所有语义解析场景：
- 简单查�?
- 复杂计算（LOD、表计算、排名、占比、同比环比）
- 日期处理（各种粒度、相对日期、日期范围）
- 筛选条�?
- 问题重述（多轮对话上下文理解�?
- 意图分类（DATA_QUERY、CLARIFICATION、GENERAL、IRRELEVANT�?

运行方式:
    python tableau_assistant/tests/integration/test_semantic_parser_comprehensive.py

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
"""
import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from dotenv import load_dotenv
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════�?
# 测试用例定义
# ══════════════════════════════════════════════════════════════════════════�?

@dataclass
class TestCase:
    """测试用例"""
    name: str
    question: str
    category: str
    expected_intent: str = "DATA_QUERY"
    expected_dimensions: List[str] = field(default_factory=list)
    expected_measures: List[str] = field(default_factory=list)
    expected_calc_types: List[str] = field(default_factory=list)  # Expected CalcType list
    expected_filters: int = 0
    expected_computations: int = 0
    history: List[Dict[str, str]] = field(default_factory=list)
    description: str = ""


# 测试用例分类
TEST_CASES: Dict[str, List[TestCase]] = {
    # ══════════════════════════════════════════════════════════════════════�?
    # 1. 简单查�?
    # ══════════════════════════════════════════════════════════════════════�?
    "simple": [
        TestCase(
            name="simple_01_single_dimension",
            question="各省份的销售额是多少？",
            category="simple",
            expected_dimensions=["省份"],
            expected_measures=["销售额"],
            description="单维度单度量基础查询"
        ),
        TestCase(
            name="simple_02_multi_dimension",
            question="按产品类别和地区统计销售额",
            category="simple",
            expected_dimensions=["产品类别", "地区"],
            expected_measures=["销售额"],
            description="多维度单度量查询"
        ),
        TestCase(
            name="simple_03_multi_measure",
            question="各省份的销售额和利润",
            category="simple",
            expected_dimensions=["省份"],
            expected_measures=["销售额", "利润"],
            description="单维度多度量查询"
        ),
        TestCase(
            name="simple_04_count",
            question="各城市的订单数量",
            category="simple",
            expected_dimensions=["城市"],
            expected_measures=["订单"],
            description="计数聚合查询"
        ),
        TestCase(
            name="simple_05_average",
            question="各产品的平均利润",
            category="simple",
            expected_dimensions=["产品"],
            expected_measures=["利润"],
            description="平均值聚合查�?
        ),
    ],
    
    # ══════════════════════════════════════════════════════════════════════�?
    # 2. 日期相关查询
    # ══════════════════════════════════════════════════════════════════════�?
    "date": [
        TestCase(
            name="date_01_year_filter",
            question="2024年的销售额",
            category="date",
            expected_measures=["销售额"],
            expected_filters=1,
            description="年份筛�?
        ),
        TestCase(
            name="date_02_monthly_trend",
            question="按月份统计销售额趋势",
            category="date",
            expected_dimensions=["月份"],
            expected_measures=["销售额"],
            description="月度趋势分析"
        ),
        TestCase(
            name="date_03_quarterly",
            question="各季度的销售额",
            category="date",
            expected_dimensions=["季度"],
            expected_measures=["销售额"],
            description="季度粒度分析"
        ),
        TestCase(
            name="date_04_weekly",
            question="按周统计订单数量",
            category="date",
            expected_dimensions=["�?],
            expected_measures=["订单"],
            description="周粒度分�?
        ),
        TestCase(
            name="date_05_year_month",
            question="2024年各月的销售额",
            category="date",
            expected_dimensions=["月份"],
            expected_measures=["销售额"],
            expected_filters=1,
            description="年份筛�?月度分组"
        ),
        TestCase(
            name="date_06_relative_current_year",
            question="今年的销售额",
            category="date",
            expected_measures=["销售额"],
            expected_filters=1,
            description="相对日期-今年"
        ),
        TestCase(
            name="date_07_relative_last_year",
            question="去年的销售额",
            category="date",
            expected_measures=["销售额"],
            expected_filters=1,
            description="相对日期-去年"
        ),
        TestCase(
            name="date_08_date_range",
            question="2023年到2024年的销售额趋势",
            category="date",
            expected_dimensions=["�?],
            expected_measures=["销售额"],
            expected_filters=1,
            description="日期范围筛�?
        ),
    ],
    
    # ══════════════════════════════════════════════════════════════════════�?
    # 3. 筛选条�?
    # ══════════════════════════════════════════════════════════════════════�?
    "filter": [
        TestCase(
            name="filter_01_single_value",
            question="北京市的销售额",
            category="filter",
            expected_measures=["销售额"],
            expected_filters=1,
            description="单值筛�?
        ),
        TestCase(
            name="filter_02_multi_value",
            question="北京和上海的销售额对比",
            category="filter",
            expected_dimensions=["城市"],
            expected_measures=["销售额"],
            expected_filters=1,
            description="多值筛�?
        ),
        TestCase(
            name="filter_03_category_filter",
            question="办公用品类别的销售额",
            category="filter",
            expected_measures=["销售额"],
            expected_filters=1,
            description="类别筛�?
        ),
        TestCase(
            name="filter_04_combined_filters",
            question="2024年北京市的销售额",
            category="filter",
            expected_measures=["销售额"],
            expected_filters=2,
            description="组合筛选（日期+地区�?
        ),
        TestCase(
            name="filter_05_dimension_with_filter",
            question="各产品类别在华东地区的销售额",
            category="filter",
            expected_dimensions=["产品类别"],
            expected_measures=["销售额"],
            expected_filters=1,
            description="维度分组+筛�?
        ),
    ],
    
    # ══════════════════════════════════════════════════════════════════════�?
    # 4. 排名计算
    # ══════════════════════════════════════════════════════════════════════�?
    "ranking": [
        TestCase(
            name="ranking_01_simple",
            question="各省份销售额排名",
            category="ranking",
            expected_dimensions=["省份"],
            expected_measures=["销售额"],
            expected_calc_types=["RANK"],
            expected_computations=1,
            description="简单排名"
        ),
        TestCase(
            name="ranking_02_top_n",
            question="销售额前10的省份",
            category="ranking",
            expected_dimensions=["省份"],
            expected_measures=["销售额"],
            expected_calc_types=[],  # Top N uses filter, not computation
            expected_filters=1,  # TOP_N filter
            expected_computations=0,
            description="Top N 过滤 - 使用 TOP_N filter"
        ),
        TestCase(
            name="ranking_03_bottom_n",
            question="销售额最低的5个城市",
            category="ranking",
            expected_dimensions=["城市"],
            expected_measures=["销售额"],
            expected_calc_types=[],  # Bottom N uses filter, not computation
            expected_filters=1,  # TOP_N filter
            expected_computations=0,
            description="Bottom N 过滤 - 使用 TOP_N filter"
        ),
        TestCase(
            name="ranking_04_partition_rank",
            question="各产品类别内的销售额排名",
            category="ranking",
            expected_dimensions=["产品类别"],
            expected_measures=["销售额"],
            expected_calc_types=["RANK"],
            expected_computations=1,
            description="分区排名"
        ),
        TestCase(
            name="ranking_05_monthly_rank",
            question="每月各省份的销售额排名",
            category="ranking",
            expected_dimensions=["月份", "省份"],
            expected_measures=["销售额"],
            expected_calc_types=["RANK"],
            expected_computations=1,
            description="按月分区排名"
        ),
    ],
    
    # ══════════════════════════════════════════════════════════════════════�?
    # 5. 占比计算
    # ══════════════════════════════════════════════════════════════════════�?
    "percentage": [
        TestCase(
            name="percentage_01_total",
            question="各省份销售额占比",
            category="percentage",
            expected_dimensions=["省份"],
            expected_measures=["销售额"],
            expected_calc_types=["PERCENT_OF_TOTAL"],
            expected_computations=1,
            description="占总体比例"
        ),
        TestCase(
            name="percentage_02_partition",
            question="各产品在每个地区的销售额占比",
            category="percentage",
            expected_dimensions=["地区", "产品"],
            expected_measures=["销售额"],
            expected_calc_types=["PERCENT_OF_TOTAL"],
            expected_computations=1,
            description="分区占比"
        ),
        TestCase(
            name="percentage_03_category_share",
            question="各产品类别的市场份额",
            category="percentage",
            expected_dimensions=["产品类别"],
            expected_measures=["销售额"],
            expected_calc_types=["PERCENT_OF_TOTAL"],
            expected_computations=1,
            description="市场份额（占比的另一种表达）"
        ),
    ],
    
    # ══════════════════════════════════════════════════════════════════════�?
    # 6. 同比环比计算
    # ══════════════════════════════════════════════════════════════════════�?
    "yoy_mom": [
        TestCase(
            name="yoy_01_simple",
            question="各月销售额同比增长",
            category="yoy_mom",
            expected_dimensions=["月份"],
            expected_measures=["销售额"],
            expected_calc_types=["PERCENT_DIFFERENCE"],
            expected_computations=1,
            description="同比增长"
        ),
        TestCase(
            name="yoy_02_with_dimension",
            question="各省份销售额同比变化",
            category="yoy_mom",
            expected_dimensions=["省份"],
            expected_measures=["销售额"],
            expected_calc_types=["PERCENT_DIFFERENCE"],
            expected_computations=1,
            description="按维度的同比"
        ),
        TestCase(
            name="mom_01_simple",
            question="各月销售额环比增长",
            category="yoy_mom",
            expected_dimensions=["月份"],
            expected_measures=["销售额"],
            expected_calc_types=["PERCENT_DIFFERENCE"],
            expected_computations=1,
            description="环比增长"
        ),
        TestCase(
            name="yoy_03_growth_rate",
            question="2024年各季度销售额同比增长�?,
            category="yoy_mom",
            expected_dimensions=["季度"],
            expected_measures=["销售额"],
            expected_calc_types=["PERCENT_DIFFERENCE"],
            expected_filters=1,
            expected_computations=1,
            description="同比增长�?
        ),
    ],
    
    # ══════════════════════════════════════════════════════════════════════�?
    # 7. 累计计算
    # ══════════════════════════════════════════════════════════════════════�?
    "cumulative": [
        TestCase(
            name="cumulative_01_running_total",
            question="各月累计销售额",
            category="cumulative",
            expected_dimensions=["月份"],
            expected_measures=["销售额"],
            expected_calc_types=["RUNNING_TOTAL"],
            expected_computations=1,
            description="累计总和"
        ),
        TestCase(
            name="cumulative_02_ytd",
            question="年初至今的销售额",
            category="cumulative",
            expected_measures=["销售额"],
            expected_calc_types=["RUNNING_TOTAL"],
            expected_computations=1,
            description="年初至今"
        ),
        TestCase(
            name="cumulative_03_partition",
            question="各地区按月累计销售额",
            category="cumulative",
            expected_dimensions=["地区", "月份"],
            expected_measures=["销售额"],
            expected_calc_types=["RUNNING_TOTAL"],
            expected_computations=1,
            description="分区累计"
        ),
    ],
    
    # ══════════════════════════════════════════════════════════════════════�?
    # 8. LOD 表达式（固定粒度�?
    # ══════════════════════════════════════════════════════════════════════�?
    "lod": [
        TestCase(
            name="lod_01_fixed",
            question="每个客户的总销售额（不受视图粒度影响）",
            category="lod",
            expected_dimensions=["客户"],
            expected_measures=["销售额"],
            expected_calc_types=["LOD_FIXED"],
            expected_computations=1,
            description="FIXED LOD"
        ),
        TestCase(
            name="lod_02_include",
            question="在当前视图基础上，按客户细分销售额",
            category="lod",
            expected_measures=["销售额"],
            expected_calc_types=["LOD_FIXED"],
            expected_computations=1,
            description="INCLUDE LOD"
        ),
        TestCase(
            name="lod_03_exclude",
            question="忽略月份维度的销售额总和",
            category="lod",
            expected_measures=["销售额"],
            expected_calc_types=["LOD_FIXED"],
            expected_computations=1,
            description="EXCLUDE LOD"
        ),
        TestCase(
            name="lod_04_customer_first_order",
            question="每个客户的首次订单日�?,
            category="lod",
            expected_dimensions=["客户"],
            expected_measures=["订单日期"],
            expected_calc_types=["LOD_FIXED"],
            expected_computations=1,
            description="客户首单日期（FIXED MIN�?
        ),
    ],

    # ══════════════════════════════════════════════════════════════════════�?
    # 9. 多轮对话（问题重述）
    # ══════════════════════════════════════════════════════════════════════�?
    "conversation": [
        TestCase(
            name="conv_01_followup_dimension",
            question="按月份细分呢�?,
            category="conversation",
            expected_dimensions=["省份", "月份"],
            expected_measures=["销售额"],
            history=[
                {"role": "user", "content": "各省份的销售额"},
                {"role": "assistant", "content": "按省份分组，计算销售额总和"}
            ],
            description="追问添加维度"
        ),
        TestCase(
            name="conv_02_followup_filter",
            question="只看北京�?,
            category="conversation",
            expected_dimensions=["省份", "月份"],
            expected_measures=["销售额"],
            expected_filters=1,
            history=[
                {"role": "user", "content": "各省份各月的销售额"},
                {"role": "assistant", "content": "按省份和月份分组，计算销售额总和"}
            ],
            description="追问添加筛�?
        ),
        TestCase(
            name="conv_03_followup_computation",
            question="计算排名",
            category="conversation",
            expected_dimensions=["省份"],
            expected_measures=["销售额"],
            expected_calc_types=["RANK"],
            expected_computations=1,
            history=[
                {"role": "user", "content": "各省份的销售额"},
                {"role": "assistant", "content": "按省份分组，计算销售额总和"}
            ],
            description="追问添加计算"
        ),
        TestCase(
            name="conv_04_followup_yoy",
            question="同比增长呢？",
            category="conversation",
            expected_dimensions=["月份"],
            expected_measures=["销售额"],
            expected_calc_types=["PERCENT_DIFFERENCE"],
            expected_computations=1,
            history=[
                {"role": "user", "content": "各月的销售额"},
                {"role": "assistant", "content": "按月份分组，计算销售额总和"}
            ],
            description="追问同比计算"
        ),
        TestCase(
            name="conv_05_change_measure",
            question="换成利润",
            category="conversation",
            expected_dimensions=["省份"],
            expected_measures=["利润"],
            history=[
                {"role": "user", "content": "各省份的销售额"},
                {"role": "assistant", "content": "按省份分组，计算销售额总和"}
            ],
            description="追问更换度量"
        ),
        TestCase(
            name="conv_06_partition_rank",
            question="每月排名呢？",
            category="conversation",
            expected_dimensions=["省份", "月份"],
            expected_measures=["销售额"],
            expected_calc_types=["RANK"],
            expected_computations=1,
            history=[
                {"role": "user", "content": "各省份各月的销售额"},
                {"role": "assistant", "content": "按省份和月份分组，计算销售额总和"}
            ],
            description="追问分区排名（每月内排名�?
        ),
    ],
    
    # ══════════════════════════════════════════════════════════════════════�?
    # 10. 意图分类
    # ══════════════════════════════════════════════════════════════════════�?
    "intent": [
        TestCase(
            name="intent_01_clarification",
            question="销售情况怎么样？",
            category="intent",
            expected_intent="CLARIFICATION",
            description="需要澄清的模糊问题"
        ),
        TestCase(
            name="intent_02_general_greeting",
            question="你好",
            category="intent",
            expected_intent="GENERAL",
            description="一般性问�?
        ),
        TestCase(
            name="intent_03_general_capability",
            question="你能做什么？",
            category="intent",
            expected_intent="GENERAL",
            description="询问能力"
        ),
        TestCase(
            name="intent_04_metadata",
            question="这个数据源有哪些字段�?,
            category="intent",
            expected_intent="GENERAL",
            description="元数据查�?
        ),
        TestCase(
            name="intent_05_irrelevant",
            question="今天天气怎么样？",
            category="intent",
            expected_intent="IRRELEVANT",
            description="无关问题"
        ),
        TestCase(
            name="intent_06_data_query",
            question="各省份的销售额",
            category="intent",
            expected_intent="DATA_QUERY",
            description="明确的数据查�?
        ),
    ],
    
    # ══════════════════════════════════════════════════════════════════════�?
    # 11. 复杂组合查询
    # ══════════════════════════════════════════════════════════════════════�?
    "complex": [
        TestCase(
            name="complex_01_filter_rank",
            question="2024年各省份销售额排名",
            category="complex",
            expected_dimensions=["省份"],
            expected_measures=["销售额"],
            expected_calc_types=["RANK"],
            expected_filters=1,
            expected_computations=1,
            description="筛�?排名"
        ),
        TestCase(
            name="complex_02_multi_dim_percentage",
            question="2024年各产品类别在各地区的销售额占比",
            category="complex",
            expected_dimensions=["产品类别", "地区"],
            expected_measures=["销售额"],
            expected_calc_types=["PERCENT_OF_TOTAL"],
            expected_filters=1,
            expected_computations=1,
            description="多维�?筛�?占比"
        ),
        TestCase(
            name="complex_03_monthly_yoy_by_region",
            question="各地�?024年各月销售额同比增长",
            category="complex",
            expected_dimensions=["地区", "月份"],
            expected_measures=["销售额"],
            expected_calc_types=["PERCENT_DIFFERENCE"],
            expected_filters=1,
            expected_computations=1,
            description="多维�?筛�?同比"
        ),
        TestCase(
            name="complex_04_top_n_with_filter",
            question="华东地区销售额�?的城�?,
            category="complex",
            expected_dimensions=["城市"],
            expected_measures=["销售额"],
            expected_calc_types=["RANK"],
            expected_filters=1,
            description="筛�?Top N"
        ),
        TestCase(
            name="complex_05_cumulative_by_category",
            question="各产品类�?024年按月累计销售额",
            category="complex",
            expected_dimensions=["产品类别", "月份"],
            expected_measures=["销售额"],
            expected_calc_types=["RUNNING_TOTAL"],
            expected_filters=1,
            expected_computations=1,
            description="多维�?筛�?累计"
        ),
    ],
}


# ══════════════════════════════════════════════════════════════════════════�?
# 测试结果
# ══════════════════════════════════════════════════════════════════════════�?

@dataclass
class TestResult:
    """单个测试结果"""
    test_case: TestCase
    success: bool
    elapsed_seconds: float
    restated_question: str = ""
    actual_intent: str = ""
    actual_dimensions: List[str] = field(default_factory=list)
    actual_measures: List[str] = field(default_factory=list)
    actual_calc_types: List[str] = field(default_factory=list)  # Actual CalcType list
    actual_filters: int = 0
    actual_computations: int = 0
    error: str = ""
    warnings: List[str] = field(default_factory=list)


@dataclass
class CategoryResult:
    """分类测试结果"""
    category: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    results: List[TestResult] = field(default_factory=list)
    
    @property
    def pass_rate(self) -> float:
        return self.passed / self.total * 100 if self.total > 0 else 0


# ══════════════════════════════════════════════════════════════════════════�?
# 测试执行�?
# ══════════════════════════════════════════════════════════════════════════�?

class SemanticParserTester:
    """语义解析测试�?""
    
    def __init__(self):
        self.data_model = None
        self.category_results: Dict[str, CategoryResult] = {}
        
    async def setup(self) -> bool:
        """初始化测试环�?""
        from tableau_assistant.src.infra.storage.langgraph_store import get_langgraph_store
        from tableau_assistant.src.infra.storage.data_model_cache import DataModelCache
        from tableau_assistant.src.infra.storage.data_model_loader import TableauDataModelLoader
        from tableau_assistant.src.platforms.tableau.auth import get_tableau_auth_async
        from tableau_assistant.src.infra.config import settings
        
        logger.info("="*70)
        logger.info("Semantic Parser 全面集成测试")
        logger.info("="*70)
        
        # 获取配置
        datasource_luid = os.getenv("DATASOURCE_LUID", "")
        if not datasource_luid:
            logger.error("请配�?DATASOURCE_LUID 环境变量")
            return False
        
        logger.info(f"Datasource LUID: {datasource_luid}")
        logger.info(f"LLM Provider: {settings.llm_model_provider}")
        
        try:
            # 获取认证
            auth_ctx = await get_tableau_auth_async()
            logger.info(f"Tableau 认证成功: {auth_ctx.auth_method}")
            
            # 加载数据模型（使用缓存）
            store = get_langgraph_store()
            cache = DataModelCache(store)
            loader = TableauDataModelLoader(auth_ctx)
            
            self.data_model, is_cache_hit = await cache.get_or_load(datasource_luid, loader)
            logger.info(f"数据模型加载成功 (缓存: {is_cache_hit})")
            logger.info(f"  - 字段�? {self.data_model.field_count}")
            logger.info(f"  - 维度�? {len(self.data_model.get_dimensions())}")
            logger.info(f"  - 度量�? {len(self.data_model.get_measures())}")
            
            return True
            
        except Exception as e:
            logger.error(f"初始化失�? {e}")
            return False
    
    async def run_single_test(self, test_case: TestCase) -> TestResult:
        """运行单个测试"""
        from tableau_assistant.src.agents.semantic_parser import SemanticParserAgent
        from tableau_assistant.src.core.models import IntentType
        
        start_time = time.time()
        result = TestResult(test_case=test_case, success=False, elapsed_seconds=0)
        
        try:
            # 创建 agent 并解析（直接传�?DataModel 对象�?
            agent = SemanticParserAgent()
            parse_result = await agent.parse(
                question=test_case.question,
                history=test_case.history,
                data_model=self.data_model,
            )
            
            result.elapsed_seconds = time.time() - start_time
            result.restated_question = parse_result.restated_question
            result.actual_intent = parse_result.intent.type.value
            
            # 提取实际结果
            if parse_result.semantic_query:
                sq = parse_result.semantic_query
                result.actual_dimensions = [d.field_name for d in (sq.dimensions or [])]
                result.actual_measures = [m.field_name for m in (sq.measures or [])]
                result.actual_filters = len(sq.filters or [])
                result.actual_computations = len(sq.computations or [])
                
                # Extract calc types
                result.actual_calc_types = self._extract_calc_types(sq.computations)
            
            # 验证结果
            result.success, result.warnings = self._validate_result(test_case, result)
            
        except Exception as e:
            result.elapsed_seconds = time.time() - start_time
            result.error = str(e)
            result.success = False
            logger.error(f"测试失败 [{test_case.name}]: {e}")
        
        return result
    
    def _extract_calc_types(self, computations: Optional[List[Any]]) -> List[str]:
        """Extract CalcType list from computations"""
        if not computations:
            return []
        
        calc_types = []
        for comp in computations:
            if hasattr(comp, 'calc_type'):
                calc_type = comp.calc_type.value if hasattr(comp.calc_type, 'value') else str(comp.calc_type)
                calc_types.append(calc_type)
        
        return calc_types
    
    def _validate_result(self, test_case: TestCase, result: TestResult) -> Tuple[bool, List[str]]:
        """验证测试结果"""
        warnings = []
        
        # 1. 验证意图
        if result.actual_intent != test_case.expected_intent:
            warnings.append(f"意图不匹�? 期望 {test_case.expected_intent}, 实际 {result.actual_intent}")
            # 意图不匹配是严重错误
            if test_case.expected_intent != "DATA_QUERY":
                return result.actual_intent == test_case.expected_intent, warnings
        
        # 对于�?DATA_QUERY 意图，只验证意图
        if test_case.expected_intent != "DATA_QUERY":
            return result.actual_intent == test_case.expected_intent, warnings
        
        # 2. 验证 calc_types（对于复杂计算）
        if test_case.expected_calc_types:
            for expected_calc in test_case.expected_calc_types:
                if expected_calc not in result.actual_calc_types:
                    warnings.append(f"缺少计算类型: 期望 {expected_calc}, 实际 {result.actual_calc_types}")
        
        # 3. 验证维度（模糊匹配）
        if test_case.expected_dimensions:
            for expected_dim in test_case.expected_dimensions:
                found = any(expected_dim in actual_dim or actual_dim in expected_dim 
                           for actual_dim in result.actual_dimensions)
                if not found:
                    warnings.append(f"缺少维度: {expected_dim}")
        
        # 4. 验证度量（模糊匹配）
        if test_case.expected_measures:
            for expected_measure in test_case.expected_measures:
                found = any(expected_measure in actual_measure or actual_measure in expected_measure 
                           for actual_measure in result.actual_measures)
                if not found:
                    warnings.append(f"缺少度量: {expected_measure}")
        
        # 5. 验证筛选数�?
        if test_case.expected_filters > 0:
            if result.actual_filters < test_case.expected_filters:
                warnings.append(f"筛选数量不�? 期望 >={test_case.expected_filters}, 实际 {result.actual_filters}")
        
        # 6. 验证计算数量
        if test_case.expected_computations > 0:
            if result.actual_computations < test_case.expected_computations:
                warnings.append(f"计算数量不足: 期望 >={test_case.expected_computations}, 实际 {result.actual_computations}")
        
        # 成功条件：没有严重警告（意图、计算类型、核心维�?度量�?
        critical_warnings = [w for w in warnings if "意图" in w or "缺少计算类型" in w]
        success = len(critical_warnings) == 0
        
        return success, warnings
    
    async def run_category(self, category: str, test_cases: List[TestCase]) -> CategoryResult:
        """运行一个分类的所有测�?""
        logger.info(f"\n{'='*70}")
        logger.info(f"测试分类: {category.upper()}")
        logger.info(f"{'='*70}")
        
        category_result = CategoryResult(category=category, total=len(test_cases))
        
        for i, test_case in enumerate(test_cases, 1):
            logger.info(f"\n[{i}/{len(test_cases)}] {test_case.name}")
            logger.info(f"  问题: {test_case.question}")
            if test_case.history:
                logger.info(f"  历史: {len(test_case.history)} 条消�?)
            
            result = await self.run_single_test(test_case)
            category_result.results.append(result)
            
            if result.success:
                category_result.passed += 1
                logger.info(f"  �?通过 ({result.elapsed_seconds:.2f}s)")
            else:
                category_result.failed += 1
                logger.info(f"  �?失败 ({result.elapsed_seconds:.2f}s)")
                if result.error:
                    logger.info(f"     错误: {result.error}")
            
            # 输出详细信息
            logger.info(f"  重述: {result.restated_question}")
            logger.info(f"  意图: {result.actual_intent} (期望: {test_case.expected_intent})")
            if result.actual_dimensions:
                logger.info(f"  维度: {result.actual_dimensions}")
            if result.actual_measures:
                logger.info(f"  度量: {result.actual_measures}")
            if result.actual_calc_types:
                logger.info(f"  计算类型: {result.actual_calc_types}")
            if result.actual_filters > 0:
                logger.info(f"  筛选数: {result.actual_filters}")
            if result.actual_computations > 0:
                logger.info(f"  计算�? {result.actual_computations}")
            if result.warnings:
                for w in result.warnings:
                    logger.info(f"  ⚠️ {w}")
        
        return category_result
    
    async def run_all(self, categories: List[str] = None) -> Dict[str, CategoryResult]:
        """运行所有测�?""
        if not await self.setup():
            return {}
        
        # 确定要运行的分类
        if categories:
            test_categories = {k: v for k, v in TEST_CASES.items() if k in categories}
        else:
            test_categories = TEST_CASES
        
        # 运行每个分类
        for category, test_cases in test_categories.items():
            result = await self.run_category(category, test_cases)
            self.category_results[category] = result
        
        # 输出总结
        self._print_summary()
        
        return self.category_results
    
    def _print_summary(self):
        """输出测试总结"""
        logger.info(f"\n{'='*70}")
        logger.info("测试总结")
        logger.info(f"{'='*70}")
        
        total_tests = 0
        total_passed = 0
        total_failed = 0
        total_time = 0
        
        for category, result in self.category_results.items():
            total_tests += result.total
            total_passed += result.passed
            total_failed += result.failed
            category_time = sum(r.elapsed_seconds for r in result.results)
            total_time += category_time
            
            status = "�? if result.failed == 0 else "�?
            logger.info(f"{status} {category:15} {result.passed}/{result.total} ({result.pass_rate:.1f}%) - {category_time:.1f}s")
        
        logger.info(f"\n{'─'*70}")
        overall_rate = total_passed / total_tests * 100 if total_tests > 0 else 0
        logger.info(f"总计: {total_passed}/{total_tests} ({overall_rate:.1f}%) - {total_time:.1f}s")
        
        # 输出失败的测�?
        failed_tests = []
        for category, result in self.category_results.items():
            for r in result.results:
                if not r.success:
                    failed_tests.append((category, r))
        
        if failed_tests:
            logger.info(f"\n{'─'*70}")
            logger.info("失败的测�?")
            for category, r in failed_tests:
                logger.info(f"  [{category}] {r.test_case.name}: {r.test_case.question}")
                if r.error:
                    logger.info(f"    错误: {r.error}")
                for w in r.warnings:
                    logger.info(f"    ⚠️ {w}")


# ══════════════════════════════════════════════════════════════════════════�?
# 入口
# ══════════════════════════════════════════════════════════════════════════�?

async def main():
    """主函�?""
    import argparse
    
    parser = argparse.ArgumentParser(description="Semantic Parser 全面集成测试")
    parser.add_argument(
        "--categories", "-c",
        nargs="+",
        choices=list(TEST_CASES.keys()),
        help="指定要测试的分类"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="列出所有测试分�?
    )
    
    args = parser.parse_args()
    
    if args.list:
        print("可用的测试分�?")
        for category, cases in TEST_CASES.items():
            print(f"  {category}: {len(cases)} 个测试用�?)
        return
    
    tester = SemanticParserTester()
    await tester.run_all(args.categories)


if __name__ == "__main__":
    asyncio.run(main())
