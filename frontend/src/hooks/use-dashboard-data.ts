"use client";

import { useQuery } from "@tanstack/react-query";
import { getTutorNotes, getMasterySnapshot, getTodayPlan } from "@/services/learning";
import { getProgressHistory } from "@/services/analytics";
import { useAuthStore } from "@/stores/auth-store";

export function useDashboardData() {
  const userId = useAuthStore((state) => state.user?.id);
  const planQuery = useQuery({
    queryKey: ["plan-today", userId],
    queryFn: getTodayPlan,
    enabled: Boolean(userId),
  });

  const masteryQuery = useQuery({
    queryKey: ["mastery", userId],
    queryFn: getMasterySnapshot,
    enabled: Boolean(userId),
  });

  const progressQuery = useQuery({
    queryKey: ["progress", userId],
    queryFn: getProgressHistory,
    enabled: Boolean(userId),
  });

  const tutorNotesQuery = useQuery({
    queryKey: ["tutor-notes", userId],
    queryFn: getTutorNotes,
    enabled: Boolean(userId),
  });

  return {
    planQuery,
    masteryQuery,
    progressQuery,
    tutorNotesQuery,
  };
}

