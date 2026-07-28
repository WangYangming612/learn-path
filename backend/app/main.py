"""
LearnPath API 主应用入口

What: FastAPI 应用实例，作为整个后端服务的 HTTP 入口点
Why: 统一管理路由注册、中间件配置和应用生命周期
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.auth import router as auth_router
from app.api.v1.events import router as events_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.journals import router as journals_router
from app.api.v1.plans import router as plans_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.profile import router as profile_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 应用生命周期管理

    What: 在应用启动时启动 APScheduler，关闭时停止
    Why: scheduler 需要在 FastAPI 事件循环内运行，使用 lifespan 管理其生命周期
    """
    from app.core.scheduler import scheduler

    scheduler.start()
    yield
    scheduler.shutdown()


# 创建 FastAPI 应用实例
app = FastAPI(
    title="LearnPath API",
    description="个性化学习路径动态生成系统后端 API",
    version="0.1.0",
    lifespan=lifespan,
)

# 配置 CORS 中间件
# What: 跨域资源共享，允许前端浏览器跨域访问后端 API
# Why: 前后端分离架构下，前端 localhost:5173 访问后端 localhost:8000 属于跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # 开发阶段前端地址
    ],
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有 HTTP 方法
    allow_headers=["*"],  # 允许所有请求头
)

# 注册认证路由
# What: 将 auth 模块的路由注册到 FastAPI 应用
# Why: 不注册则路由不可用，include_router 统一管理所有子路由
app.include_router(auth_router, prefix="/api/v1")
app.include_router(events_router, prefix="/api/v1")
app.include_router(feedback_router, prefix="/api/v1")
app.include_router(journals_router, prefix="/api/v1")
app.include_router(plans_router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")
app.include_router(profile_router, prefix="/api/v1")



@app.get("/")
async def root():
    """
    根路由健康检查

    What: 返回服务运行状态
    Why: 用于前端和监控系统快速验证后端是否正常运行
    """
    return {"status": "ok"}
