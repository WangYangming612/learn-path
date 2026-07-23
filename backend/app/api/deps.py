"""
API 依赖注入

What: FastAPI Depends 函数集合，提供请求级别的可注入依赖
Why: 鉴权逻辑集中于此，路由函数只需声明依赖即可获取当前用户，
     符合 DRY 原则且便于单元测试 mock
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

# ── OAuth2 方案 ────────────────────────────────────────────
# What: FastAPI OAuth2PasswordBearer，从请求头提取 Bearer Token
# Why: 标准 OAuth2 密码流，Swagger UI 自动生成 Authorize 按钮
# Note: tokenUrl 指向登录接口，Swagger 文档中的认证弹窗会请求此 URL
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
)


# ── 当前用户依赖 ────────────────────────────────────────────
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    获取当前已认证用户

    What: 从请求 Authorization Header 中提取 JWT，解码后查询对应 User
    Why: 路由函数通过 Depends(get_current_user) 即可获得当前用户对象，
         无需手动解析 Token

    Args:
        token: OAuth2PasswordBearer 自动提取的 Bearer Token
        db: 异步数据库会话

    Returns:
        已认证的 User ORM 对象

    Raises:
        401: Token 无效、过期或 payload 缺少 sub 字段
        401: 用户不存在（Token 有效但用户已删除）
        403: 用户账户已被禁用
    """
    # 1. 验证 JWT 签名和有效期
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. 提取 user_id
    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 载荷无效：缺少 sub 字段",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. 查询用户
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 4. 检查账户状态
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用",
        )

    return user
