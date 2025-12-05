import { api } from "@/lib/http";
import { TutorNotesResponse, MasteryEntry, PlanTask, StudyPlanDetail } from "@/types/learning";
import { Session } from "@/types/session";

export type PlanTodayResponse = {
  plan: StudyPlanDetail;
  tasks: PlanTask[];
};

function hasBlockIds(plan: StudyPlanDetail | undefined): boolean {
  if (!plan?.blocks?.length) return false;
  return plan.blocks.some((block) => Boolean(block.block_id));
}

export async function getTodayPlan(): Promise<PlanTodayResponse> {
  const { data } = await api.get<PlanTodayResponse>("/api/learning/plan/today");
  if (hasBlockIds(data.plan)) {
    return data;
  }
  const regen = await api.post<PlanTodayResponse>("/api/learning/plan/regenerate");
  return regen.data;
}

export async function getMasterySnapshot(): Promise<MasteryEntry[]> {
  const { data } = await api.get<{ mastery: MasteryEntry[] }>("/api/learning/mastery");
  return data.mastery;
}

export async function startPlanTask(blockId: string): Promise<{
  session: Session;
  task: PlanTask;
}> {
  const { data } = await api.post<{ session: Session; task: PlanTask }>(
    `/api/learning/plan/tasks/${encodeURIComponent(blockId)}/start`
  );
  return data;
}

export async function listPlanTasks(): Promise<PlanTask[]> {
  const { data } = await api.get<{ tasks: PlanTask[] }>("/api/learning/plan/tasks");
  return data.tasks;
}

export async function getTutorNotes(): Promise<TutorNotesResponse> {
  const { data } = await api.get<TutorNotesResponse>("/api/learning/tutor-notes/today");
  return data;
}

