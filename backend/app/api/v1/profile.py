"""
Profile Agent API 路由

What: 提供画像查询、摸底问答、校准、历史等 REST API 端点
Why: 前端画像页面通过此路由获取和操作用户学习画像

架构说明：
  GET  /profile                  → 查询完整画像
  GET  /profile/survey/next      → 获取下一摸底问题（启动或恢复）
  POST /profile/survey           → 提交摸底回答
  POST /profile/calibrate/{dim}  → 校准维度置信度
  GET  /profile/history          → 查询画像变更历史

  survey session 用内存 dict 缓存（单机够用，无需 Redis），
  以 user_id 为 key 确保每人仅有一个活跃的摸底会话
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.agents.profile_agent import run_survey_first, run_survey_next
from app.core.profile_service import (
    calibrate_dimension,
    get_profile_history,
    get_user_profile,
)
from app.models.user import User
from app.schemas.profile import (
    CalibrateRequest,
    CalibrateResponse,
    ProfileDataSchema,
    ProfileHistoryItem,
    ProfileHistoryResponse,
    ProfileResponse,
    SurveyAnswerRequest,
    SurveyAnswerResponse,
    SurveyNextResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profile", tags=["profile"])


# ── Survey Session 缓存 ──────────────────────────────────────────
# What: 摸底问答多轮对话的会话状态暂存
# Why: 避免引入 Redis，单机部署下内存 dict + TTL 足够
_survey_sessions: dict[str, dict[str, Any]] = {}
_SESSION_TTL_MINUTES = 30


def _clean_expired_sessions() -> None:
    """清理过期 survey session（懒清理，在创建新 session 时调用）"""
    now = datetime.now()
    expired = [
        uid for uid, data in _survey_sessions.items()
        if data.get("expires_at") and data["expires_at"] < now
    ]
    for uid in expired:
        _survey_sessions.pop(uid, None)
    if expired:
        logger.debug(f"[ProfileAPI] 清理了 {len(expired)} 个过期 survey session")


def _build_profile_response(profile_data: dict) -> ProfileResponse:
    """将 profile_service 返回的 dict 转为 Pydantic 响应模型"""
    return ProfileResponse(
        profile=ProfileDataSchema(**profile_data.get("profile", {})),
        total_feedback_count=profile_data.get("total_feedback_count", 0),
        last_calibrated_at=profile_data.get("last_calibrated_at"),
        needs_initial_survey=profile_data.get("needs_initial_survey", True),
        initial_survey_question=profile_data.get("initial_survey_question"),
    )


# ── 端点实现 ─────────────────────────────────────────────────────

@router.get("", response_model=ProfileResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
) -> ProfileResponse:
    """
    获取当前用户画像（GET /api/v1/profile）

    What: 查询完整 6 维度画像快照 + 元数据
    Why: 前端画像页面主数据接口
    """
    try:
        profile_data = await get_user_profile(str(current_user.id))
        return _build_profile_response(profile_data)
    except Exception as exc:
        logger.exception(f"[ProfileAPI] 查询画像失败: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="画像查询失败，请稍后再试",
        )


@router.get("/survey/next", response_model=SurveyNextResponse)
async def get_survey_next(
    current_user: User = Depends(get_current_user),
) -> SurveyNextResponse:
    """
    获取下一摸底问题（GET /api/v1/profile/survey/next）

    What: 启动摸底问答或恢复已有会话
    Why: 前端画像页检测 needs_initial_survey=true 时调用，循环获取问题
    """
    _clean_expired_sessions()
    user_id = str(current_user.id)

    # 已有活跃 session → 返回当前问题
    existing = _survey_sessions.get(user_id)
    if existing and existing.get("expires_at", datetime.min) > datetime.now():
        return SurveyNextResponse(
            complete=False,
            round=existing["round"],
            total_rounds=existing["total_rounds"],
            question=existing.get("survey_question", ""),
        )

    # 检查画像是否已完整 → 无需摸底
    # get_user_profile 内部有完整容错（DB 异常返回默认画像），此处无需额外 try/except
    profile_data = await get_user_profile(user_id)
    if not profile_data.get("needs_initial_survey", True):
        return SurveyNextResponse(complete=True)

    # 启动新摸底问答
    try:
        result = await run_survey_first(user_id)
        _survey_sessions[user_id] = {
            "user_id": user_id,
            "survey_answers": [],
            "round": result["round"],
            "total_rounds": result["total_rounds"],
            "survey_question": result["question"],
            "expires_at": datetime.now() + timedelta(minutes=_SESSION_TTL_MINUTES),
        }
        return SurveyNextResponse(
            complete=False,
            round=result["round"],
            total_rounds=result["total_rounds"],
            question=result["question"],
        )
    except Exception as exc:
        logger.exception(f"[ProfileAPI] 启动摸底失败: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="摸底问答启动失败，请稍后再试",
        )


@router.post("/survey", response_model=SurveyAnswerResponse)
async def submit_survey_answer(
    body: SurveyAnswerRequest,
    current_user: User = Depends(get_current_user),
) -> SurveyAnswerResponse:
    """
    提交摸底回答（POST /api/v1/profile/survey）

    What: 接收用户对本轮问题的回答，分析并返回下一轮或完成
    Why: 前端循环调用此端点，直到 profile_complete=true
    """
    user_id = str(current_user.id)
    session = _survey_sessions.get(user_id)

    if not session or session.get("expires_at", datetime.min) < datetime.now():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有活跃的摸底问答会话，请先调用 GET /survey/next",
        )

    try:
        context = {
            "survey_answers": session.get("survey_answers", []),
            "survey_question": session.get("survey_question", ""),
        }
        result = await run_survey_next(user_id, body.answer, context)

        if result["profile_complete"]:
            _survey_sessions.pop(user_id, None)
            return SurveyAnswerResponse(
                profile_complete=True,
                needs_followup=False,
                next_question=None,
            )

        # 更新 session
        session["survey_answers"] = context["survey_answers"] + [body.answer]
        session["round"] = len(session["survey_answers"]) + 1
        session["survey_question"] = result.get("next_question", "")
        session["expires_at"] = datetime.now() + timedelta(minutes=_SESSION_TTL_MINUTES)

        return SurveyAnswerResponse(
            profile_complete=False,
            needs_followup=result["needs_followup"],
            next_question=result.get("next_question"),
        )
    except Exception as exc:
        logger.exception(f"[ProfileAPI] 处理摸底回答失败: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="摸底回答处理失败，请稍后再试",
        )


@router.post("/calibrate/{dimension}", response_model=CalibrateResponse)
async def calibrate_profile_dimension(
    dimension: str,
    body: CalibrateRequest,
    current_user: User = Depends(get_current_user),
) -> CalibrateResponse:
    """
    校准画像维度（POST /api/v1/profile/calibrate/{dimension}）

    What: 用户对某维度判断点踩，将该维度置信度减半
    Why: 让用户参与画像校准，提升画像准确性
    """
    try:
        result = await calibrate_dimension(
            str(current_user.id), dimension, body.comment
        )
        return CalibrateResponse(**result)
    except Exception as exc:
        logger.exception(f"[ProfileAPI] 校准维度失败: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="维度校准失败，请稍后再试",
        )


@router.get("/history", response_model=ProfileHistoryResponse)
async def get_history(
    current_user: User = Depends(get_current_user),
) -> ProfileHistoryResponse:
    """
    查询画像变更历史（GET /api/v1/profile/history）

    What: 返回画像变更记录，按时间倒序
    Why: 前端画像页面展示画像演变过程
    """
    try:
        raw = await get_profile_history(str(current_user.id))
        items = [
            ProfileHistoryItem(
                timestamp=entry.get("timestamp", datetime.min),
                source=entry.get("source", ""),
                changes=entry.get("changes", []),
            )
            for entry in raw
        ]
        return ProfileHistoryResponse(history=items)
    except Exception as exc:
        logger.exception(f"[ProfileAPI] 查询画像历史失败: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="画像历史查询失败，请稍后再试",
        )
