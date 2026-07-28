"""
Schedule Agent 子图：协调多个活跃学习计划并生成每日任务。

架构说明：
  子图（含审查 loop + 落库）：
      START → load_context → generate_schedule → schedule_review
          ├─ pass → persist_schedule → END
          └─ fail (未达上限) → retry generate_schedule
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Literal

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.agents.review import get_reviewer, register_reviewer
from app.agents.state import ScheduleAgentState
from app.core.profile_service import get_user_profile
from app.core.task_service import create_daily_tasks
from app.db.session import get_db
from app.llm.client import llm_client
from app.llm.prompts.schedule import SCHEDULE_GUIDE_SYSTEM_PROMPT, SCHEDULE_GUIDE_USER_PROMPT
from app.models.daily_task import DailyTask
from app.models.knowledge_node import KnowledgeNode
from app.models.plan import Plan

logger = logging.getLogger(__name__)
DEFAULT_DAILY_BUDGET = 60
MIN_TASK_MINUTES = 5
MAX_REVIEW_ATTEMPTS = 3
_REQUIRED_GUIDE_SECTIONS = ("## 重点理解", "## 建议练习", "## 搜索关键词")


def _profile_value(profile: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = profile.get(key)
        if isinstance(value, dict):
            value = value.get("label", value.get("value"))
        if value not in (None, "", "未知"):
            return value
    return None


def _daily_budget(profile: dict[str, Any], supplied_budget: int | None) -> int:
    if supplied_budget:
        return supplied_budget
    value = _profile_value(profile, "daily_budget", "daily_available_minutes")
    try:
        return max(int(value), MIN_TASK_MINUTES)
    except (TypeError, ValueError):
        return DEFAULT_DAILY_BUDGET


def _preferred_start(profile: dict[str, Any]) -> time:
    value = str(_profile_value(profile, "best_time_slots", "best_time", "time_preference") or "")
    if "早" in value or "morning" in value.lower():
        return time(8, 0)
    if "午" in value or "afternoon" in value.lower():
        return time(14, 0)
    if "晚" in value or "night" in value.lower() or "evening" in value.lower():
        return time(19, 0)
    return time(19, 0)


def _plan_priority(plan: Plan) -> int:
    """返回持久化计划优先级，异常值按中优先级处理。"""

    try:
        priority = int(plan.priority)
    except (TypeError, ValueError):
        priority = 2
    return priority if priority in (1, 2, 3) else 2


def _fallback_guide(node_name: str, duration_minutes: int, node_description: str | None = None) -> str:
    """LLM 不可用时的 Markdown 学习指引兜底。"""

    focus = (node_description or "").strip() or f"「{node_name}」的核心概念与适用场景"
    return (
        f"## 重点理解\n"
        f"{focus}\n\n"
        f"## 建议练习\n"
        f"- 用 {duration_minutes} 分钟精读并整理 3 条要点\n"
        f"- 完成后用一句话向自己复述该知识点\n\n"
        f"## 搜索关键词\n"
        f"{node_name}, 入门, 练习"
    )


async def _generate_guide(plan: Plan, node: KnowledgeNode, duration_minutes: int) -> str:
    try:
        chat_model = llm_client.get_chat_model(temperature=0.4, timeout=30)
        response = await chat_model.ainvoke([
            {"role": "system", "content": SCHEDULE_GUIDE_SYSTEM_PROMPT},
            {"role": "user", "content": SCHEDULE_GUIDE_USER_PROMPT.format(
                plan_title=plan.title,
                node_name=node.name,
                duration_minutes=duration_minutes,
                node_description=node.description or "无",
            )},
        ])
        content = str(response.content).strip()
        if content:
            return content
        return _fallback_guide(node.name, duration_minutes, node.description)
    except Exception as exc:
        logger.warning("[ScheduleAgent] 学习指引生成失败，使用兜底内容: %s", exc)
        return _fallback_guide(node.name, duration_minutes, node.description)


def _parse_target_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and value:
        return date.fromisoformat(value)
    return date.today()


def _empty_schedule_result(target_date: date) -> dict[str, Any]:
    return {
        "scheduled_date": str(target_date),
        "tasks": [],
        "total_minutes": 0,
        "overflow_detected": False,
    }


def _compress_durations(requested: list[int], budget: int) -> tuple[list[int], bool]:
    """按预算比例压缩时长，必要时从末尾再削到不超预算。"""

    total_requested = sum(requested)
    overflow_detected = bool(total_requested > budget and total_requested)
    if not overflow_detected:
        return requested, False

    durations = [max(MIN_TASK_MINUTES, round(item * budget / total_requested)) for item in requested]
    overflow = sum(durations) - budget
    for index in range(len(durations) - 1, -1, -1):
        reducible = durations[index] - MIN_TASK_MINUTES
        reduction = min(reducible, overflow)
        durations[index] -= reduction
        overflow -= reduction
        if overflow <= 0:
            break
    return durations, True


# ── 审查回路 ─────────────────────────────────────────────────────

def _collect_review_issues(planned_items: list[dict[str, Any]], budget: int) -> tuple[list[str], list[str]]:
    """收集排期草案问题与修改建议。"""

    issues: list[str] = []
    suggestions: list[str] = []

    if budget < MIN_TASK_MINUTES:
        issues.append("可用预算不足")
        suggestions.append(f"将 daily_budget 提升到至少 {MIN_TASK_MINUTES} 分钟")

    if not planned_items:
        issues.append("排期结果不能为空")
        suggestions.append("确保存在可排期的活跃计划与知识节点")
        return issues, suggestions

    total_duration = 0
    previous_end: time | None = None
    seen_pairs: set[tuple[Any, Any]] = set()

    for index, item in enumerate(planned_items):
        plan_id = item.get("plan_id")
        knowledge_node_id = item.get("knowledge_node_id")
        start_time = item.get("start_time")
        end_time = item.get("end_time")
        duration_minutes = item.get("duration_minutes")
        guide_content = str(item.get("guide_content") or "").strip()

        if plan_id is None:
            issues.append(f"任务[{index}]缺少 plan_id")
            suggestions.append(f"为任务[{index}]补充所属计划")
        if duration_minutes is None or int(duration_minutes) < MIN_TASK_MINUTES:
            issues.append(f"任务[{index}]时长过短")
            suggestions.append(f"将任务[{index}]时长调整到至少 {MIN_TASK_MINUTES} 分钟")
        if not guide_content:
            issues.append(f"任务[{index}]指引不能为空")
            suggestions.append(f"为任务[{index}]重新生成学习指引")
        else:
            missing = [section for section in _REQUIRED_GUIDE_SECTIONS if section not in guide_content]
            if missing:
                issues.append(f"任务[{index}]指引缺少小节: {', '.join(missing)}")
                suggestions.append(f"任务[{index}]指引需包含重点理解 / 建议练习 / 搜索关键词")
        if start_time is None or end_time is None:
            issues.append(f"任务[{index}]时间段不能为空")
            suggestions.append(f"为任务[{index}]补全 start_time / end_time")
        elif previous_end is not None and start_time < previous_end:
            issues.append(f"任务[{index}]时间段与前序任务重叠")
            suggestions.append("按顺序重排时间段，避免重叠")
        if (plan_id, knowledge_node_id) in seen_pairs:
            issues.append(f"任务[{index}]重复排期")
            suggestions.append("同一计划-知识点组合只排一次")

        seen_pairs.add((plan_id, knowledge_node_id))
        if end_time is not None:
            previous_end = end_time
        if duration_minutes is not None:
            total_duration += int(duration_minutes)

    if total_duration > budget:
        issues.append("任务总时长超过可用预算")
        suggestions.append("按优先级压缩任务时长或减少任务数量")

    return issues, suggestions


async def schedule_reviewer(raw_output: dict, user_input: str, context: dict) -> dict:
    """
    Schedule Agent 输出质量审查器

    What: 审查排期草案的预算、时段、去重与指引结构
    Why: 作为 Agent Loop 中的审查环节，防止写入无效排期
    """
    del user_input  # 排期审查不依赖用户原话
    planned_items = list(raw_output.get("planned_items") or [])
    budget = int(context.get("budget") or raw_output.get("budget") or DEFAULT_DAILY_BUDGET)
    issues, suggestions = _collect_review_issues(planned_items, budget)
    return {
        "verdict": "fail" if issues else "pass",
        "issues": issues,
        "suggestions": suggestions,
    }


async def schedule_review_node(state: ScheduleAgentState) -> dict[str, Any]:
    """
    Schedule Agent 审查网关节点

    What: 调用注册的审查器检查 planned_items，决定放行或重试
    Why: 实现 Agent Loop 中的审查环节
    """
    if state.get("skip_reason"):
        return {
            "raw_agent_output": {"skipped": True, "reason": state.get("skip_reason")},
            "review_attempts": state.get("review_attempts", 0),
            "review_results": list(state.get("review_results", [])),
            "review_verdict": "pass",
        }

    context = state.get("schedule_context") or {}
    planned_items = list(state.get("planned_items") or [])
    raw_output = {
        "planned_items": planned_items,
        "budget": context.get("budget", DEFAULT_DAILY_BUDGET),
        "overflow_detected": bool(state.get("overflow_detected", False)),
    }

    review_attempts = state.get("review_attempts", 0) + 1
    review_max = state.get("review_max_attempts", MAX_REVIEW_ATTEMPTS)
    review_results = list(state.get("review_results", []))

    reviewer = get_reviewer("schedule_agent")
    if reviewer:
        try:
            result = await reviewer(
                raw_output,
                "",
                {
                    "agent_type": state.get("agent_type", "schedule"),
                    "budget": raw_output["budget"],
                },
            )
        except Exception as exc:
            logger.warning("[ScheduleAgent] 审查器执行异常: %s", exc)
            result = {"verdict": "pass", "issues": [f"审查器异常: {exc!s}"], "suggestions": []}
    else:
        result = {"verdict": "pass", "issues": ["审查器未注册，默认放行"], "suggestions": []}

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
            "[ScheduleAgent] 审查未通过但已达重试上限 "
            "(attempts=%s/%s, issues=%s)",
            review_attempts,
            review_max,
            result.get("issues", []),
        )

    return {
        "raw_agent_output": raw_output,
        "review_attempts": review_attempts,
        "review_results": review_results,
        "review_verdict": "pass" if is_final else "fail",
    }


def review_router(state: ScheduleAgentState) -> Literal["retry", "end"]:
    """根据 review_verdict 决定重试生成或进入落库。"""

    if state.get("review_verdict", "") == "pass":
        return "end"
    return "retry"


# ── 子图节点 ─────────────────────────────────────────────────────

async def load_schedule_context(state: ScheduleAgentState) -> dict[str, Any]:
    """加载用户预算、活跃计划与可排期知识节点。"""

    try:
        user_id = int(state.get("user_id", "0"))
        target_date = _parse_target_date(state.get("scheduled_date"))
        profile = await get_user_profile(str(user_id))
        budget = _daily_budget(profile, state.get("daily_budget"))
        start_at = datetime.combine(target_date, _preferred_start(profile))

        async for db in get_db():
            from app.models.user import User

            user_result = await db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()
            if state.get("daily_budget") is None and user:
                budget = max(user.daily_available_minutes, MIN_TASK_MINUTES)

            plans_result = await db.execute(
                select(Plan).where(Plan.user_id == user_id, Plan.status == "active")
            )
            plans = sorted(plans_result.scalars().all(), key=lambda plan: (_plan_priority(plan), plan.id))
            if not plans:
                return {
                    "scheduled_date": target_date,
                    "skip_reason": "当前没有可排期的活跃学习计划。",
                    "schedule_context": None,
                    "planned_items": [],
                    "overflow_detected": False,
                    "schedule_result": _empty_schedule_result(target_date),
                    "messages": [AIMessage(content="当前没有可排期的活跃学习计划。")],
                    "review_attempts": 0,
                }

            completed_node_result = await db.execute(
                select(DailyTask.knowledge_node_id).where(
                    DailyTask.user_id == user_id,
                    DailyTask.status == "completed",
                    DailyTask.knowledge_node_id.is_not(None),
                )
            )
            completed_node_ids = set(completed_node_result.scalars().all())
            candidates: list[dict[str, Any]] = []
            for plan in plans:
                node_result = await db.execute(
                    select(KnowledgeNode)
                    .where(KnowledgeNode.plan_id == plan.id)
                    .order_by(KnowledgeNode.order_index.asc(), KnowledgeNode.id.asc())
                )
                node = next(
                    (item for item in node_result.scalars().all() if item.id not in completed_node_ids),
                    None,
                )
                if node:
                    candidates.append({
                        "plan_id": plan.id,
                        "plan_title": plan.title,
                        "node_id": node.id,
                        "node_name": node.name,
                        "node_description": node.description,
                        "estimated_minutes": max(node.estimated_minutes or MIN_TASK_MINUTES, MIN_TASK_MINUTES),
                    })

            if not candidates:
                return {
                    "scheduled_date": target_date,
                    "skip_reason": "当前活跃计划暂无可排期的知识节点。",
                    "schedule_context": None,
                    "planned_items": [],
                    "overflow_detected": False,
                    "schedule_result": _empty_schedule_result(target_date),
                    "messages": [AIMessage(content="当前活跃计划暂无可排期的知识节点。")],
                    "review_attempts": 0,
                }

            requested = [item["estimated_minutes"] for item in candidates]
            durations, overflow_detected = _compress_durations(requested, budget)
            return {
                "scheduled_date": target_date,
                "skip_reason": None,
                "overflow_detected": overflow_detected,
                "planned_items": [],
                "schedule_result": None,
                "review_attempts": 0,
                "review_results": [],
                "review_verdict": "",
                "schedule_context": {
                    "user_id": user_id,
                    "budget": budget,
                    "start_at": start_at.isoformat(),
                    "candidates": candidates,
                    "durations": durations,
                },
            }
    except Exception as exc:
        logger.exception("[ScheduleAgent] load_schedule_context 失败: %s", exc)
        target_date = _parse_target_date(state.get("scheduled_date"))
        return {
            "scheduled_date": target_date,
            "skip_reason": "今日任务生成失败，请稍后重试。",
            "schedule_context": None,
            "planned_items": [],
            "overflow_detected": False,
            "schedule_result": {"tasks": []},
            "messages": [AIMessage(content="今日任务生成失败，请稍后重试。")],
            "review_attempts": 0,
        }


async def generate_schedule(state: ScheduleAgentState) -> dict[str, Any]:
    """根据上下文生成排期草案（含学习指引），不落库。"""

    if state.get("skip_reason"):
        return {}

    context = state.get("schedule_context") or {}
    candidates = list(context.get("candidates") or [])
    durations = list(context.get("durations") or [])
    budget = int(context.get("budget") or DEFAULT_DAILY_BUDGET)
    start_at = datetime.fromisoformat(str(context["start_at"]))

    planned_items: list[dict[str, Any]] = []
    cursor = start_at
    remaining = budget

    # 重试用轻量兜底指引，避免审查循环反复打 LLM
    use_fallback_guide = int(state.get("review_attempts", 0) or 0) > 0

    async for db in get_db():
        for candidate, duration in zip(candidates, durations):
            if remaining < MIN_TASK_MINUTES:
                break
            duration = min(int(duration), remaining)
            end_at = cursor + timedelta(minutes=duration)

            plan = await db.get(Plan, candidate["plan_id"])
            node = await db.get(KnowledgeNode, candidate["node_id"])
            if plan is None or node is None:
                continue

            if use_fallback_guide:
                guide = _fallback_guide(node.name, duration, node.description)
            else:
                guide = await _generate_guide(plan, node, duration)

            planned_items.append({
                "plan_id": plan.id,
                "knowledge_node_id": node.id,
                "title": f"{plan.title}：{node.name}",
                "description": node.description,
                "start_time": cursor.time(),
                "end_time": end_at.time(),
                "duration_minutes": duration,
                "guide_content": guide,
            })
            cursor = end_at
            remaining -= duration
        break

    return {"planned_items": planned_items}


async def persist_schedule(state: ScheduleAgentState) -> dict[str, Any]:
    """审查通过（或达上限）后将排期写入数据库。"""

    if state.get("skip_reason"):
        return {
            "schedule_result": state.get("schedule_result") or {"tasks": []},
            "next": "",
        }

    context = state.get("schedule_context") or {}
    user_id = int(context.get("user_id") or state.get("user_id") or 0)
    target_date = _parse_target_date(state.get("scheduled_date"))
    planned_items = list(state.get("planned_items") or [])
    overflow_detected = bool(state.get("overflow_detected", False))

    try:
        async for db in get_db():
            created = await create_daily_tasks(db, user_id, planned_items, target_date)
            total_minutes = sum(task.duration_minutes for task in created)
            task_summary = [
                {
                    "task_id": task.id,
                    "plan_id": task.plan_id,
                    "title": task.title,
                    "duration_minutes": task.duration_minutes,
                    "guide_content": task.guide_content,
                    "start_time": task.start_time.strftime("%H:%M") if task.start_time else None,
                    "end_time": task.end_time.strftime("%H:%M") if task.end_time else None,
                }
                for task in created
            ]
            return {
                "messages": [AIMessage(content=f"已生成 {len(created)} 个今日学习任务，共 {total_minutes} 分钟。")],
                "schedule_result": {
                    "scheduled_date": str(target_date),
                    "tasks": task_summary,
                    "total_minutes": total_minutes,
                    "overflow_detected": overflow_detected,
                },
                "next": "",
            }
    except Exception as exc:
        logger.exception("[ScheduleAgent] persist_schedule 失败: %s", exc)
        return {
            "messages": [AIMessage(content="今日任务生成失败，请稍后重试。")],
            "schedule_result": {"tasks": []},
            "next": "",
        }


def create_schedule_graph():
    """
    创建 Schedule Agent 子图

    Loop 流程:
        load_context → generate_schedule → schedule_review
            ├─ pass → persist_schedule → END
            └─ fail (未达上限) → retry generate_schedule
    """

    graph = StateGraph(ScheduleAgentState)
    graph.add_node("load_context", load_schedule_context)
    graph.add_node("generate_schedule", generate_schedule)
    graph.add_node("schedule_review", schedule_review_node)
    graph.add_node("persist_schedule", persist_schedule)
    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "generate_schedule")
    graph.add_edge("generate_schedule", "schedule_review")
    graph.add_conditional_edges(
        "schedule_review",
        review_router,
        {"retry": "generate_schedule", "end": "persist_schedule"},
    )
    graph.add_edge("persist_schedule", END)
    return graph.compile()


async def run_schedule_graph(
    user_id: str,
    daily_budget: int | None = None,
    scheduled_date: date | None = None,
) -> dict[str, Any]:
    """运行 Schedule Agent 子图的便捷入口。"""

    graph = create_schedule_graph()
    initial_state: ScheduleAgentState = {
        "messages": [],
        "user_id": user_id,
        "plan_id": None,
        "session_id": "",
        "agent_type": "schedule",
        "tools": [],
        "next": "",
        "parsed_goal": None,
        "plan_result": None,
        "execution_plan": [],
        "execution_index": 0,
        "step_results": {},
        "orchestration_warnings": [],
        "review_attempts": 0,
        "review_max_attempts": MAX_REVIEW_ATTEMPTS,
        "review_results": [],
        "raw_agent_output": None,
        "review_verdict": "",
        "daily_budget": daily_budget,
        "scheduled_date": scheduled_date or date.today(),
        "schedule_context": None,
        "planned_items": [],
        "schedule_result": None,
        "overflow_detected": False,
        "skip_reason": None,
    }
    return await graph.ainvoke(initial_state)


# 兼容旧入口：单节点包装（供外部若仍引用 schedule_agent_node）
async def schedule_agent_node(state: dict[str, Any]) -> dict[str, Any]:
    """兼容旧调用：将扁平状态交给完整子图执行。"""

    return await run_schedule_graph(
        user_id=str(state.get("user_id", "0")),
        daily_budget=state.get("daily_budget"),
        scheduled_date=_parse_target_date(state.get("scheduled_date")),
    )


register_reviewer("schedule_agent", schedule_reviewer)
