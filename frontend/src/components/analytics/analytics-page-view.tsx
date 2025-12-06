 "use client";

import Link from "next/link";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/app-shell";
import { useI18n } from "@/hooks/use-i18n";
import { getDiagnosticStatus } from "@/services/diagnostic";
import { getMasterySnapshot, getTodayPlan } from "@/services/learning";
import {
  getProgressHistory,
  getEfficiencySummary,
  getMistakeQueue,
  type EfficiencySummary,
  type MistakeQueue,
} from "@/services/analytics";
import { useAuthStore } from "@/stores/auth-store";
import type { MasteryEntry, PlanBlock, PlanTask, ProgressEntry } from "@/types/learning";

export function AnalyticsPageView() {
  const { t } = useI18n();
  const userId = useAuthStore((state) => state.user?.id);

  const diagnosticQuery = useQuery({
    queryKey: ["diagnostic-status", userId],
    queryFn: getDiagnosticStatus,
    enabled: Boolean(userId),
  });

  const canLoadPlan =
    Boolean(userId) && diagnosticQuery.status === "success" && !diagnosticQuery.data?.requires_diagnostic;

  const progressQuery = useQuery({
    queryKey: ["analytics-progress", userId],
    queryFn: getProgressHistory,
    enabled: Boolean(userId),
  });

  const masteryQuery = useQuery({
    queryKey: ["analytics-mastery", userId],
    queryFn: getMasterySnapshot,
    enabled: Boolean(userId),
  });

  const planQuery = useQuery({
    queryKey: ["analytics-plan", userId],
    queryFn: getTodayPlan,
    enabled: canLoadPlan,
  });

  const efficiencyQuery = useQuery({
    queryKey: ["analytics-efficiency", userId],
    queryFn: getEfficiencySummary,
    enabled: Boolean(userId),
  });

  const mistakesQuery = useQuery({
    queryKey: ["analytics-mistakes", userId],
    queryFn: getMistakeQueue,
    enabled: Boolean(userId),
  });

  if (!userId) {
    return (
      <AppShell>
        <div className="col-span-full mx-auto flex w-full max-w-4xl flex-col gap-4 px-4 py-10 text-white/70">
          <p>{t("auth.login.error")}</p>
        </div>
      </AppShell>
    );
  }

  if (diagnosticQuery.isLoading) {
    return (
      <AppShell>
        <div className="col-span-full mx-auto flex w-full max-w-5xl flex-col gap-4 px-4 py-10 text-white/60">
          <p>{t("diagnostic.card.loading")}</p>
        </div>
      </AppShell>
    );
  }

  if (diagnosticQuery.error) {
    return (
      <AppShell>
        <div className="col-span-full mx-auto flex w-full max-w-5xl flex-col gap-4 px-4 py-10 text-white/70">
          <p>{t("diagnostic.card.error")}</p>
        </div>
      </AppShell>
    );
  }

  if (diagnosticQuery.data?.requires_diagnostic) {
    return (
      <AppShell>
        <div className="col-span-full mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-10">
          <section className="card-ambient rounded-3xl border border-white/10 bg-[#0b1424] p-6 text-white space-y-4">
            <p className="text-xs uppercase tracking-[0.3em] text-white/50">{t("analytics.page.title")}</p>
            <h1 className="text-2xl font-semibold">{t("analytics.readiness.locked")}</h1>
            <p className="text-sm text-white/70">{t("diagnostic.card.subtitle")}</p>
            <div className="flex flex-wrap gap-3">
              <Link href="/diagnostic" className="btn-cta">{t("analytics.readiness.cta")}</Link>
              <Link href="/" className="btn-ghost">{t("analytics.action.back")}</Link>
            </div>
          </section>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <StudentAnalyticsContent
        progress={progressQuery.data ?? []}
        progressLoading={progressQuery.isLoading}
        mastery={masteryQuery.data ?? []}
        masteryLoading={masteryQuery.isLoading}
        planData={planQuery.data}
        planLoading={planQuery.isLoading}
        efficiencyData={efficiencyQuery.data}
        efficiencyLoading={efficiencyQuery.isLoading}
        mistakeData={mistakesQuery.data}
        mistakesLoading={mistakesQuery.isLoading}
      />
    </AppShell>
  );
}

type StudentAnalyticsContentProps = {
  progress: ProgressEntry[];
  progressLoading: boolean;
  mastery: MasteryEntry[];
  masteryLoading: boolean;
  planData?: { plan: { blocks: PlanBlock[]; target_minutes: number; target_questions: number }; tasks: PlanTask[] };
  planLoading: boolean;
  efficiencyData?: EfficiencySummary;
  efficiencyLoading: boolean;
  mistakeData?: MistakeQueue;
  mistakesLoading: boolean;
};

function StudentAnalyticsContent({
  progress,
  progressLoading,
  mastery,
  masteryLoading,
  planData,
  planLoading,
  efficiencyData,
  efficiencyLoading,
  mistakeData,
  mistakesLoading,
}: StudentAnalyticsContentProps) {
  const { t } = useI18n();

  const summary = useMemo(() => summarizeProgress(progress), [progress]);
  const streak = summary.dayStreak;
  const weeklySlice = useMemo(() => progress.slice(Math.max(progress.length - 7, 0)), [progress]);

  const [strengths, focusAreas] = useMemo(() => deriveSkillInsights(mastery), [mastery]);

  const planTasks = planData?.tasks ?? [];
  const completedBlocks = planTasks.filter((task) => task.status === "completed").length;
  const totalBlocks =
    planTasks.length || planData?.plan?.blocks?.length || (planData ? planData.plan.blocks.length : 0);
  const activeBlocks = planTasks.filter((task) => task.status === "active");

  const recommendations = buildRecommendations({
    focusAreas,
    activeBlocks,
    streak,
    hasPlan: Boolean(planData?.plan),
    t,
  });

  return (
    <div className="col-span-full mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-8 text-white">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-white/40">{t("analytics.page.title")}</p>
          <h1 className="mt-1 text-3xl font-semibold text-white">{t("analytics.page.subtitle")}</h1>
        </div>
        <Link href="/" className="btn-ghost px-4 py-2 text-sm">
          {t("analytics.action.back")}
        </Link>
      </header>

      <section className="card-ambient rounded-3xl border border-white/10 bg-[#0b1424] p-6">
        <h2 className="text-sm uppercase tracking-wide text-white/50">{t("analytics.section.activity")}</h2>
        {progressLoading ? (
          <p className="mt-4 text-sm text-white/60">{t("ai.loading")}</p>
        ) : progress.length === 0 ? (
          <p className="mt-4 text-sm text-white/60">{t("analytics.empty.progress")}</p>
        ) : (
          <div className="mt-5 grid gap-3 md:grid-cols-4">
            <StatCard label={t("analytics.stat.questions")} value={summary.totalQuestions.toString()} />
            <StatCard label={t("analytics.stat.sessions")} value={summary.totalSessions.toString()} />
            <StatCard label={t("analytics.stat.accuracy")} value={formatPercent(summary.avgAccuracy)} />
            <StatCard label={t("analytics.stat.streak")} value={`${summary.dayStreak}d`} />
          </div>
        )}
        {weeklySlice.length > 0 && (
          <div className="mt-6">
            <p className="text-xs uppercase tracking-wide text-white/50">{t("analytics.section.trend")}</p>
            <ActivityTrend data={weeklySlice} />
          </div>
        )}
      </section>

      <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="card-ambient rounded-3xl border border-white/10 bg-[#0b1424] p-6">
          <h2 className="text-sm uppercase tracking-wide text-white/50">{t("analytics.section.skills")}</h2>
          {masteryLoading ? (
            <p className="mt-4 text-sm text-white/60">{t("ai.loading")}</p>
          ) : mastery.length === 0 ? (
            <p className="mt-4 text-sm text-white/60">{t("analytics.empty.mastery")}</p>
          ) : (
            <SkillInsight strengths={strengths} focusAreas={focusAreas} />
          )}
        </div>

        <div className="space-y-6">
          <div className="card-ambient rounded-3xl border border-white/10 bg-[#0b1424] p-6">
            <h2 className="text-sm uppercase tracking-wide text-white/50">{t("analytics.section.plan")}</h2>
            {planLoading ? (
              <p className="mt-4 text-sm text-white/60">{t("ai.loading")}</p>
            ) : !planData ? (
              <p className="mt-4 text-sm text-white/60">{t("analytics.empty.plan")}</p>
            ) : (
              <PlanSummary
                completed={completedBlocks}
                total={totalBlocks}
                activeBlocks={activeBlocks}
                t={t}
              />
            )}
          </div>

          <div className="card-ambient rounded-3xl border border-white/10 bg-[#0b1424] p-6">
            <h2 className="text-sm uppercase tracking-wide text-white/50">{t("analytics.section.recommendations")}</h2>
            <ul className="mt-3 list-disc space-y-2 pl-4 text-sm text-white/80">
              {recommendations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <EfficiencyCard data={efficiencyData} loading={efficiencyLoading} />
        <MistakeReview data={mistakeData} loading={mistakesLoading} />
      </section>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
      <p className="text-xs uppercase tracking-wide text-white/50">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-white">{value}</p>
    </div>
  );
}

function ActivityTrend({ data }: { data: ProgressEntry[] }) {
  const { t } = useI18n();
  if (data.length < 2 || data.every((entry) => !entry.questions_answered)) {
    return (
      <p className="mt-2 text-sm text-white/60">
        {t("analytics.trend.empty")}
      </p>
    );
  }
  const maxQuestions = Math.max(...data.map((entry) => entry.questions_answered), 1);
  return (
    <div className="mt-3 flex items-end gap-3">
      {data.map((entry) => {
        const height = Math.max((entry.questions_answered / maxQuestions) * 100, 8);
        const dayLabel = new Date(entry.day).toLocaleDateString(undefined, { weekday: "short" });
        return (
          <div key={entry.day} className="flex flex-1 flex-col items-center gap-2">
            <div
              className="w-full rounded-full bg-gradient-to-b from-white/80 to-white/30"
              style={{ height: `${height}%`, minHeight: "6px" }}
              title={`${entry.questions_answered} q`}
            />
            <p className="text-xs text-white/60">{dayLabel}</p>
          </div>
        );
      })}
    </div>
  );
}

function SkillInsight({
  strengths,
  focusAreas,
}: {
  strengths: MasteryEntry[];
  focusAreas: MasteryEntry[];
}) {
  const { t } = useI18n();
  return (
    <div className="mt-4 grid gap-5 md:grid-cols-2">
      <div>
        <p className="text-xs uppercase tracking-wide text-white/50">{t("analytics.strength.label")}</p>
        <div className="mt-2 space-y-3">
          {strengths.map((entry) => (
            <SkillRow key={entry.skill_tag} entry={entry} />
          ))}
        </div>
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-white/50">{t("analytics.focus.label")}</p>
        <div className="mt-2 space-y-3">
          {focusAreas.length ? (
            focusAreas.map((entry) => <SkillRow key={entry.skill_tag} entry={entry} emphasize />)
          ) : (
            <p className="text-sm text-white/60">{t("analytics.empty.mastery")}</p>
          )}
        </div>
      </div>
    </div>
  );
}

function SkillRow({ entry, emphasize }: { entry: MasteryEntry; emphasize?: boolean }) {
  const label = entry.label ?? entry.skill_tag;
  const score = Math.round((entry.mastery_score ?? 0) * 100);
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <p className={emphasize ? "font-semibold text-white" : "text-white/80"}>{label}</p>
        <span className="text-white/60">{score}%</span>
      </div>
      <div className="h-2 rounded-full bg-white/5">
        <div
          className={`h-full rounded-full ${emphasize ? "bg-rose-400" : "bg-emerald-400/80"}`}
          style={{ width: `${score}%` }}
        />
      </div>
    </div>
  );
}

function PlanSummary({
  completed,
  total,
  activeBlocks,
  t,
}: {
  completed: number;
  total: number;
  activeBlocks: PlanTask[];
  t: ReturnType<typeof useI18n>["t"];
}) {
  const percent = total ? Math.min((completed / total) * 100, 100) : 0;
  return (
    <div className="space-y-4">
      <div>
        <p className="text-sm font-semibold text-white">
          {t("analytics.plan.blocksCompleted", { completed, total: total || "0" })}
        </p>
        <div className="mt-2 h-2 rounded-full bg-white/5">
          <div className="h-full rounded-full bg-white/70" style={{ width: `${percent}%` }} />
        </div>
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-white/50">{t("analytics.plan.activeLabel")}</p>
        {activeBlocks.length === 0 ? (
          <p className="mt-2 text-sm text-white/60">{t("plan.empty")}</p>
        ) : (
          <div className="mt-2 space-y-2">
            {activeBlocks.map((task) => (
              <div
                key={task.block_id}
                className="rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/80"
              >
                <div className="flex items-center justify-between">
                  <span>{task.block_id.replace(/^[^:]+:/, "")}</span>
                  <span>
                    {task.questions_completed}/{task.questions_target}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function EfficiencyCard({
  data,
  loading,
}: {
  data?: EfficiencySummary;
  loading: boolean;
}) {
  const { t } = useI18n();
  return (
    <div className="card-ambient rounded-3xl border border-white/10 bg-[#0b1424] p-6">
      <h2 className="text-sm uppercase tracking-wide text-white/50">{t("analytics.section.efficiency")}</h2>
      {loading ? (
        <p className="mt-4 text-sm text-white/60">{t("ai.loading")}</p>
      ) : !data || !data.sample_size ? (
        <p className="mt-4 text-sm text-white/60">{t("analytics.efficiency.empty")}</p>
      ) : (
        <div className="mt-4 space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
              <p className="text-xs uppercase tracking-wide text-white/50">{t("analytics.efficiency.overall")}</p>
              <p className="mt-2 text-lg font-semibold text-white">
                {formatSeconds(data.overall_avg_time_sec)}
                <span className="ml-2 text-sm text-white/60">
                  / {formatSeconds(data.overall_recommended_time_sec)}
                </span>
              </p>
              <p className="text-xs text-white/50">
                {t("analytics.efficiency.samples", { count: data.sample_size })}
              </p>
            </div>
          </div>
          <div className="space-y-3">
            {data.sections.map((section) => (
              <div key={section.section}>
                <div className="flex items-center justify-between text-sm text-white/70">
                  <span>{section.section}</span>
                  <span>
                    {formatSeconds(section.avg_time_sec)} / {formatSeconds(section.recommended_time_sec)}
                  </span>
                </div>
                <div className="mt-1 h-2 rounded-full bg-white/5">
                  <div
                    className={`h-full rounded-full ${
                      section.avg_time_sec > section.recommended_time_sec + 5
                        ? "bg-rose-400"
                        : "bg-emerald-400/80"
                    }`}
                    style={{
                      width: `${Math.min(
                        (section.avg_time_sec / section.recommended_time_sec) * 100,
                        120
                      )}%`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
          {data.slow_skills.length ? (
            <div>
              <p className="text-xs uppercase tracking-wide text-white/50">
                {t("analytics.efficiency.skillLag")}
              </p>
              <ul className="mt-2 space-y-2 text-sm text-white/80">
                {data.slow_skills.slice(0, 3).map((skill) => (
                  <li key={skill.skill_tag} className="rounded-2xl border border-white/10 bg-white/5 px-3 py-2">
                    <div className="flex items-center justify-between">
                      <span>{skill.label}</span>
                      <span>
                        {formatSeconds(skill.avg_time_sec)} / {formatSeconds(skill.recommended_time_sec)}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

function MistakeReview({
  data,
  loading,
}: {
  data?: MistakeQueue;
  loading: boolean;
}) {
  const { t } = useI18n();
  return (
    <div className="card-ambient rounded-3xl border border-white/10 bg-[#0b1424] p-6">
      <h2 className="text-sm uppercase tracking-wide text-white/50">{t("analytics.section.mistakes")}</h2>
      {loading ? (
        <p className="mt-4 text-sm text-white/60">{t("ai.loading")}</p>
      ) : !data || data.total_mistakes === 0 ? (
        <p className="mt-4 text-sm text-white/60">{t("analytics.mistakes.empty")}</p>
      ) : (
        <div className="mt-4 space-y-4">
          <div className="flex gap-3">
            <div className="flex-1 rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/80">
              <p className="text-xs uppercase tracking-wide text-white/50">{t("analytics.mistakes.pending")}</p>
              <p className="text-xl font-semibold text-white">{data.pending_explanations}</p>
            </div>
            <div className="flex-1 rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/80">
              <p className="text-xs uppercase tracking-wide text-white/50">{t("analytics.mistakes.reviewed")}</p>
              <p className="text-xl font-semibold text-white">
                {data.total_mistakes - data.pending_explanations}
              </p>
            </div>
          </div>
          <ul className="space-y-3 text-sm text-white/80">
            {data.items.slice(0, 4).map((item) => (
              <li key={item.log_id} className="rounded-2xl border border-white/10 bg-white/5 px-3 py-2">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-semibold text-white">
                      {item.question_uid ? `#${item.question_uid}` : `Q${item.question_id}`}
                    </p>
                    <p className="text-xs text-white/60">
                      {item.section}
                      {item.skill_tags?.[0] ? ` · ${item.skill_tags[0]}` : ""}
                    </p>
                  </div>
                  <span
                    className={`rounded-full px-3 py-1 text-xs ${
                      item.viewed_explanation ? "bg-emerald-500/20 text-emerald-100" : "bg-rose-500/10 text-rose-100"
                    }`}
                  >
                    {item.viewed_explanation ? t("analytics.mistakes.viewed") : t("analytics.mistakes.unviewed")}
                  </span>
                </div>
                <div className="mt-2 flex items-center justify-between text-xs text-white/60">
                  <span>{item.answered_at ? new Date(item.answered_at).toLocaleString() : "—"}</span>
                  <span>{formatSeconds(item.time_spent_sec)}</span>
                </div>
                <div className="mt-2">
                  <Link
                    href={item.question_uid ? `/ai/explain?search=${encodeURIComponent(item.question_uid)}` : "/ai/explain"}
                    className="text-xs text-white/70 underline hover:text-white"
                  >
                    {t("analytics.mistakes.viewExplain")}
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function formatSeconds(value?: number | null) {
  if (!value && value !== 0) return "—";
  const rounded = Math.round(value);
  if (rounded < 60) {
    return `${rounded}s`;
  }
  const minutes = Math.floor(rounded / 60);
  const seconds = rounded % 60;
  return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
}

function summarizeProgress(entries: ProgressEntry[]) {
  const totalQuestions = entries.reduce((sum, entry) => sum + (entry.questions_answered || 0), 0);
  const totalSessions = entries.reduce((sum, entry) => sum + (entry.sessions_completed || 0), 0);
  const avgAccuracyRaw =
    entries.reduce((sum, entry) => sum + (typeof entry.accuracy === "number" ? entry.accuracy : 0), 0) /
    (entries.length || 1);
  const dayStreak = computeStreak(entries);
  return {
    totalQuestions,
    totalSessions,
    avgAccuracy: avgAccuracyRaw,
    dayStreak,
  };
}

function computeStreak(entries: ProgressEntry[]) {
  let streak = 0;
  for (let i = entries.length - 1; i >= 0; i -= 1) {
    if (entries[i].questions_answered > 0) {
      streak += 1;
    } else {
      break;
    }
  }
  return streak;
}

function formatPercent(value: number) {
  if (!value && value !== 0) return "—";
  return `${Math.round(value * 100)}%`;
}

function deriveSkillInsights(entries: MasteryEntry[]): [MasteryEntry[], MasteryEntry[]] {
  if (!entries.length) {
    return [[], []];
  }
  const sorted = [...entries].sort((a, b) => (b.mastery_score ?? 0) - (a.mastery_score ?? 0));
  const strengths = sorted.slice(0, 3);
  const reversed = [...sorted].reverse();
  const focus = reversed
    .filter((entry) => (entry.mastery_score ?? 0) < 0.75)
    .slice(0, 3);
  return [strengths, focus];
}

function buildRecommendations({
  focusAreas,
  activeBlocks,
  streak,
  hasPlan,
  t,
}: {
  focusAreas: MasteryEntry[];
  activeBlocks: PlanTask[];
  streak: number;
  hasPlan: boolean;
  t: ReturnType<typeof useI18n>["t"];
}) {
  const recs: string[] = [];
  if (focusAreas[0]) {
    recs.push(
      t("analytics.reco.focusSkill", {
        skill: focusAreas[0].label ?? focusAreas[0].skill_tag,
      })
    );
  }
  if (activeBlocks[0]) {
    recs.push(
      t("analytics.reco.plan", {
        name: activeBlocks[0].block_id,
      })
    );
  } else if (!hasPlan) {
    recs.push(t("analytics.reco.startPlan"));
  }
  if (streak >= 1) {
    recs.push(
      t("analytics.reco.consistency", {
        streak,
      })
    );
  }
  return recs.length ? recs : [t("analytics.reco.startPlan")];
}

