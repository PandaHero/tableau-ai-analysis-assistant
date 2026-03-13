# -*- coding: utf-8 -*-
"""用户反馈路由。"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends

from analytics_assistant.src.api.dependencies import (
    get_feedback_repository,
    get_tableau_username,
)
from analytics_assistant.src.api.models.feedback import FeedbackRequest
from analytics_assistant.src.infra.business_storage import FeedbackRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("")
def submit_feedback(
    request: FeedbackRequest,
    tableau_username: str = Depends(get_tableau_username),
    repo: FeedbackRepository = Depends(get_feedback_repository),
) -> dict[str, str]:
    """提交用户反馈。"""
    feedback_id = str(uuid.uuid4())
    repo.save(
        feedback_id,
        {
            "tableau_username": tableau_username,
            "message_id": request.message_id,
            "type": request.type,
            "reason": request.reason,
            "comment": request.comment,
        },
    )

    logger.info(
        "提交反馈: id=%s, user=%s, message_id=%s, type=%s",
        feedback_id,
        tableau_username,
        request.message_id,
        request.type,
    )
    return {"message": "反馈已提交", "feedback_id": feedback_id}
