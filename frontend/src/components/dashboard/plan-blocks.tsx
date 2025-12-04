import { PlanBlock } from "@/types/learning";
import { useI18n } from "@/hooks/use-i18n";

type PlanBlocksProps = {
  blocks: PlanBlock[];
};

export function PlanBlocks({ blocks }: PlanBlocksProps) {
  const { t } = useI18n();
  if (!blocks.length) {
    return <p className="text-sm text-white/40">{t("plan.empty")}</p>;
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {blocks.map((block) => (
        <div
          key={`${block.focus_skill}-${block.minutes}-${block.questions}`}
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
          <p className="mt-1 text-xs text-white/60 whitespace-pre-line leading-snug">
            {t("plan.blockMeta", {
              minutes: block.minutes,
              questions: block.questions,
              section: block.section,
            })}
          </p>
        </div>
      ))}
    </div>
  );
}

