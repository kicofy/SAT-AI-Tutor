import { api } from "@/lib/http";
import { ProgressEntry } from "@/types/learning";

export type EfficiencySection = {
  section: string;
  avg_time_sec: number;
  recommended_time_sec: number;
  question_count: number;
};

export type SlowSkillInsight = {
  skill_tag: string;
  label: string;
  avg_time_sec: number;
  question_count: number;
  section?: string;
  recommended_time_sec?: number;
};

export type EfficiencySummary = {
  sample_size: number;
  sections: EfficiencySection[];
  slow_skills: SlowSkillInsight[];
  overall_avg_time_sec?: number | null;
  overall_recommended_time_sec?: number | null;
};

export type MistakeEntry = {
  log_id: number;
  question_id: number;
  question_uid?: string;
  section?: string;
  sub_section?: string | null;
  skill_tags: string[];
  answered_at?: string | null;
  time_spent_sec?: number | null;
  viewed_explanation?: boolean;
};

export type MistakeQueue = {
  items: MistakeEntry[];
  pending_explanations: number;
  total_mistakes: number;
};

export async function getProgressHistory(): Promise<ProgressEntry[]> {
  const { data } = await api.get<{ progress: ProgressEntry[] }>("/api/analytics/progress");
  return data.progress || [];
}

export async function getEfficiencySummary(): Promise<EfficiencySummary> {
  const { data } = await api.get<EfficiencySummary>("/api/analytics/efficiency");
  return data;
}

export async function getMistakeQueue(): Promise<MistakeQueue> {
  const { data } = await api.get<MistakeQueue>("/api/analytics/mistakes");
  return data;
}

