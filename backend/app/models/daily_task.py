"""
DailyTask ORM 模型

What: 每日学习任务实体，Schedule Agent 根据活跃计划 + 画像时段偏好生成
Why: 用户每日视图展示今日任务清单，Feedback Agent 在完成任务后触发追问
How: 双向关联 User / Plan / KnowledgeNode，scheduled_date 用于日期筛选
"""

from datetime import date, datetime, time
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.knowledge_node import KnowledgeNode
    from app.models.plan import Plan
    from app.models.user import User


class DailyTask(Base, TimestampMixin):
    """
    每日任务表

    What: 用户每天需要完成的单个学习任务
    Why: Schedule Agent 每日生成，为用户提供可操作的当日学习清单

    状态: pending / completed / skipped
    """

    __tablename__ = "daily_tasks"

    # ── 主键 ────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="任务唯一标识"
    )

    # ── 外键 ────────────────────────────────────────────────
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属用户 ID",
    )
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属计划 ID",
    )
    knowledge_node_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("knowledge_nodes.id", ondelete="SET NULL"),
        default=None,
        index=True,
        comment="关联知识节点 ID (可为空)",
    )

    # ── 基本信息 ────────────────────────────────────────────
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="任务标题"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, default=None, comment="任务描述"
    )

    # ── 排期信息 ────────────────────────────────────────────
    scheduled_date: Mapped[date] = mapped_column(
        Date, nullable=False, index=True, comment="计划执行日期"
    )
    duration_minutes: Mapped[int] = mapped_column(
        Integer, default=30, comment="预计耗时（分钟）"
    )
    start_time: Mapped[Optional[time]] = mapped_column(
        Time, default=None, comment="任务开始时间"
    )
    end_time: Mapped[Optional[time]] = mapped_column(
        Time, default=None, comment="任务结束时间"
    )
    guide_content: Mapped[Optional[str]] = mapped_column(
        Text, default=None, comment="任务学习指引"
    )

    # ── 状态管理 ────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
        comment="任务状态: pending / completed / skipped",
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=None, comment="实际完成时间"
    )
    # ── 反馈闭环字段 ──
    feedback_signal: Mapped[Optional[str]] = mapped_column(
        String(20), default=None, comment="用户反馈信号: too_easy/normal/stuck/need_practice"
    )
    feedback_confidence_delta: Mapped[Optional[float]] = mapped_column(
        Float, default=None, comment="用户反馈导致的掌握度变化"
    )

    # ── 关联关系 ────────────────────────────────────────────
    user: Mapped["User"] = relationship(
        "User", back_populates="daily_tasks"
    )
    plan: Mapped["Plan"] = relationship(
        "Plan", back_populates="daily_tasks"
    )
    knowledge_node: Mapped[Optional["KnowledgeNode"]] = relationship(
        "KnowledgeNode"
    )

    def __repr__(self) -> str:
        return (
            f"<DailyTask(id={self.id}, title='{self.title}', "
            f"status='{self.status}', date={self.scheduled_date})>"
        )
