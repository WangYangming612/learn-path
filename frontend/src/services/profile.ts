/**
 * 画像相关 API
 */

import api from "./api";
import type {
  BackendProfileRaw,
  ProfileData,
  ProfileHistoryItem,
  ProfileHistoryResponse,
  ProfileResponse,
  ProfileTimelineItem,
} from "@/types/profile";

function normalizeMetric(raw: unknown) {
  const value = raw as { label?: string; confidence?: number } | undefined;
  return {
    label: value?.label ?? "",
    confidence: typeof value?.confidence === "number" ? value.confidence : 0,
  };
}

function normalizeProfile(raw: BackendProfileRaw): ProfileData {
  return {
    learning_style: normalizeMetric(raw.learning_style),
    best_time: normalizeMetric(raw.best_time),
    learning_rhythm: normalizeMetric(raw.learning_rhythm),
    feedback_baseline: normalizeMetric(raw.feedback_baseline),
    persistence: normalizeMetric(raw.persistence),
    knowledge_retention: normalizeMetric(raw.knowledge_retention),
  };
}

function toTimelineItems(
  history: ProfileHistoryItem[] | undefined,
  fallbackUpdatedAt?: string | null
): ProfileTimelineItem[] {
  const items = (history ?? []).map((item) => ({
    timestamp: item.timestamp,
    title: item.changes[0]?.title ?? item.source,
    reason: item.changes[0]?.reason ?? "",
    changes: item.changes,
  }));

  if (items.length > 0) return items;

  if (!fallbackUpdatedAt) return [];

  return [
    {
      timestamp: fallbackUpdatedAt,
      title: "画像已更新",
      reason: "基于最近一次反馈与任务完成情况刷新画像",
      changes: [],
    },
  ];
}

export async function fetchProfile(): Promise<ProfileResponse> {
  const { data } = await api.get<BackendProfileRaw>("/profile");
  return {
    profile: normalizeProfile(data),
    total_feedback_count: data.total_feedback_count ?? 0,
    last_calibrated_at: data.last_calibrated_at ?? null,
    needs_initial_survey: data.needs_initial_survey ?? false,
    initial_survey_question: data.initial_survey_question ?? null,
    updated_at: data.updated_at ?? data.last_calibrated_at ?? null,
  };
}

export async function fetchProfileHistory(): Promise<ProfileHistoryResponse> {
  const { data } = await api.get<ProfileHistoryResponse>("/profile/history");
  return {
    history: data.history ?? [],
  };
}

export async function calibrateProfileDimension(
  dimension: string,
  comment?: string
): Promise<unknown> {
  const { data } = await api.post(`/profile/calibrate/${dimension}`, {
    comment: comment ?? "",
  });
  return data;
}

export async function fetchProfileWithTimeline(): Promise<{
  profile: ProfileResponse;
  timeline: ProfileTimelineItem[];
}> {
  const profile = await fetchProfile();
  try {
    const history = await fetchProfileHistory();
    return {
      profile,
      timeline: toTimelineItems(history.history, profile.updated_at),
    };
  } catch {
    return {
      profile,
      timeline: toTimelineItems([], profile.updated_at),
    };
  }
}
