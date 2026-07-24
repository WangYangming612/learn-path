"""
学习计划服务模块

What: 负责计划拓扑排序、画像自适应调整和 ORM 持久化
Why: 将 LLM 生成结果转为可落库、可重算的结构化计划
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.profile_service import get_user_profile
from app.models.knowledge_node import KnowledgeNode
from app.models.plan import Plan
from app.schemas.plan import KnowledgeNodeDraft, ParsedLearningGoal, PlanDraft


@dataclass(slots=True)
class OrderedDraftNode:
    temp_id: str
    draft: KnowledgeNodeDraft
    order_index: int


def _normalize_profile_value(profile: dict[str, Any], key: str) -> str:
    value = profile.get(key, "")
    if isinstance(value, dict):
        return str(value.get("label") or value.get("value") or "")
    return str(value or "")


def adjust_estimated_minutes(base_minutes: int, profile: dict[str, Any]) -> int:
    """根据用户画像调整学习时长"""

    rhythm = _normalize_profile_value(profile, "learning_rhythm")
    factor = 1.0

    if rhythm == "稳健型":
        factor = 1.3
    elif rhythm == "冲刺型":
        factor = 0.8
    elif rhythm == "间歇型":
        factor = 1.2

    adjusted = int(round(base_minutes * factor))
    return max(adjusted, 10)


def topological_sort_nodes(nodes: list[KnowledgeNodeDraft]) -> list[OrderedDraftNode]:
    """根据 prerequisite_ids 对节点进行拓扑排序"""

    node_map = {node.id: node for node in nodes}
    indegree: dict[str, int] = {node.id: 0 for node in nodes}
    graph: dict[str, list[str]] = defaultdict(list)

    for node in nodes:
        for prereq in node.prerequisite_ids:
            if prereq not in node_map:
                raise ValueError(f"节点 {node.id} 依赖了不存在的前置节点: {prereq}")
            graph[prereq].append(node.id)
            indegree[node.id] += 1

    queue = deque(sorted([node_id for node_id, deg in indegree.items() if deg == 0]))
    ordered: list[OrderedDraftNode] = []
    order_index = 1

    while queue:
        node_id = queue.popleft()
        ordered.append(OrderedDraftNode(temp_id=node_id, draft=node_map[node_id], order_index=order_index))
        order_index += 1
        for next_id in graph[node_id]:
            indegree[next_id] -= 1
            if indegree[next_id] == 0:
                queue.append(next_id)

    if len(ordered) != len(nodes):
        raise ValueError("知识路径存在环，无法生成 DAG")

    return ordered


async def create_plan_from_draft(
    db: AsyncSession,
    user_id: int,
    draft: PlanDraft,
) -> Plan:
    """将 LLM 草稿保存为 Plan + KnowledgeNode"""

    profile = await get_user_profile(str(user_id))
    ordered_nodes = topological_sort_nodes(draft.nodes)

    parsed_goal = draft.parsed_goal
    title = parsed_goal.domain
    description = f"{parsed_goal.duration_months}个月学习目标：{draft.goal_text}"

    today = date.today()
    start_date = today
    end_date = today + timedelta(days=max(parsed_goal.duration_months * 30, 1))

    plan = Plan(
        user_id=user_id,
        title=title,
        description=description,
        status="active",
        start_date=start_date,
        end_date=end_date,
    )
    db.add(plan)
    await db.flush()

    temp_to_real_id: dict[str, int] = {}
    created_rows: list[KnowledgeNode] = []

    for ordered in ordered_nodes:
        node_draft = ordered.draft
        adjusted_minutes = adjust_estimated_minutes(node_draft.estimated_minutes, profile)

        prerequisite_real_ids = [temp_to_real_id[pid] for pid in node_draft.prerequisite_ids if pid in temp_to_real_id]
        parent_id = prerequisite_real_ids[0] if prerequisite_real_ids else None

        node = KnowledgeNode(
            plan_id=plan.id,
            parent_id=parent_id,
            name=node_draft.title,
            description=node_draft.description,
            difficulty=_infer_difficulty(node_draft.title),
            estimated_minutes=adjusted_minutes,
            mastery_level=0.0,
            order_index=ordered.order_index,
        )
        db.add(node)
        await db.flush()

        temp_to_real_id[ordered.temp_id] = node.id
        created_rows.append(node)

    await db.commit()
    await db.refresh(plan)
    return plan


def _infer_difficulty(title: str) -> int:
    lower = title.lower()
    if any(keyword in lower for keyword in ["基础", "入门", "intro"]):
        return 1
    if any(keyword in lower for keyword in ["进阶", "应用", "实践"]):
        return 3
    if any(keyword in lower for keyword in ["深度", "高级", "原理"]):
        return 4
    return 2


async def rebuild_plan_topology(db: AsyncSession, plan_id: int) -> None:
    """预留：基于现有节点重新计算拓扑顺序"""

    result = await db.execute(
        select(KnowledgeNode).where(KnowledgeNode.plan_id == plan_id)
    )
    nodes = list(result.scalars().all())
    if not nodes:
        return

    # 当前阶段仅预留接口，后续可加入 skip/prioritize 逻辑
    nodes.sort(key=lambda n: (n.parent_id is not None, n.id))
    for index, node in enumerate(nodes, start=1):
        node.order_index = index
    await db.commit()
