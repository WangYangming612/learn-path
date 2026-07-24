"""
Orchestrator 编排智能体模块

What: 实现系统入口智能体，负责意图分类和子图路由
Why: Orchestrator 是用户请求的统一入口，通过意图分类将请求分发到对应子 Agent

架构说明:
    __start__ → intent_classifier → (条件边) → plan_agent / feedback_agent /
                                                profile_agent / fallback_handler
    各子节点 → __end__
"""

from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from app.agents.state import AgentState, create_initial_state
from app.llm.client import llm_client
from app.llm.prompts.orchestrator import build_intent_classification_messages
from app.agents.profile_agent import run_profile_get_chat


# ── 意图分类（关键词规则） ────────────────────────────────────────
# What: LLM 不可用时的 fallback 关键词规则
# Why: 确保在无 API Key 或网络不可用时 Orchestrator 仍可正常运行和测试
_INTENT_KEYWORDS: dict[str, list[str]] = {
    "create_plan": ["创建", "学习计划", "制定", "入门", "规划", "目标", "想要学", "打算学"],
    "submit_feedback": ["学完了", "完成了", "感觉难", "感觉", "难", "容易", "反馈", "理解", "掌握", "巩固"],
    "view_profile": ["学习情况", "学习画像", "学习进度", "看看我的"],
}


def _classify_by_keywords(user_input: str) -> str:
    """
    基于关键词的意图分类（LLM fallback）

    What: 使用简单的关键词匹配规则判断用户意图
    Why: 作为 LLM 调用失败时的降级方案，保证系统可独立验证

    Args:
        user_input: 用户输入文本

    Returns:
        str: 意图标签
    """
    text = user_input.lower()
    for intent, keywords in _INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return intent
    return "other"


# ── 图节点函数 ──────────────────────────────────────────────────

def intent_classifier_node(state: AgentState) -> dict[str, Any]:
    """
    意图分类节点

    What: 调用 LLM 对用户输入进行意图分类，将结果写入 state["next"]
    Why: 输入路由决策的核心节点，决定后续子图流向

    Args:
        state: 当前 Agent 状态

    Returns:
        dict: 更新后的状态字段，包含 next 路由目标
    """
    # 从消息列表中提取最后一条用户消息
    last_user_msg = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            last_user_msg = msg.content
            break

    if not last_user_msg:
        return {"next": "other"}

    # 尝试使用 LLM 进行意图分类
    try:
        messages = build_intent_classification_messages(last_user_msg)
        chat_model = llm_client.get_chat_model(temperature=0, timeout=5)  # 意图分类用低温度
        response = chat_model.invoke(messages)
        intent = response.content.strip().lower()

        # 验证返回值是否在合法意图范围内
        valid_intents = {"create_plan", "submit_feedback", "view_profile", "other"}
        if intent not in valid_intents:
            intent = "other"

        return {"next": intent}
    except Exception:
        # LLM 调用失败 → 使用关键词 fallback
        intent = _classify_by_keywords(last_user_msg)
        return {"next": intent}


def plan_agent_node(state: AgentState) -> dict[str, Any]:
    """
    计划 Agent 占位节点

    What: 占位节点，表示路由已到达计划 Agent
    Why: 在 Step 7 实现 Plan Agent 之前用作占位，保证图结构完整

    Returns:
        dict: 包含一条通知消息和空 next（无后续路由）
    """
    return {
        "messages": [AIMessage(content="[占位] 已到达计划 Agent，计划创建功能将在 Step 7 实现")]
    }


def feedback_agent_node(state: AgentState) -> dict[str, Any]:
    """
    反馈 Agent 节点

    What: 路由到 Feedback Agent，返回引导消息让用户提交 task_id
    Why: Feedback Agent 通过 REST API 交互（SSE 流式追问），
         Orchestrator 在此提示用户使用反馈端点

    Returns:
        dict: 包含 Feedback Agent 入口提示消息
    """
    return {
        "messages": [AIMessage(
            content=(
                "反馈功能已就绪！请完成学习任务后，通过以下方式提交反馈：\n\n"
                "1\u20e3 调用 `POST /api/v1/feedback/start` 并传入 task_id\n"
                "2\u20e3 系统会生成个性化追问（SSE 流式返回）\n"
                "3\u20e3 回复后再调用 `POST /api/v1/feedback/reply` 提交回复\n\n"
                "你也可以直接在对话框里告诉我你的学习感受，我来帮你分析。"
            )
        )]
    }
async def profile_agent_node(state: AgentState) -> dict[str, Any]:
    """
    画像 Agent 节点

    What: 调用 Profile Agent 加载用户画像并格式化为自然语言聊天消息
    Why: Orchestrator 路由到 view_profile 意图时，通过此节点返回画像卡片

    Args:
        state: 当前 Agent 状态

    Returns:
        dict: 包含 profile 聊天消息的 messages 列表
    """
    try:
        result = await run_profile_get_chat(
            user_id=state["user_id"],
            session_id=state["session_id"],
        )
        return {"messages": result.get("messages", [])}
    except Exception as exc:
        logger.exception(f"[Orchestrator] 画像 Agent 节点执行失败: {exc}")
        return {
            "messages": [AIMessage(content="抱歉，暂时无法获取您的学习画像，请稍后再试。")]
        }


def fallback_handler_node(state: AgentState) -> dict[str, Any]:
    """
    Fallback 处理节点

    What: 当意图为 "other" 时生成友好的 fallback 回复
    Why: 给用户一个友好的回应，而不是什么都不返回

    Returns:
        dict: 包含一条友好的 fallback 消息和空 next
    """
    return {
        "messages": [
            AIMessage(
                content="抱歉，我不太理解你的意图。我可以帮你做以下几件事：\n\n"
                "1️⃣ **创建学习计划** — 告诉我你想学什么，比如「我想3个月入门Python」\n"
                "2️⃣ **提交学习反馈** — 学完后告诉我你的感受，比如「函数参数有点难」\n"
                "3️⃣ **查看学习画像** — 说「看看我的学习情况」了解系统对你的认知\n\n"
                "你想试试哪个？"
            )
        ]
    }


# ── 条件路由函数 ────────────────────────────────────────────────

def router_after_classification(state: AgentState) -> Literal[
    "plan_agent",
    "feedback_agent",
    "profile_agent",
    "fallback_handler",
]:
    """
    意图分类后的条件路由

    What: 根据 state["next"] 的值路由到对应的子 Agent
    Why: LangGraph 的条件边需要一个函数返回目标节点名称

    Returns:
        str: 目标节点名称
    """
    intent = state.get("next", "other")

    routing_map = {
        "create_plan": "plan_agent",
        "submit_feedback": "feedback_agent",
        "view_profile": "profile_agent",
    }

    return routing_map.get(intent, "fallback_handler")


# ── 图构建与运行 ────────────────────────────────────────────────

def create_orchestrator_graph() -> StateGraph:
    """
    创建 Orchestrator 状态图

    What: 构建完整的 Orchestrator StateGraph，注册所有节点和边
    Why: 导出此函数供外部调用，保持图构建和运行分离（便于测试）

    Returns:
        StateGraph: 编译好的 Orchestrator 图
    """
    # 创建图实例，使用 AgentState 作为状态类型
    graph = StateGraph(AgentState)

    # ── 注册节点 ──────────────────────────────────────────────
    graph.add_node("intent_classifier", intent_classifier_node)
    graph.add_node("plan_agent", plan_agent_node)
    graph.add_node("feedback_agent", feedback_agent_node)
    graph.add_node("profile_agent", profile_agent_node)
    graph.add_node("fallback_handler", fallback_handler_node)

    # ── 注册边 ────────────────────────────────────────────────
    # 起始 → 意图分类器
    graph.add_edge(START, "intent_classifier")

    # 意图分类器 → 条件路由 → 各子节点
    graph.add_conditional_edges(
        "intent_classifier",
        router_after_classification,
        {
            "plan_agent": "plan_agent",
            "feedback_agent": "feedback_agent",
            "profile_agent": "profile_agent",
            "fallback_handler": "fallback_handler",
        },
    )

    # 各子节点 → 终点
    graph.add_edge("plan_agent", END)
    graph.add_edge("feedback_agent", END)
    graph.add_edge("profile_agent", END)
    graph.add_edge("fallback_handler", END)

    return graph.compile()


async def run_orchestrator(
    user_input: str,
    user_id: str = "test_user",
    session_id: str = "test_session",
    **kwargs: Any,
) -> dict[str, Any]:
    """
    运行 Orchestrator 的便捷函数

    What: 快速运行 Orchestrator 的入口，用于 MVP 验证和测试
    Why: 省略手动构建状态和图的步骤，一行代码即可验证意图分类效果

    Args:
        user_input: 用户输入的文本
        user_id: 用户 ID，默认 "test_user"
        session_id: 会话 ID，默认 "test_session"
        **kwargs: 传递给 create_initial_state 的其他参数

    Returns:
        dict: 执行完成后的最终状态（包含 messages 和 next 等字段）
    """
    # 构建初始状态
    initial_state = create_initial_state(
        user_id=user_id,
        session_id=session_id,
        messages=[HumanMessage(content=user_input)],
        **kwargs,
    )

    # 编译并运行图（ainvoke 支持混合 sync/async 节点）
    graph = create_orchestrator_graph()
    result = await graph.ainvoke(initial_state)

    return result
