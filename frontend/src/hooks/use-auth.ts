"use client";

import { useEffect } from "react";
import { useAuthStore } from "@/stores/auth-store";
import { getClientToken } from "@/lib/auth-storage";

export function useAuth() {
  const store = useAuthStore();

  useEffect(() => {
    const token = getClientToken();
    if (token && !store.user && !store.loading) {
      store.loadProfile().catch(() => undefined);
    }
  }, [store]);

  return store;
}

