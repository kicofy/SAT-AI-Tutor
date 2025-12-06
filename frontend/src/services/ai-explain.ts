import { api } from "@/lib/http";
import type {
  ExplainDetailResponse,
  ExplainHistoryItem,
  ExplainHistoryResponse,
} from "@/types/explain";

export type ExplainHistoryFilters = {
  status?: "all" | "correct" | "incorrect";
  section?: string;
  difficulty?: string;
  search?: string;
  page?: number;
  perPage?: number;
};

export async function getExplainHistory(
  filters: ExplainHistoryFilters = {}
): Promise<ExplainHistoryResponse> {
  const params: Record<string, string | number> = {};
  if (filters.status && filters.status !== "all") {
    params.status = filters.status;
  }
  if (filters.section && filters.section !== "all") {
    params.section = filters.section;
  }
  if (filters.difficulty && filters.difficulty !== "all") {
    params.difficulty = filters.difficulty;
  }
  if (filters.search) {
    params.search = filters.search;
  }
  if (filters.page) {
    params.page = filters.page;
  }
  if (filters.perPage) {
    params.per_page = filters.perPage;
  }
  const { data } = await api.get<ExplainHistoryResponse>("/api/ai/explain/history", {
    params,
  });
  return data;
}

export async function getExplainDetail(payload: {
  questionId: number;
  logId?: number | null;
}): Promise<ExplainDetailResponse> {
  const body = {
    question_id: payload.questionId,
    log_id: payload.logId,
  };
  const { data } = await api.post<ExplainDetailResponse>("/api/ai/explain/detail", body);
  return data;
}

export async function generateExplain(payload: {
  questionId: number;
  logId?: number | null;
}) {
  const body = {
    question_id: payload.questionId,
    log_id: payload.logId,
  };
  const { data } = await api.post<{ explanation: unknown }>("/api/ai/explain/generate", body);
  return data.explanation;
}

