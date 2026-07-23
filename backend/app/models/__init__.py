"""
ORM 模型统一入口

What: 集中导入所有 ORM 模型，注册到 SQLAlchemy metadata
Why: 单一导入点确保所有模型类在映射器配置时存在，
     解决跨文件 relationship 字符串引用的延迟解析问题
How: 按依赖顺序导入，供 init_db.py 和 alembic 使用
"""

from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.plan import Plan
from app.models.knowledge_node import KnowledgeNode
from app.models.daily_task import DailyTask
from app.models.feedback_session import FeedbackSession
from app.models.study_journal import StudyJournal

__all__ = [
    "User",
    "UserProfile",
    "Plan",
    "KnowledgeNode",
    "DailyTask",
    "FeedbackSession",
    "StudyJournal",
]
