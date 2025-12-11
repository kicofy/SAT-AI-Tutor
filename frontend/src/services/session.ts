import { api } from "@/lib/http";
import {
  AnswerPayload,
  AnswerResponse,
  ExplanationResponse,
  Session,
  StartSessionPayload,
} from "@/types/session";

export async function startSession(
  payload: StartSessionPayload
): Promise<Session> {
  const { data } = await api.post<{ session: Session }>(
    "/api/learning/session/start",
    payload
  );
  return data.session;
}

export async function submitAnswer(
  payload: AnswerPayload
): Promise<AnswerResponse> {
  const { data } = await api.post<AnswerResponse>(
    "/api/learning/session/answer",
    payload
  );
  return data;
}

export async function endSession(sessionId: number): Promise<void> {
  await api.post("/api/learning/session/end", { session_id: sessionId });
}

export async function abortSession(sessionId: number | undefined): Promise<void> {
  await api.post("/api/learning/session/abort", { session_id: sessionId });
}

export async function fetchExplanation(params: {
  session_id: number;
  question_id: number;
}): Promise<ExplanationResponse> {
  const { data } = await api.post<ExplanationResponse>(
    "/api/learning/session/explanation",
    params,
    { timeout: 60_000 }
  );
  return data;
}

export async function getActiveSession(): Promise<Session | null> {
  const { data } = await api.get<{ session: Session | null }>(
    "/api/learning/session/active"
  );
  return data.session;
}

