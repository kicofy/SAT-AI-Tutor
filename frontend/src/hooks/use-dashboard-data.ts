"use client";

import { useQuery } from "@tanstack/react-query";
import { getTutorNotes, getMasterySnapshot, getTodayPlan } from "@/services/learning";
import { getProgressHistory } from "@/services/analytics";
import { useAuthStore } from "@/stores/auth-store";
import { getDiagnosticStatus } from "@/services/diagnostic";

export function useDashboardData() {
  const userId = useAuthStore((state) => state.user?.id);
  const membership = useAuthStore((state) => state.user?.membership);
  const diagnosticQuery = useQuery({
    queryKey: ["diagnostic-status", userId],
    queryFn: getDiagnosticStatus,
    enabled: Boolean(userId),
  });
  const planAllowed =
    membership === undefined || membership === null
      ? true
      : Boolean(membership.is_member || membership.trial_active);
  const canLoadPlan =
    Boolean(userId) &&
    planAllowed &&
    diagnosticQuery.status === "success" &&
    !diagnosticQuery.data?.requires_diagnostic;
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

  const languagePref = useAuthStore(
    (state) =>
      state.user?.profile?.language_preference?.toLowerCase().includes("zh") ? "zh" : "en"
  );
  const tutorNotesQuery = useQuery({
    queryKey: ["tutor-notes", userId, languagePref],
    queryFn: () => getTutorNotes({ lang: languagePref }),
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

