export type PlanBlock = {
  block_id?: string;
  focus_skill: string;
  focus_skill_label?: string;
  section: string;
  domain?: string;
  minutes: number;
  questions: number;
  notes?: string;
  priority_score?: number;
  strategy_tips?: string[];
  reasons?: string[];
  mastery_score?: number;
  recency_days?: number | null;
  recent_accuracy?: number | null;
};

export type StudyPlanDetail = {
  plan_date: string;
  target_minutes: number;
  target_questions: number;
  section_split?: Record<string, number>;
  allocation?: {
    section_minutes_target?: Record<string, number>;
    section_minutes_assigned?: Record<string, number>;
  };
  insights?: string[];
  blocks: PlanBlock[];
  tasks?: PlanTask[];
};

export type MasteryEntry = {
  skill_tag: string;
  label?: string;
  domain?: string;
  description?: string;
  mastery_score: number;
  success_streak?: number;
  last_practiced_at?: string | null;
};

export type ProgressEntry = {
  day: string;
  questions_answered: number;
  accuracy: number | null;
  sessions_completed: number;
  avg_difficulty?: number | null;
  predicted_score_rw?: number | null;
  predicted_score_math?: number | null;
};

export type PlanTask = {
  block_id: string;
  status: "pending" | "active" | "completed" | "expired";
  questions_target: number;
  questions_completed: number;
  session_id?: number | null;
  plan_date: string;
  started_at?: string | null;
  completed_at?: string | null;
};

export type TutorNote = {
  title: string;
  body: string;
  priority?: "info" | "warning" | "success";
};

export type TutorNotesResponse = {
  notes: TutorNote[];
};

