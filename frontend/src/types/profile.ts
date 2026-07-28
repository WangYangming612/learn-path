export interface ProfileMetric {
  label: string;
  confidence: number;
}

export interface ProfileData {
  learning_style: ProfileMetric;
  best_time_slots: ProfileMetric;
  learning_rhythm: ProfileMetric;
  feedback_baseline: ProfileMetric;
  persistence: ProfileMetric;
  knowledge_retention: ProfileMetric;
}

/** 后端返回的 profile 内部原始数据结构 */
export interface ProfileRaw {
  learning_style: ProfileMetric & { evidence?: string[] };
  best_time_slots: ProfileMetric & { evidence?: string[] };
  learning_rhythm: ProfileMetric & { evidence?: string[] };
  feedback_baseline: ProfileMetric & { evidence?: string[] };
  persistence: ProfileMetric & { evidence?: string[] };
  knowledge_retention: ProfileMetric & { evidence?: string[] };
}

export interface BackendProfileRaw {
  profile: ProfileRaw;
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
// ── 摸底选择题相关类型 ──────────────────────────────────────────────

export interface SurveyOption {
  option_id: string;
  text: string;
}

export interface SurveyQuestion {
  id: number;
  dimension: string;
  question: string;
  options: SurveyOption[];
}

export interface SurveyQuestionsResponse {
  questions: SurveyQuestion[];
  total: number;
}

export interface McAnswerItem {
  question_id: number;
  option_id: string;
}

export interface McSurveySubmitRequest {
  answers: McAnswerItem[];
}

export interface McSurveySubmitResponse {
  success: boolean;
  message: string;
  profile_complete: boolean;
  completeness: number;
}
