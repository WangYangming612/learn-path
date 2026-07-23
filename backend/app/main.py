"""
LearnPath API 主应用入口

What: FastAPI 应用实例，作为整个后端服务的 HTTP 入口点
Why: 统一管理路由注册、中间件配置和应用生命周期
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 创建 FastAPI 应用实例
# What: FastAPI 应用对象，用于注册路由和中间件
# Why: FastAPI 是异步 Web 框架，支持自动生成 OpenAPI 文档（Swagger）
app = FastAPI(
    title="LearnPath API",
    description="个性化学习路径动态生成系统后端 API",
    version="0.1.0",
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


@app.get("/")
async def root():
    """
    根路由健康检查

    What: 返回服务运行状态
    Why: 用于前端和监控系统快速验证后端是否正常运行
    """
    return {"status": "ok"}
