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
from app.core.config import settings
import pathlib
import os

# 从.env文件加载代理配置（可选，VPN/翻墙用户才需要设置）
env_path = pathlib.Path(__file__).resolve().parent / '.env'
if env_path.exists():
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line.startswith('HTTP_PROXY=') or line.startswith('HTTPS_PROXY='):
            key, val = line.split('=', 1)
            val = val.strip(chr(34))
            if val and key not in os.environ:
                try:
                    import socket
                    host_part = val.replace('http://', '').replace('https://', '')
                    host, port = host_part.split(':')
                    sock = socket.create_connection((host, int(port)), timeout=1)
                    sock.close()
                    os.environ[key] = val
                    print(f"[Proxy] {key} 可用，已加载")
                except Exception:
                    print(f"[Proxy] {key} 不可用（VPN未开启），跳过")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.core.scheduler import scheduler
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(
    title="LearnPath API",
    description="个性化学习路径动态生成系统后端 API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import logging
    logging.getLogger(__name__).exception('[500] %s', exc)
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={'detail': '服务器错误: ' + str(exc)[:300]},
    )


# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(auth_router, prefix='/api/v1')
app.include_router(events_router, prefix='/api/v1')
app.include_router(feedback_router, prefix='/api/v1')
app.include_router(journals_router, prefix='/api/v1')
app.include_router(plans_router, prefix='/api/v1')
app.include_router(tasks_router, prefix='/api/v1')
app.include_router(profile_router, prefix='/api/v1')


@app.get('/')
async def root():
    return {'status': 'ok'}
