import Link from "next/link";
import { PlanBlock, PlanTask } from "@/types/learning";
import { useI18n } from "@/hooks/use-i18n";

type PlanBlocksProps = {
  blocks: PlanBlock[];
  taskMap: Record<string, PlanTask | undefined>;
};

export function PlanBlocks({ blocks, taskMap }: PlanBlocksProps) {
  const { t } = useI18n();
  if (!blocks.length) {
    return <p className="text-sm text-white/40">{t("plan.empty")}</p>;
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {blocks.map((block) => (
        <div
          key={`${block.focus_skill}-${block.minutes}-${block.questions}-${block.block_id ?? "legacy"}`}
          className="card-ambient rounded-2xl border border-white/10 bg-white/5 px-4 py-4 text-sm text-white/80"
        >
          <div className="flex flex-col gap-1">
            <p className="font-medium text-white break-words leading-tight">
              {block.focus_skill_label ?? block.focus_skill}
            </p>
            {block.domain ? (
              <span className="text-xs uppercase tracking-wide text-white/50">{block.domain}</span>
            ) : null}
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-xs text-white/60">
            <span className="chip-soft">
              {t("plan.block.minutes", { minutes: block.minutes })}
            </span>
            <span className="chip-soft">
              {t("plan.block.questions", { count: block.questions })}
            </span>
          </div>
          {block.block_id ? (
            <PlanBlockAction blockId={block.block_id} task={taskMap[block.block_id]} />
          ) : null}
        </div>
      ))}
    </div>
  );
}

function PlanBlockAction({ blockId, task }: { blockId: string; task?: PlanTask }) {
  const { t } = useI18n();
  const isCompleted = task?.status === "completed";
  const inProgress = task?.status === "active";
  let label = t("plan.block.start");
  if (isCompleted) {
    label = t("plan.block.completed");
  } else if (inProgress) {
    label = t("plan.block.continue", {
      completed: task?.questions_completed ?? 0,
      total: task?.questions_target ?? 0,
    });
  }
  return (
    <Link
      href={`/plan/tasks/${encodeURIComponent(blockId)}`}
      className={`mt-3 text-xs font-semibold ${
        isCompleted ? "chip-soft chip-soft--success pointer-events-none" : "btn-ghost"
      }`}
      aria-disabled={isCompleted}
    >
      {label}
    </Link>
  );
}

