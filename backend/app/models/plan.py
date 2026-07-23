"""
Plan ORM 模型

What: 学习计划实体，承载用户的学习目标及其生命周期管理
Why: Plan Agent 创建计划并生成知识图谱，Schedule Agent 读取活跃计划排期
How: 继承 Base + TimestampMixin，外键关联 User
"""

from datetime import date
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.daily_task import DailyTask
    from app.models.knowledge_node import KnowledgeNode
    from app.models.user import User


class Plan(Base, TimestampMixin):
    """
    学习计划表

    What: 用户创建的学习计划，Plan Agent 据此生成知识图谱 DAG
    Why: 计划是路径生成的基本单位，排期/反馈/干预均以计划为上下文

    状态流转:
        draft → active → completed
                  ↓
               paused → active (恢复)
    """

    __tablename__ = "plans"

    # ── 主键 ────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="计划唯一标识"
    )

    # ── 外键 ────────────────────────────────────────────────
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属用户 ID",
    )

    # ── 基本信息 ────────────────────────────────────────────
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="学习计划标题"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, default=None, comment="计划描述，用户输入的自然语言学习目标"
    )

    # ── 状态管理 ────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(20),
        default="draft",
        nullable=False,
        comment="计划状态: draft / active / paused / completed",
    )

    # ── 时间节点 ────────────────────────────────────────────
    start_date: Mapped[Optional[date]] = mapped_column(
        Date, default=None, comment="计划开始日期"
    )
    end_date: Mapped[Optional[date]] = mapped_column(
        Date, default=None, comment="计划结束日期"
    )

    # ── 关联关系 ────────────────────────────────────────────
    user: Mapped["User"] = relationship(
        "User", back_populates="plans"
    )
    knowledge_nodes: Mapped[List["KnowledgeNode"]] = relationship(
        "KnowledgeNode", back_populates="plan"
    )
    daily_tasks: Mapped[List["DailyTask"]] = relationship(
        "DailyTask", back_populates="plan"
    )

    def __repr__(self) -> str:
        return f"<Plan(id={self.id}, title='{self.title}', status='{self.status}')>"
