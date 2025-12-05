"use client";
import { PracticeView } from "@/components/practice/practice-view";

type PlanTaskPracticeProps = {
  blockId: string;
};

export function PlanTaskPractice({ blockId }: PlanTaskPracticeProps) {
  if (!blockId) {
    return null;
  }
  return <PracticeView planBlockId={blockId} />;
}

