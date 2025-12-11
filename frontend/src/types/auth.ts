export type UserProfile = {
  daily_available_minutes: number;
  daily_plan_questions?: number | null;
  language_preference: string;
  target_score_rw: number | null;
  target_score_math: number | null;
};

export type MembershipStatus = {
  is_member: boolean;
  expires_at?: string | null;
  trial_days_total?: number;
  trial_days_used?: number;
  trial_days_remaining?: number;
  trial_active?: boolean;
  trial_expires_at?: string | null;
};

export type AiExplainQuota = {
  limit: number | null;
  used: number;
  resets_at?: string | null;
};

export type User = {
  id: number;
  email: string;
  username: string;
  role: "student" | "admin";
  is_email_verified?: boolean;
  is_active?: boolean;
  locked_reason?: string | null;
  locked_at?: string | null;
  profile?: UserProfile | null;
  membership?: MembershipStatus;
  ai_explain_quota?: AiExplainQuota;
};

export type AuthResponse = {
  access_token: string;
  user: User;
};

