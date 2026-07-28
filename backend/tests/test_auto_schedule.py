"""Step 15：自动排期 + SSE 通知测试。"""

from datetime import date
from pathlib import Path
import sys
from uuid import uuid4

import pytest
from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.notification_service import (
    format_sse_message,
    notification_service,
)
from app.core.scheduler import run_daily_auto_schedule
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.daily_task import DailyTask
from app.models.knowledge_node import KnowledgeNode
from app.models.plan import Plan
from app.models.user import User


@pytest.mark.asyncio
async def test_notification_publish_delivers_to_subscriber():
    suffix = uuid4().hex[:8]
    user_id = int(suffix[:6], 16) % 900000 + 100000

    queue = await notification_service.subscribe(user_id)
    try:
        delivered = await notification_service.publish_schedule_updated(
            user_id,
            date_str="2026-07-28",
            tasks=[],
            total_minutes=0,
            message="测试排期通知",
        )
        assert delivered == 1
        event = await queue.get()
        assert event["type"] == "schedule_updated"
        assert event["payload"]["date"] == "2026-07-28"
        assert event["payload"]["message"] == "测试排期通知"
        assert "event_id" in event
        assert "timestamp" in event

        frame = format_sse_message(event)
        assert frame.startswith("event: schedule_updated\n")
        assert "data: " in frame
    finally:
        await notification_service.unsubscribe(user_id, queue)


@pytest.mark.asyncio
async def test_daily_auto_schedule_creates_tasks_and_notifies():
    suffix = uuid4().hex[:8]
    async for db in get_db():
        user = User(
            username=f"auto-sched-{suffix}",
            email=f"auto-sched-{suffix}@example.com",
            hashed_password="test",
            daily_available_minutes=60,
        )
        db.add(user)
        await db.flush()
        plan = Plan(user_id=user.id, title="自动排期计划", status="active", priority=1)
        db.add(plan)
        await db.flush()
        db.add(
            KnowledgeNode(
                plan_id=plan.id,
                name="自动排期知识点",
                estimated_minutes=40,
                order_index=1,
            )
        )
        await db.commit()
        user_id = user.id
        break

    queue = await notification_service.subscribe(user_id)
    try:
        result = await run_daily_auto_schedule(date.today())
        assert result["success"] >= 1
        assert any(item["user_id"] == user_id and item["ok"] for item in result["details"])

        async for db in get_db():
            tasks = (
                await db.execute(
                    select(DailyTask).where(
                        DailyTask.user_id == user_id,
                        DailyTask.scheduled_date == date.today(),
                    )
                )
            ).scalars().all()
            assert len(tasks) >= 1
            assert tasks[0].guide_content
            assert "## 重点理解" in (tasks[0].guide_content or "") or len(tasks[0].guide_content) > 0
            break

        event = await queue.get()
        assert event["type"] == "schedule_updated"
        assert event["payload"]["total_tasks"] >= 1
        assert isinstance(event["payload"]["tasks"], list)
        assert "guide_content" in event["payload"]["tasks"][0]
    finally:
        await notification_service.unsubscribe(user_id, queue)


def test_events_stream_rejects_invalid_token(client):
    response = client.get("/api/v1/events/stream?token=not-a-valid-jwt")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_events_stream_route_registered_with_valid_token_auth():
    """合法 token 通过鉴权后可进入流式响应（不断开长连接，只校验入口）。"""

    from fastapi.responses import StreamingResponse
    from app.api.v1 import events as events_module
    from app.db.session import get_db as _get_db

    suffix = uuid4().hex[:8]
    async for db in get_db():
        user = User(
            username=f"sse-{suffix}",
            email=f"sse-{suffix}@example.com",
            hashed_password="test",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id
        break

    token = create_access_token({"sub": str(user_id)})
    async for db in _get_db():
        response = await events_module.event_stream(token=token, db=db)
        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"
        break
