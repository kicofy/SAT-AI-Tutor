import { api } from "@/lib/http";
import { ProgressEntry } from "@/types/learning";

export async function getProgressHistory(): Promise<ProgressEntry[]> {
  const { data } = await api.get<{ progress: ProgressEntry[] }>("/api/analytics/progress");
  return data.progress || [];
}

