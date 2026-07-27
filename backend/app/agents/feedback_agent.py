
"""
Feedback Agent 子图模块

What: 实现反馈分析子图，包含 load_context → generate_question → parse_signal → generate_response
Why: 接收用户完成任务的反馈，通过 LLM 分析输出结构化信号和画像更新

架构说明：
  由于 LangGraph 子图不能"等待"外部输入，将流程拆为两段供外部 API 调用：
  - run_feedback_graph_first_half:  load_context → generate_question（返回追问）
  - run_feedback_graph_second_half: parse_signal → generate_response （返回信号+响应）
"""

import json
import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.state import FeedbackAgentState
from app.core.profile_service import get_user_profile
from app.llm.client import llm_client
from app.llm.prompts.feedback import (
    FEEDBACK_QUESTION_PROMPT,
    FEEDBACK_RESPONSE_PROMPT,
    FEEDBACK_SIGNAL_PROMPT,
)

logger = logging.getLogger(__name__)


# ── 辅助函数 ─────────────────────────────────────────────────────

def _safe_profile(val: Any, default: str = "未知") -> str:
    """
    安全提取画像维度值（兼容新旧格式）

    What: 从 ProfileService 返回的画像数据中提取可显示的字符串
    Why: 旧格式为纯字符串 "理解偏慢型"，新格式为 {label, confidence, evidence}，
         此函数统一两种格式的输出，确保 LLM prompt 不受影响

    Args:
        val: 画像维度值（str | dict | None）
        default: 无法提取时的默认值

    Returns:
        str: 用于 LLM prompt 的维度字符串
    """
    if val is None:
        return default
    if isinstance(val, dict):
        return str(val.get("label", val.get("value", default)))
    return str(val) if val else default


# ── 节点实现 ─────────────────────────────────────────────────────

async def load_context(state: FeedbackAgentState) -> dict[str, Any]:
    """
    加载上下文节点

    What: 根据 task_id 查询知识节点内容，从 profile_service 加载用户画像
    Why: 为 LLM 追问提供输入上下文，若 KnowledgeNode 不存在则使用 task 标题
    """
    user_id = state.get("user_id", "")
    task_id = state.get("task_id", "")

    # 1. 查询任务详情和关联的知识节点内容
    learning_content = ""
    try:
        from sqlalchemy import select
        from app.db.session import get_db as _get_db
        from app.models.daily_task import DailyTask
        from app.models.knowledge_node import KnowledgeNode

        async for db in _get_db():
            result = await db.execute(
                select(DailyTask).where(DailyTask.id == int(task_id))
            )
            task = result.scalar_one_or_none()
            if task:
                content_parts = [f"任务标题：{task.title}"]
                if task.description:
                    content_parts.append(f"任务描述：{task.description}")
                if task.knowledge_node_id:
                    kn_result = await db.execute(
                        select(KnowledgeNode).where(
                            KnowledgeNode.id == task.knowledge_node_id
                        )
                    )
                    kn = kn_result.scalar_one_or_none()
                    if kn:
                        content_parts.append(f"知识点：{kn.name}")
                        if kn.description:
                            content_parts.append(f"知识点描述：{kn.description}")
                learning_content = "\n".join(content_parts)
            break
    except Exception as exc:
        logger.warning(f"[FeedbackAgent] 查询任务/知识节点失败: {exc}")
        learning_content = f"任务 #{task_id}"

    # 2. 获取用户画像（失败时自动使用默认画像）
    profile_full = await get_user_profile(user_id)
    profile = profile_full.get("profile", {})
    profile["total_feedback_count"] = profile_full.get("total_feedback_count", 0)
    profile["recent_feedback_history"] = []

    return {
        "learning_content": learning_content,
        "profile_updates": profile,
    }


async def generate_question(state: FeedbackAgentState) -> dict[str, Any]:
    """
    生成追问节点

    What: 调用 LLM 生成个性化追问，基于画像 + 学习内容 + 反馈历史
    Why: 追问是反馈流程的第一步，引导用户描述学习感受
    """
    learning_content = state.get("learning_content", "未知内容")
    profile = state.get("profile_updates", {})

    prompt_args = {
        "learning_style": _safe_profile(profile.get("learning_style")),
        "best_time_slots": _safe_profile(profile.get("best_time_slots")),
        "learning_rhythm": _safe_profile(profile.get("learning_rhythm")),
        "feedback_baseline": _safe_profile(profile.get("feedback_baseline")),
        "persistence": _safe_profile(profile.get("persistence")),
        "knowledge_retention": _safe_profile(profile.get("knowledge_retention")),
        "total_feedback_count": profile.get("total_feedback_count", 0),
        "learning_content": learning_content,
        "recent_feedback_history": str(profile.get("recent_feedback_history", [])),
    }

    question = ""
    try:
        chat_model = llm_client.get_chat_model(temperature=0.7, timeout=30)
        response = await chat_model.ainvoke([
            {"role": "system", "content": FEEDBACK_QUESTION_PROMPT.format(**prompt_args)},
            {"role": "user", "content": "请根据以上信息生成追问。"},
        ])
        question = response.content.strip()
    except Exception as exc:
        logger.error(f"[FeedbackAgent] 生成追问失败: {exc}")
        question = "今天的学习感觉怎么样？有什么想和我分享的吗？"

    # 微观自审：检查追问是否合理
    if question:
        review = await _self_review_question(
            question=question,
            learning_content=state.get("learning_content", ""),
        )
        if review.get("verdict") == "fail":
            logger.info(f"[FeedbackAgent] 追问自审不通过: {review.get('issues')}")

    return {"feedback_question": question}


async def _self_review_question(question: str, learning_content: str) -> dict:
    """
    追问质量自审

    What: 先用规则快速过滤，再用 LLM 做语义审查
    Why: 避免生成无关或质量差的追问影响用户体验
    """
    # 规则检查（快速，免 LLM）
    if len(question) < 5:
        return {"verdict": "fail", "issues": ["追问太短"]}

    # LLM 语义审查
    try:
        chat_model = llm_client.get_chat_model(temperature=0, timeout=10)
        response = await chat_model.ainvoke([
            {"role": "system", "content": (
                "你是一个追问质量审查员。检查以下追问是否合理。标准：\n"
                "1. 追问是否与学习内容相关\n"
                "2. 追问是否回避用户没提过的新概念\n"
                "3. 追问语气是否友好、开放\n"
                "请回复 JSON: {\"verdict\": \"pass\"|\"fail\", \"issues\": [\"问题1\", \"问题2\"]}"
            )},
            {"role": "user", "content": f"学习内容：{learning_content}\n追问：{question}"},
        ])
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]
        import json
        return json.loads(raw)
    except Exception:
        return {"verdict": "pass"}  # 自审失败时放行，不阻塞


async def parse_signal(state: FeedbackAgentState) -> dict[str, Any]:
    """
    信号解析节点

    What: 调用 LLM 语义分析用户回复，输出 signal、confidence_delta 和 profile_updates
    Why: 将自然语言回复转化为结构化信号
    """
    user_reply = state.get("user_reply", "")
    learning_content = state.get("learning_content", "未知内容")
    profile = state.get("profile_updates", {})

    profile_summary = (
        f"学习风格: {_safe_profile(profile.get('learning_style'))}, "
        f"学习节奏: {_safe_profile(profile.get('learning_rhythm'))}, "
        f"反馈基线: {_safe_profile(profile.get('feedback_baseline'))}"
    )

    signal = "normal"
    confidence_delta = 0.0
    profile_updates = {}
    replan_triggered = False

    try:
        chat_model = llm_client.get_chat_model(temperature=0.3, timeout=30)
        response = await chat_model.ainvoke([
            {"role": "system", "content": FEEDBACK_SIGNAL_PROMPT.format(
                user_reply=user_reply,
                learning_content=learning_content,
                profile_summary=profile_summary,
            )},
            {"role": "user", "content": "请分析上述回复。"},
        ])
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("\n", 1)[0] if "\n" in raw else raw
            if raw.endswith("```"):
                raw = raw[:-3]
        parsed = json.loads(raw)
        signal = parsed.get("signal", "normal")
        confidence_delta = float(parsed.get("confidence_delta", 0.0))
        profile_updates = parsed.get("profile_updates", {})
        if signal in ("stuck", "need_practice"):
            replan_triggered = True
    except Exception as exc:
        logger.error(f"[FeedbackAgent] 信号解析失败: {exc}")
        stuck_keywords = ["难", "不懂", "困惑", "复杂", "不清楚", "迷茫"]
        practice_keywords = ["理解", "懂", "会", "练习", "巩固", "复习", "再练"]
        easy_keywords = ["简单", "容易", "太浅", "都会", "早就"]
        for kw in stuck_keywords:
            if kw in user_reply:
                signal = "stuck"
                confidence_delta = -0.3
                replan_triggered = True
                break
        if signal == "normal":
            for kw in practice_keywords:
                if kw in user_reply:
                    signal = "need_practice"
                    confidence_delta = 0.3
                    replan_triggered = True
                    break
        if signal == "normal":
            for kw in easy_keywords:
                if kw in user_reply:
                    signal = "too_easy"
                    confidence_delta = 0.5
                    break

    return {
        "feedback_signal": signal,
        "confidence_delta": confidence_delta,
        "profile_updates": profile_updates,
        "replan_triggered": replan_triggered,
    }


async def generate_response(state: FeedbackAgentState) -> dict[str, Any]:
    """
    系统响应生成节点

    What: 根据信号分析结果，调用 LLM 生成自然语言回复
    Why: 让用户感知到系统已理解反馈并做出调整
    """
    signal = state.get("feedback_signal", "normal")
    confidence_delta = state.get("confidence_delta", 0.0)
    replan_triggered = state.get("replan_triggered", False)

    system_response = ""
    try:
        chat_model = llm_client.get_chat_model(temperature=0.7, timeout=30)
        response = await chat_model.ainvoke([
            {"role": "system", "content": FEEDBACK_RESPONSE_PROMPT.format(
                signal=signal,
                confidence_delta=confidence_delta,
                replan_triggered=replan_triggered,
            )},
            {"role": "user", "content": "请根据以上分析结果生成回复。"},
        ])
        system_response = response.content.strip()
    except Exception as exc:
        logger.error(f"[FeedbackAgent] 生成系统响应失败: {exc}")
        response_map = {
            "too_easy": "收到你的反馈！看来这部分内容对你偏简单，我会在后续安排更有挑战性的内容。",
            "normal": "收到你的反馈！难度适中是最理想的学习节奏，继续保持！",
            "stuck": "收到你的反馈！这部分确实有难度，我来调整一下学习路径，安排一些前置内容帮你打好基础。",
            "need_practice": "收到你的反馈！理解概念是第一步，我会安排一些练习帮你巩固。",
        }
        system_response = response_map.get(
            signal, "收到你的反馈！我会根据你的情况调整后续学习安排。"
        )

    return {"system_response": system_response}


# ── 图构建 ──────────────────────────────────────────────────────

def create_feedback_graph() -> StateGraph:
    """创建 Feedback Agent 前半段子图：load_context → generate_question"""
    graph = StateGraph(FeedbackAgentState)
    graph.add_node("load_context", load_context)
    graph.add_node("generate_question", generate_question)
    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "generate_question")
    graph.add_edge("generate_question", END)
    return graph.compile()


def create_feedback_graph_second_half() -> StateGraph:
    """创建 Feedback Agent 后半段子图：parse_signal → generate_response"""
    graph = StateGraph(FeedbackAgentState)
    graph.add_node("parse_signal", parse_signal)
    graph.add_node("generate_response", generate_response)
    graph.add_edge(START, "parse_signal")
    graph.add_edge("parse_signal", "generate_response")
    graph.add_edge("generate_response", END)
    return graph.compile()


# ── 便捷调用函数 ─────────────────────────────────────────────────

async def run_feedback_graph_first_half(
    user_id: str,
    task_id: str,
) -> dict[str, Any]:
    """
    运行 Feedback Agent 前半段：加载上下文 → 生成追问

    Args:
        user_id: 用户 ID
        task_id: 每日任务 ID

    Returns:
        dict: 包含 learning_content, feedback_question 等状态字段
    """
    graph = create_feedback_graph()
    initial_state: FeedbackAgentState = {
        "messages": [],
        "user_id": user_id,
        "plan_id": None,
        "session_id": "",
        "agent_type": "feedback",
        "tools": [],
        "next": "",
        "parsed_goal": None,
        "plan_result": None,
        "execution_plan": [],
        "execution_index": 0,
        "step_results": {},
        "orchestration_warnings": [],
        "review_attempts": 0,
        "review_max_attempts": 3,
        "review_results": [],
        "raw_agent_output": None,
        "review_verdict": "",
        "feedback_signal": None,
        "confidence_delta": None,
        "replan_triggered": False,
        "profile_updates": None,
        "task_id": task_id,
        "learning_content": None,
        "feedback_question": None,
        "user_reply": None,
        "system_response": None,
    }
    result = await graph.ainvoke(initial_state)
    return result


async def run_feedback_graph_second_half(
    user_id: str,
    task_id: str,
    user_reply: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """
    运行 Feedback Agent 后半段：解析信号 → 生成响应

    Args:
        user_id: 用户 ID
        task_id: 每日任务 ID
        user_reply: 用户对追问的回复文本
        context: 前半段返回的状态（含 learning_content, profile_updates 等）

    Returns:
        dict: 包含 signal, confidence_delta, replan_triggered, profile_updates, system_response
    """
    graph = create_feedback_graph_second_half()
    profile_updates = context.get("profile_updates")
    if not isinstance(profile_updates, dict):
        profile_updates = {}

    initial_state: FeedbackAgentState = {
        "messages": [],
        "user_id": user_id,
        "plan_id": None,
        "session_id": "",
        "agent_type": "feedback",
        "tools": [],
        "next": "",
        "parsed_goal": None,
        "plan_result": None,
        "execution_plan": [],
        "execution_index": 0,
        "step_results": {},
        "orchestration_warnings": [],
        "review_attempts": 0,
        "review_max_attempts": 3,
        "review_results": [],
        "raw_agent_output": None,
        "review_verdict": "",
        "feedback_signal": None,
        "confidence_delta": None,
        "replan_triggered": False,
        "profile_updates": profile_updates,
        "task_id": task_id,
        "learning_content": context.get("learning_content"),
        "feedback_question": context.get("feedback_question"),
        "user_reply": user_reply,
        "system_response": None,
    }
    result = await graph.ainvoke(initial_state)
    return result


async def save_feedback_session(
    user_id: str,
    task_id: str,
    signal: str,
    confidence_delta: float,
    replan_triggered: bool,
    profile_updates: dict,
    question: str,
    reply: str,
    system_response: str,
) -> bool:
    """
    保存反馈会话记录到 FeedbackSession ORM 表

    What: 持久化反馈历史供 Profile Agent 后续读取
    Why: 确保反馈数据不丢失，Step 6 Profile Agent 可用时查询
    """
    try:
        from app.db.session import get_db as _get_db
        from app.models.feedback_session import FeedbackSession

        content = {
            "task_id": task_id,
            "questions": [question],
            "answers": [reply],
            "signals": [{
                "signal": signal,
                "confidence_delta": confidence_delta,
                "replan_triggered": replan_triggered,
            }],
            "profile_updates": profile_updates,
            "system_response": system_response,
        }

        async for db in _get_db():
            session = FeedbackSession(
                user_id=int(user_id),
                session_type="daily_feedback",
                content=content,
            )
            db.add(session)
            await db.commit()
            # ── 信号闭环：将反馈信号写回 DailyTask，供 Schedule 读取 ──
            try:
                from app.models.daily_task import DailyTask
                from sqlalchemy import select

                result = await db.execute(
                    select(DailyTask).where(DailyTask.id == int(task_id))
                )
                task = result.scalar_one_or_none()
                if task:
                    task.feedback_signal = signal
                    task.feedback_confidence_delta = confidence_delta
                    await db.commit()
                    logger.info(
                        f"[FeedbackAgent] 反馈信号写入 DailyTask #{task_id}: signal={signal}, delta={confidence_delta}"
                    )
            except Exception as exc:
                logger.warning(f"[FeedbackAgent] 写入 DailyTask 反馈信号失败: {exc}")
            break
        return True
    except Exception as exc:
        logger.error(f"[FeedbackAgent] 保存反馈会话失败: {exc}")
        return False
