"""学习日记与每周学习简报相关 Schema。"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class JournalCreateRequest(BaseModel):
    """创建学习日记请求。"""

    task_id: int | None = Field(default=None, description="关联的已完成任务 ID，可为空")
    title: str = Field(..., min_length=1, max_length=200, description="日记标题")
    content: str | None = Field(default=None, max_length=10000, description="学习笔记正文")
    mood: str | None = Field(default=None, max_length=30, description="本次学习情绪")
    study_duration: int | None = Field(
        default=None, ge=1, le=1440, description="实际学习时长（分钟）"
    )


class JournalResponse(BaseModel):
    """学习日记响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int | None
    title: str
    content: str | None
    mood: str | None
    study_duration: int | None
    created_at: datetime
    updated_at: datetime | None = None


class WeeklyReportResponse(BaseModel):
    """最近一周学习简报响应。"""

    week_start: date
    week_end: date
    completed_task_count: int
    planned_task_count: int
    completed_minutes: int
    journal_count: int
    summary: str
