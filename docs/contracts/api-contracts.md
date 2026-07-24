# REST API 接口规范文档 (API Contracts)

> 版本：v1.0
> 最后更新：2026-07-23
> 维护人：Developer A
> 审查人：组长（Lead）
> 用途：定义前后端所有 REST API 的请求/响应格式

---

## 一、全局规范

### 1.1 基础信息
- **基础路径：** `/api/v1`
- **响应格式：** 统一包裹
```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```
- **错误响应：**
```json
{
  "code": 40001,
  "message": "具体错误信息",
  "data": null
}
```

| `code` | 含义 |
|--------|------|
| `0` | 成功 |
| `40001` | 请求参数错误 |
| `40100` | 未认证（Token 缺失/无效） |
| `40300` | 无权限 |
| `40400` | 资源不存在 |
| `50000` | 服务器内部错误 |

### 1.2 认证方式
- **Header：** `Authorization: Bearer {jwt_token}`
- **Token 有效期：** 7 天
- **401 处理：** 前端清除 Token，跳转 `/login`

### 1.3 日期时间格式
- 日期：`YYYY-MM-DD`（如 `2026-07-23`）
- 时间：`HH:MM`（24 小时制，如 `20:30`）
- 时间戳：ISO 8601（如 `2026-07-23T20:30:00+08:00`）

### 1.4 分页格式
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [...],
    "total": 42,
    "page": 1,
    "page_size": 20,
    "total_pages": 3
  }
}
```

---

## 二、认证模块 — Auth

### 2.1 注册

```
POST /api/v1/auth/register
```

**请求体：**
```json
{
  "username": "zhangsan",
  "email": "zhangsan@example.com",
  "password": "abc123456"
}
```

| 字段 | 类型 | 必填 | 约束 |
|------|------|------|------|
| `username` | `string` | 是 | 3-50 字符，字母数字下划线 |
| `email` | `string` | 否 | 合法邮箱格式 |
| `password` | `string` | 是 | 6-32 字符 |

**成功响应 (code=0)：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "user_id": "uuid-xxx",
    "username": "zhangsan",
    "email": "zhangsan@example.com",
    "created_at": "2026-07-23T10:00:00+08:00"
  }
}
```

---

### 2.2 登录

```
POST /api/v1/auth/login
```

**请求体：**
```json
{
  "username": "zhangsan",
  "password": "abc123456"
}
```

**成功响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "expires_in": 604800,
    "user": {
      "user_id": "uuid-xxx",
      "username": "zhangsan",
      "email": "zhangsan@example.com"
    }
  }
}
```

**前端处理：** 将 `access_token` 存入 localStorage/zustand，后续所有请求在 Axios 拦截器中注入 Header。

---

### 2.3 获取当前用户

```
GET /api/v1/auth/profile
```

**Headers：** `Authorization: Bearer {token}`

**成功响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "user_id": "uuid-xxx",
    "username": "zhangsan",
    "email": "zhangsan@example.com",
    "daily_available_minutes": 90,
    "is_active": true,
    "created_at": "2026-07-23T10:00:00+08:00"
  }
}
```

---

## 三、计划模块 — Plans

### 3.1 创建计划

```
POST /api/v1/plans
```

**请求体：**
```json
{
  "title": "Python 入门",
  "goal": "想3个月后能自己写爬虫",
  "priority": 1,
  "daily_budget": 30,
  "time_preference": {
    "morning": 0,
    "afternoon": 20,
    "evening": 80
  },
  "start_date": "2026-07-24",
  "end_date": "2026-10-24"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `title` | `string` | 是 | 计划名称，1-100 字 |
| `goal` | `string` | 是 | 用户原始目标，自然语言 |
| `priority` | `int` | 是 | 1=高优先级，2=中，3=低 |
| `daily_budget` | `int` | 是 | 每日学习预算（分钟） |
| `time_preference` | `object` | 否 | 时段偏好权重，三项之和=100 |
| `start_date` | `string` | 是 | YYYY-MM-DD |
| `end_date` | `string` | 是 | YYYY-MM-DD |

**成功响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "plan": {
      "id": "plan-uuid-xxx",
      "title": "Python 入门",
      "goal": "想3个月后能自己写爬虫",
      "priority": 1,
      "daily_budget": 30,
      "time_preference": { "morning": 0, "afternoon": 20, "evening": 80 },
      "status": "active",
      "estimated_total_hours": 45.0,
      "start_date": "2026-07-24",
      "end_date": "2026-10-24",
      "node_count": 15,
      "created_at": "2026-07-23T10:00:00+08:00"
    },
    "feasibility_report": "根据你的学习记录，你属于理解偏慢但记忆牢固的类型...预计10周完成。",
    "knowledge_nodes": [
      {
        "id": "node-uuid-1",
        "title": "Python 环境搭建与基础语法",
        "description": "安装Python、Hello World、变量与基本数据类型",
        "estimated_minutes": 120,
        "prerequisite_ids": [],
        "order_index": 1,
        "status": "pending",
        "mastery_level": 0
      },
      {
        "id": "node-uuid-2",
        "title": "控制流：条件判断与循环",
        "description": "if/else、for、while 语句",
        "estimated_minutes": 150,
        "prerequisite_ids": ["node-uuid-1"],
        "order_index": 2,
        "status": "pending",
        "mastery_level": 0
      }
    ]
  }
}
```

---

### 3.2 获取计划列表

```
GET /api/v1/plans
```

**Query 参数：** 无（只返回当前用户的所有计划）

**成功响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "plans": [
      {
        "id": "plan-uuid-xxx",
        "title": "Python 入门",
        "priority": 1,
        "daily_budget": 30,
        "status": "active",
        "estimated_total_hours": 45.0,
        "progress_percent": 15,
        "completed_nodes": 2,
        "total_nodes": 15,
        "start_date": "2026-07-24",
        "end_date": "2026-10-24",
        "created_at": "2026-07-23T10:00:00+08:00"
      },
      {
        "id": "plan-uuid-yyy",
        "title": "英语口语",
        "priority": 2,
        "daily_budget": 20,
        "status": "active",
        "estimated_total_hours": 30.0,
        "progress_percent": 8,
        "completed_nodes": 1,
        "total_nodes": 12,
        "start_date": "2026-07-25",
        "end_date": "2026-09-25",
        "created_at": "2026-07-23T11:00:00+08:00"
      }
    ],
    "total_daily_budget": 50,
    "user_daily_available": 90,
    "remaining_daily": 40
  }
}
```

**前端用途：** Dashboard 概览卡片、计划列表页。

---

### 3.3 获取计划详情

```
GET /api/v1/plans/{plan_id}
```

**成功响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "plan": { /* 同 3.1 的 plan 结构 */ },
    "knowledge_nodes": [ /* 同 3.1 的 knowledge_nodes 列表 */ ],
    "feasibility_report": "..."
  }
}
```

**前端用途：** 计划详情页，展示 DAG 路径图。

---

### 3.4 更新计划

```
PATCH /api/v1/plans/{plan_id}
```

**请求体（所有字段可选，只传要改的）：**
```json
{
  "title": "Python 进阶",
  "priority": 2,
  "daily_budget": 25,
  "status": "paused"
}
```

**成功响应：** 返回更新后的 `plan` 对象。

---

### 3.5 删除计划

```
DELETE /api/v1/plans/{plan_id}
```

**成功响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": null
}
```

---

### 3.6 可行性评估

```
POST /api/v1/plans/{plan_id}/assess
```

**说明：** 对已存在的计划重新做可行性评估（通常创建时已自动执行）。

**成功响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "feasibility_report": "评估文本...",
    "estimated_total_hours": 45.0,
    "daily_required": 30,
    "user_daily_available": 90,
    "feasible": true
  }
}
```

---

## 四、路径模块 — Path

### 4.1 获取路径 DAG

```
GET /api/v1/plans/{plan_id}/path
```

**成功响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "nodes": [
      {
        "id": "node-uuid-1",
        "title": "Python 环境搭建与基础语法",
        "estimated_minutes": 120,
        "status": "mastered",
        "mastery_level": 90,
        "order_index": 1,
        "adjusted_minutes": 156
      },
      {
        "id": "node-uuid-2",
        "title": "控制流：条件判断与循环",
        "estimated_minutes": 150,
        "status": "in_progress",
        "mastery_level": 45,
        "order_index": 2,
        "adjusted_minutes": 195
      }
    ],
    "edges": [
      { "source": "node-uuid-1", "target": "node-uuid-2" },
      { "source": "node-uuid-1", "target": "node-uuid-3" },
      { "source": "node-uuid-2", "target": "node-uuid-4" }
    ]
  }
}
```

**前端说明：** `nodes` = React Flow 的节点列表，`edges` = React Flow 的边列表。

---

### 4.2 操作路径节点

```
PATCH /api/v1/plans/{plan_id}/path/nodes/{node_id}
```

**请求体：**
```json
{
  "operation": "prioritize"
}
```

| `operation` | 含义 |
|-------------|------|
| `skip` | 跳过此节点（标记为已掌握） |
| `prioritize` | 优先学习此节点（提前排序） |
| `resume` | 恢复为此节点安排时间 |

**成功响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "nodes": [ /* 重排后的完整 DAG */ ],
    "edges": [ /* 重排后的完整边列表 */ ],
    "adjustment_note": "已将'函数进阶'提前到第3位，后续节点依次后移。"
  }
}
```

---

## 五、每日任务模块 — Tasks

### 5.1 获取今日任务

```
GET /api/v1/tasks/today
```

**成功响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "date": "2026-07-23",
    "total_tasks": 3,
    "total_minutes": 60,
    "remaining_minutes": 30,
    "tasks": [
      {
        "id": "task-uuid-1",
        "plan_id": "plan-uuid-xxx",
        "plan_title": "Python 入门",
        "plan_priority": 1,
        "knowledge_node_id": "node-uuid-2",
        "title": "Python 控制流练习",
        "guide_content": "重点理解：if/elif/else 的执行顺序...",
        "date": "2026-07-23",
        "start_time": "20:00",
        "end_time": "20:30",
        "duration_minutes": 30,
        "status": "pending",
        "is_review": false,
        "sort_order": 1
      },
      {
        "id": "task-uuid-2",
        "plan_id": "plan-uuid-yyy",
        "plan_title": "英语口语",
        "plan_priority": 2,
        "knowledge_node_id": "node-uuid-8",
        "title": "第3单元词汇复习",
        "guide_content": null,
        "date": "2026-07-23",
        "start_time": "07:30",
        "end_time": "07:50",
        "duration_minutes": 20,
        "status": "completed",
        "is_review": true,
        "sort_order": 2
      }
    ]
  }
}
```

---

### 5.2 按日期查询任务

```
GET /api/v1/tasks?date=2026-07-24
```

**响应格式：** 同 5.1。

---

### 5.3 更新任务状态

```
PATCH /api/v1/tasks/{task_id}
```

**请求体：**
```json
{
  "status": "completed"
}
```

| `status` | 含义 |
|----------|------|
| `completed` | 已完成 |
| `skipped` | 跳过 |

**成功响应：** 返回更新后的 `task` 对象。

---

### 5.4 拖拽重排

```
PUT /api/v1/tasks/today/reorder
```

**请求体：**
```json
{
  "task_ids": ["task-uuid-2", "task-uuid-1", "task-uuid-3"]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_ids` | `string[]` | 是 | 按新顺序排列的任务 ID 列表 |

**成功响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "tasks": [ /* 重排后的完整任务列表 */ ]
  }
}
```

---

## 六、反馈模块 — Feedback

### 6.1 建立 SSE 连接

```
GET /api/v1/events/stream?token={jwt_token}
```

**说明：** 这个端点是全局 SSE 推送入口。所有实时事件（排期更新、反馈流、周报、干预）都通过此连接推送。事件格式见 `docs/contracts/sse-events.md`。

---

### 6.2 开始反馈对话

```
POST /api/v1/feedback/start
```

**请求体：**
```json
{
  "task_id": "task-uuid-1"
}
```

**说明：** 用户完成一个任务后调此接口。后端通过 SS E 连接推送追问内容（`feedback_stream` 事件）。

**成功响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "session_id": "session-uuid-xxx",
    "message": "反馈对话已建立，请通过 SSE 连接接收追问。"
  }
}
```

---

### 6.3 回复反馈追问

```
POST /api/v1/feedback/reply
```

**请求体：**
```json
{
  "session_id": "session-uuid-xxx",
  "reply": "函数参数这部分比变量作用域难一些，看了一遍视频大概懂了，但自己写的时候还有点卡"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `session_id` | `string` | 是 | 来自 6.2 返回的 session_id |
| `reply` | `string` | 是 | 用户回复文本 |

**说明：** 后端解析后通过 SSE 推送 `response` chunk 类型。如果需要追问，推送 `content` + `end` chunk。

**成功响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "session_id": "session-uuid-xxx",
    "action_taken": "replan + profile_update",
    "response_preview": "明白了。函数参数这块...",
    "needs_followup": false
  }
}
```

---

## 七、画像模块 — Profile

### 7.1 获取当前画像

```
GET /api/v1/profile
```

**成功响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "profile": {
      "learning_style": {
        "label": "理解偏慢但记忆牢固型",
        "confidence": 78,
        "evidence": [
          "反馈'函数参数'时表示需要巩固，但三天后复习正确率90%",
          "变量作用域花了2天但测试满分"
        ]
      },
      "best_time_slots": {
        "label": "夜猫子型（20:00-22:00）",
        "confidence": 85,
        "evidence": ["过去14天中11天的学习发生在20:00后"]
      },
      "learning_rhythm": {
        "label": "稳健型",
        "confidence": 72,
        "evidence": ["任务完成耗时平均为预估时间的1.3倍"]
      },
      "feedback_baseline": {
        "label": "标准严格型",
        "confidence": 65,
        "evidence": ["说'太难'时实际测试正确率62%"]
      },
      "persistence": {
        "label": "间歇型（平均每10天一次2-3天中断）",
        "confidence": 80,
        "evidence": ["过去30天出现了2次中断"]
      },
      "knowledge_retention": {
        "label": "短期记忆需巩固",
        "confidence": 60,
        "evidence": ["复习通过率85%，但首轮间隔7天后降至60%"]
      }
    },
    "total_feedback_count": 24,
    "last_calibrated_at": "2026-07-22T20:30:00+08:00",
    "needs_initial_survey": false,
    "initial_survey_question": null
  }
}
```

**特殊说明：** 如果 `needs_initial_survey == true`，表示用户还没有画像，前端需展示摸底问答弹窗。`initial_survey_question` 字段包含第一个摸底问题。

---

### 7.2 回答摸底问题（初始画像建立）

```
POST /api/v1/profile/survey
```

**说明：** `needs_initial_survey == true` 时，用户回答摸底问题后调此接口。

**请求体：**
```json
{
  "answer": "我之前学过一点C语言，知道变量和循环。平时学习喜欢慢慢来，把每个知识点搞透再往下走。"
}
```

**成功响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "profile_complete": false,
    "needs_followup": true,
    "next_question": "你觉得自己学新东西快吗？是看一遍就会了，还是要反复练习才能掌握？"
  }
}
```

**循环调用：** 前端循环调用此接口，直到 `profile_complete == true` 为止。通常 3-5 轮。

---

### 7.3 获取画像变更历史

```
GET /api/v1/profile/history
```

**成功响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "history": [
      {
        "timestamp": "2026-07-22T20:30:00+08:00",
        "source": "feedback_session:session-uuid-xxx",
        "changes": [
          "learning_style: 未知 → 理解偏慢但记忆牢固型 (+78%)",
          "knowledge_retention: 未知 → 短期记忆需巩固 (+60%)"
        ]
      },
      {
        "timestamp": "2026-07-21T19:00:00+08:00",
        "source": "initial_survey",
        "changes": [
          "best_time_slots: 未知 → 夜猫子型 (+70%)"
        ]
      }
    ]
  }
}
```

---

### 7.4 校准画像维度

```
POST /api/v1/profile/calibrate/{dimension}
```

**路径参数：** `dimension` 取值：`learning_style` / `best_time_slots` / `learning_rhythm` / `feedback_baseline` / `persistence` / `knowledge_retention`

**请求体：**
```json
{
  "comment": "我觉得我学东西不算慢，只是喜欢搞透彻。"
}
```

**成功响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "dimension": "learning_style",
    "old_label": "理解偏慢但记忆牢固型",
    "old_confidence": 78,
    "new_label": "理解偏慢但记忆牢固型",  // 没变
    "new_confidence": 50,               // 置信度下调
    "message": "收到你的反馈。confidence已从78下调至50，接下来会通过更多反馈重新评估这个维度。"
  }
}
```

---

## 八、学习日记模块 — Journals

### 8.1 创建学习日记

```
POST /api/v1/journals
```

**请求体：**
```json
{
  "task_id": "task-uuid-1",
  "content": "今天终于搞懂了函数参数的传递方式，*args和**kwargs之前一直模糊，现在明白了"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_id` | `string` | 是 | 关联的每日任务 ID |
| `content` | `string` | 是 | 一句话笔记（1-500 字） |

**成功响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": "journal-uuid-xxx",
    "task_id": "task-uuid-1",
    "knowledge_node_title": "Python 函数基础",
    "content": "今天终于搞懂了...",
    "created_at": "2026-07-23T20:35:00+08:00"
  }
}
```

---

### 8.2 查询学习日记

```
GET /api/v1/journals?node_id=node-uuid-2&page=1&page_size=20
```

**Query 参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `node_id` | `string` | 否 | 按知识节点筛选 |
| `plan_id` | `string` | 否 | 按计划筛选 |
| `page` | `int` | 否 | 默认 1 |
| `page_size` | `int` | 否 | 默认 20，最大 100 |

**成功响应（分页格式）：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": "journal-uuid-xxx",
        "plan_title": "Python 入门",
        "knowledge_node_title": "Python 函数基础",
        "content": "今天终于搞懂了...",
        "created_at": "2026-07-23T20:35:00+08:00"
      }
    ],
    "total": 5,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  }
}
```

---

## 九、摸底问答模块 — Initial Survey

### 9.1 获取下一个摸底问题

```
GET /api/v1/profile/survey/next
```

**说明：** 新用户首次进入画像页时调用。如果已建立完整画像，返回 `complete: true`。

**成功响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "complete": false,
    "round": 1,
    "total_rounds": 4,
    "question": "你过去学过编程吗？有没有什么特别擅长或者特别吃力的科目？"
  }
}
```

---

## 十、接口依赖关系总表

| 前端页面 | 依赖 API | 依赖后端 Step |
|---------|---------|-------------|
| 登录/注册页 | 2.1 注册, 2.2 登录 | Step 3 (A) |
| Dashboard 首页 | 2.3 当前用户, 3.2 计划列表, 5.1 今日任务 | Step 3 + Step 7 + Step 8 |
| 计划列表页 | 3.2 计划列表, 3.5 删除计划 | Step 7 (B) |
| 计划创建向导 | 3.1 创建计划 | Step 7 (B) |
| 计划详情页 (DAG) | 3.3 计划详情, 4.1 获取 DAG | Step 7 (B) |
| 每日视图 | 5.1 今日任务, 5.3 更新状态, 5.4 拖拽重排 | Step 8 (B) |
| 反馈对话弹窗 | 6.2 开始反馈, 6.3 回复追问 + SSE | Step 9 (你) |
| 画像页面 | 7.1 获取画像, 7.2 摸底回答, 7.3 历史, 7.4 校准 | Step 6 (A) |
| 学习日记 | 8.1 创建日记, 8.2 查询 | Step 14 (B) |

---

## 十一、变更记录

| 日期 | 版本 | 变更内容 | 变更人 |
|------|------|---------|--------|
| 2026-07-23 | v1.0 | 首次定稿：定义全部 16 个 API 的请求/响应格式 | Lead (初稿) |
