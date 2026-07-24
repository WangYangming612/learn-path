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
    """手动触发指定日期排期的请求。"""

    scheduled_date: date | None = Field(default=None, description="排期日期，默认今天")
    daily_budget: int | None = Field(
        default=None, ge=1, le=1440, description="当天可用分钟数，未传时读取用户画像"
    )


class GenerateTasksResponse(BaseModel):
    """排期生成响应。"""

    scheduled_date: date
    tasks: list[DailyTaskResponse]


class TaskStatusUpdateRequest(BaseModel):
    """更新每日任务状态的请求。"""

    status: Literal["pending", "completed", "skipped"]
