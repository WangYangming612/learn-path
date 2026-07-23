"""
User ORM 模型

What: 用户实体，承载认证信息、学习偏好和所有关联数据的入口
Why: 系统所有功能（认证/画像/计划/任务/反馈）都以 User 为外键锚点
How: 继承 Base + TimestampMixin，使用 SQLAlchemy 2.0 的 Mapped 类型注解
"""

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

# TYPE_CHECKING 守卫：类型检查时导入，运行时跳过
# relationship() 中的字符串引用由 SQLAlchemy 延迟解析，
# 当 models/__init__.py 导入全部模型后即可正常配置
if TYPE_CHECKING:
    from app.models.daily_task import DailyTask
    from app.models.feedback_session import FeedbackSession
    from app.models.plan import Plan
    from app.models.study_journal import StudyJournal
    from app.models.user_profile import UserProfile


class User(Base, TimestampMixin):
    """
    用户表

    What: 存储用户认证凭据和学习偏好配置
    Why: 认证鉴权 + 排期时间预算 + 所有下游数据的关联根
    """

    __tablename__ = "users"

    # ── 主键 ────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="用户唯一标识"
    )

    # ── 认证字段 ────────────────────────────────────────────
    username: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True, comment="用户名"
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True, comment="邮箱"
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="bcrypt 哈希密码"
    )

    # ── 学习偏好 ────────────────────────────────────────────
    daily_available_minutes: Mapped[int] = mapped_column(
        Integer, default=60, comment="每日可用学习分钟数"
    )

    # ── 状态 ────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="账户是否激活"
    )

    # ── 关联关系 ────────────────────────────────────────────
    # What: 定义 User 到其他实体的 ORM 关系
    # Why: 后续查询可通过 user.plans / user.profile 等直接获取关联数据
    # Note: 字符串引用由 SQLAlchemy 延迟解析，所有模型就绪后通过
    #       models/__init__.py 统一导入即可触发完整 mapper 配置

    profile: Mapped[Optional["UserProfile"]] = relationship(
        "UserProfile", back_populates="user", uselist=False
    )
    plans: Mapped[List["Plan"]] = relationship(
        "Plan", back_populates="user"
    )
    daily_tasks: Mapped[List["DailyTask"]] = relationship(
        "DailyTask", back_populates="user"
    )
    feedback_sessions: Mapped[List["FeedbackSession"]] = relationship(
        "FeedbackSession", back_populates="user"
    )
    study_journals: Mapped[List["StudyJournal"]] = relationship(
        "StudyJournal", back_populates="user"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}')>"
