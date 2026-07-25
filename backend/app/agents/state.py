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
    parsed_goal: dict | None
    plan_result: dict | None


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
        parsed_goal: 可选，解析后的学习目标
        plan_result: 可选，Plan Agent 的最终结果

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
class FeedbackAgentState(AgentState):
    """
    反馈分析智能体状态

    What: 扩展 AgentState，增加反馈分析所需的专有字段
    Why: 承载 Feedback Agent 子图中各节点间的数据流转

    Attributes:
        feedback_signal: 解析后的信号: too_easy / normal / stuck / need_practice
        confidence_delta: 掌握度变化量 (-1.0 ~ 1.0)
        replan_triggered: 是否触发重规划
        profile_updates: 待更新的画像维度
        task_id: 关联的每日任务 ID
        learning_content: 本次学习内容
        feedback_question: 生成的追问
        user_reply: 用户的回复
        system_response: 系统响应
    """
    feedback_signal: str | None
    confidence_delta: float | None
    replan_triggered: bool
    profile_updates: dict | None
    task_id: str | None
    learning_content: str | None
    feedback_question: str | None
    user_reply: str | None
    system_response: str | None


class ProfileDimension(TypedDict):
    """
    画像单维度数据结构

    What: 定义单个画像维度的 label、confidence 和 evidence
    Why: ProfileData 和 ProfileAgentState 依赖此类型，
         确保画像 6 维度结构统一、便于序列化和 LLM 解析

    Attributes:
        label: 维度标签（如 "理解偏慢但记忆牢固型"）
        confidence: 置信度，范围 0-100
        evidence: 证据列表，每条是触发该判断的反馈记录摘要
    """
    label: str
    confidence: float
    evidence: list[str]


class ProfileData(TypedDict):
    """
    完整画像数据（6 维度）

    What: 聚合所有画像维度的结构化快照
    Why: 作为 ProfileAgentState.profile 的承载类型，
         供 Plan / Schedule / Feedback Agent 按维度读取画像

    Attributes:
        learning_style: 学习风格
        best_time_slots: 最佳学习时段
        learning_rhythm: 学习节奏偏好
        feedback_baseline: 反馈校准基线
        persistence: 持续力特征
        knowledge_retention: 知识保留特征
    """
    learning_style: ProfileDimension
    best_time_slots: ProfileDimension
    learning_rhythm: ProfileDimension
    feedback_baseline: ProfileDimension
    persistence: ProfileDimension
    knowledge_retention: ProfileDimension


class ProfileAgentState(AgentState):
    """
    画像智能体状态

    What: 扩展 AgentState，增加画像查询/构建/更新/校准所需字段
    Why: 承载 Profile Agent 子图中各节点间的数据流转

    Attributes:
        action: 操作类型: initial_survey / update_profile / get_profile / calibrate_dimension
        survey_answers: 用户对摸底问题的回答历史（initial_survey 使用）
        feedback_signal: 反馈信号，来自 Feedback Agent（update_profile 使用）
        confidence_delta: 掌握度变化量 -1.0 ~ 1.0（update_profile 使用）
        source_session: 来源反馈会话 ID（update_profile 使用）
        target_dimension: 用户点踩的维度名（calibrate_dimension 使用）
        user_comment: 用户校准说明（calibrate_dimension 使用）
        profile: 当前画像快照
        survey_question: 摸底追问问题
        calibration_result: 校准结果说明
        profile_changed: 画像是否有变更
        profile_changelog: 变更记录列表
    """
    action: str
    survey_answers: list[str] | None
    feedback_signal: str | None
    confidence_delta: float | None
    source_session: str | None
    target_dimension: str | None
    user_comment: str | None
    profile: ProfileData | None
    survey_question: str | None
    calibration_result: str | None
    profile_changed: bool | None
    profile_changelog: list[dict] | None
