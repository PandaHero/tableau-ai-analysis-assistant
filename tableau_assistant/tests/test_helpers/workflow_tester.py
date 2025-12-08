"""
工作流测试器

负责测试完整的工作流程，包括：
- 问题Boost Agent
- 问题理解Agent
- 任务规划Agent
- 查询构建器
- 查询执行器
"""
import time
from typing import Tuple, List, Dict, Any, Optional

from tableau_assistant.tests.test_helpers.test_environment import TestEnvironment
from tableau_assistant.tests.test_helpers.test_models import TestStageResult
from tableau_assistant.src.models.workflow.state import VizQLState
from tableau_assistant.src.models.boost import QuestionBoost
from tableau_assistant.src.models.question import QuestionUnderstanding
from tableau_assistant.src.models.query_plan import QueryPlanningResult
from tableau_assistant.src.models.vizql_types import VizQLQuery
from tableau_assistant.src.components.query_builder.builder import QueryBuilder
from tableau_assistant.src.components.query_executor import QueryExecutor


class WorkflowTester:
    """
    工作流测试器
    
    测试从问题输入到结果输出的完整工作流程
    """
    
    def __init__(self, environment: TestEnvironment):
        """
        初始化工作流测试器
        
        Args:
            environment: 测试环境实例
        """
        self.environment = environment
        self.runtime = environment.get_runtime()
        self.metadata_manager = environment.get_metadata_manager()
        self.datasource_luid = environment.get_datasource_luid()
        self.tableau_config = environment.get_tableau_config()
    
    async def test_question_boost(
        self,
        question: str,
        metadata: Optional[Any] = None
    ) -> Tuple[Optional[QuestionBoost], TestStageResult]:
        """
        测试问题Boost Agent
        
        Args:
            question: 用户问题
            metadata: 可选的元数据
        
        Returns:
            (QuestionBoost对象, 测试结果)
        """
        start_time = time.time()
        
        try:
            # 导入Agent
            from tableau_assistant.src.agents.question_boost_agent import question_boost_agent_node
            
            # 创建状态
            state: VizQLState = {
                "question": question,
                "boosted_question": None,
                "boost": None,
                "understanding": None,
                "query_plan": None,
                "subtask_results": [],
                "all_query_results": [],
                "insights": [],
                "all_insights": [],
                "merged_data": None,
                "replan_decision": None,
                "replan_history": [],
                "final_report": None,
                "replan_count": 0,
                "current_stage": "boost",
                "execution_path": [],
                "metadata": None,
                "dimension_hierarchy": None,
                "statistics": None,
                "errors": [],
                "warnings": [],
                "performance": None,
                "visualizations": []
            }
            
            # 调用Agent
            result = await question_boost_agent_node(
                state=state,
                runtime=self.runtime,
                metadata=metadata,
                show_tokens=False  # 测试时不显示token
            )
            
            # 获取boost结果
            boost = result.get("boost")
            
            if not boost:
                return None, TestStageResult(
                    stage_name="question_boost",
                    success=False,
                    duration=time.time() - start_time,
                    error_message="未能获取问题Boost结果"
                )
            
            # 创建成功结果
            test_result = TestStageResult(
                stage_name="question_boost",
                success=True,
                duration=time.time() - start_time,
                output_data={
                    "boosted_question": boost.boosted_question if hasattr(boost, 'boosted_question') else None,
                    "suggestions_count": len(boost.suggestions) if hasattr(boost, 'suggestions') else 0
                }
            )
            
            # 添加元数据
            if hasattr(boost, 'boosted_question'):
                test_result.add_metadata("boosted_question", boost.boosted_question)
            if hasattr(boost, 'suggestions'):
                test_result.add_metadata("suggestions_count", len(boost.suggestions))
            
            return boost, test_result
            
        except Exception as e:
            return None, TestStageResult(
                stage_name="question_boost",
                success=False,
                duration=time.time() - start_time,
                error_message=f"问题Boost失败: {str(e)}"
            )
    
    async def test_understanding(
        self,
        question: str
    ) -> Tuple[Optional[QuestionUnderstanding], TestStageResult]:
        """
        测试问题理解Agent
        
        Args:
            question: 用户问题
        
        Returns:
            (QuestionUnderstanding对象, 测试结果)
        """
        start_time = time.time()
        
        try:
            # 导入Agent
            from tableau_assistant.src.agents.understanding_agent import understanding_agent_node
            
            # 创建状态
            state: VizQLState = {
                "question": question,
                "boosted_question": None,
                "boost": None,
                "understanding": None,
                "query_plan": None,
                "subtask_results": [],
                "all_query_results": [],
                "insights": [],
                "all_insights": [],
                "merged_data": None,
                "replan_decision": None,
                "replan_history": [],
                "final_report": None,
                "replan_count": 0,
                "current_stage": "understanding",
                "execution_path": [],
                "metadata": None,
                "dimension_hierarchy": None,
                "statistics": None,
                "errors": [],
                "warnings": [],
                "performance": None,
                "visualizations": []
            }
            
            # 调用Agent
            result = await understanding_agent_node(
                state=state,
                runtime=self.runtime,
                show_tokens=False  # 测试时不显示token
            )
            
            # 获取understanding结果
            understanding = result.get("understanding")
            
            if not understanding:
                return None, TestStageResult(
                    stage_name="understanding",
                    success=False,
                    duration=time.time() - start_time,
                    error_message="未能获取问题理解结果"
                )
            
            # 创建成功结果
            test_result = TestStageResult(
                stage_name="understanding",
                success=True,
                duration=time.time() - start_time,
                output_data={
                    "question_type": understanding.question_type if hasattr(understanding, 'question_type') else None,
                    "complexity": understanding.complexity if hasattr(understanding, 'complexity') else None,
                    "dimensions": understanding.dimensions if hasattr(understanding, 'dimensions') else [],
                    "measures": understanding.measures if hasattr(understanding, 'measures') else []
                }
            )
            
            # 添加元数据
            if hasattr(understanding, 'question_type'):
                test_result.add_metadata("question_type", str(understanding.question_type))
            if hasattr(understanding, 'complexity'):
                test_result.add_metadata("complexity", str(understanding.complexity))
            if hasattr(understanding, 'dimensions'):
                test_result.add_metadata("dimensions_count", len(understanding.dimensions))
            if hasattr(understanding, 'measures'):
                test_result.add_metadata("measures_count", len(understanding.measures))
            
            return understanding, test_result
            
        except Exception as e:
            return None, TestStageResult(
                stage_name="understanding",
                success=False,
                duration=time.time() - start_time,
                error_message=f"问题理解失败: {str(e)}"
            )
    
    async def test_task_planning(
        self,
        question: str,
        understanding: QuestionUnderstanding,
        metadata: Any,
        dimension_hierarchy: Optional[Dict] = None
    ) -> Tuple[Optional[QueryPlanningResult], TestStageResult]:
        """
        测试任务规划Agent
        
        Args:
            question: 用户问题
            understanding: 问题理解结果
            metadata: 元数据
            dimension_hierarchy: 维度层级
        
        Returns:
            (QueryPlanningResult对象, 测试结果)
        """
        start_time = time.time()
        
        try:
            # 导入Agent
            from tableau_assistant.src.agents.task_planner_agent import query_planner_agent_node
            
            # 创建状态
            state: VizQLState = {
                "question": question,
                "boosted_question": None,
                "boost": None,
                "understanding": understanding,
                "query_plan": None,
                "subtask_results": [],
                "all_query_results": [],
                "insights": [],
                "all_insights": [],
                "merged_data": None,
                "replan_decision": None,
                "replan_history": [],
                "final_report": None,
                "replan_count": 0,
                "current_stage": "planning",
                "execution_path": [],
                "metadata": metadata,
                "dimension_hierarchy": dimension_hierarchy,
                "statistics": None,
                "errors": [],
                "warnings": [],
                "performance": None,
                "visualizations": []
            }
            
            # 调用Agent
            result = await query_planner_agent_node(
                state=state,
                runtime=self.runtime,
                show_tokens=False  # 测试时不显示token
            )
            
            # 获取query_plan结果
            query_plan = result.get("query_plan")
            
            if not query_plan:
                return None, TestStageResult(
                    stage_name="task_planning",
                    success=False,
                    duration=time.time() - start_time,
                    error_message="未能获取任务规划结果"
                )
            
            # 创建成功结果
            subtasks_count = len(query_plan.subtasks) if hasattr(query_plan, 'subtasks') else 0
            
            test_result = TestStageResult(
                stage_name="task_planning",
                success=True,
                duration=time.time() - start_time,
                output_data={
                    "subtasks_count": subtasks_count,
                    "query_plan": query_plan
                }
            )
            
            # 添加元数据
            test_result.add_metadata("subtasks_count", subtasks_count)
            
            return query_plan, test_result
            
        except Exception as e:
            return None, TestStageResult(
                stage_name="task_planning",
                success=False,
                duration=time.time() - start_time,
                error_message=f"任务规划失败: {str(e)}"
            )
    
    async def test_query_building(
        self,
        query_plan: QueryPlanningResult,
        metadata: Any
    ) -> Tuple[List[VizQLQuery], TestStageResult]:
        """
        测试查询构建器
        
        Args:
            query_plan: 查询规划结果
            metadata: 元数据
        
        Returns:
            (VizQLQuery列表, 测试结果)
        """
        start_time = time.time()
        
        try:
            # 创建QueryBuilder
            query_builder = QueryBuilder(
                metadata=metadata,
                anchor_date=None,
                week_start_day=0
            )
            
            # 构建查询
            queries = []
            if hasattr(query_plan, 'subtasks'):
                for i, subtask in enumerate(query_plan.subtasks):
                    try:
                        print(f"\n构建查询 {i+1}:")
                        print(f"  子任务描述: {subtask.description if hasattr(subtask, 'description') else 'N/A'}")
                        
                        query = query_builder.build_query(subtask)
                        queries.append(query)
                        
                        # 打印生成的VizQL查询
                        print(f"  生成的VizQL查询:")
                        import json
                        query_dict = query.model_dump(exclude_none=True)
                        print(f"  {json.dumps(query_dict, indent=2, ensure_ascii=False)}")
                        
                    except Exception as e:
                        # 记录单个子任务的构建错误，但继续处理其他子任务
                        print(f"⚠️  子任务构建失败: {str(e)}")
                        import traceback
                        traceback.print_exc()
            
            if not queries:
                return [], TestStageResult(
                    stage_name="query_building",
                    success=False,
                    duration=time.time() - start_time,
                    error_message="未能构建任何查询"
                )
            
            # 创建成功结果
            test_result = TestStageResult(
                stage_name="query_building",
                success=True,
                duration=time.time() - start_time,
                output_data={
                    "queries_count": len(queries),
                    "queries": queries
                }
            )
            
            # 添加元数据
            test_result.add_metadata("queries_count", len(queries))
            
            return queries, test_result
            
        except Exception as e:
            return [], TestStageResult(
                stage_name="query_building",
                success=False,
                duration=time.time() - start_time,
                error_message=f"查询构建失败: {str(e)}"
            )
    
    async def test_query_execution(
        self,
        queries: List[VizQLQuery]
    ) -> Tuple[List[Dict[str, Any]], TestStageResult]:
        """
        测试查询执行器
        
        Args:
            queries: VizQLQuery列表
        
        Returns:
            (查询结果列表, 测试结果)
        """
        start_time = time.time()
        
        try:
            # 创建QueryExecutor
            query_executor = QueryExecutor(
                max_retries=3,
                retry_delay=1.0,
                timeout=30
            )
            
            # 执行查询
            results = []
            total_rows = 0
            
            for i, query in enumerate(queries):
                try:
                    print(f"\n执行查询 {i+1}:")
                    print(f"  数据源LUID: {self.datasource_luid}")
                    print(f"  Tableau域: {self.tableau_config.get('tableau_domain')}")
                    
                    result = query_executor.execute_query(
                        query=query,
                        datasource_luid=self.datasource_luid,
                        tableau_config=self.tableau_config,
                        enable_retry=True
                    )
                    results.append(result)
                    total_rows += result.get("row_count", 0)
                    print(f"  ✓ 查询成功，返回 {result.get('row_count', 0)} 行")
                    
                except Exception as e:
                    # 记录单个查询的执行错误，但继续处理其他查询
                    print(f"⚠️  查询 {i+1} 执行失败: {str(e)}")
                    results.append({
                        "error": str(e),
                        "query_index": i
                    })
            
            if not results:
                return [], TestStageResult(
                    stage_name="query_execution",
                    success=False,
                    duration=time.time() - start_time,
                    error_message="未能执行任何查询"
                )
            
            # 统计成功和失败的查询
            successful_queries = sum(1 for r in results if "error" not in r)
            failed_queries = len(results) - successful_queries
            
            # 创建结果
            test_result = TestStageResult(
                stage_name="query_execution",
                success=successful_queries > 0,  # 只要有一个成功就算成功
                duration=time.time() - start_time,
                output_data={
                    "total_queries": len(queries),
                    "successful_queries": successful_queries,
                    "failed_queries": failed_queries,
                    "total_rows": total_rows,
                    "results": results
                }
            )
            
            # 添加元数据
            test_result.add_metadata("total_queries", len(queries))
            test_result.add_metadata("successful_queries", successful_queries)
            test_result.add_metadata("failed_queries", failed_queries)
            test_result.add_metadata("total_rows", total_rows)
            
            # 添加警告
            if failed_queries > 0:
                test_result.add_warning(f"有 {failed_queries} 个查询执行失败")
            
            return results, test_result
            
        except Exception as e:
            return [], TestStageResult(
                stage_name="query_execution",
                success=False,
                duration=time.time() - start_time,
                error_message=f"查询执行失败: {str(e)}"
            )


# ============= 导出 =============

__all__ = [
    "WorkflowTester",
]
