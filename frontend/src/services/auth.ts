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
  email?: string;
  languagePreference?: "en" | "zh" | "bilingual";
};

export async function updateProfileSettings(payload: UpdateProfilePayload): Promise<User> {
  const body: Record<string, string> = {};
  if (payload.email) {
    body.email = payload.email;
  }
  if (payload.languagePreference) {
    body.language_preference = payload.languagePreference;
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

