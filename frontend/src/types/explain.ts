import type { SessionQuestion, QuestionAnswer } from "@/types/session";
import type { AiExplainQuota } from "@/types/auth";
import type { AnimExplanation } from "@/components/practice/explanation-viewer";

export type ExplainHistoryItem = {
  log_id: number;
  question_id: number;
  question_uid?: string;
  section: string;
  sub_section?: string | null;
  skill_tags: string[];
  difficulty?: number | null;
  is_correct: boolean;
  answered_at: string;
  time_spent_sec?: number | null;
  session_type?: string | null;
  plan_block_id?: string | null;
  attempt_count: number;
  has_ai_explanation?: boolean;
};

export type ExplainHistoryResponse = {
  items: ExplainHistoryItem[];
  pagination: {
    page: number;
    pages: number;
    total: number;
    per_page: number;
    has_next: boolean;
    has_prev: boolean;
  };
};

export type ExplainDetailResponse = {
  question: SessionQuestion;
  meta: {
    question_id: number;
    question_uid?: string;
    log_id?: number | null;
    is_correct?: boolean | null;
    answered_at?: string | null;
    time_spent_sec?: number | null;
    user_answer?: QuestionAnswer | null;
    correct_answer?: QuestionAnswer | null;
    difficulty?: number | null;
    difficulty_label?: string | null;
    section: string;
    sub_section?: string | null;
    skill_tags: string[];
    session_type?: string | null;
    plan_block_id?: string | null;
    source_label?: string | null;
    attempt_count?: number;
    has_ai_explanation?: boolean;
    explanation_language?: string;
  };
  text_explanation?: string | null;
  ai_explanation?: AnimExplanation | null;
  quota?: AiExplainQuota;
};

