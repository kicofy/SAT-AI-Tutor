import { Session } from "@/types/session";

export type DiagnosticSkillProgress = {
  tag: string;
  label: string;
  completed: number;
  total: number;
};

export type DiagnosticProgressSnapshot = {
  total_questions: number;
  completed_questions: number;
  skills: DiagnosticSkillProgress[];
};

export type DiagnosticAttemptSummary = {
  id: number;
  status: "pending" | "completed" | "skipped";
  total_questions: number;
  started_at?: string | null;
  completed_at?: string | null;
  result_summary?: Record<string, unknown> | null;
  progress_snapshot?: DiagnosticProgressSnapshot;
};

export type DiagnosticStatus = {
  requires_diagnostic: boolean;
  attempt: DiagnosticAttemptSummary | null;
  progress: DiagnosticProgressSnapshot | null;
  session: Session | null;
};

