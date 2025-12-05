import { api } from "@/lib/http";

export async function ingestPdf(file: File) {
  const formData = new FormData();
  formData.append("file", file);
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

