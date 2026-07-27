/**
 * 每日任务 API
 * 对齐 backend/app/api/v1/tasks.py
 */

import api from "./api";
import {
  normalizeDailyTask,
  type BackendDailyTaskRaw,
  type DailyTask,
  type GenerateTasksRequest,
  type GenerateTasksResponse,
  type TaskStatus,
} from "@/types";

const ORDER_KEY_PREFIX = "learnpath_task_order_";

function todayKey(date = new Date()): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** 读取本地拖拽顺序（后端暂无 reorder 接口） */
export function readLocalTaskOrder(date = todayKey()): string[] {
  try {
    const raw = localStorage.getItem(`${ORDER_KEY_PREFIX}${date}`);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

/** 持久化本地拖拽顺序 */
export function writeLocalTaskOrder(taskIds: string[], date = todayKey()): void {
  try {
    localStorage.setItem(`${ORDER_KEY_PREFIX}${date}`, JSON.stringify(taskIds));
  } catch {
    // ignore quota / private mode
  }
}

/** 按本地顺序重排，未出现在本地列表的任务追加到末尾 */
export function applyLocalOrder(tasks: DailyTask[], date = todayKey()): DailyTask[] {
  const order = readLocalTaskOrder(date);
  if (order.length === 0) {
    return tasks.map((task, index) => ({ ...task, sort_order: index }));
  }

  const map = new Map(tasks.map((task) => [task.id, task]));
  const ordered: DailyTask[] = [];

  for (const id of order) {
    const task = map.get(id);
    if (task) {
      ordered.push(task);
      map.delete(id);
    }
  }
  for (const task of map.values()) {
    ordered.push(task);
  }

  return ordered.map((task, index) => ({ ...task, sort_order: index }));
}

function normalizeList(raw: BackendDailyTaskRaw[]): DailyTask[] {
  return raw.map((item, index) => normalizeDailyTask(item, index));
}

/** GET /tasks/today → DailyTask[] */
export async function fetchTodayTasks(): Promise<DailyTask[]> {
  const { data } = await api.get<BackendDailyTaskRaw[]>("/tasks/today");
  const list = Array.isArray(data) ? data : [];
  return applyLocalOrder(normalizeList(list));
}

/** PUT /tasks/{task_id}/status */
export async function updateTaskStatus(
  taskId: string,
  status: TaskStatus
): Promise<DailyTask> {
  const { data } = await api.put<BackendDailyTaskRaw>(`/tasks/${taskId}/status`, {
    status,
  });
  return normalizeDailyTask(data);
}

/** POST /tasks/generate */
export async function generateTodayTasks(
  payload: GenerateTasksRequest = {}
): Promise<GenerateTasksResponse> {
  const body: Record<string, unknown> = {};
  if (payload.scheduled_date) body.scheduled_date = payload.scheduled_date;
  if (payload.daily_budget != null) body.daily_budget = payload.daily_budget;

  const { data } = await api.post<{
    scheduled_date: string;
    tasks: BackendDailyTaskRaw[];
  }>("/tasks/generate", body, { timeout: 120000 });

  const date = String(data.scheduled_date).slice(0, 10);
  const tasks = applyLocalOrder(normalizeList(data.tasks ?? []), date);

  return { scheduled_date: date, tasks };
}
