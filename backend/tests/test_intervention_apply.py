"""
Intervention Agent apply_intervention 测试

覆盖:
  - adjust_priority: Plan.priority 修改落库
  - pause_plan: Plan.status → "paused"
  - add_prerequisite: KnowledgeNode 新增
  - adjust_minutes: KnowledgeNode.estimated_minutes 修改
  - 异常处理: 无效 plan_id 不崩溃
  - 空 actions 不崩溃
"""

import pytest


def _seed_plan(db, user_id: int):
    """在测试 DB 中创建活跃计划 + 3 个知识节点，返回 plan"""
    from app.models.plan import Plan
    from app.models.knowledge_node import KnowledgeNode

    plan = Plan(
        user_id=user_id,
        title="测试计划",
        status="active",
        priority=2,
    )
    db.add(plan)
    return plan


async def _seed_plan_async(db, user_id: int):
    """异步版本：在测试 DB 中创建活跃计划 + 3 个知识节点，返回 plan"""
    from app.models.plan import Plan
    from app.models.knowledge_node import KnowledgeNode

    plan = Plan(
        user_id=user_id,
        title="测试计划",
        status="active",
        priority=2,
    )
    db.add(plan)
    await db.flush()

    nodes = [
        KnowledgeNode(plan_id=plan.id, name="节点1", estimated_minutes=30, order_index=1),
        KnowledgeNode(plan_id=plan.id, name="节点2", estimated_minutes=45, order_index=2),
        KnowledgeNode(plan_id=plan.id, name="节点3", estimated_minutes=60, order_index=3),
    ]
    db.add_all(nodes)
    await db.commit()
    return plan


class TestAdjustPriority:
    """adjust_priority 动作"""

    @pytest.mark.asyncio
    async def test_adjust_priority_updates_db(self):
        from app.agents.intervention_agent import apply_intervention
        from app.agents.state import AgentState
        from app.db.session import get_db as _get_db
        from app.models.plan import Plan
        from sqlalchemy import select

        # seed
        async for db in _get_db():
            from app.models.user import User
            user = User(username="test-adj-pri", email="adj-pri@t.com", hashed_password="x")
            db.add(user)
            await db.flush()
            plan = await _seed_plan_async(db, user.id)
            plan_id = plan.id
            break

        state: AgentState = {
            "messages": [], "user_id": str(user.id), "plan_id": str(plan_id),
            "session_id": "", "agent_type": "intervention", "tools": [], "next": "",
            "parsed_goal": None, "plan_result": None,
            "execution_plan": [], "execution_index": 0,
            "step_results": {}, "orchestration_warnings": [],
            "review_attempts": 0, "review_max_attempts": 3,
            "review_results": [], "raw_agent_output": None, "review_verdict": "",
            "intervention_actions": [
                {"type": "adjust_priority", "target": "提升", "reason": "重要",
                 "priority": 1, "params": {"new_priority": 1}}
            ],
            "intervention_summary": "优先级调整",
        }

        result = await apply_intervention(state)
        applied = result.get("intervention_applied", [])
        assert len(applied) == 1
        assert applied[0]["type"] == "adjust_priority"

        async for db in _get_db():
            db_plan = await db.get(Plan, plan_id)
            assert db_plan is not None
            assert db_plan.priority == 1
            break

    @pytest.mark.asyncio
    async def test_adjust_priority_clamps_to_valid_range(self):
        from app.agents.intervention_agent import apply_intervention
        from app.agents.state import AgentState
        from app.db.session import get_db as _get_db
        from app.models.plan import Plan

        async for db in _get_db():
            from app.models.user import User
            user = User(username="test-clamp", email="clamp@t.com", hashed_password="x")
            db.add(user)
            await db.flush()
            plan = await _seed_plan_async(db, user.id)
            plan_id = plan.id
            break

        state: AgentState = {
            "messages": [], "user_id": str(user.id), "plan_id": str(plan_id),
            "session_id": "", "agent_type": "intervention", "tools": [], "next": "",
            "parsed_goal": None, "plan_result": None,
            "execution_plan": [], "execution_index": 0,
            "step_results": {}, "orchestration_warnings": [],
            "review_attempts": 0, "review_max_attempts": 3,
            "review_results": [], "raw_agent_output": None, "review_verdict": "",
            "intervention_actions": [
                {"type": "adjust_priority", "target": "提升", "reason": "测试",
                 "priority": 2, "params": {"new_priority": 99}}
            ],
            "intervention_summary": "clamp测试",
        }

        result = await apply_intervention(state)
        assert len(result.get("intervention_applied", [])) == 1

        async for db in _get_db():
            db_plan = await db.get(Plan, plan_id)
            assert db_plan.priority == 3  # clamped to max 3
            break


class TestPausePlan:
    """pause_plan 动作"""

    @pytest.mark.asyncio
    async def test_pause_plan_sets_status(self):
        from app.agents.intervention_agent import apply_intervention
        from app.agents.state import AgentState
        from app.db.session import get_db as _get_db
        from app.models.plan import Plan

        async for db in _get_db():
            from app.models.user import User
            user = User(username="test-pause", email="pause@t.com", hashed_password="x")
            db.add(user)
            await db.flush()
            plan = await _seed_plan_async(db, user.id)
            plan_id = plan.id
            break

        assert plan.status == "active"

        state: AgentState = {
            "messages": [], "user_id": str(user.id), "plan_id": str(plan_id),
            "session_id": "", "agent_type": "intervention", "tools": [], "next": "",
            "parsed_goal": None, "plan_result": None,
            "execution_plan": [], "execution_index": 0,
            "step_results": {}, "orchestration_warnings": [],
            "review_attempts": 0, "review_max_attempts": 3,
            "review_results": [], "raw_agent_output": None, "review_verdict": "",
            "intervention_actions": [
                {"type": "pause_plan", "target": "暂停", "reason": "困难",
                 "priority": 1, "params": {}}
            ],
            "intervention_summary": "暂停",
        }

        result = await apply_intervention(state)
        assert len(result.get("intervention_applied", [])) == 1

        async for db in _get_db():
            db_plan = await db.get(Plan, plan_id)
            assert db_plan.status == "paused"
            break


class TestAddPrerequisite:
    """add_prerequisite 动作"""

    @pytest.mark.asyncio
    async def test_add_prerequisite_creates_node(self):
        from app.agents.intervention_agent import apply_intervention
        from app.agents.state import AgentState
        from app.db.session import get_db as _get_db
        from app.models.knowledge_node import KnowledgeNode
        from sqlalchemy import select

        async for db in _get_db():
            from app.models.user import User
            user = User(username="test-addpre", email="addpre@t.com", hashed_password="x")
            db.add(user)
            await db.flush()
            plan = await _seed_plan_async(db, user.id)
            plan_id = plan.id
            break

        state: AgentState = {
            "messages": [], "user_id": str(user.id), "plan_id": str(plan_id),
            "session_id": "", "agent_type": "intervention", "tools": [], "next": "",
            "parsed_goal": None, "plan_result": None,
            "execution_plan": [], "execution_index": 0,
            "step_results": {}, "orchestration_warnings": [],
            "review_attempts": 0, "review_max_attempts": 3,
            "review_results": [], "raw_agent_output": None, "review_verdict": "",
            "intervention_actions": [
                {"type": "add_prerequisite", "target": "闭包基础",
                 "reason": "缺前置知识", "priority": 1,
                 "params": {"node_name": "闭包基础", "node_description": "理解作用域",
                            "estimated_minutes": 40}}
            ],
            "intervention_summary": "加前置",
        }

        result = await apply_intervention(state)
        assert len(result.get("intervention_applied", [])) == 1

        async for db in _get_db():
            nodes_result = await db.execute(
                select(KnowledgeNode)
                .where(KnowledgeNode.plan_id == plan_id)
                .order_by(KnowledgeNode.order_index.asc())
            )
            nodes = nodes_result.scalars().all()
            assert len(nodes) == 4  # 3 orig + 1 new
            assert nodes[-1].name == "闭包基础"
            assert nodes[-1].estimated_minutes == 40
            break


class TestAdjustMinutes:
    """adjust_minutes 动作"""

    @pytest.mark.asyncio
    async def test_adjust_minutes_updates_node(self):
        from app.agents.intervention_agent import apply_intervention
        from app.agents.state import AgentState
        from app.db.session import get_db as _get_db
        from app.models.knowledge_node import KnowledgeNode
        from sqlalchemy import select

        async for db in _get_db():
            from app.models.user import User
            user = User(username="test-adjmin", email="adjmin@t.com", hashed_password="x")
            db.add(user)
            await db.flush()
            plan = await _seed_plan_async(db, user.id)
            plan_id = plan.id
            break

        state: AgentState = {
            "messages": [], "user_id": str(user.id), "plan_id": str(plan_id),
            "session_id": "", "agent_type": "intervention", "tools": [], "next": "",
            "parsed_goal": None, "plan_result": None,
            "execution_plan": [], "execution_index": 0,
            "step_results": {}, "orchestration_warnings": [],
            "review_attempts": 0, "review_max_attempts": 3,
            "review_results": [], "raw_agent_output": None, "review_verdict": "",
            "intervention_actions": [
                {"type": "adjust_minutes", "target": "节点2时长调整",
                 "reason": "节奏过快", "priority": 1,
                 "params": {"node_index": 1, "new_minutes": 20}}
            ],
            "intervention_summary": "调整时长",
        }

        result = await apply_intervention(state)
        assert len(result.get("intervention_applied", [])) == 1

        async for db in _get_db():
            nodes_result = await db.execute(
                select(KnowledgeNode)
                .where(KnowledgeNode.plan_id == plan_id)
                .order_by(KnowledgeNode.order_index.asc())
            )
            nodes = nodes_result.scalars().all()
            assert len(nodes) == 3
            assert nodes[1].estimated_minutes == 20  # 节点2
            break

    @pytest.mark.asyncio
    async def test_adjust_minutes_clamps_minimum(self):
        from app.agents.intervention_agent import apply_intervention
        from app.agents.state import AgentState
        from app.db.session import get_db as _get_db
        from app.models.knowledge_node import KnowledgeNode
        from sqlalchemy import select

        async for db in _get_db():
            from app.models.user import User
            user = User(username="test-minclamp", email="minclamp@t.com", hashed_password="x")
            db.add(user)
            await db.flush()
            plan = await _seed_plan_async(db, user.id)
            plan_id = plan.id
            break

        state: AgentState = {
            "messages": [], "user_id": str(user.id), "plan_id": str(plan_id),
            "session_id": "", "agent_type": "intervention", "tools": [], "next": "",
            "parsed_goal": None, "plan_result": None,
            "execution_plan": [], "execution_index": 0,
            "step_results": {}, "orchestration_warnings": [],
            "review_attempts": 0, "review_max_attempts": 3,
            "review_results": [], "raw_agent_output": None, "review_verdict": "",
            "intervention_actions": [
                {"type": "adjust_minutes", "target": "过小值", "reason": "",
                 "priority": 2, "params": {"node_index": 0, "new_minutes": -10}}
            ],
            "intervention_summary": "最小值测试",
        }

        result = await apply_intervention(state)
        assert len(result.get("intervention_applied", [])) == 1

        async for db in _get_db():
            nodes_result = await db.execute(
                select(KnowledgeNode)
                .where(KnowledgeNode.plan_id == plan_id)
                .order_by(KnowledgeNode.order_index.asc())
            )
            nodes = nodes_result.scalars().all()
            assert nodes[0].estimated_minutes == 5  # clamped to min 5
            break


class TestErrorHandling:
    """异常处理"""

    @pytest.mark.asyncio
    async def test_invalid_plan_id_does_not_crash(self):
        from app.agents.intervention_agent import apply_intervention
        from app.agents.state import AgentState

        state: AgentState = {
            "messages": [], "user_id": "999999", "plan_id": "999999",
            "session_id": "", "agent_type": "intervention", "tools": [], "next": "",
            "parsed_goal": None, "plan_result": None,
            "execution_plan": [], "execution_index": 0,
            "step_results": {}, "orchestration_warnings": [],
            "review_attempts": 0, "review_max_attempts": 3,
            "review_results": [], "raw_agent_output": None, "review_verdict": "",
            "intervention_actions": [
                {"type": "adjust_priority", "target": "x", "reason": "x",
                 "priority": 1, "params": {"new_priority": 1}}
            ],
            "intervention_summary": "x",
        }

        result = await apply_intervention(state)
        assert "intervention_applied" in result
        assert "intervention_errors" in result

    @pytest.mark.asyncio
    async def test_empty_actions_does_not_crash(self):
        from app.agents.intervention_agent import apply_intervention
        from app.agents.state import AgentState

        state: AgentState = {
            "messages": [], "user_id": "1", "plan_id": "1",
            "session_id": "", "agent_type": "intervention", "tools": [], "next": "",
            "parsed_goal": None, "plan_result": None,
            "execution_plan": [], "execution_index": 0,
            "step_results": {}, "orchestration_warnings": [],
            "review_attempts": 0, "review_max_attempts": 3,
            "review_results": [], "raw_agent_output": None, "review_verdict": "",
            "intervention_actions": [],
            "intervention_summary": "",
        }

        result = await apply_intervention(state)
        assert result.get("intervention_applied", []) == []
        assert result.get("intervention_errors", []) == []

    @pytest.mark.asyncio
    async def test_unknown_action_type_is_skipped(self):
        from app.agents.intervention_agent import apply_intervention
        from app.agents.state import AgentState
        from app.db.session import get_db as _get_db

        async for db in _get_db():
            from app.models.user import User
            user = User(username="test-unknown", email="unknown@t.com", hashed_password="x")
            db.add(user)
            await db.flush()
            plan = await _seed_plan_async(db, user.id)
            plan_id = plan.id
            break

        state: AgentState = {
            "messages": [], "user_id": str(user.id), "plan_id": str(plan_id),
            "session_id": "", "agent_type": "intervention", "tools": [], "next": "",
            "parsed_goal": None, "plan_result": None,
            "execution_plan": [], "execution_index": 0,
            "step_results": {}, "orchestration_warnings": [],
            "review_attempts": 0, "review_max_attempts": 3,
            "review_results": [], "raw_agent_output": None, "review_verdict": "",
            "intervention_actions": [
                {"type": "suggest_review", "target": "复习", "reason": "",
                 "priority": 2, "params": {}}
            ],
            "intervention_summary": "unknown",
        }

        result = await apply_intervention(state)
        applied = result.get("intervention_applied", [])
        assert len(applied) == 1
        assert "无需落库操作" in applied[0]["result"]
