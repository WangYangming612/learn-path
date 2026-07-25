"""
画像相关 Pydantic Schema

What: 定义 Profile Agent 的请求/响应数据模型
Why: FastAPI 依赖 Pydantic 做请求体验证和响应序列化，
     覆盖画像查询、摸底问答、历史、校准四个子模块
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── 画像维度内部结构 ─────────────────────────────────────────────

class ProfileDimensionSchema(BaseModel):
    """画像单维度：label + confidence + evidence"""
    label: str = Field(..., description="维度标签，如 '理解偏慢但记忆牢固型'")
    confidence: float = Field(..., description="置信度，范围 0-100")
    evidence: list[str] = Field(default_factory=list, description="证据列表，每条是触发该判断的反馈记录摘要")


class ProfileDataSchema(BaseModel):
    """完整画像数据（6 维度）"""
    learning_style: ProfileDimensionSchema = Field(..., description="学习风格")
    best_time_slots: ProfileDimensionSchema = Field(..., description="最佳学习时段")
    learning_rhythm: ProfileDimensionSchema = Field(..., description="学习节奏偏好")
    feedback_baseline: ProfileDimensionSchema = Field(..., description="反馈校准基线")
    persistence: ProfileDimensionSchema = Field(..., description="持续力特征")
    knowledge_retention: ProfileDimensionSchema = Field(..., description="知识保留特征")


# ── 7.1 获取当前画像 ─────────────────────────────────────────────

class ProfileResponse(BaseModel):
    """获取画像响应（GET /api/v1/profile）"""
    profile: ProfileDataSchema = Field(..., description="当前画像 6 维度完整快照")
    total_feedback_count: int = Field(..., description="累计反馈次数")
    last_calibrated_at: Optional[datetime] = Field(None, description="上次校准时间（ISO 8601）")
    needs_initial_survey: bool = Field(..., description="是否需要摸底问答（画像未建立时为 true）")
    initial_survey_question: Optional[str] = Field(None, description="第一个摸底问题（needs_initial_survey=true 时填充）")


# ── 7.2 / 9.1 摸底问答 ──────────────────────────────────────────

class SurveyAnswerRequest(BaseModel):
    """摸底回答请求（POST /api/v1/profile/survey）"""
    answer: str = Field(..., min_length=1, description="用户对摸底问题的回答文本")


class SurveyAnswerResponse(BaseModel):
    """摸底回答响应 — 循环调用直到 profile_complete=true"""
    profile_complete: bool = Field(..., description="整轮摸底是否完成")
    needs_followup: bool = Field(..., description="是否还有下一轮追问")
    next_question: Optional[str] = Field(None, description="下一轮追问文本（needs_followup=true 时必有值）")


class SurveyNextResponse(BaseModel):
    """摸底下一题响应（GET /api/v1/profile/survey/next）"""
    complete: bool = Field(..., description="完整画像是否已建立（true 时无需再答题）")
    round: int = Field(default=0, description="当前轮次（complete=true 时无意义）")
    total_rounds: int = Field(default=0, description="预计总轮次")
    question: Optional[str] = Field(None, description="本轮问题文本（complete=true 时为 null）")


# ── 7.3 画像变更历史 ─────────────────────────────────────────────

class ProfileHistoryItem(BaseModel):
    """单条画像变更记录"""
    timestamp: datetime = Field(..., description="变更时间（ISO 8601）")
    source: str = Field(..., description="变更来源: feedback_session:{id} / initial_survey / user_calibration")
    changes: list[str] = Field(default_factory=list, description="变更描述列表，每条格式：'维度: 旧值 → 新值 (±置信度%)'")


class ProfileHistoryResponse(BaseModel):
    """画像变更历史响应（GET /api/v1/profile/history）"""
    history: list[ProfileHistoryItem] = Field(default_factory=list, description="变更记录列表，按时间倒序")


# ── 7.4 校准画像维度 ─────────────────────────────────────────────

class CalibrateRequest(BaseModel):
    """校准请求（POST /api/v1/profile/calibrate/{dimension}）"""
    comment: str = Field(..., min_length=1, description="用户对维度判断的反馈说明")


class CalibrateResponse(BaseModel):
    """校准响应"""
    dimension: str = Field(..., description="被校准的维度名")
    old_label: str = Field(..., description="校准前的维度标签")
    old_confidence: float = Field(..., description="校准前的置信度 (0-100)")
    new_label: str = Field(..., description="校准后的维度标签")
    new_confidence: float = Field(..., description="校准后的置信度 (0-100)")
    message: str = Field(..., description="系统自然语言反馈说明")
