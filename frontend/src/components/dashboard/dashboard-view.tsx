"use client";

import { useMemo, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { PlanBlocks } from "@/components/dashboard/plan-blocks";
import { MasteryProgress } from "@/components/dashboard/mastery-progress";
import { useDashboardData } from "@/hooks/use-dashboard-data";
import { PlanTask, ProgressEntry, StudyPlanDetail } from "@/types/learning";
import { useI18n } from "@/hooks/use-i18n";

function deriveHighlights(
  plan: StudyPlanDetail | undefined,
  latestProgress: ProgressEntry | undefined,
  t: ReturnType<typeof useI18n>["t"]
) {
  const highlights: string[] = [];
  const pushUnique = (text: string | undefined) => {
    if (!text) return;
    if (!highlights.includes(text)) {
      highlights.push(text);
    }
  };
  if (plan) {
    pushUnique(
      t("ai.highlightTarget", {
        minutes: plan.target_minutes,
        questions: plan.target_questions,
      })
    );
  }
  if (plan?.blocks?.length) {
    const firstBlock = plan.blocks[0];
    pushUnique(
      t("ai.highlightFirstBlock", {
        skill: firstBlock.focus_skill_label ?? firstBlock.focus_skill,
      })
    );
  }
  if (plan?.insights?.length) {
    plan.insights.slice(0, 2).forEach((insight) => pushUnique(insight));
  }
  if (latestProgress) {
    pushUnique(
      t("ai.highlightRecentAccuracy", {
        accuracy: Math.round(latestProgress.accuracy * 100),
        questions: latestProgress.questions_answered,
      })
    );
  }
  return highlights;
}

export function DashboardView() {
  const { planQuery, masteryQuery, progressQuery, tutorNotesQuery } = useDashboardData();
  const { t } = useI18n();
  const [collapsed, setCollapsed] = useState({
    plan: false,
    mastery: false,
  });

  const planDetail = planQuery.data?.plan;
  const planTaskMap = useMemo(() => {
    const entries: Record<string, PlanTask | undefined> = {};
    const tasks = planQuery.data?.tasks ?? planDetail?.tasks ?? [];
    tasks.forEach((task) => {
      entries[task.block_id] = task;
    });
    return entries;
  }, [planQuery.data?.tasks, planDetail?.tasks]);

  const latestProgress = progressQuery.data?.[progressQuery.data.length - 1];
  const fallbackHighlights = deriveHighlights(planDetail, latestProgress, t);
  const planBlocks = planDetail?.blocks ?? [];
  const sessionCount = progressQuery.data?.length ?? 0;
  const heroStats = [
    {
      label: t("plan.hero.stat.minutes"),
      value:
        planDetail && typeof planDetail.target_minutes === "number"
          ? `${planDetail.target_minutes} min`
          : t("plan.hero.stat.placeholder"),
    },
    {
      label: t("plan.hero.stat.questions"),
      value:
        planDetail && typeof planDetail.target_questions === "number"
          ? `${planDetail.target_questions}`
          : t("plan.hero.stat.placeholder"),
    },
    {
      label: t("plan.hero.stat.accuracy"),
      value: latestProgress
        ? `${Math.round(latestProgress.accuracy * 100)}%`
        : t("plan.hero.stat.placeholder"),
    },
    {
      label: t("plan.hero.stat.sessions"),
      value: sessionCount ? `${sessionCount}` : t("plan.hero.stat.placeholder"),
    },
  ];

  function renderSectionHeader(section: "plan" | "mastery", title: string, subtitle: string) {
    return (
      <button
        type="button"
        onClick={() =>
          setCollapsed((prev) => ({
            ...prev,
            [section]: !prev[section],
          }))
        }
        className="flex w-full items-center justify-between gap-4 text-left"
      >
        <div>
          <p className="text-sm font-semibold text-white">{title}</p>
          <p className="text-xs text-white/60">{subtitle}</p>
        </div>
        <span className="text-xs uppercase tracking-wide text-white/60">
          {collapsed[section] ? t("plan.section.expand") : t("plan.section.collapse")}
        </span>
      </button>
    );
  }

  const isInitialPlanLoading = planQuery.isLoading && !planQuery.data;
  const isPlanRefreshing = planQuery.isFetching && !!planQuery.data;

  return (
    <AppShell>
      <div className="col-span-full mx-auto flex w-full max-w-5xl flex-col gap-8 px-4 py-8">
        <section className="rounded-3xl border border-white/10 bg-[#0c1527] p-6 text-center">
          <p className="text-xs uppercase tracking-[0.3em] text-white/50">{t("plan.hero.heading")}</p>
          <p className="mt-2 text-2xl font-semibold text-white">{t("plan.card.title")}</p>
          <p className="text-sm text-white/60">{t("plan.hero.subtitle")}</p>
          <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {heroStats.map((stat) => (
              <div
                key={stat.label}
                className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-white"
              >
                <p className="text-xs uppercase tracking-wide text-white/50">{stat.label}</p>
                <p className="mt-1 text-lg font-semibold">{stat.value}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-3xl border border-white/10 bg-[#0b1424] p-6">
          {renderSectionHeader("plan", t("plan.card.title"), t("plan.card.subtitle"))}
          {!collapsed.plan && (
            <div className="mt-5 flex flex-col gap-5 lg:flex-row">
              <div className="flex-1 rounded-2xl border border-white/10 bg-white/5 p-4">
                {isInitialPlanLoading ? (
                  <PlanGeneratingState />
                ) : planQuery.error ? (
                  <p className="text-sm text-red-400">{t("plan.error")}</p>
                ) : planBlocks.length ? (
                  <>
                    {isPlanRefreshing && (
                      <p className="mb-2 text-xs text-emerald-200/80">{t("plan.refreshing")}</p>
                    )}
                    <PlanBlocks blocks={planBlocks} taskMap={planTaskMap} />
                  </>
                ) : (
                  <p className="text-sm text-white/40">{t("plan.empty")}</p>
                )}
              </div>
              <div className="w-full rounded-2xl border border-white/10 bg-white/5 p-4 lg:max-w-xs">
                <p className="text-xs uppercase tracking-wide text-white/50">
                  {t("plan.hero.highlightsTitle")}
                </p>
                <div className="mt-3 space-y-2 text-sm text-white/80">
                  {isInitialPlanLoading || progressQuery.isLoading || tutorNotesQuery.isLoading ? (
                    <p className="text-white/50">{t("ai.loading")}</p>
                  ) : tutorNotesQuery.error ? (
                    <p className="text-white/50">{t("plan.hero.highlightsEmpty")}</p>
                  ) : (
                    (tutorNotesQuery.data?.notes?.length
                      ? tutorNotesQuery.data.notes
                      : fallbackHighlights.map((text) => ({ title: "", body: text, priority: "info" }))
                    ).slice(0, 3).map((note, idx) => (
                      <div key={`${note.body}-${idx}`} className="space-y-1 rounded-xl border border-white/10 bg-black/10 p-2">
                        <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-white/50">
                          <span
                            className={`h-1.5 w-1.5 rounded-full ${
                              note.priority === "warning"
                                ? "bg-amber-300"
                                : note.priority === "success"
                                ? "bg-emerald-400"
                                : "bg-sky-300"
                            }`}
                          />
                          {note.title || t("plan.hero.noteDefaultTitle")}
                        </div>
                        <p className="text-sm text-white/80">{note.body}</p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          )}
        </section>

        <section className="rounded-3xl border border-white/10 bg-[#0b1424] p-6">
          {renderSectionHeader("mastery", t("mastery.card.title"), t("mastery.card.subtitle"))}
          {!collapsed.mastery && (
            <div className="mt-5">
              {masteryQuery.isLoading ? (
                <p className="text-sm text-white/50">{t("mastery.loading")}</p>
              ) : masteryQuery.error ? (
                <p className="text-sm text-red-400">{t("mastery.error")}</p>
              ) : (
                <MasteryProgress mastery={masteryQuery.data ?? []} />
              )}
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}

function PlanGeneratingState() {
  const { t } = useI18n();
  return (
    <div className="space-y-4 rounded-2xl border border-dashed border-white/20 bg-black/10 p-4 text-sm text-white/70">
      <div>
        <p className="text-base font-semibold text-white">
          {t("plan.generating.title")}
        </p>
        <p className="text-xs text-white/60">{t("plan.generating.subtitle")}</p>
        <p className="text-xs text-white/40">{t("plan.generating.eta")}</p>
      </div>
      <div className="space-y-3">
        {[0, 1, 2].map((index) => (
          <div
            key={index}
            className="h-12 rounded-2xl border border-white/5 bg-white/5 px-4 py-2"
          >
            <div className="h-full w-full animate-pulse rounded-xl bg-white/10" />
          </div>
        ))}
      </div>
    </div>
  );
}

