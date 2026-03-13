# -*- coding: utf-8 -*-
"""后台 artifact refresh 调度运行时。

这个模块把 `prepare_datasource_artifacts()` 包装成正式的异步 builder 入口。
职责只有三件事：
1. 对同一份 refresh request 去重，避免重复构建。
2. 控制并发与队列上限，避免在线请求把后台 builder 撑爆。
3. 暴露轻量运行时指标，方便观察队列深度和最近构建结果。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass
from threading import Lock
from typing import Any, Optional

from analytics_assistant.src.platform.tableau import data_loader as data_loader_module
from analytics_assistant.src.platform.tableau.auth import TableauAuthContext

logger = logging.getLogger(__name__)

_runtime_metrics_lock = Lock()
_active_request_keys: set[str] = set()
_completed_builds = 0
_failed_builds = 0
_last_build_latency_ms: Optional[int] = None
_last_completed_request_key: Optional[str] = None
_last_failed_request_key: Optional[str] = None


@dataclass(slots=True)
class ArtifactRefreshRuntimeSnapshot:
    """描述当前 builder 运行时的轻量快照。"""

    active_requests: int
    queued_requests: int
    max_concurrency: int
    max_queue_size: int
    completed_builds: int
    failed_builds: int
    last_build_latency_ms: Optional[int]
    last_completed_request_key: Optional[str]
    last_failed_request_key: Optional[str]


class ArtifactRefresher:
    """负责执行单次 datasource artifact refresh。"""

    async def refresh(
        self,
        *,
        datasource_id: str,
        auth: Optional[TableauAuthContext],
        refresh_request: Optional[dict[str, object]],
    ) -> None:
        async with data_loader_module.TableauDataLoader() as loader:
            await loader.prepare_datasource_artifacts(
                datasource_id=datasource_id,
                auth=auth,
                refresh_request=refresh_request,
            )


class ArtifactBuilderRuntime:
    """后台 datasource artifact builder。

    这是进程内 runtime，不做分布式锁；它负责把重复请求合并，并把构建压到
    配置化并发与队列上限内。
    """

    def __init__(self, refresher: Optional[ArtifactRefresher] = None) -> None:
        self._refresher = refresher or ArtifactRefresher()

    def schedule(
        self,
        *,
        datasource_id: str,
        auth: Optional[TableauAuthContext] = None,
        refresh_request: Optional[dict[str, object]] = None,
    ) -> bool:
        request_key = data_loader_module._build_prewarm_request_key(
            datasource_id=datasource_id,
            auth=auth,
            refresh_request=refresh_request,
        )
        max_concurrency, max_queue_size = data_loader_module._get_prewarm_runtime_limits()
        with data_loader_module._prewarm_lock:
            if request_key in data_loader_module._prewarming_requests:
                logger.debug("后台 refresh 请求已在队列中，跳过重复调度: %s", request_key)
                return False
            if len(data_loader_module._prewarming_requests) >= max_queue_size:
                logger.warning(
                    "后台 refresh 队列已满，拒绝新请求: datasource=%s queue_size=%s max_queue_size=%s %s",
                    datasource_id,
                    len(data_loader_module._prewarming_requests),
                    max_queue_size,
                    data_loader_module._describe_refresh_request(refresh_request),
                )
                return False
            data_loader_module._prewarming_requests.add(request_key)

        async def _run() -> None:
            semaphore = data_loader_module._get_prewarm_semaphore(max_concurrency)
            started_at = time.perf_counter()
            try:
                async with semaphore:
                    with data_loader_module._prewarm_lock:
                        queued_count = max(
                            0,
                            len(data_loader_module._prewarming_requests)
                            - len(_active_request_keys)
                            - 1,
                        )
                    with _runtime_metrics_lock:
                        _active_request_keys.add(request_key)
                    logger.info(
                        "后台 refresh 开始: datasource=%s concurrency_limit=%s queued=%s %s",
                        datasource_id,
                        max_concurrency,
                        queued_count,
                        data_loader_module._describe_refresh_request(refresh_request),
                    )
                    await self._refresher.refresh(
                        datasource_id=datasource_id,
                        auth=auth,
                        refresh_request=refresh_request,
                    )
                    self._record_success(
                        request_key=request_key,
                        latency_ms=int((time.perf_counter() - started_at) * 1000),
                    )
                    logger.info(
                        "后台 refresh 完成: datasource=%s %s",
                        datasource_id,
                        data_loader_module._describe_refresh_request(refresh_request),
                    )
            except Exception as exc:
                self._record_failure(
                    request_key=request_key,
                    latency_ms=int((time.perf_counter() - started_at) * 1000),
                )
                logger.warning(
                    "后台 refresh 失败: datasource=%s %s error=%s",
                    datasource_id,
                    data_loader_module._describe_refresh_request(refresh_request),
                    exc,
                )
            finally:
                with _runtime_metrics_lock:
                    _active_request_keys.discard(request_key)
                with data_loader_module._prewarm_lock:
                    data_loader_module._prewarming_requests.discard(request_key)
                    data_loader_module._prewarm_tasks.pop(request_key, None)

        try:
            task = asyncio.create_task(_run())
        except RuntimeError:
            with data_loader_module._prewarm_lock:
                data_loader_module._prewarming_requests.discard(request_key)
            logger.warning("当前上下文没有运行中的事件循环，无法调度后台 refresh 任务")
            return False

        with data_loader_module._prewarm_lock:
            data_loader_module._prewarm_tasks[request_key] = task
        return True

    @staticmethod
    def _record_success(*, request_key: str, latency_ms: int) -> None:
        global _completed_builds, _last_build_latency_ms, _last_completed_request_key
        with _runtime_metrics_lock:
            _completed_builds += 1
            _last_build_latency_ms = latency_ms
            _last_completed_request_key = request_key

    @staticmethod
    def _record_failure(*, request_key: str, latency_ms: int) -> None:
        global _failed_builds, _last_build_latency_ms, _last_failed_request_key
        with _runtime_metrics_lock:
            _failed_builds += 1
            _last_build_latency_ms = latency_ms
            _last_failed_request_key = request_key


_artifact_builder_runtime = ArtifactBuilderRuntime()


def schedule_datasource_artifact_preparation(
    datasource_id: str,
    auth: Optional[TableauAuthContext] = None,
    refresh_request: Optional[dict[str, object]] = None,
) -> bool:
    """调度后台 datasource artifact refresh。"""

    return _artifact_builder_runtime.schedule(
        datasource_id=datasource_id,
        auth=auth,
        refresh_request=refresh_request,
    )


def get_datasource_artifact_refresh_runtime_snapshot() -> dict[str, Any]:
    """返回当前 builder 运行时的轻量观测快照。"""

    max_concurrency, max_queue_size = data_loader_module._get_prewarm_runtime_limits()
    with _runtime_metrics_lock:
        snapshot = ArtifactRefreshRuntimeSnapshot(
            active_requests=len(_active_request_keys),
            queued_requests=max(
                0,
                len(data_loader_module._prewarming_requests) - len(_active_request_keys),
            ),
            max_concurrency=max_concurrency,
            max_queue_size=max_queue_size,
            completed_builds=_completed_builds,
            failed_builds=_failed_builds,
            last_build_latency_ms=_last_build_latency_ms,
            last_completed_request_key=_last_completed_request_key,
            last_failed_request_key=_last_failed_request_key,
        )
    return asdict(snapshot)


def reset_datasource_artifact_refresh_runtime_for_tests() -> None:
    """重置 builder 运行时指标，仅供测试使用。"""

    global _completed_builds, _failed_builds, _last_build_latency_ms
    global _last_completed_request_key, _last_failed_request_key
    with _runtime_metrics_lock:
        _active_request_keys.clear()
        _completed_builds = 0
        _failed_builds = 0
        _last_build_latency_ms = None
        _last_completed_request_key = None
        _last_failed_request_key = None


__all__ = [
    "ArtifactBuilderRuntime",
    "ArtifactRefresher",
    "get_datasource_artifact_refresh_runtime_snapshot",
    "schedule_datasource_artifact_preparation",
]
