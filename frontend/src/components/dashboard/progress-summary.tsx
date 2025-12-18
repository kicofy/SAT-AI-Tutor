"use client";

import { TodayProgress } from "@/types/learning";

type ProgressSummaryProps = {
  progress?: TodayProgress;
  isLoading?: boolean;
  error?: unknown;
};

function formatPercent(n: number, denom: number) {
  if (!denom) return 0;
  return Math.min(100, Math.round((n / denom) * 100));
}

export function ProgressSummary({ progress, isLoading, error }: ProgressSummaryProps) {
  if (isLoading) {
    return (
      <div className="card-ambient rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-white/70">
        <p className="text-xs uppercase tracking-wide text-white/60">Today</p>
        <div className="mt-3 h-20 animate-pulse rounded-xl bg-white/10" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="card-ambient rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-red-300">
        Failed to load today&apos;s progress.
      </div>
    );
  }

  if (!progress) {
    return null;
  }

  const questionsPct = formatPercent(progress.completed_questions, progress.target_questions || 0);
  const minutesPct = formatPercent(progress.completed_minutes, progress.target_minutes || 0);
  const streakGoal = progress.streak_next_goal ?? progress.streak_days;
  const streakPct = formatPercent(progress.streak_days, streakGoal || progress.streak_days || 1);

  const renderBar = (label: string, value: string, percent: number) => (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs text-white/70">
        <span>{label}</span>
        <span className="font-semibold text-white">{value}</span>
      </div>
      <div className="h-2 rounded-full bg-white/10">
        <div
          className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-sky-400 transition-all"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );

  return (
    <div className="card-ambient rounded-2xl border border-white/10 bg-white/5 p-4 text-white text-left">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-white/60">Today</p>
          <p className="text-lg font-semibold text-white">Progress & Streak</p>
        </div>
        <div className="chip-soft chip-soft--info text-xs">
          Streak: {progress.streak_days} day{progress.streak_days === 1 ? "" : "s"}
          {progress.streak_next_goal
            ? ` · ${progress.streak_next_goal - progress.streak_days} to ${progress.streak_next_goal}`
            : ""}
        </div>
      </div>

      <div className="mt-4 space-y-4">
        {renderBar(
          "Questions",
          `${progress.completed_questions}/${progress.target_questions || "—"}`,
          questionsPct
        )}
        {renderBar(
          "Minutes",
          `${Math.round(progress.completed_minutes)}/${progress.target_minutes || "—"} min`,
          minutesPct
        )}
        {streakGoal ? (
          renderBar(
            "Streak momentum",
            `${progress.streak_days}/${streakGoal} days`,
            streakPct
          )
        ) : (
          <div className="text-xs text-white/60">
            Streak: {progress.streak_days} day{progress.streak_days === 1 ? "" : "s"}
          </div>
        )}
      </div>

      {progress.last_active_day && (
        <p className="mt-3 text-[11px] uppercase tracking-wide text-white/40">
          Last active: {progress.last_active_day}
        </p>
      )}
    </div>
  );
}

