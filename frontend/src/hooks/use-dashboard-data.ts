"use client";

import { useQuery } from "@tanstack/react-query";
import { getMasterySnapshot, getTodayPlan } from "@/services/learning";
import { getProgressHistory } from "@/services/analytics";

export function useDashboardData() {
  const planQuery = useQuery({
    queryKey: ["plan-today"],
    queryFn: getTodayPlan,
  });

  const masteryQuery = useQuery({
    queryKey: ["mastery"],
    queryFn: getMasterySnapshot,
  });

  const progressQuery = useQuery({
    queryKey: ["progress"],
    queryFn: getProgressHistory,
  });

  return {
    planQuery,
    masteryQuery,
    progressQuery,
  };
}

