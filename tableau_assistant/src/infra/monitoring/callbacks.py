"""
LangChain Callbacks 监控系统

基于 SQLite 的 Callbacks，追踪 LLM 调用、成本、性能
"""
from langchain_core.callbacks import BaseCallbackHandler
from typing import Any, Dict, List, Optional
from uuid import UUID
import time
import logging

logger = logging.getLogger(__name__)


class SQLiteTrackingCallback(BaseCallbackHandler):
    """基于 SQLite 的追踪 Callback"""
    
    def __init__(self, store, user_id: str, session_id: str, agent_name: str = "unknown"):
        self.store = store
        self.user_id = user_id
        self.session_id = session_id
        self.agent_name = agent_name
        self.call_stack = {}
    
    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], *, run_id: UUID,
                     parent_run_id: Optional[UUID] = None, tags: Optional[List[str]] = None,
                     metadata: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        try:
            self.call_stack[run_id] = {
                "run_id": str(run_id),
                "parent_run_id": str(parent_run_id) if parent_run_id else None,
                "user_id": self.user_id,
                "session_id": self.session_id,
                "agent_name": self.agent_name,
                "model": serialized.get("name", "unknown"),
                "prompt_length": len(prompts[0]) if prompts else 0,
                "tags": tags or [],
                "metadata": metadata or {},
                "start_time": time.time(),
                "status": "running"
            }
        except Exception as e:
            logger.error(f"[Callback] on_llm_start 失败: {e}")
    
    def on_llm_end(self, response: Any, *, run_id: UUID, parent_run_id: Optional[UUID] = None,
                   tags: Optional[List[str]] = None, metadata: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        try:
            if run_id not in self.call_stack:
                return
            call_info = self.call_stack[run_id]
            end_time = time.time()
            token_usage = {}
            if hasattr(response, 'llm_output') and response.llm_output:
                token_usage = response.llm_output.get('token_usage', {})
            call_info.update({
                "end_time": end_time,
                "duration_ms": int((end_time - call_info["start_time"]) * 1000),
                "status": "completed",
                "prompt_tokens": token_usage.get('prompt_tokens', 0),
                "completion_tokens": token_usage.get('completion_tokens', 0),
                "total_tokens": token_usage.get('total_tokens', 0),
                "response_length": len(str(response))
            })
            self._save_to_store(call_info)
            del self.call_stack[run_id]
        except Exception as e:
            logger.error(f"[Callback] on_llm_end 失败: {e}")
    
    def on_llm_error(self, error: Exception, *, run_id: UUID, parent_run_id: Optional[UUID] = None,
                     tags: Optional[List[str]] = None, metadata: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        try:
            if run_id not in self.call_stack:
                return
            call_info = self.call_stack[run_id]
            end_time = time.time()
            call_info.update({
                "end_time": end_time,
                "duration_ms": int((end_time - call_info["start_time"]) * 1000),
                "status": "error",
                "error": str(error),
                "error_type": type(error).__name__
            })
            self._save_to_store(call_info)
            del self.call_stack[run_id]
        except Exception as e:
            logger.error(f"[Callback] on_llm_error 失败: {e}")
    
    def _save_to_store(self, call_info: Dict[str, Any]):
        try:
            self.store.put(
                namespace=("llm_calls", self.user_id, self.session_id),
                key=call_info["run_id"],
                value=call_info,
                ttl=7 * 24 * 3600
            )
        except Exception as e:
            logger.error(f"[Callback] 保存到 Store 失败: {e}")
    
    def get_session_stats(self) -> Dict[str, Any]:
        try:
            items = self.store.search(namespace_prefix=("llm_calls", self.user_id, self.session_id), limit=1000)
            if not items:
                return {"total_calls": 0, "total_tokens": 0, "total_cost": 0.0, "avg_duration_ms": 0}
            total_calls = len(items)
            total_tokens = sum(item.value.get("total_tokens", 0) for item in items)
            avg_duration = sum(item.value.get("duration_ms", 0) for item in items) / total_calls
            return {"total_calls": total_calls, "total_tokens": total_tokens, "avg_duration_ms": int(avg_duration)}
        except Exception as e:
            logger.error(f"[Callback] 获取会话统计失败: {e}")
            return {}


__all__ = ["SQLiteTrackingCallback"]
