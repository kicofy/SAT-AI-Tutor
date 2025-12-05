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
          className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/80 transition hover:border-white/30"
        >
          <p className="font-medium text-white break-words leading-tight">
            {block.focus_skill_label ?? block.focus_skill}
            {block.domain ? (
              <span className="ml-2 text-xs uppercase tracking-wide text-white/50">
                {block.domain}
              </span>
            ) : null}
          </p>
          <p className="mt-2 text-xs text-white/50">
            {t("plan.block.minutes", { minutes: block.minutes })} ·{" "}
            {t("plan.block.questions", { count: block.questions })}
          </p>
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
      className={`mt-3 inline-flex items-center justify-center rounded-xl border px-3 py-1 text-xs font-medium transition ${
        isCompleted
          ? "border-emerald-300/40 bg-emerald-500/20 text-emerald-100 pointer-events-none"
          : "border-white/20 text-white/90 hover:border-white/50"
      }`}
      aria-disabled={isCompleted}
    >
      {label}
    </Link>
  );
}

