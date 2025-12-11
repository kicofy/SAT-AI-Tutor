"use client";

import { create } from "zustand";
import { AuthResponse, User } from "@/types/auth";
import { clearToken, saveToken } from "@/lib/auth-storage";
import * as AuthService from "@/services/auth";
import { extractErrorMessage } from "@/lib/errors";
import { persistLocale } from "@/i18n/locale-storage";

type AuthState = {
  user: User | null;
  token: string | null;
  loading: boolean;
  error: string | null;
  login: (identifier: string, password: string) => Promise<void>;
  register: (
    email: string,
    username: string,
    password: string,
    code: string,
    language?: "en" | "zh"
  ) => Promise<void>;
  loadProfile: () => Promise<void>;
  updateUser: (user: User) => void;
  completeLogin: (payload: AuthResponse) => void;
  logout: () => void;
};

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: null,
  loading: false,
  error: null,

  async login(identifier, password) {
    set({ loading: true, error: null });
    try {
      const data = await AuthService.login({ identifier, password });
      applyAuthResponse(data, set);
    } catch (error: unknown) {
      const message = extractErrorMessage(error, "登录失败");
      set({
        error: message,
        loading: false,
      });
      throw error;
    }
  },

  async register(email, username, password, code, language = "en") {
    set({ loading: true, error: null });
    try {
      const data = await AuthService.register({
        email,
        username,
        password,
        code,
        languagePreference: language,
      });
      applyAuthResponse(data, set);
      set({ loading: false });
    } catch (error: unknown) {
      const message = extractErrorMessage(error, "注册失败");
      set({
        error: message,
        loading: false,
      });
      throw error;
    }
  },

  async loadProfile() {
    set({ loading: true, error: null });
    try {
      const user = await AuthService.fetchProfile();
      applyLocalePreference(user);
      set({ user, loading: false });
    } catch {
      set({ user: null, token: null, loading: false });
    }
  },

  updateUser(user) {
    applyLocalePreference(user);
    set({ user });
  },

  completeLogin(payload) {
    applyAuthResponse(payload, set);
  },

  logout() {
    clearToken();
    set({ user: null, token: null, error: null });
  },
}));

if (typeof window !== "undefined") {
  window.addEventListener("sat:auth-expired", () => {
    const logout = useAuthStore.getState().logout;
    logout();
  });
}

function applyLocalePreference(user?: User | null) {
  const pref = user?.profile?.language_preference?.toLowerCase();
  if (pref && pref.includes("zh")) {
    persistLocale("zh");
  } else {
    persistLocale("en");
  }
}

function applyAuthResponse(response: AuthResponse, set: (partial: Partial<AuthState>) => void) {
  saveToken(response.access_token);
  applyLocalePreference(response.user);
  set({ token: response.access_token, user: response.user, loading: false, error: null });
}

