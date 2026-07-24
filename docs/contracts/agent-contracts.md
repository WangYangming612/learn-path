# 智能体接口契约文档 (Agent Interface Contracts)

> 版本：v1.0
> 最后更新：2026-07-23
> 维护人：组长（Lead）
> 变更通知：每次修改请在群内 @所有人

---

## 一、全局约定

### 1.1 通信原则
- 所有用户请求**必须**经过 Orchestrator Agent 分发，不允许子 Agent 之间直接点对点调用
- 子 Agent 之间如果需要数据交换，通过 Orchestrator 中介转发
- 每种子图调用必须明确：**输入状态 → 处理逻辑 → 输出状态**

### 1.2 错误处理约定
- 每个 Agent 的图执行必须包含异常分支（`__error__` 或 fallback 节点）
- LLM 调用失败时：重试 2 次，间隔 2 秒，仍失败则回退到默认回复
- Agent 输出状态中 `next` 字段为 `"__end__"` 表示子图执行完毕

### 1.3 类型标注规范
- 所有 AgentState 使用 `TypedDict` 定义（轻量、类型安全、可扩展）
- 子 Agent 专属字段使用 `NotRequired` 标记为可选，保持基类干净

---

## 二、基类状态：AgentState

所有子 Agent 的状态继承自此基类。定义在 `backend/app/agents/state.py`。

```python
from typing import TypedDict, NotRequired, Optional
from langchain_core.messages import BaseMessage
from langchain_core.tools import Tool

class AgentState(TypedDict):
    """通用智能体状态基类——所有子Agent共用"""
    # —————— 必填字段 ——————
    messages: list[BaseMessage]       # 对话历史（包含用户消息和AI回复）
    user_id: str                       # 当前用户 UUID
    session_id: str                    # 当前会话 UUID
    agent_type: str                    # 智能体类型标识
    next: str                          # 下一步路由目标（节点名或 "__end__"）

    # —————— 可选字段 ——————
    plan_id: NotRequired[Optional[str]]  # 当前计划上下文（反馈/路径操作时必填）
    tools: NotRequired[list[Tool]]       # 可调用的工具集
    error: NotRequired[Optional[str]]    # 错误信息（异常分支填充）
```

### 2.1 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `messages` | `list[BaseMessage]` | 是 | 对话历史，顺序排列。系统消息在最前，用户消息和 AI 回复交替 |
| `user_id` | `str` | 是 | 用户 UUID，从 JWT 中解析，所有 Agent 共用 |
| `session_id` | `str` | 是 | 会话 UUID，单次交互全链路唯一。用于追踪日志 |
| `agent_type` | `str` | 是 | 枚举值：`"orchestrator"` / `"profile"` / `"plan"` / `"schedule"` / `"feedback"` / `"intervention"` |
| `next` | `str` | 是 | 下一个执行的节点名。`"__end__"` 表示结束 |
| `plan_id` | `str | None` | 否 | 创建计划后必填，反馈/路径操作时必填 |
| `tools` | `list[Tool]` | 否 | 子 Agent 可用工具集，由 Orchestrator 初始化时注入 |
| `error` | `str | None` | 否 | 异常时填充错误信息，路由到 fallback 处理节点 |

---

## 三、子 Agent 专属状态

### 3.1 OrchestratorState

定义在 `backend/app/agents/orchestrator.py`。

```python
class OrchestratorState(AgentState):
    """Orchestrator 扩展状态——意图识别与子图路由"""
    # —————— 输入 ——————
    user_input: str                     # 用户原始输入文本
    intent: NotRequired[Optional[str]]  # 意图分类结果（LLM 输出后填充）

    # —————— 路由结果 ——————
    target_agent: NotRequired[Optional[str]]  # 目标子 Agent 类型
    subgraph_result: NotRequired[Optional[dict]]  # 子图执行结果（JSON 序列化）

    # —————— 异步联动标记 ——————
    pending_async_updates: NotRequired[list[dict]]  # 待异步执行的联动操作列表
```

#### 字段说明

| 字段 | 类型 | 填充时机 | 说明 |
|------|------|---------|------|
| `user_input` | `str` | 入口节点 | 用户发来的原始文本 |
| `intent` | `str | None` | 意图分类后 | 枚举：`"create_plan"` / `"submit_feedback"` / `"view_profile"` / `"view_plans"` / `"view_tasks"` / `"adjust_plan"` / `"other"` |
| `target_agent` | `str | None` | 路由决策后 | 枚举同 `agent_type` |
| `subgraph_result` | `dict | None` | 子图返回后 | 子 Agent 输出状态的 JSON 快照 |
| `pending_async_updates` | `list[dict]` | 联动触发后 | 每个元素：`{target_agent, action, payload}` |

---

### 3.2 ProfileAgentState

定义在 `backend/app/agents/profile_agent.py`。

```python
class ProfileDimension(TypedDict):
    """画像单维度数据结构"""
    label: str                         # 维度标签（如："理解偏慢但记忆牢固型"）
    confidence: float                  # 置信度 0-100
    evidence: list[str]                # 证据列表（每条是触发该判断的反馈记录）

class ProfileData(TypedDict):
    """完整画像数据"""
    learning_style: ProfileDimension    # 学习风格
    best_time_slots: ProfileDimension   # 最佳学习时段
    learning_rhythm: ProfileDimension   # 学习节奏偏好
    feedback_baseline: ProfileDimension # 反馈校准基线
    persistence: ProfileDimension       # 持续力特征
    knowledge_retention: ProfileDimension  # 知识保留特征

class ProfileAgentState(AgentState):
    """画像智能体扩展状态"""
    # —————— 输入 ——————
    action: str                        # 操作类型
    # action 枚举：
    #   "initial_survey"     — 新用户摸底问答
    #   "update_profile"     — 增量更新画像
    #   "get_profile"        — 查询当前画像
    #   "calibrate_dimension" — 用户校准某维度

    # —————— 按 action 分组的参数 ——————
    # 用于 initial_survey
    survey_answers: NotRequired[Optional[list[str]]]  # 用户对摸底问题的回答列表

    # 用于 update_profile
    feedback_signal: NotRequired[Optional[str]]  # 反馈信号（来自 Feedback Agent）
    confidence_delta: NotRequired[float]          # 掌握度变化量
    source_session: NotRequired[Optional[str]]    # 来源反馈会话 ID

    # 用于 calibrate_dimension
    target_dimension: NotRequired[Optional[str]]  # 用户点踩的维度名
    user_comment: NotRequired[Optional[str]]      # 用户说明

    # —————— 输出 ——————
    profile: NotRequired[Optional[ProfileData]]         # 当前画像快照
    survey_question: NotRequired[Optional[str]]         # 摸底追问问题
    calibration_result: NotRequired[Optional[str]]      # 校准结果说明
    profile_changed: NotRequired[bool]                  # 画像是否有变更
    profile_changelog: NotRequired[Optional[list[dict]]]  # 变更记录列表
```

---

### 3.3 PlanAgentState

定义在 `backend/app/agents/plan_agent.py`。

```python
class KnowledgeNode(TypedDict):
    """知识节点结构——一个学习单元"""
    id: str                              # 节点 UUID
    plan_id: str                         # 所属计划 ID
    title: str                           # 节点标题（如："Python 变量与数据类型"）
    description: str                     # 节点描述
    estimated_minutes: int               # 预估学习时长（分钟）
    prerequisite_ids: list[str]          # 前置依赖节点 ID 列表（构建 DAG）
    order_index: int                     # 拓扑排序后的序号
    status: str                          # 枚举："pending" / "in_progress" / "mastered" / "reviewing"
    mastery_level: float                 # 掌握度 0-100

class PlanAgentState(AgentState):
    """路径规划智能体扩展状态"""
    # —————— 输入 ——————
    action: str                          # 操作类型
    # action 枚举：
    #   "create_plan"       — 创建新计划+生成路径
    #   "get_path"           — 查询已有路径
    #   "adjust_node"        — 用户干预路径节点
    #   "replan"             — 反馈触发的重规划

    # —————— 创建新计划 ——————
    plan_title: NotRequired[Optional[str]]     # 计划名称
    plan_goal: NotRequired[Optional[str]]      # 用户输入的原始目标（自然语言）
    daily_budget: NotRequired[Optional[int]]   # 每日时间预算（分钟）
    priority: NotRequired[Optional[int]]       # 优先级 1-3
    time_preference: NotRequired[Optional[dict]]  # 时段偏好权重
    start_date: NotRequired[Optional[str]]     # 开始日期 YYYY-MM-DD
    end_date: NotRequired[Optional[str]]       # 结束日期 YYYY-MM-DD

    # —————— 路径操作 ——————
    node_id: NotRequired[Optional[str]]        # 目标节点 ID
    operation: NotRequired[Optional[str]]      # 枚举："skip" / "prioritize" / "resume"
    new_prerequisite_ids: NotRequired[Optional[list[str]]]  # 重设前置依赖

    # —————— 重规划 ——————
    feedback_signal: NotRequired[Optional[str]]  # 来自 Feedback Agent
    confidence_changes: NotRequired[Optional[dict]]  # 掌握度变更映射 {node_id: delta}

    # —————— 输出 ——————
    feasibility_report: NotRequired[Optional[str]]   # 可行性评估文本
    knowledge_nodes: NotRequired[Optional[list[KnowledgeNode]]]  # DAG 节点列表
    adjustment_explanation: NotRequired[Optional[str]]  # 重规划调整说明
    plan_created: NotRequired[Optional[dict]]          # 创建的计划基础信息
```

---

### 3.4 ScheduleAgentState

定义在 `backend/app/agents/schedule_agent.py`。

```python
class DailyTaskItem(TypedDict):
    """单条排期任务"""
    id: str                              # 任务 UUID
    plan_id: str                         # 所属计划 ID
    knowledge_node_id: str               # 关联知识节点 ID
    title: str                           # 任务标题
    guide_content: NotRequired[Optional[str]]  # 学习重点指引（Markdown）
    date: str                            # 日期 YYYY-MM-DD
    start_time: NotRequired[Optional[str]]     # 建议开始时间 HH:MM
    end_time: NotRequired[Optional[str]]       # 建议结束时间 HH:MM
    duration_minutes: int                 # 时长（分钟）
    status: str                          # "pending" / "completed" / "skipped"
    is_review: bool                      # 是否为复习任务
    sort_order: int                      # 当日排序序号

class ScheduleAgentState(AgentState):
    """排期智能体扩展状态"""
    # —————— 输入 ——————
    action: str                          # 操作类型
    # action 枚举：
    #   "generate_daily"     — 生成某天的排期
    #   "reorder_tasks"      — 用户拖拽重排
    #   "reschedule_plan"    — 反馈触发重新排期

    # —————— 按 action 分组 ——————
    target_date: NotRequired[Optional[str]]      # 目标日期 YYYY-MM-DD（generate_daily 必填）
    active_plan_ids: NotRequired[Optional[list[str]]]  # 活跃计划 ID 列表
    user_daily_budget: NotRequired[Optional[int]]      # 用户每日可用总时长
    user_time_preferences: NotRequired[Optional[dict]] # 画像时段偏好

    # 拖拽重排
    plan_id_for_reorder: NotRequired[Optional[str]]
    task_order: NotRequired[Optional[list[str]]]  # 按顺序排列的任务 ID 列表

    # 重排期
    feedback_signal: NotRequired[Optional[str]]
    profile_daily_adjustment: NotRequired[Optional[float]]  # 日预算调整系数

    # —————— 输出 ——————
    daily_tasks: NotRequired[Optional[list[DailyTaskItem]]]   # 当日任务列表
    total_minutes: NotRequired[Optional[int]]                  # 当日总时长
    budget_status: NotRequired[Optional[str]]                  # "within" / "overflow"
    conflict_resolution: NotRequired[Optional[list[str]]]     # 冲突消解说明
```

---

### 3.5 FeedbackAgentState

定义在 `backend/app/agents/feedback_agent.py`。

```python
class FeedbackSignal(TypedDict):
    """反馈信号结构化输出"""
    signal: str                          # 枚举："too_easy" / "normal" / "need_practice" / "stuck" / "no_time"
    confidence: float                    # 信号置信度 0-100
    description: str                     # 自然语言描述

class ProfileUpdateRequest(TypedDict):
    """画像更新请求"""
    dimension: str                       # 要更新的维度名
    delta: dict                          # 变更内容
    source: str                          # 来源："feedback_session:{session_id}"

class FeedbackAgentState(AgentState):
    """反馈分析智能体扩展状态"""
    # —————— 输入 ——————
    action: str                          # 操作类型
    # action 枚举：
    #   "generate_question"  — 生成追问（初始调用）
    #   "parse_reply"        — 解析用户回复
    #   "stream_question"    — SSE 流式生成追问

    # —————— 上下文 ——————
    task_id: NotRequired[Optional[str]]          # 关联的每日任务 ID
    knowledge_node_title: NotRequired[Optional[str]]  # 当前学习内容标题
    profile: NotRequired[Optional[ProfileData]]  # 当前画像快照（Orchestrator 注入）
    feedback_history: NotRequired[Optional[list[dict]]]  # 近期反馈历史

    # —————— 追问相关 ——————
    generated_question: NotRequired[Optional[str]]   # 生成的追问文本
    question_round: NotRequired[int]                  # 当前是第几轮追问（max 3）
    prompt_hints: NotRequired[Optional[list[str]]]   # 引导提示列表

    # —————— 用户回复解析 ——————
    user_reply: NotRequired[Optional[str]]           # 用户的回复
    parsed_signal: NotRequired[Optional[FeedbackSignal]]  # 解析后的信号
    response_message: NotRequired[Optional[str]]     # 给用户的自然语言回应
    response_action: NotRequired[Optional[str]]      # 动作意图：告知用户系统将如何调整

    # —————— 触发联动 ——————
    replan_triggered: NotRequired[bool]               # 是否触发重规划
    profile_updates: NotRequired[Optional[list[ProfileUpdateRequest]]]  # 待更新的画像维度
    schedule_adjustment_needed: NotRequired[bool]     # 是否需要重排期
```

#### 信号-动作对照表（Feedback Agent 用）

| 信号 | 含义 | 系统动作 | 重规划? | 画像更新? |
|------|------|---------|---------|----------|
| `too_easy` | 偏简单，推进顺利 | 前置后续内容，掌握度+20；当天问是否加学其他计划 | 否 | learning_rhythm 提速 |
| `normal` | 难度适中 | 保持节奏，掌握度+10 | 否 | 无（维持） |
| `need_practice` | 理解了但需要巩固 | 2-3天后插入复习任务，掌握度+5 | 否 | knowledge_retention 调整 |
| `stuck` | 没搞懂 | 标记薄弱，拆细重排，延长该节点时长 | 是 | learning_style 调整 |
| `no_time` | 时间不够 | 评估是内容多还是安排不合理，压缩单次任务量 | 是 | persistence 调整 |

---

### 3.6 InterventionAgentState

定义在 `backend/app/agents/intervention_agent.py`。

```python
class InterventionAgentState(AgentState):
    """干预智能体扩展状态"""
    # —————— 输入 ——————
    action: str                          # 操作类型
    # action 枚举：
    #   "check_interruption"  — APScheduler 每日巡检触发
    #   "generate_recovery"   — 用户回归后生成恢复方案
    #   "schedule_review"     — 遗忘曲线复习排期

    # —————— 中断检测 ——————
    days_inactive: NotRequired[Optional[int]]     # 连续未登录天数
    interruption_detected: NotRequired[bool]      # 是否检测到中断

    # —————— 恢复方案 ——————
    persistence_label: NotRequired[Optional[str]] # 画像持续力标签
    recovery_plan: NotRequired[Optional[list[dict]]]  # 恢复期每日任务安排
    recovery_message: NotRequired[Optional[str]]  # 给用户的恢复方案说明

    # —————— 复习排期 ——————
    mastered_node_ids: NotRequired[Optional[list[str]]]  # 已掌握节点 ID 列表
    review_intervals: NotRequired[Optional[dict]]         # 复习间隔映射 {node_id: days_later}
    review_tasks: NotRequired[Optional[list[DailyTaskItem]]]  # 生成的复习任务
```

---

## 四、Orchestrator 路由表

### 4.1 意图→子图映射

| 意图 (`intent`) | 路由到子 Agent (`agent_type`) | 触发场景 |
|----------------|------------------------------|---------|
| `create_plan` | `plan` | 用户创建新学习计划 |
| `submit_feedback` | `feedback` | 用户完成学习后提交反馈 |
| `view_profile` | `profile` | 用户查看画像页面 |
| `view_plans` | `plan` (仅查询) | 用户查看计划列表 |
| `view_tasks` | `schedule` | 用户查看每日任务 |
| `adjust_plan` | `plan` | 用户手动干预路径节点 |
| `other` | 无（fallback） | 不属于以上分类的请求 |

### 4.2 异步联动规则

Feedback Agent 执行完毕后，Orchestrator 检查输出状态，触发联动：

| 触发条件 | 联动操作 | 说明 |
|---------|---------|------|
| `replan_triggered == true` | 异步调用 Plan Agent（action=`replan`）→ Schedule Agent（action=`reschedule_plan`） | 按顺序执行，Plan 先重算路径，Schedule 再重新排期 |
| `profile_updates` 非空 | 异步调用 Profile Agent（action=`update_profile`） | 传入 profile_updates |
| `schedule_adjustment_needed == true` | 异步调用 Schedule Agent（action=`reschedule_plan`） | 仅重排期，不重算路径 |

---

## 五、变更记录

| 日期 | 版本 | 变更内容 | 变更人 |
|------|------|---------|--------|
| 2026-07-23 | v1.0 | 首次定稿：定义所有 AgentState 和路由规则 | Lead |
