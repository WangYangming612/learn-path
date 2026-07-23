"""
UserProfile ORM 模型

What: 用户画像实体，持久化 Profile Agent 生成的多维度学习画像
Why: 画像数据需要跨会话持久化，Plan/Schedule/Feedback Agent 均依赖画像做个性化
How: user_id 唯一外键实现 1:1，profile_data 用 JSON 存储灵活维度结构
"""

from typing import TYPE_CHECKING, Optional

from sqlalchemy import Float, ForeignKey, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class UserProfile(Base, TimestampMixin):
    """
    用户画像表

    What: 存储 Profile Agent 生成的 6 维度学习画像及置信度
    Why: 画像驱动 Plan Agent 路径调优、Feedback Agent 追问生成、排期偏好

    profile_data 结构示例:
        {
            "learning_style":    {"label": "视觉型",    "confidence": 0.85},
            "best_time":         {"label": "夜晚",      "confidence": 0.70},
            "learning_pace":     {"label": "稳健型",    "confidence": 0.60},
            "feedback_baseline": {"label": "高敏感",    "confidence": 0.75},
            "persistence":       {"label": "中等持续",  "confidence": 0.50},
            "knowledge_retention":{"label": "遗忘较快", "confidence": 0.55}
        }
    """

    __tablename__ = "user_profiles"

    # ── 主键 ────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="画像记录唯一标识"
    )

    # ── 外键 ────────────────────────────────────────────────
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,   # 1:1 关系
        nullable=False,
        index=True,
        comment="关联用户 ID",
    )

    # ── 画像数据 ────────────────────────────────────────────
    profile_data: Mapped[Optional[dict]] = mapped_column(
        JSON, default=dict, comment="画像维度数据，JSON 格式"
    )
    completeness: Mapped[float] = mapped_column(
        Float, default=0.0, comment="画像完成度 (0.0 ~ 1.0)"
    )

    # ── 关联关系 ────────────────────────────────────────────
    user: Mapped["User"] = relationship(
        "User", back_populates="profile"
    )

    def __repr__(self) -> str:
        return f"<UserProfile(id={self.id}, user_id={self.user_id}, comp={self.completeness})>"
