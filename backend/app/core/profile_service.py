
"""
画像服务模块（stub 版本）

What: 提供画像查询和更新能力，供 Feedback Agent 联动
Why: Step 6 Profile Agent 可能不存在，此处用 stub 实现降级；
     Step 6 完成后替换为真实实现即可
How: 所有操作 try/except 兜底，不因依赖缺失而崩溃
"""

import logging

logger = logging.getLogger(__name__)


async def get_user_profile(user_id: str) -> dict:
    """
    获取用户画像（stub 版本）

    What: 尝试从 UserProfile 表查询真实画像，失败则返回默认画像
    Why: Profile Agent 未就绪时系统仍可运行

    Args:
        user_id: 用户 ID

    Returns:
        dict: 包含 learning_style、best_time_slots 等维度的画像字典
    """
    try:
        # 尝试从数据库查询真实画像
        # 如果 UserProfile 表或 DB session 不可用，直接走 stub
        from sqlalchemy import select
        from app.db.session import get_db as _get_db
        from app.models.user_profile import UserProfile

        # 获取异步 DB session
        async for db in _get_db():
            result = await db.execute(
                select(UserProfile).where(UserProfile.user_id == int(user_id))
            )
            profile = result.scalar_one_or_none()
            if profile and profile.profile_data:
                # 将 profile_data JSON 展平为简单键值对
                flat = {}
                for key, val in profile.profile_data.items():
                    if isinstance(val, dict):
                        flat[key] = val.get("label", str(val))
                    else:
                        flat[key] = str(val)
                flat["total_feedback_count"] = 0  # 需单独查询 counts
                flat["recent_feedback_history"] = []
                return flat
            break
    except Exception:
        logger.warning(f"[ProfileStub] DB 查询失败，使用默认画像 (user_id={user_id})")

    # 默认画像（所有维度为"未知"）
    return {
        "learning_style": "未知",
        "best_time_slots": "未知",
        "learning_rhythm": "未知",
        "feedback_baseline": "未知",
        "persistence": "未知",
        "knowledge_retention": "未知",
        "total_feedback_count": 0,
        "recent_feedback_history": [],
    }


async def update_profile(user_id: str, updates: dict) -> bool:
    """
    更新用户画像（stub 版本）

    What: 尝试写入 UserProfile 表，失败仅日志记录
    Why: Step 6 完成后替换为真实实现

    Args:
        user_id: 用户 ID
        updates: 待更新的画像维度字典

    Returns:
        bool: 是否更新成功
    """
    if not updates:
        logger.info(f"[ProfileStub] 无更新内容 (user_id={user_id})")
        return True

    try:
        from sqlalchemy import select, update as sa_update
        from app.db.session import get_db as _get_db
        from app.db.base import Base
        from app.models.user_profile import UserProfile

        async for db in _get_db():
            result = await db.execute(
                select(UserProfile).where(UserProfile.user_id == int(user_id))
            )
            profile = result.scalar_one_or_none()
            if profile:
                # 合并已有 profile_data 与新 updates
                current_data = profile.profile_data or {}
                for key, value in updates.items():
                    if isinstance(value, dict):
                        # 如果已存在该维度，合并 confidence
                        if key in current_data and isinstance(current_data[key], dict):
                            current_data[key].update(value)
                        else:
                            current_data[key] = value
                    else:
                        current_data[key] = value
                profile.profile_data = current_data
                await db.commit()
                logger.info(f"[ProfileStub] 画像更新成功 (user_id={user_id}, updates={updates})")
            else:
                logger.info(
                    f"[ProfileStub] 用户画像不存在，跳过更新 (user_id={user_id})"
                )
            break
        return True
    except Exception as exc:
        logger.warning(
            f"[ProfileStub] 画像更新失败 (user_id={user_id}): {exc}"
        )
        return False
