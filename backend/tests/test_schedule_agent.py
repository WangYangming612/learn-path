from datetime import date
from pathlib import Path
import sys
from uuid import uuid4

import pytest
from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agents.schedule_agent import run_schedule_graph
from app.core.task_service import get_tasks_by_date
from app.db.session import get_db
from app.models.daily_task import DailyTask
from app.models.knowledge_node import KnowledgeNode
from app.models.plan import Plan
from app.models.user import User


@pytest.mark.asyncio
async def test_schedule_agent_persists_priority_order_and_required_fields():
    suffix = uuid4().hex[:8]
    async for db in get_db():
        user = User(
            username=f"schedule-{suffix}",
            email=f"schedule-{suffix}@example.com",
            hashed_password="test",
        )
        db.add(user)
        await db.flush()

        low_plan = Plan(user_id=user.id, title="low priority", status="active", priority=3)
        high_plan = Plan(user_id=user.id, title="high priority", status="active", priority=1)
        db.add_all([low_plan, high_plan])
        await db.flush()
        db.add_all([
            KnowledgeNode(plan_id=low_plan.id, name="low node", estimated_minutes=50, order_index=1),
            KnowledgeNode(plan_id=high_plan.id, name="high node", estimated_minutes=50, order_index=1),
        ])
        await db.commit()
        user_id = user.id
        high_plan_id = high_plan.id
        low_plan_id = low_plan.id
        break

    result = await run_schedule_graph(str(user_id), daily_budget=60)

    generated = result["schedule_result"]["tasks"]
    task_plan_ids = [task["plan_id"] for task in generated]
    assert task_plan_ids[0] == high_plan_id, f"Expected high(1) first, got plan_ids={task_plan_ids}"

    async for db in get_db():
        tasks = await get_tasks_by_date(db, user_id, date.today())
        task_plan_ids_persisted = [task.plan_id for task in tasks]
        assert task_plan_ids_persisted[0] == high_plan_id, f"Expected high(1) first in DB, got plan_ids={task_plan_ids_persisted}"
        assert sum(task.duration_minutes for task in tasks) == 60
        assert tasks[0].start_time is not None
        assert tasks[0].end_time is not None
        assert tasks[0].guide_content
        assert tasks[0].description is None

        persisted = await db.execute(select(DailyTask).where(DailyTask.id == tasks[0].id))
        stored_task = persisted.scalar_one()
        assert stored_task.start_time == tasks[0].start_time
        assert stored_task.end_time == tasks[0].end_time
        assert stored_task.guide_content == tasks[0].guide_content
        break
