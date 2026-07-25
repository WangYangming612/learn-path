from pathlib import Path
import sys

import pytest
from langchain_core.messages import HumanMessage
from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agents.plan_agent import plan_agent_node
from app.agents.state import create_initial_state
from app.db.session import get_db
from app.models.knowledge_node import KnowledgeNode
from app.models.plan import Plan


@pytest.mark.asyncio
async def test_plan_agent_node_creates_plan_and_nodes():
    state = create_initial_state(
        user_id="1",
        session_id="test-plan-agent",
        messages=[HumanMessage(content="我想3个月入门Python人工智能")],
        agent_type="plan",
    )

    result = await plan_agent_node(state)

    assert "plan_result" in result
    assert "plan_id" in result
    assert result["plan_result"]["plan_id"] == int(result["plan_id"])

    plan_id = int(result["plan_id"])

    async for db in get_db():
        plan_result = await db.execute(select(Plan).where(Plan.id == plan_id))
        plan = plan_result.scalar_one_or_none()
        assert plan is not None

        node_result = await db.execute(select(KnowledgeNode).where(KnowledgeNode.plan_id == plan_id))
        nodes = node_result.scalars().all()
        assert len(nodes) > 0
        assert all(node.estimated_minutes > 0 for node in nodes)
        assert all(node.order_index > 0 for node in nodes)
        break
