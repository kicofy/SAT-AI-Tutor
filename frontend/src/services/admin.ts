import { api } from "@/lib/http";
import {
  AdminSource,
  AdminSourceDetail,
  AdminUser,
  AdminUserDetail,
  PaginatedResponse,
  AdminQuestion,
  GeneralSettings,
  AIPaperJob,
  OpenAILogEntry,
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

import { QuestionCategory } from "@/types/admin";

export async function deleteQuestion(questionId: number) {
  await api.delete(`/api/admin/questions/${questionId}`);
}

export async function deleteQuestionsBulk(questionIds: number[]) {
  await api.post("/api/admin/questions/bulk-delete", { ids: questionIds });
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
  return data as { logs: OpenAILogEntry[] };
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

export async function updateUserMembership(
  userId: number,
  payload: { action: "extend" | "set" | "revoke"; days?: number; note?: string }
): Promise<{ membership: unknown; user: AdminUser }> {
  const { data } = await api.post(`/api/admin/users/${userId}/membership`, payload);
  return data;
}

export async function getAdminQuestions(params: {
  page?: number;
  per_page?: number;
  section?: string;
  question_uid?: string;
  question_id?: number;
  source_id?: number;
  skill_tag?: string;
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

export async function getGeneralSettings(): Promise<GeneralSettings> {
  const { data } = await api.get("/api/admin/settings/general");
  return data.settings as GeneralSettings;
}

export async function updateGeneralSettings(payload: GeneralSettings): Promise<GeneralSettings> {
  const { data } = await api.put("/api/admin/settings/general", payload);
  return data.settings as GeneralSettings;
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

export async function deleteSource(sourceId: number) {
  await api.delete(`/api/admin/sources/${sourceId}`);
}

export async function deleteSourceForce(sourceId: number) {
  await api.delete(`/api/admin/sources/${sourceId}/force`);
}

export async function resumeImportJob(jobId: number) {
  const { data } = await api.post(`/api/admin/questions/imports/${jobId}/resume`);
  return data;
}

export async function getQuestionCategories(): Promise<QuestionCategory[]> {
  const { data } = await api.get("/api/admin/questions/categories");
  return Array.isArray(data?.categories) ? data.categories : [];
}

export async function listAIPaperJobs(params?: {
  page?: number;
  per_page?: number;
}): Promise<PaginatedResponse<AIPaperJob>> {
  const { data } = await api.get("/api/admin/ai/papers", { params });
  return data;
}

export async function createAIPaperJob(payload: { name?: string; config?: Record<string, unknown> }) {
  const { data } = await api.post("/api/admin/ai/papers", payload);
  return data as AIPaperJob;
}

export async function getAIPaperJob(jobId: number): Promise<AIPaperJob> {
  const { data } = await api.get(`/api/admin/ai/papers/${jobId}`);
  return data as AIPaperJob;
}

export async function resumeAIPaperJob(jobId: number): Promise<AIPaperJob> {
  const { data } = await api.post(`/api/admin/ai/papers/${jobId}/resume`);
  return data as AIPaperJob;
}

export async function deleteAIPaperJob(jobId: number): Promise<void> {
  await api.delete(`/api/admin/ai/papers/${jobId}`);
}

