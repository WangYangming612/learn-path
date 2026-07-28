"""
APScheduler 定时任务基础设施

What: 注册 AsyncIOScheduler，管理每日/每周定时触发的系统任务
Why: 中断检测、遗忘复习、自动排期、周报等需定时巡检，而非等待用户主动触发

架构说明：
    scheduler.py 只负责：创建 scheduler + 注册 cron job + 调用业务函数
    不涉及：DB 查询细节、遗忘曲线计算、模型修改（委托给各 Agent/Service）

时间表：
    00:00  中断检测（Intervention）
    00:05  每日自动排期（Schedule Agent）— 在中断检测之后，跳过已暂停计划
    01:00  遗忘曲线复习（Intervention）
    周一 08:00  每周学习简报 + SSE 推送
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@scheduler.scheduled_job("cron", hour=0, minute=0)
async def daily_interruption_check():
    """
    每日中断检测（00:00 执行）

    What: 每日零点巡检所有用户，检测是否有连续 3 天未学习的用户
    Why: 中断检测是生成恢复方案的前置条件，定时触发确保不漏检
    """
    logger.info("[Scheduler] 执行每日中断检测任务")
    try:
        from app.agents.intervention_agent import run_interruption_check

        await run_interruption_check()
    except ImportError as exc:
        logger.warning(f"[Scheduler] 导入 run_interruption_check 失败: {exc}")
    except Exception as exc:
        logger.exception(f"[Scheduler] 中断检测任务执行异常: {exc}")


@scheduler.scheduled_job("cron", hour=0, minute=5)
async def daily_auto_schedule():
    """
    每日自动排期（00:05 执行）

    What: 遍历所有拥有活跃计划的用户，调用 Schedule Agent 生成今日任务，并 SSE 推送
    Why: E1 日排期自动生成；放在中断检测之后，已暂停用户不会被排期
    """
    logger.info("[Scheduler] 执行每日自动排期任务")
    try:
        result = await run_daily_auto_schedule()
        logger.info(
            "[Scheduler] 自动排期完成: users=%s success=%s failed=%s",
            result.get("total_users"),
            result.get("success"),
            result.get("failed"),
        )
    except Exception as exc:
        logger.exception(f"[Scheduler] 自动排期任务执行异常: {exc}")


@scheduler.scheduled_job("cron", hour=1, minute=0)
async def daily_forgetting_review():
    """
    每日遗忘曲线复习（01:00 执行）

    What: 每日一点查询所有已完成知识节点，根据画像知识保留特征计算复习间隔，
          对需要复习的节点生成复习任务
    Why: 遗忘曲线排期是干预 Agent 的核心功能，定时触发确保复习不遗漏
    """
    logger.info("[Scheduler] 执行每日遗忘曲线复习任务")
    try:
        from app.agents.intervention_agent import run_forgetting_curve_review

        await run_forgetting_curve_review()
    except ImportError as exc:
        logger.warning(f"[Scheduler] 导入 run_forgetting_curve_review 失败: {exc}")
    except Exception as exc:
        logger.exception(f"[Scheduler] 遗忘曲线复习任务执行异常: {exc}")


@scheduler.scheduled_job("cron", day_of_week="mon", hour=8, minute=0)
async def weekly_report_job():
    """
    每周学习简报（周一 08:00 执行）

    What: 为有学习记录的用户生成周报，并通过 SSE 推送 weekly_report
    Why: L1/L2 每周简报自动生成与推送
    """
    logger.info("[Scheduler] 执行每周学习简报任务")
    try:
        result = await run_weekly_report_push()
        logger.info(
            "[Scheduler] 周报推送完成: users=%s success=%s",
            result.get("total_users"),
            result.get("success"),
        )
    except Exception as exc:
        logger.exception(f"[Scheduler] 周报任务执行异常: {exc}")


async def run_daily_auto_schedule(target_date: date | None = None) -> dict[str, Any]:
    """
    为所有拥有活跃计划的用户生成当日排期并推送 SSE

    What: 供 cron 与测试调用的自动排期入口
    Why: 与 scheduler job 解耦，便于单测直接调用

    Returns:
        {total_users, success, failed, details}
    """
    from app.agents.schedule_agent import run_schedule_graph
    from app.core.notification_service import notification_service
    from app.core.task_service import get_tasks_by_date, serialize_task_item_for_sse
    from app.db.session import get_db
    from app.models.plan import Plan

    scheduled_date = target_date or date.today()
    details: list[dict[str, Any]] = []
    success = 0
    failed = 0

    async for db in get_db():
        user_rows = await db.execute(
            select(Plan.user_id).where(Plan.status == "active").distinct()
        )
        user_ids = [row[0] for row in user_rows]
        break
    else:
        user_ids = []

    for user_id in user_ids:
        try:
            result = await run_schedule_graph(
                user_id=str(user_id),
                scheduled_date=scheduled_date,
            )
            schedule_result = result.get("schedule_result") or {}
            overflow_detected = bool(schedule_result.get("overflow_detected", False))

            async for db in get_db():
                tasks = await get_tasks_by_date(db, user_id, scheduled_date)
                task_items = [serialize_task_item_for_sse(task) for task in tasks]
                total_minutes = sum(task.duration_minutes for task in tasks)
                break
            else:
                task_items = []
                total_minutes = 0

            message = (
                f"今日计划已生成，共{len(task_items)}项任务，总用时{total_minutes}分钟。"
            )
            if overflow_detected:
                message += "部分任务已按优先级压缩以适应时间预算。"

            await notification_service.publish_schedule_updated(
                user_id,
                date_str=str(scheduled_date),
                tasks=task_items,
                total_minutes=total_minutes,
                overflow_detected=overflow_detected,
                message=message,
            )
            success += 1
            details.append({
                "user_id": user_id,
                "ok": True,
                "task_count": len(task_items),
                "total_minutes": total_minutes,
            })
        except Exception as exc:
            failed += 1
            logger.exception(
                "[Scheduler] 用户 %s 自动排期失败: %s", user_id, exc
            )
            details.append({"user_id": user_id, "ok": False, "error": str(exc)})

    return {
        "total_users": len(user_ids),
        "success": success,
        "failed": failed,
        "scheduled_date": str(scheduled_date),
        "details": details,
    }


async def run_weekly_report_push(today: date | None = None) -> dict[str, Any]:
    """
    为近期有任务的用户生成周报并 SSE 推送

    What: 供 cron 与测试调用的周报推送入口
    """
    from app.core.notification_service import notification_service
    from app.core.weekly_report import generate_weekly_report
    from app.db.session import get_db
    from app.models.daily_task import DailyTask

    report_day = today or date.today()
    success = 0

    async for db in get_db():
        user_rows = await db.execute(select(DailyTask.user_id).distinct())
        user_ids = [row[0] for row in user_rows]
        break
    else:
        user_ids = []

    for user_id in user_ids:
        try:
            async for db in get_db():
                report = await generate_weekly_report(db, user_id, report_day)
                break
            else:
                continue

            week_number = report_day.isocalendar().week
            payload = {
                "week_number": week_number,
                "report_date": str(report_day),
                "summary": {
                    "total_hours": round(report["completed_minutes"] / 60, 1),
                    "hours_change": 0,
                    "total_tasks_completed": report["completed_task_count"],
                    "streak_days": 0,
                },
                "plan_progress": [],
                "profile_updates": [],
                "weak_spots": [],
                "motivational_message": report["summary"],
            }
            await notification_service.publish_weekly_report(user_id, payload)
            success += 1
        except Exception as exc:
            logger.exception("[Scheduler] 用户 %s 周报推送失败: %s", user_id, exc)

    return {
        "total_users": len(user_ids),
        "success": success,
        "report_date": str(report_day),
    }
