"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { AppShell } from "@/components/layout/app-shell";
import { useI18n } from "@/hooks/use-i18n";
import {
  getDiagnosticStatus,
  startDiagnosticAttempt,
  skipDiagnosticAttempt,
} from "@/services/diagnostic";
import { extractErrorMessage } from "@/lib/errors";
import { DiagnosticStatus } from "@/types/diagnostic";

export function DiagnosticPageView() {
  const { t } = useI18n();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["diagnostic-status", "page"],
    queryFn: getDiagnosticStatus,
  });
  const [actionError, setActionError] = useState<string | null>(null);
  const [isStarting, setStarting] = useState(false);
  const [isSkipping, setSkipping] = useState(false);
  const totalQuestions = data?.progress?.total_questions ?? 22;
  const completedQuestions = data?.progress?.completed_questions ?? 0;

  const handleStart = async () => {
    setActionError(null);
    setStarting(true);
    try {
      await startDiagnosticAttempt();
      await queryClient.invalidateQueries({ queryKey: ["diagnostic-status"] });
      router.push("/practice?autoResume=diagnostic");
    } catch (err) {
      setActionError(extractErrorMessage(err, t("diagnostic.error.start")));
    } finally {
      setStarting(false);
    }
  };

  const handleSkip = async () => {
    setActionError(null);
    setSkipping(true);
    try {
      await skipDiagnosticAttempt();
      await queryClient.invalidateQueries({ queryKey: ["diagnostic-status"] });
      await refetch();
    } catch (err) {
      setActionError(extractErrorMessage(err, t("diagnostic.error.skip")));
    } finally {
      setSkipping(false);
    }
  };

  const requiresDiagnostic = data?.requires_diagnostic ?? true;

  if (!requiresDiagnostic && !isLoading) {
    return (
      <AppShell>
        <div className="col-span-full mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-12 text-white">
          <div className="mb-2 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <Link
              href="/"
              className="inline-flex items-center gap-2 text-sm font-semibold text-white/80 transition hover:text-white"
            >
              <span aria-hidden="true">←</span>
              {t("diagnostic.page.returnDashboard")}
            </Link>
            <div className="chip-soft">
              {t("diagnostic.card.progress", { completed: completedQuestions, total: totalQuestions })}
            </div>
          </div>
          <div className="card-ambient rounded-3xl border border-white/10 bg-[#0b1424] p-6 text-center">
            <p className="text-xs uppercase tracking-[0.3em] text-white/40">
              {t("diagnostic.page.completedHeading")}
            </p>
            <h1 className="mt-3 text-2xl font-semibold">{t("diagnostic.page.completedTitle")}</h1>
            <p className="mt-2 text-white/70">{t("diagnostic.page.completedSubtitle")}</p>
            <Link
              href="/"
              className="mt-6 btn-cta justify-center"
            >
              {t("diagnostic.page.returnDashboard")}
            </Link>
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="col-span-full mx-auto flex w-full max-w-5xl flex-col gap-8 px-4 py-10 text-white">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-sm font-semibold text-white/80 transition hover:text-white"
          >
            <span aria-hidden="true">←</span>
            {t("diagnostic.page.returnDashboard")}
          </Link>
          <div className="chip-soft">
            {t("diagnostic.card.progress", { completed: completedQuestions, total: totalQuestions })}
          </div>
        </div>
        <header className="card-ambient rounded-3xl border border-white/10 bg-[#0b1424] p-6">
          <p className="text-xs uppercase tracking-[0.3em] text-white/50">
            {t("diagnostic.page.heading")}
          </p>
          <h1 className="mt-2 text-3xl font-semibold">{t("diagnostic.page.title")}</h1>
          <p className="mt-3 text-white/70">{t("diagnostic.page.subtitle")}</p>
          <ul className="mt-4 list-disc space-y-2 pl-5 text-sm text-white/70">
            <li>{t("diagnostic.page.tip.coverage")}</li>
            <li>{t("diagnostic.page.tip.time")}</li>
            <li>{t("diagnostic.page.tip.skip")}</li>
          </ul>
          <div className="mt-6 flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              className="btn-cta flex-1 justify-center"
              onClick={handleStart}
              disabled={isStarting || isLoading}
            >
              {isStarting
                ? t("diagnostic.page.button.preparing")
                : data?.session
                ? t("diagnostic.page.button.resume")
                : t("diagnostic.page.button.start")}
            </button>
            <button
              type="button"
              className="btn-ghost flex-1 justify-center"
              onClick={handleSkip}
              disabled={isSkipping}
            >
              {isSkipping
                ? t("diagnostic.page.button.skipping")
                : t("diagnostic.page.button.skip")}
            </button>
          </div>
          {actionError && <p className="mt-3 text-sm text-red-400">{actionError}</p>}
        </header>

        <DiagnosticDetail status={data} isLoading={isLoading} error={error} t={t} />
      </div>
    </AppShell>
  );
}

type DiagnosticDetailProps = {
  status: DiagnosticStatus | undefined;
  isLoading: boolean;
  error: unknown;
  t: ReturnType<typeof useI18n>["t"];
};

function DiagnosticDetail({ status, isLoading, error, t }: DiagnosticDetailProps) {
  const total = status?.progress?.total_questions ?? 22;
  const completed = status?.progress?.completed_questions ?? 0;
  const skills = status?.progress?.skills ?? [];
  const progressPct = total > 0 ? Math.round((completed / total) * 100) : 0;

  return (
    <section className="card-ambient rounded-3xl border border-white/10 bg-[#0b1424] p-6">
      <div className="flex flex-col gap-6 lg:flex-row">
        <div className="flex-1">
          <h2 className="text-xl font-semibold text-white">{t("diagnostic.page.progressTitle")}</h2>
          {isLoading ? (
            <p className="mt-2 text-sm text-white/60">{t("diagnostic.card.loading")}</p>
          ) : error ? (
            <p className="mt-2 text-sm text-red-400">{t("diagnostic.card.error")}</p>
          ) : (
            <>
              <p className="mt-2 text-sm text-white/60">
                {t("diagnostic.card.progress", { completed, total })}
              </p>
              <div className="mt-4 h-3 rounded-full bg-white/10">
                <div
                  className="h-full rounded-full bg-emerald-400"
                  style={{ width: `${Math.min(progressPct, 100)}%` }}
                />
              </div>
            </>
          )}
        </div>
        <div className="flex-1">
          <h2 className="text-xl font-semibold text-white">{t("diagnostic.page.skillsTitle")}</h2>
          {skills.length ? (
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {skills.map((skill) => (
                <div
                  key={skill.tag}
                  className="card-ambient rounded-2xl border border-white/10 bg-white/5 px-3 py-3 text-sm text-white/80"
                >
                  <p className="font-semibold">{skill.label}</p>
                  <p className="text-xs text-white/50">
                    {skill.completed}/{skill.total}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-2 text-sm text-white/60">{t("diagnostic.card.skillsEmpty")}</p>
          )}
        </div>
      </div>
    </section>
  );
}

