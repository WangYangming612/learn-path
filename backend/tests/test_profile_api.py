"""
Profile API 端点测试

覆盖:
  GET  /api/v1/profile
  GET  /api/v1/profile/survey/next
  POST /api/v1/profile/survey
  POST /api/v1/profile/calibrate/{dimension}
  GET  /api/v1/profile/history
"""


class TestGetProfile:
    """GET /api/v1/profile — 画像查询"""

    def test_new_user_returns_default_profile(self, client):
        resp = client.get("/api/v1/profile", headers={"Authorization": "Bearer t"})
        assert resp.status_code == 200
        data = resp.json()
        assert "profile" in data
        assert data["total_feedback_count"] == 0
        assert data["needs_initial_survey"] is True
        assert len(data["profile"]) == 6
        assert data["profile"]["learning_style"]["label"] == "未知"
        assert data["profile"]["learning_style"]["confidence"] == 0

    def test_profile_has_all_six_dimensions(self, client):
        resp = client.get("/api/v1/profile", headers={"Authorization": "Bearer t"})
        data = resp.json()
        expected = [
            "learning_style", "best_time_slots", "learning_rhythm",
            "feedback_baseline", "persistence", "knowledge_retention",
        ]
        for dim in expected:
            assert dim in data["profile"], f"Missing dimension: {dim}"
            assert "label" in data["profile"][dim]
            assert "confidence" in data["profile"][dim]
            assert "evidence" in data["profile"][dim]


class TestSurveyNext:
    """GET /api/v1/profile/survey/next — 摸底问题"""

    def test_returns_first_question(self, client):
        resp = client.get(
            "/api/v1/profile/survey/next",
            headers={"Authorization": "Bearer t"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["complete"] is False
        assert data["round"] == 1
        assert data["total_rounds"] == 4
        assert len(data["question"]) > 0

    def test_idempotent_same_session(self, client):
        """重复调用返回同一 session 的当前问题"""
        r1 = client.get("/api/v1/profile/survey/next", headers={"Authorization": "Bearer t"})
        r2 = client.get("/api/v1/profile/survey/next", headers={"Authorization": "Bearer t"})
        assert r1.json()["round"] == r2.json()["round"]
        assert r1.json()["question"] == r2.json()["question"]


class TestSurveySubmit:
    """POST /api/v1/profile/survey — 提交摸底回答"""

    def test_complete_four_round_survey(self, client):
        answers = [
            "我喜欢先理解概念再练习",
            "我每天固定晚上学习",
            "遇到困难会反复尝试",
            "喜欢通过实践巩固知识",
        ]

        # 先启动摸底
        client.get("/api/v1/profile/survey/next", headers={"Authorization": "Bearer t"})

        for i, answer in enumerate(answers):
            resp = client.post(
                "/api/v1/profile/survey",
                json={"answer": answer},
                headers={"Authorization": "Bearer t"},
            )
            assert resp.status_code == 200
            data = resp.json()
            if i < len(answers) - 1:
                assert data["needs_followup"] is True, f"Round {i+1} should have followup"
                assert data["next_question"] is not None
            else:
                assert data["profile_complete"] is True, f"Round {i+1} should be complete"

    def test_no_active_session_returns_400(self, client):
        """未启动摸底直接提交 → 400"""
        resp = client.post(
            "/api/v1/profile/survey",
            json={"answer": "test"},
            headers={"Authorization": "Bearer t"},
        )
        assert resp.status_code == 400

    def test_empty_answer_rejected(self, client):
        resp = client.post(
            "/api/v1/profile/survey",
            json={"answer": ""},
            headers={"Authorization": "Bearer t"},
        )
        assert resp.status_code == 422  # Pydantic validation error


class TestCalibrate:
    """POST /api/v1/profile/calibrate/{dimension} — 校准维度"""

    def test_calibrate_valid_dimension(self, client):
        # 先触发 profile 初始化
        client.get("/api/v1/profile", headers={"Authorization": "Bearer t"})

        resp = client.post(
            "/api/v1/profile/calibrate/learning_style",
            json={"comment": "我觉得判断不太准"},
            headers={"Authorization": "Bearer t"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["dimension"] == "learning_style"
        assert "old_label" in data
        assert "new_label" in data
        assert "message" in data
        assert data["new_confidence"] <= data["old_confidence"]

    def test_calibrate_invalid_dimension_returns_error(self, client):
        resp = client.post(
            "/api/v1/profile/calibrate/invalid_dim",
            json={"comment": "test"},
            headers={"Authorization": "Bearer t"},
        )
        assert resp.status_code == 200
        assert "不存在" in resp.json()["message"]

    def test_empty_comment_rejected(self, client):
        resp = client.post(
            "/api/v1/profile/calibrate/learning_style",
            json={"comment": ""},
            headers={"Authorization": "Bearer t"},
        )
        assert resp.status_code == 422


class TestHistory:
    """GET /api/v1/profile/history — 画像变更历史"""

    def test_returns_list(self, client):
        resp = client.get("/api/v1/profile/history", headers={"Authorization": "Bearer t"})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["history"], list)

    def test_history_item_structure(self, client):
        resp = client.get("/api/v1/profile/history", headers={"Authorization": "Bearer t"})
        data = resp.json()
        for item in data["history"]:
            assert "timestamp" in item
            assert "source" in item
            assert "changes" in item
            assert isinstance(item["changes"], list)
