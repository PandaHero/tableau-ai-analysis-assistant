"""业务存储模块。

该模块承载需要长期保留、可审计、可分页查询的业务数据：
- 会话与消息
- 用户设置
- 用户反馈
- 分析运行记录
- 中断记录
- 查询审计日志

与 `infra.storage` 中基于 LangGraph BaseStore 的通用 KV/缓存能力不同，
这里使用结构化表模型，满足生产环境下的分页、审计和恢复需求。
"""

from .database import BusinessDatabase, get_business_database, reset_business_database
from .repositories import (
    AnalysisRunRepository,
    FeedbackRepository,
    InterruptRepository,
    MessageRepository,
    QueryAuditRepository,
    SessionRepository,
    SettingsRepository,
)

__all__ = [
    "AnalysisRunRepository",
    "BusinessDatabase",
    "FeedbackRepository",
    "InterruptRepository",
    "MessageRepository",
    "QueryAuditRepository",
    "SessionRepository",
    "SettingsRepository",
    "get_business_database",
    "reset_business_database",
]
