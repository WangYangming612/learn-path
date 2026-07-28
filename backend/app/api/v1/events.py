"""
全局 SSE 事件流 API

What: GET /events/stream?token= 建立长连接，推送排期/周报/干预等事件
Why: 浏览器 EventSource 无法自定义 Authorization 头，需用 query token 鉴权
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.notification_service import format_sse_message, notification_service
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["events"])

# 无业务事件时发送注释行保活（契约：60 秒）
_KEEPALIVE_SECONDS = 60


async def _user_from_token(token: str, db: AsyncSession) -> User:
    """用 query token 解析并校验用户（EventSource 专用）。"""

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
        )
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 载荷无效：缺少 sub 字段",
        )

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用",
        )
    return user


async def _event_generator(user_id: int) -> AsyncGenerator[str, None]:
    """订阅通知队列并持续产出 SSE 帧。"""

    queue = await notification_service.subscribe(user_id)
    try:
        # 首帧注释，确认连接建立
        yield ": connected\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_SECONDS)
                yield format_sse_message(event)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        logger.debug("[EventsAPI] stream cancelled user=%s", user_id)
        raise
    finally:
        await notification_service.unsubscribe(user_id, queue)


@router.get("/stream")
async def event_stream(
    token: str = Query(..., description="JWT access token"),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    全局 SSE 推送入口

    事件类型见 docs/contracts/sse-events.md：
    schedule_updated / weekly_report / intervention / feedback_stream
    """

    user = await _user_from_token(token, db)
    return StreamingResponse(
        _event_generator(user.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
