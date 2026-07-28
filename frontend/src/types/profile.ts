export interface ProfileMetric {
  label: string;
  confidence: number;
}

export interface ProfileData {
  learning_style: ProfileMetric;
  best_time: ProfileMetric;
  learning_rhythm: ProfileMetric;
  feedback_baseline: ProfileMetric;
  persistence: ProfileMetric;
  knowledge_retention: ProfileMetric;
}

export interface BackendProfileRaw extends Partial<Record<keyof ProfileData, ProfileMetric>> {
  total_feedback_count?: number;
  last_calibrated_at?: string | null;
  needs_initial_survey?: boolean;
  initial_survey_question?: string | null;
  updated_at?: string | null;
}

export interface ProfileResponse {
  profile: ProfileData;
  total_feedback_count: number;
  last_calibrated_at: string | null;
  needs_initial_survey: boolean;
  initial_survey_question: string | null;
  updated_at?: string | null;
}

export interface ProfileHistoryChange {
  dimension?: string;
  title?: string;
  reason?: string;
  from?: string;
  to?: string;
}

export interface ProfileHistoryItem {
  timestamp: string;
  source: string;
  changes: ProfileHistoryChange[];
}

export interface ProfileHistoryResponse {
  history: ProfileHistoryItem[];
}

export interface ProfileTimelineItem {
  timestamp: string;
  title: string;
  reason: string;
  changes: ProfileHistoryChange[];
}
