"""
画像服务模块

What: 提供画像查询、更新、校准和历史能力
Why: 作为 Profile Agent 和 Feedback Agent 的数据层，
     负责 UserProfile ORM 的读写和 FeedbackSession 的聚合查询
How: 所有操作 try/except 兜底，不因依赖缺失而崩溃
"""

import logging
from collections import OrderedDict

logger = logging.getLogger(__name__)

# ── 常量 ─────────────────────────────────────────────────────────
PROFILE_DIMENSIONS = (
    "learning_style",
    "best_time_slots",
    "learning_rhythm",
    "feedback_baseline",
    "persistence",
    "knowledge_retention",
)
DEFAULT_LABEL = "未知"
_COMPLETENESS_THRESHOLD = 0.3
_MAX_EVIDENCE = 10


# ── 内部辅助 ─────────────────────────────────────────────────────

def _safe_int(val):
    """将 user_id 安全转为 int，容错非数字字符串"""
    try:
        return int(val)
    except (TypeError, ValueError):
        logger.warning(f"[ProfileService] 无法转换 user_id 为 int: {val!r}")
        return 0


def _ensure_dimension_struct(val):
    """
    规范化单维度数据为 {label, confidence, evidence} 结构

    What: 兼容旧数据（纯字符串）和新数据（结构化 dict），确保调用方始终拿到一致的结构
    Why: 历史数据可能只存了 label 字符串，profile_data JSON 可任意写入，此处统一出入口
    """
    if isinstance(val, dict):
        return {
            "label": str(val.get("label", DEFAULT_LABEL)),
            "confidence": float(val.get("confidence", 0)),
            "evidence": list(val.get("evidence", [])),
        }
    return {
        "label": str(val) if val else DEFAULT_LABEL,
        "confidence": 0.0,
        "evidence": [],
    }


def _calculate_completeness(profile_data: dict) -> float:
    """
    计算画像完整度 (0.0 ~ 1.0)

    What: 遍历 6 个维度，统计 label 有效的维度数
    Why: 驱动 needs_initial_survey 判断（完整度低于阈值需摸底问答）
    """
    if not profile_data:
        return 0.0
    valid = 0
    for dim in PROFILE_DIMENSIONS:
        entry = profile_data.get(dim)
        if isinstance(entry, dict) and entry.get("label", "").strip() not in ("", DEFAULT_LABEL):
            valid += 1
        elif isinstance(entry, str) and entry.strip() not in ("", DEFAULT_LABEL):
            valid += 1
    return round(valid / len(PROFILE_DIMENSIONS), 2)


def _merge_dimension(current: dict, updates: dict) -> tuple[dict, dict | None]:
    """
    合并单个维度的更新，返回 (新维度数据, changelog 条目或 None)

    What: 根据 updates 中的 label / confidence_delta / evidence 逐字段合并
    Why: 统一画像更新的合并逻辑，避免 update_profile 中重复代码

    Args:
        current: 当前维度的 {label, confidence, evidence} 结构
        updates: 新数据，每项可选:
            - label: str | None     → 新标签
            - confidence_delta: float → 置信度变化量
            - evidence: str         → 新增证据文本

    Returns:
        tuple[dict, dict | None]: (合并后的维度数据, changelog 条目或 None)
    """
    old_label = current.get("label", DEFAULT_LABEL)
    old_confidence = float(current.get("confidence", 0))

    new_label = str(updates.get("label", old_label)) if updates.get("label") is not None else old_label
    evidence_text = updates.get("evidence")

    # ── confidence 加权合并 ──
    confidence_delta = updates.get("confidence_delta")
    new_confidence = old_confidence
    if confidence_delta is not None:
        try:
            suggested = max(0.0, min(100.0, old_confidence + float(confidence_delta) * 30))
            new_confidence = round(old_confidence * 0.7 + suggested * 0.3, 1)
        except (TypeError, ValueError):
            pass

    # ── evidence 追加 ──
    evidence = list(current.get("evidence", []))
    if evidence_text and isinstance(evidence_text, str) and evidence_text.strip():
        ev = evidence_text.strip()
        if ev not in evidence:
            evidence.append(ev)
        if len(evidence) > _MAX_EVIDENCE:
            evidence = evidence[-_MAX_EVIDENCE:]

    merged = {
        "label": new_label,
        "confidence": new_confidence,
        "evidence": evidence,
    }

    # ── 构建 changelog 条目 ──
    label_changed = new_label != old_label
    confidence_changed = abs(new_confidence - old_confidence) > 0.05
    if not label_changed and not confidence_changed:
        return merged, None

    return merged, {
        "old_label": old_label,
        "old_confidence": old_confidence,
        "new_label": new_label,
        "new_confidence": new_confidence,
    }


# ── 公开 API ─────────────────────────────────────────────────────

async def get_or_create_profile(user_id: str, db):
    """
    获取或创建用户画像行

    What: 确保 user_profiles 表中存在该用户的记录，不存在则创建初始行
    Why: update_profile / calibrate_dimension 等写入操作的前置步骤

    Args:
        user_id: 用户 ID
        db: 异步 SQLAlchemy session

    Returns:
        UserProfile: ORM 实例
    """
    from sqlalchemy import select
    from app.models.user_profile import UserProfile

    uid = _safe_int(user_id)
    if uid == 0:
        raise ValueError(f"无效的 user_id: {user_id!r}")

    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == uid)
    )
    profile = result.scalar_one_or_none()

    if profile is None:
        profile = UserProfile(
            user_id=uid,
            profile_data={},
            completeness=0.0,
        )
        db.add(profile)
        await db.flush()
        logger.info(f"[ProfileService] 为用户 {user_id} 创建画像初始记录")

    return profile


async def get_user_profile(user_id: str) -> dict:
    """
    获取用户画像

    What: 查询 UserProfile 表，返回结构化画像快照和元数据
    Why: Profile Agent + Feedback Agent 的画像数据入口

    Args:
        user_id: 用户 ID

    Returns:
        dict: {
            profile: {dim: {label, confidence, evidence}, ...},
            total_feedback_count: int,
            last_calibrated_at: str | None,        ← 暂返回 None，需模型新增字段
            needs_initial_survey: bool,
            initial_survey_question: None,         ← 第一阶段固定 None
        }
    """
    try:
        from sqlalchemy import func, select
        from app.db.session import get_db as _get_db
        from app.models.feedback_session import FeedbackSession
        from app.models.user_profile import UserProfile

        async for db in _get_db():
            # 1. 查询或创建画像行
            profile_row = await get_or_create_profile(user_id, db)
            raw_data = profile_row.profile_data or {}
            completeness = profile_row.completeness or 0.0

            # 2. 规范化 6 维度 → 统一 {label, confidence, evidence}
            profile_dict = OrderedDict()
            for dim in PROFILE_DIMENSIONS:
                profile_dict[dim] = _ensure_dimension_struct(raw_data.get(dim))

            # 3. 统计反馈次数
            uid = _safe_int(user_id)
            count_result = await db.execute(
                select(func.count(FeedbackSession.id)).where(
                    FeedbackSession.user_id == uid
                )
            )
            total_feedback_count = count_result.scalar() or 0

            # 4. 判断是否需要摸底问答
            if completeness == 0.0 and total_feedback_count == 0:
                needs_initial_survey = True
            else:
                needs_initial_survey = completeness < _COMPLETENESS_THRESHOLD

            return {
                "profile": dict(profile_dict),
                "total_feedback_count": total_feedback_count,
                "last_calibrated_at": None,
                "needs_initial_survey": needs_initial_survey,
                "initial_survey_question": None,
            }
    except Exception:
        logger.warning(
            f"[ProfileService] DB 查询失败，使用默认画像 (user_id={user_id})",
            exc_info=True,
        )

    # 默认画像
    default_profile = OrderedDict()
    for dim in PROFILE_DIMENSIONS:
        default_profile[dim] = {"label": DEFAULT_LABEL, "confidence": 0.0, "evidence": []}
    return {
        "profile": dict(default_profile),
        "total_feedback_count": 0,
        "last_calibrated_at": None,
        "needs_initial_survey": True,
        "initial_survey_question": None,
    }


async def update_profile(user_id: str, updates: dict) -> dict:
    """
    增量更新用户画像

    What: 接收 Feedback Agent 或其他来源的画像增量，合并写入 UserProfile
    Why: 支持 label 更新、confidence_delta 加权、evidence 追加，自动重算 completeness

    Args:
        user_id: 用户 ID
        updates: 待更新的维度字典，格式:
            {
                "<dimension>": {
                    "label": "str?",            ← 新标签（可选）
                    "confidence_delta": float?, ← 置信度变化量（可选）
                    "evidence": "str?",         ← 新增证据文本（可选）
                },
                ...
            }

    Returns:
        dict: {
            success: bool,             ← 操作是否成功
            profile_changed: bool,     ← 是否有维度发生变更
            profile_changelog: [       ← 本次变更明细
                {dimension, old_label, old_confidence, new_label, new_confidence}
            ],
        }
    """
    if not updates:
        logger.info(f"[ProfileService] 无更新内容 (user_id={user_id})")
        return {"success": True, "profile_changed": False, "profile_changelog": []}

    try:
        from app.db.session import get_db as _get_db

        async for db in _get_db():
            profile_row = await get_or_create_profile(user_id, db)
            current_data = dict(profile_row.profile_data or {})

            changelog = []
            any_changed = False

            for dim in PROFILE_DIMENSIONS:
                dim_updates = updates.get(dim)
                if not dim_updates or not isinstance(dim_updates, dict):
                    continue

                old = _ensure_dimension_struct(current_data.get(dim))
                merged, entry = _merge_dimension(old, dim_updates)

                if merged != old:
                    any_changed = True
                    current_data[dim] = merged
                    if entry:
                        changelog.append({"dimension": dim, **entry})

            if not any_changed:
                return {"success": True, "profile_changed": False, "profile_changelog": []}

            # 重算完整度
            completeness = _calculate_completeness(current_data)
            profile_row.profile_data = current_data
            profile_row.completeness = completeness
            await db.commit()

            logger.info(
                f"[ProfileService] 画像更新成功 "
                f"(user_id={user_id}, dims={list(updates.keys())}, completeness={completeness})"
            )
            return {"success": True, "profile_changed": True, "profile_changelog": changelog}
    except Exception as exc:
        logger.warning(
            f"[ProfileService] 画像更新失败 (user_id={user_id}): {exc}", exc_info=True
        )
        return {"success": False, "profile_changed": False, "profile_changelog": []}


async def calibrate_dimension(user_id: str, dimension: str, comment: str) -> dict:
    """
    校准指定画像维度

    What: 用户对某维度的判断点踩时，将该维度置信度减半
    Why: 实现合约 /api/v1/profile/calibrate/{dimension} 的后端逻辑

    Args:
        user_id: 用户 ID
        dimension: 维度名（PROFILE_DIMENSIONS 之一）
        comment: 用户校准说明文本

    Returns:
        dict: {
            dimension, old_label, old_confidence,
            new_label, new_confidence, message
        }
    """
    if dimension not in PROFILE_DIMENSIONS:
        return {
            "dimension": dimension,
            "old_label": DEFAULT_LABEL,
            "old_confidence": 0.0,
            "new_label": DEFAULT_LABEL,
            "new_confidence": 0.0,
            "message": f"维度 '{dimension}' 不存在，有效维度：{', '.join(PROFILE_DIMENSIONS)}",
        }

    try:
        from app.db.session import get_db as _get_db

        async for db in _get_db():
            profile_row = await get_or_create_profile(user_id, db)
            current_data = dict(profile_row.profile_data or {})
            old = _ensure_dimension_struct(current_data.get(dimension))

            old_label = old["label"]
            old_confidence = old["confidence"]

            # 置信度减半（用户点踩）
            new_confidence = round(old_confidence * 0.5, 1)
            new_label = old_label  # 标签不变

            current_data[dimension] = {
                "label": new_label,
                "confidence": new_confidence,
                "evidence": old.get("evidence", []),
            }

            completeness = _calculate_completeness(current_data)
            profile_row.profile_data = current_data
            profile_row.completeness = completeness
            await db.commit()

            message = (
                f"收到你的反馈。{dimension} 维度 confidence 已从 {old_confidence} "
                f"下调至 {new_confidence}，接下来会通过更多反馈重新评估这个维度。"
            )

            logger.info(
                f"[ProfileService] 维度校准成功 "
                f"(user_id={user_id}, dim={dimension}, {old_confidence}→{new_confidence})"
            )

            return {
                "dimension": dimension,
                "old_label": old_label,
                "old_confidence": old_confidence,
                "new_label": new_label,
                "new_confidence": new_confidence,
                "message": message,
            }
    except Exception as exc:
        logger.warning(
            f"[ProfileService] 维度校准失败 (user_id={user_id}, dim={dimension}): {exc}",
            exc_info=True,
        )
        return {
            "dimension": dimension,
            "old_label": DEFAULT_LABEL,
            "old_confidence": 0.0,
            "new_label": DEFAULT_LABEL,
            "new_confidence": 0.0,
            "message": f"校准失败，请稍后再试。",
        }


async def get_profile_history(user_id: str, limit: int = 20) -> list[dict]:
    """
    获取画像变更历史

    What: 从 FeedbackSession 表推导画像变更记录，按时间倒序
    Why: 实现合约 GET /api/v1/profile/history 的后端逻辑

    Args:
        user_id: 用户 ID
        limit: 返回条数上限，默认 20

    Returns:
        list[dict]: [
            {timestamp: datetime, source: str, changes: [str]},
            ...
        ]
    """
    try:
        from sqlalchemy import desc, select
        from app.db.session import get_db as _get_db
        from app.models.feedback_session import FeedbackSession

        async for db in _get_db():
            uid = _safe_int(user_id)
            result = await db.execute(
                select(FeedbackSession)
                .where(FeedbackSession.user_id == uid)
                .where(FeedbackSession.content.isnot(None))
                .order_by(desc(FeedbackSession.created_at))
                .limit(limit)
            )
            sessions = result.scalars().all()

            history = []
            for session in sessions:
                content = session.content or {}
                profile_updates = content.get("profile_updates")
                if not profile_updates or not isinstance(profile_updates, dict):
                    continue

                changes = []
                for dim, val in profile_updates.items():
                    if isinstance(val, dict):
                        old_l = val.get("old_label")
                        new_l = val.get("new_label", val.get("label", DEFAULT_LABEL))
                        old_c = val.get("old_confidence", 0)
                        new_c = val.get("new_confidence", val.get("confidence", 0))
                        # 仅当显式包含 old_label 时视为变更记录；否则视为原始维度值
                        if old_l is not None:
                            if old_l != new_l or abs(new_c - old_c) > 0.05:
                                changes.append(f"{dim}: {old_l} → {new_l} ({new_c:+.0f}%)")
                        else:
                            changes.append(f"{dim}: {new_l} (置信度 {new_c})")
                    elif val:
                        changes.append(f"{dim}: → {val}")

                if changes:
                    history.append({
                        "timestamp": session.created_at,
                        "source": f"feedback_session:{session.id}",
                        "changes": changes,
                    })

            return history
    except Exception as exc:
        logger.warning(
            f"[ProfileService] 查询画像历史失败 (user_id={user_id}): {exc}",
            exc_info=True,
        )
        return []
