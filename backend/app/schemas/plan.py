"""
计划相关 Pydantic Schema

What: 定义 Plan Agent / Plan API 的请求、响应与结构化输出模型
Why: 统一 LLM 结构化输出、服务层校验和 API 响应格式
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class LearningGoalRequest(BaseModel):
    """创建学习计划请求体"""

    goal: str = Field(..., min_length=1, description="自然语言学习目标")


class ParsedLearningGoal(BaseModel):
    """LLM 解析后的学习目标"""

    domain: str = Field(..., description="目标领域")
    duration_months: int = Field(..., ge=1, description="学习周期（月）")
    current_level: str = Field(..., description="当前基础")
    target_depth: str = Field(..., description="目标深度")


class KnowledgeNodeDraft(BaseModel):
    """LLM 生成的知识节点草稿"""

    id: str = Field(..., description="节点临时 ID")
    title: str = Field(..., min_length=1, description="节点标题")
    description: str = Field(default="", description="节点描述")
    estimated_minutes: int = Field(..., ge=1, description="预计学习时长（分钟）")
    prerequisite_ids: list[str] = Field(default_factory=list, description="前置节点临时 ID 列表")
    order_index: int | None = Field(default=None, description="可选顺序，仅供输出展示，不作为最终排序依据")


class PlanDraft(BaseModel):
    """Plan Agent 的结构化输出"""

    goal_text: str = Field(..., description="原始学习目标")
    parsed_goal: ParsedLearningGoal = Field(..., description="解析后的目标")
    nodes: list[KnowledgeNodeDraft] = Field(default_factory=list, description="知识节点列表")


class PlanNodeResponse(BaseModel):
    """返回给前端的知识节点"""

    id: int
    title: str
    description: str | None = None
    estimated_minutes: int
    prerequisite_ids: list[int] = Field(default_factory=list)
    order_index: int

    model_config = ConfigDict(from_attributes=True)


class PlanResponse(BaseModel):
    """创建计划响应"""

    id: int
    title: str
    description: str | None = None
    status: str
    start_date: date | None = None
    end_date: date | None = None
    created_at: datetime
    updated_at: datetime | None = None
    nodes: list[PlanNodeResponse] = Field(default_factory=list)
    parsed_goal: ParsedLearningGoal

    model_config = ConfigDict(from_attributes=True)


class PlanRebuildRequest(BaseModel):
    """预留的计划重算请求"""

    node_id: int | None = Field(default=None, description="需要优先处理或跳过的节点 ID")
    action: str = Field(..., description="skip_node / prioritize_node / rebuild_topology")
