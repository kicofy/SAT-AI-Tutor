import { UserProfile, MembershipStatus, AiExplainQuota } from "@/types/auth";
import { QuestionFigureRef } from "@/types/session";

export type Pagination = {
  page: number;
  per_page: number;
  pages: number;
  total: number;
  has_next: boolean;
  has_prev: boolean;
};

export type PaginatedResponse<T> = {
  items: T[];
  pagination: Pagination;
};

export type AdminUser = {
  id: number;
  email: string;
  username: string;
  role: "student" | "admin";
  is_email_verified: boolean;
  is_active?: boolean;
  locked_reason?: string | null;
  locked_at?: string | null;
  created_at?: string | null;
  profile?: UserProfile | null;
  membership?: MembershipStatus;
  ai_explain_quota?: AiExplainQuota;
};

export type UserLearningSnapshot = {
  last_active_at: string | null;
  total_questions: number;
  accuracy_percent: number | null;
  avg_time_sec: number | null;
  plan_tasks_completed: number;
  plan_tasks_total: number;
  active_plan?: {
    block_id?: string | null;
    status?: string | null;
    section?: string | null;
    focus_skill?: string | null;
    questions_target?: number | null;
    plan_date?: string | null;
    updated_at?: string | null;
  } | null;
  predicted_score_rw?: number | null;
  predicted_score_math?: number | null;
  avg_difficulty?: number | null;
};

export type AdminUserDetail = {
  user: AdminUser;
  snapshot: UserLearningSnapshot | null;
};

export type QuestionPassage = {
  id?: number;
  content_text: string;
  metadata?: Record<string, unknown> | null;
};

export type AdminQuestion = {
  id: number;
  question_uid?: string | null;
  section: string;
  sub_section?: string | null;
  question_type?: string | null;
  passage?: QuestionPassage | null;
  difficulty_level?: number | null;
  stem_text?: string | null;
  skill_tags?: string[];
  choices?: Record<string, string>;
  correct_answer?: { value?: string | null } | null;
  answer_schema?: Record<string, unknown> | null;
  estimated_time_sec?: number | null;
  irt_a?: number | null;
  irt_b?: number | null;
  source_page?: number | null;
  page?: string | null;
  index_in_set?: number | null;
  metadata?: Record<string, unknown> | null;
  has_figure?: boolean;
  figures?: QuestionFigureRef[];
  source?: {
    id: number;
    filename?: string | null;
    original_name?: string | null;
  } | null;
};

export type AdminSource = {
  id: number;
  filename: string;
  original_name?: string | null;
  total_pages?: number | null;
  created_at?: string | null;
  question_count?: number;
};

export type AdminSourceDetail = {
  source: AdminSource;
  questions: AdminQuestion[];
  pagination: Pagination;
};

export type GeneralSettings = {
  suggestion_email?: string | null;
};

export type QuestionCategory = {
  key: string;
  label: string;
  domain: string;
  question_count: number;
  section_counts?: Record<string, number>;
};

export type AIPaperJob = {
  id: number;
  name: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled" | "cancelling";
  stage?: string | null;
  stage_index?: number | null;
  progress: number;
  total_tasks: number;
  completed_tasks: number;
  config: Record<string, unknown>;
  status_message?: string | null;
  error?: string | null;
  source_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type OpenAILogEntry = {
  timestamp: string;
  kind: string;
  job_id?: number | null;
  stage?: string | null;
  purpose?: string | null;
  page?: number | null;
  total_pages?: number | null;
  attempt?: number | null;
  max_attempts?: number | null;
  wait_seconds?: number | null;
  normalized_count?: number | null;
  status_code?: number | null;
  duration_ms?: number | null;
  model?: string | null;
  error?: string | null;
  message?: string | null;
  state?: string | null;
};

