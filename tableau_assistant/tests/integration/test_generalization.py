# -*- coding: utf-8 -*-
"""
Generalization Test - 测试 LLM 是否学会了通用规则

目的：使用与模板/数据模型中完全不同的表达方式，测试 LLM 是否真正理解了规则，
而不是简单地匹配关键词。

模板中的关键词（需要避免）：
- SIMPLE: "total sales", "average price", "top 5 cities", "bottom 10 products"
- COMPLEX: "rank all provinces", "percentile ranking", "YTD", "cumulative total", 
           "running sum", "MoM growth", "YoY change", "3-month moving average",
           "percent of total", "share of category"

测试策略：
1. 使用同义词和不同表达方式
2. 使用中文表达（模板是英文）
3. 使用口语化/非标准表达
4. 输出完整的语义理解最终结果

运行方式:
    python tableau_assistant/tests/integration/test_generalization.py
"""
import asyncio
import logging
import os
import sys
import time
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class GeneralizationTestCase:
    """泛化测试用例"""
    name: str
    question: str  # 使用非模板关键词的问题
    expected_how_type: str  # SIMPLE or COMPLEX
    expected_calc_types: List[str] = field(default_factory=list)  # 期望的计算类型
    description: str = ""  # 测试目的说明
    template_equivalent: str = ""  # 模板中的等价表达（用于对比）


# ═══════════════════════════════════════════════════════════════════════════
# 泛化测试用例 - 使用非模板关键词
# ═══════════════════════════════════════════════════════════════════════════

GENERALIZATION_TESTS: List[GeneralizationTestCase] = [
    # ─────────────────────────────────────────────────────────────────────────
    # 1. SIMPLE 场景 - 应该被识别为 SIMPLE
    # ─────────────────────────────────────────────────────────────────────────
    GeneralizationTestCase(
        name="simple_01_sum_alt",
        question="把所有订单的金额加起来是多少",  # 避免 "total sales"
        expected_how_type="SIMPLE",
        expected_calc_types=[],
        description="求和的口语化表达",
        template_equivalent="total sales"
    ),
    GeneralizationTestCase(
        name="simple_02_avg_alt",
        question="每笔订单的平均金额是多少",  # 更明确的平均值表达
        expected_how_type="SIMPLE",
        expected_calc_types=[],
        description="平均值的口语化表达",
        template_equivalent="average price"
    ),
    GeneralizationTestCase(
        name="simple_03_topn_alt",
        question="业绩最好的前三个销售员",  # 避免 "top N"
        expected_how_type="SIMPLE",
        expected_calc_types=[],
        description="Top N 的口语化表达 - 应该是过滤而非排名计算",
        template_equivalent="top 5 cities by sales"
    ),
    GeneralizationTestCase(
        name="simple_04_bottomn_alt",
        question="卖得最差的几款产品",  # 避免 "bottom N"
        expected_how_type="SIMPLE",
        expected_calc_types=[],
        description="Bottom N 的口语化表达 - 应该是过滤而非排名计算",
        template_equivalent="bottom 10 products"
    ),
    GeneralizationTestCase(
        name="simple_05_groupby_alt",
        question="每个部门花了多少钱",  # 避免 "sales by region"
        expected_how_type="SIMPLE",
        expected_calc_types=[],
        description="分组聚合的口语化表达",
        template_equivalent="sales by region"
    ),
    
    # ─────────────────────────────────────────────────────────────────────────
    # 2. COMPLEX - 排名场景（应该被识别为 COMPLEX）
    # ─────────────────────────────────────────────────────────────────────────
    GeneralizationTestCase(
        name="complex_rank_01",
        question="给所有店铺按营业额排个序，标上第几名",  # 避免 "rank all provinces"
        expected_how_type="COMPLEX",
        expected_calc_types=["RANK", "DENSE_RANK"],
        description="排名的口语化表达 - 需要添加排名列",
        template_equivalent="rank all provinces"
    ),
    GeneralizationTestCase(
        name="complex_rank_02",
        question="看看每个员工在团队里业绩排第几",  # 完全不同的表达
        expected_how_type="COMPLEX",
        expected_calc_types=["RANK", "DENSE_RANK"],
        description="排名的另一种口语化表达",
        template_equivalent="rank all provinces"
    ),
    GeneralizationTestCase(
        name="complex_rank_03",
        question="各个城市的订单量处于什么位次",  # 使用"位次"而非"排名"
        expected_how_type="COMPLEX",
        expected_calc_types=["RANK", "DENSE_RANK"],
        description="使用'位次'表达排名",
        template_equivalent="rank all cities"
    ),
    
    # ─────────────────────────────────────────────────────────────────────────
    # 3. COMPLEX - 累计场景（应该被识别为 COMPLEX）
    # ─────────────────────────────────────────────────────────────────────────
    GeneralizationTestCase(
        name="complex_running_01",
        question="从年初到现在一共卖了多少钱，按月看",  # 避免 "YTD", "cumulative"
        expected_how_type="COMPLEX",
        expected_calc_types=["RUNNING_TOTAL"],
        description="YTD 的口语化表达",
        template_equivalent="YTD"
    ),
    GeneralizationTestCase(
        name="complex_running_02",
        question="每个月的销售额逐月叠加起来是多少",  # 避免 "running sum"
        expected_how_type="COMPLEX",
        expected_calc_types=["RUNNING_TOTAL"],
        description="累计的口语化表达",
        template_equivalent="cumulative total"
    ),
    GeneralizationTestCase(
        name="complex_running_03",
        question="订单金额一个月一个月往上加的趋势",  # 完全口语化
        expected_how_type="COMPLEX",
        expected_calc_types=["RUNNING_TOTAL"],
        description="累计的另一种口语化表达",
        template_equivalent="running sum"
    ),
    
    # ─────────────────────────────────────────────────────────────────────────
    # 4. COMPLEX - 环比/同比场景（应该被识别为 COMPLEX）
    # ─────────────────────────────────────────────────────────────────────────
    GeneralizationTestCase(
        name="complex_growth_01",
        question="这个月比上个月多卖了百分之多少",  # 避免 "MoM growth"
        expected_how_type="COMPLEX",
        expected_calc_types=["PERCENT_DIFFERENCE"],
        description="环比增长的口语化表达",
        template_equivalent="MoM growth"
    ),
    GeneralizationTestCase(
        name="complex_growth_02",
        question="跟去年同期相比涨了还是跌了",  # 避免 "YoY change"
        expected_how_type="COMPLEX",
        expected_calc_types=["PERCENT_DIFFERENCE", "DIFFERENCE"],
        description="同比的口语化表达",
        template_equivalent="YoY change"
    ),
    GeneralizationTestCase(
        name="complex_growth_03",
        question="每个季度的业绩和前一个季度差多少",  # 避免 "difference from previous"
        expected_how_type="COMPLEX",
        expected_calc_types=["DIFFERENCE", "PERCENT_DIFFERENCE"],
        description="差异的口语化表达",
        template_equivalent="difference from previous"
    ),
    
    # ─────────────────────────────────────────────────────────────────────────
    # 5. COMPLEX - 移动平均场景（应该被识别为 COMPLEX）
    # ─────────────────────────────────────────────────────────────────────────
    GeneralizationTestCase(
        name="complex_moving_01",
        question="每个月都要看一下前三个月的平均销售额变化趋势",  # 更明确的移动窗口表达
        expected_how_type="COMPLEX",
        expected_calc_types=["MOVING_CALC"],
        description="移动平均的口语化表达 - 强调'前三个月'的滑动窗口",
        template_equivalent="3-month moving average"
    ),
    GeneralizationTestCase(
        name="complex_moving_02",
        question="计算每周的订单数，要用滑动窗口看最近4周的平均",  # 使用"滑动窗口"
        expected_how_type="COMPLEX",
        expected_calc_types=["MOVING_CALC"],
        description="移动平均的技术表达 - 使用'滑动窗口'关键词",
        template_equivalent="rolling average"
    ),
    
    # ─────────────────────────────────────────────────────────────────────────
    # 6. COMPLEX - 占比场景（应该被识别为 COMPLEX）
    # ─────────────────────────────────────────────────────────────────────────
    GeneralizationTestCase(
        name="complex_percent_01",
        question="每个产品线贡献了多少比例的收入",  # 避免 "percent of total"
        expected_how_type="COMPLEX",
        expected_calc_types=["PERCENT_OF_TOTAL"],
        description="占比的口语化表达",
        template_equivalent="percent of total"
    ),
    GeneralizationTestCase(
        name="complex_percent_02",
        question="各个区域的销售额在整体中占多大份额",  # 避免 "share of category"
        expected_how_type="COMPLEX",
        expected_calc_types=["PERCENT_OF_TOTAL"],
        description="份额的口语化表达",
        template_equivalent="share of category"
    ),
    GeneralizationTestCase(
        name="complex_percent_03",
        question="算一下每个品牌的市场占有率",  # 使用"市场占有率"
        expected_how_type="COMPLEX",
        expected_calc_types=["PERCENT_OF_TOTAL"],
        description="市场占有率表达",
        template_equivalent="market share"
    ),
    
    # ─────────────────────────────────────────────────────────────────────────
    # 7. 边界测试 - 容易混淆的场景
    # ─────────────────────────────────────────────────────────────────────────
    GeneralizationTestCase(
        name="boundary_01_topn_vs_rank",
        question="找出销量最高的5个商品",  # 应该是 SIMPLE (过滤)
        expected_how_type="SIMPLE",
        expected_calc_types=[],
        description="Top N 过滤 - 不需要排名列",
        template_equivalent="top 5 products"
    ),
    GeneralizationTestCase(
        name="boundary_02_rank_all",
        question="给所有商品的销量排个名次",  # 应该是 COMPLEX (排名计算)
        expected_how_type="COMPLEX",
        expected_calc_types=["RANK", "DENSE_RANK"],
        description="排名计算 - 需要添加排名列到所有行",
        template_equivalent="rank all products"
    ),
    GeneralizationTestCase(
        name="boundary_03_simple_sum",
        question="今年一共赚了多少钱",  # 应该是 SIMPLE
        expected_how_type="SIMPLE",
        expected_calc_types=[],
        description="简单求和 - 不是累计",
        template_equivalent="total revenue"
    ),
    GeneralizationTestCase(
        name="boundary_04_cumulative",
        question="看看今年每个月赚的钱加起来的变化趋势",  # 应该是 COMPLEX
        expected_how_type="COMPLEX",
        expected_calc_types=["RUNNING_TOTAL"],
        description="累计趋势 - 需要 RUNNING_TOTAL",
        template_equivalent="cumulative revenue by month"
    ),
]


class GeneralizationTester:
    """泛化测试器"""
    
    def __init__(self):
        self.data_model = None
        self.results: List[Dict[str, Any]] = []
        
    async def setup(self) -> bool:
        """初始化测试环境"""
        from tableau_assistant.src.infra.storage.langgraph_store import get_langgraph_store
        from tableau_assistant.src.infra.storage.data_model_cache import DataModelCache
        from tableau_assistant.src.infra.storage.data_model_loader import TableauDataModelLoader
        from tableau_assistant.src.platforms.tableau.auth import get_tableau_auth_async
        from tableau_assistant.src.infra.config import settings
        
        logger.info("="*80)
        logger.info("Generalization Test - 测试 LLM 是否学会了通用规则")
        logger.info("="*80)
        
        datasource_luid = os.getenv("DATASOURCE_LUID", "")
        if not datasource_luid:
            logger.error("请配置 DATASOURCE_LUID 环境变量")
            return False
        
        logger.info(f"Datasource LUID: {datasource_luid}")
        logger.info(f"LLM Provider: {settings.llm_model_provider}")
        
        try:
            auth_ctx = await get_tableau_auth_async()
            logger.info(f"Tableau 认证成功: {auth_ctx.auth_method}")
            
            store = get_langgraph_store()
            cache = DataModelCache(store)
            loader = TableauDataModelLoader(auth_ctx)
            
            self.data_model, is_cache_hit = await cache.get_or_load(datasource_luid, loader)
            logger.info(f"数据模型加载成功 (缓存: {is_cache_hit})")
            
            return True
            
        except Exception as e:
            logger.error(f"初始化失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def run_single_test(self, test_case: GeneralizationTestCase) -> Dict[str, Any]:
        """运行单个测试并返回完整结果"""
        from tableau_assistant.src.agents.semantic_parser import SemanticParserAgent
        from langchain_core.callbacks import AsyncCallbackHandler
        
        class StreamingHandler(AsyncCallbackHandler):
            def __init__(self):
                self.token_count = 0
                self.step_name = ""
            
            async def on_llm_start(self, serialized, prompts, **kwargs):
                self.step_name = kwargs.get("name", "LLM")
                print(f"\n  📝 [{self.step_name}] ", end="", flush=True)
            
            async def on_llm_new_token(self, token: str, **kwargs):
                self.token_count += 1
                print(token, end="", flush=True)
            
            async def on_llm_end(self, response, **kwargs):
                print(f"\n  ✓ ({self.token_count} tokens)")
                self.token_count = 0
        
        start_time = time.time()
        result = {
            "test_case": test_case.name,
            "question": test_case.question,
            "expected_how_type": test_case.expected_how_type,
            "expected_calc_types": test_case.expected_calc_types,
            "description": test_case.description,
            "template_equivalent": test_case.template_equivalent,
            "success": False,
            "elapsed_seconds": 0,
            "error": None,
            # 语义理解结果
            "semantic_result": None,
        }
        
        try:
            agent = SemanticParserAgent()
            streaming_handler = StreamingHandler()
            config = {"callbacks": [streaming_handler]}
            
            parse_result = await agent.parse(
                question=test_case.question,
                history=[],
                data_model=self.data_model,
                config=config,
            )
            
            result["elapsed_seconds"] = time.time() - start_time
            
            # 从 SemanticQuery 构建语义理解结果
            # SemanticParseResult 只有: restated_question, intent, semantic_query
            # 需要从 semantic_query 推断 how_type (有 computations 就是 COMPLEX)
            
            sq = parse_result.semantic_query
            has_computations = sq and sq.computations and len(sq.computations) > 0
            inferred_how_type = "COMPLEX" if has_computations else "SIMPLE"
            
            semantic_result = {
                "restated_question": parse_result.restated_question,
                "intent": {
                    "type": parse_result.intent.type.value,
                    "reasoning": parse_result.intent.reasoning,
                },
                "how_type": inferred_how_type,
                "semantic_query": None,
            }
            
            # SemanticQuery (最终输出)
            if sq:
                semantic_result["semantic_query"] = {
                    "dimensions": [
                        {
                            "field_name": d.field_name, 
                            "date_granularity": d.date_granularity.value if d.date_granularity else None
                        }
                        for d in (sq.dimensions or [])
                    ],
                    "measures": [
                        {
                            "field_name": m.field_name, 
                            "aggregation": m.aggregation.value if hasattr(m.aggregation, 'value') else str(m.aggregation)
                        }
                        for m in (sq.measures or [])
                    ],
                    "filters": [
                        {
                            "field_name": getattr(f, 'field_name', None),
                            "filter_type": type(f).__name__,
                        }
                        for f in (sq.filters or [])
                    ],
                    "computations": [
                        {
                            "calc_type": c.calc_type.value if hasattr(c.calc_type, 'value') else str(c.calc_type),
                            "target": c.target,
                            "partition_by": c.partition_by,
                        }
                        for c in (sq.computations or [])
                    ],
                    "sorts": [
                        {
                            "field_name": s.field_name, 
                            "direction": s.direction.value if hasattr(s.direction, 'value') else str(s.direction)
                        }
                        for s in (sq.sorts or [])
                    ] if sq.sorts else [],
                }
            
            result["semantic_result"] = semantic_result
            
            # 验证结果
            actual_how_type = inferred_how_type
            actual_calc_types = []
            if sq and sq.computations:
                actual_calc_types = [
                    c.calc_type.value if hasattr(c.calc_type, 'value') else str(c.calc_type)
                    for c in sq.computations
                ]
            
            # 检查 how_type
            how_type_match = actual_how_type == test_case.expected_how_type
            
            # 检查 calc_types (如果期望有的话)
            calc_type_match = True
            if test_case.expected_calc_types:
                calc_type_match = any(
                    expected in actual_calc_types 
                    for expected in test_case.expected_calc_types
                )
            
            result["success"] = how_type_match and calc_type_match
            result["actual_how_type"] = actual_how_type
            result["actual_calc_types"] = actual_calc_types
            
        except Exception as e:
            result["elapsed_seconds"] = time.time() - start_time
            result["error"] = str(e)
            import traceback
            traceback.print_exc()
        
        return result
    
    async def run_all(self) -> List[Dict[str, Any]]:
        """运行所有测试"""
        if not await self.setup():
            return []
        
        logger.info(f"\n共 {len(GENERALIZATION_TESTS)} 个测试用例")
        logger.info("="*80)
        
        passed = 0
        failed = 0
        
        for i, test_case in enumerate(GENERALIZATION_TESTS, 1):
            logger.info(f"\n[{i}/{len(GENERALIZATION_TESTS)}] {test_case.name}")
            logger.info(f"  问题: {test_case.question}")
            logger.info(f"  描述: {test_case.description}")
            logger.info(f"  期望: how_type={test_case.expected_how_type}, calc_types={test_case.expected_calc_types}")
            logger.info(f"  模板等价: {test_case.template_equivalent}")
            
            result = await self.run_single_test(test_case)
            self.results.append(result)
            
            if result["success"]:
                passed += 1
                logger.info(f"\n  ✅ 通过 ({result['elapsed_seconds']:.2f}s)")
            else:
                failed += 1
                logger.info(f"\n  ❌ 失败 ({result['elapsed_seconds']:.2f}s)")
                if result.get("error"):
                    logger.info(f"     错误: {result['error']}")
            
            # 输出语义理解结果
            if result.get("semantic_result"):
                sr = result["semantic_result"]
                logger.info(f"\n  ═══ 语义理解最终结果 ═══")
                logger.info(f"  重述问题: {sr['restated_question']}")
                logger.info(f"  意图: {sr['intent']['type']}")
                logger.info(f"  复杂度(推断): {sr['how_type']}")
                
                # 输出最终 SemanticQuery
                if sr.get("semantic_query"):
                    sq = sr["semantic_query"]
                    if sq.get("dimensions"):
                        logger.info(f"  维度: {[d['field_name'] for d in sq['dimensions']]}")
                    if sq.get("measures"):
                        logger.info(f"  度量: {[m['field_name'] for m in sq['measures']]}")
                    if sq.get("filters"):
                        logger.info(f"  筛选: {sq['filters']}")
                    if sq.get("computations"):
                        logger.info(f"  计算: {sq['computations']}")
                    if sq.get("sorts"):
                        logger.info(f"  排序: {sq['sorts']}")
                    
                    logger.info(f"\n  ═══ SemanticQuery JSON ═══")
                    logger.info(f"  {json.dumps(sq, ensure_ascii=False, indent=4)}")
            
            # 对比期望和实际
            logger.info(f"\n  ═══ 对比 ═══")
            logger.info(f"  期望 how_type: {test_case.expected_how_type}")
            logger.info(f"  实际 how_type: {result.get('actual_how_type', 'N/A')}")
            logger.info(f"  期望 calc_types: {test_case.expected_calc_types}")
            logger.info(f"  实际 calc_types: {result.get('actual_calc_types', [])}")
        
        # 输出总结
        logger.info(f"\n{'='*80}")
        logger.info("测试总结")
        logger.info(f"{'='*80}")
        logger.info(f"通过: {passed}/{len(GENERALIZATION_TESTS)} ({passed/len(GENERALIZATION_TESTS)*100:.1f}%)")
        logger.info(f"失败: {failed}/{len(GENERALIZATION_TESTS)}")
        
        # 输出失败的测试
        failed_tests = [r for r in self.results if not r["success"]]
        if failed_tests:
            logger.info(f"\n失败的测试:")
            for r in failed_tests:
                logger.info(f"  - {r['test_case']}: {r['question']}")
                logger.info(f"    期望: {r['expected_how_type']}, 实际: {r.get('actual_how_type', 'N/A')}")
        
        return self.results


async def main():
    """主函数"""
    tester = GeneralizationTester()
    await tester.run_all()


if __name__ == "__main__":
    asyncio.run(main())
