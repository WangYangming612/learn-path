"""
Schedule Agent 子图：协调多个活跃学习计划并生成每日任务。

架构说明：
  子图（含审查 loop + 落库）：
      START → load_context → generate_schedule → schedule_review
          ├─ pass → persist_schedule → END
          └─ fail (未达上限) → retry generate_schedule
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Literal

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select, desc

from app.agents.review import get_reviewer, register_reviewer
from app.agents.state import ScheduleAgentState
from app.core.profile_service import get_user_profile, PROFILE_DIMENSIONS, DEFAULT_LABEL
from app.core.task_service import create_daily_tasks
from app.db.session import get_db
from app.llm.client import llm_client
from app.llm.prompts.schedule import SCHEDULE_GUIDE_SYSTEM_PROMPT, SCHEDULE_GUIDE_USER_PROMPT
from app.models.daily_task import DailyTask
from app.models.knowledge_node import KnowledgeNode
from app.models.plan import Plan
from app.schemas.schedule import LLMScheduleOutput

logger = logging.getLogger(__name__)
DEFAULT_DAILY_BUDGET = 60
MIN_TASK_MINUTES = 5
MAX_REVIEW_ATTEMPTS = 3
_REQUIRED_GUIDE_SECTIONS = ("## 重点理解", "## 建议练习", "## 搜索关键词")


def _profile_value(profile: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = profile.get(key)
        if isinstance(value, dict):
            value = value.get("label", value.get("value"))
        if value not in (None, "", "未知"):
            return value
    return None


def _daily_budget(profile: dict[str, Any], supplied_budget: int | None) -> int:
    if supplied_budget:
        return supplied_budget
    value = _profile_value(profile, "daily_budget", "daily_available_minutes")
    try:
        return max(int(value), MIN_TASK_MINUTES)
    except (TypeError, ValueError):
        return DEFAULT_DAILY_BUDGET


def _preferred_start(profile: dict[str, Any]) -> time:
    value = str(_profile_value(profile, "best_time_slots", "best_time", "time_preference") or "")
    if "早" in value or "morning" in value.lower():
        return time(8, 0)
    if "午" in value or "afternoon" in value.lower():
        return time(14, 0)
    if "晚" in value or "night" in value.lower() or "evening" in value.lower():
        return time(19, 0)
    return time(19, 0)


def _plan_priority(plan: Plan) -> int:
    """返回持久化计划优先级，异常值按中优先级处理。"""

    try:
        priority = int(plan.priority)
    except (TypeError, ValueError):
        priority = 2
    return priority if priority in (1, 2, 3) else 2


def _fallback_guide(node_name, duration_minutes, node_description=None):
    """LLM 不可用时学习指引兜底"""
    node_desc = (node_description or '').strip()
    focus = node_desc or ('学习' + node_name)
    NL = chr(10)
    parts = [
        '## 重点理解',
        focus,
        '',
        '## 建议练习',
        '- 用 ' + str(duration_minutes) + ' 分钟精读并理解核心概念',
        '- 尝试用自己的语言总结 3 个关键点',
        '- 完成 2~3 道相关练习题',
        '',
        '## 搜索关键词',
        node_name + ', 教程, 练习',
    ]
    return NL.join(parts)


async def _generate_guide(plan: Plan, node: KnowledgeNode, duration_minutes: int) -> str:
    try:
        chat_model = llm_client.get_chat_model(temperature=0.4, timeout=30)
        response = await chat_model.ainvoke([
            {"role": "system", "content": SCHEDULE_GUIDE_SYSTEM_PROMPT},
            {"role": "user", "content": SCHEDULE_GUIDE_USER_PROMPT.format(
                plan_title=plan.title,
                node_name=node.name,
                duration_minutes=duration_minutes,
                node_description=node.description or "无",
            )},
        ])
        content = str(response.content).strip()
        if content:
            return content
        return _fallback_guide(node.name, duration_minutes, node.description)
    except Exception as exc:
        logger.warning("[ScheduleAgent] 学习指引生成失败，使用兜底内容: %s", exc)
        return _fallback_guide(node.name, duration_minutes, node.description)


def _parse_target_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and value:
        return date.fromisoformat(value)
    return date.today()


def _empty_schedule_result(target_date: date) -> dict[str, Any]:
    return {
        "scheduled_date": str(target_date),
        "tasks": [],
        "total_minutes": 0,
        "overflow_detected": False,
    }


def _compress_durations(requested: list[int], budget: int) -> tuple[list[int], bool]:
    """按预算比例压缩时长，必要时从末尾再削到不超预算。"""

    total_requested = sum(requested)
    overflow_detected = bool(total_requested > budget and total_requested)
    if not overflow_detected:
        return requested, False

    durations = [max(MIN_TASK_MINUTES, round(item * budget / total_requested)) for item in requested]
    overflow = sum(durations) - budget
    for index in range(len(durations) - 1, -1, -1):
        reducible = durations[index] - MIN_TASK_MINUTES
        reduction = min(reducible, overflow)
        durations[index] -= reduction
        overflow -= reduction
        if overflow <= 0:
            break
    return durations, True
# ── LLM 排期上下文格式化（画像、计划、反馈） ──────────────

def _format_profile_for_llm(profile: dict[str, Any]) -> str:
    """将用户画像格式化为 LLM 可读的摘要文本"""
    dim_names = {
        "learning_style": "学习风格",
        "best_time_slots": "最佳学习时段",
        "learning_rhythm": "学习节奏偏好",
        "feedback_baseline": "反馈基线",
        "persistence": "持续力特征",
        "knowledge_retention": "知识保留特征",
    }
    lines = []
    for dim in PROFILE_DIMENSIONS:
        entry = profile.get(dim, {})
        if isinstance(entry, dict):
            label = entry.get("label", DEFAULT_LABEL)
            confidence = entry.get("confidence", 0)
            display_name = dim_names.get(dim, dim)
            if label not in (DEFAULT_LABEL, ""):
                lines.append(f"  - {display_name}: {label} (置信度 {confidence}%)")
            else:
                lines.append(f"  - {display_name}: 未知")
    return "\n".join(lines) if lines else "  （无画像数据）"


def _format_plans_for_llm(plans_with_nodes: list[dict[str, Any]]) -> str:
    """将活跃计划及知识节点格式化为 LLM 可读文本"""
    if not plans_with_nodes:
        return "  （当前无活跃计划）"
    lines = []
    for p in plans_with_nodes:
        priority_label = {1: "高", 2: "中", 3: "低"}.get(p.get("priority", 2), "中")
        lines.append(f"  - [{p['plan_title']}] 优先级={priority_label}, 每日预算={p['daily_budget']}分钟")
        for node in p.get("nodes", []):
            lines.append(f"    * 节点: {node['name']}  |  预计: {node['estimated_minutes']}分钟  |  ID: {node['id']}")
            if node.get("description"):
                lines.append(f"      描述: {node['description']}")
    return "\n".join(lines)


def _format_feedback_for_llm(feedback_records: list[dict[str, Any]]) -> str:
    """将近期反馈信号格式化为 LLM 可读文本"""
    if not feedback_records:
        return "  （近 7 天无反馈记录）"
    lines = []
    for fb in feedback_records:
        signal_label = {
            "stuck": "卡住了",
            "too_easy": "太简单",
            "normal": "节奏合适",
            "need_practice": "需要练习",
        }.get(fb.get("signal"), fb.get("signal", "未知"))
        lines.append(f"  - [{fb.get('date', '?')}] {fb.get('node_name', '?')} -> {signal_label}")
    return "\n".join(lines)


def _parse_time_str(time_str: str) -> tuple[int, int]:
    """解析 "HH:MM" 格式时间字符串为 (时, 分)"""
    try:
        parts = time_str.strip().split(":")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return 19, 0





# ── 审查回路 ─────────────────────────────────────────────────────

def _collect_review_issues(planned_items: list[dict[str, Any]], budget: int) -> tuple[list[str], list[str]]:
    """收集排期草案问题与修改建议。"""

    issues: list[str] = []
    suggestions: list[str] = []

    if budget < MIN_TASK_MINUTES:
        issues.append("可用预算不足")
        suggestions.append(f"将 daily_budget 提升到至少 {MIN_TASK_MINUTES} 分钟")

    if not planned_items:
        issues.append("排期结果不能为空")
        suggestions.append("确保存在可排期的活跃计划与知识节点")
        return issues, suggestions

    total_duration = 0
    previous_end: time | None = None
    seen_pairs: set[tuple[Any, Any]] = set()

    for index, item in enumerate(planned_items):
        plan_id = item.get("plan_id")
        knowledge_node_id = item.get("knowledge_node_id")
        start_time = item.get("start_time")
        end_time = item.get("end_time")
        duration_minutes = item.get("duration_minutes")
        guide_content = str(item.get("guide_content") or "").strip()

        if plan_id is None:
            issues.append(f"任务[{index}]缺少 plan_id")
            suggestions.append(f"为任务[{index}]补充所属计划")
        if duration_minutes is None or int(duration_minutes) < MIN_TASK_MINUTES:
            issues.append(f"任务[{index}]时长过短")
            suggestions.append(f"将任务[{index}]时长调整到至少 {MIN_TASK_MINUTES} 分钟")
        if not guide_content:
            issues.append(f"任务[{index}]指引不能为空")
            suggestions.append(f"为任务[{index}]重新生成学习指引")
        else:
            missing = [section for section in _REQUIRED_GUIDE_SECTIONS if section not in guide_content]
            if missing:
                issues.append(f"任务[{index}]指引缺少小节: {', '.join(missing)}")
                suggestions.append(f"任务[{index}]指引需包含重点理解 / 建议练习 / 搜索关键词")
        if start_time is None or end_time is None:
            issues.append(f"任务[{index}]时间段不能为空")
            suggestions.append(f"为任务[{index}]补全 start_time / end_time")
        elif previous_end is not None and start_time < previous_end:
            issues.append(f"任务[{index}]时间段与前序任务重叠")
            suggestions.append("按顺序重排时间段，避免重叠")
        if (plan_id, knowledge_node_id) in seen_pairs:
            issues.append(f"任务[{index}]重复排期")
            suggestions.append("同一计划-知识点组合只排一次")

        seen_pairs.add((plan_id, knowledge_node_id))
        if end_time is not None:
            previous_end = end_time
        if duration_minutes is not None:
            total_duration += int(duration_minutes)

    if total_duration > budget:
        issues.append("任务总时长超过可用预算")
        suggestions.append("按优先级压缩任务时长或减少任务数量")

    return issues, suggestions


async def schedule_reviewer(raw_output: dict, user_input: str, context: dict) -> dict:
    """
    Schedule Agent 输出质量审查器

    What: 审查排期草案的预算、时段、去重与指引结构
    Why: 作为 Agent Loop 中的审查环节，防止写入无效排期
    """
    del user_input  # 排期审查不依赖用户原话
    planned_items = list(raw_output.get("planned_items") or [])
    budget = int(context.get("budget") or raw_output.get("budget") or DEFAULT_DAILY_BUDGET)
    issues, suggestions = _collect_review_issues(planned_items, budget)
    return {
        "verdict": "fail" if issues else "pass",
        "issues": issues,
        "suggestions": suggestions,
    }


async def schedule_review_node(state: ScheduleAgentState) -> dict[str, Any]:
    """
    Schedule Agent 审查网关节点

    What: 调用注册的审查器检查 planned_items，决定放行或重试
    Why: 实现 Agent Loop 中的审查环节
    """
    if state.get("skip_reason"):
        return {
            "raw_agent_output": {"skipped": True, "reason": state.get("skip_reason")},
            "review_attempts": state.get("review_attempts", 0),
            "review_results": list(state.get("review_results", [])),
            "review_verdict": "pass",
        }

    context = state.get("schedule_context") or {}
    planned_items = list(state.get("planned_items") or [])
    raw_output = {
        "planned_items": planned_items,
        "budget": context.get("budget", DEFAULT_DAILY_BUDGET),
        "overflow_detected": bool(state.get("overflow_detected", False)),
    }

    review_attempts = state.get("review_attempts", 0) + 1
    review_max = state.get("review_max_attempts", MAX_REVIEW_ATTEMPTS)
    review_results = list(state.get("review_results", []))

    reviewer = get_reviewer("schedule_agent")
    if reviewer:
        try:
            result = await reviewer(
                raw_output,
                "",
                {
                    "agent_type": state.get("agent_type", "schedule"),
                    "budget": raw_output["budget"],
                },
            )
        except Exception as exc:
            logger.warning("[ScheduleAgent] 审查器执行异常: %s", exc)
            result = {"verdict": "pass", "issues": [f"审查器异常: {exc!s}"], "suggestions": []}
    else:
        result = {"verdict": "pass", "issues": ["审查器未注册，默认放行"], "suggestions": []}

    review_results.append({
        "attempt": review_attempts,
        "verdict": result.get("verdict", "pass"),
        "issues": result.get("issues", []),
        "suggestions": result.get("suggestions", []),
    })

    verdict = result.get("verdict", "pass")
    is_final = verdict == "pass" or review_attempts >= review_max
    if is_final and verdict != "pass":
        logger.info(
            "[ScheduleAgent] 审查未通过但已达重试上限 "
            "(attempts=%s/%s, issues=%s)",
            review_attempts,
            review_max,
            result.get("issues", []),
        )

    return {
        "raw_agent_output": raw_output,
        "review_attempts": review_attempts,
        "review_results": review_results,
        "review_verdict": "pass" if is_final else "fail",
    }


def review_router(state: ScheduleAgentState) -> Literal["retry", "end"]:
    """根据 review_verdict 决定重试生成或进入落库。"""

    if state.get("review_verdict", "") == "pass":
        return "end"
    return "retry"


# ── 子图节点 ─────────────────────────────────────────────────────

async def load_schedule_context(state: ScheduleAgentState) -> dict[str, Any]:
    """加载用户预算、活跃计划、可排期知识节点、用户画像及近期反馈信号"""
    try:
        user_id = int(state.get("user_id", "0"))
        target_date = _parse_target_date(state.get("scheduled_date"))
        profile_full = await get_user_profile(str(user_id))
        profile = profile_full.get("profile", {})
        budget = _daily_budget(profile, state.get("daily_budget"))
        start_at = datetime.combine(target_date, _preferred_start(profile))

        async for db in get_db():
            from app.models.user import User
            user_result = await db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()
            if state.get("daily_budget") is None and user:
                budget = max(user.daily_available_minutes, MIN_TASK_MINUTES)

            plans_result = await db.execute(
                select(Plan).where(Plan.user_id == user_id, Plan.status == "active")
            )
            plans = sorted(plans_result.scalars().all(), key=lambda p: (_plan_priority(p), p.id))

            # 优先使用计划的 daily_budget 总和（而非前端传入的 user.daily_available_minutes 默认值60）
            if plans:
                plan_budget = sum(p.daily_budget for p in plans)
                budget = max(plan_budget, MIN_TASK_MINUTES)

            if not plans:
                return _build_skip_result(target_date, "当前没有可排期的活跃学习计划。")

            # 获取所有节点及其完成状态
            completed_node_result = await db.execute(
                select(DailyTask.knowledge_node_id).where(
                    DailyTask.user_id == user_id,
                    DailyTask.status == "completed",
                    DailyTask.knowledge_node_id.is_not(None),
                )
            )
            completed_node_ids = set(completed_node_result.scalars().all())

            # 构建计划+节点信息
            plans_with_nodes = []
            candidates = []
            for plan in plans:
                node_result = await db.execute(
                    select(KnowledgeNode)
                    .where(KnowledgeNode.plan_id == plan.id)
                    .order_by(KnowledgeNode.order_index.asc(), KnowledgeNode.id.asc())
                )
                nodes = list(node_result.scalars().all())
                plan_nodes_info = []
                for node in nodes:
                    plan_nodes_info.append({
                        "id": node.id,
                        "name": node.name,
                        "description": node.description,
                        "estimated_minutes": max(node.estimated_minutes or MIN_TASK_MINUTES, MIN_TASK_MINUTES),
                        "completed": node.id in completed_node_ids,
                    })
                plans_with_nodes.append({
                    "plan_id": plan.id,
                    "plan_title": plan.title,
                    "daily_budget": plan.daily_budget,
                    "priority": _plan_priority(plan),
                    "nodes": plan_nodes_info,
                })
                # 每个计划取第一个未完成节点作为候选
                for node in plan_nodes_info:
                    if not node["completed"]:
                        candidates.append({
                            "plan_id": plan.id,
                            "plan_title": plan.title,
                            "plan_priority": _plan_priority(plan),
                            "daily_budget": plan.daily_budget,
                            "node_id": node["id"],
                            "node_name": node["name"],
                            "node_description": node["description"],
                            "estimated_minutes": node["estimated_minutes"],
                        })
                        break

            if not candidates:
                return _build_skip_result(target_date, "当前活跃计划暂无可排期的知识节点。")

            # 加载近期反馈信号（7天内）
            recent_feedback_records = []
            try:
                db_desc = desc
                feedback_result = await db.execute(
                    select(DailyTask)
                    .where(
                        DailyTask.user_id == user_id,
                        DailyTask.scheduled_date >= target_date - timedelta(days=7),
                        DailyTask.feedback_signal.is_not(None),
                    )
                    .order_by(db_desc(DailyTask.scheduled_date))
                )
                for ftask in feedback_result.scalars().all():
                    recent_feedback_records.append({
                        "date": str(ftask.scheduled_date),
                        "signal": ftask.feedback_signal,
                        "node_name": ftask.title,
                        "confidence_delta": ftask.feedback_confidence_delta or 0,
                    })
            except Exception as exc:
                logger.warning("[ScheduleAgent] 加载反馈记录失败: %s", exc)

            # 格式化上下文供 LLM 使用
            profile_summary = _format_profile_for_llm(profile)
            plans_summary = _format_plans_for_llm(plans_with_nodes)
            feedback_summary = _format_feedback_for_llm(recent_feedback_records)

            return {
                "scheduled_date": target_date,
                "skip_reason": None,
                "overflow_detected": False,
                "planned_items": [],
                "schedule_result": None,
                "review_attempts": 0,
                "review_results": [],
                "review_verdict": "",
                "schedule_context": {
                    "user_id": user_id,
                    "budget": budget,
                    "start_at": start_at.isoformat(),
                    "preferred_start": str(start_at.time()),
                    "candidates": candidates,
                    "profile_summary": profile_summary,
                    "plans_summary": plans_summary,
                    "feedback_summary": feedback_summary,
                    "plans_with_nodes": plans_with_nodes,
                    "raw_profile": profile,
                },
            }
    except Exception as exc:
        logger.exception("[ScheduleAgent] load_schedule_context 失败: %s", exc)
        target_date = _parse_target_date(state.get("scheduled_date"))
        return _build_skip_result(target_date, "今日任务生成失败，请稍后重试。")
def _build_skip_result(target_date, reason):
    return {
        "scheduled_date": target_date,
        "skip_reason": reason,
        "schedule_context": None,
        "planned_items": [],
        "overflow_detected": False,
        "schedule_result": {"tasks": [], "total_minutes": 0, "overflow_detected": False, "scheduled_date": str(target_date)},
        "review_attempts": 0,
    }


async def llm_generate_schedule(state: ScheduleAgentState) -> dict[str, Any]:
    """LLM驱动排期：直接用 httpx 调用 DeepSeek API"""
    if state.get('skip_reason'): return {}
    context = state.get('schedule_context') or {}
    budget = int(context.get('budget', DEFAULT_DAILY_BUDGET))
    pref_start = str(context.get('preferred_start', '19:00'))
    use_fb = int(state.get('review_attempts', 0) or 0) > 0
    if use_fb:
        return await _fallback_llm_schedule(state, context, budget)
    try:
        import httpx
        from app.core.config import settings
        from app.schemas.schedule import LLMScheduleOutput, ScheduleTaskItem

        today = str(_parse_target_date(state.get('scheduled_date')))
        ps = context.get('profile_summary', '-')
        ls = context.get('plans_summary', '-')
        fs = context.get('feedback_summary', '-')

        NL = chr(10)
        parts = [SCHEDULE_LLM_SYSTEM_PROMPT, '', '## 当前输入', '',
            '今天日期：' + today,
            '可用预算：' + str(budget) + ' 分钟',
            '偏好起始时间：' + pref_start, '',
            '===== 用户画像 =====', ps, '',
            '===== 活跃计划 =====', ls, '',
            '===== 近期反馈 =====', fs, '',
            '## 输出要求',
            '请严格输出JSON格式。输出格式：',
            '{"reasoning": "推理", "replan_decisions": [], "tasks": [{"plan_id": 1, "knowledge_node_id": 1, "title": "任务", "duration_minutes": 60}]}',
        ]
        user_content = NL.join(parts)

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                settings.LLM_BASE_URL + '/chat/completions',
                json={'model': 'deepseek-chat', 'messages': [
                    {'role': 'system', 'content': '你是一位智能学习排期专家。以JSON格式输出今日最优排期。'},
                    {'role': 'user', 'content': user_content},
                ], 'temperature': 0.3, 'max_tokens': 2000},
                headers={'Authorization': 'Bearer ' + settings.LLM_API_KEY, 'Content-Type': 'application/json'},
            )

        if resp.status_code != 200:
            raise RuntimeError('HTTP ' + str(resp.status_code) + ': ' + resp.text[:200])

        raw = resp.json()['choices'][0]['message']['content'].strip()
        if raw.startswith('`'):
            raw = raw.split('\n', 1)[-1] if '\n' in raw else raw[3:]
            if raw.endswith('`'): raw = raw[:-3]
            raw = raw.strip()

        import json as _json
        parsed = _json.loads(raw)
        reason = str(parsed.get('reasoning', ''))
        tasks_raw = parsed.get('tasks', [])
        if not tasks_raw: raise ValueError('LLM返回空任务列表')

        valid = []
        for t in tasks_raw:
            valid.append(ScheduleTaskItem(
                plan_id=int(t['plan_id']),
                knowledge_node_id=int(t['knowledge_node_id']),
                title=str(t.get('title', '')),
                duration_minutes=int(t.get('duration_minutes', 30)),
            ))
        llm_out = LLMScheduleOutput(reasoning=reason, replan_decisions=parsed.get('replan_decisions', []), tasks=valid)

        logger.info('[ScheduleAgent] LLM排期成功: %d 个任务, reason=%s', len(llm_out.tasks), reason[:60])

        cmap = {c['node_id']: c for c in context.get('candidates', [])}
        items = []; ch, cm = _parse_time_str(pref_start)
        for t in llm_out.tasks:
            c = cmap.get(t.knowledge_node_id)
            if not c: continue
            used = sum(i['duration_minutes'] for i in items)
            dur = min(int(t.duration_minutes), budget - used)
            if dur < MIN_TASK_MINUTES: continue
            sm = ch*60+cm; em = sm+dur
            items.append({'plan_id': c['plan_id'], 'knowledge_node_id': c['node_id'],
                'title': t.title or (c['plan_title'] + '：' + c['node_name']),
                'description': c.get('node_description'),
                'start_time': time(sm//60, sm%60), 'end_time': time(em//60, em%60),
                'duration_minutes': dur, 'guide_content': None})
            cm += dur; ch += cm//60; cm %= 60

        if not items: return {'planned_items': []}
        return {'planned_items': items, 'llm_reasoning': reason}
    except Exception as e:
        logger.warning('[ScheduleAgent] LLM排期失败: %s', e)
        fb = await _fallback_llm_schedule(state, context, budget)
        fb['llm_error'] = str(e)[:400]
        return fb
async def _fallback_llm_schedule(
    state: ScheduleAgentState | None,
    context: dict[str, Any],
    budget: int,
) -> dict[str, Any]:
    """画像感知兜底排期：利用画像信息做更合理的分配，而非简单的平均压缩"""
    candidates = list(context.get("candidates", []))
    if not candidates:
        return {"planned_items": []}

    start_s = str(context.get("start_at", ""))
    try:
        start_at = datetime.fromisoformat(start_s)
    except (ValueError, TypeError):
        start_at = datetime.combine(date.today(), time(19, 0))

    # 利用画像信息：获取最佳时段偏好，调整任务时长
    raw_profile = context.get("raw_profile", {})
    preferred_label = ""
    if isinstance(raw_profile, dict):
        best_time = raw_profile.get("best_time_slots", {})
        if isinstance(best_time, dict):
            preferred_label = best_time.get("label", "")

    # 按优先级排序，同优先级内按每日预算降序
    candidates.sort(key=lambda c: (c.get("plan_priority", 2), -c.get("daily_budget", 30)))

    # 对候选项：考虑画像的节奏偏好来调整时长分配
    rhythm_label = ""
    if isinstance(raw_profile, dict):
        rhythm = raw_profile.get("learning_rhythm", {})
        if isinstance(rhythm, dict):
            rhythm_label = rhythm.get("label", "")

    # 按权重分配：高优先级分配更多时间
    total_priority_weight = 0
    priority_weights = {1: 3, 2: 2, 3: 1}
    for c in candidates:
        p = c.get("plan_priority", 2)
        total_priority_weight += priority_weights.get(p, 2)

    planned_items = []
    cursor = start_at
    remaining = budget

    for c in candidates:
        if remaining < MIN_TASK_MINUTES:
            break
        p = c.get("plan_priority", 2)
        weight = priority_weights.get(p, 2)
        base = c.get("estimated_minutes", 30)
        # 高优先级获得更大比例的时间
        fair_share = int(budget * weight / total_priority_weight) if total_priority_weight > 0 else base
        duration = min(max(fair_share, MIN_TASK_MINUTES), base, remaining)
        duration = max(duration, MIN_TASK_MINUTES)
        end_at = cursor + timedelta(minutes=duration)
        planned_items.append({
            "plan_id": c["plan_id"],
            "knowledge_node_id": c["node_id"],
            "title": c["plan_title"] + "：" + c["node_name"],
            "description": c.get("node_description"),
            "start_time": cursor.time(),
            "end_time": end_at.time(),
            "duration_minutes": duration,
            "guide_content": None,
        })
        cursor = end_at
        remaining -= duration

    logger.info("[ScheduleAgent] 画像感知兜底排期完成: %d 个任务 (budget=%d, profile='%s')",
                len(planned_items), budget, preferred_label[:20])
    return {"planned_items": planned_items, "llm_reasoning": "fallback(profile-aware)", "llm_replan_decisions": []}





async def generate_task_guides(state: ScheduleAgentState) -> dict[str, Any]:
    """为排期方案中的每个任务生成学习指引（guide_content）"""
    if state.get("skip_reason"):
        return {}
    planned_items = list(state.get("planned_items", []))
    if not planned_items:
        return {"planned_items": []}
    use_fallback = int(state.get("review_attempts", 0) or 0) > 0
    async for db in get_db():
        for item in planned_items:
            plan = await db.get(Plan, item["plan_id"])
            node = await db.get(KnowledgeNode, item["knowledge_node_id"])
            if plan is None or node is None:
                continue
            if use_fallback:
                item["guide_content"] = _fallback_guide(node.name, item["duration_minutes"], node.description)
            else:
                item["guide_content"] = await _generate_guide(plan, node, item["duration_minutes"])
        break
    return {"planned_items": planned_items}


async def persist_schedule(state: ScheduleAgentState) -> dict[str, Any]:
    """审查通过（或达上限）后将排期写入数据库。"""

    if state.get("skip_reason"):
        return {
            "schedule_result": state.get("schedule_result") or {"tasks": []},
            "next": "",
        }

    context = state.get("schedule_context") or {}
    user_id = int(context.get("user_id") or state.get("user_id") or 0)
    target_date = _parse_target_date(state.get("scheduled_date"))
    planned_items = list(state.get("planned_items") or [])
    overflow_detected = bool(state.get("overflow_detected", False))

    try:
        async for db in get_db():
            created = await create_daily_tasks(db, user_id, planned_items, target_date)
            total_minutes = sum(task.duration_minutes for task in created)
            task_summary = [
                {
                    "task_id": task.id,
                    "plan_id": task.plan_id,
                    "title": task.title,
                    "duration_minutes": task.duration_minutes,
                    "guide_content": task.guide_content,
                    "start_time": task.start_time.strftime("%H:%M") if task.start_time else None,
                    "end_time": task.end_time.strftime("%H:%M") if task.end_time else None,
                }
                for task in created
            ]
            return {
                "messages": [AIMessage(content=f"已生成 {len(created)} 个今日学习任务，共 {total_minutes} 分钟。")],
                "schedule_result": {
                    "scheduled_date": str(target_date),
                    "tasks": task_summary,
                    "total_minutes": total_minutes,
                    "overflow_detected": overflow_detected,
                },
                "next": "",
            }
    except Exception as exc:
        logger.exception("[ScheduleAgent] persist_schedule 失败: %s", exc)
        return {
            "messages": [AIMessage(content="今日任务生成失败，请稍后重试。")],
            "schedule_result": {"tasks": []},
            "next": "",
        }


def create_schedule_graph():
    """
    创建 Schedule Agent 子图（LLM 驱动版）

    Loop 流程:
        load_context -> llm_generate_schedule -> generate_task_guides -> schedule_review
             +-- pass -> persist_schedule -> END
             +-- fail (未达上限) -> retry llm_generate_schedule
    """
    graph = StateGraph(ScheduleAgentState)
    graph.add_node("load_context", load_schedule_context)
    graph.add_node("llm_generate_schedule", llm_generate_schedule)
    graph.add_node("generate_task_guides", generate_task_guides)
    graph.add_node("schedule_review", schedule_review_node)
    graph.add_node("persist_schedule", persist_schedule)
    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "llm_generate_schedule")
    graph.add_edge("llm_generate_schedule", "generate_task_guides")
    graph.add_edge("generate_task_guides", "schedule_review")
    graph.add_conditional_edges(
        "schedule_review", review_router,
        {"retry": "llm_generate_schedule", "end": "persist_schedule"},
    )
    graph.add_edge("persist_schedule", END)
    return graph.compile()



async def run_schedule_graph(
    user_id: str,
    daily_budget: int | None = None,
    scheduled_date: date | None = None,
) -> dict[str, Any]:
    """运行 Schedule Agent 子图的便捷入口。"""

    graph = create_schedule_graph()
    initial_state: ScheduleAgentState = {
        "messages": [],
        "user_id": user_id,
        "plan_id": None,
        "session_id": "",
        "agent_type": "schedule",
        "tools": [],
        "next": "",
        "parsed_goal": None,
        "plan_result": None,
        "execution_plan": [],
        "execution_index": 0,
        "step_results": {},
        "orchestration_warnings": [],
        "review_attempts": 0,
        "review_max_attempts": MAX_REVIEW_ATTEMPTS,
        "review_results": [],
        "raw_agent_output": None,
        "review_verdict": "",
        "daily_budget": daily_budget,
        "scheduled_date": scheduled_date or date.today(),
        "schedule_context": None,
        "planned_items": [],
        "schedule_result": None,
        "overflow_detected": False,
        "skip_reason": None,
    }
    return await graph.ainvoke(initial_state)


# 兼容旧入口：单节点包装（供外部若仍引用 schedule_agent_node）
async def schedule_agent_node(state: dict[str, Any]) -> dict[str, Any]:
    """兼容旧调用：将扁平状态交给完整子图执行。"""

    return await run_schedule_graph(
        user_id=str(state.get("user_id", "0")),
        daily_budget=state.get("daily_budget"),
        scheduled_date=_parse_target_date(state.get("scheduled_date")),
    )


register_reviewer("schedule_agent", schedule_reviewer)
