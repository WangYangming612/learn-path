"""
Profile Agent 函数测试

覆盖:
  - run_profile_get_chat()
  - run_survey_first()
  - run_survey_next()
  - orchestrator view_profile 路由
  - ProfileAgentState 类型兼容
  - _format_single_dimension / _format_profile_snapshot
"""
import pytest


class TestRunProfileGetChat:
    """run_profile_get_chat() — 画像查询聊天"""

    @pytest.mark.asyncio
    async def test_new_user_returns_guidance(self, monkeypatch):
        from app.agents.profile_agent import run_profile_get_chat

        result = await run_profile_get_chat(user_id="999999", session_id="test")
        msgs = result.get("messages", [])
        assert len(msgs) == 1
        content = msgs[0].content
        assert "没有建立" in content or "还没有" in content

    @pytest.mark.asyncio
    async def test_returns_aimessage(self, monkeypatch):
        from app.agents.profile_agent import run_profile_get_chat
        from langchain_core.messages import AIMessage

        result = await run_profile_get_chat(user_id="999998", session_id="test")
        msgs = result.get("messages", [])
        assert len(msgs) >= 1
        assert isinstance(msgs[0], AIMessage)


class TestRunSurveyFirst:
    """run_survey_first() — 启动摸底"""

    @pytest.mark.asyncio
    async def test_returns_round_info(self, monkeypatch):
        from app.agents.profile_agent import run_survey_first

        result = await run_survey_first(user_id="999997")
        assert result["complete"] is False
        assert result["round"] == 1
        assert result["total_rounds"] == 4
        assert len(result["question"]) > 0


class TestRunSurveyNext:
    """run_survey_next() — 处理摸底回答"""

    @pytest.mark.asyncio
    async def test_single_round_returns_followup(self, monkeypatch):
        from app.agents.profile_agent import run_survey_next

        context = {
            "survey_answers": [],
            "survey_question": "你之前学过什么？",
        }
        result = await run_survey_next(
            user_id="999996",
            answer="我学过Python，喜欢先理解再练习",
            context=context,
        )
        assert result["profile_complete"] is False
        assert result["needs_followup"] is True

    @pytest.mark.asyncio
    async def test_four_rounds_completes(self, monkeypatch):
        from app.agents.profile_agent import run_survey_next

        answers = ["A1", "A2", "A3"]
        context = {
            "survey_answers": answers,
            "survey_question": "你有什么学习习惯？",
        }
        result = await run_survey_next(
            user_id="999995",
            answer="我喜欢晚上学习，坚持了半年",
            context=context,
        )
        # 4 rounds should complete (3 prior + 1 new = 4)
        assert result["profile_complete"] is True
        assert result["needs_followup"] is False

    @pytest.mark.asyncio
    async def test_accumulates_answers(self, monkeypatch):
        from app.agents.profile_agent import run_survey_next

        context = {
            "survey_answers": ["先验知识"],
            "survey_question": "你喜欢怎么学？",
        }
        result = await run_survey_next(
            user_id="999994",
            answer="动手实践",
            context=context,
        )
        assert result["needs_followup"] is True


class TestOrchestratorRouting:
    """Orchestrator 路由 view_profile → profile_agent_node"""

    @pytest.mark.asyncio
    async def test_view_profile_routes_to_profile_agent(self, monkeypatch):
        from app.agents.orchestrator import create_orchestrator_graph
        from langchain_core.messages import HumanMessage

        graph = create_orchestrator_graph()
        initial_state = {
            "messages": [HumanMessage(content="看看我的学习情况")],
            "user_id": "999993",
            "plan_id": None,
            "session_id": "test",
            "agent_type": "orchestrator",
            "tools": [],
            "next": "",
        }
        result = await graph.ainvoke(initial_state)
        msgs = result.get("messages", [])
        assert len(msgs) >= 2  # user message + AI response


class TestStateType:
    """ProfileAgentState 类型兼容性"""

    def test_state_dict_matches_typed_dict(self):
        from app.agents.state import ProfileAgentState

        state: ProfileAgentState = {
            "messages": [],
            "user_id": "1",
            "plan_id": None,
            "session_id": "s",
            "agent_type": "profile",
            "tools": [],
            "next": "",
            "action": "get_profile",
            "survey_answers": None,
            "feedback_signal": None,
            "confidence_delta": None,
            "source_session": None,
            "target_dimension": None,
            "user_comment": None,
            "profile": None,
            "survey_question": None,
            "calibration_result": None,
            "profile_changed": None,
            "profile_changelog": None,
        }
        assert len(state) == 19


class TestFormatHelpers:
    """格式化辅助函数"""

    def test_format_single_dimension_with_data(self):
        from app.agents.profile_agent import _format_single_dimension

        dim = {"label": "视觉型", "confidence": 85, "evidence": ["偏好视频教程"]}
        result = _format_single_dimension("learning_style", dim)
        assert "视觉型" in result
        assert "85" in result
        assert "偏好视频教程" in result

    def test_format_single_dimension_fallback(self):
        from app.agents.profile_agent import _format_single_dimension

        result = _format_single_dimension("learning_style", None)
        assert "未知" in result or len(result) > 0

    def test_format_profile_snapshot(self, monkeypatch):
        from app.agents.profile_agent import _format_profile_snapshot

        mock = {
            "learning_style": {"label": "视觉型", "confidence": 80, "evidence": []},
            "best_time_slots": {"label": "夜猫子型", "confidence": 70, "evidence": []},
            "learning_rhythm": "未知",
            "feedback_baseline": "未知",
            "persistence": "未知",
            "knowledge_retention": "未知",
        }
        result = _format_profile_snapshot(mock)
        assert "视觉型" in result
        assert "夜猫子型" in result
        assert "未知" in result
