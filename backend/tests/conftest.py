"""
Profile Agent 测试共享 Fixtures

提供：Mock 鉴权、Mock LLM、FastAPI TestClient
"""
import json

import pytest
from fastapi.testclient import TestClient


# ── Mock User ─────────────────────────────────────────────────────

class MockUser:
    id = 999888
    username = "test_user"
    email = "test@example.com"
    is_active = True


# ── Mock AIMessage ────────────────────────────────────────────────

class MockAIMessage:
    """模拟 langchain_core.messages.AIMessage"""

    def __init__(self, content: str):
        self.content = content


# ── Mock Chat Model ───────────────────────────────────────────────

class MockChatModel:
    """模拟 LLM chat_model，返回预设 JSON 或文本"""

    def __init__(self, response_content: str = ""):
        self._response = response_content

    async def ainvoke(self, messages, **kwargs):
        return MockAIMessage(self._response)

    def invoke(self, messages, **kwargs):
        return MockAIMessage(self._response)


def _mock_survey_analysis_response() -> str:
    """生成模拟的 LLM 摸底分析 JSON 响应"""
    return json.dumps({
        "profile_updates": {
            "learning_style": {
                "label": "理解偏慢但记忆牢固型",
                "confidence": 60,
                "evidence": "喜欢搞透彻",
            },
            "best_time_slots": {
                "label": "夜猫子型（20:00-22:00）",
                "confidence": 70,
                "evidence": "晚上学习效率最高",
            },
        },
        "profile_complete": False,
        "followup_question": "你一般用什么方式学习？看视频、看书、还是动手实践？",
        "reasoning": "分析完成",
    })


def _mock_survey_final_response() -> str:
    """生成模拟的 LLM 摸底最终轮 JSON 响应"""
    return json.dumps({
        "profile_updates": {
            "learning_rhythm": {
                "label": "稳健型",
                "confidence": 65,
                "evidence": "指定详细计划",
            },
            "persistence": {
                "label": "稳定每日型",
                "confidence": 75,
                "evidence": "坚持了半年多",
            },
        },
        "profile_complete": True,
        "followup_question": None,
        "reasoning": "4 轮完成",
    })


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_llm(monkeypatch):
    """全局 Mock LLM，避免真实 API 调用"""

    call_count = {"count": 0}

    def _get_chat_model(temperature=0, timeout=30, streaming=False):
        call_count["count"] += 1
        # 根据调用次数返回不同的 mock 响应
        if call_count["count"] % 2 == 1:
            # 摸底问题生成（奇数调用）
            return MockChatModel("你之前学过什么？喜欢怎么学习？")
        else:
            # 摸底答案分析（偶数调用）
            if call_count["count"] >= 8:
                return MockChatModel(_mock_survey_final_response())
            return MockChatModel(_mock_survey_analysis_response())

    monkeypatch.setattr(
        "app.llm.client.llm_client.get_chat_model", _get_chat_model
    )
    monkeypatch.setattr(
        "app.agents.profile_agent.llm_client.get_chat_model", _get_chat_model
    )
    yield


@pytest.fixture
def client(monkeypatch):
    """FastAPI TestClient（含鉴权绕过）"""
    from app.api.deps import get_current_user

    async def _mock_auth():
        return MockUser()

    monkeypatch.setattr("app.api.deps.get_current_user", _mock_auth)

    from app.main import app
    app.dependency_overrides[get_current_user] = _mock_auth
    return TestClient(app)
