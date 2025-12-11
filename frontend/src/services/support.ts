import { api } from "@/lib/http";

export type SuggestionPayload = {
  title: string;
  content: string;
  contact?: string;
};

export async function submitSuggestion(payload: SuggestionPayload) {
  await api.post("/api/support/suggestions", payload);
}

