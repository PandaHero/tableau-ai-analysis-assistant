# -*- coding: utf-8 -*-
"""
工作流输出打印器

封装节点输出的格式化和打印逻辑。

使用示例:
    from tableau_assistant.src.orchestration.workflow.printer import WorkflowPrinter
    from tableau_assistant.src.orchestration.workflow.executor import WorkflowExecutor
    
    printer = WorkflowPrinter()
    executor = WorkflowExecutor()
    
    # 流式打印
    async for event in executor.stream("各产品类别的销售额是多少?"):
        printer.print_event(event)
    
    # 打印结果
    result = await executor.run("各产品类别的销售额是多少?")
    printer.print_result(result)
"""

import sys
from typing import Optional

from tableau_assistant.src.core.models import SemanticQuery, MappedQuery, ReplanDecision
from tableau_assistant.src.core.models import ExecuteResult
from tableau_assistant.src.platforms.tableau.models import VizQLQueryRequest as VizQLQuery
from tableau_assistant.src.orchestration.workflow.executor import NodeOutput, WorkflowEvent, WorkflowResult

# Windows 终端编码修复
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

try:
    from colorama import Fore, Style, init
    init(autoreset=True)
except ImportError:
    # colorama 不可用时的降级处理
    class Fore:
        CYAN = YELLOW = GREEN = RED = BLUE = MAGENTA = WHITE = ""
    class Style:
        RESET_ALL = ""


class WorkflowPrinter:
    """工作流输出打印器"""
    
    def __init__(self, verbose: bool = True, show_tokens: bool = True):
        """
        初始化打印器
        
        Args:
            verbose: 是否显示详细输出
            show_tokens: 是否显示 token 流
        """
        self.verbose = verbose
        self.show_tokens = show_tokens
        self._token_buffer = []
    
    def print_event(self, event: WorkflowEvent):
        """打印工作流事件"""
        from tableau_assistant.src.orchestration.workflow.executor import EventType
        
        if event.type == EventType.NODE_START:
            self._flush_tokens()
            print(f"\n{Fore.YELLOW}>>> [{event.node_name}] 开始执行...{Style.RESET_ALL}")
        
        elif event.type == EventType.TOKEN:
            if self.show_tokens and event.content:
                print(f"{Fore.WHITE}{event.content}{Style.RESET_ALL}", end="", flush=True)
                self._token_buffer.append(event.content)
        
        elif event.type == EventType.NODE_COMPLETE:
            self._flush_tokens()
            print(f"{Fore.GREEN}<<< [{event.node_name}] 完成{Style.RESET_ALL}")
            # 使用 output (NodeOutput Pydantic 对象)
            if self.verbose and event.output:
                self._print_node_output(event.node_name, event.output)
        
        elif event.type == EventType.ERROR:
            self._flush_tokens()
            print(f"{Fore.RED}!!! 错误: {event.content}{Style.RESET_ALL}")
        
        elif event.type == EventType.COMPLETE:
            self._flush_tokens()
            print(f"\n{Fore.GREEN}=== 工作流完成{Style.RESET_ALL}")
    
    def print_result(self, result: WorkflowResult):
        """打印工作流结果"""
        print(f"\n{'='*60}")
        print(f"{Fore.CYAN}执行结果{Style.RESET_ALL}")
        print(f"{'='*60}")
        
        status = f"{Fore.GREEN}成功" if result.success else f"{Fore.RED}失败"
        print(f"状态: {status}")
        print(f"耗时: {result.duration:.2f}s")
        print(f"重规划次数: {result.replan_count}")
        
        if result.error:
            print(f"{Fore.RED}错误: {result.error}{Style.RESET_ALL}")
        
        if self.verbose:
            if result.semantic_query:
                self._print_semantic_query(result.semantic_query)
            if result.query_result:
                self._print_query_result(result.query_result)
    
    def _flush_tokens(self):
        """刷新 token 缓冲区"""
        if self._token_buffer:
            print()  # 换行
            self._token_buffer = []
    
    def _print_node_output(self, node_name: str, output: NodeOutput):
        """打印节点输出 (NodeOutput Pydantic 对象)"""
        
        if node_name == "semantic_parser":
            if output.semantic_query:
                self._print_semantic_query(output.semantic_query)
        elif node_name == "field_mapper":
            if output.mapped_query:
                self._print_mapped_query(output.mapped_query)
        elif node_name == "query_builder":
            if output.vizql_query:
                self._print_vizql_query(output.vizql_query)
        elif node_name == "execute":
            if output.query_result:
                self._print_query_result(output.query_result)
        elif node_name == "replanner":
            if output.replan_decision:
                self._print_replan_decision(output.replan_decision)
    
    def _print_semantic_query(self, sq: SemanticQuery):
        """打印 SemanticQuery"""
        try:
            measures = [m.name for m in (sq.measures or [])]
            dimensions = [d.name for d in (sq.dimensions or [])]
            print(f"  {Fore.BLUE}├─ measures: {measures}")
            print(f"  {Fore.BLUE}├─ dimensions: {dimensions}")
            print(f"  {Fore.BLUE}├─ filters: {len(sq.filters or [])} 个")
            print(f"  {Fore.BLUE}└─ analyses: {len(sq.analyses or [])} 个")
        except Exception as e:
            print(f"  {Fore.BLUE}└─ (解析错误: {e})")
    
    def _print_mapped_query(self, mq: MappedQuery):
        """打印 MappedQuery"""
        try:
            mappings = mq.field_mappings or {}
            print(f"  {Fore.BLUE}├─ field_mappings: {len(mappings)} 个")
            for i, (term, fm) in enumerate(list(mappings.items())[:5]):
                print(f"  {Fore.BLUE}│  {i+1}. {term} -> {fm.technical_field}")
        except Exception as e:
            print(f"  {Fore.BLUE}└─ (解析错误: {e})")
    
    def _print_vizql_query(self, vq: VizQLQuery):
        """打印 VizQLQuery"""
        try:
            fields = vq.fields or []
            filters = vq.filters or []
            print(f"  {Fore.BLUE}├─ fields: {len(fields)} 个")
            print(f"  {Fore.BLUE}└─ filters: {len(filters)} 个")
        except Exception as e:
            print(f"  {Fore.BLUE}└─ (解析错误: {e})")
    
    def _print_query_result(self, qr: ExecuteResult):
        """打印 ExecuteResult"""
        try:
            data = qr.data if hasattr(qr, 'data') else []
            print(f"  {Fore.BLUE}├─ rows: {len(data)} 行")
            if data:
                for row in data[:3]:
                    print(f"  {Fore.BLUE}│  {row}")
                if len(data) > 3:
                    print(f"  {Fore.BLUE}│  ... 还有 {len(data) - 3} 行")
        except Exception as e:
            print(f"  {Fore.BLUE}└─ (解析错误: {e})")
    
    def _print_replan_decision(self, rd: ReplanDecision):
        """打印 ReplanDecision"""
        try:
            print(f"  {Fore.BLUE}├─ should_replan: {rd.should_replan}")
            print(f"  {Fore.BLUE}├─ completeness_score: {rd.completeness_score}")
            print(f"  {Fore.BLUE}└─ reason: {(rd.reason or '')[:50]}...")
        except Exception as e:
            print(f"  {Fore.BLUE}└─ (解析错误: {e})")
