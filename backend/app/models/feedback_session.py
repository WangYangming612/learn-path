"""
FeedbackSession ORM 模型

What: 反馈会话实体，记录用户与 Feedback Agent 的一轮完整对话
Why: 存储追问内容、用户回答、信号解析结果和画像增量，供 Profile Agent 后续更新
How: content 用 JSON 存储结构化对话数据，rating 评估反馈质量
"""

from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class FeedbackSession(Base, TimestampMixin):
    """
    反馈会话表

    What: 一次完整的反馈对话记录
    Why: Feedback Agent 解析反馈信号后写入，Profile Agent 读取增量更新画像

    content JSON 结构:
        {
            "task_id": 1,
            "questions": ["今天的学习内容理解程度如何？"],
            "answers": ["大部分理解了，函数闭包还有点模糊"],
            "signals": [
                {"type": "mastery", "value": 0.6, "target": "闭包"},
                {"type": "difficulty_perception", "value": 0.7}
            ],
            "profile_updates": {
                "learning_style": {"label": "实践型", "confidence_delta": 0.05}
            }
        }
    """

    __tablename__ = "feedback_sessions"

    # ── 主键 ────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="会话唯一标识"
    )

    # ── 外键 ────────────────────────────────────────────────
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属用户 ID",
    )

    # ── 会话信息 ────────────────────────────────────────────
    session_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="会话类型: daily_feedback / weekly_review",
    )
    content: Mapped[Optional[dict]] = mapped_column(
        JSON, default=dict, comment="结构化反馈内容 (JSON)"
    )
    rating: Mapped[Optional[int]] = mapped_column(
        Integer,
        default=None,
        comment="用户对本次反馈的评分 (1-5)",
    )

    # ── 关联关系 ────────────────────────────────────────────
    user: Mapped["User"] = relationship(
        "User", back_populates="feedback_sessions"
    )

    def __repr__(self) -> str:
        return (
            f"<FeedbackSession(id={self.id}, type='{self.session_type}', "
            f"rating={self.rating})>"
        )
