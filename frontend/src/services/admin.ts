import { api } from "@/lib/http";
import {
  AdminSource,
  AdminSourceDetail,
  AdminUser,
  AdminUserDetail,
  PaginatedResponse,
  AdminQuestion,
} from "@/types/admin";
import { FigureSource } from "@/types/figure";

export async function ingestPdf(file: File, options?: { force?: boolean }) {
  const formData = new FormData();
  formData.append("file", file);
  if (options?.force) {
    formData.append("force", "true");
  }
  const { data } = await api.post(
    "/api/admin/questions/ingest-pdf",
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
    }
  );
  return data;
}

export async function deleteQuestion(questionId: number) {
  await api.delete(`/api/admin/questions/${questionId}`);
}

export async function clearQuestionExplanation(questionId: number) {
  await api.post(`/api/admin/questions/${questionId}/explanations/clear`);
}

export async function fetchImportStatus() {
  const { data } = await api.get("/api/admin/questions/imports");
  return data;
}

export async function deleteDraft(draftId: number) {
  await api.delete(`/api/admin/questions/drafts/${draftId}`);
}

export async function publishDraft(draftId: number) {
  const { data } = await api.post(`/api/admin/questions/drafts/${draftId}/publish`);
  return data;
}

export async function updateDraft(
  draftId: number,
  payload: Partial<AdminQuestion>
): Promise<{ draft: unknown }> {
  const { data } = await api.patch(`/api/admin/questions/drafts/${draftId}`, payload);
  return data;
}

export async function fetchDraftFigureSource(draftId: number) {
  const { data } = await api.get(`/api/admin/questions/drafts/${draftId}/figure-source`);
  return data as { page: number; image: string; width: number; height: number };
}

export async function uploadDraftFigure(draftId: number, formData: FormData) {
  const { data } = await api.post(
    `/api/admin/questions/drafts/${draftId}/figure`,
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
    }
  );
  return data;
}

export async function fetchDraftFigures(draftId: number) {
  const { data } = await api.get(`/api/admin/questions/drafts/${draftId}/figures`);
  return data;
}

export async function deleteDraftFigure(draftId: number, figureId: number) {
  await api.delete(`/api/admin/questions/drafts/${draftId}/figures/${figureId}`);
}

export async function fetchQuestionFigureSource(questionId: number, page?: number) {
  const { data } = await api.get(`/api/admin/questions/${questionId}/figure-source`, {
    params: page ? { page } : undefined,
  });
  return data as FigureSource;
}

export async function uploadQuestionFigure(questionId: number, formData: FormData) {
  const { data } = await api.post(`/api/admin/questions/${questionId}/figure`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function deleteQuestionFigure(questionId: number, figureId: number) {
  await api.delete(`/api/admin/questions/${questionId}/figures/${figureId}`);
}

export async function fetchOpenaiLogs(limit = 100) {
  const { data } = await api.get("/api/admin/logs/openai", { params: { limit } });
  return data;
}

export async function cancelImport(jobId: number) {
  await api.delete(`/api/admin/questions/imports/${jobId}`);
}

type QuestionListParams = {
  page?: number;
  per_page?: number;
  section?: string;
  question_id?: number;
  question_uid?: string;
  source_id?: number;
};

export async function listQuestions(params?: QuestionListParams) {
  const { data } = await api.get("/api/admin/questions", { params });
  return data;
}

export async function getAdminUsers(params: {
  page?: number;
  per_page?: number;
  search?: string;
  role?: string;
  verified?: string;
}): Promise<PaginatedResponse<AdminUser>> {
  const { data } = await api.get("/api/admin/users", { params });
  return data;
}

export async function getAdminUser(userId: number): Promise<AdminUserDetail> {
  const { data } = await api.get(`/api/admin/users/${userId}`);
  return data;
}

export async function updateAdminUser(
  userId: number,
  payload: Partial<Pick<AdminUser, "email" | "username" | "role">> & {
    language_preference?: string;
    reset_password?: string;
    is_active?: boolean;
    locked_reason?: string | null;
  }
): Promise<{ user: AdminUser }> {
  const { data } = await api.patch(`/api/admin/users/${userId}`, payload);
  return data;
}

export async function getAdminQuestions(params: {
  page?: number;
  per_page?: number;
  section?: string;
  question_uid?: string;
  question_id?: number;
  source_id?: number;
}): Promise<{ items: AdminQuestion[]; page: number; per_page: number; total: number }> {
  const { data } = await api.get("/api/admin/questions", { params });
  return data;
}

export async function getAdminQuestion(questionId: number): Promise<{ question: AdminQuestion }> {
  const { data } = await api.get(`/api/admin/questions/${questionId}`);
  return data;
}

export async function updateAdminQuestion(
  questionId: number,
  payload: Partial<AdminQuestion>
): Promise<{ question: AdminQuestion }> {
  const { data } = await api.put(`/api/admin/questions/${questionId}`, payload);
  return data;
}

export async function getAdminSources(params: {
  page?: number;
  per_page?: number;
  search?: string;
}): Promise<PaginatedResponse<AdminSource>> {
  const { data } = await api.get("/api/admin/sources", { params });
  return data;
}

export async function getAdminSourceDetail(
  sourceId: number,
  params?: { page?: number; per_page?: number }
): Promise<AdminSourceDetail> {
  const { data } = await api.get(`/api/admin/sources/${sourceId}`, { params });
  return data;
}

