/**
 * 今日任务数据 Hook
 */

import { useCallback, useState } from "react";
import * as tasksApi from "@/services/tasks";
import type { DailyTask, TaskStatus } from "@/types";

function todayISO(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function useTasks() {
  const [tasks, setTasks] = useState<DailyTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [date, setDate] = useState(todayISO);

  const fetchToday = useCallback(async () => {
    setLoading(true);
    try {
      const list = await tasksApi.fetchTodayTasks();
      setTasks(list);
      setDate(todayISO());
      return list;
    } finally {
      setLoading(false);
    }
  }, []);

  const generate = useCallback(async (dailyBudget?: number) => {
    setGenerating(true);
    try {
      const result = await tasksApi.generateTodayTasks({
        scheduled_date: todayISO(),
        daily_budget: dailyBudget,
      });
      setTasks(result.tasks);
      setDate(result.scheduled_date);
      return result.tasks;
    } finally {
      setGenerating(false);
    }
  }, []);

  const updateStatus = useCallback(async (taskId: string, status: TaskStatus) => {
    const updated = await tasksApi.updateTaskStatus(taskId, status);
    setTasks((prev) =>
      prev.map((task) =>
        task.id === taskId
          ? { ...updated, sort_order: task.sort_order }
          : task
      )
    );
    return updated;
  }, []);

  const reorder = useCallback(
    (orderedIds: string[]) => {
      setTasks((prev) => {
        const map = new Map(prev.map((task) => [task.id, task]));
        const next = orderedIds
          .map((id, index) => {
            const task = map.get(id);
            return task ? { ...task, sort_order: index } : null;
          })
          .filter((task): task is DailyTask => task != null);

        // 兜底：漏掉的任务追加末尾
        for (const task of prev) {
          if (!orderedIds.includes(task.id)) {
            next.push({ ...task, sort_order: next.length });
          }
        }

        tasksApi.writeLocalTaskOrder(
          next.map((task) => task.id),
          date
        );
        return next;
      });
    },
    [date]
  );

  const stats = {
    total: tasks.length,
    completed: tasks.filter((t) => t.status === "completed").length,
    skipped: tasks.filter((t) => t.status === "skipped").length,
    pending: tasks.filter((t) => t.status === "pending").length,
    totalMinutes: tasks.reduce((sum, t) => sum + (t.duration_minutes || 0), 0),
    remainingMinutes: tasks
      .filter((t) => t.status === "pending")
      .reduce((sum, t) => sum + (t.duration_minutes || 0), 0),
  };

  return {
    tasks,
    date,
    loading,
    generating,
    stats,
    fetchToday,
    generate,
    updateStatus,
    reorder,
  };
}

export default useTasks;
