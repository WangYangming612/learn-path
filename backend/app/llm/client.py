"""
LLM 统一客户端模块

What: 封装 langchain_openai.ChatOpenAI，提供单例模式的 LLM 调用入口
Why: 隔离 LLM 调用细节，避免各 Agent 重复配置；单例模式确保全局只有一份实例
"""

import os
from typing import Any

from langchain_openai import ChatOpenAI

from app.core.config import settings


class LLMClient:
    """
    LLM 统一客户端（单例模式）

    What: 封装 ChatOpenAI，提供统一的 LLM 模型获取入口
    Why: 单例模式确保全局只初始化一次，避免重复创建连接；
         支持通过 config 字典、环境变量、全局 settings 三种方式配置

    How: 使用 __new__ 实现单例，构造函数只执行一次初始化逻辑

    Attributes:
        model: 模型名称
        base_url: API 地址
        api_key: API 密钥
        temperature: 生成温度
        timeout: 请求超时秒数
    """

    _instance: "LLMClient | None" = None
    _initialized: bool = False

    def __new__(cls, *args: Any, **kwargs: Any) -> "LLMClient":
        """单例控制：确保全局只有一个实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config: dict | None = None) -> None:
        """
        初始化 LLM 客户端

        What: 从配置字典或环境变量中读取 LLM 参数
        Why: 支持灵活配置，优先级：config 字典 > 环境变量 > settings 单例 > 默认值

        Args:
            config: 可选配置字典，可包含 model、base_url、api_key、temperature、timeout
        """
        # 单例模式：只初始化一次
        if LLMClient._initialized:
            return
        LLMClient._initialized = True

        # 合并配置：config 字典（最高优先级）
        config = config or {}

        # ── 模型名称 ────────────────────────────────────────────
        self.model: str = (
            config.get("model")
            or os.getenv("LLM_MODEL")
            or settings.LLM_MODEL
            or "gpt-4o-mini"
        )

        # ── API 地址 ────────────────────────────────────────────
        # 支持 OPENAI_BASE_URL（标准 OpenAI 环境变量）和 LLM_BASE_URL（项目自定义）
        self.base_url: str = (
            config.get("base_url")
            or os.getenv("OPENAI_BASE_URL")
            or os.getenv("LLM_BASE_URL")
            or settings.LLM_BASE_URL
            or "https://api.openai.com/v1"
        )

        # ── API 密钥 ────────────────────────────────────────────
        # 支持 OPENAI_API_KEY（标准 OpenAI 环境变量）和 LLM_API_KEY（项目自定义）
        self.api_key: str = (
            config.get("api_key")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("LLM_API_KEY")
            or settings.LLM_API_KEY
            or ""
        )

        # ── 生成参数 ────────────────────────────────────────────
        self.temperature: float = config.get("temperature", 0.7)
        self.timeout: int = config.get("timeout", 60)

    def get_chat_model(self, **kwargs: Any) -> ChatOpenAI:
        """
        获取配置好的 ChatOpenAI 实例

        What: 基于当前客户端配置创建 ChatOpenAI 实例
        Why: 封装实例化逻辑，kwargs 允许按需覆盖参数（如温度、模型等）

        Args:
            **kwargs: 可覆盖的参数，支持 model、temperature、timeout 等

        Returns:
            ChatOpenAI: 配置好的 LLM 实例
        """
        return ChatOpenAI(
            model=kwargs.get("model", self.model),
            base_url=kwargs.get("base_url", self.base_url),
            api_key=kwargs.get("api_key", self.api_key),
            temperature=kwargs.get("temperature", self.temperature),
            timeout=kwargs.get("timeout", self.timeout),
        )

    @classmethod
    def reset_instance(cls) -> None:
        """
        重置单例（主要用于测试）

        What: 清空 _instance 和 _initialized，下次调用 __init__ 会重新初始化
        Why: 测试时需要隔离不同测试用例的配置状态
        """
        cls._instance = None
        cls._initialized = False


# 全局默认客户端实例
llm_client = LLMClient()
