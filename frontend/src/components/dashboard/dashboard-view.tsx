"use client";

import { useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { PlanBlocks } from "@/components/dashboard/plan-blocks";
import { MasteryProgress } from "@/components/dashboard/mastery-progress";
import { useDashboardData } from "@/hooks/use-dashboard-data";
import { ProgressEntry, StudyPlanDetail } from "@/types/learning";
import { useI18n } from "@/hooks/use-i18n";

function deriveHighlights(
  plan: StudyPlanDetail | undefined,
  latestProgress: ProgressEntry | undefined,
  t: ReturnType<typeof useI18n>["t"]
) {
  const highlights: string[] = [];
  if (plan) {
    highlights.push(
      t("ai.highlightTarget", {
        minutes: plan.target_minutes,
        questions: plan.target_questions,
      })
    );
  }
  if (plan?.blocks?.length) {
    const firstBlock = plan.blocks[0];
    highlights.push(
      t("ai.highlightFirstBlock", {
        skill: firstBlock.focus_skill_label ?? firstBlock.focus_skill,
      })
    );
  }
  if (latestProgress) {
    highlights.push(
      t("ai.highlightRecentAccuracy", {
        accuracy: Math.round(latestProgress.accuracy * 100),
        questions: latestProgress.questions_answered,
      })
    );
  }
  return highlights;
}

export function DashboardView() {
  const { planQuery, masteryQuery, progressQuery } = useDashboardData();
  const { t } = useI18n();
  const [collapsed, setCollapsed] = useState({
    plan: false,
    mastery: false,
  });

  const latestProgress = progressQuery.data?.[progressQuery.data.length - 1];
  const highlights = deriveHighlights(planQuery.data, latestProgress, t);
  const planBlocks = planQuery.data?.blocks ?? [];
  const sessionCount = progressQuery.data?.length ?? 0;
  const heroStats = [
    {
      label: t("plan.hero.stat.minutes"),
      value:
        planQuery.data && typeof planQuery.data.target_minutes === "number"
          ? `${planQuery.data.target_minutes} min`
          : t("plan.hero.stat.placeholder"),
    },
    {
      label: t("plan.hero.stat.questions"),
      value:
        planQuery.data && typeof planQuery.data.target_questions === "number"
          ? `${planQuery.data.target_questions}`
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
                {planQuery.isLoading ? (
                  <p className="text-sm text-white/60">{t("plan.loading")}</p>
                ) : planQuery.error ? (
                  <p className="text-sm text-red-400">{t("plan.error")}</p>
                ) : planBlocks.length ? (
                  <PlanBlocks blocks={planBlocks} />
                ) : (
                  <p className="text-sm text-white/40">{t("plan.empty")}</p>
                )}
              </div>
              <div className="w-full rounded-2xl border border-white/10 bg-white/5 p-4 lg:max-w-xs">
                <p className="text-xs uppercase tracking-wide text-white/50">
                  {t("plan.hero.highlightsTitle")}
                </p>
                <div className="mt-3 space-y-2 text-sm text-white/80">
                  {planQuery.isLoading || progressQuery.isLoading ? (
                    <p className="text-white/50">{t("ai.loading")}</p>
                  ) : highlights.length ? (
                    highlights.slice(0, 3).map((tip, idx) => (
                      <div key={`${tip}-${idx}`} className="flex items-start gap-2">
                        <span className="mt-1 h-1.5 w-1.5 rounded-full bg-emerald-300" />
                        <p>{tip}</p>
                      </div>
                    ))
                  ) : (
                    <p className="text-white/50">{t("plan.hero.highlightsEmpty")}</p>
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

