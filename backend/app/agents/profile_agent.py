"""
Profile Agent 子图模块

What: 实现画像查询展示和摸底问答，包含 profile_get 和 profile_survey 两个子图
Why: 用户聊天询问画像时返回自然语言卡片；新用户通过摸底问答建立初始画像

架构说明：
  子图 A — profile_get_graph（含审查 loop）：
      START → load_profile → format_chat_message → profile_review
          ├─ pass → END
          └─ fail (未达上限) → retry format_chat_message

  子图 B — profile_survey_graph（LLM 驱动，含审查 loop）：
      START → generate_survey_question → profile_review
          ├─ pass → END
          └─ fail (未达上限) → retry generate_survey_question

  子图 C — profile_survey_half2_graph（暂不接入 loop）：
      START → analyze_survey_answer → END
"""

import json
import logging
from typing import Any, Literal

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from app.agents.review import get_reviewer
from app.agents.state import ProfileAgentState
from app.core.profile_service import (
    DEFAULT_LABEL,
    PROFILE_DIMENSIONS,
    get_user_profile,
    update_profile,
)
from app.llm.client import llm_client
from app.llm.prompts.profile import (
    SURVEY_ANALYZE_ANSWER_PROMPT,
    SURVEY_GENERATE_QUESTION_PROMPT,
)

logger = logging.getLogger(__name__)

# ── 常量 ─────────────────────────────────────────────────────────
_TOTAL_ROUNDS = 4


# ── 辅助函数 ─────────────────────────────────────────────────────

def _convert_confidence_to_delta(target_confidence: float, old_confidence: float) -> float:
    """
    将 LLM 输出的绝对 confidence 转换为 profile_service.update_profile 所需的 confidence_delta

    What: SURVEY_ANALYZE_ANSWER_PROMPT 要求 LLM 输出绝对值 confidence(0-100)，
          但 profile_service._merge_dimension 只认 confidence_delta 字段做加权合并
    Why: 两套接口语义不兼容，需在 Agent 层做适配转换

    推导：
        profile_service._merge_dimension 中:
            new = old*0.7 + clamp(old + delta*30, 0, 100)*0.3
        忽略 clamp → new = old + 9*delta
        反推 → delta = (target - old) / 9

    Args:
        target_confidence: LLM 输出的目标绝对置信度 (0-100)
        old_confidence: 当前画像中该维度的置信度

    Returns:
        float: confidence_delta 值
    """
    if old_confidence >= target_confidence and target_confidence == 0:
        return 0.0
    return round((target_confidence - old_confidence) / 9, 4)


def _format_single_dimension(dim_name: str, dim_data: dict) -> str:
    """
    将单个维度格式化为可读文本行

    What: 从 {label, confidence, evidence} 结构中提取格式化的维度描述
    Why: format_chat_message 节点遍历 6 维度时的通用格式化逻辑
    """
    label = dim_data.get("label", DEFAULT_LABEL) if isinstance(dim_data, dict) else str(dim_data)
    confidence = dim_data.get("confidence", 0) if isinstance(dim_data, dict) else 0
    evidence_list = dim_data.get("evidence", []) if isinstance(dim_data, dict) else []

    dim_names = {
        "learning_style": "学习风格",
        "best_time_slots": "最佳学习时段",
        "learning_rhythm": "学习节奏",
        "feedback_baseline": "反馈校准基线",
        "persistence": "持续力",
        "knowledge_retention": "知识保留",
    }
    display = dim_names.get(dim_name, dim_name)

    lines = [f"  {display}：{label}  (置信度 {confidence}%)"]
    if evidence_list:
        for ev in evidence_list:
            lines.append(f"    • {ev}")
    return "\n".join(lines)


def _format_profile_snapshot(profile_data: dict) -> str:
    """
    将画像快照格式化为 LLM prompt 用的精简文本

    What: 输出每个维度的 label + confidence，未知维度标记"未知"
    Why: 供 SURVEY_GENERATE_QUESTION_PROMPT 和 SURVEY_ANALYZE_ANSWER_PROMPT 使用
    """
    dim_names = {
        "learning_style": "学习风格",
        "best_time_slots": "最佳学习时段",
        "learning_rhythm": "学习节奏",
        "feedback_baseline": "反馈校准基线",
        "persistence": "持续力",
        "knowledge_retention": "知识保留",
    }
    lines = ["当前画像维度状态："]
    for dim in PROFILE_DIMENSIONS:
        entry = profile_data.get(dim)
        if isinstance(entry, dict) and entry.get("label", "").strip() not in ("", DEFAULT_LABEL):
            lines.append(f"  - {dim_names.get(dim, dim)}：{entry['label']} (置信度 {entry.get('confidence', 0)}%)")
        else:
            lines.append(f"  - {dim_names.get(dim, dim)}：未知")
    return "\n".join(lines)


# ── 子图 A：画像查询 ─────────────────────────────────────────────

async def load_profile(state: ProfileAgentState) -> dict[str, Any]:
    """
    加载用户画像

    What: 调用 profile_service.get_user_profile 获取完整画像快照
    Why: 后续 format_chat_message 节点依赖此数据生成自然语言回复
    """
    user_id = state.get("user_id", "")
    profile_full = await get_user_profile(user_id)
    return {
        "profile": profile_full.get("profile", {}),
    }


async def format_chat_message(state: ProfileAgentState) -> dict[str, Any]:
    """
    将结构化画像格式化为聊天消息

    What: 遍历 6 个画像维度，拼接为自然语言卡片；无画像时返回引导消息
    Why: Orchestrator 期望子节点返回 messages 列表中包含 AIMessage
    """
    profile_data = state.get("profile") or {}

    has_profile = False
    for dim in PROFILE_DIMENSIONS:
        entry = profile_data.get(dim)
        if isinstance(entry, dict) and entry.get("label", "").strip() not in ("", DEFAULT_LABEL):
            has_profile = True
            break

    if not has_profile:
        return {
            "messages": [
                AIMessage(content=(
                    "您还没有建立学习画像。\n\n"
                    "学习画像可以帮助我：\n"
                    "  • 根据您的学习风格调整内容呈现方式\n"
                    "  • 在您的最佳时段安排学习任务\n"
                    "  • 匹配您的学习节奏避免过载\n\n"
                    "要不要现在来做个 4 轮摸底问答？我简单问您几个问题就好。"
                    "（后续可通过对话框说「开始摸底」来启动）"
                ))
            ]
        }

    parts = ["📊 学习画像\n"]
    for dim in PROFILE_DIMENSIONS:
        entry = profile_data.get(dim)
        if isinstance(entry, dict) and entry.get("label", "").strip() not in ("", DEFAULT_LABEL):
            parts.append(_format_single_dimension(dim, entry))

    parts.append(f"\n💡 如果某个维度判断不太准，可以告诉我，我会帮你校准。")

    return {
        "messages": [AIMessage(content="\n".join(parts))]
    }


# ── 子图 B：摸底问答 ─────────────────────────────────────────────

async def generate_survey_question(state: ProfileAgentState) -> dict[str, Any]:
    """
    生成摸底追问问题

    What: 基于当前轮次、已有回答、画像快照，调用 LLM 生成下一轮摸底问题
    Why: 追问应自然递进，优先探索未建立的维度
    """
    user_id = state.get("user_id", "")
    survey_answers = state.get("survey_answers") or []
    current_round = len(survey_answers) + 1

    # 加载当前画像状态
    profile_full = await get_user_profile(user_id)
    profile_data = profile_full.get("profile", {})

    if survey_answers:
        answers_context = "学生之前的回答：\n" + "\n".join(
            f"  第{i+1}轮：{ans}" for i, ans in enumerate(survey_answers)
        )
    else:
        answers_context = "（这是第 1 轮，学生还没有回答过任何问题）"

    profile_snapshot = _format_profile_snapshot(profile_data)

    question = ""
    try:
        chat_model = llm_client.get_chat_model(temperature=0.7, timeout=30)
        response = await chat_model.ainvoke([
            {
                "role": "system",
                "content": SURVEY_GENERATE_QUESTION_PROMPT.format(
                    round=current_round,
                    total_rounds=_TOTAL_ROUNDS,
                    answers_context=answers_context,
                    profile_snapshot=profile_snapshot,
                ),
            },
            {"role": "user", "content": "请生成本轮摸底问题。"},
        ])
        question = response.content.strip()
    except Exception as exc:
        logger.exception(f"[ProfileAgent] 生成摸底问题失败: {exc}")
        fallback_questions = [
            "你好！我是你的 AI 学习助手。能先跟我聊聊你之前的学习经历吗？比如学过什么，喜欢怎么学？",
            "你觉得自己学新东西快吗？是看一遍就会了，还是需要反复练习？",
            "你一般什么时间学习效率最高？早上、下午、还是晚上？",
            "最后再确认一下——还有没有什么学习习惯想补充的？",
        ]
        idx = min(current_round - 1, len(fallback_questions) - 1)
        question = fallback_questions[idx]

    return {"survey_question": question}


async def analyze_survey_answer(state: ProfileAgentState) -> dict[str, Any]:
    """
    分析摸底回答

    What: 调用 LLM 解析用户对摸底问题的回答，输出画像维度更新和完成状态
    Why: 将自然语言回答转化为结构化的 ProfileDimension 更新
    """
    user_id = state.get("user_id", "")
    survey_answers = state.get("survey_answers") or []
    current_question = state.get("survey_question", "")
    answer = survey_answers[-1] if survey_answers else ""
    current_round = len(survey_answers)

    # 加载当前画像状态
    profile_full = await get_user_profile(user_id)
    profile_data = profile_full.get("profile", {})
    profile_json = json.dumps(profile_data, ensure_ascii=False, indent=2)

    profile_updates = {}
    profile_complete = current_round >= _TOTAL_ROUNDS
    followup_question = None
    reasoning = ""

    try:
        chat_model = llm_client.get_chat_model(temperature=0.5, timeout=30)
        response = await chat_model.ainvoke([
            {
                "role": "system",
                "content": SURVEY_ANALYZE_ANSWER_PROMPT.format(
                    question=current_question,
                    answer=answer,
                    profile_json=profile_json,
                    total_rounds=_TOTAL_ROUNDS,
                ),
            },
            {"role": "user", "content": "请分析上述回答。"},
        ])
        raw = response.content.strip()
        # 移除可能的 markdown 代码块标记（更健壮的去尾处理）
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        parsed = json.loads(raw)
        profile_updates = parsed.get("profile_updates", {})
        profile_complete = parsed.get("profile_complete", profile_complete)
        followup_question = parsed.get("followup_question")
        reasoning = parsed.get("reasoning", "")

        # confidence → confidence_delta 适配转换
        # profile_service._merge_dimension 只认 confidence_delta，
        # 而 LLM 输出的是绝对值 confidence，需在此转换
        if isinstance(profile_updates, dict):
            for dim, dim_val in profile_updates.items():
                if isinstance(dim_val, dict) and "confidence" in dim_val:
                    llm_confidence = float(dim_val.get("confidence", 0))
                    old_entry = profile_data.get(dim)
                    old_confidence = float(old_entry.get("confidence", 0)) if isinstance(old_entry, dict) else 0.0
                    dim_val["confidence_delta"] = _convert_confidence_to_delta(
                        llm_confidence, old_confidence
                    )
                    dim_val.pop("confidence", None)
    except json.JSONDecodeError as exc:
        logger.warning(f"[ProfileAgent] LLM 返回非 JSON 格式: {exc}")
        profile_updates = {}
        followup_question = "谢谢你！还有什么其他学习习惯想分享的吗？"
    except Exception as exc:
        logger.exception(f"[ProfileAgent] 分析摸底回答失败: {exc}")
        profile_updates = {}
        followup_question = "谢谢你！还有什么其他学习习惯想分享的吗？"

    logger.info(
        f"[ProfileAgent] 摸底第{current_round}轮分析完成 "
        f"updates={list(profile_updates.keys())} complete={profile_complete}"
    )

    return {
        "profile": profile_updates,
        "profile_changed": bool(profile_updates),
        "survey_question": followup_question,
        "calibration_result": reasoning,
    }


# ── 审查回路 ─────────────────────────────────────────────────────

async def profile_reviewer(raw_output: dict, user_input: str, context: dict) -> dict:
    """
    Profile Agent 输出质量审查器

    What: 审查 profile_agent 各节点输出的内容质量
    Why: 作为 Agent Loop 中的审查环节，确保画像查询和摸底问答输出符合标准

    Returns:
        dict: {"verdict": "pass"|"fail", "issues": [...], "suggestions": [...]}
    """
    issues = []
    suggestions = []

    if "messages" in raw_output:
        messages = raw_output.get("messages", [])
        if not messages:
            issues.append("输出 messages 为空")
            suggestions.append("确保节点返回有效的 AIMessage 列表")
        else:
            for msg in messages:
                content = ""
                if hasattr(msg, "content"):
                    content = msg.content
                elif isinstance(msg, dict):
                    content = msg.get("content", "")
                if not content or len(content.strip()) < 5:
                    issues.append("回复消息内容为空或过短")
                    suggestions.append("生成更详细的自然语言描述")

    if "survey_question" in raw_output:
        question = raw_output.get("survey_question", "")
        if not question or not question.strip():
            issues.append("摸底问题为空")
            suggestions.append("重新调用 LLM 生成摸底问题")
        elif len(question.strip()) < 5:
            issues.append("摸底问题过短（<5 字符）")
            suggestions.append("生成更自然、更详细的摸底问题")

    verdict = "fail" if issues else "pass"
    return {"verdict": verdict, "issues": issues, "suggestions": suggestions}


async def profile_review_node(state: ProfileAgentState) -> dict[str, Any]:
    """
    Profile Agent 审查网关节点

    What: 收集当前子图执行输出，调用注册的审查器进行质量检查，
          根据结果决定放行或触发重试
    Why: 实现 Agent Loop 中的审查环节，确保 profile_agent 输出质量
    """
    raw_output = {}
    msgs = state.get("messages", [])
    if msgs:
        raw_output["messages"] = [msgs[-1]]
    if state.get("survey_question"):
        raw_output["survey_question"] = state["survey_question"]

    user_input = ""
    for msg in reversed(state.get("messages", [])):
        if hasattr(msg, "content") and getattr(msg, "type", "") == "human":
            user_input = msg.content
            break

    review_attempts = state.get("review_attempts", 0) + 1
    review_max = state.get("review_max_attempts", 3)
    review_results = list(state.get("review_results", []))

    reviewer = get_reviewer("profile_agent")
    if reviewer:
        try:
            result = await reviewer(
                raw_output, user_input,
                {"agent_type": state.get("agent_type", "profile")},
            )
        except Exception as exc:
            logger.warning(f"[ProfileAgent] 审查器执行异常: {exc}")
            result = {"verdict": "pass", "issues": [f"审查器异常: {exc!s}"]}
    else:
        result = {"verdict": "pass", "issues": ["审查器未注册，默认放行"]}

    review_results.append({
        "attempt": review_attempts,
        "verdict": result.get("verdict", "pass"),
        "issues": result.get("issues", []),
        "suggestions": result.get("suggestions", []),
    })

    verdict = result.get("verdict", "pass")
    is_final = verdict == "pass" or review_attempts >= review_max

    if is_final and verdict != "pass":
        logger.info(
            f"[ProfileAgent] 审查未通过但已达重试上限 "
            f"(attempts={review_attempts}/{review_max}, "
            f"issues={result.get('issues', [])})"
        )

    return {
        "raw_agent_output": raw_output,
        "review_attempts": review_attempts,
        "review_results": review_results,
        "review_verdict": "pass" if is_final else "fail",
    }


def review_router(state: ProfileAgentState) -> Literal["retry", "end"]:
    """
    审查结果条件路由

    What: 根据 review_verdict 决定下一步走向
    Why: 作为条件边的路由函数，pass → END, fail → retry
    """
    if state.get("review_verdict", "") == "pass":
        return "end"
    return "retry"


# ── 图构建 ──────────────────────────────────────────────────────

def create_profile_get_graph() -> StateGraph:
    """
    创建画像查询子图：load_profile → format_chat_message → review ⇄ loop

    Loop 流程:
        load_profile → format_chat_message → profile_review
            ├─ pass → END
            └─ fail (未达上限) → retry format_chat_message
    """
    graph = StateGraph(ProfileAgentState)
    graph.add_node("load_profile", load_profile)
    graph.add_node("format_chat_message", format_chat_message)
    graph.add_node("profile_review", profile_review_node)
    graph.add_edge(START, "load_profile")
    graph.add_edge("load_profile", "format_chat_message")
    graph.add_edge("format_chat_message", "profile_review")
    graph.add_conditional_edges(
        "profile_review",
        review_router,
        {"retry": "format_chat_message", "end": END},
    )
    return graph.compile()


def create_profile_survey_graph() -> StateGraph:
    """
    创建摸底问答前半段子图：generate_survey_question → review ⇄ loop

    Loop 流程:
        generate_survey_question → profile_review
            ├─ pass → END
            └─ fail (未达上限) → retry generate_survey_question
    """
    graph = StateGraph(ProfileAgentState)
    graph.add_node("generate_survey_question", generate_survey_question)
    graph.add_node("profile_review", profile_review_node)
    graph.add_edge(START, "generate_survey_question")
    graph.add_edge("generate_survey_question", "profile_review")
    graph.add_conditional_edges(
        "profile_review",
        review_router,
        {"retry": "generate_survey_question", "end": END},
    )
    return graph.compile()


def create_profile_survey_half2_graph() -> StateGraph:
    """创建摸底问答后半段子图：analyze_survey_answer"""
    graph = StateGraph(ProfileAgentState)
    graph.add_node("analyze_survey_answer", analyze_survey_answer)
    graph.add_edge(START, "analyze_survey_answer")
    graph.add_edge("analyze_survey_answer", END)
    return graph.compile()


# ── 便捷调用函数 ─────────────────────────────────────────────────

async def run_profile_get_chat(
    user_id: str,
    session_id: str = "",
) -> dict[str, Any]:
    """
    运行画像查询子图（聊天模式）

    What: 加载画像并格式化为自然语言聊天消息
    Why: 供 Orchestrator 的 profile_agent_node 调用

    Args:
        user_id: 用户 ID
        session_id: 会话 ID（可选）

    Returns:
        dict: 包含 messages 的最终状态
    """
    graph = create_profile_get_graph()
    initial_state: ProfileAgentState = {
        "messages": [],
        "user_id": user_id,
        "plan_id": None,
        "session_id": session_id,
        "agent_type": "profile",
        "tools": [],
        "next": "",
        "action": "get_profile",
        "survey_answers": None,
        "feedback_signal": None,
        "confidence_delta": None,
        "source_session": None,
        "target_dimension": None,
        "user_comment": None,
        "profile": None,
        "survey_question": None,
        "calibration_result": None,
        "profile_changed": None,
        "profile_changelog": None,
    }
    result = await graph.ainvoke(initial_state)
    return result


async def run_survey_first(user_id: str) -> dict[str, Any]:
    """
    启动摸底问答 — 生成第 1 轮问题

    What: 加载画像状态，调用 LLM 生成首轮摸底问题
    Why: 供 GET /api/v1/profile/survey/next 调用

    Args:
        user_id: 用户 ID

    Returns:
        dict: {complete: bool, round: int, total_rounds: int, question: str}
    """
    graph = create_profile_survey_graph()
    initial_state: ProfileAgentState = {
        "messages": [],
        "user_id": user_id,
        "plan_id": None,
        "session_id": "",
        "agent_type": "profile",
        "tools": [],
        "next": "",
        "action": "initial_survey",
        "survey_answers": [],
        "feedback_signal": None,
        "confidence_delta": None,
        "source_session": None,
        "target_dimension": None,
        "user_comment": None,
        "profile": None,
        "survey_question": None,
        "calibration_result": None,
        "profile_changed": None,
        "profile_changelog": None,
    }
    result = await graph.ainvoke(initial_state)

    return {
        "complete": False,
        "round": 1,
        "total_rounds": _TOTAL_ROUNDS,
        "question": result.get("survey_question", ""),
    }


async def run_survey_next(
    user_id: str,
    answer: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """
    处理摸底回答 — 分析答案并决定下一轮

    What: 调用 LLM 解析回答，更新画像；完成则落库，未完成则返回下一题
    Why: 供 POST /api/v1/profile/survey 调用

    Args:
        user_id: 用户 ID
        answer: 用户本轮回答文本
        context: 前序上下文，包含:
            survey_answers: 历史回答列表
            survey_question: 用户正在回答的问题
            round: 当前轮次

    Returns:
        dict: {profile_complete: bool, needs_followup: bool, next_question: str | None}
    """
    previous_answers = list(context.get("survey_answers", []))
    survey_question = context.get("survey_question", "")
    all_answers = previous_answers + [answer]
    current_round = len(all_answers)

    graph = create_profile_survey_half2_graph()
    initial_state: ProfileAgentState = {
        "messages": [],
        "user_id": user_id,
        "plan_id": None,
        "session_id": "",
        "agent_type": "profile",
        "tools": [],
        "next": "",
        "action": "initial_survey",
        "survey_answers": all_answers,
        "feedback_signal": None,
        "confidence_delta": None,
        "source_session": None,
        "target_dimension": None,
        "user_comment": None,
        "profile": None,
        "survey_question": survey_question,
        "calibration_result": None,
        "profile_changed": None,
        "profile_changelog": None,
    }
    result = await graph.ainvoke(initial_state)

    profile_updates = result.get("profile") or {}
    followup_question = result.get("survey_question")
    profile_complete = current_round >= _TOTAL_ROUNDS or not followup_question

    # 如果完成，落库
    if profile_complete and profile_updates:
        await update_profile(user_id, profile_updates)
        logger.info(
            f"[ProfileAgent] 摸底完成，画像已保存 "
            f"(user_id={user_id}, rounds={current_round}, dims={list(profile_updates.keys())})"
        )

    return {
        "profile_complete": profile_complete,
        "needs_followup": not profile_complete,
        "next_question": followup_question if not profile_complete else None,
    }


# ── 审查器注册 ──────────────────────────────────────────────────
from app.agents.review import register_reviewer as _reg

_reg("profile_agent", profile_reviewer)
