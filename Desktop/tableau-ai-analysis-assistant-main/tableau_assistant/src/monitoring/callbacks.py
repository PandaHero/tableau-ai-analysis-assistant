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
    """
    基于 SQLite 的追踪 Callback
    
    追踪所有 LLM 调用并保存到 SQLite（通过 PersistentStore）
    """
    
    def __init__(self, store, user_id: str, session_id: str, agent_name: str = "unknown"):
        """
        初始化追踪 Callback
        
        Args:
            store: PersistentStore 实例
            user_id: 用户ID
            session_id: 会话ID
            agent_name: Agent 名称
        """
        self.store = store
        self.user_id = user_id
        self.session_id = session_id
        self.agent_name = agent_name
        self.call_stack = {}  # {run_id: call_info}
    
    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> None:
        """LLM 调用开始"""
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
            
            logger.debug(f"[Callback] LLM 调用开始: {self.agent_name} (run_id: {str(run_id)[:8]}...)")
        
        except Exception as e:
            logger.error(f"[Callback] on_llm_start 失败: {e}")
    
    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> None:
        """LLM 调用结束"""
        try:
            if run_id not in self.call_stack:
                logger.warning(f"[Callback] run_id {run_id} 不在调用栈中")
                return
            
            call_info = self.call_stack[run_id]
            end_time = time.time()
            
            # 提取 token 使用量
            token_usage = {}
            if hasattr(response, 'llm_output') and response.llm_output:
                token_usage = response.llm_output.get('token_usage', {})
            
            prompt_tokens = token_usage.get('prompt_tokens', 0)
            completion_tokens = token_usage.get('completion_tokens', 0)
            total_tokens = token_usage.get('total_tokens', 0)
            
            # 更新调用信息
            call_info.update({
                "end_time": end_time,
                "duration_ms": int((end_time - call_info["start_time"]) * 1000),
                "status": "completed",
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "response_length": len(str(response))
            })
            
            # 保存到 SQLite
            self._save_to_store(call_info)
            
            logger.info(
                f"[Callback] LLM 调用完成: {self.agent_name} "
                f"({total_tokens} tokens, {call_info['duration_ms']}ms)"
            )
            
            # 清理
            del self.call_stack[run_id]
        
        except Exception as e:
            logger.error(f"[Callback] on_llm_end 失败: {e}")
    
    def on_llm_error(
        self,
        error: Exception,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> None:
        """LLM 调用错误"""
        try:
            if run_id not in self.call_stack:
                logger.warning(f"[Callback] run_id {run_id} 不在调用栈中")
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
            
            # 保存到 SQLite
            self._save_to_store(call_info)
            
            logger.error(
                f"[Callback] LLM 调用失败: {self.agent_name} "
                f"({call_info['duration_ms']}ms) - {error}"
            )
            
            # 清理
            del self.call_stack[run_id]
        
        except Exception as e:
            logger.error(f"[Callback] on_llm_error 失败: {e}")
    
    def _save_to_store(self, call_info: Dict[str, Any]):
        """保存调用信息到 Store"""
        try:
            # 使用命名空间：("llm_calls", user_id, session_id)
            self.store.put(
                namespace=("llm_calls", self.user_id, self.session_id),
                key=call_info["run_id"],
                value=call_info,
                ttl=7 * 24 * 3600  # 保留7天
            )
        except Exception as e:
            logger.error(f"[Callback] 保存到 Store 失败: {e}")
    

    def get_session_stats(self) -> Dict[str, Any]:
        """获取当前会话的统计信息"""
        try:
            # 搜索当前会话的所有调用
            items = self.store.search(
                namespace_prefix=("llm_calls", self.user_id, self.session_id),
                limit=1000
            )
            
            if not items:
                return {
                    "total_calls": 0,
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "avg_duration_ms": 0
                }
            
            # 统计
            total_calls = len(items)
            total_tokens = sum(item.value.get("total_tokens", 0) for item in items)
            avg_duration = sum(item.value.get("duration_ms", 0) for item in items) / total_calls
            
            # 按状态分组
            status_counts = {}
            for item in items:
                status = item.value.get("status", "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1
            
            # 按 Agent 分组
            agent_counts = {}
            for item in items:
                agent = item.value.get("agent_name", "unknown")
                agent_counts[agent] = agent_counts.get(agent, 0) + 1
            
            return {
                "total_calls": total_calls,
                "total_tokens": total_tokens,
                "avg_duration_ms": int(avg_duration),
                "status_counts": status_counts,
                "agent_counts": agent_counts
            }
        except Exception as e:
            logger.error(f"[Callback] 获取会话统计失败: {e}")
            return {}


# ============= 导出 =============

__all__ = [
    "SQLiteTrackingCallback",
]
