"""
认证路由

What: 用户注册和登录的 REST API 端点
Why: 用户系统的入口，注册创建账户，登录获取 JWT
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import TokenResponse
from app.schemas.user import UserCreate, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


# ── 注册接口 ────────────────────────────────────────────────

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    用户注册

    What: 创建新用户账户
    Why: 前端注册页面提交表单，后端校验唯一性 + 密码哈希后写入数据库

    Raises:
        409: username 或 email 已被注册
    """
    # 1. 检查 username 唯一性
    result = await db.execute(select(User).where(User.username == body.username))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已被注册",
        )

    # 2. 检查 email 唯一性
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="邮箱已被注册",
        )

    # 3. 创建用户
    user = User(
        username=body.username,
        email=body.email,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return user


# ── 登录接口 ────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(OAuth2PasswordRequestForm),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    用户登录

    What: 验证用户名密码，签发 JWT 访问令牌
    Why: 同时支持 Swagger OAuth2 表单 (x-www-form-urlencoded) 和前端 JSON 请求

    Returns:
        TokenResponse: access_token + user 基本信息

    Raises:
        401: 用户名或密码错误
    """
    # 1. 查询用户
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()

    # 2. 验证密码
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    # 3. 签发 JWT
    token = create_access_token(data={"sub": str(user.id)})

    return TokenResponse(access_token=token)


# ── 当前用户接口 ────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    获取当前用户信息

    What: 返回当前已认证用户的公开信息
    Why: 前端刷新页面后通过此接口恢复用户状态（如展示头像、用户名）
         鉴权由 get_current_user 依赖自动完成
    """
    return current_user
