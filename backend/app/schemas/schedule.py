"""
排期相关 Pydantic Schema

What: 定义 Schedule Agent 的 LLM 结构化输出模型
Why: 让 LLM 以结构化方式输出今日排期方案，包含推理过程和任务列表
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScheduleTaskItem(BaseModel):
    """LLM 输出的单个排期任务项"""

    plan_id: int = Field(..., description="所属计划 ID")
    knowledge_node_id: int = Field(..., description="知识节点 ID")
    title: str = Field(..., min_length=1, description='任务标题，如 Day 5: 运算符')
    duration_minutes: int = Field(..., ge=10, le=480, description='建议学习时长（分钟）')
    priority_note: str | None = Field(default=None, description='排期优先级备注')


class ReplanDecision(BaseModel):
    """基于反馈的排期调整决策"""

    action: str = Field(..., description='调整动作')
    node_name: str = Field(..., description='涉及的节点名称')
    reason: str = Field(..., description='调整原因')


class LLMScheduleOutput(BaseModel):
    """LLM 排期方案的完整结构化输出"""

    reasoning: str = Field(..., min_length=1, description='排期推理过程')
    replan_decisions: list[ReplanDecision] = Field(
        default_factory=list,
        description='基于反馈的调整决策列表',
    )
    tasks: list[ScheduleTaskItem] = Field(
        ..., min_length=1,
        description='今日任务列表',
    )
