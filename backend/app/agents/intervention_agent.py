"""
Intervention Agent 子图模块

What: 当 Feedback Agent 检测到学习异常信号（stuck/need_practice）时，
      分析根因并生成结构化干预方案，审查通过后自动落库执行
Why: 让系统能自动诊断学习困难、提出补救建议并执行干预

架构说明：
  子图（含审查 loop + 执行）：
      START → load_context → analyze_situation → generate_intervention
          → intervention_review
              ├─ pass → apply_intervention → END
              └─ fail (未达上限) → retry generate_intervention
"""

import json
import logging
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from app.agents.review import get_reviewer
from app.agents.state import AgentState
from app.core.profile_service import get_user_profile
from app.llm.client import llm_client

logger = logging.getLogger(__name__)

# ── Prompt 模板 ────────────────────────────────────────────────────

SITUATION_ANALYSIS_SYSTEM = """你是一位学习诊断专家。请根据以下信息分析学生学习困难的根因。

用户画像：
{profile_summary}

学习计划上下文：
{plan_context}

反馈信号：{signal}
掌握度变化：{confidence_delta}

请分析：
1. 困难根因是什么（前置知识缺失？节奏过快？练习不足？概念抽象？）
2. 严重程度（high / medium / low）
3. 受影响的维度有哪些

请输出 JSON（不要 markdown 代码块标记，只输出纯 JSON）：
{{
  "root_cause": "根因描述",
  "severity": "high|medium|low",
  "affected_dimensions": ["知识保留", "学习节奏"],
  "reasoning": "简要分析理由"
}}"""

INTERVENTION_GENERATION_SYSTEM = """你是一位学习干预专家。根据诊断结果，生成结构化的干预方案。

诊断结果：
{diagnosis_json}

可用干预动作类型及所需参数：
- add_prerequisite: 插入前置知识节点
  params: {{"node_name": "知识点名称", "node_description": "简短描述", "estimated_minutes": 30}}
- adjust_priority: 调整计划优先级
  params: {{"new_priority": 1}}  (1=高/2=中/3=低)
- pause_plan: 暂停当前计划
  params: {{}}
- add_practice: 增加练习节点
  params: {{"node_name": "练习名称", "estimated_minutes": 20}}
- adjust_minutes: 调整节点预估时长
  params: {{"node_index": 0, "new_minutes": 45}}
- suggest_review: 建议复习已学内容
  params: {{"suggestion": "复习建议"}}

请输出 JSON（不要 markdown 代码块标记，只输出纯 JSON）：
{{
  "interventions": [
    {{
      "type": "干预类型",
      "target": "目标描述",
      "reason": "此干预的原因",
      "priority": 1-3,
      "params": {{}}
    }}
  ],
  "summary": "一句话总结干预方案"
}}"""


# ── 节点实现 ──────────────────────────────────────────────────────

async def load_context(state: AgentState) -> dict[str, Any]:
    """
    加载干预上下文节点

    What: 查询用户画像 + 计划信息 + 反馈信号，为后续分析准备输入
    Why: 干预分析需要画像特征和学习进度作为上下文
    """
    user_id = state.get("user_id", "")
    plan_id = state.get("plan_id", "")
    signal = state.get("intervention_signal") or state.get("next", "stuck")
    confidence_delta = state.get("intervention_confidence_delta", 0.0)

    profile_snapshot: dict[str, Any] = {}
    try:
        profile_full = await get_user_profile(user_id)
        profile_snapshot = profile_full.get("profile", {})
    except Exception as exc:
        logger.warning(f"[InterventionAgent] 加载画像失败: {exc}")

    plan_context: dict[str, Any] = {}
    try:
        from sqlalchemy import select
        from app.db.session import get_db as _get_db
        from app.models.plan import Plan
        from app.models.knowledge_node import KnowledgeNode

        async for db in _get_db():
            if plan_id:
                plan_result = await db.execute(
                    select(Plan).where(Plan.id == int(plan_id))
                )
                plan = plan_result.scalar_one_or_none()
                if plan:
                    plan_context["plan_title"] = plan.title
                    plan_context["plan_status"] = plan.status
                    plan_context["plan_priority"] = plan.priority

                    nodes_result = await db.execute(
                        select(KnowledgeNode)
                        .where(KnowledgeNode.plan_id == plan.id)
                        .order_by(KnowledgeNode.order_index.asc())
                    )
                    nodes = nodes_result.scalars().all()
                    plan_context["total_nodes"] = len(nodes)
                    plan_context["nodes"] = [
                        {
                            "name": n.name,
                            "difficulty": n.difficulty,
                            "estimated_minutes": n.estimated_minutes,
                            "mastery_level": n.mastery_level,
                            "order_index": n.order_index,
                        }
                        for n in nodes
                    ]
            break
    except Exception as exc:
        logger.warning(f"[InterventionAgent] 加载计划上下文失败: {exc}")
        plan_context = {"plan_title": "未知计划"}

    return {
        "profile_snapshot": profile_snapshot,
        "plan_context": plan_context,
        "intervention_signal": signal,
        "intervention_confidence_delta": confidence_delta,
    }


async def analyze_situation(state: AgentState) -> dict[str, Any]:
    """
    诊断分析节点

    What: 调用 LLM 分析学习异常的根因和严重程度
    Why: 干预需要先诊断问题，再开处方
    """
    profile = state.get("profile_snapshot") or {}
    plan_ctx = state.get("plan_context") or {}
    signal = state.get("intervention_signal", "stuck")
    confidence_delta = state.get("intervention_confidence_delta", 0.0)

    profile_summary = _format_profile_for_prompt(profile)
    plan_context_str = json.dumps(plan_ctx, ensure_ascii=False, indent=2)

    diagnosis = {
        "root_cause": "未知",
        "severity": "medium",
        "affected_dimensions": [],
        "reasoning": "LLM 分析未执行",
    }

    try:
        chat_model = llm_client.get_chat_model(temperature=0.3, timeout=30)
        response = await chat_model.ainvoke([
            {
                "role": "system",
                "content": SITUATION_ANALYSIS_SYSTEM.format(
                    profile_summary=profile_summary,
                    plan_context=plan_context_str,
                    signal=signal,
                    confidence_delta=confidence_delta,
                ),
            },
            {"role": "user", "content": "请分析该学生的学习困难根因。"},
        ])
        raw = response.content.strip()
        raw = _strip_markdown_code(raw)
        diagnosis = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(f"[InterventionAgent] LLM 返回非 JSON: {exc}")
    except Exception as exc:
        logger.exception(f"[InterventionAgent] 诊断分析失败: {exc}")

    logger.info(
        f"[InterventionAgent] 诊断完成: "
        f"root_cause={diagnosis.get('root_cause', '')[:50]}, "
        f"severity={diagnosis.get('severity', 'unknown')}"
    )

    return {"intervention_diagnosis": diagnosis}


async def generate_intervention(state: AgentState) -> dict[str, Any]:
    """
    生成干预方案节点

    What: 根据诊断结果，调用 LLM 生成结构化的干预动作列表
    Why: 将分析结论转化为可执行的干预建议
    """
    diagnosis = state.get("intervention_diagnosis") or {}

    interventions: list[dict[str, Any]] = []
    summary = ""

    try:
        chat_model = llm_client.get_chat_model(temperature=0.5, timeout=30)
        response = await chat_model.ainvoke([
            {
                "role": "system",
                "content": INTERVENTION_GENERATION_SYSTEM.format(
                    diagnosis_json=json.dumps(diagnosis, ensure_ascii=False, indent=2),
                ),
            },
            {"role": "user", "content": "请根据诊断结果生成干预方案。"},
        ])
        raw = response.content.strip()
        raw = _strip_markdown_code(raw)
        parsed = json.loads(raw)
        interventions = parsed.get("interventions", [])
        summary = parsed.get("summary", "")
    except json.JSONDecodeError as exc:
        logger.warning(f"[InterventionAgent] 干预方案 JSON 解析失败: {exc}")
        summary = "诊断完成，但干预方案生成遇到格式问题。"
    except Exception as exc:
        logger.exception(f"[InterventionAgent] 生成干预方案失败: {exc}")
        summary = "干预方案生成失败，请稍后重试。"

    logger.info(
        f"[InterventionAgent] 干预方案生成完成: "
        f"actions={len(interventions)}, "
        f"summary={summary[:80]}"
    )

    return {
        "intervention_actions": interventions,
        "intervention_summary": summary,
    }


# ── 辅助函数 ─────────────────────────────────────────────────────

def _strip_markdown_code(raw: str) -> str:
    """移除 LLM 响应中可能的 markdown 代码块标记"""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def _format_profile_for_prompt(profile: dict) -> str:
    """将画像快照格式化为 LLM prompt 可用的精简文本"""
    dim_names = {
        "learning_style": "学习风格",
        "best_time_slots": "最佳学习时段",
        "learning_rhythm": "学习节奏",
        "feedback_baseline": "反馈校准基线",
        "persistence": "持续力",
        "knowledge_retention": "知识保留",
    }
    parts = []
    for dim, name in dim_names.items():
        entry = profile.get(dim)
        if isinstance(entry, dict):
            label = entry.get("label", "未知")
            conf = entry.get("confidence", 0)
            parts.append(f"  {name}: {label} (置信度 {conf}%)")
        else:
            parts.append(f"  {name}: 未知")
    return "\n".join(parts) if parts else "（无画像数据）"


# ── 审查回路 ─────────────────────────────────────────────────────

_VALID_ACTION_TYPES = frozenset({
    "add_prerequisite",
    "adjust_priority",
    "pause_plan",
    "add_practice",
    "adjust_rhythm",
    "suggest_review",
    "adjust_minutes",
    "schedule_review",
})


async def intervention_reviewer(raw_output: dict, user_input: str, context: dict) -> dict:
    """
    Intervention Agent 输出质量审查器

    What: 审查干预方案的质量，确保动作类型合法、目标明确、优先级合理
    Why: 作为 Agent Loop 中的审查环节，防止生成无效或矛盾的干预动作

    Returns:
        dict: {"verdict": "pass"|"fail", "issues": [...], "suggestions": [...]}
    """
    issues = []
    suggestions = []

    actions = raw_output.get("intervention_actions", [])
    summary = raw_output.get("intervention_summary", "")
    signal = raw_output.get("intervention_signal", "")

    if not actions:
        issues.append("干预动作列表为空")
        suggestions.append("至少生成一个干预动作")
    else:
        for i, action in enumerate(actions):
            action_type = action.get("type", "")
            target = action.get("target", "")
            priority = action.get("priority", 0)

            if action_type not in _VALID_ACTION_TYPES:
                issues.append(f"动作[{i}]类型非法: {action_type}")
                suggestions.append(f"使用合法类型: {sorted(_VALID_ACTION_TYPES)}")

            if not target or not target.strip():
                issues.append(f"动作[{i}]缺少目标")
                suggestions.append(f"为动作[{i}]补充目标描述")

            if not isinstance(priority, (int, float)) or not (1 <= priority <= 3):
                issues.append(f"动作[{i}]优先级无效: {priority}")
                suggestions.append(f"动作[{i}]优先级设为 1-3")

        types = {a.get("type") for a in actions}
        if {"pause_plan", "add_prerequisite"} <= types:
            issues.append("同时暂停计划又新增前置节点，逻辑矛盾")
            suggestions.append("暂停计划时不新增节点，或新节点时不暂停")

    if not summary or len(summary.strip()) < 10:
        issues.append("干预摘要为空或过短")
        suggestions.append("生成简洁但有实质内容的干预摘要")

    if signal == "stuck" and not any(
        t in {"add_prerequisite", "adjust_rhythm", "adjust_minutes", "suggest_review"}
        for t in {a.get("type") for a in actions}
    ):
        issues.append("stuck 信号下缺少对症干预（前置知识/调整节奏/建议复习）")
        suggestions.append("stuck 信号建议优先: add_prerequisite / adjust_rhythm / adjust_minutes / suggest_review")

    verdict = "fail" if issues else "pass"
    return {"verdict": verdict, "issues": issues, "suggestions": suggestions}


async def intervention_review_node(state: AgentState) -> dict[str, Any]:
    """
    Intervention Agent 审查网关节点

    What: 收集当前子图执行输出，调用注册的审查器进行质量检查，
          根据结果决定放行或触发重试
    Why: 实现 Agent Loop 中的审查环节，确保干预方案输出质量
    """
    raw_output = {
        "intervention_actions": state.get("intervention_actions", []),
        "intervention_summary": state.get("intervention_summary", ""),
        "intervention_signal": state.get("intervention_signal", ""),
    }

    user_input = ""
    for msg in reversed(state.get("messages", [])):
        if hasattr(msg, "content") and getattr(msg, "type", "") == "human":
            user_input = msg.content
            break

    review_attempts = state.get("review_attempts", 0) + 1
    review_max = state.get("review_max_attempts", 3)
    review_results = list(state.get("review_results", []))

    reviewer = get_reviewer("intervention_agent")
    if reviewer:
        try:
            result = await reviewer(
                raw_output, user_input,
                {"agent_type": state.get("agent_type", "intervention")},
            )
        except Exception as exc:
            logger.warning(f"[InterventionAgent] 审查器执行异常: {exc}")
            result = {"verdict": "pass", "issues": [f"审查器异常: {exc!s}"]}
    else:
        result = {"verdict": "pass", "issues": ["审查器未注册，默认放行"]}

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
            f"[InterventionAgent] 审查未通过但已达重试上限 "
            f"(attempts={review_attempts}/{review_max}, "
            f"issues={result.get('issues', [])})"
        )

    return {
        "raw_agent_output": raw_output,
        "review_attempts": review_attempts,
        "review_results": review_results,
        "review_verdict": "pass" if is_final else "fail",
    }


def review_router(state: AgentState) -> Literal["retry", "end"]:
    """
    审查结果条件路由

    What: 根据 review_verdict 决定下一步走向
    Why: 作为条件边的路由函数，pass → END, fail → retry
    """
    if state.get("review_verdict", "") == "pass":
        return "end"
    return "retry"


# ── 应用干预节点 ─────────────────────────────────────────────────

async def apply_intervention(state: AgentState) -> dict[str, Any]:
    """
    应用干预方案节点

    What: 遍历审查通过的干预动作列表，逐一执行落库操作
    Why: 将 LLM 生成的方案转化为实际的 DB 变更
    """
    user_id = state.get("user_id", "")
    plan_id_str = state.get("plan_id", "")
    actions = state.get("intervention_actions") or []
    summary = state.get("intervention_summary", "")

    applied: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    try:
        plan_id = int(plan_id_str) if plan_id_str else 0
    except (ValueError, TypeError):
        plan_id = 0

    if plan_id and actions:
        for i, action in enumerate(actions):
            action_type = action.get("type", "")
            params = action.get("params") or {}
            try:
                result = await _apply_single_action(
                    user_id, plan_id, action_type, params, action
                )
                applied.append({"index": i, "type": action_type, "result": result})
                logger.info(
                    f"[InterventionAgent] 动作[{i}]应用成功: type={action_type}, result={result}"
                )
            except Exception as exc:
                err_msg = f"{type(exc).__name__}: {exc}"
                errors.append({"index": i, "type": action_type, "error": err_msg})
                logger.warning(
                    f"[InterventionAgent] 动作[{i}]应用失败: type={action_type}, error={err_msg}"
                )

    return {
        "intervention_applied": applied,
        "intervention_errors": errors,
        "intervention_summary": summary,
    }


async def _apply_single_action(
    user_id: str,
    plan_id: int,
    action_type: str,
    params: dict,
    action: dict,
) -> str:
    """
    执行单个干预动作的 DB 操作

    What: 根据动作类型分发到具体的 ORM 操作
    Why: 每种干预类型映射到不同的 DB 表/字段修改
    """
    from sqlalchemy import select, update
    from app.db.session import get_db as _get_db
    from app.models.plan import Plan
    from app.models.knowledge_node import KnowledgeNode

    async for db in _get_db():
        if action_type == "adjust_priority":
            new_priority = params.get("new_priority", action.get("priority", 2))
            new_priority = max(1, min(3, int(new_priority)))
            plan = await db.get(Plan, plan_id)
            if plan is None:
                raise ValueError(f"计划 #{plan_id} 不存在")
            plan.priority = new_priority
            await db.commit()
            return f"计划优先级已调整为 {new_priority}"

        elif action_type == "pause_plan":
            plan = await db.get(Plan, plan_id)
            if plan is None:
                raise ValueError(f"计划 #{plan_id} 不存在")
            plan.status = "paused"
            await db.commit()
            return "计划已暂停"

        elif action_type == "add_prerequisite":
            node_name = params.get("node_name") or action.get("target", "前置知识")
            node_desc = params.get("node_description", "")
            est_minutes = params.get("estimated_minutes", 30)

            max_order_result = await db.execute(
                select(KnowledgeNode.order_index)
                .where(KnowledgeNode.plan_id == plan_id)
                .order_by(KnowledgeNode.order_index.desc())
                .limit(1)
            )
            max_order = max_order_result.scalar() or 0

            node = KnowledgeNode(
                plan_id=plan_id,
                name=str(node_name)[:200],
                description=str(node_desc) if node_desc else None,
                estimated_minutes=int(est_minutes),
                difficulty=1,
                order_index=max_order + 1,
            )
            db.add(node)
            await db.commit()
            await db.refresh(node)
            return f"前置节点已创建: {node.name} (id={node.id})"

        elif action_type == "adjust_minutes":
            node_index = params.get("node_index", 0)
            new_minutes = params.get("new_minutes", 30)

            nodes_result = await db.execute(
                select(KnowledgeNode)
                .where(KnowledgeNode.plan_id == plan_id)
                .order_by(KnowledgeNode.order_index.asc())
            )
            nodes = nodes_result.scalars().all()
            if node_index < 0 or node_index >= len(nodes):
                raise ValueError(f"节点索引 {node_index} 越界 (共 {len(nodes)} 个节点)")
            node = nodes[node_index]
            node.estimated_minutes = max(5, int(new_minutes))
            await db.commit()
            return f"节点「{node.name}」预估时长调整为 {node.estimated_minutes} 分钟"

        elif action_type == "schedule_review":
            node_id = params.get("node_id")
            next_review_date_str = params.get("next_review_date", "")
            if not node_id:
                raise ValueError("schedule_review 缺少 node_id")
            node = await db.get(KnowledgeNode, int(node_id))
            if node is None:
                raise ValueError(f"知识节点 #{node_id} 不存在")
            from datetime import date as _date, datetime as _datetime
            if next_review_date_str:
                node.next_review_at = _date.fromisoformat(next_review_date_str)
            node.last_reviewed_at = _datetime.now()
            await db.commit()
            return f"节点「{node.name}」复习排期已更新: next_review_at={node.next_review_at}"

        else:
            return f"动作类型 {action_type} 无需落库操作（suggest_review / add_practice 暂不执行）"

    return "未执行（数据库会话异常）"



def create_intervention_graph() -> StateGraph:
    """
    创建干预分析+执行子图

    Loop 流程:
        load_context → analyze_situation → generate_intervention → intervention_review
            ├─ pass → apply_intervention → END
            └─ fail (未达上限) → retry generate_intervention
    """
    graph = StateGraph(AgentState)
    graph.add_node("load_context", load_context)
    graph.add_node("analyze_situation", analyze_situation)
    graph.add_node("generate_intervention", generate_intervention)
    graph.add_node("intervention_review", intervention_review_node)
    graph.add_node("apply_intervention", apply_intervention)
    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "analyze_situation")
    graph.add_edge("analyze_situation", "generate_intervention")
    graph.add_edge("generate_intervention", "intervention_review")
    graph.add_conditional_edges(
        "intervention_review",
        review_router,
        {"retry": "generate_intervention", "end": "apply_intervention"},
    )
    graph.add_edge("apply_intervention", END)
    return graph.compile()


# ── 便捷调用函数 ─────────────────────────────────────────────────

async def run_intervention(
    user_id: str,
    plan_id: str = "",
    signal: str = "stuck",
    confidence_delta: float = 0.0,
    session_id: str = "",
) -> dict[str, Any]:
    """
    运行干预分析

    What: 加载上下文 → 诊断分析 → 生成干预方案
    Why: 供 Feedback Agent 或 API 层在检测到异常信号时调用

    Args:
        user_id: 用户 ID
        plan_id: 目标计划 ID
        signal: 触发信号 (stuck / need_practice)
        confidence_delta: 掌握度变化量
        session_id: 会话 ID（可选）

    Returns:
        dict: 包含 diagnosis, actions, summary 的完整状态
    """
    graph = create_intervention_graph()
    initial_state: AgentState = {
        "messages": [],
        "user_id": user_id,
        "plan_id": plan_id,
        "session_id": session_id,
        "agent_type": "intervention",
        "tools": [],
        "next": "",
        "parsed_goal": None,
        "plan_result": None,
        "execution_plan": [],
        "execution_index": 0,
        "step_results": {},
        "orchestration_warnings": [],
        "review_attempts": 0,
        "review_max_attempts": 3,
        "review_results": [],
        "raw_agent_output": None,
        "review_verdict": "",
        "intervention_signal": signal,
        "intervention_confidence_delta": confidence_delta,
    }
    result = await graph.ainvoke(initial_state)
    return result


# ── 定时任务入口函数 ──────────────────────────────────────────────

_INACTIVE_DAYS_THRESHOLD = 3
_RETENTION_INTERVALS: dict[str, float] = {
    "遗忘较快": 1.5,
    "短期记忆需巩固": 2.0,
    "长期记忆良好": 4.5,
    "扎实牢靠": 6.0,
}
_DEFAULT_REVIEW_INTERVAL = 3.0


async def run_interruption_check() -> dict[str, Any]:
    """
    每日中断检测（供 scheduler 调用）

    What: 查询所有用户，检测连续未学习天数，超阈值则暂停活跃计划
    Why: 中断检测是恢复方案的前置条件，定时触发确保不漏检

    Returns:
        dict: {user_id: {interruption_detected, last_active_at, paused_plans}}
    """
    from datetime import date as _date, datetime as _datetime, timedelta
    from sqlalchemy import select, func
    from app.db.session import get_db as _get_db
    from app.models.daily_task import DailyTask
    from app.models.plan import Plan

    threshold_date = _datetime.now() - timedelta(days=_INACTIVE_DAYS_THRESHOLD)
    results: dict[str, Any] = {}

    try:
        async for db in _get_db():
            user_rows = await db.execute(
                select(DailyTask.user_id, func.max(DailyTask.completed_at).label("last_done"))
                .where(DailyTask.status == "completed")
                .group_by(DailyTask.user_id)
            )
            for row in user_rows:
                uid = row.user_id
                last_done = row.last_done
                inactive = last_done is None or last_done < threshold_date
                if not inactive:
                    results[str(uid)] = {
                        "interruption_detected": False,
                        "last_active_at": last_done.isoformat() if last_done else None,
                        "paused_plans": [],
                    }
                    continue

                plan_rows = await db.execute(
                    select(Plan).where(Plan.user_id == uid, Plan.status == "active")
                )
                active_plans = plan_rows.scalars().all()
                paused: list[str] = []
                for plan in active_plans:
                    plan.status = "paused"
                    paused.append(str(plan.id))
                    logger.info(
                        f"[InterventionAgent] 用户 {uid} 中断检测：暂停计划 #{plan.id}"
                    )
                if active_plans:
                    await db.commit()

                results[str(uid)] = {
                    "interruption_detected": True,
                    "last_active_at": last_done.isoformat() if last_done else None,
                    "paused_plans": paused,
                }
            break
    except Exception as exc:
        logger.exception(f"[InterventionAgent] 中断检测失败: {exc}")

    logger.info(f"[InterventionAgent] 中断检测完成: 检查 {len(results)} 位用户")
    return results


async def run_forgetting_curve_review() -> dict[str, Any]:
    """
    每日遗忘曲线复习（供 scheduler 调用）

    What: 读取画像 knowledge_retention，计算每个已掌握节点的复习间隔，
          对需复习的节点更新 next_review_at
    Why: 遗忘曲线排期是干预 Agent 的核心功能，定时触发确保复习不遗漏

    Returns:
        dict: {user_id: {reviewed_nodes: [...], skipped: int}}
    """
    from datetime import date as _date, datetime as _datetime, timedelta
    from sqlalchemy import select
    from app.db.session import get_db as _get_db
    from app.models.knowledge_node import KnowledgeNode
    from app.models.plan import Plan
    from app.core.profile_service import get_user_profile

    results: dict[str, Any] = {}
    today = _date.today()

    try:
        async for db in _get_db():
            user_rows = await db.execute(
                select(Plan.user_id.distinct())
                .where(Plan.status.in_(["active", "paused"]))
            )
            user_ids = [row[0] for row in user_rows]

            for uid in user_ids:
                profile_data = await get_user_profile(str(uid))
                profile = profile_data.get("profile", {})
                retention = profile.get("knowledge_retention", {})
                retention_label = (
                    retention.get("label", "")
                    if isinstance(retention, dict)
                    else str(retention) if retention else ""
                )
                interval_days = _RETENTION_INTERVALS.get(
                    retention_label, _DEFAULT_REVIEW_INTERVAL
                )

                nodes_result = await db.execute(
                    select(KnowledgeNode)
                    .where(
                        KnowledgeNode.plan.has(Plan.user_id == uid),
                        KnowledgeNode.mastery_level > 0,
                    )
                    .order_by(KnowledgeNode.plan_id, KnowledgeNode.order_index)
                )
                nodes = nodes_result.scalars().all()

                reviewed: list[str] = []
                for node in nodes:
                    if node.last_reviewed_at is None:
                        next_review = today + timedelta(days=int(interval_days))
                        node.next_review_at = next_review
                        reviewed.append(
                            f"node#{node.id} '{node.name}' → {next_review.isoformat()}"
                        )
                        continue

                    if node.next_review_at is not None and node.next_review_at > today:
                        continue

                    next_review = today + timedelta(days=int(interval_days))
                    node.next_review_at = next_review
                    reviewed.append(
                        f"node#{node.id} '{node.name}' → {next_review.isoformat()}"
                    )

                if reviewed:
                    await db.commit()

                results[str(uid)] = {
                    "reviewed_nodes": reviewed,
                    "interval_days": interval_days,
                    "retention_label": retention_label or "默认",
                }

            break
    except Exception as exc:
        logger.exception(f"[InterventionAgent] 遗忘曲线复习任务失败: {exc}")

    total_reviewed = sum(len(v["reviewed_nodes"]) for v in results.values())
    logger.info(
        f"[InterventionAgent] 遗忘曲线复习完成: "
        f"{len(results)} 位用户, {total_reviewed} 个节点已排期"
    )
    return results


# ── 审查器注册 ──────────────────────────────────────────────────
from app.agents.review import register_reviewer as _reg

_reg("intervention_agent", intervention_reviewer)
