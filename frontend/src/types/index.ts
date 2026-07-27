/**
 * 前端 TypeScript 类型定义
 * 对齐 docs/contracts/frontend-types.md，并兼容当前后端字段差异
 */

/** 全局 API 响应包装（契约格式） */
export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T | null;
}

/** 分页响应 */
export interface PaginatedData<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** 用户信息 */
export interface UserInfo {
  user_id: string;
  username: string;
  email: string | null;
  daily_available_minutes: number;
  is_active: boolean;
  created_at: string;
}

/** 登录响应 */
export interface LoginResponse {
  access_token: string;
  token_type: "bearer" | string;
  expires_in?: number;
  user?: UserInfo;
}

/** 注册请求 */
export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
}

/** 登录请求 */
export interface LoginRequest {
  username: string;
  password: string;
}

/** 后端原始用户响应（id 为 number） */
export interface BackendUserRaw {
  id?: number | string;
  user_id?: string;
  username: string;
  email?: string | null;
  daily_available_minutes?: number;
  is_active?: boolean;
  created_at?: string;
}

/** 将后端用户字段归一化为前端 UserInfo */
export function normalizeUser(raw: BackendUserRaw): UserInfo {
  const id = raw.user_id ?? (raw.id != null ? String(raw.id) : "");
  return {
    user_id: id,
    username: raw.username,
    email: raw.email ?? null,
    daily_available_minutes: raw.daily_available_minutes ?? 90,
    is_active: raw.is_active ?? true,
    created_at: raw.created_at ?? new Date().toISOString(),
  };
}

/* ========== 计划模块 ========== */

export type PlanStatus = "draft" | "active" | "paused" | "completed";
export type PlanPriority = 1 | 2 | 3;
export type NodeStatus = "pending" | "in_progress" | "mastered" | "reviewing";

export interface TimePreference {
  morning: number;
  afternoon: number;
  evening: number;
}

export interface ParsedLearningGoal {
  domain: string;
  duration_months: number;
  current_level: string;
  target_depth: string;
}

export interface KnowledgeNode {
  id: string;
  plan_id?: string;
  title: string;
  description: string;
  estimated_minutes: number;
  adjusted_minutes?: number;
  prerequisite_ids: string[];
  order_index: number;
  status: NodeStatus;
  mastery_level: number;
}

export interface GraphEdge {
  source: string;
  target: string;
}

export interface PathGraphData {
  nodes: KnowledgeNode[];
  edges: GraphEdge[];
}

export interface PlanSummary {
  id: string;
  title: string;
  local_title?: string | null;
  priority: PlanPriority;
  daily_budget: number;
  status: PlanStatus | string;
  estimated_total_hours: number;
  progress_percent: number;
  completed_nodes: number;
  total_nodes: number;
  start_date: string | null;
  end_date: string | null;
  created_at: string;
  description?: string | null;
  goal?: string | null;
}

export interface PlanDetail extends PlanSummary {
  goal: string;
  time_preference: TimePreference;
  feasibility_report: string | null;
  parsed_goal?: ParsedLearningGoal | null;
  updated_at?: string | null;
}

/** 创建向导表单（前端收集；当前后端仅消费 goal + priority） */
export interface CreatePlanRequest {
  title: string;
  goal: string;
  priority: PlanPriority;
  daily_budget: number;
  time_preference?: Partial<TimePreference>;
  start_date?: string;
  end_date?: string;
}

export interface CreatePlanResponse {
  plan: PlanDetail;
  feasibility_report: string;
  knowledge_nodes: KnowledgeNode[];
}

export interface PlanListResponse {
  plans: PlanSummary[];
  total_daily_budget: number;
  user_daily_available: number;
  remaining_daily: number;
}

/** 当前后端创建计划原始响应 */
export interface BackendPlanRaw {
  id: number | string;
  title: string;
  description?: string | null;
  status: string;
  priority: number;
  start_date?: string | null;
  end_date?: string | null;
  created_at: string;
  updated_at?: string | null;
  nodes?: BackendPlanNodeRaw[];
  parsed_goal?: ParsedLearningGoal;
  goal?: string;
  daily_budget?: number;
  time_preference?: TimePreference;
  feasibility_report?: string | null;
  estimated_total_hours?: number;
  progress_percent?: number;
  completed_nodes?: number;
  total_nodes?: number;
  node_count?: number;
}

export interface BackendPlanNodeRaw {
  id: number | string;
  plan_id?: number | string;
  title: string;
  description?: string | null;
  estimated_minutes: number;
  adjusted_minutes?: number;
  prerequisite_ids?: Array<number | string>;
  order_index: number;
  status?: NodeStatus | string;
  mastery_level?: number;
}

export function normalizeKnowledgeNode(raw: BackendPlanNodeRaw): KnowledgeNode {
  return {
    id: String(raw.id),
    plan_id: raw.plan_id != null ? String(raw.plan_id) : undefined,
    title: raw.title,
    description: raw.description ?? "",
    estimated_minutes: raw.estimated_minutes,
    adjusted_minutes: raw.adjusted_minutes,
    prerequisite_ids: (raw.prerequisite_ids ?? []).map(String),
    order_index: raw.order_index,
    status: (raw.status as NodeStatus) || "pending",
    mastery_level: raw.mastery_level ?? 0,
  };
}

export function buildEdgesFromNodes(nodes: KnowledgeNode[]): GraphEdge[] {
  const edges: GraphEdge[] = [];
  for (const node of nodes) {
    for (const pre of node.prerequisite_ids) {
      edges.push({ source: pre, target: node.id });
    }
  }
  return edges;
}

function isPlaceholderTitle(title?: string | null): boolean {
  const normalized = title?.trim();
  return !normalized || ["未命名计划", "untitled", "unnamed"].includes(normalized.toLowerCase());
}

/** 展示用计划名称：用户填写名 > 后端标题 > 目标/描述 > 占位 */
export function resolvePlanTitle(
  plan: Partial<Pick<PlanSummary, "title" | "local_title" | "goal" | "description">> | null | undefined
): string {
  if (!plan) return "未命名计划";
  const candidates = [plan.local_title, plan.title, plan.goal, plan.description];
  for (const candidate of candidates) {
    const trimmed = candidate?.trim();
    if (trimmed && !isPlaceholderTitle(trimmed)) return trimmed;
  }
  return "未命名计划";
}

export function normalizePlanDetail(
  raw: BackendPlanRaw,
  nodes?: KnowledgeNode[],
  feasibility?: string | null,
  titleFallback?: string
): PlanDetail {
  const knowledgeNodes = nodes ?? (raw.nodes ?? []).map(normalizeKnowledgeNode);
  const totalMinutes = knowledgeNodes.reduce(
    (sum, n) => sum + (n.adjusted_minutes ?? n.estimated_minutes),
    0
  );
  const completed = knowledgeNodes.filter((n) => n.status === "mastered").length;
  const total = knowledgeNodes.length;
  const dailyBudget = raw.daily_budget ?? 30;
  const rawLocalTitle = (raw as BackendPlanRaw & { local_title?: string | null }).local_title?.trim() || "";
  // 用户显式填写的名称优先于后端 domain 标题
  const preferredTitle = titleFallback?.trim() || rawLocalTitle || "";
  const rawTitle = raw.title?.trim() || "";
  const goalOrDesc = raw.goal?.trim() || raw.description?.trim() || "";
  const normalizedTitle =
    (!isPlaceholderTitle(preferredTitle) ? preferredTitle : "") ||
    (!isPlaceholderTitle(rawTitle) ? rawTitle : "") ||
    goalOrDesc ||
    "未命名计划";
  const localTitle = preferredTitle || normalizedTitle;

  return {
    id: String(raw.id),
    title: normalizedTitle,
    local_title: localTitle,
    goal: raw.goal ?? raw.description ?? "",
    description: raw.description ?? raw.goal ?? null,
    priority: (raw.priority as PlanPriority) || 2,
    daily_budget: dailyBudget,
    status: raw.status,
    estimated_total_hours:
      raw.estimated_total_hours ?? Math.round((totalMinutes / 60) * 10) / 10,
    progress_percent:
      raw.progress_percent ??
      (total > 0 ? Math.round((completed / total) * 100) : 0),
    completed_nodes: raw.completed_nodes ?? completed,
    total_nodes: raw.total_nodes ?? raw.node_count ?? total,
    start_date: raw.start_date ?? null,
    end_date: raw.end_date ?? null,
    created_at: raw.created_at,
    updated_at: raw.updated_at ?? null,
    time_preference: raw.time_preference ?? {
      morning: 0,
      afternoon: 20,
      evening: 80,
    },
    feasibility_report: feasibility ?? raw.feasibility_report ?? null,
    parsed_goal: raw.parsed_goal ?? null,
  };
}

export function toPlanSummary(plan: PlanDetail): PlanSummary {
  const title = resolvePlanTitle(plan);
  return {
    id: plan.id,
    title,
    local_title: plan.local_title?.trim() || title,
    priority: plan.priority,
    daily_budget: plan.daily_budget,
    status: plan.status,
    estimated_total_hours: plan.estimated_total_hours,
    progress_percent: plan.progress_percent,
    completed_nodes: plan.completed_nodes,
    total_nodes: plan.total_nodes,
    start_date: plan.start_date,
    end_date: plan.end_date,
    created_at: plan.created_at,
    description: plan.description,
    goal: plan.goal,
  };
}

/* ========== 每日任务模块 ========== */

export type TaskStatus = "pending" | "completed" | "skipped";

export interface DailyTask {
  id: string;
  plan_id: string;
  knowledge_node_id: string | null;
  plan_title: string | null;
  title: string;
  description: string | null;
  scheduled_date: string;
  start_time: string | null;
  end_time: string | null;
  duration_minutes: number;
  guide_content: string | null;
  status: TaskStatus;
  completed_at: string | null;
  /** 前端本地排序序号（后端暂无 reorder API） */
  sort_order: number;
}

export interface BackendDailyTaskRaw {
  id: number | string;
  plan_id: number | string;
  knowledge_node_id?: number | string | null;
  plan_title?: string | null;
  title: string;
  description?: string | null;
  scheduled_date: string;
  start_time?: string | null;
  end_time?: string | null;
  duration_minutes: number;
  guide_content?: string | null;
  status: TaskStatus | string;
  completed_at?: string | null;
}

export interface GenerateTasksRequest {
  scheduled_date?: string;
  daily_budget?: number;
}

export interface GenerateTasksResponse {
  scheduled_date: string;
  tasks: DailyTask[];
}

function formatTimeField(value?: string | null): string | null {
  if (!value) return null;
  // FastAPI time 可能是 "HH:MM:SS" 或 "HH:MM:SS.micro"
  return value.slice(0, 5);
}

export function normalizeDailyTask(
  raw: BackendDailyTaskRaw,
  sortOrder = 0
): DailyTask {
  return {
    id: String(raw.id),
    plan_id: String(raw.plan_id),
    knowledge_node_id:
      raw.knowledge_node_id != null ? String(raw.knowledge_node_id) : null,
    plan_title: raw.plan_title ?? null,
    title: raw.title,
    description: raw.description ?? null,
    scheduled_date: String(raw.scheduled_date).slice(0, 10),
    start_time: formatTimeField(raw.start_time),
    end_time: formatTimeField(raw.end_time),
    duration_minutes: raw.duration_minutes,
    guide_content: raw.guide_content ?? null,
    status: (raw.status as TaskStatus) || "pending",
    completed_at: raw.completed_at ?? null,
    sort_order: sortOrder,
  };
}

/* ========== 反馈模块 ========== */

export type FeedbackSignal =
  | "too_easy"
  | "normal"
  | "stuck"
  | "need_practice"
  | string;

/** 对齐后端 POST /feedback/start 的 SSE 事件 */
export type FeedbackStreamEvent =
  | { type: "question_chunk"; content: string }
  | { type: "question_done"; session_id: string }
  | { type: "error"; content: string };

export interface FeedbackReplyRequest {
  session_id: string;
  reply: string;
}

export interface FeedbackReplyResponse {
  signal: FeedbackSignal;
  confidence_delta: number;
  replan_triggered: boolean;
  profile_updates: Record<string, unknown>;
  system_response: string;
}

export interface ChatMessage {
  id: string;
  role: "assistant" | "user" | "system";
  content: string;
  streaming?: boolean;
}
