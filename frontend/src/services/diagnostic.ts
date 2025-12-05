import { api } from "@/lib/http";
import { DiagnosticStatus } from "@/types/diagnostic";

type DiagnosticResponse = DiagnosticStatus;

export async function getDiagnosticStatus(): Promise<DiagnosticStatus> {
  const { data } = await api.get<DiagnosticResponse>("/api/diagnostic/status");
  return data;
}

export async function startDiagnosticAttempt(): Promise<DiagnosticStatus> {
  const { data } = await api.post<DiagnosticResponse>("/api/diagnostic/start");
  return data;
}

export async function skipDiagnosticAttempt(): Promise<DiagnosticStatus> {
  const { data } = await api.post<DiagnosticResponse>("/api/diagnostic/skip");
  return data;
}

