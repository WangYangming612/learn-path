"""
数据库会话管理

What: 创建 SQLAlchemy 异步引擎和 session 工厂，提供 FastAPI 依赖注入函数
Why: 统一管理数据库连接生命周期，路由函数通过 Depends(get_db) 获取 AsyncSession
How: 模块级 engine 单例 + async_sessionmaker + async generator 依赖注入
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# ── 异步引擎 ────────────────────────────────────────────────
# What: SQLAlchemy AsyncEngine，管理数据库连接池
# Why: 整个应用共享一个引擎实例，避免重复创建连接池
#      模块级延迟创建，确保 settings 已就绪
_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    """
    获取全局异步引擎（惰性初始化）

    What: 返回模块级单例 AsyncEngine，首次调用时创建
    Why: 暴露给 init_db.py 执行 create_all()；惰性创建避免导入即连接
    """
    global _engine
    if _engine is None:
        _connect_args = {}
        if "sqlite" in settings.DATABASE_URL:
            # SQLite 不允许跨线程使用同一连接，异步需禁掉线程检查
            _connect_args["check_same_thread"] = False

        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,         # 开发环境打印 SQL，生产关闭
            connect_args=_connect_args,
        )
    return _engine


# ── Session 工厂 ────────────────────────────────────────────
# What: async_sessionmaker 绑定到上面引擎，用于快速创建 AsyncSession
# Why: sessionmaker 可预设参数，后续只需 async_session_factory() 即可
def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """内部辅助：惰性获取 session 工厂"""
    return async_sessionmaker(
        get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,  # commit 后对象属性仍可访问，避免额外查询
    )


# What: 模块级 session 工厂引用，首次使用时初始化
# Why: 避免每次调用 get_db 都重新创建 sessionmaker
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """获取全局 session 工厂（惰性初始化）"""
    global _session_factory
    if _session_factory is None:
        _session_factory = _get_session_factory()
    return _session_factory


# ── FastAPI 依赖注入 ───────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 数据库会话依赖

    What: 为每个 HTTP 请求创建一个独立的 AsyncSession，请求结束时自动关闭
    Why: FastAPI 的 Depends(get_db) 机制让路由函数无需关心会话生命周期
    How: async generator，yield 前开启会话，finally 中关闭

    Usage:
        @router.get("/users")
        async def list_users(db: AsyncSession = Depends(get_db)):
            return await db.execute(select(User))
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
