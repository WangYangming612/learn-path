"""
APScheduler 定时任务基础设施

What: 注册 AsyncIOScheduler，管理每日定时触发的中断检测和遗忘曲线复习
Why: 系统需要定时巡检用户状态（中断检测）和生成复习任务（遗忘曲线），
     而非等待用户主动触发

架构说明：
    scheduler.py 只负责：创建 scheduler + 注册 cron job + 调用 agent 函数
    不涉及：DB 查询、遗忘曲线计算、模型修改
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

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
