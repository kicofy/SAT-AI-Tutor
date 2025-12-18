"use client";

import Link from "next/link";
import { useMemo, useState, useCallback, type ReactNode } from "react";
import { AxiosError } from "axios";
import { useQueryClient } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/app-shell";
import { PlanBlocks } from "@/components/dashboard/plan-blocks";
import { ProgressSummary } from "@/components/dashboard/progress-summary";
import { MasteryProgress } from "@/components/dashboard/mastery-progress";
import { useDashboardData } from "@/hooks/use-dashboard-data";
import { PlanBlock, PlanTask, ProgressEntry, StudyPlanDetail } from "@/types/learning";
import { useI18n } from "@/hooks/use-i18n";
import { skipDiagnosticAttempt } from "@/services/diagnostic";
import { extractErrorMessage } from "@/lib/errors";
import { DiagnosticStatus } from "@/types/diagnostic";
import { useAuthStore } from "@/stores/auth-store";
import type { MembershipStatus } from "@/types/auth";

const formatMinutesDuration = (minutes: number) => {
  if (!Number.isFinite(minutes) || minutes <= 0) {
    return "—";
  }
  if (minutes < 60) {
    return `${Math.round(minutes)} min`;
  }
  const hrs = Math.floor(minutes / 60);
  const mins = Math.round(minutes % 60);
  if (!mins) {
    return `${hrs}h`;
  }
  return `${hrs}h ${mins}m`;
};

const formatEtaTime = (date: Date) =>
  date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

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
  if (latestProgress && typeof latestProgress.accuracy === "number") {
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
  const {
    planQuery,
    masteryQuery,
    progressQuery,
    todayProgressQuery,
    tutorNotesQuery,
    diagnosticQuery,
  } =
    useDashboardData();
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [collapsed, setCollapsed] = useState({
    plan: false,
    mastery: false,
  });
  const [isSkippingDiagnostic, setSkippingDiagnostic] = useState(false);
  const [skipError, setSkipError] = useState<string | null>(null);
  const diagnosticStatus = diagnosticQuery.data;
  const requiresDiagnostic = diagnosticStatus?.requires_diagnostic ?? false;
  const planDetail = planQuery.data?.plan;
  const membership = useAuthStore((state) => state.user?.membership);
  const planQueryError = planQuery.error;
  const planMembershipPayload =
    planQueryError instanceof AxiosError &&
    planQueryError.response?.status === 402 &&
    planQueryError.response?.data?.error === "membership_required"
      ? (planQueryError.response?.data as { membership?: MembershipStatus; message?: string })
      : null;
  const showPlanLocked =
    Boolean(planMembershipPayload) ||
    (membership ? !(membership.is_member || membership.trial_active) : false);
  const planLockedMembership = planMembershipPayload?.membership ?? membership;
  const planLockedMessage = planMembershipPayload?.message ?? null;
  const showTrialBanner = Boolean(
    membership?.trial_active &&
      membership.trial_expires_at &&
      !membership.is_member
  );
  const trialBannerDate = showTrialBanner
    ? new Date(membership!.trial_expires_at!).toLocaleDateString()
    : null;
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
  const planBlocksById = useMemo(() => {
    const map = new Map<string, PlanBlock>();
    planBlocks.forEach((block) => {
      if (block.block_id) {
        map.set(block.block_id, block);
      }
    });
    return map;
  }, [planBlocks]);
  const planProgressSummary = useMemo(() => {
    if (!planDetail || !planBlocks.length) {
      return null;
    }
    const totalQuestions =
      planDetail.target_questions ??
      planBlocks.reduce((sum, block) => sum + (block.questions ?? 0), 0);
    const totalMinutes =
      planDetail.target_minutes ?? planBlocks.reduce((sum, block) => sum + (block.minutes ?? 0), 0);
    if (!totalQuestions && !totalMinutes) {
      return null;
    }
    const avgMinutesPerQuestion =
      totalQuestions > 0 && totalMinutes > 0 ? totalMinutes / totalQuestions : 0;
    let completedQuestions = 0;
    let consumedMinutes = 0;
    Object.values(planTaskMap).forEach((task) => {
      if (!task) return;
      const block = task.block_id ? planBlocksById.get(task.block_id) : undefined;
      const blockQuestions = block?.questions ?? task.questions_target ?? 0;
      const blockMinutes = block?.minutes ?? (blockQuestions ? blockQuestions * avgMinutesPerQuestion : 0);
      const perQuestionMinutes =
        blockQuestions > 0
          ? blockMinutes / blockQuestions
          : avgMinutesPerQuestion || 0;
      const completed = Math.min(
        task.questions_completed ?? 0,
        blockQuestions || (task.questions_completed ?? 0)
      );
      completedQuestions += completed;
      consumedMinutes += perQuestionMinutes * completed;
    });
    const remainingQuestions = Math.max(totalQuestions - completedQuestions, 0);
    const remainingMinutes = Math.max(totalMinutes - consumedMinutes, 0);
    const etaDate =
      remainingMinutes > 0 ? new Date(Date.now() + remainingMinutes * 60 * 1000) : null;
    return {
      remainingQuestions,
      totalQuestions,
      remainingMinutes,
      totalMinutes,
      etaDate,
    };
  }, [planBlocks, planBlocksById, planDetail, planTaskMap]);
  const planSummaryStats = useMemo(() => {
    if (!planProgressSummary) {
      return [];
    }
    return [
      {
        label: t("plan.summary.remaining"),
        value: `${planProgressSummary.remainingQuestions}/${planProgressSummary.totalQuestions}`,
      },
      {
        label: t("plan.summary.timeLeft"),
        value: formatMinutesDuration(planProgressSummary.remainingMinutes),
      },
      {
        label: t("plan.summary.eta"),
        value: planProgressSummary.etaDate
          ? formatEtaTime(planProgressSummary.etaDate)
          : t("plan.summary.etaUnset"),
      },
    ];
  }, [planProgressSummary, t]);
  const activePlanTask = useMemo(() => {
    const tasks = planQuery.data?.tasks ?? planDetail?.tasks ?? [];
    return tasks.find((task) => task.status === "active") ?? null;
  }, [planDetail?.tasks, planQuery.data?.tasks]);
  const sessionCount = progressQuery.data?.length ?? 0;
  const todayProgress = todayProgressQuery.data;
  const handleSkipDiagnostic = useCallback(async () => {
    setSkipError(null);
    setSkippingDiagnostic(true);
    try {
      await skipDiagnosticAttempt();
      await queryClient.invalidateQueries({ queryKey: ["diagnostic-status"] });
      await queryClient.invalidateQueries({ queryKey: ["plan-today"] });
      await queryClient.invalidateQueries({ queryKey: ["tutor-notes"] });
    } catch (err) {
      setSkipError(extractErrorMessage(err, t("diagnostic.error.skip")));
    } finally {
      setSkippingDiagnostic(false);
    }
  }, [queryClient, t]);

  if (requiresDiagnostic) {
    return (
      <AppShell>
        <div className="col-span-full mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-10">
          <DiagnosticRequirementCard
            status={diagnosticStatus}
            isLoading={diagnosticQuery.isLoading}
            error={diagnosticQuery.error}
            onSkip={handleSkipDiagnostic}
            isSkipping={isSkippingDiagnostic}
            skipError={skipError}
            t={t}
          />
        </div>
      </AppShell>
    );
  }

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
      value:
        latestProgress && typeof latestProgress.accuracy === "number"
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
        {showTrialBanner && trialBannerDate && (
          <div className="card-ambient rounded-2xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
            {t("plan.trial.banner", { date: trialBannerDate })}
          </div>
        )}
        <section className="card-ambient rounded-3xl border border-white/10 bg-[#0c1527]/95 p-6 text-center">
          <p className="text-xs uppercase tracking-[0.3em] text-white/50">{t("plan.hero.heading")}</p>
          <p className="mt-2 text-2xl font-semibold text-white">{t("plan.card.title")}</p>
          <p className="text-sm text-white/60">{t("plan.hero.subtitle")}</p>
          <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {heroStats.map((stat) => (
              <div key={stat.label} className="stat-pill text-white">
                <p className="text-xs uppercase tracking-wide text-white/50">{stat.label}</p>
                <p className="mt-1 text-lg font-semibold">{stat.value}</p>
              </div>
            ))}
          </div>
          <div className="mt-6">
            <ProgressSummary
              progress={todayProgress}
              isLoading={todayProgressQuery.isLoading}
              error={todayProgressQuery.error}
            />
          </div>
        </section>

        <section className="card-ambient rounded-3xl border border-white/10 bg-[#0b1424] p-6">
          {renderSectionHeader("plan", t("plan.card.title"), t("plan.card.subtitle"))}
          <Collapsible isOpen={!collapsed.plan}>
            <div className="mt-5 flex flex-col gap-5 lg:flex-row">
              <div className="card-ambient flex-1 rounded-2xl border border-white/10 bg-white/5 p-4">
                {showPlanLocked ? (
                  <PlanLockedState membership={planLockedMembership} message={planLockedMessage} />
                ) : isInitialPlanLoading ? (
                  <PlanGeneratingState />
                ) : planQuery.error ? (
                  <p className="text-sm text-red-400">{t("plan.error")}</p>
                ) : planBlocks.length ? (
                  <>
                    {isPlanRefreshing && (
                      <p className="mb-2 text-xs text-emerald-200/80">{t("plan.refreshing")}</p>
                    )}
                    {planSummaryStats.length > 0 && (
                      <div className="mb-4 flex flex-wrap gap-3">
                        {planSummaryStats.map((stat) => (
                          <div key={stat.label} className="stat-pill min-w-[160px] text-white">
                            <p className="text-[11px] uppercase tracking-wide text-white/60">
                              {stat.label}
                            </p>
                            <p className="text-base font-semibold">{stat.value}</p>
                          </div>
                        ))}
                      </div>
                    )}
                    <PlanBlocks blocks={planBlocks} taskMap={planTaskMap} />
                  </>
                ) : (
                  <p className="text-sm text-white/40">{t("plan.empty")}</p>
                )}
              </div>
              <div className="card-ambient w-full rounded-2xl border border-white/10 bg-white/5 p-4 lg:max-w-xs">
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
                      <div
                        key={`${note.body}-${idx}`}
                        className="card-ambient space-y-1 rounded-xl border border-white/10 bg-black/10 p-2"
                      >
                        <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-white">
                          <span
                            className={`h-1.5 w-1.5 rounded-full ${
                              note.priority === "warning"
                                ? "bg-amber-300"
                                : note.priority === "success"
                                ? "bg-emerald-400"
                                : "bg-sky-300"
                            }`}
                          />
                          <span className="font-semibold text-white/90">
                            {note.title || t("plan.hero.noteDefaultTitle")}
                          </span>
                        </div>
                        <p className="text-sm text-white/80">{note.body}</p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </Collapsible>
        </section>

        <section className="card-ambient rounded-3xl border border-white/10 bg-[#0b1424] p-6">
          {renderSectionHeader("mastery", t("mastery.card.title"), t("mastery.card.subtitle"))}
          <Collapsible isOpen={!collapsed.mastery}>
            <div className="mt-5">
              {masteryQuery.isLoading ? (
                <p className="text-sm text-white/50">{t("mastery.loading")}</p>
              ) : masteryQuery.error ? (
                <p className="text-sm text-red-400">{t("mastery.error")}</p>
              ) : (
                <MasteryProgress mastery={masteryQuery.data ?? []} />
              )}
            </div>
          </Collapsible>
        </section>
      </div>
    </AppShell>
  );
}

function Collapsible({ isOpen, children }: { isOpen: boolean; children: ReactNode }) {
  return (
    <div
      className={`grid transition-all duration-300 ease-in-out ${
        isOpen ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
      }`}
    >
      <div className="overflow-hidden">{children}</div>
    </div>
  );
}

function PlanGeneratingState() {
  const { t } = useI18n();
  return (
    <div className="card-ambient space-y-4 rounded-2xl border border-dashed border-white/20 bg-black/10 p-4 text-sm text-white/70">
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

function PlanLockedState({
  membership,
  message,
}: {
  membership?: MembershipStatus | null;
  message?: string | null;
}) {
  const { t } = useI18n();
  const trialRemaining = membership?.trial_days_remaining ?? 0;
  const trialActive = Boolean(membership?.trial_active);
  let body = message;
  if (!body) {
    body = trialActive
      ? t("plan.locked.trial", { days: trialRemaining })
      : t("plan.locked.detail");
  }
  return (
    <div className="space-y-3 text-center text-white/70">
      <p className="text-lg font-semibold text-white">{t("plan.locked.title")}</p>
      <p className="text-sm text-white/60">{body}</p>
      <Link href="/settings" className="btn-cta w-full justify-center sm:w-auto">
        {t("plan.locked.cta")}
      </Link>
    </div>
  );
}

type DiagnosticRequirementCardProps = {
  status: DiagnosticStatus | undefined;
  isLoading: boolean;
  error: unknown;
  onSkip: () => Promise<void>;
  isSkipping: boolean;
  skipError: string | null;
  t: ReturnType<typeof useI18n>["t"];
};

function DiagnosticRequirementCard({
  status,
  isLoading,
  error,
  onSkip,
  isSkipping,
  skipError,
  t,
}: DiagnosticRequirementCardProps) {
  const total = status?.progress?.total_questions ?? 22;
  const completed = status?.progress?.completed_questions ?? 0;
  const skills = status?.progress?.skills ?? [];
  const progressPct = total > 0 ? Math.round((completed / total) * 100) : 0;
  const skillsToShow = skills.slice(0, 4);
  return (
    <section className="card-ambient rounded-3xl border border-white/10 bg-[#0b1424] p-6 text-white">
      <p className="text-xs uppercase tracking-[0.3em] text-white/50">{t("diagnostic.card.heading")}</p>
      <h1 className="mt-2 text-2xl font-semibold">{t("diagnostic.card.title")}</h1>
      <p className="mt-1 text-sm text-white/60">{t("diagnostic.card.subtitle")}</p>
      {isLoading ? (
        <p className="mt-4 text-sm text-white/60">{t("diagnostic.card.loading")}</p>
      ) : error ? (
        <p className="mt-4 text-sm text-red-400">{t("diagnostic.card.error")}</p>
      ) : (
        <>
          <div className="mt-6">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-white/60">
              <span className="chip-soft chip-soft--info">
                {t("diagnostic.card.progress", { completed, total })}
              </span>
              <span className="font-semibold text-white/80">{progressPct}%</span>
            </div>
            <div className="mt-2 h-2 rounded-full bg-white/10">
              <div
                className="h-full rounded-full bg-emerald-400 transition-all"
                style={{ width: `${Math.min(progressPct, 100)}%` }}
              />
            </div>
          </div>
          <div className="mt-6">
            <p className="text-xs uppercase tracking-wide text-white/50">
              {t("diagnostic.card.skillsTitle")}
            </p>
            {skillsToShow.length ? (
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                {skillsToShow.map((skill) => (
                  <div
                    key={skill.tag}
                    className="card-ambient rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/80"
                  >
                    <p className="font-semibold">{skill.label}</p>
                    <p className="text-xs text-white/50">
                      {skill.completed}/{skill.total}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-3 text-sm text-white/50">{t("diagnostic.card.skillsEmpty")}</p>
            )}
          </div>
        </>
      )}
      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        <Link
          href="/diagnostic"
          className="btn-cta w-full flex-1 justify-center"
        >
          {t("diagnostic.card.cta")}
        </Link>
        <button
          type="button"
          onClick={onSkip}
          disabled={isSkipping}
          className="btn-ghost w-full flex-1 justify-center"
        >
          {isSkipping ? t("diagnostic.card.skipping") : t("diagnostic.card.skip")}
        </button>
      </div>
      {skipError && <p className="mt-3 text-sm text-red-400">{skipError}</p>}
    </section>
  );
}

