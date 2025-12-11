import { api } from "@/lib/http";
import { AuthResponse, User } from "@/types/auth";

type LoginPayload = {
  identifier: string;
  password: string;
};

type RegisterPayload = {
  email: string;
  password: string;
  username: string;
  languagePreference?: "en" | "zh";
  dailyPlanQuestions?: number;
};

export async function login(payload: LoginPayload): Promise<AuthResponse> {
  const { data } = await api.post<AuthResponse>("/api/auth/login", payload);
  return data;
}

export async function register(payload: RegisterPayload & { code: string }): Promise<AuthResponse> {
  const body = {
    email: payload.email,
    password: payload.password,
    username: payload.username,
    code: payload.code,
    profile: {
      daily_available_minutes: 60,
      daily_plan_questions: payload.dailyPlanQuestions ?? 12,
      language_preference: payload.languagePreference === "zh" ? "zh" : "en",
    },
  };
  const { data } = await api.post<AuthResponse>("/api/auth/register", body);
  return data;
}

export async function fetchProfile(): Promise<User> {
  const { data } = await api.get<{ user: User }>("/api/auth/me");
  return data.user;
}

type UpdateProfilePayload = {
  languagePreference?: "en" | "zh" | "bilingual";
  dailyPlanQuestions?: number;
};

export async function updateProfileSettings(payload: UpdateProfilePayload): Promise<User> {
  const body: Record<string, string | number> = {};
  if (payload.languagePreference) {
    body.language_preference = payload.languagePreference;
  }
  if (typeof payload.dailyPlanQuestions === "number") {
    body.daily_plan_questions = payload.dailyPlanQuestions;
  }
  const { data } = await api.patch<{ user: User }>("/api/auth/profile", body);
  return data.user;
}

type ChangePasswordPayload = {
  currentPassword: string;
  newPassword: string;
};

export async function changePassword(payload: ChangePasswordPayload): Promise<void> {
  await api.post("/api/auth/password", {
    current_password: payload.currentPassword,
    new_password: payload.newPassword,
  });
}

export async function requestRegistrationCode(payload: {
  email: string;
  languagePreference?: "en" | "zh";
}): Promise<void> {
  await api.post("/api/auth/register/request-code", {
    email: payload.email,
    language_preference: payload.languagePreference ?? "en",
  });
}

export async function requestEmailChangeCode(newEmail: string): Promise<void> {
  await api.post("/api/auth/email/change/request", { new_email: newEmail });
}

export async function confirmEmailChange(payload: { newEmail: string; code: string }): Promise<User> {
  const { data } = await api.post<{ user: User }>("/api/auth/email/change/confirm", {
    new_email: payload.newEmail,
    code: payload.code,
  });
  return data.user;
}

export async function requestPasswordReset(identifier: string): Promise<void> {
  await api.post("/api/auth/password/reset/request", { identifier });
}

export async function confirmPasswordReset(payload: { token: string; newPassword: string }): Promise<User> {
  const { data } = await api.post<{ user: User }>("/api/auth/password/reset/confirm", {
    token: payload.token,
    new_password: payload.newPassword,
  });
  return data.user;
}

