"""
StudyJournal ORM 模型

What: 学习日记实体，记录用户的学习心得、情绪和反思
Why: 用户完成任务后可记笔记，周报 Agent 汇总分析情绪趋势
How: content 用 Text 存长文，mood 用短标签记录学习状态
"""

from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.daily_task import DailyTask
    from app.models.user import User


class StudyJournal(Base, TimestampMixin):
    """
    学习日记表

    What: 用户每次学习后的笔记记录
    Why: 促进反思习惯，为每周学习简报提供素材

    mood 示例: focused / distracted / confident / confused / motivated / tired
    """

    __tablename__ = "study_journals"

    # ── 主键 ────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="日记唯一标识"
    )

    # ── 外键 ────────────────────────────────────────────────
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属用户 ID",
    )
    task_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("daily_tasks.id", ondelete="SET NULL"),
        default=None,
        index=True,
        comment="关联任务 ID (可为空，支持自由日记)",
    )

    # ── 日记内容 ────────────────────────────────────────────
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="日记标题"
    )
    content: Mapped[Optional[str]] = mapped_column(
        Text, default=None, comment="日记正文"
    )
    mood: Mapped[Optional[str]] = mapped_column(
        String(30),
        default=None,
        comment="学习情绪: focused / distracted / confident / confused / motivated / tired",
    )
    study_duration: Mapped[Optional[int]] = mapped_column(
        Integer,
        default=None,
        comment="实际学习时长（分钟）",
    )

    # ── 关联关系 ────────────────────────────────────────────
    user: Mapped["User"] = relationship(
        "User", back_populates="study_journals"
    )
    task: Mapped[Optional["DailyTask"]] = relationship(
        "DailyTask"
    )

    def __repr__(self) -> str:
        return (
            f"<StudyJournal(id={self.id}, title='{self.title}', "
            f"mood='{self.mood}')>"
        )
