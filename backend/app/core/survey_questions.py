"""
摸底选择题题库与画像计算逻辑

What: 定义 12 道选择题（覆盖 6 个画像维度），提供 calculate_profile 函数根据作答计算初始画像
Why: 为用户提供结构化的选择题摸底流程，替代原有的 LLM 开放式问答
"""

import logging
from typing import Any

from app.core.profile_service import PROFILE_DIMENSIONS

logger = logging.getLogger(__name__)


# ── 问题定义 ──────────────────────────────────────────────────────────
# 每个选项包含：
#   option_id: 唯一标识
#   text:      展示给用户的文本
#   label:     选中后赋予对应画像维度的标签
#   weight:    置信度权重 (0-100)，越高表示该选项越能确定画像方向

_QUESTIONS = [
    # ── learning_style (学习风格) ──
    {
        "id": 1,
        "dimension": "learning_style",
        "question": "你在学习新知识时，更倾向于哪种方式？",
        "options": [
            {"option_id": "q1_a", "text": "看图表、视频和图文资料", "label": "视觉型", "weight": 70},
            {"option_id": "q1_b", "text": "听讲解、参与讨论", "label": "听觉型", "weight": 70},
            {"option_id": "q1_c", "text": "动手操作和实际练习", "label": "动觉型", "weight": 70},
            {"option_id": "q1_d", "text": "以上方式结合使用", "label": "混合型", "weight": 50},
        ],
    },
    {
        "id": 2,
        "dimension": "learning_style",
        "question": "当你需要理解一个复杂概念时，你通常会怎么做？",
        "options": [
            {"option_id": "q2_a", "text": "寻找思维导图或流程图来理解", "label": "视觉型", "weight": 60},
            {"option_id": "q2_b", "text": "找人讨论或听别人讲解", "label": "听觉型", "weight": 60},
            {"option_id": "q2_c", "text": "自己动手尝试和做实验", "label": "动觉型", "weight": 60},
            {"option_id": "q2_d", "text": "阅读相关文章和书籍资料", "label": "读写型", "weight": 60},
        ],
    },
    # ── best_time_slots (最佳学习时段) ──
    {
        "id": 3,
        "dimension": "best_time_slots",
        "question": "你感觉自己在一天中哪个时间段学习效率最高？",
        "options": [
            {"option_id": "q3_a", "text": "早晨起床后（6:00-9:00）", "label": "清晨型", "weight": 80},
            {"option_id": "q3_b", "text": "上午（9:00-12:00）", "label": "上午型", "weight": 80},
            {"option_id": "q3_c", "text": "下午（14:00-17:00）", "label": "下午型", "weight": 80},
            {"option_id": "q3_d", "text": "晚上（19:00-23:00）", "label": "晚间型", "weight": 80},
            {"option_id": "q3_e", "text": "深夜（23:00以后）", "label": "深夜型", "weight": 80},
        ],
    },
    {
        "id": 4,
        "dimension": "best_time_slots",
        "question": "需要高度专注的学习或工作任务，你倾向于安排在什么时间？",
        "options": [
            {"option_id": "q4_a", "text": "早上头脑最清醒的时候", "label": "清晨型", "weight": 60},
            {"option_id": "q4_b", "text": "上午精力充沛的时候", "label": "上午型", "weight": 60},
            {"option_id": "q4_c", "text": "下午比较安静的时候", "label": "下午型", "weight": 60},
            {"option_id": "q4_d", "text": "晚上没人打扰的时候", "label": "晚间型", "weight": 60},
        ],
    },
    # ── learning_rhythm (学习节奏) ──
    {
        "id": 5,
        "dimension": "learning_rhythm",
        "question": "你通常如何安排学习时间？",
        "options": [
            {"option_id": "q5_a", "text": "每天固定时段学习，很有规律", "label": "规律型", "weight": 75},
            {"option_id": "q5_b", "text": "有空就学，时间不固定", "label": "随机型", "weight": 75},
            {"option_id": "q5_c", "text": "喜欢集中一段时间高强度学习", "label": "突击型", "weight": 75},
            {"option_id": "q5_d", "text": "跟着计划和日程安排走", "label": "计划型", "weight": 75},
        ],
    },
    {
        "id": 6,
        "dimension": "learning_rhythm",
        "question": "你更喜欢哪种学习节奏？",
        "options": [
            {"option_id": "q6_a", "text": "短时间高专注，多次休息（类似番茄钟）", "label": "短跑型", "weight": 65},
            {"option_id": "q6_b", "text": "长时间持续学习，中间少休息", "label": "长跑型", "weight": 65},
            {"option_id": "q6_c", "text": "看状态而定，灵活调整节奏", "label": "灵活型", "weight": 65},
            {"option_id": "q6_d", "text": "跟着课程或学习计划走", "label": "跟随型", "weight": 65},
        ],
    },
    # ── feedback_baseline (反馈校准基线) ──
    {
        "id": 7,
        "dimension": "feedback_baseline",
        "question": "做完练习题或测试后，你通常会怎么做？",
        "options": [
            {"option_id": "q7_a", "text": "立刻对答案，及时纠错", "label": "即时反馈型", "weight": 75},
            {"option_id": "q7_b", "text": "过一段时间再回顾检查", "label": "延迟反馈型", "weight": 75},
            {"option_id": "q7_c", "text": "需要别人来帮我检查和反馈", "label": "外部依赖型", "weight": 75},
            {"option_id": "q7_d", "text": "只关心对错，不太关注反馈细节", "label": "简单反馈型", "weight": 75},
        ],
    },
    {
        "id": 8,
        "dimension": "feedback_baseline",
        "question": "对于学习中的错误，你通常是怎样的态度？",
        "options": [
            {"option_id": "q8_a", "text": "仔细分析错误原因，避免再犯", "label": "深度分析型", "weight": 65},
            {"option_id": "q8_b", "text": "记住正确答案就行", "label": "结果导向型", "weight": 65},
            {"option_id": "q8_c", "text": "有点沮丧，不太想面对错误", "label": "回避型", "weight": 65},
            {"option_id": "q8_d", "text": "希望有人能帮我指出并解释错误", "label": "寻求指导型", "weight": 65},
        ],
    },
    # ── persistence (持续力) ──
    {
        "id": 9,
        "dimension": "persistence",
        "question": "你觉得自己在学习上的持续力如何？",
        "options": [
            {"option_id": "q9_a", "text": "能长期坚持，很少中断", "label": "高持续力", "weight": 80},
            {"option_id": "q9_b", "text": "能坚持一阵，但偶尔会松懈", "label": "中等持续力", "weight": 80},
            {"option_id": "q9_c", "text": "容易三分钟热度，需要外在督促", "label": "低持续力", "weight": 80},
        ],
    },
    {
        "id": 10,
        "dimension": "persistence",
        "question": "当学习遇到困难或感到枯燥时，你通常会怎么做？",
        "options": [
            {"option_id": "q10_a", "text": "咬牙坚持，不完成不罢休", "label": "坚韧型", "weight": 65},
            {"option_id": "q10_b", "text": "暂时放下，过会儿再回来学", "label": "弹性型", "weight": 65},
            {"option_id": "q10_c", "text": "容易想放弃，换点别的事情做", "label": "易放弃型", "weight": 65},
            {"option_id": "q10_d", "text": "找人鼓励或寻求帮助", "label": "社交型", "weight": 65},
        ],
    },
    # ── knowledge_retention (知识保留) ──
    {
        "id": 11,
        "dimension": "knowledge_retention",
        "question": "学过的内容，你通常能记住多久？",
        "options": [
            {"option_id": "q11_a", "text": "很久不忘记，记忆深刻", "label": "强保留", "weight": 80},
            {"option_id": "q11_b", "text": "定期复习就能记住", "label": "中等保留", "weight": 80},
            {"option_id": "q11_c", "text": "很容易忘记，需要反复回顾", "label": "弱保留", "weight": 80},
        ],
    },
    {
        "id": 12,
        "dimension": "knowledge_retention",
        "question": "你用什么方式来巩固学过的知识？",
        "options": [
            {"option_id": "q12_a", "text": "定期复习和自测", "label": "主动复习型", "weight": 65},
            {"option_id": "q12_b", "text": "通过做练习和项目实践来巩固", "label": "实践巩固型", "weight": 65},
            {"option_id": "q12_c", "text": "整理笔记和构建知识体系", "label": "整理归纳型", "weight": 65},
            {"option_id": "q12_d", "text": "很少专门复习，靠自然记忆", "label": "自然记忆型", "weight": 65},
        ],
    },
]


# ── 公开 API ─────────────────────────────────────────────────────────

def get_all_questions() -> list[dict]:
    """
    返回完整题库列表（不含 label 和 weight，供前端展示）。
    """
    return [
        {
            "id": q["id"],
            "dimension": q["dimension"],
            "question": q["question"],
            "options": [
                {"option_id": opt["option_id"], "text": opt["text"]}
                for opt in q["options"]
            ],
        }
        for q in _QUESTIONS
    ]


def calculate_profile(answers: list[dict]) -> dict:
    """
    根据选择题作答结果计算初始画像。

    Args:
        answers: [{question_id: int, option_id: str}, ...]

    Returns:
        dict: {
            "profile_updates": {dim: {label, confidence_delta, evidence}, ...},
            "profile_data":    {dim: {label, confidence, evidence}, ...},
        }
    """
    # 1. 构建答案映射
    answer_map: dict[int, str] = {}
    for ans in answers:
        qid = int(ans.get("question_id", 0))
        oid = str(ans.get("option_id", ""))
        if qid and oid:
            answer_map[qid] = oid

    # 2. 按维度聚合
    dim_selections: dict[str, list[tuple[str, float]]] = {}
    for q in _QUESTIONS:
        qid = q["id"]
        dim = q["dimension"]
        selected_oid = answer_map.get(qid)
        if not selected_oid:
            continue
        for opt in q["options"]:
            if opt["option_id"] == selected_oid:
                dim_selections.setdefault(dim, []).append((opt["label"], opt["weight"]))
                break

    # 3. 计算
    profile_updates: dict[str, dict] = {}
    profile_data: dict[str, dict] = {}

    for dim in PROFILE_DIMENSIONS:
        selections = dim_selections.get(dim, [])
        if not selections:
            continue
        label_weights: dict[str, float] = {}
        for label, weight in selections:
            label_weights[label] = label_weights.get(label, 0) + weight
        best_label = max(label_weights, key=label_weights.get)
        avg_weight = round(sum(label_weights.values()) / len(selections), 1)
        evidence_text = f"摸底问答：选择了「{best_label}」相关选项"
        profile_updates[dim] = {
            "label": best_label,
            "confidence_delta": 0.7,
            "evidence": evidence_text,
        }
        profile_data[dim] = {
            "label": best_label,
            "confidence": avg_weight,
            "evidence": [evidence_text],
        }

    return {"profile_updates": profile_updates, "profile_data": profile_data}
