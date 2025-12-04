export type PlanBlock = {
  focus_skill: string;
  focus_skill_label?: string;
  section: string;
  domain?: string;
  minutes: number;
  questions: number;
  notes?: string;
};

export type StudyPlanDetail = {
  plan_date: string;
  target_minutes: number;
  target_questions: number;
  section_split?: Record<string, number>;
  blocks: PlanBlock[];
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
  accuracy: number;
  sessions_completed: number;
};

