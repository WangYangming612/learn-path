"""
Profile Agent 测试共享 Fixtures

提供：Mock 鉴权、Mock LLM、FastAPI TestClient
"""
import json
import uuid

import pytest
from fastapi.testclient import TestClient


# ── Mock User ─────────────────────────────────────────────────────

def _random_user_id() -> int:
    """每次调用生成 7 位唯一 user_id，避免测试间 DB 数据污染"""
    return uuid.uuid4().int % 9_000_000 + 1_000_000


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

    def with_structured_output(self, schema, **kwargs):
        """模拟 LangChain 结构化输出"""
        return self

    async def astream(self, messages, **kwargs):
        """模拟流式输出"""
        yield MockAIMessage(self._response)


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



# ── PlanDraft Mock Data ───────────────────────────────────────────
_MOCK_PLAN_DRAFT_JSON = {
    "goal_text": "我想3个月入门Python人工智能",
    "parsed_goal": {
        "domain": "Python人工智能",
        "duration_months": 3,
        "current_level": "beginner",
        "target_depth": "introduction",
    },
    "nodes": [
        {
            "id": "mock-n1",
            "title": "Python 基础语法",
            "description": "掌握 Python 核心语法",
            "estimated_minutes": 300,
            "prerequisite_ids": [],
        },
        {
            "id": "mock-n2",
            "title": "NumPy 与数据处理",
            "description": "学习 NumPy 数组操作",
            "estimated_minutes": 240,
            "prerequisite_ids": ["mock-n1"],
        },
    ],
}


async def _mock_plan_draft_ainvoke(*args, **kwargs):
    """返回可模型校验的 mock PlanDraft"""
    from app.schemas.plan import PlanDraft
    return PlanDraft.model_validate(_MOCK_PLAN_DRAFT_JSON)


# ── Plan Agent 专用 Mock ─────────────────────────────────────────
@pytest.fixture
def mock_llm_for_plan_agent(monkeypatch):
    """Mock LLM 以保证 plan_agent 的 with_structured_output 调用成功"""

    def _get_chat_model_for_plan(temperature=0, timeout=60, streaming=False):
        model = MockChatModel("mock")
        model.ainvoke = _mock_plan_draft_ainvoke
        return model

    monkeypatch.setattr(
        "app.agents.plan_agent.llm_client.get_chat_model", _get_chat_model_for_plan
    )
    yield

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def _ensure_schema():
    """
    确保测试数据库 schema 与 ORM 模型一致，自动补齐所有缺失字段。

    What: 对比 Base.metadata 中定义的表/列与实际 SQLite 数据库，
          对缺失列执行 ALTER TABLE ADD COLUMN
    Why: 项目无 Alembic，OR 模型变更后已有数据库文件不会自动更新 schema。
         此 fixture 保证每次测试运行前 schema 始终与 ORM 同步。
    """
    import asyncio
    from sqlalchemy import text
    from app.db.base import Base
    from app.db.session import get_engine

    async def _migrate():
        engine = get_engine()
        async with engine.begin() as conn:
            # 空库时先建表，再做缺列迁移；否则 PRAGMA 空结果会误走 ALTER TABLE
            await conn.run_sync(Base.metadata.create_all)
            for table in Base.metadata.sorted_tables:
                table_name = table.name
                # 查询数据库中该表现有列名
                result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
                existing_columns = {row[1] for row in result.fetchall()}

                for column in table.columns:
                    if column.name not in existing_columns:
                        col_type = _sqlite_type(column)
                        nullable = ""
                        if column.nullable:
                            nullable = ""
                        else:
                            nullable = " NOT NULL"
                        default_clause = ""
                        if column.default is not None:
                            default_val = column.default.arg
                            if isinstance(default_val, str):
                                default_clause = f" DEFAULT '{default_val}'"
                            elif isinstance(default_val, bool):
                                default_clause = f" DEFAULT {1 if default_val else 0}"
                            elif isinstance(default_val, (int, float)):
                                default_clause = f" DEFAULT {default_val}"
                        elif not column.nullable:
                            # SQLite requires a default for NOT NULL columns added via ALTER
                            if col_type in ("INTEGER", "FLOAT", "REAL"):
                                default_clause = " DEFAULT 0"
                            elif col_type == "TEXT":
                                default_clause = " DEFAULT ''"
                            elif col_type == "BOOLEAN":
                                default_clause = " DEFAULT 0"
                        sql = (
                            f"ALTER TABLE {table_name} ADD COLUMN "
                            f"{column.name} {col_type}{nullable}{default_clause}"
                        )
                        await conn.execute(text(sql))
        await engine.dispose()

    asyncio.run(_migrate())
    yield


def _sqlite_type(column) -> str:
    """将 SQLAlchemy 列类型映射为 SQLite 类型名"""
    import sqlalchemy.types as types

    type_map = {
        types.Integer: "INTEGER",
        types.String: "TEXT",
        types.Text: "TEXT",
        types.Float: "REAL",
        types.Boolean: "BOOLEAN",
        types.Date: "DATE",
        types.DateTime: "DATETIME",
        types.Time: "TIME",
        types.JSON: "TEXT",
    }
    for py_type, sql_type in type_map.items():
        if isinstance(column.type, py_type):
            return sql_type
    return "TEXT"


@pytest.fixture(autouse=True)
def _clean_db():
    """自动重建测试数据库表，防止跨测试数据和旧 schema 污染。"""
    import asyncio
    from app.db.session import get_engine
    from app.db.base import Base

    async def _reset():
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_reset())
    yield
    # 测试结束后清理所有表数据
    async def _clean():
        engine = get_engine()
        async with engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                await conn.execute(table.delete())
    asyncio.run(_clean())


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
    """FastAPI TestClient（含鉴权绕过 + 唯一 user_id 避免测试污染）"""
    from app.api.deps import get_current_user

    class MockUser:
        id = _random_user_id()
        username = "test_user"
        email = "test@example.com"
        is_active = True

    async def _mock_auth():
        return MockUser()

    monkeypatch.setattr("app.api.deps.get_current_user", _mock_auth)

    from app.main import app
    app.dependency_overrides[get_current_user] = _mock_auth
    return TestClient(app)


