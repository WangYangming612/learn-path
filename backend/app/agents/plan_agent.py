"""
Plan Agent 子图模块

What: 解析自然语言学习目标并生成结构化学习路径草稿
Why: 将用户目标转化为可落库的 DAG 学习计划
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError

from app.agents.state import AgentState
from app.core.plan_service import create_plan_from_draft
from app.db.session import get_db
from app.llm.client import llm_client
from app.llm.prompts.plan import PLAN_SYSTEM_PROMPT, PLAN_USER_PROMPT
from app.schemas.plan import KnowledgeNodeDraft, PlanDraft

logger = logging.getLogger(__name__)

_MAX_REVIEW_ATTEMPTS = 3


async def generate_plan_draft(goal: str) -> PlanDraft:
    """使用结构化输出生成计划草稿，并在生成后做结果审核"""

    chat_model = llm_client.get_chat_model(temperature=0.2, timeout=60)
    structured_model = chat_model.with_structured_output(PlanDraft)
    last_error: Exception | None = None

    for attempt in range(1, _MAX_REVIEW_ATTEMPTS + 1):
        try:
            result = await structured_model.ainvoke(
                [
                    {"role": "system", "content": PLAN_SYSTEM_PROMPT},
                    {"role": "user", "content": PLAN_USER_PROMPT.format(goal=goal)},
                ]
            )
            if isinstance(result, PlanDraft):
                draft = result
            else:
                draft = PlanDraft.model_validate(result)

            _review_plan_draft(draft)
            return draft
        except Exception as exc:
            last_error = exc
            logger.warning(
                f"[PlanAgent] 第 {attempt} 轮计划草稿审核失败，准备重试: {exc}"
            )

    logger.warning(f"[PlanAgent] LLM 计划草稿审核多轮失败，使用降级路径: {last_error}")
    fallback = _build_fallback_draft(goal)
    try:
        draft = PlanDraft.model_validate(fallback)
        _review_plan_draft(draft)
        return draft
    except ValidationError:
        raise


def _review_plan_draft(draft: PlanDraft) -> None:
    """对 LLM 输出的计划草稿做基础审核"""

    if not draft.goal_text.strip():
        raise ValueError("goal_text 不能为空")

    if not draft.nodes:
        raise ValueError("nodes 不能为空")

    node_ids = [node.id for node in draft.nodes]
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("节点 ID 不能重复")

    if not draft.parsed_goal.domain.strip():
        raise ValueError("parsed_goal.domain 不能为空")

    if draft.parsed_goal.duration_months < 1:
        raise ValueError("parsed_goal.duration_months 必须大于 0")

    node_map = {node.id: node for node in draft.nodes}
    for node in draft.nodes:
        if not node.title.strip():
            raise ValueError(f"节点 {node.id} 的标题不能为空")
        if node.estimated_minutes < 1:
            raise ValueError(f"节点 {node.id} 的预计时长必须大于 0")
        for prereq in node.prerequisite_ids:
            if prereq not in node_map:
                raise ValueError(f"节点 {node.id} 依赖了不存在的节点 {prereq}")

    _ensure_acyclic(draft.nodes)


def _ensure_acyclic(nodes: list[KnowledgeNodeDraft]) -> None:
    """校验节点依赖是否存在环"""

    indegree: dict[str, int] = {node.id: 0 for node in nodes}
    graph: dict[str, list[str]] = {node.id: [] for node in nodes}

    for node in nodes:
        for prereq in node.prerequisite_ids:
            graph[prereq].append(node.id)
            indegree[node.id] += 1

    queue = deque(sorted(node_id for node_id, degree in indegree.items() if degree == 0))
    visited = 0

    while queue:
        node_id = queue.popleft()
        visited += 1
        for next_id in graph[node_id]:
            indegree[next_id] -= 1
            if indegree[next_id] == 0:
                queue.append(next_id)

    if visited != len(nodes):
        raise ValueError("知识路径存在环，无法通过审核")


def _build_fallback_draft(goal: str) -> dict[str, Any]:
    """简单兜底草稿，避免 LLM 不可用时 API 完全失败"""

    return {
        "goal_text": goal,
        "parsed_goal": {
            "domain": goal[:20] if goal else "学习目标",
            "duration_months": 3,
            "current_level": "beginner",
            "target_depth": "introduction",
        },
        "nodes": [
            {
                "id": "n1",
                "title": "基础入门",
                "description": "理解该领域的基础概念与核心术语",
                "estimated_minutes": 300,
                "prerequisite_ids": [],
            },
            {
                "id": "n2",
                "title": "核心技能",
                "description": "掌握该领域最重要的实践技能",
                "estimated_minutes": 420,
                "prerequisite_ids": ["n1"],
            },
            {
                "id": "n3",
                "title": "综合应用",
                "description": "通过项目或案例整合所学知识",
                "estimated_minutes": 360,
                "prerequisite_ids": ["n2"],
            },
        ],
    }


async def plan_agent_node(state: AgentState) -> dict[str, Any]:
    """
    LangGraph Plan 节点入口

    What: 从 AgentState 读取学习目标，生成计划草稿并落库
    Why: 让 Plan 能直接接入现有 Orchestrator 图流程
    """
    goal_text = ""
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            goal_text = str(msg.content).strip()
            break

    if not goal_text:
        goal_text = "学习一个新主题"

    try:
        draft = await generate_plan_draft(goal_text)
        user_id = state.get("user_id", "0")

        async for db in get_db():
            plan = await create_plan_from_draft(
                db=db,
                user_id=int(user_id),
                draft=draft,
            )

            result_msg = AIMessage(
                content=(
                    f"已为你生成学习计划：{plan.title}。"
                    f" 计划包含 {len(draft.nodes)} 个知识节点。"
                )
            )

            return {
                "messages": [result_msg],
                "parsed_goal": draft.parsed_goal.model_dump(),
                "plan_result": {
                    "plan_id": plan.id,
                    "title": plan.title,
                    "status": plan.status,
                },
                "plan_id": str(plan.id),
                "next": "",
            }
    except Exception as exc:
        logger.error(f"[PlanAgent] plan_agent_node 执行失败: {exc}")
        return {
            "messages": [AIMessage(content="学习计划生成失败，请稍后重试。")],
            "next": "",
        }
