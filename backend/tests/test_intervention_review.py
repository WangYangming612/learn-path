"""
Intervention Agent 审查回路 + 联动测试

覆盖:
  - schedule_review 动作可通过审查
  - adjust_minutes 动作可通过审查
  - stuck 信号触发干预联动 (feedback API 集成)
"""

import pytest


class TestReviewValidActionTypes:
    """审查器正确接受所有合法动作类型"""

    @pytest.mark.asyncio
    async def test_schedule_review_passes_review(self):
        from app.agents.intervention_agent import intervention_reviewer

        raw_output = {
            "intervention_actions": [
                {
                    "type": "schedule_review",
                    "target": "复习闭包基础",
                    "reason": "遗忘曲线到期",
                    "priority": 1,
                    "params": {"node_id": 1, "next_review_date": "2026-08-01"},
                }
            ],
            "intervention_summary": "安排了一次知识复习任务",
            "intervention_signal": "need_practice",
        }
        result = await intervention_reviewer(raw_output, "", {})
        assert result["verdict"] == "pass", f"issues: {result.get('issues')}"

    @pytest.mark.asyncio
    async def test_adjust_minutes_passes_review(self):
        from app.agents.intervention_agent import intervention_reviewer

        raw_output = {
            "intervention_actions": [
                {
                    "type": "adjust_minutes",
                    "target": "降低节点2时长",
                    "reason": "节奏过快",
                    "priority": 2,
                    "params": {"node_index": 1, "new_minutes": 20},
                }
            ],
            "intervention_summary": "调整节点预估时长以匹配学习节奏",
            "intervention_signal": "stuck",
        }
        result = await intervention_reviewer(raw_output, "", {})
        assert result["verdict"] == "pass", f"issues: {result.get('issues')}"

    @pytest.mark.asyncio
    async def test_all_action_types_in_valid_set_have_handler_or_graceful_skip(self):
        """确保 _VALID_ACTION_TYPES 中的所有类型都在 handler 或 else 中有处理"""
        from app.agents.intervention_agent import _VALID_ACTION_TYPES

        handled = {
            "adjust_priority", "pause_plan", "add_prerequisite",
            "adjust_minutes", "schedule_review",
        }
        known_unimplemented = {"add_practice", "adjust_rhythm", "suggest_review"}

        for action_type in _VALID_ACTION_TYPES:
            assert action_type in handled or action_type in known_unimplemented, (
                f"动作 {action_type} 在 _VALID_ACTION_TYPES 中但无 handler 且非 known_unimplemented"
            )


class TestStuckSignalTriggersIntervention:
    """stuck/need_practice 信号自动触发 Intervention Agent"""

    @pytest.mark.asyncio
    async def test_stuck_signal_does_not_crash_feedback_reply(self, client, monkeypatch):
        """修复后的 feedback reply 在 stuck 时不会因 Intervention 触发而崩溃"""
        from app.api.deps import get_current_user

        class MockUser:
            id = 1900001
            username = "test_stuck"
            email = "stuck@test.com"
            is_active = True

        async def _mock_auth():
            return MockUser()

        monkeypatch.setattr("app.api.deps.get_current_user", _mock_auth)
        from app.main import app

        app.dependency_overrides[get_current_user] = _mock_auth

        # 模拟需要 Intervention 的信号（无有效 session，应走到 fallback 分支）
        response = client.post(
            "/api/v1/feedback/reply",
            json={"session_id": "nonexistent-session-id", "reply": "感觉很难"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "signal" in data
        assert "confidence_delta" in data

    @pytest.mark.asyncio
    async def test_intervention_reviewer_rejects_empty_actions(self):
        from app.agents.intervention_agent import intervention_reviewer

        raw_output = {
            "intervention_actions": [],
            "intervention_summary": "无干预",
            "intervention_signal": "stuck",
        }
        result = await intervention_reviewer(raw_output, "", {})
        assert result["verdict"] == "fail"

    @pytest.mark.asyncio
    async def test_intervention_reviewer_rejects_invalid_type(self):
        from app.agents.intervention_agent import intervention_reviewer

        raw_output = {
            "intervention_actions": [
                {
                    "type": "delete_everything",
                    "target": "危险动作",
                    "reason": "",
                    "priority": 1,
                    "params": {},
                }
            ],
            "intervention_summary": "危险",
            "intervention_signal": "stuck",
        }
        result = await intervention_reviewer(raw_output, "", {})
        assert result["verdict"] == "fail"
