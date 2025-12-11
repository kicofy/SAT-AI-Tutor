"use client";

import { useDeferredValue, useEffect, useMemo, useState, type ReactNode, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { DashboardCard } from "@/components/ui/dashboard-card";
import { useI18n } from "@/hooks/use-i18n";
import {
  generateExplain,
  getExplainDetail,
  getExplainHistory,
  type ExplainHistoryFilters,
} from "@/services/ai-explain";
import type {
  ExplainHistoryItem,
  ExplainDetailResponse,
  ExplainHistoryResponse,
} from "@/types/explain";
import {
  ExplanationViewer,
  HighlightedText,
  type StepDirective,
  type Translator,
} from "@/components/practice/explanation-viewer";
import type { SessionQuestion } from "@/types/session";
import Link from "next/link";
import { useAuthStore } from "@/stores/auth-store";
import type { AiExplainQuota, MembershipStatus } from "@/types/auth";
import { getQuestionDecorations } from "@/lib/question-decorations";

const REFRESH_INTERVAL = 1000 * 30;

export function AIExplainPage() {
  return <AIExplainContent />;
}

function AIExplainContent() {
  const { t } = useI18n();
  const [filters, setFilters] = useState<ExplainHistoryFilters>({
    page: 1,
    perPage: 15,
  });
  const [selected, setSelected] = useState<ExplainHistoryItem | null>(null);
  const [activeDirectives, setActiveDirectives] = useState<StepDirective[]>([]);
  const [searchTerm, setSearchTerm] = useState(filters.search ?? "");
  const deferredSearch = useDeferredValue(searchTerm);
  const authUser = useAuthStore((state) => state.user);
  const updateAuthUser = useAuthStore((state) => state.updateUser);
  const applyQuotaUpdate = useCallback(
    (quota?: AiExplainQuota) => {
      if (!quota || !authUser) return;
      updateAuthUser({ ...authUser, ai_explain_quota: quota });
    },
    [authUser, updateAuthUser]
  );
  const membership = authUser?.membership;
  const aiQuota = authUser?.ai_explain_quota;
  const quotaLimit =
    aiQuota?.limit === undefined ? null : aiQuota?.limit === null ? null : aiQuota.limit;
  const quotaRemaining =
    quotaLimit === null ? null : Math.max(quotaLimit - (aiQuota?.used ?? 0), 0);
  const quotaExhausted = quotaLimit !== null && quotaRemaining !== null && quotaRemaining <= 0;

  useEffect(() => {
    setSearchTerm(filters.search ?? "");
  }, [filters.search]);

  const historyQuery = useQuery({
    queryKey: ["ai-explain-history", filters],
    queryFn: () => getExplainHistory(filters),
    refetchInterval: REFRESH_INTERVAL,
  });

  const items = historyQuery.data?.items ?? [];

  useEffect(() => {
    if (deferredSearch !== (filters.search ?? "")) {
      setFilters((prev) => ({
        ...prev,
        search: deferredSearch.trim() ? deferredSearch.trim() : undefined,
        page: 1,
      }));
    }
  }, [deferredSearch, filters.search]);

  useEffect(() => {
    if (!items.length) {
      setSelected(null);
      return;
    }
    if (selected && items.some((entry) => entry.log_id === selected.log_id)) {
      return;
    }
    setSelected(items[0]);
  }, [items, selected]);

  const detailQuery = useQuery({
    queryKey: ["ai-explain-detail", selected?.question_id, selected?.log_id],
    queryFn: () =>
      selected
        ? getExplainDetail({ questionId: selected.question_id, logId: selected.log_id })
        : Promise.resolve(null),
    enabled: Boolean(selected),
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
  });
  useEffect(() => {
    if (!detailQuery.error) return;
    const err = detailQuery.error;
    if (err instanceof AxiosError && err.response?.status === 404) {
      setSelected(null);
      historyQuery.refetch();
    }
  }, [detailQuery.error, historyQuery]);

  const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(event.target.value);
  };

  const detail = detailQuery.data ?? null;
  const pagination = historyQuery.data?.pagination;

  return (
    <div className="col-span-full mx-auto w-full max-w-6xl px-4 py-8">
      <div className="flex flex-col gap-4">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-sm font-semibold text-white/80 transition hover:text-white"
        >
          <span aria-hidden="true">←</span>
          {t("aiExplain.cta.home")}
        </Link>
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-white/50">{t("nav.ai")}</p>
          <h1 className="text-3xl font-semibold text-white">{t("aiExplain.title")}</h1>
          <p className="text-white/60 text-sm">{t("aiExplain.subtitle")}</p>
        </div>
        <QuotaNotice quota={aiQuota} membership={membership} />
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-[360px_minmax(0,1fr)]">
        <div className="space-y-4">
          <SearchCard searchValue={searchTerm} onSearchChange={handleSearchChange} />

          <HistoryPanel
            items={items}
            loading={historyQuery.isLoading}
            selected={selected}
            onSelect={setSelected}
            total={historyQuery.data?.pagination.total ?? 0}
            pagination={pagination}
            onPageChange={(delta) =>
              setFilters((prev) => ({
                ...prev,
                page: Math.max(1, (prev.page ?? 1) + delta),
              }))
            }
          />
        </div>

        <div className="space-y-4">
          <ExplainDetailSurface
            selected={selected}
            detail={detail}
            isLoading={detailQuery.isFetching}
            error={detailQuery.error}
            onBack={() => setSelected(null)}
            activeDirectives={activeDirectives}
            onDirectivesChange={setActiveDirectives}
            onRefreshDetail={detailQuery.refetch}
            quotaExhausted={quotaExhausted}
            onQuotaUpdate={applyQuotaUpdate}
          />
        </div>
      </div>
    </div>
  );
}

function ExplainDetailSurface({
  selected,
  detail,
  isLoading,
  error,
  onBack,
  activeDirectives,
  onDirectivesChange,
  onRefreshDetail,
  quotaExhausted,
  onQuotaUpdate,
}: {
  selected: ExplainHistoryItem | null;
  detail: ExplainDetailResponse | null;
  isLoading: boolean;
  error: unknown;
  onBack: () => void;
  activeDirectives: StepDirective[];
  onDirectivesChange: (directives: StepDirective[]) => void;
  onRefreshDetail: () => Promise<unknown>;
  quotaExhausted: boolean;
  onQuotaUpdate: (quota?: AiExplainQuota) => void;
}) {
  const { t } = useI18n();
  useEffect(() => {
    if (detail?.quota) {
      onQuotaUpdate(detail.quota as AiExplainQuota);
    }
  }, [detail?.quota, onQuotaUpdate]);

  if (!selected) {
    return (
      <div className="card-ambient rounded-3xl border border-dashed border-white/10 bg-white/5 px-6 py-16 text-center text-white/60">
        {t("aiExplain.detail.selectPrompt")}
      </div>
    );
  }

  if (isLoading) {
    return <DetailSkeleton selected={selected} />;
  }

  if (error) {
    return (
      <div className="card-ambient rounded-3xl border border-rose-400/40 bg-rose-500/10 px-6 py-10 text-center text-rose-100">
        {t("aiExplain.detail.error", {
          message: (error as Error).message ?? t("aiExplain.detail.errorUnknown"),
        })}
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="card-ambient rounded-3xl border border-white/10 bg-white/5 px-6 py-16 text-center text-white/60">
        {t("aiExplain.detail.noData")}
      </div>
    );
  }

  return (
    <ExplainDetailPanel
      detail={detail}
      onBack={onBack}
      activeDirectives={activeDirectives}
      onDirectivesChange={onDirectivesChange}
            onRefreshDetail={onRefreshDetail}
      quotaExhausted={quotaExhausted}
      onQuotaUpdate={onQuotaUpdate}
    />
  );
}

function ExplainDetailPanel({
  detail,
  onBack,
  activeDirectives,
  onDirectivesChange,
  onRefreshDetail,
  quotaExhausted,
  onQuotaUpdate,
}: {
  detail: ExplainDetailResponse;
  onBack: () => void;
  activeDirectives: StepDirective[];
  onDirectivesChange: (directives: StepDirective[]) => void;
  onRefreshDetail: () => Promise<unknown>;
  quotaExhausted: boolean;
  onQuotaUpdate: (quota?: AiExplainQuota) => void;
}) {
  const { t } = useI18n();
  const translator = useMemo<Translator>(
    () => ((key, params) => t(key as any, params as any)) as Translator,
    [t]
  );
  const [isGenerating, setIsGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const question = detail.question as SessionQuestion;
  const meta = detail.meta;
  const aiExplanation = detail.ai_explanation;
  const userValue = meta.user_answer?.value;
  const correctValue = meta.correct_answer?.value;

  const questionDecorations = useMemo(
    () => getQuestionDecorations(question),
    [question]
  );
  const combinedDirectives = useMemo(
    () => [...questionDecorations, ...activeDirectives],
    [questionDecorations, activeDirectives]
  );

  const sectionLabel = [meta.section, meta.sub_section].filter(Boolean).join(" · ");
  const skillLabel = meta.skill_tags?.slice(0, 2).join(" / ");

  const summaryFields = [
    {
      label: t("aiExplain.detail.field.attempts"),
      value: `${meta.attempt_count ?? 1}`,
    },
    { label: t("aiExplain.detail.field.correct"), value: correctValue || t("common.unknown") },
    { label: t("aiExplain.detail.field.mine"), value: userValue || t("common.unknown") },
    {
      label: t("aiExplain.detail.field.time"),
      value: meta.answered_at ? formatDateTime(meta.answered_at) : t("common.unknown"),
    },
    {
      label: t("aiExplain.detail.field.duration"),
      value: formatDuration(meta.time_spent_sec),
    },
    {
      label: t("aiExplain.detail.field.difficulty"),
      value: meta.difficulty_label || meta.difficulty || t("common.unknown"),
    },
  ];
  const resultLabel =
    meta.is_correct === undefined
      ? t("aiExplain.detail.result.unanswered")
      : meta.is_correct
      ? t("aiExplain.detail.result.correct")
      : t("aiExplain.detail.result.incorrect");

  async function handleGenerate() {
    if (!meta.question_id) return;
    setGenerateError(null);
    setIsGenerating(true);
    try {
      const response = await generateExplain({ questionId: meta.question_id, logId: meta.log_id });
      onQuotaUpdate(response.quota as AiExplainQuota | undefined);
      await onRefreshDetail();
    } catch (err) {
      if (
        err instanceof AxiosError &&
        err.response?.status === 429 &&
        err.response.data?.error === "ai_explain_quota_exceeded"
      ) {
        onQuotaUpdate(err.response.data.quota as AiExplainQuota | undefined);
        setGenerateError(t("aiExplain.detail.quotaExceeded"));
      } else {
        const message = err instanceof Error ? err.message : t("aiExplain.detail.errorUnknown");
        setGenerateError(message);
      }
    } finally {
      setIsGenerating(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="card-ambient rounded-3xl border border-white/10 bg-[#070f22]/60 px-5 py-4 space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-[11px] uppercase tracking-[0.3em] text-white/40">Question</p>
            <h2 className="text-xl font-semibold text-white">
              {meta.question_uid || `#${meta.question_id}`}
            </h2>
            <p className="text-sm text-white/50">
              {sectionLabel}
              {skillLabel ? ` · ${skillLabel}` : ""}
            </p>
          </div>
          <button type="button" className="btn-ghost self-start sm:self-auto" onClick={onBack}>
            返回列表
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className={`chip-soft ${meta.is_correct ? "chip-soft--success" : ""}`}>
            {resultLabel}
          </span>
        </div>
        <dl className="flex flex-wrap gap-3 text-xs text-white/50">
          {summaryFields.map((field) => (
            <div
              key={field.label}
              className="flex items-center gap-2 rounded-full border border-white/10 px-3 py-1"
            >
              <dt className="uppercase tracking-wide text-[10px] text-white/40">{field.label}</dt>
              <dd className="text-sm text-white/80 font-medium">{field.value}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="card-ambient rounded-3xl border border-white/10 bg-[#080f20]/95 p-6 space-y-5">
        {question.passage?.content_text ? (
          <div className="space-y-2">
            <p className="text-xs uppercase tracking-wide text-white/40">Passage</p>
            <HighlightedText
              text={question.passage.content_text}
              directives={combinedDirectives.filter((d) => d.target === "passage")}
              className="rounded-2xl border border-white/5 bg-white/5 p-4 text-white/80"
            />
          </div>
        ) : null}
        <div className="mt-4 space-y-3">
          <p className="text-xs uppercase tracking-wide text-white/40">Question</p>
          <HighlightedText
            text={question.stem_text}
            directives={combinedDirectives.filter((d) => d.target === "stem")}
            className="text-white text-lg font-semibold"
          />
        </div>
        <div className="mt-4 space-y-2">
          {Object.entries(question.choices).map(([choiceKey, text]) => {
            const isUser = userValue === choiceKey;
            const isCorrect = correctValue === choiceKey;
            return (
              <div
                key={choiceKey}
                className={`rounded-2xl border px-4 py-2 text-sm transition ${
                  isCorrect
                    ? "border-emerald-400/60 bg-emerald-500/10 text-emerald-100"
                    : isUser
                    ? "border-rose-400/60 bg-rose-500/10 text-rose-100"
                    : "border-white/10 bg-white/5 text-white/80"
                }`}
              >
                <span className="mr-3 font-semibold">{choiceKey}.</span>
                <HighlightedText
                  text={text}
                  directives={combinedDirectives.filter(
                    (d) => d.target === "choices" && d.choice_id === choiceKey
                  )}
                  className="inline"
                />
              </div>
            );
          })}
        </div>
      </div>

      {detail.text_explanation ? (
        <DashboardCard
          title="文本解析"
          subtitle="课堂讲义式说明，来自人工或题库备注"
          tone="subtle"
        >
          <p className="text-sm text-white/80 whitespace-pre-line">
            {detail.text_explanation}
          </p>
        </DashboardCard>
      ) : null}

      {aiExplanation ? (
        <ExplanationViewer
          explanation={aiExplanation}
          onDirectivesChange={onDirectivesChange}
          t={translator}
        />
      ) : (
        <div className="card-ambient space-y-3 rounded-2xl border border-white/10 bg-white/5 px-4 py-6 text-center text-white/70">
          <p>{t("aiExplain.detail.generatePrompt")}</p>
          <button
            type="button"
            className="btn-ghost px-4 py-2 text-sm"
            onClick={handleGenerate}
            disabled={isGenerating || quotaExhausted}
          >
            {isGenerating ? t("aiExplain.detail.generating") : t("aiExplain.detail.generate")}
          </button>
          {generateError && (
            <p className="text-xs text-rose-300">{generateError}</p>
          )}
          {quotaExhausted && !generateError && (
            <p className="text-xs text-amber-200">{t("aiExplain.detail.quotaExceeded")}</p>
          )}
        </div>
      )}
    </div>
  );
}

function QuotaNotice({
  quota,
  membership,
}: {
  quota?: AiExplainQuota | null;
  membership?: MembershipStatus | null;
}) {
  const { t } = useI18n();
  if (!quota) {
    return null;
  }
  if (quota.limit === null) {
    return (
      <div className="rounded-2xl border border-emerald-400/30 bg-emerald-500/5 px-4 py-2 text-sm text-emerald-100">
        {t("aiExplain.quota.unlimited")}
      </div>
    );
  }
  const remaining = Math.max(quota.limit - (quota.used ?? 0), 0);
  const resetsLabel = quota.resets_at
    ? new Date(quota.resets_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : null;
  return (
    <div
      className={`rounded-2xl border px-4 py-3 text-sm ${
        remaining > 0
          ? "border-white/15 bg-white/5 text-white/70"
          : "border-amber-400/40 bg-amber-500/10 text-amber-100"
      }`}
    >
      <p>
        {remaining > 0
          ? t("aiExplain.quota.remaining", { remaining, limit: quota.limit })
          : t("aiExplain.quota.exhausted")}
      </p>
      {resetsLabel && (
        <p className="text-xs text-white/40">{t("aiExplain.quota.resets", { time: resetsLabel })}</p>
      )}
      {remaining <= 0 && (
        <Link href="/settings" className="btn-ghost mt-3 inline-flex items-center justify-center gap-2 px-3 py-1 text-xs">
          {t("plan.locked.cta")}
        </Link>
      )}
    </div>
  );
}

function DetailSkeleton({ selected }: { selected: ExplainHistoryItem }) {
  const { t } = useI18n();
  return (
    <div className="space-y-5 animate-pulse">
      <div className="card-ambient rounded-2xl border border-white/10 bg-[#080f20]/80 px-5 py-4">
        <div className="h-4 w-24 rounded bg-white/5" />
        <div className="mt-3 h-6 w-40 rounded bg-white/5" />
        <div className="mt-2 h-4 w-56 rounded bg-white/5" />
      </div>
      <div className="card-ambient rounded-3xl border border-white/10 bg-[#080f20]/90 p-6 space-y-4">
        <div className="h-6 w-32 rounded bg-white/5" />
        <div className="h-20 rounded-2xl border border-white/5 bg-white/5" />
        <div className="space-y-2">
          {[0, 1, 2, 3].map((idx) => (
            <div key={idx} className="h-10 rounded-xl border border-white/5 bg-white/5" />
          ))}
        </div>
      </div>
      <div className="card-ambient rounded-2xl border border-white/10 bg-white/5 px-4 py-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2, 3, 4].map((idx) => (
            <div key={idx} className="h-12 rounded-xl border border-white/10 bg-white/5" />
          ))}
        </div>
      </div>
      <div className="card-ambient rounded-2xl border border-white/10 bg-white/5 px-4 py-6 text-center text-white/60">
        {t("aiExplain.detail.loading")}
      </div>
    </div>
  );
}

function HistoryPanel({
  items,
  loading,
  selected,
  onSelect,
  total,
  pagination,
  onPageChange,
}: {
  items: ExplainHistoryItem[];
  loading: boolean;
  selected: ExplainHistoryItem | null;
  onSelect: (item: ExplainHistoryItem) => void;
  total: number;
  pagination?: ExplainHistoryResponse["pagination"];
  onPageChange: (delta: number) => void;
}) {
  const { t } = useI18n();
  return (
    <div className="card-ambient rounded-3xl border border-white/10 bg-[#081126]">
      <div className="border-b border-white/5 px-4 py-3 text-xs uppercase tracking-wide text-white/50">
        {t("aiExplain.history.title", { count: total })}
      </div>
      <div className="max-h-[640px] overflow-y-auto p-3">
        {loading ? (
          <p className="text-sm text-white/60">{t("aiExplain.history.loading")}</p>
        ) : !items.length ? (
          <p className="text-sm text-white/60">{t("aiExplain.history.empty")}</p>
        ) : (
          <div className="space-y-3">
            {items.map((item) => {
              const isActive = selected?.log_id === item.log_id;
              return (
                <button
                  key={item.log_id}
                  type="button"
                  className={`w-full rounded-2xl border px-3 py-3 text-left transition ${
                    isActive
                      ? "border-white/60 bg-white/10 shadow-[0_0_25px_rgba(63,145,255,0.45)]"
                      : "border-white/10 bg-transparent hover:border-white/30 hover:bg-white/5"
                  }`}
                  onClick={() => onSelect(item)}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-white">
                        {item.question_uid || `#${item.question_id}`}
                      </p>
                      <p className="text-xs text-white/50">
                        {item.section}
                        {item.sub_section ? ` · ${item.sub_section}` : ""}
                      </p>
                    </div>
                    <span
                      className={`chip-soft text-[11px] ${
                        item.is_correct ? "chip-soft--success" : ""
                      }`}
                    >
                      {item.is_correct
                        ? t("aiExplain.detail.result.correct")
                        : t("aiExplain.detail.result.incorrect")}
                    </span>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-white/45">
                    <span>{formatDateTime(item.answered_at)}</span>
                    <span>·</span>
                    <span>{formatDuration(item.time_spent_sec)}</span>
                    <span className="chip-soft text-[10px] text-white/70">
                      ×{item.attempt_count}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
      {pagination && (
        <div className="flex items-center justify-between border-t border-white/5 px-4 py-3 text-sm text-white/60">
          <button
            type="button"
            className="btn-ghost px-3 py-1 text-xs"
            onClick={() => onPageChange(-1)}
            disabled={!pagination.has_prev}
          >
            {t("aiExplain.pagination.prev")}
          </button>
          <p>
            {t("aiExplain.pagination.pageInfo", {
              current: pagination.page,
              total: Math.max(pagination.pages, 1),
            })}
          </p>
          <button
            type="button"
            className="btn-ghost px-3 py-1 text-xs"
            onClick={() => onPageChange(1)}
            disabled={!pagination.has_next}
          >
            {t("aiExplain.pagination.next")}
          </button>
        </div>
      )}
    </div>
  );
}

function SearchCard({
  searchValue,
  onSearchChange,
}: {
  searchValue: string;
  onSearchChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
}) {
  const { t } = useI18n();
  return (
    <DashboardCard tone="subtle" title={t("aiExplain.search.title")} subtitle={t("aiExplain.search.subtitle")}>
      <label className="flex flex-col gap-2 text-sm text-white/70">
        <span className="text-xs uppercase text-white/40">{t("aiExplain.search.title")}</span>
        <input
          type="search"
          className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-white/80 placeholder:text-white/40"
          placeholder={t("aiExplain.search.placeholder")}
          value={searchValue}
          onChange={onSearchChange}
        />
      </label>
    </DashboardCard>
  );
}

function formatDateTime(value: string | number | Date | undefined | null): string {
  if (!value) {
    return "—";
  }
  try {
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) {
      return "—";
    }
    return new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  } catch {
    return "—";
  }
}

function formatDuration(value: number | null | undefined): string {
  if (!value || value <= 0) {
    return "—";
  }
  if (value < 60) {
    return `${value} 秒`;
  }
  const minutes = Math.floor(value / 60);
  const seconds = value % 60;
  if (seconds === 0) {
    return `${minutes} 分`;
  }
  return `${minutes} 分 ${seconds} 秒`;
}
