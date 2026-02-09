# -*- coding: utf-8 -*-
"""
用户反馈路由

提供用户反馈端点：
- POST /api/feedback    提交用户反馈

注意：使用同步 CRUD 方法，因为默认 SqliteStore 后端不支持异步操作。
"""

import logging
import uuid

from fastapi import APIRouter, Depends

from analytics_assistant.src.api.dependencies import (
    get_feedback_repository,
    get_tableau_username,
)
from analytics_assistant.src.api.models.feedback import FeedbackRequest
from analytics_assistant.src.infra.storage import BaseRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("")
def submit_feedback(
    request: FeedbackRequest,
    tableau_username: str = Depends(get_tableau_username),
    repo: BaseRepository = Depends(get_feedback_repository),
) -> dict:
    """提交用户反馈。

    Args:
        request: 反馈请求
        tableau_username: Tableau 用户名
        repo: 反馈 Repository

    Returns:
        提交确认
    """
    feedback_id = str(uuid.uuid4())

    repo.save(feedback_id, {
        "tableau_username": tableau_username,
        "message_id": request.message_id,
        "type": request.type,
        "reason": request.reason,
        "comment": request.comment,
    })

    logger.info(
        f"提交反馈: id={feedback_id}, user={tableau_username}, "
        f"message_id={request.message_id}, type={request.type}"
    )

    return {"message": "反馈已提交", "feedback_id": feedback_id}
