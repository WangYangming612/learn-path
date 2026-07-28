"""每日任务 API 路由。"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.schedule_agent import run_schedule_graph
from app.api.deps import get_current_user
from app.core.notification_service import notification_service
from app.core.task_service import (
    get_tasks_by_date,
    serialize_daily_task,
    serialize_task_item_for_sse,
    update_task_status,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.task import (
    DailyTaskResponse,
    GenerateTasksRequest,
    GenerateTasksResponse,
    TaskStatusUpdateRequest,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])



@router.get('/diagnose-llm')
async def diagnose_llm():
    import httpx, datetime, logging
    from app.core.config import settings
    logger = logging.getLogger(__name__)
    start = datetime.datetime.now()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                settings.LLM_BASE_URL + '/chat/completions',
                json={
                    'model': 'deepseek-chat',
                    'messages': [
                        {'role': 'system', 'content': '用中文回复，只说一句话：连接测试成功'},
                        {'role': 'user', 'content': '测试连接'},
                    ],
                    'max_tokens': 50,
                },
                headers={'Authorization': 'Bearer ' + settings.LLM_API_KEY, 'Content-Type': 'application/json'},
            )
        elapsed = (datetime.datetime.now() - start).total_seconds()
        if resp.status_code == 200:
            content = resp.json()['choices'][0]['message']['content']
            return {'status': 'ok', 'response': str(content)[:200], 'elapsed': round(elapsed, 2)}
        else:
            body = resp.text[:300]
            return {'status': 'error', 'error': f'HTTP {resp.status_code}: {body}', 'elapsed': round(elapsed, 2)}
    except Exception as e:
        elapsed = (datetime.datetime.now() - start).total_seconds()
        logger.warning('[Diagnose] LLM连接失败: %s', e)
        return {'status': 'error', 'error': str(e), 'error_type': type(e).__name__, 'elapsed': round(elapsed, 2)}

@router.post("/generate", response_model=GenerateTasksResponse)
async def generate_tasks(
    body: GenerateTasksRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GenerateTasksResponse:
    """手动触发指定日期的学习任务排期。"""
    import logging
    logger = logging.getLogger(__name__)
    scheduled_date = body.scheduled_date or date.today()
    result = await run_schedule_graph(
        user_id=str(current_user.id),
        daily_budget=body.daily_budget,
        scheduled_date=scheduled_date,
    )

    tasks = await get_tasks_by_date(db, current_user.id, scheduled_date)
    total_minutes = sum(task.duration_minutes for task in tasks)
    schedule_result = result.get('schedule_result') or {}
    await notification_service.publish_schedule_updated(
        current_user.id,
        date_str=str(scheduled_date),
        tasks=[serialize_task_item_for_sse(task) for task in tasks],
        total_minutes=total_minutes,
        overflow_detected=bool(schedule_result.get("overflow_detected", False)),
    )
    llm_reasoning = result.get('llm_reasoning', '') or ''
    llm_error = result.get('llm_error', '') or ''
    is_fallback = 'fallback' in llm_reasoning.lower() or '\u515c\u5e95' in llm_reasoning
    llm_display = llm_reasoning[:200] if llm_reasoning else (llm_error[:200] if llm_error else None)

    logger.info(
        '[TasksAPI] 排期完成: user=%s, tasks=%d, fallback=%s',
        current_user.id, len(tasks), is_fallback,
    )

    return GenerateTasksResponse(
        scheduled_date=scheduled_date,
        tasks=[DailyTaskResponse(**serialize_daily_task(task)) for task in tasks],
        llm_used=not is_fallback,
        llm_reasoning=llm_display,
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



