"""
Schema 统一导出

What: 集中导出所有 Pydantic Schema，供 API 路由模块引用
Why: 单一导入入口，避免在多个路由文件中重复写长 import 路径
"""

from app.schemas.common import TokenResponse
from app.schemas.user import UserCreate, UserLogin, UserResponse

__all__ = [
    "TokenResponse",
    "UserCreate",
    "UserLogin",
    "UserResponse",
]
