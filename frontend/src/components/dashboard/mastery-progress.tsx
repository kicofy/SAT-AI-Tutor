import { MasteryEntry } from "@/types/learning";
import { useI18n } from "@/hooks/use-i18n";

type MasteryProps = { mastery: MasteryEntry[] };

export function MasteryProgress({ mastery }: MasteryProps) {
  const { t } = useI18n();

  if (!mastery.length) {
    return <p className="text-sm text-white/40">{t("mastery.empty")}</p>;
  }
  return (
    <div className="space-y-3">
      {mastery.map((skill) => (
        <div key={skill.skill_tag}>
          {(() => {
            const hasProgress = Boolean(skill.last_practiced_at);
            const percentage = hasProgress ? Math.round(skill.mastery_score * 100) : 0;
            const labelValue = hasProgress ? `${percentage}%` : t("mastery.noDataLabel");
            return (
              <>
                <div className="flex items-center justify-between text-sm text-white/70">
                  <span className="font-medium text-white">
                    {skill.label ?? skill.skill_tag}
                    {skill.domain ? (
                      <span className="ml-2 text-xs font-normal uppercase tracking-wide text-white/50">
                        {skill.domain}
                      </span>
                    ) : null}
                  </span>
                  <span className={hasProgress ? "" : "text-white/40"}>{labelValue}</span>
                </div>
                <div className="mt-1 h-2 w-full rounded-full bg-white/10">
                  <div
                    className="h-2 rounded-full bg-white/60"
                    style={{ width: `${Math.min(percentage, 100)}%` }}
                  />
                </div>
                {skill.description ? (
                  <p className="mt-1 text-xs text-white/50">{skill.description}</p>
                ) : null}
                {!hasProgress && (
                  <p className="text-xs text-white/30">{t("mastery.noDataDescription")}</p>
                )}
              </>
            );
          })()}
        </div>
      ))}
    </div>
  );
}

