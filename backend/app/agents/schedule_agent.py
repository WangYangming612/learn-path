"""Schedule Agent 子图：协调多个活跃学习计划并生成每日任务。"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.agents.state import AgentState
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
        return str(response.content).strip()
    except Exception as exc:
        logger.warning("[ScheduleAgent] 学习指引生成失败，使用兜底内容: %s", exc)
        return f"用 {duration_minutes} 分钟学习「{node.name}」，梳理核心概念并记录 1 个关键结论；完成后确认自己能用一句话说明该知识点。"


async def schedule_agent_node(state: AgentState) -> dict[str, Any]:
    """LangGraph Schedule 节点入口，读取活跃计划并为当天生成任务。"""

    try:
        user_id = int(state.get("user_id", "0"))
        target_date = state.get("scheduled_date") or date.today()
        if isinstance(target_date, str):
            target_date = date.fromisoformat(target_date)
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
                    "messages": [AIMessage(content="当前没有可排期的活跃学习计划。")],
                    "schedule_result": {"scheduled_date": str(target_date), "tasks": []},
                    "next": "",
                }

            completed_node_result = await db.execute(
                select(DailyTask.knowledge_node_id).where(
                    DailyTask.user_id == user_id,
                    DailyTask.status == "completed",
                    DailyTask.knowledge_node_id.is_not(None),
                )
            )
            completed_node_ids = set(completed_node_result.scalars().all())
            candidates: list[tuple[Plan, KnowledgeNode]] = []
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
                    candidates.append((plan, node))

            requested = [max(node.estimated_minutes or MIN_TASK_MINUTES, MIN_TASK_MINUTES) for _, node in candidates]
            total_requested = sum(requested)
            if total_requested > budget and total_requested:
                durations = [max(MIN_TASK_MINUTES, round(item * budget / total_requested)) for item in requested]
                overflow = sum(durations) - budget
                for index in range(len(durations) - 1, -1, -1):
                    reducible = durations[index] - MIN_TASK_MINUTES
                    reduction = min(reducible, overflow)
                    durations[index] -= reduction
                    overflow -= reduction
                    if overflow <= 0:
                        break
            else:
                durations = requested

            planned_items: list[dict[str, Any]] = []
            cursor = start_at
            remaining = budget
            for (plan, node), duration in zip(candidates, durations):
                if remaining < MIN_TASK_MINUTES:
                    break
                duration = min(duration, remaining)
                end_at = cursor + timedelta(minutes=duration)
                planned_items.append({
                    "plan_id": plan.id,
                    "knowledge_node_id": node.id,
                    "title": f"{plan.title}：{node.name}",
                    "description": node.description,
                    "start_time": cursor.time(),
                    "end_time": end_at.time(),
                    "duration_minutes": duration,
                    "guide_content": await _generate_guide(plan, node, duration),
                })
                cursor = end_at
                remaining -= duration

            created = await create_daily_tasks(db, user_id, planned_items, target_date)
            task_summary = [
                {"task_id": task.id, "plan_id": task.plan_id, "title": task.title, "duration_minutes": task.duration_minutes}
                for task in created
            ]
            return {
                "messages": [AIMessage(content=f"已生成 {len(created)} 个今日学习任务，共 {sum(task.duration_minutes for task in created)} 分钟。")],
                "schedule_result": {"scheduled_date": str(target_date), "tasks": task_summary},
                "next": "",
            }
    except Exception as exc:
        logger.exception("[ScheduleAgent] schedule_agent_node 执行失败: %s", exc)
        return {
            "messages": [AIMessage(content="今日任务生成失败，请稍后重试。")],
            "schedule_result": {"tasks": []},
            "next": "",
        }


def create_schedule_graph():
    """创建 Schedule Agent 单节点子图。"""

    graph = StateGraph(AgentState)
    graph.add_node("schedule", schedule_agent_node)
    graph.add_edge(START, "schedule")
    graph.add_edge("schedule", END)
    return graph.compile()


async def run_schedule_graph(user_id: str, daily_budget: int | None = None, scheduled_date: date | None = None) -> dict[str, Any]:
    """运行 Schedule Agent 子图的便捷入口。"""

    initial_state = {
        "messages": [], "user_id": user_id, "plan_id": None, "session_id": "",
        "agent_type": "schedule", "tools": [], "next": "",
        "daily_budget": daily_budget, "scheduled_date": scheduled_date or date.today(),
    }
    # AgentState 不扩展 Step8 专属字段；直接调用节点以保留 schedule_result，
    # 子图构建函数仍可供 Orchestrator 后续接入。
    return await schedule_agent_node(initial_state)
