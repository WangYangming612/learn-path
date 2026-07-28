"""
SSE 通知推送服务

What: 维护按用户隔离的内存订阅队列，供全局 SSE 端点与定时任务推送事件
Why: 每日自动排期、周报、干预等异步事件需要实时通知在线前端
How: 每个用户可有多个连接（多标签页），publish 时向该用户全部队列投递
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# 单连接队列容量；满则丢弃最旧事件，避免阻塞生产者
_QUEUE_MAXSIZE = 64


def build_sse_event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """构造符合 sse-events.md 契约的事件包装。"""

    return {
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
        "type": event_type,
        "payload": payload,
    }


def format_sse_message(event: dict[str, Any]) -> str:
    """将事件字典序列化为 SSE 文本帧。"""

    import json

    event_type = event.get("type", "message")
    data = json.dumps(event, ensure_ascii=False, default=str)
    return f"event: {event_type}\ndata: {data}\n\n"


class NotificationService:
    """
    进程内 SSE 通知总线

    What: 按 user_id 管理 asyncio.Queue 订阅集合
    Why: 单机部署下无需 Redis；定时任务与 API 均可调用 publish
    """

    def __init__(self) -> None:
        self._subscribers: dict[int, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, user_id: int) -> asyncio.Queue[dict[str, Any]]:
        """为用户注册一条 SSE 订阅队列。"""

        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        async with self._lock:
            self._subscribers.setdefault(user_id, set()).add(queue)
        logger.debug("[Notification] user=%s subscribed, active=%s", user_id, len(self._subscribers.get(user_id, ())))
        return queue

    async def unsubscribe(self, user_id: int, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """移除用户的一条订阅队列。"""

        async with self._lock:
            queues = self._subscribers.get(user_id)
            if not queues:
                return
            queues.discard(queue)
            if not queues:
                self._subscribers.pop(user_id, None)
        logger.debug("[Notification] user=%s unsubscribed", user_id)

    def subscriber_count(self, user_id: int | None = None) -> int:
        """返回订阅连接数（调试/测试用）。"""

        if user_id is None:
            return sum(len(q) for q in self._subscribers.values())
        return len(self._subscribers.get(user_id, ()))

    async def publish(self, user_id: int, event_type: str, payload: dict[str, Any]) -> int:
        """
        向指定用户的所有在线连接推送事件

        Returns:
            成功投递的连接数
        """

        event = build_sse_event(event_type, payload)
        async with self._lock:
            queues = list(self._subscribers.get(user_id, set()))

        delivered = 0
        for queue in queues:
            try:
                queue.put_nowait(event)
                delivered += 1
            except asyncio.QueueFull:
                # 丢弃最旧事件后重试，保证最新通知可达
                try:
                    _ = queue.get_nowait()
                    queue.put_nowait(event)
                    delivered += 1
                except Exception:
                    logger.warning(
                        "[Notification] user=%s queue full, drop event type=%s",
                        user_id,
                        event_type,
                    )
        if delivered:
            logger.info(
                "[Notification] published type=%s user=%s delivered=%s",
                event_type,
                user_id,
                delivered,
            )
        else:
            logger.debug(
                "[Notification] no subscribers for user=%s type=%s",
                user_id,
                event_type,
            )
        return delivered

    async def publish_schedule_updated(
        self,
        user_id: int,
        *,
        date_str: str,
        tasks: list[dict[str, Any]],
        total_minutes: int,
        overflow_detected: bool = False,
        message: str | None = None,
    ) -> int:
        """推送 schedule_updated 事件（自动排期 / 手动生成后）。"""

        total_tasks = len(tasks)
        payload = {
            "date": date_str,
            "total_tasks": total_tasks,
            "total_minutes": total_minutes,
            "tasks": tasks,
            "overflow_detected": overflow_detected,
            "message": message
            or f"今日计划已生成，共{total_tasks}项任务，总用时{total_minutes}分钟。",
        }
        return await self.publish(user_id, "schedule_updated", payload)

    async def publish_weekly_report(self, user_id: int, payload: dict[str, Any]) -> int:
        """推送 weekly_report 事件。"""

        return await self.publish(user_id, "weekly_report", payload)

    async def publish_intervention(self, user_id: int, payload: dict[str, Any]) -> int:
        """推送 intervention 事件。"""

        return await self.publish(user_id, "intervention", payload)


# 模块级单例，供 API 与定时任务共享
notification_service = NotificationService()
