"""
用户相关 Schema

What: 用户注册/登录/响应的 Pydantic 数据模型
Why: FastAPI 依赖 Pydantic 做请求体验证和响应序列化，
     排除 hashed_password 避免敏感信息泄漏
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """
    用户注册请求

    What: 前端 POST /auth/register 的请求体
    Why: 校验必填字段和格式，password min_length 防弱密码
    """

    username: str = Field(
        min_length=3, max_length=50, description="用户名，3-50 字符"
    )
    email: EmailStr = Field(description="邮箱地址")
    password: str = Field(
        min_length=6, max_length=128, description="密码，6-128 字符"
    )


class UserLogin(BaseModel):
    """
    用户登录请求

    What: 前端 POST /auth/login 的请求体
    Why: 仅需 username + password，登录成功后返回 TokenResponse
    """

    username: str = Field(min_length=1, description="用户名")
    password: str = Field(min_length=1, description="密码")


class UserResponse(BaseModel):
    """
    用户信息响应

    What: 返回给前端的用户公开信息
    Why: 排除 hashed_password，仅返回非敏感字段

    from_attributes=True 允许直接从 SQLAlchemy User 对象构建
    """

    id: int
    username: str
    email: str
    daily_available_minutes: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
