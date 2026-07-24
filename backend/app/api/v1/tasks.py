"""每日任务 API 路由。"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.schedule_agent import run_schedule_graph
from app.api.deps import get_current_user
from app.core.task_service import get_tasks_by_date, serialize_daily_task, update_task_status
from app.db.session import get_db
from app.models.user import User
from app.schemas.task import (
    DailyTaskResponse,
    GenerateTasksRequest,
    GenerateTasksResponse,
    TaskStatusUpdateRequest,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("/generate", response_model=GenerateTasksResponse)
async def generate_tasks(
    body: GenerateTasksRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GenerateTasksResponse:
    """手动触发指定日期的学习任务排期。"""

    scheduled_date = body.scheduled_date or date.today()
    await run_schedule_graph(
        user_id=str(current_user.id),
        daily_budget=body.daily_budget,
        scheduled_date=scheduled_date,
    )
    tasks = await get_tasks_by_date(db, current_user.id, scheduled_date)
    return GenerateTasksResponse(
        scheduled_date=scheduled_date,
        tasks=[DailyTaskResponse(**serialize_daily_task(task)) for task in tasks],
    )


@router.get("/today", response_model=list[DailyTaskResponse])
async def get_today_tasks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DailyTaskResponse]:
    """获取当前用户今天的学习任务。"""

    tasks = await get_tasks_by_date(db, current_user.id, date.today())
    return [DailyTaskResponse(**serialize_daily_task(task)) for task in tasks]


@router.put("/{task_id}/status", response_model=DailyTaskResponse)
async def set_task_status(
    task_id: int,
    body: TaskStatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DailyTaskResponse:
    """修改当前用户每日任务的状态。"""

    task = await update_task_status(db, current_user.id, task_id, body.status)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return DailyTaskResponse(**serialize_daily_task(task))
