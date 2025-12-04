"use client";

import { create } from "zustand";
import { User } from "@/types/auth";
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
    language?: "en" | "zh"
  ) => Promise<void>;
  loadProfile: () => Promise<void>;
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
      saveToken(data.access_token);
      applyLocalePreference(data.user);
      set({ token: data.access_token, user: data.user, loading: false });
    } catch (error: unknown) {
      const message = extractErrorMessage(error, "登录失败");
      set({
        error: message,
        loading: false,
      });
      throw error;
    }
  },

  async register(email, username, password, language = "en") {
    set({ loading: true, error: null });
    try {
      const data = await AuthService.register({
        email,
        username,
        password,
        languagePreference: language,
      });
      saveToken(data.access_token);
      applyLocalePreference(data.user);
      set({ token: data.access_token, user: data.user, loading: false });
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
  if (!user?.profile?.language_preference) {
    return;
  }
  const pref = user.profile.language_preference.toLowerCase();
  if (pref.includes("zh")) {
    persistLocale("zh");
  } else if (pref.includes("en")) {
    persistLocale("en");
  }
}

