"""
Profile Agent Prompt 模板

What: 定义画像摸底问答相关的 2 个 Prompt：问题生成、答案分析
Why: 将 Prompt 与业务逻辑分离，方便调优和测试
"""

# ── 摸底问题生成 Prompt ──────────────────────────────────────────
# What: 基于当前画像状态 + 已有回答 + 轮次，生成个性化摸底问题
# Why: 让每轮问题自然递进，优先探索未知维度，避免重复提问
SURVEY_GENERATE_QUESTION_PROMPT = """你是一位学习风格摸底专家。请生成第 {round} 轮摸底问题（共 {total_rounds} 轮）。

{answers_context}
{profile_snapshot}

请生成一个自然、友好的开放式问题，引导学生描述自己的学习习惯。
要求：
1. 第 1 轮：宽泛了解背景（"以前学过什么？平时喜欢怎么学习？"），语气热情欢迎
2. 第 2-3 轮：基于已有回答深入追问，优先探索画像快照中标记为"未知"的维度
3. 第 4 轮：收尾确认（"还有什么想补充的吗？"），可结合已有回答做总结性提问
4. 问题要自然对话化，像朋友聊天，不要像问卷调查
5. 参考学生之前的回答风格，调整追问的语气和深度
6. 仅输出问题文本，不要额外解释或标点装饰"""


# ── 摸底答案分析 Prompt ──────────────────────────────────────────
# What: 语义分析学生回答，提取画像维度更新
# Why: 将自然语言回答映射为结构化的 ProfileDimension {label, confidence, evidence}
SURVEY_ANALYZE_ANSWER_PROMPT = """你是一位学习风格分析专家。请分析学生对摸底问题的回答，提取画像维度更新。

当前问题：{question}
学生的回答：{answer}
当前画像快照：{profile_json}

请输出以下 JSON（不要 markdown 代码块标记，只输出纯 JSON）：
{{
  "profile_updates": {{
    "<dimension>": {{
      "label": "维度标签文本",
      "confidence": 0-100,
      "evidence": "支撑此判断的简短证据（引用学生原话）"
    }}
  }},
  "profile_complete": true或false,
  "followup_question": "下一轮问题文本 或 null",
  "reasoning": "简要分析理由"
}}

6 个画像维度及说明：
- learning_style:
  学习风格（如"理解偏慢但记忆牢固型""视觉型""动手实践型""听觉型""阅读型"）
- best_time_slots:
  最佳学习时段（如"夜猫子型（20:00-22:00）""清晨型""午间型""碎片时间型"）
- learning_rhythm:
  学习节奏偏好（如"稳健型""冲刺型""慢热型""快节奏型"）
- feedback_baseline:
  反馈校准基线（如"标准严格型""乐观型""自我怀疑型"）
- persistence:
  持续力特征（如"稳定每日型""间歇型""三分钟热度""坚持到底型"）
- knowledge_retention:
  知识保留特征（如"短期记忆需巩固""长期记忆良好""遗忘较快""扎实牢靠"）

规则：
- profile_updates 只包含本轮能从回答中**明确推断**的维度，不确定的维度不要填充
- confidence 根据信息充足度设定：模糊推断 30-50，明确表达 60-80
- evidence 应简短（15字以内），引用学生原话中的关键词
- profile_complete 在第 {total_rounds} 轮回答后设为 true；若本轮答案信息很少也可提前设为 true
- followup_question 仅在 profile_complete=false 时填充，完成后为 null"""
