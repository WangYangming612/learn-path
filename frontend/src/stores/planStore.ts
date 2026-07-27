/**
 * 计划状态 Store
 */

import { create } from "zustand";
import * as plansApi from "@/services/plans";
import {
  normalizePlanDetail,
  resolvePlanTitle,
  type BackendPlanRaw,
  type CreatePlanRequest,
  type PathGraphData,
  type PlanDetail,
  type PlanSummary,
} from "@/types";

const PLAN_CACHE_KEY = "learnpath_plan_cache";

function readPlanCache(): PlanDetail[] {
  try {
    const raw = localStorage.getItem(PLAN_CACHE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Array<PlanDetail | BackendPlanRaw>;
    return Array.isArray(parsed) ? parsed.map(normalizePlanItem) : [];
  } catch {
    return [];
  }
}

function writePlanCache(plans: PlanDetail[]): void {
  try {
    localStorage.setItem(PLAN_CACHE_KEY, JSON.stringify(plans));
  } catch {
    // ignore cache write failures
  }
}

function toSummary(plan: PlanDetail): PlanSummary {
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

function normalizePlanItem(raw: PlanDetail | BackendPlanRaw): PlanDetail {
  const asDetail = raw as PlanDetail;
  const titleHint = asDetail.local_title ?? asDetail.title;
  return normalizePlanDetail(raw as BackendPlanRaw, undefined, undefined, titleHint);
}

function buildLocalPlan(payload: CreatePlanRequest): PlanDetail {
  const now = new Date().toISOString();
  const estimated_total_hours = Math.max(1, Math.round((payload.daily_budget * 12) / 60) || 1);
  const title = payload.title.trim() || payload.goal.trim() || "未命名计划";

  return {
    id: `local-${Date.now()}`,
    title,
    local_title: title,
    goal: payload.goal,
    description: payload.goal,
    priority: payload.priority,
    daily_budget: payload.daily_budget,
    status: "draft",
    estimated_total_hours,
    progress_percent: 0,
    completed_nodes: 0,
    total_nodes: 0,
    start_date: payload.start_date ?? null,
    end_date: payload.end_date ?? null,
    created_at: now,
    updated_at: now,
    time_preference: {
      morning: 0,
      afternoon: 20,
      evening: 80,
    },
    feasibility_report: "当前计划已本地创建，后端创建失败时仍可继续编辑查看。",
    parsed_goal: null,
  };
}

function applyUserTitle(plan: PlanDetail, userTitle: string, goal: string): PlanDetail {
  const title = userTitle.trim() || resolvePlanTitle({ ...plan, goal }) || "未命名计划";
  return {
    ...plan,
    title,
    local_title: title,
    goal: plan.goal?.trim() || goal.trim() || plan.description || "",
  };
}

interface PlanState {
  plans: PlanSummary[];
  currentPlan: PlanDetail | null;
  currentGraph: PathGraphData | null;
  loading: boolean;
  listLoaded: boolean;

  fetchPlans: () => Promise<void>;
  fetchPlanDetail: (id: string) => Promise<void>;
  createPlan: (payload: CreatePlanRequest) => Promise<PlanDetail>;
  deletePlan: (id: string) => Promise<void>;
  clearCurrentPlan: () => void;
}

export const usePlanStore = create<PlanState>((set, get) => ({
  plans: readPlanCache().map(toSummary),
  currentPlan: null,
  currentGraph: null,
  loading: false,
  listLoaded: false,

  fetchPlans: async () => {
    set({ loading: true });
    try {
      const cached = readPlanCache();
      set({ plans: cached.map(toSummary), loading: false, listLoaded: true });
    } catch (error) {
      set({ loading: false, listLoaded: true });
      throw error;
    }
  },

  fetchPlanDetail: async (id) => {
    set({ loading: true });
    try {
      const cached = readPlanCache();
      const localPlan = cached.find((item) => String(item.id) === String(id));
      if (localPlan) {
        set({ currentPlan: localPlan, currentGraph: { nodes: [], edges: [] }, loading: false });
        return;
      }

      const fallback = get().plans.find((item) => String(item.id) === String(id));
      if (fallback) {
        const detail: PlanDetail = normalizePlanDetail(
          {
            id: fallback.id,
            title: fallback.title,
            status: fallback.status,
            priority: fallback.priority,
            created_at: fallback.created_at,
            start_date: fallback.start_date,
            end_date: fallback.end_date,
            description: fallback.description ?? undefined,
            goal: fallback.goal ?? undefined,
            daily_budget: fallback.daily_budget,
            estimated_total_hours: fallback.estimated_total_hours,
            progress_percent: fallback.progress_percent,
            completed_nodes: fallback.completed_nodes,
            total_nodes: fallback.total_nodes,
          },
          undefined,
          undefined,
          fallback.local_title ?? fallback.title
        );
        set({ currentPlan: detail, currentGraph: { nodes: [], edges: [] }, loading: false });
        return;
      }

      set({ loading: false });
      throw new Error("未找到该计划");
    } catch (error) {
      set({ loading: false });
      throw error;
    }
  },

  createPlan: async (payload) => {
    set({ loading: true });
    const userTitle = payload.title.trim();
    const userGoal = payload.goal.trim();
    const localPlan = buildLocalPlan({ ...payload, title: userTitle, goal: userGoal });

    try {
      const result = await plansApi.createPlan({ ...payload, title: userTitle, goal: userGoal });
      const normalizedPlan = normalizePlanDetail(
        {
          id: result.plan.id,
          title: result.plan.title,
          status: result.plan.status,
          priority: result.plan.priority,
          created_at: result.plan.created_at,
          start_date: result.plan.start_date,
          end_date: result.plan.end_date,
          description: result.plan.description,
          goal: result.plan.goal || userGoal,
          daily_budget: result.plan.daily_budget ?? payload.daily_budget,
          estimated_total_hours: result.plan.estimated_total_hours,
          progress_percent: result.plan.progress_percent,
          completed_nodes: result.plan.completed_nodes,
          total_nodes: result.plan.total_nodes,
          time_preference: result.plan.time_preference,
          feasibility_report: result.plan.feasibility_report,
          parsed_goal: result.plan.parsed_goal ?? undefined,
        },
        undefined,
        undefined,
        userTitle
      );
      const mergedPlan = applyUserTitle(normalizedPlan, userTitle, userGoal);
      const plans = readPlanCache();
      const nextPlans = [mergedPlan, ...plans.filter((item) => String(item.id) !== String(mergedPlan.id))];
      writePlanCache(nextPlans);

      set({
        currentPlan: mergedPlan,
        currentGraph: { nodes: result.knowledge_nodes, edges: [] },
        plans: nextPlans.map(toSummary),
        loading: false,
      });
      return mergedPlan;
    } catch {
      const plans = readPlanCache();
      const nextPlans = [localPlan, ...plans.filter((item) => String(item.id) !== String(localPlan.id))];
      writePlanCache(nextPlans);
      set({
        currentPlan: localPlan,
        currentGraph: { nodes: [], edges: [] },
        plans: nextPlans.map(toSummary),
        loading: false,
      });
      return localPlan;
    }
  },

  deletePlan: async (id) => {
    set({ loading: true });
    try {
      await plansApi.deletePlan(id);
    } catch {
      // 允许离线/后端未实现删除时继续删除本地缓存
    }

    const nextPlans = readPlanCache().filter((item) => String(item.id) !== String(id));
    writePlanCache(nextPlans);

    set((state) => ({
      plans: state.plans.filter((item) => String(item.id) !== String(id)),
      currentPlan: state.currentPlan && String(state.currentPlan.id) === String(id) ? null : state.currentPlan,
      currentGraph: state.currentPlan && String(state.currentPlan.id) === String(id) ? null : state.currentGraph,
      loading: false,
    }));
  },

  clearCurrentPlan: () => set({ currentPlan: null, currentGraph: null }),
}));
