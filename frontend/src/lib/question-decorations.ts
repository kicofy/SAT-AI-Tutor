import type { StepDirective } from "@/components/practice/explanation-viewer";
import type { SessionQuestion } from "@/types/session";

type DecorationRecord = {
  target?: string;
  action?: string;
  text?: string;
  choice_id?: string | number;
};

export function getQuestionDecorations(
  question?: Pick<SessionQuestion, "metadata"> | null
): StepDirective[] {
  if (!question?.metadata || typeof question.metadata !== "object") {
    return [];
  }
  const metadata = question.metadata as Record<string, unknown>;
  const decorations = metadata["decorations"];
  if (!Array.isArray(decorations)) {
    return [];
  }
  return decorations
    .map((entry) => normalizeDecoration(entry))
    .filter((entry): entry is StepDirective => Boolean(entry));
}

function normalizeDecoration(entry: unknown): StepDirective | null {
  if (!entry || typeof entry !== "object") {
    return null;
  }
  const record = entry as DecorationRecord;
  const text = typeof record.text === "string" ? record.text.trim() : "";
  if (!text) {
    return null;
  }
  const target =
    typeof record.target === "string" && record.target.length > 0 ? (record.target as StepDirective["target"]) : "passage";
  const action =
    typeof record.action === "string" && record.action.length > 0 ? (record.action as StepDirective["action"]) : "underline";
  return {
    target,
    text,
    action,
  };
}

