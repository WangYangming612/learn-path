"""学习日记与每周学习简报 API 路由。"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.journal_service import create_journal, get_journals, serialize_journal
from app.core.weekly_report import generate_weekly_report
from app.db.session import get_db
from app.models.user import User
from app.schemas.journal import (
    JournalCreateRequest,
    JournalResponse,
    WeeklyReportResponse,
)

router = APIRouter(prefix="/journals", tags=["journals"])


@router.post("", response_model=JournalResponse, status_code=status.HTTP_201_CREATED)
async def create_study_journal(
    body: JournalCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JournalResponse:
    """为当前用户创建学习日记。"""

    journal = await create_journal(db, current_user.id, body)
    if journal is None:
        raise HTTPException(status_code=404, detail="已完成的关联任务不存在")
    return JournalResponse(**serialize_journal(journal))


@router.get("", response_model=list[JournalResponse])
async def list_study_journals(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[JournalResponse]:
    """归档查询当前用户的学习日记。"""

    journals = await get_journals(db, current_user.id, limit=limit, offset=offset)
    return [JournalResponse(**serialize_journal(journal)) for journal in journals]


@router.get("/weekly-report", response_model=WeeklyReportResponse)
async def get_weekly_report(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WeeklyReportResponse:
    """生成当前用户最近一周的学习简报。"""

    report = await generate_weekly_report(db, current_user.id)
    return WeeklyReportResponse(**report)
