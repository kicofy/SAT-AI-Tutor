import { api } from "@/lib/http";
import { MasteryEntry, StudyPlanDetail } from "@/types/learning";

export async function getTodayPlan(): Promise<StudyPlanDetail> {
  const { data } = await api.get<{ plan: StudyPlanDetail }>("/api/learning/plan/today");
  return data.plan;
}

export async function getMasterySnapshot(): Promise<MasteryEntry[]> {
  const { data } = await api.get<{ mastery: MasteryEntry[] }>("/api/learning/mastery");
  return data.mastery;
}

