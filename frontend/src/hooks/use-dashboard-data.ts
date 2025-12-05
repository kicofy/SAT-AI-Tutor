"use client";

import { useQuery } from "@tanstack/react-query";
import { getTutorNotes, getMasterySnapshot, getTodayPlan } from "@/services/learning";
import { getProgressHistory } from "@/services/analytics";
import { useAuthStore } from "@/stores/auth-store";
import { getDiagnosticStatus } from "@/services/diagnostic";

export function useDashboardData() {
  const userId = useAuthStore((state) => state.user?.id);
  const diagnosticQuery = useQuery({
    queryKey: ["diagnostic-status", userId],
    queryFn: getDiagnosticStatus,
    enabled: Boolean(userId),
  });
  const canLoadPlan = Boolean(userId) && diagnosticQuery.status === "success" && !diagnosticQuery.data?.requires_diagnostic;
  const planQuery = useQuery({
    queryKey: ["plan-today", userId],
    queryFn: getTodayPlan,
    enabled: canLoadPlan,
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
    enabled: canLoadPlan,
  });

  return {
    diagnosticQuery,
    planQuery,
    masteryQuery,
    progressQuery,
    tutorNotesQuery,
  };
}

