# -*- coding: utf-8 -*-
"""
工作流执行器

封装工作流执行逻辑，提供简洁的对外接口。

使用示例:
    from tableau_assistant.src.orchestration.workflow.executor import WorkflowExecutor
    
    executor = WorkflowExecutor()
    
    # 简单执行
    result = await executor.run("各产品类别的销售额是多少?")
    print(result.semantic_query)
    print(result.query_result)
    
    # 流式执行
    async for event in executor.stream("各产品类别的销售额是多少?"):
        if event.type == "token":
            print(event.content, end="", flush=True)
        elif event.type == "node_complete":
            print(f"\\n[{event.node_name}] 完成")

认证机制:
    - 工作流启动时获取一次 Tableau token
    - 通过 RunnableConfig["configurable"]["workflow_context"].auth 传递给所有节点
    - Token 过期时自动刷新
"""

import os
import time
import uuid
import logging
from typing import Dict, Optional, List, AsyncIterator, Any
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field

from tableau_assistant.src.orchestration.workflow.factory import create_workflow
from tableau_assistant.src.orchestration.workflow.context import (
    WorkflowContext,
    MetadataLoadStatus,
    create_workflow_config,
    get_context,
)
from tableau_assistant.src.platforms.tableau import (
    TableauAuthContext,
    TableauAuthError,
    get_tableau_auth_async,
)
from tableau_assistant.src.infra.storage.langgraph_store import get_langgraph_store
from tableau_assistant.src.infra.storage.data_model_cache import DataModelCache
from tableau_assistant.src.platforms.tableau import TableauDataModelLoader
from tableau_assistant.src.core.models import SemanticQuery, ExecuteResult
from tableau_assistant.src.agents.replanner.models import ReplanDecision
from tableau_assistant.src.agents.insight.models import Insight
from tableau_assistant.src.agents.field_mapper.models import MappedQuery
from tableau_assistant.src.platforms.tableau.models import VizQLQueryRequest as VizQLQuery

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """事件类型"""
    NODE_START = "node_start"
    NODE_COMPLETE = "node_complete"
    TOKEN = "token"
    ERROR = "error"
    COMPLETE = "complete"


class NodeOutput(BaseModel):
    """节点输出数据结构 - 包含各节点可能的输出"""
    model_config = {"extra": "allow"}  # 允许额外字段
    
    # SemanticParser 节点输出
    semantic_query: Optional[SemanticQuery] = None
    is_analysis_question: Optional[bool] = None
    
    # FieldMapper 节点输出
    mapped_query: Optional[MappedQuery] = None
    
    # QueryBuilder 节点输出
    vizql_query: Optional[VizQLQuery] = None
    
    # Execute 节点输出
    query_result: Optional[ExecuteResult] = None
    
    # Replanner 节点输出
    replan_decision: Optional[ReplanDecision] = None
    
    # 通用字段
    errors: Optional[List[object]] = None


class WorkflowEvent(BaseModel):
    """工作流事件"""
    type: EventType
    node_name: Optional[str] = None
    content: Optional[str] = None
    output: Optional[NodeOutput] = None  # 节点输出 (Pydantic 对象)
    timestamp: float = Field(default_factory=time.time)


@dataclass
class WorkflowResult:
    """工作流执行结果"""
    question: str
    success: bool
    duration: float
    
    # 各节点输出 (Pydantic 对象，使用具体类型)
    semantic_query: Optional[SemanticQuery] = None
    mapped_query: Optional[MappedQuery] = None
    vizql_query: Optional[VizQLQuery] = None
    query_result: Optional[ExecuteResult] = None
    insights: List[Insight] = field(default_factory=list)
    replan_decision: Optional[ReplanDecision] = None
    
    # 元信息
    is_analysis_question: bool = True
    replan_count: int = 0
    error: Optional[str] = None
    
    # 非分析响应（当 is_analysis_question=False 时使用）
    clarification_question: Optional[str] = None
    general_response: Optional[str] = None
    non_analysis_response: Optional[str] = None
    
    @classmethod
    def from_state(cls, question: str, state: Dict[str, object], duration: float) -> "WorkflowResult":
        """从工作流状态创建结果"""
        return cls(
            question=question,
            success=state.get("errors") is None or len(state.get("errors", [])) == 0,
            duration=duration,
            semantic_query=state.get("semantic_query"),
            mapped_query=state.get("mapped_query"),
            vizql_query=state.get("vizql_query"),
            query_result=state.get("query_result"),
            insights=state.get("insights", []),
            replan_decision=state.get("replan_decision"),
            is_analysis_question=state.get("is_analysis_question", True),
            replan_count=state.get("replan_count", 0),
            error=state.get("errors", [{}])[0].get("error") if state.get("errors") else None,
            # 非分析响应
            clarification_question=state.get("clarification_question"),
            general_response=state.get("general_response"),
            non_analysis_response=state.get("non_analysis_response"),
        )


class WorkflowExecutor:
    """
    工作流执行器
    
    封装工作流执行逻辑，提供：
    1. run() - 简单执行，返回完整结果
    2. stream() - 流式执行，逐步返回事件
    
    使用 WorkflowContext 统一管理依赖：
    - auth: Tableau 认证
    - store: 持久化存储
    - metadata: 数据模型（包含维度层级）
    """
    
    # 工作流节点列表
    NODES = ["semantic_parser", "field_mapper", "query_builder", "execute", "insight", "replanner"]
    
    def __init__(
        self,
        datasource_luid: Optional[str] = None,
        tableau_domain: Optional[str] = None,
        max_replan_rounds: int = 2,
        use_memory_checkpointer: bool = True,
    ):
        """
        初始化执行器
        
        Args:
            datasource_luid: 数据源 LUID（可选，默认从环境变量获取）
            tableau_domain: Tableau 域名（可选，用于多环境支持）
            max_replan_rounds: 最大重规划轮数
            use_memory_checkpointer: 是否使用内存检查点
        """
        from tableau_assistant.src.infra.config.settings import settings
        self._datasource_luid = datasource_luid or settings.datasource_luid
        self._tableau_domain = tableau_domain
        self._max_replan_rounds = max_replan_rounds
        
        # 初始化 LangGraph Store 和 DataModelCache
        self._langgraph_store = get_langgraph_store()
        self._data_model_cache = DataModelCache(self._langgraph_store)
        
        self._workflow = create_workflow(
            use_memory_checkpointer=use_memory_checkpointer,
            config={"max_replan_rounds": max_replan_rounds}
        )
    
    async def run(
        self,
        question: str,
        thread_id: Optional[str] = None,
        datasource_luid: Optional[str] = None,
    ) -> WorkflowResult:
        """
        执行工作流
        
        Args:
            question: 用户问题
            thread_id: 线程ID（可选，自动生成）
            datasource_luid: 数据源 LUID（可选，覆盖初始化时的值）
            
        Returns:
            WorkflowResult 包含所有节点输出
        """
        thread_id = thread_id or f"thread_{uuid.uuid4().hex[:8]}"
        ds_luid = datasource_luid or self._datasource_luid
        
        start_time = time.time()
        
        try:
            # 1. 获取 Tableau 认证（多环境支持）
            try:
                auth_ctx = await get_tableau_auth_async(target_domain=self._tableau_domain)
            except TableauAuthError as e:
                logger.error(f"Tableau 认证失败: {e}")
                return WorkflowResult(
                    question=question,
                    success=False,
                    duration=time.time() - start_time,
                    error=f"Tableau 认证失败: {e}",
                )
            
            # 2. 使用 DataModelCache 加载数据模型（缓存优先）
            loader = TableauDataModelLoader(auth_ctx)
            data_model, is_cache_hit = await self._data_model_cache.get_or_load(ds_luid, loader)
            
            # 构建加载状态
            load_status = MetadataLoadStatus(
                source="cache" if is_cache_hit else "api",
                hierarchy_inferred=not is_cache_hit,
                message="从缓存加载" if is_cache_hit else "从 API 加载并缓存"
            )
            logger.info(f"数据模型加载状态: {load_status.message}")
            
            # 3. 创建 WorkflowContext
            ctx = WorkflowContext(
                auth=auth_ctx,
                datasource_luid=ds_luid,
                tableau_domain=self._tableau_domain or auth_ctx.domain,
                data_model=data_model,
                max_replan_rounds=self._max_replan_rounds,
                metadata_load_status=load_status,
            )
            
            # 4. 创建配置
            config = create_workflow_config(thread_id, ctx)
            
            # 5. 注入 middleware 到 config（使所有节点可以使用 middleware）
            from tableau_assistant.src.orchestration.workflow.factory import inject_middleware_to_config
            if hasattr(self._workflow, 'middleware'):
                config = inject_middleware_to_config(config, self._workflow.middleware)
            
            # 6. 构建初始 State（包含数据模型）
            state = self._create_initial_state(question, ctx)
            
            # 7. 执行工作流
            result = await self._workflow.ainvoke(state, config)
            
            duration = time.time() - start_time
            return WorkflowResult.from_state(question, result, duration)
            
        except Exception as e:
            logger.exception(f"Workflow execution failed: {e}")
            return WorkflowResult(
                question=question,
                success=False,
                duration=time.time() - start_time,
                error=str(e),
            )
    
    def _create_initial_state(
        self,
        question: str,
        ctx: WorkflowContext
    ) -> Dict[str, Any]:
        """
        创建初始工作流状态
        
        Args:
            question: 用户问题
            ctx: WorkflowContext
        
        Returns:
            初始状态字典
        """
        return {
            "question": question,
            "messages": [],
            # 数据模型（所有节点共享）
            "data_model": ctx.data_model,
            "dimension_hierarchy": ctx.dimension_hierarchy,
            "datasource": ctx.datasource_luid,
            # Replanner 需要的额外数据（初始为空，由 Insight 节点填充）
            "data_insight_profile": None,
            "current_dimensions": [],
        }
    
    async def stream(
        self,
        question: str,
        thread_id: Optional[str] = None,
        datasource_luid: Optional[str] = None,
    ) -> AsyncIterator[WorkflowEvent]:
        """
        流式执行工作流
        
        Args:
            question: 用户问题
            thread_id: 线程ID（可选，自动生成）
            datasource_luid: 数据源 LUID（可选，覆盖初始化时的值）
            
        Yields:
            WorkflowEvent 事件流
        """
        thread_id = thread_id or f"thread_{uuid.uuid4().hex[:8]}"
        ds_luid = datasource_luid or self._datasource_luid
        
        try:
            # 1. 获取 Tableau 认证
            try:
                auth_ctx = await get_tableau_auth_async(target_domain=self._tableau_domain)
            except TableauAuthError as e:
                logger.error(f"Tableau 认证失败: {e}")
                yield WorkflowEvent(
                    type=EventType.ERROR,
                    content=f"Tableau 认证失败: {e}",
                )
                return
            
            # 2. 使用 DataModelCache 加载数据模型
            loader = TableauDataModelLoader(auth_ctx)
            data_model, is_cache_hit = await self._data_model_cache.get_or_load(ds_luid, loader)
            
            # 构建加载状态
            load_status = MetadataLoadStatus(
                source="cache" if is_cache_hit else "api",
                hierarchy_inferred=not is_cache_hit,
                message="从缓存加载" if is_cache_hit else "从 API 加载并缓存"
            )
            
            # 3. 创建 WorkflowContext
            ctx = WorkflowContext(
                auth=auth_ctx,
                datasource_luid=ds_luid,
                tableau_domain=self._tableau_domain or auth_ctx.domain,
                data_model=data_model,
                max_replan_rounds=self._max_replan_rounds,
                metadata_load_status=load_status,
            )
            
            # 4. 创建配置和初始状态
            config = create_workflow_config(thread_id, ctx)
            
            # 5. 注入 middleware 到 config（使所有节点可以使用 middleware）
            from tableau_assistant.src.orchestration.workflow.factory import inject_middleware_to_config
            if hasattr(self._workflow, 'middleware'):
                config = inject_middleware_to_config(config, self._workflow.middleware)
            
            state = self._create_initial_state(question, ctx)
            
            current_node = None
            event_stream = None
            
            try:
                event_stream = self._workflow.astream_events(state, config, version="v2")
                async for event in event_stream:
                    event_type = event.get("event")
                    event_name = event.get("name", "")
                    event_data = event.get("data", {})
                    
                    # LLM 流式输出 - Token 级别
                    if event_type == "on_chat_model_stream":
                        chunk = event_data.get("chunk")
                        if chunk and hasattr(chunk, "content") and chunk.content:
                            yield WorkflowEvent(
                                type=EventType.TOKEN,
                                node_name=current_node,
                                content=chunk.content,
                            )
                    
                    # 节点开始
                    elif event_type == "on_chain_start" and event_name in self.NODES:
                        current_node = event_name
                        
                        # 发送节点开始事件
                        yield WorkflowEvent(
                            type=EventType.NODE_START,
                            node_name=event_name,
                        )
                    
                    # 节点完成
                    elif event_type == "on_chain_end" and event_name in self.NODES:
                        output = event_data.get("output", {})
                        
                        # 构建节点输出
                        node_output = NodeOutput(**output) if output else None
                        
                        # 发送节点完成事件
                        yield WorkflowEvent(
                            type=EventType.NODE_COMPLETE,
                            node_name=event_name,
                            output=node_output,
                        )
                        current_node = None
                    
                    # 错误
                    elif event_type == "on_chain_error":
                        yield WorkflowEvent(
                            type=EventType.ERROR,
                            node_name=current_node,
                            content=str(event_data.get("error", "未知错误")),
                        )
                
                # 完成
                yield WorkflowEvent(type=EventType.COMPLETE)
            finally:
                # 确保正确关闭异步生成器
                if event_stream is not None:
                    await event_stream.aclose()
            
        except Exception as e:
            logger.exception(f"Workflow streaming failed: {e}")
            yield WorkflowEvent(
                type=EventType.ERROR,
                content=str(e),
            )


