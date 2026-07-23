"""
通用 Schema

What: API 层共用的 Pydantic 模型
Why: 多处复用的 Schema 集中管理，避免重复定义
"""

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    """
    JWT 令牌响应

    What: 登录成功后返回 access_token 和 token 类型
    Why: 前端存储 token，后续请求放入 Authorization header
    """

    access_token: str = Field(description="JWT 访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
