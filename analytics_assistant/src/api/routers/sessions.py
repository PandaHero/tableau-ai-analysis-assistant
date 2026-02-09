# -*- coding: utf-8 -*-
"""
会话管理路由

提供会话 CRUD 端点：
- POST   /api/sessions           创建会话
- GET    /api/sessions           获取用户会话列表
- GET    /api/sessions/{id}      获取会话详情
- PUT    /api/sessions/{id}      更新会话
- DELETE /api/sessions/{id}      删除会话

数据隔离：通过 X-Tableau-Username 请求头过滤，跨用户访问返回 403。

注意：使用同步 CRUD 方法（save/find_by_id/find_all/remove），
因为默认 SqliteStore 后端不支持异步操作。FastAPI 会自动在线程池中运行同步端点。
"""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

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
from analytics_assistant.src.infra.storage import BaseRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=CreateSessionResponse)
def create_session(
    request: CreateSessionRequest,
    tableau_username: str = Depends(get_tableau_username),
    repo: BaseRepository = Depends(get_session_repository),
) -> CreateSessionResponse:
    """创建新会话。

    Args:
        request: 创建会话请求
        tableau_username: Tableau 用户名
        repo: 会话 Repository

    Returns:
        创建的会话信息（session_id + created_at）
    """
    session_id = str(uuid.uuid4())
    title = request.title or "新对话"

    saved = repo.save(session_id, {
        "tableau_username": tableau_username,
        "title": title,
        "messages": [],
    })

    logger.info(f"创建会话: id={session_id}, user={tableau_username}")

    return CreateSessionResponse(
        session_id=session_id,
        created_at=datetime.fromisoformat(saved["created_at"]),
    )


@router.get("", response_model=GetSessionsResponse)
def get_sessions(
    tableau_username: str = Depends(get_tableau_username),
    repo: BaseRepository = Depends(get_session_repository),
) -> GetSessionsResponse:
    """获取当前用户的所有会话（按 updated_at 倒序）。

    Args:
        tableau_username: Tableau 用户名
        repo: 会话 Repository

    Returns:
        会话列表和总数
    """
    results = repo.find_all(
        filter_dict={"tableau_username": tableau_username},
    )

    # 按 updated_at 倒序排序
    results.sort(key=lambda x: x.get("updated_at", ""), reverse=True)

    sessions = [
        SessionResponse(
            id=r["id"],
            tableau_username=r["tableau_username"],
            title=r.get("title", ""),
            messages=r.get("messages", []),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in results
    ]

    return GetSessionsResponse(sessions=sessions, total=len(sessions))


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: str,
    tableau_username: str = Depends(get_tableau_username),
    repo: BaseRepository = Depends(get_session_repository),
) -> SessionResponse:
    """获取会话详情。

    Args:
        session_id: 会话 ID
        tableau_username: Tableau 用户名
        repo: 会话 Repository

    Returns:
        会话详情

    Raises:
        HTTPException: 404 会话不存在，403 无权访问
    """
    data = repo.find_by_id(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    if data.get("tableau_username") != tableau_username:
        raise HTTPException(status_code=403, detail="无权访问此会话")

    return SessionResponse(
        id=data.get("id", session_id),
        tableau_username=data["tableau_username"],
        title=data.get("title", ""),
        messages=data.get("messages", []),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )


@router.put("/{session_id}", response_model=SessionResponse)
def update_session(
    session_id: str,
    request: UpdateSessionRequest,
    tableau_username: str = Depends(get_tableau_username),
    repo: BaseRepository = Depends(get_session_repository),
) -> SessionResponse:
    """更新会话（标题和/或消息列表）。

    Args:
        session_id: 会话 ID
        request: 更新请求
        tableau_username: Tableau 用户名
        repo: 会话 Repository

    Returns:
        更新后的会话

    Raises:
        HTTPException: 404 会话不存在，403 无权访问
    """
    data = repo.find_by_id(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    if data.get("tableau_username") != tableau_username:
        raise HTTPException(status_code=403, detail="无权访问此会话")

    # 部分更新：只更新非 None 字段
    update_data = {
        "tableau_username": data["tableau_username"],
        "title": data.get("title", ""),
        "messages": data.get("messages", []),
    }

    if request.title is not None:
        update_data["title"] = request.title

    if request.messages is not None:
        update_data["messages"] = [
            {"role": msg.role, "content": msg.content}
            for msg in request.messages
        ]

    saved = repo.save(session_id, update_data)

    logger.info(f"更新会话: id={session_id}, user={tableau_username}")

    return SessionResponse(
        id=saved.get("id", session_id),
        tableau_username=saved["tableau_username"],
        title=saved.get("title", ""),
        messages=saved.get("messages", []),
        created_at=saved["created_at"],
        updated_at=saved["updated_at"],
    )


@router.delete("/{session_id}")
def delete_session(
    session_id: str,
    tableau_username: str = Depends(get_tableau_username),
    repo: BaseRepository = Depends(get_session_repository),
) -> dict:
    """删除会话。

    Args:
        session_id: 会话 ID
        tableau_username: Tableau 用户名
        repo: 会话 Repository

    Returns:
        删除确认

    Raises:
        HTTPException: 404 会话不存在，403 无权访问
    """
    data = repo.find_by_id(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    if data.get("tableau_username") != tableau_username:
        raise HTTPException(status_code=403, detail="无权访问此会话")

    repo.remove(session_id)

    logger.info(f"删除会话: id={session_id}, user={tableau_username}")

    return {"message": "会话已删除"}
