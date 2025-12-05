import { PlanTaskPractice } from "@/components/practice/plan-task-practice";

export const metadata = {
  title: "Plan Task - SAT AI Tutor",
};

type PlanTaskPageProps = {
  params: Promise<{
    blockId: string;
  }> | {
    blockId: string;
  };
};

export default async function PlanTaskPage({ params }: PlanTaskPageProps) {
  const resolved = await params;
  const blockId = decodeURIComponent(resolved.blockId);
  return <PlanTaskPractice blockId={blockId} />;
}

