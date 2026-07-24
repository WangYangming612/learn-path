# SSE 事件流契约文档 (Server-Sent Events Contract)

> 版本：v1.0
> 最后更新：2026-07-23
> 维护人：组长（Lead）
> 用途：定义后端 → 前端的所有实时推送事件格式

---

## 一、传输层约定

### 1.1 连接方式
- 使用浏览器原生 `EventSource` API
- 连接端点：`GET /api/v1/events/stream`
- 认证方式：URL Query 参数携带 Token：`/api/v1/events/stream?token={jwt_token}`
- 连接超时：服务端 60 秒无事件发送时发送 `:keepalive` 注释行保持连接

### 1.2 错误处理
- 连接断开时前端自动重连（`EventSource` 原生支持）
- 重连间隔：3 秒
- 401 错误：前端清除 Token，跳转登录页

### 1.3 前端接入示例

```typescript
// hooks/useSSE.ts
const useSSE = () => {
  useEffect(() => {
    const token = useAuthStore.getState().token;
    const es = new EventSource(`/api/v1/events/stream?token=${token}`);

    es.addEventListener("schedule_updated", (e) => {
      const data = JSON.parse(e.data);
      // 处理排期更新
    });

    es.addEventListener("feedback_stream", (e) => {
      const data = JSON.parse(e.data);
      // 追加对话气泡
    });

    es.addEventListener("weekly_report", (e) => {
      const data = JSON.parse(e.data);
      // 展示周报卡片
    });

    es.addEventListener("intervention", (e) => {
      const data = JSON.parse(e.data);
      // 展示恢复方案
    });

    es.addEventListener("error", () => {
      // 断线重连
    });

    return () => es.close();
  }, []);
};
```

---

## 二、事件格式规范

所有 SSE 事件遵循以下通用格式：

```
event: {event_type}\n
data: {json_string}\n\n
```

### 2.1 通用数据包装

每条事件的 `data` 字段统一包装：

```typescript
interface SSEEventData {
  event_id: string;          // 事件唯一 ID (UUID)
  timestamp: string;         // ISO 8601 时间戳
  type: string;              // 事件类型（同 event 字段）
  payload: Record<string, any>;  // 具体业务数据
}
```

---

## 三、事件类型定义

### 3.1 `schedule_updated` — 排期更新通知

**触发时机：** 每日 0 点自动排期生成后，或用户拖拽重排后。

```typescript
// event: schedule_updated
{
  "event_id": "e7a1c2b3-...",
  "timestamp": "2026-07-24T00:00:00+08:00",
  "type": "schedule_updated",
  "payload": {
    "date": "2026-07-24",
    "total_tasks": 3,
    "total_minutes": 60,
    "tasks": [
      {
        "id": "task-uuid-1",
        "plan_title": "Python入门",
        "title": "Python 函数基础",
        "start_time": "20:00",
        "end_time": "20:40",
        "duration_minutes": 40,
        "guide_content": "重点理解：...",
        "status": "pending",
        "is_review": false
      },
      {
        "id": "task-uuid-2",
        "plan_title": "英语口语",
        "title": "第3单元词汇复习",
        "start_time": "07:30",
        "end_time": "07:50",
        "duration_minutes": 20,
        "guide_content": null,
        "status": "pending",
        "is_review": true
      }
    ],
    "overflow_detected": false,
    "message": "今日计划已生成，共3项任务，总用时60分钟。"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `date` | `string` | 是 | 排期的目标日期 YYYY-MM-DD |
| `total_tasks` | `number` | 是 | 当日任务总数 |
| `total_minutes` | `number` | 是 | 当日总学习时长（分钟） |
| `tasks` | `TaskItem[]` | 是 | 任务列表，按 sort_order 排列 |
| `overflow_detected` | `boolean` | 是 | 是否超出时间预算 |
| `message` | `string` | 是 | 给用户的自然语言提示 |

**`TaskItem` 类型：**

```typescript
interface TaskItem {
  id: string;
  plan_title: string;
  title: string;
  start_time: string | null;   // "HH:MM" 或 null（无固定时间）
  end_time: string | null;
  duration_minutes: number;
  guide_content: string | null; // Markdown 格式
  status: "pending" | "completed" | "skipped";
  is_review: boolean;
}
```

---

### 3.2 `feedback_stream` — 反馈对话流式推送

**触发时机：** 用户提交反馈后，Feedback Agent 生成追问时逐 chunk 推送。

```typescript
// event: feedback_stream
// 每个 chunk 单独推送，前端逐字追加

// Chunk 类型 1: 开始信号（首帧）
{
  "event_id": "f3b2a1c4-...",
  "timestamp": "2026-07-23T20:30:00+08:00",
  "type": "feedback_stream",
  "payload": {
    "session_id": "session-uuid",
    "chunk_type": "start",
    "task_title": "Python 函数基础",
    "profile_context": "理解偏慢但记忆牢固型"
  }
}

// Chunk 类型 2: 内容流（中间帧，可重复多次）
{
  "event_id": "f3b2a1c4-...",
  "timestamp": "2026-07-23T20:30:01+08:00",
  "type": "feedback_stream",
  "payload": {
    "session_id": "session-uuid",
    "chunk_type": "content",
    "text": "你上次学"变量作用域"时提到过" // 这是模型生成的部分文本
  }
}

// 后续 chunk 继续追加 text 字段
// 前端将这些 text 按序拼接成完整追问

// Chunk 类型 3: 结束信号（末帧+引导提示）
{
  "event_id": "f3b2a1c4-...",
  "timestamp": "2026-07-23T20:30:05+08:00",
  "type": "feedback_stream",
  "payload": {
    "session_id": "session-uuid",
    "chunk_type": "end",
    "full_question": "你上次学...完整的追问内容...",
    "hints": [
      "和之前比，这次理解起来是更容易还是更难？",
      "写代码的时候有卡住的地方吗？"
    ],
    "expects_reply": true
  }
}

// Chunk 类型 4: 回复响应（用户回复后，系统生成的回应）
{
  "event_id": "f3b2a1c4-...",
  "timestamp": "2026-07-23T20:30:20+08:00",
  "type": "feedback_stream",
  "payload": {
    "session_id": "session-uuid",
    "chunk_type": "response",
    "text": "明白了。函数参数这块你觉得需要再巩固，我把明天的计划从'函数进阶'改为'函数练习题+复习'，等练熟了再往后走。",
    "adjustment_summary": {
      "action": "replan",
      "affected_plan": "Python入门",
      "changes": ["tomorrow_task_changed: 函数进阶 → 函数练习题+复习"]
    }
  }
}
```

| `chunk_type` | 顺序 | 说明 | 关键字段 |
|-------------|------|------|---------|
| `start` | 第 1 帧 | 会话开始，展示上下文 | `task_title`, `profile_context` |
| `content` | 中间 N 帧 | 模型流式生成的文本片段 | `text`（前端逐帧追加） |
| `end` | 最后 1 帧 | 追问生成完毕 | `full_question`, `hints`, `expects_reply` |
| `response` | 用户回复后 | 系统回应的完整文本 | `text`, `adjustment_summary` |

---

### 3.3 `weekly_report` — 每周简报推送

**触发时机：** 每周一 08:00 自动生成并推送。

```typescript
// event: weekly_report
{
  "event_id": "r9c8b7a6-...",
  "timestamp": "2026-07-28T08:00:00+08:00",
  "type": "weekly_report",
  "payload": {
    "week_number": 3,
    "report_date": "2026-07-28",
    "summary": {
      "total_hours": 5.5,
      "hours_change": 1.0,
      "total_tasks_completed": 12,
      "streak_days": 5
    },
    "plan_progress": [
      {
        "plan_title": "Python入门",
        "nodes_completed": 3,
        "total_nodes": 10,
        "mastery_changes": [
          { "node": "Python 函数", "from": 40, "to": 75 },
          { "node": "Python 文件", "from": 0, "to": 35 }
        ]
      },
      {
        "plan_title": "英语口语",
        "nodes_completed": 1,
        "total_nodes": 8,
        "mastery_changes": [
          { "node": "英语词汇", "from": 60, "to": 65 }
        ]
      }
    ],
    "profile_updates": [
      "确认你属于"理解偏慢但记忆牢固"类型",
      "函数部分花了比预期多2天，但掌握后测试正确率达90%"
    ],
    "weak_spots": [
      {
        "node": "文件读写",
        "mastery": 35,
        "consecutive_stuck_days": 3,
        "suggestion": "建议下周安排2天集中突破"
      }
    ],
    "motivational_message": "这周你保持了5天连续学习，不错！函数部分虽然费了些功夫但掌握得很扎实，继续保持这个节奏。"
  }
}
```

---

### 3.4 `intervention` — 干预通知

**触发时机：** 用户中断后回归时，或遗忘复习排期生成时。

```typescript
// event: intervention
// 子类型 A: 中断恢复
{
  "event_id": "i1a2b3c4-...",
  "timestamp": "2026-07-25T10:30:00+08:00",
  "type": "intervention",
  "payload": {
    "subtype": "recovery",
    "days_inactive": 6,
    "message": "你已经有6天没学习了，没关系。根据你的学习记录，之前中断后恢复时安排太满反而容易再次中断。这周我们慢慢来，先每天20分钟，找回状态再说。",
    "recovery_plan": [
      { "day": 1, "minutes": 20, "task": "复习上次学过的内容" },
      { "day": 2, "minutes": 20, "task": "继续上次进度" },
      { "day": 3, "minutes": 25, "task": "恢复正常节奏" }
    ],
    "severity": "medium"
  }
}

// 子类型 B: 遗忘复习通知
{
  "event_id": "i2b3c4d5-...",
  "timestamp": "2026-07-26T08:00:00+08:00",
  "type": "intervention",
  "payload": {
    "subtype": "review",
    "message": "今天安排了一次复习任务：Python 变量与类型（上次学习：7月20日，已过6天）。",
    "review_count": 1,
    "review_nodes": ["Python 变量与类型"]
  }
}
```

| `subtype` | 触发条件 | 说明 |
|-----------|---------|------|
| `recovery` | 中断 >= 3 天后首次登录 | 恢复方案 |
| `review` | 到达遗忘复习间隔 | 复习任务推送 |

---

## 四、前端对接清单

前端 C 在对接 SSE 时需要处理：

| 事件类型 | 前端处理逻辑 | 对应组件/页面 |
|---------|-------------|-------------|
| `schedule_updated` | 刷新当日任务列表；如果是新的一天，展示通知提醒 | `DailyView.tsx`, toast 通知 |
| `feedback_stream` | 打开对话弹窗；`start` 帧清空气泡；`content` 帧追加文本；`end` 帧展示输入框；`response` 帧追加系统回复 | `ChatBubble.tsx` |
| `weekly_report` | 展示周报卡片弹窗或通知 | `WeeklyReport.tsx` |
| `intervention` (recovery) | 展示恢复方案弹窗，包含每日计划 | `DailyView.tsx` |
| `intervention` (review) | 在今日任务中标记"复习"标签 | `TaskCard.tsx` |

---

## 五、变更记录

| 日期 | 版本 | 变更内容 | 变更人 |
|------|------|---------|--------|
| 2026-07-23 | v1.0 | 首次定稿：定义 4 类 SSE 事件的完整格式 | Lead |
