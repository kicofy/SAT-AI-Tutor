export type UserProfile = {
  daily_available_minutes: number;
  language_preference: string;
  target_score_rw: number | null;
  target_score_math: number | null;
};

export type User = {
  id: number;
  email: string;
  username: string;
  role: "student" | "admin";
  is_email_verified?: boolean;
  profile?: UserProfile | null;
};

export type AuthResponse = {
  access_token: string;
  user: User;
};

