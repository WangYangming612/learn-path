"""每日任务相关 Pydantic Schema。"""

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DailyTaskResponse(BaseModel):
    """每日任务响应。"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    plan_id: int
    knowledge_node_id: int | None
    plan_title: str | None = None
    title: str
    description: str | None = None
    scheduled_date: date
    start_time: time | None = None
    end_time: time | None = None
    duration_minutes: int
    guide_content: str | None = None
    status: str
    completed_at: datetime | None = None


class GenerateTasksRequest(BaseModel):
    scheduled_date: date | None = Field(default=None)
    daily_budget: int | None = Field(default=None, ge=1, le=1440)


class GenerateTasksResponse(BaseModel):
    scheduled_date: date
    tasks: list[DailyTaskResponse]
    llm_used: bool | None = Field(default=None)
    llm_reasoning: str | None = Field(default=None)


class TaskStatusUpdateRequest(BaseModel):
    status: Literal["pending", "completed", "skipped"]
