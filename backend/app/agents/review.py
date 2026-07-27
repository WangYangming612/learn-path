"""
审查回路基础设施

What: 提供审查器注册机制 + 通用审查网关节点
Why: 各子 Agent 实现各自的审查逻辑后注册到此，Orchestrator 的审查网关自动调用

Usage:
    # 在 plan_agent.py 末尾注册
    register_reviewer("plan_agent", plan_reviewer)
"""

import logging
from typing import Any, Callable, Coroutine

from app.llm.client import llm_client

logger = logging.getLogger(__name__)

# 审查器注册表
# key: agent_type (str)
# value: async function (raw_output, user_input, context) -> dict
_review_registry: dict[str, Callable[..., Coroutine[Any, Any, dict]]] = {}


def register_reviewer(
    agent_type: str,
    reviewer_fn: Callable[..., Coroutine[Any, Any, dict]],
) -> None:
    """
    注册审查器

    Args:
        agent_type: Agent 类型标识，如 "plan_agent"
        reviewer_fn: 审查函数，签名：
            async fn(raw_output: dict, user_input: str, context: dict) -> dict
            返回: {"verdict": "pass"|"fail", "issues": [...], "suggestions": [...]}
    """
    _review_registry[agent_type] = reviewer_fn
    logger.info(f"[ReviewRegistry] 已注册审查器: {agent_type}")


def get_reviewer(agent_type: str) -> Callable | None:
    """获取指定 Agent 的审查器"""
    return _review_registry.get(agent_type)
