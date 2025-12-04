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

export async function register(payload: RegisterPayload): Promise<AuthResponse> {
  const body = {
    email: payload.email,
    password: payload.password,
    username: payload.username,
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

