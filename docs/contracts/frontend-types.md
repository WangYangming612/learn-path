# 前端 TypeScript 类型定义对照

> 版本：v1.0
> 最后更新：2026-07-23
> 用途：前端 C 开发 `frontend/src/types/index.ts` 时的参考

---

## 一、通用类型

```typescript
// ======= 全局响应包装 =======
interface ApiResponse<T> {
  code: number;        // 0=成功，其他=错误码
  message: string;     // 成功为"success"，错误时为具体信息
  data: T | null;
}

// ======= 分页响应 =======
interface PaginatedData<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// ======= 用户 =======
interface UserInfo {
  user_id: string;
  username: string;
  email: string | null;
  daily_available_minutes: number;
  is_active: boolean;
  created_at: string;    // ISO 8601
}

interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: UserInfo;
}
```

---

## 二、计划模块类型

```typescript
// ======= 计划 =======
interface PlanSummary {
  id: string;
  title: string;
  priority: 1 | 2 | 3;
  daily_budget: number;
  status: "active" | "paused" | "completed";
  estimated_total_hours: number;
  progress_percent: number;   // 0-100
  completed_nodes: number;
  total_nodes: number;
  start_date: string;         // YYYY-MM-DD
  end_date: string;
  created_at: string;
}

interface PlanDetail extends PlanSummary {
  goal: string;
  time_preference: TimePreference;
  feasibility_report: string | null;
}

interface TimePreference {
  morning: number;     // 0-100
  afternoon: number;   // 0-100
  evening: number;     // 0-100
  // 三项之和 = 100
}

interface CreatePlanRequest {
  title: string;
  goal: string;
  priority: 1 | 2 | 3;
  daily_budget: number;
  time_preference?: Partial<TimePreference>;
  start_date: string;
  end_date: string;
}

interface CreatePlanResponse {
  plan: PlanDetail;
  feasibility_report: string;
  knowledge_nodes: KnowledgeNode[];
}

interface PlanListResponse {
  plans: PlanSummary[];
  total_daily_budget: number;
  user_daily_available: number;
  remaining_daily: number;
}
```

---

## 三、知识节点（DAG）类型

```typescript
// ======= 知识节点 =======
interface KnowledgeNode {
  id: string;
  plan_id?: string;
  title: string;
  description: string;
  estimated_minutes: number;
  adjusted_minutes?: number;    // 经画像系数调整后的值
  prerequisite_ids: string[];   // 前置节点 ID
  order_index: number;
  status: "pending" | "in_progress" | "mastered" | "reviewing";
  mastery_level: number;        // 0-100
}

interface GraphEdge {
  source: string;   // 前置节点 ID
  target: string;   // 后置节点 ID
}

interface PathGraphResponse {
  nodes: KnowledgeNode[];
  edges: GraphEdge[];
}

// React Flow 渲染时需要转换：
// nodes: nodes.map(n => ({ id: n.id, data: { label: n.title, ...n }, position: { x: 0, y: 0 } }))
// edges: edges.map(e => ({ id: `${e.source}->${e.target}`, source: e.source, target: e.target }))
```

---

## 四、每日任务类型

```typescript
// ======= 每日任务 =======
interface DailyTask {
  id: string;
  plan_id: string;
  plan_title: string;
  plan_priority: 1 | 2 | 3;
  knowledge_node_id: string;
  title: string;
  guide_content: string | null;   // Markdown 格式
  date: string;                    // YYYY-MM-DD
  start_time: string | null;       // HH:MM 或 null
  end_time: string | null;
  duration_minutes: number;
  status: "pending" | "completed" | "skipped";
  is_review: boolean;
  sort_order: number;
}

interface DailyTasksResponse {
  date: string;
  total_tasks: number;
  total_minutes: number;
  remaining_minutes: number;
  tasks: DailyTask[];
}

interface ReorderRequest {
  task_ids: string[];   // 按新顺序排列
}
```

---

## 五、画像模块类型

```typescript
// ======= 画像维度 =======
interface ProfileDimension {
  label: string;
  confidence: number;       // 0-100
  evidence: string[];       // 判断依据
}

interface UserProfile {
  learning_style: ProfileDimension;
  best_time_slots: ProfileDimension;
  learning_rhythm: ProfileDimension;
  feedback_baseline: ProfileDimension;
  persistence: ProfileDimension;
  knowledge_retention: ProfileDimension;
}

interface ProfileResponse {
  profile: UserProfile;
  total_feedback_count: number;
  last_calibrated_at: string | null;
  needs_initial_survey: boolean;
  initial_survey_question: string | null;
}

// ======= 画像历史 =======
interface ProfileHistoryEntry {
  timestamp: string;
  source: string;           // 如 "feedback_session:xxx" / "initial_survey"
  changes: string[];        // 如 ["learning_style: 未知 → 理解偏慢型 (+78%)"]
}

interface ProfileHistoryResponse {
  history: ProfileHistoryEntry[];
}

// ======= 摸底问答 =======
interface SurveyNextResponse {
  complete: boolean;
  round: number;
  total_rounds: number;
  question: string;
}

interface SurveyAnswerResponse {
  profile_complete: boolean;
  needs_followup: boolean;
  next_question: string | null;
}

// ======= 维度校准 =======
interface CalibrateResponse {
  dimension: string;
  old_label: string;
  old_confidence: number;
  new_label: string;
  new_confidence: number;
  message: string;
}
```

---

## 六、反馈模块类型

```typescript
// ======= 反馈 =======
interface StartFeedbackResponse {
  session_id: string;
  message: string;
}

interface ReplyFeedbackRequest {
  session_id: string;
  reply: string;
}

interface ReplyFeedbackResponse {
  session_id: string;
  action_taken: string;         // 如 "replan + profile_update"
  response_preview: string;
  needs_followup: boolean;
}

// ======= SSE 事件类型（详见 sse-events.md） =======
interface SSEEventData {
  event_id: string;
  timestamp: string;
  type: EventType;
  payload: Record<string, any>;
}

type EventType =
  | "schedule_updated"
  | "feedback_stream"
  | "weekly_report"
  | "intervention";

// feedback_stream 的 chunk_type
type FeedbackChunkType =
  | "start"      // 首帧：会话开始
  | "content"    // 中间帧：文本片段
  | "end"        // 末帧：追问完毕
  | "response";  // 用户回复后：系统回应

// intervention 的子类型
type InterventionSubtype =
  | "recovery"   // 中断恢复
  | "review";    // 遗忘复习
```

---

## 七、学习日记类型

```typescript
// ======= 学习日记 =======
interface JournalEntry {
  id: string;
  plan_title: string;
  knowledge_node_title: string;
  content: string;
  created_at: string;
}

interface CreateJournalRequest {
  task_id: string;
  content: string;      // 1-500 字
}
```

---

## 八、组件 Props 类型示例

```typescript
// ======= 复用组件 Props =======

// 路径图组件
interface PathGraphProps {
  nodes: KnowledgeNode[];
  edges: GraphEdge[];
  onNodeClick?: (nodeId: string) => void;
  onNodeSkip?: (nodeId: string) => void;
  onNodePrioritize?: (nodeId: string) => void;
  readOnly?: boolean;
}

// 任务卡片组件
interface TaskCardProps {
  task: DailyTask;
  onStatusChange: (taskId: string, status: "completed" | "skipped") => void;
  onFeedback?: (taskId: string) => void;
  onJournal?: (taskId: string) => void;
  dragHandleProps?: Record<string, any>;  // dnd-kit
}

// 画像雷达图组件
interface ProfileRadarProps {
  profile: UserProfile;
  width?: number;
  height?: number;
}

// 对话气泡组件
interface ChatBubbleProps {
  messages: ChatMessage[];
  onSend: (text: string) => void;
  isStreaming: boolean;
  hints?: string[];              // 引导提示列表
}

interface ChatMessage {
  id: string;
  role: "system" | "user";
  content: string;
  timestamp: string;
  isStreaming?: boolean;         // 是否正在流式输出
}

// 周报卡片组件
interface WeeklyReportProps {
  report: WeeklyReportData;
  visible: boolean;
  onClose: () => void;
}

interface WeeklyReportData {
  week_number: number;
  report_date: string;
  summary: {
    total_hours: number;
    hours_change: number;
    total_tasks_completed: number;
    streak_days: number;
  };
  plan_progress: Array<{
    plan_title: string;
    nodes_completed: number;
    total_nodes: number;
    mastery_changes: Array<{ node: string; from: number; to: number }>;
  }>;
  profile_updates: string[];
  weak_spots: Array<{
    node: string;
    mastery: number;
    consecutive_stuck_days: number;
    suggestion: string;
  }>;
  motivational_message: string;
}
```

---

## 九、状态管理 Store 结构建议

```typescript
// stores/authStore.ts
interface AuthState {
  token: string | null;
  user: UserInfo | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  checkAuth: () => Promise<void>;
}

// stores/planStore.ts
interface PlanState {
  plans: PlanSummary[];
  currentPlan: PlanDetail | null;
  currentPath: PathGraphResponse | null;
  loading: boolean;
  fetchPlans: () => Promise<void>;
  fetchPlanDetail: (id: string) => Promise<void>;
  createPlan: (req: CreatePlanRequest) => Promise<CreatePlanResponse>;
}

// stores/appStore.ts
interface AppState {
  todayTasks: DailyTask[];
  feedbackSessionId: string | null;
  sseConnected: boolean;
  fetchTodayTasks: () => Promise<void>;
  setFeedbackSession: (sessionId: string | null) => void;
}
```

---

## 十、变更记录

| 日期 | 版本 | 变更内容 | 变更人 |
|------|------|---------|--------|
| 2026-07-23 | v1.0 | 首次定稿：定义全部 TypeScript 类型 | Lead |
