# -*- coding: utf-8 -*-
"""
WorkflowExecutor - 工作流执行器

编排完整的查询执行流程：
1. 认证（获取 Tableau auth token）
2. 数据源解析 + 数据模型加载（TableauDataLoader）
3. 字段语义推断（FieldSemanticInference）
4. 创建 WorkflowContext 并注入 SSE 回调
5. 执行 semantic_parser 子图

使用示例:
    executor = WorkflowExecutor(tableau_username="admin")
    async for event in executor.execute_stream(
        question="各区域销售额",
        datasource_name="销售数据",
    ):
        # event: {"type": "token", "content": "..."} 等
        yield format_sse_event(event)
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

from analytics_assistant.src.agents.semantic_parser.graph import (
    compile_semantic_parser_graph,
)
from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader

from .callbacks import SSECallbacks
from .context import WorkflowContext, create_workflow_config

logger = logging.getLogger(__name__)

# 默认超时（秒）
_DEFAULT_WORKFLOW_TIMEOUT = 60


class WorkflowExecutor:
    """工作流执行器。

    负责编排完整的查询工作流：认证 → 数据模型加载 → 字段语义 → 语义解析。

    重要说明：
    - semantic_parser 子图已经是完整的端到端流程（15+ 节点）
    - field_mapper 在 semantic_parser 子图内部调用
    - field_semantic 在数据准备阶段通过 WorkflowContext.load_field_semantic() 调用

    Attributes:
        _tableau_username: Tableau 用户名
        _timeout: 工作流执行超时（秒）
    """

    def __init__(self, tableau_username: str):
        """初始化 WorkflowExecutor。

        Args:
            tableau_username: Tableau 用户名（用于认证和数据隔离）
        """
        self._tableau_username = tableau_username
        self._timeout = self._load_timeout()

    def _load_timeout(self) -> int:
        """从 app.yaml 读取工作流超时配置。

        Returns:
            超时秒数
        """
        try:
            config = get_config()
            return config.get("api", {}).get(
                "timeout", {},
            ).get("workflow_execution", _DEFAULT_WORKFLOW_TIMEOUT)
        except Exception as e:
            logger.warning(f"读取超时配置失败，使用默认值: {e}")
            return _DEFAULT_WORKFLOW_TIMEOUT

    async def execute_stream(
        self,
        question: str,
        datasource_name: str,
        history: Optional[List[Dict[str, str]]] = None,
        language: str = "zh",
        analysis_depth: str = "detailed",
        session_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """执行工作流并返回 SSE 事件流。

        内部流程：
        1. 认证（获取 Tableau auth token）
        2. 数据模型加载（TableauDataLoader，内部解析 name → LUID）
        3. 字段语义推断
        4. 创建 WorkflowContext + 注入 SSE 回调
        5. 执行 semantic_parser 子图

        Args:
            question: 用户问题
            datasource_name: 数据源名称（前端传入）
            history: 对话历史（已裁剪）
            language: 语言（"zh" 或 "en"）
            analysis_depth: 分析深度
            session_id: 会话 ID

        Yields:
            SSE 事件字典，如 {"type": "token", "content": "..."}
        """
        event_queue: asyncio.Queue[Optional[Dict[str, Any]]] = asyncio.Queue()
        callbacks = SSECallbacks(event_queue, language=language)

        async def _run_workflow() -> None:
            """在后台任务中执行工作流。"""
            try:
                # 1. 认证
                await callbacks.on_node_start("authentication")
                auth = await get_tableau_auth_async()
                await callbacks.on_node_end("authentication")

                # 2. 数据模型加载（内部自动解析 datasource_name → LUID）
                await callbacks.on_node_start("data_preparation")
                loader = TableauDataLoader()
                data_model = await loader.load_data_model(
                    datasource_name=datasource_name,
                    auth=auth,
                )
                datasource_luid = data_model.datasource_id

                # 3. 创建 WorkflowContext 并加载字段语义
                ctx = WorkflowContext(
                    auth=auth,
                    datasource_luid=datasource_luid,
                    data_model=data_model,
                    current_time=datetime.now().isoformat(),
                    user_id=self._tableau_username,
                )
                ctx = await ctx.load_field_semantic()
                await callbacks.on_node_end("data_preparation")

                # 4. 编译 semantic_parser 子图
                graph = compile_semantic_parser_graph()

                # 5. 创建 RunnableConfig，注入回调
                config = create_workflow_config(
                    thread_id=session_id or f"stream-{datasource_luid}",
                    context=ctx,
                    on_token=callbacks.on_token,
                    on_thinking=callbacks.on_thinking,
                )

                # 6. 构建初始状态
                initial_state = {
                    "question": question,
                    "datasource_luid": datasource_luid,
                    "history": history or [],
                    "language": language,
                    "analysis_depth": analysis_depth,
                }

                # 7. 执行子图，监听节点事件
                async for event in graph.astream(
                    initial_state,
                    config,
                    stream_mode="updates",
                ):
                    for node_name, node_output in event.items():
                        await callbacks.on_node_start(node_name)

                        # 转发结构化数据事件
                        if isinstance(node_output, dict):
                            if "query_result" in node_output:
                                await event_queue.put({
                                    "type": "data",
                                    "tableData": node_output["query_result"],
                                })
                            if "chart_config" in node_output:
                                await event_queue.put({
                                    "type": "chart",
                                    "chartConfig": node_output["chart_config"],
                                })
                            if "suggestions" in node_output:
                                await event_queue.put({
                                    "type": "suggestions",
                                    "questions": node_output["suggestions"],
                                })

                        await callbacks.on_node_end(node_name)

                # 完成
                await event_queue.put({"type": "complete"})

            except asyncio.CancelledError:
                logger.info("工作流被取消")
                await event_queue.put({
                    "type": "error",
                    "error": "请求已取消",
                })
            except Exception as e:
                logger.exception(
                    f"工作流执行失败: user={self._tableau_username}, "
                    f"datasource={datasource_name}, error={e}"
                )
                await event_queue.put({
                    "type": "error",
                    "error": str(e),
                })
            finally:
                # 标记队列结束
                await event_queue.put(None)

        # 启动后台任务（带超时）
        workflow_task = asyncio.create_task(_run_workflow())

        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        event_queue.get(),
                        timeout=float(self._timeout),
                    )
                except asyncio.TimeoutError:
                    logger.error(
                        f"工作流超时: timeout={self._timeout}s, "
                        f"user={self._tableau_username}"
                    )
                    yield {"type": "error", "error": "工作流执行超时"}
                    break

                if event is None:
                    break
                yield event
        finally:
            # 客户端断开时取消工作流
            if not workflow_task.done():
                workflow_task.cancel()
                try:
                    await workflow_task
                except asyncio.CancelledError:
                    pass


__all__ = [
    "WorkflowExecutor",
]
