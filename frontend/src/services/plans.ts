/**
 * 计划相关 API
 */

import api from "./api";
import {
  buildEdgesFromNodes,
  normalizeKnowledgeNode,
  normalizePlanDetail,
  toPlanSummary,
  type BackendPlanNodeRaw,
  type BackendPlanRaw,
  type CreatePlanRequest,
  type CreatePlanResponse,
  type KnowledgeNode,
  type PathGraphData,
  type PlanDetail,
  type PlanListResponse,
  type PlanSummary,
} from "@/types";

interface BackendPlanListRaw {
  plans?: BackendPlanRaw[];
  items?: BackendPlanRaw[];
  total_daily_budget?: number;
  user_daily_available?: number;
  remaining_daily?: number;
  total?: number;
}

interface BackendPlanDetailRaw extends BackendPlanRaw {
  nodes?: BackendPlanNodeRaw[];
  knowledge_nodes?: BackendPlanNodeRaw[];
  knowledge_graph?: {
    nodes?: BackendPlanNodeRaw[];
    edges?: Array<{ source: string | number; target: string | number }>;
  };
}

function normalizeGraph(
  raw: BackendPlanDetailRaw,
  detail: PlanDetail
): PathGraphData {
  const nodeRaw = raw.nodes ?? raw.knowledge_nodes ?? raw.knowledge_graph?.nodes ?? [];
  const nodes: KnowledgeNode[] = nodeRaw.map(normalizeKnowledgeNode);
  const edges = raw.knowledge_graph?.edges
    ? raw.knowledge_graph.edges.map((edge) => ({
        source: String(edge.source),
        target: String(edge.target),
      }))
    : buildEdgesFromNodes(nodes);

  return {
    nodes: nodes.length > 0 ? nodes : detail.total_nodes > 0 ? [] : [],
    edges,
  };
}

export async function fetchPlans(): Promise<PlanListResponse> {
  const { data } = await api.get<BackendPlanListRaw | BackendPlanRaw[]>('/plans');
  const list = Array.isArray(data)
    ? data
    : data.plans ?? data.items ?? [];

  const plans: PlanSummary[] = list.map((item) => toPlanSummary(normalizePlanDetail(item)));

  return {
    plans,
    total_daily_budget:
      !Array.isArray(data) ? data.total_daily_budget ?? 0 : plans.reduce((sum, p) => sum + p.daily_budget, 0),
    user_daily_available: !Array.isArray(data) ? data.user_daily_available ?? 90 : 90,
    remaining_daily: !Array.isArray(data) ? data.remaining_daily ?? 0 : 90 - plans.reduce((sum, p) => sum + p.daily_budget, 0),
  };
}

export async function fetchPlanDetail(id: string): Promise<{ plan: PlanDetail; graph: PathGraphData }> {
  const { data } = await api.get<BackendPlanDetailRaw>(`/plans/${id}`);
  const plan = normalizePlanDetail(data);
  return {
    plan,
    graph: normalizeGraph(data, plan),
  };
}

export async function createPlan(payload: CreatePlanRequest): Promise<CreatePlanResponse> {
  // 后端 LearningGoalRequest 仅消费 goal + priority；title 由前端本地保留
    const { data } = await api.post<BackendPlanDetailRaw | CreatePlanResponse>('/plans', {
        goal: payload.goal,
        priority: payload.priority,
        daily_budget: payload.daily_budget,
    });

    if (data && 'plan' in data && data.plan) {
    const wrapped = data as CreatePlanResponse;
        return {
            ...wrapped,
            plan: normalizePlanDetail(wrapped.plan as unknown as BackendPlanRaw, undefined, undefined, payload.title),
        };
    }

  const detail = data as BackendPlanDetailRaw;
  const plan = normalizePlanDetail(detail, undefined, undefined, payload.title);
  const nodes = (detail.nodes ?? []).map(normalizeKnowledgeNode);

  return {
    plan,
    feasibility_report: plan.feasibility_report ?? '',
    knowledge_nodes: nodes,
  };
}

export async function deletePlan(id: string): Promise<void> {
  await api.delete(`/plans/${id}`);
}
