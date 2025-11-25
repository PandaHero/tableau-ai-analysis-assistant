"""
流式工作流测试器

支持流式输出和详细节点耗时统计的测试器
"""
import time
import asyncio
from typing import AsyncIterator, Dict, Any, Optional, List
from dataclasses import dataclass, field

from tableau_assistant.tests.test_helpers.test_environment import TestEnvironment
from tableau_assistant.tests.test_helpers.test_models import TestStageResult, TestResult
from tableau_assistant.src.workflows.vizql_workflow import run_vizql_workflow_stream
from tableau_assistant.src.models.state import VizQLInput


@dataclass
class NodeTiming:
    """节点耗时统计"""
    node_name: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    token_count: int = 0
    
    def complete(self):
        """标记节点完成"""
        if self.end_time is None:
            self.end_time = time.time()
            self.duration = self.end_time - self.start_time
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "node_name": self.node_name,
            "duration": self.duration,
            "token_count": self.token_count,
            "start_time": self.start_time,
            "end_time": self.end_time
        }


@dataclass
class StreamingTestResult:
    """流式测试结果"""
    test_case_name: str
    success: bool
    total_duration: float
    node_timings: List[NodeTiming] = field(default_factory=list)
    stage_results: List[TestStageResult] = field(default_factory=list)
    error_message: Optional[str] = None
    total_tokens: int = 0
    
    def add_node_timing(self, timing: NodeTiming):
        """添加节点耗时"""
        self.node_timings.append(timing)
        if timing.duration:
            self.total_tokens += timing.token_count
    
    def get_node_timing(self, node_name: str) -> Optional[NodeTiming]:
        """获取指定节点的耗时"""
        for timing in self.node_timings:
            if timing.node_name == node_name:
                return timing
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "test_case_name": self.test_case_name,
            "success": self.success,
            "total_duration": self.total_duration,
            "node_timings": [t.to_dict() for t in self.node_timings],
            "stage_results": [s.to_dict() for s in self.stage_results],
            "error_message": self.error_message,
            "total_tokens": self.total_tokens
        }


class StreamingWorkflowTester:
    """
    流式工作流测试器
    
    支持：
    1. 流式输出（实时显示进度和token）
    2. 详细的节点耗时统计
    3. Token使用量统计
    """
    
    def __init__(self, environment: TestEnvironment, verbose: bool = True):
        """
        初始化流式工作流测试器
        
        Args:
            environment: 测试环境实例
            verbose: 是否显示详细输出
        """
        self.environment = environment
        self.verbose = verbose
        self.datasource_luid = environment.get_datasource_luid()
        self.tableau_config = environment.get_tableau_config()
        
        # 节点耗时追踪
        self.current_node_timings: Dict[str, NodeTiming] = {}
    
    async def test_workflow_with_streaming(
        self,
        question: str,
        test_case_name: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        测试完整工作流（流式输出）
        
        Args:
            question: 用户问题
            test_case_name: 测试用例名称
        
        Yields:
            流式事件字典，包含：
            - type: 事件类型（token, node_start, node_complete, etc.）
            - data: 事件数据
        """
        start_time = time.time()
        node_timings: List[NodeTiming] = []
        stage_results: List[TestStageResult] = []
        success = True
        error_message = None
        
        try:
            # 发送测试开始事件
            yield {
                "type": "test_start",
                "data": {
                    "test_case_name": test_case_name,
                    "question": question,
                    "timestamp": start_time
                }
            }
            
            # 创建输入
            input_data = {"question": question, "boost_question": False}
            
            # 运行工作流（流式）
            # 注意：Tableau配置会从环境变量或Store中获取
            store_manager = self.environment.get_store_manager()
            event_stream = run_vizql_workflow_stream(
                input_data=input_data,
                datasource_luid=self.datasource_luid,
                store=store_manager.store if store_manager else None
            )
            
            # 处理事件流 - LangGraph astream_events 返回的事件格式
            current_node = None
            async for event in event_stream:
                event_type = event.get("event")  # LangGraph uses "event" not "type"
                event_name = event.get("name", "")
                event_data = event.get("data", {})
                
                # ========== 处理节点开始事件 ==========
                if event_type == "on_chain_start":
                    # 节点开始
                    node_name = event_name
                    if node_name and node_name not in ["RunnableSequence", "RunnableLambda"]:
                        current_node = node_name
                        timing = NodeTiming(
                            node_name=node_name,
                            start_time=time.time()
                        )
                        self.current_node_timings[node_name] = timing
                        
                        if self.verbose:
                            yield {
                                "type": "node_start",
                                "data": {
                                    "node_name": node_name,
                                    "timestamp": timing.start_time
                                }
                            }
                
                # ========== 处理节点完成事件 ==========
                elif event_type == "on_chain_end":
                    node_name = event_name
                    if node_name and node_name in self.current_node_timings:
                        timing = self.current_node_timings[node_name]
                        timing.complete()
                        node_timings.append(timing)
                        del self.current_node_timings[node_name]
                        current_node = None
                        
                        if self.verbose:
                            yield {
                                "type": "node_complete",
                                "data": {
                                    "node_name": node_name,
                                    "duration": timing.duration,
                                    "token_count": timing.token_count,
                                    "timestamp": timing.end_time
                                }
                            }
                
                # ========== 处理Token流式输出 ==========
                elif event_type == "on_chat_model_stream":
                    # LLM token 流式输出
                    chunk = event_data.get("chunk", {})
                    if hasattr(chunk, "content"):
                        token = chunk.content
                    else:
                        token = str(chunk)
                    
                    # 统计token
                    if current_node and current_node in self.current_node_timings:
                        self.current_node_timings[current_node].token_count += 1
                    
                    if self.verbose and token:
                        yield {
                            "type": "token",
                            "data": {
                                "token": token,
                                "agent": current_node
                            }
                        }
                
                # ========== 处理错误事件 ==========
                elif event_type == "on_chain_error":
                    success = False
                    error_message = str(event_data.get("error", "未知错误"))
                    
                    yield {
                        "type": "error",
                        "data": {
                            "error": error_message,
                            "timestamp": time.time()
                        }
                    }
            
            # 计算总耗时
            total_duration = time.time() - start_time
            
            # 创建测试结果
            result = StreamingTestResult(
                test_case_name=test_case_name,
                success=success,
                total_duration=total_duration,
                node_timings=node_timings,
                stage_results=stage_results,
                error_message=error_message
            )
            
            # 发送测试完成事件
            yield {
                "type": "test_complete",
                "data": {
                    "test_case_name": test_case_name,
                    "success": success,
                    "total_duration": total_duration,
                    "node_timings": [t.to_dict() for t in node_timings],
                    "total_tokens": result.total_tokens,
                    "error_message": error_message,
                    "timestamp": time.time()
                }
            }
        
        except Exception as e:
            error_message = f"测试执行失败: {str(e)}"
            success = False
            
            yield {
                "type": "error",
                "data": {
                    "error": error_message,
                    "timestamp": time.time()
                }
            }
    
    def print_node_timings(self, node_timings: List[NodeTiming]):
        """
        打印节点耗时统计
        
        Args:
            node_timings: 节点耗时列表
        """
        if not node_timings:
            return
        
        print("\n" + "=" * 80)
        print("  节点耗时统计")
        print("=" * 80)
        
        # 按耗时排序
        sorted_timings = sorted(node_timings, key=lambda t: t.duration or 0, reverse=True)
        
        total_duration = sum(t.duration or 0 for t in node_timings)
        total_tokens = sum(t.token_count for t in node_timings)
        
        print(f"\n{'节点名称':<40} {'耗时':<15} {'Token数':<10} {'占比':<10}")
        print("-" * 80)
        
        for timing in sorted_timings:
            duration_str = f"{timing.duration:.2f}秒" if timing.duration else "N/A"
            percentage = (timing.duration / total_duration * 100) if timing.duration and total_duration > 0 else 0
            percentage_str = f"{percentage:.1f}%"
            
            print(f"{timing.node_name:<40} {duration_str:<15} {timing.token_count:<10} {percentage_str:<10}")
        
        print("-" * 80)
        print(f"{'总计':<40} {total_duration:.2f}秒{'':<7} {total_tokens:<10} {'100.0%':<10}")
        print()


# ============= 导出 =============

__all__ = [
    "NodeTiming",
    "StreamingTestResult",
    "StreamingWorkflowTester",
]
