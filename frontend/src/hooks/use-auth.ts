"use client";

import { useEffect } from "react";
import { useAuthStore } from "@/stores/auth-store";
import { getClientToken } from "@/lib/auth-storage";

let profileLoadInFlight = false;

export function useAuth() {
  const store = useAuthStore();
  const { user, loading, loadProfile } = store;

  useEffect(() => {
    if (typeof window === "undefined") return;
    const token = getClientToken();
    if (!token || user || loading || profileLoadInFlight) {
      return;
    }
    profileLoadInFlight = true;
    loadProfile()
      .catch(() => undefined)
      .finally(() => {
        profileLoadInFlight = false;
      });
  }, [user, loading, loadProfile]);

  return store;
}

