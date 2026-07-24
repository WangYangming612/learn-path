"""
Agent 状态定义模块

What: 定义基于 LangGraph 的通用智能体状态基类 AgentState
Why: 作为所有 Agent 状态的基础类型，确保类型安全和结构一致
"""

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages


class AgentState(TypedDict):
    """
    通用智能体状态基类

    What: 定义智能体在图中的运行时状态结构
    Why: LangGraph 的 StateGraph 依赖 TypedDict 来追踪状态变更，
         所有子 Agent 应继承或兼容此状态定义

    Attributes:
        messages: 对话历史列表，包含所有用户和 AI 消息
        user_id: 当前交互用户的唯一标识
        plan_id: 当前计划上下文（可选，子 Agent 可选择性使用）
        session_id: 当前会话的唯一标识
        agent_type: 智能体类型标识（如 "orchestrator"、"profile" 等）
        tools: 智能体可调用的工具列表
        next: 下一步路由目标，由条件边根据此字段值决定路由方向
    """
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    plan_id: str | None
    session_id: str
    agent_type: str
    tools: list
    next: str


def create_initial_state(
    user_id: str,
    session_id: str,
    *,
    plan_id: str | None = None,
    agent_type: str = "orchestrator",
    messages: Annotated[list[BaseMessage], add_messages] | None = None,
    tools: list | None = None,
    next: str = "",
) -> AgentState:
    """
    创建初始 Agent 状态

    What: 工厂函数，提供合理的默认值构建 AgentState
    Why: TypedDict 不支持字段默认值，通过此函数统一初始化入口

    Args:
        user_id: 用户 ID
        session_id: 会话 ID
        plan_id: 可选，计划 ID
        agent_type: 智能体类型，默认 "orchestrator"
        messages: 可选，初始消息列表，默认空列表
        tools: 可选，工具列表，默认空列表
        next: 可选，下一步路由，默认空字符串

    Returns:
        AgentState: 初始化后的状态字典
    """
    return {
        "messages": messages or [],
        "user_id": user_id,
        "plan_id": plan_id,
        "session_id": session_id,
        "agent_type": agent_type,
        "tools": tools or [],
        "next": next,
    }
