# -*- coding: utf-8 -*-
"""会话管理路由。"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from analytics_assistant.src.api.dependencies import (
    get_session_repository,
    get_tableau_username,
)
from analytics_assistant.src.api.models.session import (
    CreateSessionRequest,
    CreateSessionResponse,
    GetSessionsResponse,
    SessionResponse,
    UpdateSessionRequest,
)
from analytics_assistant.src.infra.business_storage import SessionRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=CreateSessionResponse)
def create_session(
    request: CreateSessionRequest,
    tableau_username: str = Depends(get_tableau_username),
    repo: SessionRepository = Depends(get_session_repository),
) -> CreateSessionResponse:
    """创建新会话。"""
    session_id = str(uuid.uuid4())
    title = str(request.title or "").strip() or "新对话"

    saved = repo.create_session(
        session_id=session_id,
        tableau_username=tableau_username,
        title=title,
    )
    logger.info("创建会话: id=%s, user=%s", session_id, tableau_username)

    return CreateSessionResponse(
        session_id=session_id,
        created_at=datetime.fromisoformat(saved["created_at"].replace("Z", "+00:00")),
    )


@router.get("", response_model=GetSessionsResponse)
def get_sessions(
    offset: int = Query(0, ge=0, description="分页偏移量"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    tableau_username: str = Depends(get_tableau_username),
    repo: SessionRepository = Depends(get_session_repository),
) -> GetSessionsResponse:
    """获取当前用户的会话列表。"""
    results, total = repo.list_for_user(
        tableau_username=tableau_username,
        offset=offset,
        limit=limit,
    )
    sessions = [
        SessionResponse(
            id=item["id"],
            tableau_username=item["tableau_username"],
            title=item.get("title", ""),
            messages=item.get("messages", []),
            created_at=item["created_at"],
            updated_at=item["updated_at"],
        )
        for item in results
    ]
    return GetSessionsResponse(sessions=sessions, total=total)


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: UUID = Path(..., description="会话 ID（UUID 格式）"),
    tableau_username: str = Depends(get_tableau_username),
    repo: SessionRepository = Depends(get_session_repository),
) -> SessionResponse:
    """获取会话详情。"""
    sid = str(session_id)
    data = repo.find_by_id(sid)
    if data is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if data.get("tableau_username") != tableau_username:
        raise HTTPException(status_code=403, detail="无权访问此会话")

    return SessionResponse(
        id=data.get("id", sid),
        tableau_username=data["tableau_username"],
        title=data.get("title", ""),
        messages=data.get("messages", []),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )


@router.put("/{session_id}", response_model=SessionResponse)
def update_session(
    request: UpdateSessionRequest,
    session_id: UUID = Path(..., description="会话 ID（UUID 格式）"),
    tableau_username: str = Depends(get_tableau_username),
    repo: SessionRepository = Depends(get_session_repository),
) -> SessionResponse:
    """更新会话标题或消息。"""
    sid = str(session_id)
    data = repo.find_by_id(sid)
    if data is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if data.get("tableau_username") != tableau_username:
        raise HTTPException(status_code=403, detail="无权访问此会话")

    updated = repo.update_session(
        session_id=sid,
        title=request.title,
        messages=(
            [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ]
            if request.messages is not None
            else None
        ),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    logger.info("更新会话: id=%s, user=%s", sid, tableau_username)
    return SessionResponse(
        id=updated.get("id", sid),
        tableau_username=updated["tableau_username"],
        title=updated.get("title", ""),
        messages=updated.get("messages", []),
        created_at=updated["created_at"],
        updated_at=updated["updated_at"],
    )


@router.delete("/{session_id}")
def delete_session(
    session_id: UUID = Path(..., description="会话 ID（UUID 格式）"),
    tableau_username: str = Depends(get_tableau_username),
    repo: SessionRepository = Depends(get_session_repository),
) -> dict[str, str]:
    """删除会话。"""
    sid = str(session_id)
    data = repo.find_by_id(sid)
    if data is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if data.get("tableau_username") != tableau_username:
        raise HTTPException(status_code=403, detail="无权访问此会话")

    repo.delete_session(sid)
    logger.info("删除会话: id=%s, user=%s", sid, tableau_username)
    return {"message": "会话已删除"}
