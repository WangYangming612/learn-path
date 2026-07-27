"""每周学习简报生成服务。"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import llm_client
from app.models.daily_task import DailyTask
from app.models.study_journal import StudyJournal

logger = logging.getLogger(__name__)


def _week_range(today: date | None = None) -> tuple[date, date]:
    """返回截至当天的最近七天日期范围。"""

    week_end = today or date.today()
    return week_end - timedelta(days=6), week_end


def _fallback_summary(data: dict[str, Any]) -> str:
    """LLM 不可用时依据统计数据生成可用简报。"""

    completed = data["completed_task_count"]
    planned = data["planned_task_count"]
    minutes = data["completed_minutes"]
    journals = data["journal_count"]
    completion = f"完成 {completed}/{planned} 项计划任务" if planned else f"完成 {completed} 项学习任务"
    journal_text = f"，记录了 {journals} 篇学习日记" if journals else "，暂未记录学习日记"
    return f"本周你{completion}，累计投入 {minutes} 分钟{journal_text}。下周建议延续当前节奏，并在完成任务后用一句话记录关键收获。"


async def collect_weekly_learning_data(
    db: AsyncSession,
    user_id: int,
    today: date | None = None,
) -> dict[str, Any]:
    """汇总最近七天任务完成情况与学习日记。"""

    week_start, week_end = _week_range(today)
    start_at = datetime.combine(week_start, time.min)
    end_at = datetime.combine(week_end + timedelta(days=1), time.min)

    task_result = await db.execute(
        select(
            func.count(DailyTask.id),
            func.coalesce(
                func.sum(
                    DailyTask.duration_minutes,
                ).filter(DailyTask.status == "completed"),
                0,
            ),
            func.count(DailyTask.id).filter(DailyTask.status == "completed"),
        ).where(
            DailyTask.user_id == user_id,
            DailyTask.scheduled_date >= week_start,
            DailyTask.scheduled_date <= week_end,
        )
    )
    planned_count, completed_minutes, completed_count = task_result.one()

    journal_result = await db.execute(
        select(StudyJournal)
        .where(
            StudyJournal.user_id == user_id,
            StudyJournal.created_at >= start_at,
            StudyJournal.created_at < end_at,
        )
        .order_by(StudyJournal.created_at.asc())
    )
    journals = list(journal_result.scalars().all())

    return {
        "week_start": week_start,
        "week_end": week_end,
        "planned_task_count": int(planned_count or 0),
        "completed_task_count": int(completed_count or 0),
        "completed_minutes": int(completed_minutes or 0),
        "journal_count": len(journals),
        "journal_notes": [
            {
                "title": journal.title,
                "content": journal.content or "",
                "mood": journal.mood or "未记录",
            }
            for journal in journals
        ],
    }


async def generate_weekly_report(
    db: AsyncSession,
    user_id: int,
    today: date | None = None,
) -> dict[str, Any]:
    """生成最近一周的自然语言学习简报，LLM 失败时使用本地兜底。"""

    data = await collect_weekly_learning_data(db, user_id, today)
    summary = ""
    try:
        chat_model = llm_client.get_chat_model(temperature=0.4, timeout=30)
        response = await chat_model.ainvoke([
            {
                "role": "system",
                "content": "你是学习陪伴助手。请基于最近一周的学习数据，用简洁、鼓励的中文写一段学习简报；只陈述给定事实，不虚构数据，并给出一条下周建议。",
            },
            {
                "role": "user",
                "content": (
                    f"统计周期：{data['week_start']} 至 {data['week_end']}\n"
                    f"计划任务：{data['planned_task_count']}\n"
                    f"完成任务：{data['completed_task_count']}\n"
                    f"完成学习时长：{data['completed_minutes']} 分钟\n"
                    f"学习日记数量：{data['journal_count']}\n"
                    f"日记摘录：{data['journal_notes']}"
                ),
            },
        ])
        summary = str(response.content).strip()
    except Exception as exc:
        logger.warning("[WeeklyReport] LLM 简报生成失败，使用本地兜底: %s", exc)

    data["summary"] = summary or _fallback_summary(data)
    data.pop("journal_notes", None)
    return data
