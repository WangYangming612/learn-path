"""
配置管理模块

What: 集中管理应用所有配置项，支持从 .env 文件和系统环境变量加载
Why: 配置与代码分离，敏感信息不硬编码；pydantic-settings 提供类型校验和 IDE 自动补全
How: 定义 Settings 类继承 BaseSettings，通过 model_config 指定 .env 路径，模块底部导出单例
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


# 项目根目录（backend/ 的父目录）
# What: 定位到 learn-path/backend/ 目录
# Why: .env 文件存放在 backend/ 下，需要基于此目录解析相对路径
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # -> backend/


class Settings(BaseSettings):
    """
    应用全局配置

    What: 所有配置项的集中定义，自动从 .env 读取
    Why: 类型安全、IDE 友好、环境切换只需修改 .env 文件
    """

    # ── 数据库 ──────────────────────────────────────────────
    # What: SQLAlchemy 异步数据库连接字符串
    # Why: Step 2 建表脚本和后续所有 ORM 操作都依赖此 URL
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/sqlite/app.db"

    # ── 安全 ────────────────────────────────────────────────
    # What: JWT 令牌签名密钥 + 敏感数据加密密钥
    # Why: Step 3 用户认证需要；生产环境必须覆盖为随机字符串
    SECRET_KEY: str = "change-this-to-a-random-secret-key"

    # ── 应用 ────────────────────────────────────────────────
    # What: 应用元信息，用于 OpenAPI 文档标题和版本
    # Why: 对应 config.yaml 中 app.name / app.version
    APP_NAME: str = "LearnPath"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    # ── 服务器 ──────────────────────────────────────────────
    # What: Uvicorn 监听地址和端口
    # Why: 对应 config.yaml 中 server.host / server.port
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000

    # ── LLM 服务（预留，Step 5 启用）─────────────────────────
    # What: 大语言模型 API 的认证密钥
    # Why: 多智能体系统依赖 LLM 进行路径生成、反馈分析等核心能力
    LLM_API_KEY: str = "sk-your-api-key"

    # What: LLM API 的请求端点地址
    # Why: 默认使用 OpenAI 兼容接口，可切换 DeepSeek / Ollama 等
    LLM_BASE_URL: str = "https://api.openai.com/v1"

    # What: 使用的模型名称
    # Why: 不同场景可能需要不同模型（如便宜模型做意图分类，强模型做路径生成）
    LLM_MODEL: str = "gpt-4o"

    # ── ChromaDB（预留，Step 2 后续阶段）─────────────────────
    # What: 向量数据库持久化目录路径
    # Why: Profile Agent 需要 ChromaDB 存储画像向量做语义检索
    CHROMA_PERSIST_DIR: str = "./data/chroma"

    # ── pydantic-settings 配置 ───────────────────────────────
    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略未定义的环境变量，避免因新增变量而报错
    )


# 全局配置单例
# What: 模块级单例，其他模块通过 from app.core.config import settings 使用
# Why: 避免重复解析 .env，保证全局配置一致
settings = Settings()
