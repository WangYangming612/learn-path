
"""
Feedback Agent API 路由

What: 提供反馈交互的 REST API 端点，含 SSE 流式追问和 JSON 回复分析
Why: 前端用户在完成任务后触发反馈流程，流式展示追问，提交回复后获得分析结果

架构说明：
  POST /feedback/start → SSE 流式返回追问文本
  POST /feedback/reply → JSON 返回信号分析结果 + 系统响应

  session 用内存 dict 缓存（单机够用，无需 Redis）
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Body, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.agents.feedback_agent import (
    run_feedback_graph_first_half,
    run_feedback_graph_second_half,
    save_feedback_session,
)
from app.core.profile_service import update_profile
from app.llm.client import llm_client
from app.models.user import User
from app.schemas.feedback import (
    FeedbackReplyRequest,
    FeedbackReplyResponse,
    FeedbackStartRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])


# ── Session 缓存（内存字典） ─────────────────────────────────────
# What: 在 POST /feedback/start 和 POST /feedback/reply 之间暂存会话状态
# Why: 避免引入 Redis 依赖，单机部署下内存 dict 足够
# How: 每次访问时检查过期时间，懒清理过期 session
_sessions: dict[str, dict[str, Any]] = {}
_SESSION_TTL_MINUTES = 30  # session 有效期 30 分钟


def _clean_expired_sessions() -> None:
    """清理过期 session（懒清理，在每次创建新 session 时调用）"""
    now = datetime.now()
    expired_keys = [
        sid for sid, data in _sessions.items()
        if data.get("expires_at") and data["expires_at"] < now
    ]
    for sid in expired_keys:
        _sessions.pop(sid, None)
    if expired_keys:
        logger.debug(f"[SessionCache] 清理了 {len(expired_keys)} 个过期 session")


# ── 流式追问生成辅助函数 ─────────────────────────────────────────

async def _stream_question(
    user_id: str,
    task_id: str,
) -> AsyncGenerator[str, None]:
    """
    流式生成追问（SSE 格式）

    What: 加载上下文 → 流式调用 LLM 生成追问 → 以 SSE 事件流形式输出
    Why: 前端可以逐步显示生成的追问，提升用户体验

    Yields:
        SSE 格式的字符串，包含 question_chunk 和 question_done 事件
    """
    session_id = ""
    try:
        # 1. 加载上下文并生成追问（先获取完整追问用于 session 保存）
        context = await run_feedback_graph_first_half(
            user_id=user_id,
            task_id=task_id,
        )
        full_question = context.get("feedback_question", "")

        # 2. 生成并保存 session
        session_id = str(uuid.uuid4())
        expires_at = datetime.now() + timedelta(minutes=_SESSION_TTL_MINUTES)
        _sessions[session_id] = {
            "user_id": user_id,
            "task_id": task_id,
            "context": context,
            "question": full_question,
            "expires_at": expires_at,
        }

        # 3. 流式输出追问文本分块
        # 使用 LLM 重新流式生成（或直接切分已生成的完整文本作为 chunk）
        if full_question:
            try:
                # 重新用流式方式生成，逐 token 输出
                chat_model = llm_client.get_chat_model(
                    temperature=0.7, timeout=30, streaming=True
                )
                from app.llm.prompts.feedback import FEEDBACK_QUESTION_PROMPT

                profile = context.get("profile_updates", {})

                def _safe(val: Any, default: str = "未知") -> str:
                    if isinstance(val, dict):
                        return str(val.get("label", val.get("value", default)))
                    return str(val) if val else default

                prompt_args = {
                    "learning_style": _safe(profile.get("learning_style")),
                    "best_time_slots": _safe(profile.get("best_time_slots")),
                    "learning_rhythm": _safe(profile.get("learning_rhythm")),
                    "feedback_baseline": _safe(profile.get("feedback_baseline")),
                    "persistence": _safe(profile.get("persistence")),
                    "knowledge_retention": _safe(profile.get("knowledge_retention")),
                    "total_feedback_count": profile.get("total_feedback_count", 0),
                    "learning_content": context.get("learning_content", ""),
                    "recent_feedback_history": str(profile.get("recent_feedback_history", [])),
                }

                stream = chat_model.astream([
                    {"role": "system", "content": FEEDBACK_QUESTION_PROMPT.format(**prompt_args)},
                    {"role": "user", "content": "请根据以上信息生成追问。"},
                ])

                async for chunk in stream:
                    content = chunk.content if hasattr(chunk, "content") else str(chunk)
                    if content:
                        yield f"data: {json.dumps({'type': 'question_chunk', 'content': content})}\n\n"

                # 更新 session 中的 question 为流式实际输出
                streamed_question = ""

            except Exception as exc:
                logger.warning(f"[FeedbackAPI] 流式生成失败（{exc}），改为全量推送")
                # Fallback：将完整文本切分为 chunk
                chunk_size = 5
                for i in range(0, len(full_question), chunk_size):
                    chunk_text = full_question[i:i + chunk_size]
                    yield f"data: {json.dumps({'type': 'question_chunk', 'content': chunk_text})}\n\n"

        # 4. 发送完成事件
        yield f"data: {json.dumps({'type': 'question_done', 'session_id': session_id})}\n\n"

    except Exception as exc:
        logger.error(f"[FeedbackAPI] 流式追问生成失败: {exc}")
        yield f"data: {json.dumps({'type': 'error', 'content': '追问生成失败，请稍后再试'})}\n\n"
        yield f"data: {json.dumps({'type': 'question_done', 'session_id': session_id})}\n\n"


# ── 端点实现 ─────────────────────────────────────────────────────

@router.post("/start", response_class=StreamingResponse)
async def start_feedback(
    body: FeedbackStartRequest,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    启动反馈流程（SSE 流式输出）

    What: 接收 task_id，加载学习内容和用户画像，SSE 流式返回追问文本
    Why: 流式输出让前端可以逐步展示追问，提升交互体验

    SSE 事件类型：
      - question_chunk: { type, content } — 追问文本片段
      - question_done:  { type, session_id } — 追问完成，携带 session_id
      - error:          { type, content } — 错误信息
    """
    # 清理过期 session
    _clean_expired_sessions()

    return StreamingResponse(
        _stream_question(user_id=str(current_user.id), task_id=body.task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/reply", response_model=FeedbackReplyResponse)
async def reply_feedback(
    body: FeedbackReplyRequest,
    current_user: User = Depends(get_current_user),
) -> FeedbackReplyResponse:
    """
    提交用户回复（JSON 返回分析结果）

    What: 接收 session_id + 用户回复，执行信号解析和系统响应生成
    Why: 完成反馈流程的后半段，返回结构化分析结果供前端展示

    Returns:
        FeedbackReplyResponse: 信号、置信度变化、画像更新、重规划标记、系统回复
    """
    session_id = body.session_id
    user_reply = body.reply

    # 1. 查找 session
    session = _sessions.get(session_id)
    if not session:
        # 尝试从已过期 session 恢复（兜底返回默认值）
        logger.warning(f"[FeedbackAPI] session 不存在或已过期: {session_id}")
        return FeedbackReplyResponse(
            signal="normal",
            confidence_delta=0.0,
            replan_triggered=False,
            profile_updates={},
            system_response="收到你的反馈！我们会根据你的情况持续优化学习体验。",
        )

    # 2. 校验用户身份
    if str(current_user.id) != session.get("user_id"):
        logger.warning(
            f"[FeedbackAPI] session 用户不匹配: {current_user.id} != {session.get('user_id')}"
        )

    context = session.get("context", {})
    task_id = session.get("task_id", "")

    # 3. 执行后半段：信号解析 → 响应生成
    try:
        result = await run_feedback_graph_second_half(
            user_id=str(current_user.id),
            task_id=task_id,
            user_reply=user_reply,
            context=context,
        )

        signal = result.get("feedback_signal", "normal")
        confidence_delta = result.get("confidence_delta", 0.0)
        replan_triggered = result.get("replan_triggered", False)
        profile_updates = result.get("profile_updates", {})
        system_response = result.get("system_response", "")

        # 4. 画像联动更新
        if profile_updates:
            await update_profile(str(current_user.id), profile_updates)

        # 5. 保存反馈会话到 DB
        await save_feedback_session(
            user_id=str(current_user.id),
            task_id=task_id,
            signal=signal,
            confidence_delta=confidence_delta,
            replan_triggered=replan_triggered,
            profile_updates=profile_updates,
            question=session.get("question", ""),
            reply=user_reply,
            system_response=system_response,
        )

        # 6. 清理已使用的 session
        _sessions.pop(session_id, None)

        return FeedbackReplyResponse(
            signal=signal,
            confidence_delta=confidence_delta,
            replan_triggered=replan_triggered,
            profile_updates=profile_updates,
            system_response=system_response,
        )

    except Exception as exc:
        logger.error(f"[FeedbackAPI] 反馈回复处理失败: {exc}")
        return FeedbackReplyResponse(
            signal="normal",
            confidence_delta=0.0,
            replan_triggered=False,
            profile_updates={},
            system_response="抱歉，分析过程出现了问题。你可以稍后再次提交反馈。",
        )
