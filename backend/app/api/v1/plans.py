"""
学习计划 API 路由

What: 提供创建学习计划的 REST API
Why: 保留直接 API 创建入口，避免与 Orchestrator 双重编排耦合
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.plan_agent import generate_plan_draft
from app.api.deps import get_current_user
from app.core.plan_service import create_plan_from_draft
from app.db.session import get_db
from app.models.knowledge_node import KnowledgeNode
from app.models.user import User
from app.schemas.plan import LearningGoalRequest, PlanNodeResponse, PlanResponse

router = APIRouter(prefix="/plans", tags=["plans"])


@router.post("", response_model=PlanResponse)
async def create_plan(
    body: LearningGoalRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlanResponse:
    """创建学习计划"""

    draft = await generate_plan_draft(body.goal)
    plan = await create_plan_from_draft(db=db, user_id=int(current_user.id), draft=draft)

    result = await db.execute(
        select(KnowledgeNode).where(KnowledgeNode.plan_id == plan.id).order_by(KnowledgeNode.order_index.asc())
    )
    nodes = result.scalars().all()
    node_responses = [
        PlanNodeResponse(
            id=node.id,
            title=node.name,
            description=node.description,
            estimated_minutes=node.estimated_minutes,
            prerequisite_ids=[node.parent_id] if node.parent_id else [],
            order_index=node.order_index,
        )
        for node in nodes
    ]

    return PlanResponse(
        id=plan.id,
        title=plan.title,
        description=plan.description,
        status=plan.status,
        start_date=plan.start_date,
        end_date=plan.end_date,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        nodes=node_responses,
        parsed_goal=draft.parsed_goal,
    )
