# -*- coding: utf-8 -*-
"""
Quick Table Calc Refactor - Integration Tests

使用真实环境、真实数据和真实 LLM 进行端到端测试。
测试场景：
- 9.1 排名场景端到端测试
- 9.2 累计场景端到端测试
- 9.3 增长率场景端到端测试
- 9.4 LOD + 表计算组合场景端到端测试

运行方式:
    python tableau_assistant/tests/integration/test_quick_table_calc_integration.py

或者使用 pytest:
    pytest tableau_assistant/tests/integration/test_quick_table_calc_integration.py -v -s

Requirements: 1.3, 5.5-5.10, 7.1-7.4
"""
import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass, field
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


# ═══════════════════════════════════════════════════════════════════════════
# 测试用例定义
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class QuickTableCalcTestCase:
    """快速表计算测试用例"""
    name: str
    question: str
    category: str
    expected_intent: str = "DATA_QUERY"
    expected_how_type: str = "COMPLEX"  # 快速表计算都是 COMPLEX
    expected_calc_types: List[str] = field(default_factory=list)
    expected_vizql_calc_type: str = ""  # 期望的 VizQL tableCalcType
    expected_dimensions: List[str] = field(default_factory=list)
    expected_measures: List[str] = field(default_factory=list)
    expected_filters: int = 0
    expected_computations: int = 1
    history: List[Dict[str, str]] = field(default_factory=list)
    description: str = ""
    validate_vizql: bool = True  # 是否验证 VizQL 输出


# ═══════════════════════════════════════════════════════════════════════════
# 测试用例分类
# ═══════════════════════════════════════════════════════════════════════════

TEST_CASES: Dict[str, List[QuickTableCalcTestCase]] = {
    # ═══════════════════════════════════════════════════════════════════════
    # 9.1 排名场景端到端测试
    # ═══════════════════════════════════════════════════════════════════════
    "ranking": [
        QuickTableCalcTestCase(
            name="rank_01_simple",
            question="各省份销售额排名",
            category="ranking",
            expected_calc_types=["RANK"],
            expected_vizql_calc_type="RANK",
            expected_dimensions=["省份"],
            expected_measures=["销售额"],
            description="简单排名 - RANK"
        ),
        QuickTableCalcTestCase(
            name="rank_02_top_n",
            question="销售额前10的省份",
            category="ranking",
            expected_how_type="SIMPLE",  # Top N is SIMPLE with filter, not COMPLEX with computation
            expected_calc_types=[],  # No computation needed
            expected_vizql_calc_type="",  # No table calc
            expected_dimensions=["省份"],
            expected_measures=["销售额"],
            expected_filters=1,  # TOP_N filter
            expected_computations=0,  # No computation
            description="Top N 过滤 - 使用 TOP_N filter 而非 RANK 计算"
        ),
        QuickTableCalcTestCase(
            name="rank_03_bottom_n",
            question="销售额最低的5个城市",
            category="ranking",
            expected_how_type="SIMPLE",  # Bottom N is SIMPLE with filter, not COMPLEX with computation
            expected_calc_types=[],  # No computation needed
            expected_vizql_calc_type="",  # No table calc
            expected_dimensions=["城市"],
            expected_measures=["销售额"],
            expected_filters=1,  # TOP_N filter
            expected_computations=0,  # No computation
            description="Bottom N 过滤 - 使用 TOP_N filter 而非 RANK 计算"
        ),
        QuickTableCalcTestCase(
            name="rank_04_partition",
            question="每月各省份的销售额排名",
            category="ranking",
            expected_calc_types=["RANK"],
            expected_vizql_calc_type="RANK",
            expected_dimensions=["月份", "省份"],
            expected_measures=["销售额"],
            description="分区排名 - 按月分区"
        ),
        QuickTableCalcTestCase(
            name="rank_05_dense",
            question="各产品类别销售额密集排名",
            category="ranking",
            expected_calc_types=["RANK", "DENSE_RANK"],  # 可能是 RANK 或 DENSE_RANK
            expected_vizql_calc_type="RANK",
            expected_dimensions=["产品类别"],
            expected_measures=["销售额"],
            description="密集排名 - DENSE_RANK"
        ),
        QuickTableCalcTestCase(
            name="rank_06_percentile",
            question="各省份销售额百分位排名",
            category="ranking",
            expected_calc_types=["PERCENTILE", "RANK"],
            expected_vizql_calc_type="PERCENTILE",
            expected_dimensions=["省份"],
            expected_measures=["销售额"],
            description="百分位排名 - PERCENTILE"
        ),
    ],
    
    # ═══════════════════════════════════════════════════════════════════════
    # 9.2 累计场景端到端测试
    # ═══════════════════════════════════════════════════════════════════════
    "cumulative": [
        QuickTableCalcTestCase(
            name="running_01_simple",
            question="各月累计销售额",
            category="cumulative",
            expected_calc_types=["RUNNING_TOTAL"],
            expected_vizql_calc_type="RUNNING_TOTAL",
            expected_dimensions=["月份"],
            expected_measures=["销售额"],
            description="简单累计 - RUNNING_TOTAL"
        ),
        QuickTableCalcTestCase(
            name="running_02_ytd",
            question="按月显示年初至今的累计销售额",
            category="cumulative",
            expected_calc_types=["RUNNING_TOTAL"],
            expected_vizql_calc_type="RUNNING_TOTAL",
            expected_dimensions=["月份"],
            expected_measures=["销售额"],
            description="年初至今 - YTD (按月累计)"
        ),
        QuickTableCalcTestCase(
            name="running_03_partition",
            question="各地区按月累计销售额",
            category="cumulative",
            expected_calc_types=["RUNNING_TOTAL"],
            expected_vizql_calc_type="RUNNING_TOTAL",
            expected_dimensions=["地区", "月份"],
            expected_measures=["销售额"],
            description="分区累计 - 按地区分区"
        ),
        QuickTableCalcTestCase(
            name="running_04_restart",
            question="各年度按月累计销售额（每年重新开始）",
            category="cumulative",
            expected_calc_types=["RUNNING_TOTAL"],
            expected_vizql_calc_type="RUNNING_TOTAL",
            expected_dimensions=["年", "月份"],
            expected_measures=["销售额"],
            description="带重启的累计 - restart_every"
        ),
        QuickTableCalcTestCase(
            name="moving_01_avg",
            question="各月销售额3个月移动平均",
            category="cumulative",
            expected_calc_types=["MOVING_CALC"],
            expected_vizql_calc_type="MOVING_CALCULATION",
            expected_dimensions=["月份"],
            expected_measures=["销售额"],
            description="移动平均 - MOVING_CALC"
        ),
        QuickTableCalcTestCase(
            name="moving_02_sum",
            question="各月销售额滚动3个月总和",
            category="cumulative",
            expected_calc_types=["MOVING_CALC"],
            expected_vizql_calc_type="MOVING_CALCULATION",
            expected_dimensions=["月份"],
            expected_measures=["销售额"],
            description="移动总和 - MOVING_CALC SUM"
        ),
    ],
    
    # ═══════════════════════════════════════════════════════════════════════
    # 9.3 增长率场景端到端测试
    # ═══════════════════════════════════════════════════════════════════════
    "growth": [
        QuickTableCalcTestCase(
            name="diff_01_simple",
            question="各月销售额与上月的差异",
            category="growth",
            expected_calc_types=["DIFFERENCE"],
            expected_vizql_calc_type="DIFFERENCE_FROM",
            expected_dimensions=["月份"],
            expected_measures=["销售额"],
            description="简单差异 - DIFFERENCE"
        ),
        QuickTableCalcTestCase(
            name="pct_diff_01_mom",
            question="各月销售额环比增长率",
            category="growth",
            expected_calc_types=["PERCENT_DIFFERENCE"],
            expected_vizql_calc_type="PERCENT_DIFFERENCE_FROM",
            expected_dimensions=["月份"],
            expected_measures=["销售额"],
            description="环比增长率 - MoM"
        ),
        QuickTableCalcTestCase(
            name="pct_diff_02_yoy",
            question="各月销售额同比增长率",
            category="growth",
            expected_calc_types=["PERCENT_DIFFERENCE"],
            expected_vizql_calc_type="PERCENT_DIFFERENCE_FROM",
            expected_dimensions=["月份"],
            expected_measures=["销售额"],
            description="同比增长率 - YoY"
        ),
        QuickTableCalcTestCase(
            name="pct_diff_03_partition",
            question="各地区销售额同比变化",
            category="growth",
            expected_calc_types=["PERCENT_DIFFERENCE"],
            expected_vizql_calc_type="PERCENT_DIFFERENCE_FROM",
            expected_dimensions=["地区"],
            expected_measures=["销售额"],
            description="分区同比 - 按地区"
        ),
        QuickTableCalcTestCase(
            name="pct_diff_04_vs_first",
            question="各月销售额相对于首月的增长率",
            category="growth",
            expected_calc_types=["PERCENT_DIFFERENCE"],
            expected_vizql_calc_type="PERCENT_DIFFERENCE_FROM",
            expected_dimensions=["月份"],
            expected_measures=["销售额"],
            description="相对首月增长 - relative_to=FIRST"
        ),
    ],
    
    # ═══════════════════════════════════════════════════════════════════════
    # 9.4 占比场景端到端测试
    # ═══════════════════════════════════════════════════════════════════════
    "percentage": [
        QuickTableCalcTestCase(
            name="pct_01_total",
            question="各省份销售额占比",
            category="percentage",
            expected_calc_types=["PERCENT_OF_TOTAL"],
            expected_vizql_calc_type="PERCENT_OF_TOTAL",
            expected_dimensions=["省份"],
            expected_measures=["销售额"],
            description="占总体比例 - PERCENT_OF_TOTAL"
        ),
        QuickTableCalcTestCase(
            name="pct_02_partition",
            question="各产品在每个地区的销售额占比",
            category="percentage",
            expected_calc_types=["PERCENT_OF_TOTAL"],
            expected_vizql_calc_type="PERCENT_OF_TOTAL",
            expected_dimensions=["地区", "产品"],
            expected_measures=["销售额"],
            description="分区占比 - 按地区分区"
        ),
        QuickTableCalcTestCase(
            name="pct_03_market_share",
            question="各产品类别的市场份额",
            category="percentage",
            expected_calc_types=["PERCENT_OF_TOTAL"],
            expected_vizql_calc_type="PERCENT_OF_TOTAL",
            expected_dimensions=["产品类别"],
            expected_measures=["销售额"],
            description="市场份额"
        ),
    ],
    
    # ═══════════════════════════════════════════════════════════════════════
    # 9.5 LOD 场景端到端测试
    # LOD 用于改变聚合粒度，典型场景：
    # - FIXED: 固定到某个维度计算，忽略视图粒度
    # - INCLUDE: 在视图粒度基础上增加维度
    # - EXCLUDE: 在视图粒度基础上排除维度
    # ═══════════════════════════════════════════════════════════════════════
    "lod": [
        QuickTableCalcTestCase(
            name="lod_01_fixed_customer_total",
            question="显示每个订单，同时显示该客户的历史总销售额（固定到客户级别计算，不受订单粒度影响）",
            category="lod",
            expected_calc_types=["LOD_FIXED"],
            expected_dimensions=["订单", "客户"],
            expected_measures=["销售额"],
            validate_vizql=False,  # LOD 生成 calculation 而非 tableCalculation
            description="FIXED LOD - 客户级别总销售额（不受订单粒度影响）"
        ),
        QuickTableCalcTestCase(
            name="lod_02_fixed_first_purchase",
            question="计算每个客户的首次购买日期（固定到客户级别，取最早订单日期）",
            category="lod",
            expected_calc_types=["LOD_FIXED"],
            expected_dimensions=["客户"],
            expected_measures=["订单日期"],
            validate_vizql=False,
            description="FIXED LOD - 客户首次购买日期 (MIN)"
        ),
        QuickTableCalcTestCase(
            name="lod_03_fixed_avg_order",
            question="计算每个客户的平均订单金额（固定到客户级别计算）",
            category="lod",
            expected_calc_types=["LOD_FIXED"],
            expected_dimensions=["客户"],
            expected_measures=["订单金额"],
            validate_vizql=False,
            description="FIXED LOD - 客户平均订单金额"
        ),
        QuickTableCalcTestCase(
            name="lod_04_exclude_month",
            question="各月销售额与年度总销售额的对比（年度总额需排除月份维度计算）",
            category="lod",
            expected_calc_types=["LOD_EXCLUDE", "LOD_FIXED"],
            expected_dimensions=["月份", "年"],
            expected_measures=["销售额"],
            validate_vizql=False,
            description="EXCLUDE LOD - 排除月份维度得到年度总额"
        ),
        QuickTableCalcTestCase(
            name="lod_05_include_product",
            question="在地区汇总视图中，显示每个地区各产品的销售额明细（在地区基础上增加产品维度计算）",
            category="lod",
            expected_calc_types=["LOD_INCLUDE", "LOD_FIXED"],
            expected_dimensions=["地区", "产品"],
            expected_measures=["销售额"],
            validate_vizql=False,
            description="INCLUDE LOD - 在地区基础上增加产品维度"
        ),
    ],
    
    # ═══════════════════════════════════════════════════════════════════════
    # 9.6 LOD + 表计算组合场景端到端测试
    # 典型组合场景：
    # - 先用 LOD 计算固定粒度的值，再用表计算进行排名/占比/累计
    # ═══════════════════════════════════════════════════════════════════════
    "combination": [
        QuickTableCalcTestCase(
            name="combo_01_customer_rank_by_first_purchase",
            question="按客户首次购买日期对客户进行排名（先固定到客户级别计算首次购买日期，再排名）",
            category="combination",
            expected_calc_types=["LOD_FIXED", "RANK"],
            expected_dimensions=["客户"],
            expected_computations=2,
            validate_vizql=False,  # 组合场景需要特殊验证
            description="LOD(首次购买日期) + RANK 组合"
        ),
        QuickTableCalcTestCase(
            name="combo_02_customer_sales_pct_of_region",
            question="每个客户的销售额占其所在地区总销售额的百分比（先固定到地区级别计算总额，再计算占比）",
            category="combination",
            expected_calc_types=["LOD_FIXED", "PERCENT_OF_TOTAL"],
            expected_dimensions=["客户", "地区"],
            expected_measures=["销售额"],
            expected_computations=2,
            validate_vizql=False,
            description="LOD(地区总额) + PERCENT_OF_TOTAL 组合"
        ),
        QuickTableCalcTestCase(
            name="combo_03_new_customer_cumulative",
            question="按首次购买日期统计累计新客户数（先固定到客户级别计算首次购买日期，再按日期累计）",
            category="combination",
            expected_calc_types=["LOD_FIXED", "RUNNING_TOTAL"],
            expected_dimensions=["购买日期"],
            expected_computations=2,
            validate_vizql=False,
            description="LOD(购买日期) + RUNNING_TOTAL 组合"
        ),
        QuickTableCalcTestCase(
            name="combo_04_customer_avg_vs_total_rank",
            question="按客户平均订单金额排名（先固定到客户级别计算平均订单金额，再排名）",
            category="combination",
            expected_calc_types=["LOD_FIXED", "RANK"],
            expected_dimensions=["客户"],
            expected_measures=["订单金额"],
            expected_computations=2,
            validate_vizql=False,
            description="LOD(客户平均订单) + RANK 组合"
        ),
    ],
}


# ═══════════════════════════════════════════════════════════════════════════
# 测试结果
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class TestResult:
    """单个测试结果"""
    test_case: QuickTableCalcTestCase
    success: bool
    elapsed_seconds: float
    restated_question: str = ""
    actual_intent: str = ""
    actual_how_type: str = ""
    actual_calc_types: List[str] = field(default_factory=list)
    actual_vizql_calc_type: str = ""
    actual_dimensions: List[str] = field(default_factory=list)
    actual_measures: List[str] = field(default_factory=list)
    actual_filters: int = 0
    actual_computations: int = 0
    vizql_output: Dict[str, Any] = field(default_factory=dict)
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


# ═══════════════════════════════════════════════════════════════════════════
# 测试执行器
# ═══════════════════════════════════════════════════════════════════════════

class QuickTableCalcTester:
    """快速表计算集成测试器"""
    
    def __init__(self):
        self.data_model = None
        self.category_results: Dict[str, CategoryResult] = {}
        self.query_builder = None
        self.enable_streaming = True  # Default to streaming enabled
        
    async def setup(self) -> bool:
        """初始化测试环境"""
        from tableau_assistant.src.infra.storage.langgraph_store import get_langgraph_store
        from tableau_assistant.src.infra.storage.data_model_cache import DataModelCache
        from tableau_assistant.src.infra.storage.data_model_loader import TableauDataModelLoader
        from tableau_assistant.src.platforms.tableau.auth import get_tableau_auth_async
        from tableau_assistant.src.platforms.tableau.query_builder import TableauQueryBuilder
        from tableau_assistant.src.infra.config import settings
        
        logger.info("="*70)
        logger.info("Quick Table Calc Refactor - Integration Tests")
        logger.info("="*70)
        
        # 获取配置
        datasource_luid = os.getenv("DATASOURCE_LUID", "")
        if not datasource_luid:
            logger.error("请配置 DATASOURCE_LUID 环境变量")
            return False
        
        logger.info(f"Datasource LUID: {datasource_luid}")
        logger.info(f"LLM Provider: {settings.llm_model_provider}")
        logger.info(f"Streaming: {'Enabled' if self.enable_streaming else 'Disabled'}")
        
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
            logger.info(f"  - 字段数: {self.data_model.field_count}")
            logger.info(f"  - 维度数: {len(self.data_model.get_dimensions())}")
            logger.info(f"  - 度量数: {len(self.data_model.get_measures())}")
            
            # 初始化 QueryBuilder
            self.query_builder = TableauQueryBuilder()
            logger.info("TableauQueryBuilder 初始化成功")
            
            return True
            
        except Exception as e:
            logger.error(f"初始化失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def run_single_test(self, test_case: QuickTableCalcTestCase, enable_streaming: bool = True) -> TestResult:
        """运行单个测试
        
        Args:
            test_case: 测试用例
            enable_streaming: 是否启用流式输出（默认 True）
        """
        from tableau_assistant.src.agents.semantic_parser import SemanticParserAgent
        from tableau_assistant.src.core.models import IntentType, HowType
        from langchain_core.callbacks import AsyncCallbackHandler
        
        # Custom async callback handler for streaming output
        class StreamingPrintHandler(AsyncCallbackHandler):
            """Print tokens to console in real-time (async version)"""
            
            def __init__(self):
                self.token_count = 0
                self.step_count = 0
            
            async def on_llm_start(self, serialized, prompts, **kwargs):
                """Called when LLM starts"""
                self.step_count += 1
                step_name = "Step 1" if self.step_count == 1 else f"Step {self.step_count}"
                print(f"\n  📝 [{step_name} Streaming] ", end="", flush=True)
            
            async def on_llm_new_token(self, token: str, **kwargs):
                """Called for each new token"""
                self.token_count += 1
                # Print token directly to console
                print(token, end="", flush=True)
            
            async def on_llm_end(self, response, **kwargs):
                """Called when LLM ends"""
                print(f"\n  ✓ ({self.token_count} tokens)")
                self.token_count = 0
        
        start_time = time.time()
        result = TestResult(test_case=test_case, success=False, elapsed_seconds=0)
        
        try:
            # 创建 agent 并解析
            agent = SemanticParserAgent()
            
            # 配置流式输出回调
            config = None
            if enable_streaming:
                streaming_handler = StreamingPrintHandler()
                config = {"callbacks": [streaming_handler]}
            
            parse_result = await agent.parse(
                question=test_case.question,
                history=test_case.history,
                data_model=self.data_model,
                config=config,
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
                
                # 提取 calc_types
                result.actual_calc_types = self._extract_calc_types(sq.computations)
                
                # 构建 VizQL 输出并验证
                if test_case.validate_vizql and sq.computations:
                    try:
                        vizql_request = self.query_builder.build(sq)
                        result.vizql_output = vizql_request
                        
                        # 提取 VizQL tableCalcType
                        result.actual_vizql_calc_type = self._extract_vizql_calc_type(vizql_request)
                    except Exception as e:
                        result.warnings.append(f"VizQL 构建失败: {e}")
            
            # 验证结果
            result.success, result.warnings = self._validate_result(test_case, result)
            
        except Exception as e:
            result.elapsed_seconds = time.time() - start_time
            result.error = str(e)
            result.success = False
            logger.error(f"测试失败 [{test_case.name}]: {e}")
            import traceback
            traceback.print_exc()
        
        return result
    
    def _extract_calc_types(self, computations: Optional[List[Any]]) -> List[str]:
        """从 computations 提取 CalcType 列表"""
        if not computations:
            return []
        
        calc_types = []
        for comp in computations:
            if hasattr(comp, 'calc_type'):
                calc_type = comp.calc_type.value if hasattr(comp.calc_type, 'value') else str(comp.calc_type)
                calc_types.append(calc_type)
        
        return calc_types
    
    def _extract_vizql_calc_type(self, vizql_request: Dict[str, Any]) -> str:
        """从 VizQL 请求提取 tableCalcType"""
        fields = vizql_request.get("fields", [])
        for field in fields:
            if "tableCalculation" in field:
                return field["tableCalculation"].get("tableCalcType", "")
        return ""
    
    def _validate_result(
        self, test_case: QuickTableCalcTestCase, result: TestResult
    ) -> Tuple[bool, List[str]]:
        """验证测试结果"""
        warnings = []
        
        # 1. 验证意图
        if result.actual_intent != test_case.expected_intent:
            warnings.append(f"意图不匹配: 期望 {test_case.expected_intent}, 实际 {result.actual_intent}")
            return False, warnings
        
        # 2. 验证 calc_types（核心验证）
        if test_case.expected_calc_types:
            found_any = False
            for expected_calc in test_case.expected_calc_types:
                if expected_calc in result.actual_calc_types:
                    found_any = True
                    break
            if not found_any:
                warnings.append(f"缺少计算类型: 期望 {test_case.expected_calc_types} 之一, 实际 {result.actual_calc_types}")
        
        # 3. 验证 VizQL tableCalcType
        if test_case.validate_vizql and test_case.expected_vizql_calc_type:
            if result.actual_vizql_calc_type != test_case.expected_vizql_calc_type:
                warnings.append(f"VizQL 类型不匹配: 期望 {test_case.expected_vizql_calc_type}, 实际 {result.actual_vizql_calc_type}")
        
        # 4. 验证计算数量
        if test_case.expected_computations > 0:
            if result.actual_computations < test_case.expected_computations:
                warnings.append(f"计算数量不足: 期望 >={test_case.expected_computations}, 实际 {result.actual_computations}")
        
        # 4.1 验证过滤器数量（用于 TOP_N 等场景）
        if test_case.expected_filters > 0:
            if result.actual_filters < test_case.expected_filters:
                warnings.append(f"过滤器数量不足: 期望 >={test_case.expected_filters}, 实际 {result.actual_filters}")
        
        # 5. 验证维度（模糊匹配）
        if test_case.expected_dimensions:
            for expected_dim in test_case.expected_dimensions:
                found = any(expected_dim in actual_dim or actual_dim in expected_dim 
                           for actual_dim in result.actual_dimensions)
                if not found:
                    warnings.append(f"缺少维度: {expected_dim}")
        
        # 6. 验证度量（模糊匹配）
        if test_case.expected_measures:
            for expected_measure in test_case.expected_measures:
                found = any(expected_measure in actual_measure or actual_measure in expected_measure 
                           for actual_measure in result.actual_measures)
                if not found:
                    warnings.append(f"缺少度量: {expected_measure}")
        
        # 成功条件：没有严重警告（意图、计算类型）
        critical_warnings = [w for w in warnings if "意图" in w or "缺少计算类型" in w or "VizQL 类型" in w]
        success = len(critical_warnings) == 0
        
        return success, warnings
    
    async def run_category(self, category: str, test_cases: List[QuickTableCalcTestCase]) -> CategoryResult:
        """运行一个分类的所有测试"""
        logger.info(f"\n{'='*70}")
        logger.info(f"测试分类: {category.upper()}")
        logger.info(f"{'='*70}")
        
        category_result = CategoryResult(category=category, total=len(test_cases))
        
        for i, test_case in enumerate(test_cases, 1):
            logger.info(f"\n[{i}/{len(test_cases)}] {test_case.name}")
            logger.info(f"  问题: {test_case.question}")
            logger.info(f"  描述: {test_case.description}")
            
            result = await self.run_single_test(test_case, enable_streaming=self.enable_streaming)
            category_result.results.append(result)
            
            if result.success:
                category_result.passed += 1
                logger.info(f"  ✅ 通过 ({result.elapsed_seconds:.2f}s)")
            else:
                category_result.failed += 1
                logger.info(f"  ❌ 失败 ({result.elapsed_seconds:.2f}s)")
                if result.error:
                    logger.info(f"     错误: {result.error}")
            
            # 输出详细信息
            logger.info(f"  重述: {result.restated_question}")
            logger.info(f"  意图: {result.actual_intent}")
            if result.actual_calc_types:
                logger.info(f"  CalcType: {result.actual_calc_types}")
            if result.actual_vizql_calc_type:
                logger.info(f"  VizQL Type: {result.actual_vizql_calc_type}")
            if result.actual_dimensions:
                logger.info(f"  维度: {result.actual_dimensions}")
            if result.actual_measures:
                logger.info(f"  度量: {result.actual_measures}")
            if result.actual_computations > 0:
                logger.info(f"  计算数: {result.actual_computations}")
            if result.warnings:
                for w in result.warnings:
                    logger.info(f"  ⚠️ {w}")
        
        return category_result
    
    async def run_all(self, categories: List[str] = None) -> Dict[str, CategoryResult]:
        """运行所有测试"""
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
            
            status = "✅" if result.failed == 0 else "❌"
            logger.info(f"{status} {category:15} {result.passed}/{result.total} ({result.pass_rate:.1f}%) - {category_time:.1f}s")
        
        logger.info(f"\n{'─'*70}")
        overall_rate = total_passed / total_tests * 100 if total_tests > 0 else 0
        logger.info(f"总计: {total_passed}/{total_tests} ({overall_rate:.1f}%) - {total_time:.1f}s")
        
        # 输出失败的测试
        failed_tests = []
        for category, result in self.category_results.items():
            for r in result.results:
                if not r.success:
                    failed_tests.append((category, r))
        
        if failed_tests:
            logger.info(f"\n{'─'*70}")
            logger.info("失败的测试:")
            for category, r in failed_tests:
                logger.info(f"  [{category}] {r.test_case.name}: {r.test_case.question}")
                if r.error:
                    logger.info(f"    错误: {r.error}")
                for w in r.warnings:
                    logger.info(f"    ⚠️ {w}")


# ═══════════════════════════════════════════════════════════════════════════
# VizQL 输出验证
# ═══════════════════════════════════════════════════════════════════════════

def validate_vizql_output(vizql_request: Dict[str, Any], expected_calc_type: str) -> Tuple[bool, str]:
    """验证 VizQL 输出格式"""
    fields = vizql_request.get("fields", [])
    
    for field in fields:
        if "tableCalculation" in field:
            table_calc = field["tableCalculation"]
            actual_type = table_calc.get("tableCalcType", "")
            
            if actual_type == expected_calc_type:
                return True, f"VizQL tableCalcType 匹配: {actual_type}"
            else:
                return False, f"VizQL tableCalcType 不匹配: 期望 {expected_calc_type}, 实际 {actual_type}"
        
        if "calculation" in field:
            # LOD 表达式
            calc = field.get("calculation", "")
            if "FIXED" in calc or "INCLUDE" in calc or "EXCLUDE" in calc:
                return True, f"LOD 表达式: {calc}"
    
    return False, "未找到 tableCalculation 或 calculation"


# ═══════════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Quick Table Calc Refactor - Integration Tests")
    parser.add_argument(
        "--categories", "-c",
        nargs="+",
        choices=list(TEST_CASES.keys()),
        help="指定要测试的分类"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="列出所有测试分类"
    )
    parser.add_argument(
        "--stream", "-s",
        action="store_true",
        default=True,
        help="启用流式输出（默认启用）"
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="禁用流式输出"
    )
    
    args = parser.parse_args()
    
    if args.list:
        print("可用的测试分类:")
        for category, cases in TEST_CASES.items():
            print(f"  {category}: {len(cases)} 个测试用例")
        return
    
    # Determine streaming mode
    enable_streaming = not args.no_stream
    
    tester = QuickTableCalcTester()
    tester.enable_streaming = enable_streaming
    await tester.run_all(args.categories)


if __name__ == "__main__":
    asyncio.run(main())
