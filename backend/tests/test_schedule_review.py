"""Schedule Agent 审查回路测试。"""

from datetime import time

import pytest

from app.agents.schedule_agent import (
    _fallback_guide,
    review_router,
    schedule_review_node,
    schedule_reviewer,
)


@pytest.mark.asyncio
async def test_schedule_reviewer_passes_valid_plan():
    guide = _fallback_guide("变量", 30, "基础概念")
    raw_output = {
        "planned_items": [
            {
                "plan_id": 1,
                "knowledge_node_id": 10,
                "start_time": time(19, 0),
                "end_time": time(19, 30),
                "duration_minutes": 30,
                "guide_content": guide,
            }
        ],
        "budget": 60,
    }
    result = await schedule_reviewer(raw_output, "", {"budget": 60})
    assert result["verdict"] == "pass"
    assert result["issues"] == []


@pytest.mark.asyncio
async def test_schedule_reviewer_rejects_budget_overflow_and_bad_guide():
    raw_output = {
        "planned_items": [
            {
                "plan_id": 1,
                "knowledge_node_id": 10,
                "start_time": time(19, 0),
                "end_time": time(20, 30),
                "duration_minutes": 90,
                "guide_content": "随便写一点",
            }
        ],
        "budget": 60,
    }
    result = await schedule_reviewer(raw_output, "", {"budget": 60})
    assert result["verdict"] == "fail"
    assert any("预算" in issue for issue in result["issues"])
    assert any("小节" in issue for issue in result["issues"])


@pytest.mark.asyncio
async def test_schedule_reviewer_rejects_overlap_and_duplicate():
    guide = _fallback_guide("A", 20)
    raw_output = {
        "planned_items": [
            {
                "plan_id": 1,
                "knowledge_node_id": 1,
                "start_time": time(19, 0),
                "end_time": time(19, 20),
                "duration_minutes": 20,
                "guide_content": guide,
            },
            {
                "plan_id": 1,
                "knowledge_node_id": 1,
                "start_time": time(19, 10),
                "end_time": time(19, 30),
                "duration_minutes": 20,
                "guide_content": guide,
            },
        ],
        "budget": 60,
    }
    result = await schedule_reviewer(raw_output, "", {"budget": 60})
    assert result["verdict"] == "fail"
    assert any("重叠" in issue for issue in result["issues"])
    assert any("重复" in issue for issue in result["issues"])


@pytest.mark.asyncio
async def test_schedule_review_node_retries_until_max_then_passes():
    guide = "无效指引"
    state = {
        "planned_items": [
            {
                "plan_id": 1,
                "knowledge_node_id": 1,
                "start_time": time(19, 0),
                "end_time": time(19, 20),
                "duration_minutes": 20,
                "guide_content": guide,
            }
        ],
        "schedule_context": {"budget": 60},
        "review_attempts": 2,
        "review_max_attempts": 3,
        "review_results": [],
        "agent_type": "schedule",
        "messages": [],
    }
    result = await schedule_review_node(state)
    assert result["review_attempts"] == 3
    # 达上限后强制放行，进入 persist
    assert result["review_verdict"] == "pass"
    assert review_router({**state, **result}) == "end"


@pytest.mark.asyncio
async def test_schedule_review_node_fail_triggers_retry():
    state = {
        "planned_items": [],
        "schedule_context": {"budget": 60},
        "review_attempts": 0,
        "review_max_attempts": 3,
        "review_results": [],
        "agent_type": "schedule",
        "messages": [],
        "skip_reason": None,
    }
    result = await schedule_review_node(state)
    assert result["review_verdict"] == "fail"
    assert review_router({**state, **result}) == "retry"


def test_review_router_pass_and_retry():
    assert review_router({"review_verdict": "pass"}) == "end"
    assert review_router({"review_verdict": "fail"}) == "retry"
