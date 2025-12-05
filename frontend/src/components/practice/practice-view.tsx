"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { DashboardCard } from "@/components/ui/dashboard-card";
import {
  abortSession,
  endSession,
  fetchExplanation,
  getActiveSession,
  startSession,
  submitAnswer,
} from "@/services/session";
import { getTodayPlan, startPlanTask } from "@/services/learning";
import { PlanTask, StudyPlanDetail } from "@/types/learning";
import {
  Session,
  SessionQuestion,
  QuestionFigureRef,
  SessionProgressEntry,
} from "@/types/session";
import { extractErrorMessage } from "@/lib/errors";
import { AxiosError } from "axios";
import { env } from "@/lib/env";
import { getClientToken } from "@/lib/auth-storage";
import { useI18n } from "@/hooks/use-i18n";
import { useAuthStore } from "@/stores/auth-store";

const API_BASE_URL = (env.apiBaseUrl || "").replace(/\/$/, "");

type ViewState = "prep" | "loading" | "active";

type PracticeViewProps = {
  planBlockId?: string;
  autoResumeDiagnostic?: boolean;
};

type StepDirective = {
  target: "passage" | "stem" | "choices" | "figure";
  text: string;
  action?: "highlight" | "underline" | "circle" | "strike" | "note" | "color" | "font";
  cue?: string;
  emphasis?: string;
  figure_id?: number | string;
  choice_id?: string | number;
};

type TranslateFn = ReturnType<typeof useI18n>["t"];

type AnimStep = {
  title?: string;
  type?: string;
  narration?: string | Record<string, string>;
  duration_ms?: number;
  delay_ms?: number;
  animations?: StepDirective[];
  board_notes?: string[];
};

type AnimExplanation = {
  protocol_version?: string;
  summary?: string;
  language?: string;
  steps?: AnimStep[];
};

type QuestionProgress = {
  isCorrect?: boolean;
  logId?: number;
  explanation?: AnimExplanation;
  revealedAnswer?: boolean;
  userChoice?: string | null;
};

const MIN_QUESTIONS = 1;
const DEFAULT_MAX_QUESTIONS = 12;

const keyForQuestion = (sessionId: number, questionId: number) =>
  `${sessionId}-${questionId}`;

export function PracticeView({ planBlockId, autoResumeDiagnostic = false }: PracticeViewProps = {}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const router = useRouter();
  const isPlanTaskMode = Boolean(planBlockId);
  const userId = useAuthStore((state) => state.user?.id);
  const initialViewState: ViewState = isPlanTaskMode || autoResumeDiagnostic ? "loading" : "prep";
  const [viewState, setViewState] = useState<ViewState>(initialViewState);
  const [session, setSession] = useState<Session | null>(null);
  const [activeSession, setActiveSession] = useState<Session | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedChoice, setSelectedChoice] = useState<string | null>(null);
  const [questionProgress, setQuestionProgress] = useState<
    Record<string, QuestionProgress>
  >({});
  const [prepConfig, setPrepConfig] = useState({ section: "RW", num_questions: 5 });
  const [planDetail, setPlanDetail] = useState<StudyPlanDetail | null>(null);
  const [planTasksMap, setPlanTasksMap] = useState<Record<string, PlanTask>>({});
  const [planError, setPlanError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [completionMessage, setCompletionMessage] = useState<string | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  const [isExplanationLoading, setExplanationLoading] = useState(false);
  const [maxQuestions, setMaxQuestions] = useState(DEFAULT_MAX_QUESTIONS);
  const [activeDirectives, setActiveDirectives] = useState<StepDirective[]>([]);
  const [mediaToken, setMediaToken] = useState<string | null>(null);
  const [isFinishDialogOpen, setFinishDialogOpen] = useState(false);
  const [isAbortDialogOpen, setAbortDialogOpen] = useState(false);
  const [isFinishing, setIsFinishing] = useState(false);
  const [isAborting, setIsAborting] = useState(false);
  const [planTask, setPlanTask] = useState<PlanTask | null>(null);
  const [hasAutoResumedDiagnostic, setHasAutoResumedDiagnostic] = useState(false);

  const pruneProgressForSession = useCallback((nextSession: Session) => {
    setQuestionProgress((prev) => {
      const allowed = new Set(
        nextSession.questions_assigned.map((question) =>
          keyForQuestion(nextSession.id, question.question_id)
        )
      );
      if (!Object.keys(prev).length) {
        return prev;
      }
      const nextEntries: Record<string, QuestionProgress> = {};
      Object.entries(prev).forEach(([key, value]) => {
        if (allowed.has(key)) {
          nextEntries[key] = value;
        }
      });
      return nextEntries;
    });
  }, []);
  const handleBackToPrep = useCallback(() => {
    if (session?.session_type === "diagnostic" || activeSession?.session_type === "diagnostic") {
      router.push("/diagnostic");
      return;
    }
    if (planBlockId) {
      router.push("/");
      return;
    }
    setViewState("prep");
  }, [session?.session_type, activeSession?.session_type, planBlockId, router]);

  const sectionOptions = useMemo(
    () => [
      {
        id: "RW",
        label: t("practice.section.rw.label"),
        helper: t("practice.section.rw.helper"),
        short: t("practice.section.rw.short"),
      },
      {
        id: "Math",
        label: t("practice.section.math.label"),
        helper: t("practice.section.math.helper"),
        short: t("practice.section.math.short"),
      },
    ],
    [t]
  );

  const diagnosticSessionActive =
    session?.session_type === "diagnostic" || activeSession?.session_type === "diagnostic";
  const isDiagnosticContext = autoResumeDiagnostic || diagnosticSessionActive;

  useEffect(() => {
    setPlanDetail(null);
    setPlanTasksMap({});
    if (!userId || isDiagnosticContext) {
      return;
    }
    let mounted = true;
    getTodayPlan()
      .then((payload) => {
        if (!mounted) return;
        const detail = payload.plan;
        setPlanDetail(detail);
        const targetQuestions = detail.target_questions ?? DEFAULT_MAX_QUESTIONS;
        const allowedMax = Math.max(DEFAULT_MAX_QUESTIONS, targetQuestions);
        setMaxQuestions(allowedMax);
        setPrepConfig((prev) => ({
          ...prev,
          num_questions: Math.min(
            Math.max(detail.target_questions ?? prev.num_questions, MIN_QUESTIONS),
            allowedMax
          ),
        }));
        const taskEntries: Record<string, PlanTask> = {};
        payload.tasks?.forEach((task) => {
          taskEntries[task.block_id] = task;
        });
        setPlanTasksMap(taskEntries);
        setPlanError(null);
      })
      .catch((err: unknown) => {
        if (!mounted) return;
        if (err instanceof AxiosError && err.response?.status === 428) {
          setPlanError(t("practice.plan.locked"));
          return;
        }
        setPlanError(t("practice.plan.fallback"));
      });
    return () => {
      mounted = false;
    };
  }, [t, userId, isDiagnosticContext]);

  useEffect(() => {
    if (planBlockId || !userId) {
      return;
    }
    let mounted = true;
    getActiveSession()
      .then(async (active) => {
        if (!mounted) return;
        const hasProgress = Boolean(active?.questions_done?.length);
        const isDiagnosticSession = active?.session_type === "diagnostic";
        if (active && !hasProgress && !isDiagnosticSession) {
          await abortSession(active.id).catch(() => undefined);
          if (!mounted) return;
          setActiveSession(null);
          return;
        }
        setActiveSession(active ?? null);
      })
      .catch(() => undefined);
    return () => {
      mounted = false;
    };
  }, [planBlockId, userId]);

  useEffect(() => {
    setMediaToken(getClientToken());
  }, []);

  const buildFigureSrc = useCallback(
    (url?: string) => {
      if (!url) return null;
      const absolute =
        url.startsWith("http://") || url.startsWith("https://")
          ? url
          : `${API_BASE_URL}${url}`;
      if (!mediaToken) {
        return absolute;
      }
      const separator = absolute.includes("?") ? "&" : "?";
      return `${absolute}${separator}token=${encodeURIComponent(mediaToken)}`;
    },
    [mediaToken]
  );

  const currentQuestion: SessionQuestion | undefined =
    session?.questions_assigned[currentIndex];

  const progressKey =
    session && currentQuestion
      ? keyForQuestion(session.id, currentQuestion.question_id)
      : null;
  const currentProgress = progressKey ? questionProgress[progressKey] : undefined;
  const explanation = currentProgress?.explanation;

  const currentSectionLine = useMemo(() => {
    if (!currentQuestion) {
      return "";
    }
    const baseLabel =
      currentQuestion.section === "Math"
        ? t("practice.section.math.short")
        : t("practice.section.rw.short");
    return currentQuestion.sub_section
      ? `${baseLabel} · ${currentQuestion.sub_section}`
      : baseLabel;
  }, [currentQuestion, t]);

  const questionReference = useMemo(() => {
    if (!currentQuestion) {
      return "";
    }
    const displayUid =
      currentQuestion.question_uid || `Q${String(currentQuestion.question_id).padStart(6, "0")}`;
    return `${displayUid} · #${currentQuestion.question_id}`;
  }, [currentQuestion]);

  const isQuestionUnavailable = Boolean(currentQuestion?.unavailable_reason);
  const questionUnavailableMessage = currentQuestion?.unavailable_reason
    ? t("practice.unavailable.message")
    : "";

  useEffect(() => {
    if (!explanation) {
      setActiveDirectives([]);
    }
  }, [explanation]);

useEffect(() => {
  if (!activeSession) {
    setAbortDialogOpen(false);
  }
}, [activeSession]);

  const passageDirectives = useMemo(
    () => activeDirectives.filter((d) => d.target === "passage"),
    [activeDirectives]
  );
  const stemDirectives = useMemo(
    () => activeDirectives.filter((d) => d.target === "stem"),
    [activeDirectives]
  );
  const choiceDirectives = useMemo(
    () => activeDirectives.filter((d) => d.target === "choices"),
    [activeDirectives]
  );
  const figureDirectives = useMemo(
    () => activeDirectives.filter((d) => d.target === "figure"),
    [activeDirectives]
  );

  const matchesChoiceDirective = useCallback((directive: StepDirective, key: string) => {
    if (!directive) return false;
    const normalizedKey = key.trim().toUpperCase();
    if (directive.choice_id !== undefined && directive.choice_id !== null) {
      const explicit = String(directive.choice_id).trim().toUpperCase();
      if (explicit) {
        return explicit === normalizedKey;
      }
    }
    const snippet = directive.text?.trim();
    if (!snippet) return false;
    const collapsed = snippet.replace(/[^A-Za-z0-9]/g, "").toUpperCase();
    if (!collapsed || collapsed.length > 12) {
      return false;
    }
    const patterns = [
      normalizedKey,
      `CHOICE${normalizedKey}`,
      `OPTION${normalizedKey}`,
      `${normalizedKey}CHOICE`,
      `${normalizedKey}OPTION`,
    ];
    return patterns.includes(collapsed);
  }, []);

  const hasChecked = Boolean(currentProgress?.logId);
  const isCorrect = currentProgress?.isCorrect;
  const revealedAnswer = currentProgress?.revealedAnswer;

  const sectionLabel = useMemo(() => {
    return sectionOptions.find((item) => item.id === prepConfig.section)?.short || "";
  }, [sectionOptions, prepConfig.section]);

  const planBlockDetail = useMemo(() => {
    if (!planBlockId || !planDetail?.blocks) {
      return null;
    }
    return planDetail.blocks.find((block) => block.block_id === planBlockId) ?? null;
  }, [planBlockId, planDetail]);

  const planTaskProgress = useMemo(() => {
    if (!isPlanTaskMode) {
      return null;
    }
    const completed =
      session?.questions_done?.length ??
      planTask?.questions_completed ??
      planTasksMap[planBlockId || ""]?.questions_completed ??
      0;
    const total =
      planTask?.questions_target ??
      planBlockDetail?.questions ??
      session?.questions_assigned.length ??
      planTasksMap[planBlockId || ""]?.questions_target ??
      0;
    return { completed, total };
  }, [isPlanTaskMode, planTask, planTasksMap, planBlockDetail, planBlockId, session]);

  const attemptStart = useCallback(async (): Promise<boolean> => {
    if (planBlockId) {
      return false;
    }
    const clampedCount = Math.min(
      Math.max(Number(prepConfig.num_questions), MIN_QUESTIONS),
      maxQuestions
    );
    let safetyCounter = 0;
    while (safetyCounter < 100) {
      try {
        const newSession = await startSession({
          num_questions: clampedCount,
          section: prepConfig.section || undefined,
        });
        setSession(newSession);
        setQuestionProgress({});
        setCurrentIndex(0);
        setSelectedChoice(null);
        setActiveDirectives([]);
        setViewState("active");
        setActiveSession(null);
        return true;
      } catch (err: unknown) {
        if (err instanceof AxiosError && err.response?.status === 409) {
          const conflict = err.response.data?.session as Session | undefined;
          const hasProgress = Boolean(conflict?.questions_done?.length);
          if (conflict && !hasProgress) {
            await abortSession(conflict.id).catch(() => undefined);
            setActiveSession(null);
            safetyCounter += 1;
            continue;
          }
          if (conflict) {
            setActiveSession(conflict);
          }
          setError(t("practice.error.activeSession"));
        } else {
          setError(extractErrorMessage(err, t("practice.error.start")));
        }
        setViewState("prep");
        return false;
      }
    }
    setError(t("practice.error.activeSession"));
    setViewState("prep");
    return false;
  }, [planBlockId, prepConfig.num_questions, prepConfig.section, maxQuestions, t]);

  async function handleStart(e: React.FormEvent) {
    e.preventDefault();
    if (planBlockId) return;
    setCompletionMessage(null);
    setError(null);
    setViewState("loading");
    await attemptStart();
  }

  async function handleCheckAnswer() {
    if (!session || !currentQuestion || !selectedChoice || !progressKey) return;
    setIsChecking(true);
    setError(null);
    try {
      const response = await submitAnswer({
        session_id: session.id,
        question_id: currentQuestion.question_id,
        user_answer: { value: selectedChoice },
      });
      setQuestionProgress((prev) => ({
        ...prev,
        [progressKey]: {
          ...prev[progressKey],
          isCorrect: response.is_correct,
          logId: response.log_id,
          userChoice: selectedChoice,
        },
      }));
    } catch (err: unknown) {
      if (err instanceof AxiosError && err.response?.status === 409) {
        const payload = err.response.data;
        if (payload?.error === "question_reassigned" && payload.session) {
          const refreshed = payload.session as Session;
          setSession(refreshed);
          pruneProgressForSession(refreshed);
          setCurrentIndex((prev) =>
            Math.min(prev, Math.max(refreshed.questions_assigned.length - 1, 0))
          );
          setSelectedChoice(null);
          setError(t("practice.error.questionReassigned"));
          setViewState("active");
          return;
        }
        if (payload?.error === "question_unavailable") {
          setSession(null);
          setViewState("prep");
          setError(t("practice.error.questionUnavailable"));
          return;
        }
      }
      setError(extractErrorMessage(err, t("practice.error.check")));
    } finally {
      setIsChecking(false);
    }
  }

  async function handleViewExplanation() {
    if (!session || !currentQuestion || !progressKey || explanation) return;
    setExplanationLoading(true);
    setError(null);
    try {
    const payload = (await fetchExplanation({
        session_id: session.id,
        question_id: currentQuestion.question_id,
    })) as AnimExplanation;
      setQuestionProgress((prev) => {
        const existing = prev[progressKey];
        return {
          ...prev,
          [progressKey]: existing
            ? { ...existing, explanation: payload }
            : {
                isCorrect: false,
                logId: 0,
                explanation: payload,
                userChoice: selectedChoice,
              },
        };
      });
    } catch (err: unknown) {
      setError(extractErrorMessage(err, t("practice.error.explanation")));
    } finally {
      setExplanationLoading(false);
    }
  }

  const goalSummary =
    planDetail?.target_questions !== undefined
      ? t("practice.goalSummary.value", { count: planDetail.target_questions })
      : t("practice.goalSummary.custom");
  const summaryStats = [
    {
      label: t("practice.summary.section"),
      value:
        sectionOptions.find((opt) => opt.id === prepConfig.section)?.label ??
        prepConfig.section,
    },
    {
      label: t("practice.summary.target"),
      value: goalSummary,
    },
  ];
  const activeTotalQuestions = activeSession?.questions_assigned.length ?? 0;
  const activeCompleted = activeSession?.questions_done?.length ?? 0;
  const activeRemaining = Math.max(activeTotalQuestions - activeCompleted, 0);
  const localSessionStats = useMemo(() => {
    if (!session) {
      return { total: 0, completed: 0, remaining: 0 };
    }
    const total = session.questions_assigned.length;
    const completed = session.questions_assigned.reduce((count, question) => {
      const key = keyForQuestion(session.id, question.question_id);
      return questionProgress[key]?.logId ? count + 1 : count;
    }, 0);
    return { total, completed, remaining: Math.max(total - completed, 0) };
  }, [session, questionProgress]);

  const buildProgressMapFromEntries = useCallback(
    (sourceSession: Session) => {
      const map: Record<string, QuestionProgress> = {};
      (sourceSession.questions_done ?? []).forEach((entry: SessionProgressEntry) => {
        if (!entry.question_id) return;
        const key = keyForQuestion(sourceSession.id, entry.question_id);
        map[key] = {
          isCorrect: entry.is_correct ?? undefined,
          logId: entry.log_id,
          userChoice: entry.user_answer?.value ?? null,
          revealedAnswer: entry.is_correct !== undefined,
        };
      });
      return map;
    },
    []
  );

  const findFirstIncompleteIndex = useCallback(
    (targetSession: Session, progress: Record<string, QuestionProgress>) => {
      for (let i = 0; i < targetSession.questions_assigned.length; i += 1) {
        const q = targetSession.questions_assigned[i];
        const key = keyForQuestion(targetSession.id, q.question_id);
        if (!progress[key]) {
          return i;
        }
      }
      return Math.max(targetSession.questions_assigned.length - 1, 0);
    },
    []
  );

  const goToQuestion = useCallback(
    (index: number) => {
      if (!session || session.questions_assigned.length === 0) return;
      const clamped = Math.max(0, Math.min(index, session.questions_assigned.length - 1));
      setCurrentIndex(clamped);
      const question = session.questions_assigned[clamped];
      if (!question) {
        setSelectedChoice(null);
        return;
      }
      const key = keyForQuestion(session.id, question.question_id);
      const existing = questionProgress[key];
      setSelectedChoice(existing?.userChoice ?? null);
      setActiveDirectives([]);
    },
    [session, questionProgress]
  );

  const resumeFromSession = useCallback(
    (saved: Session) => {
      if (!saved.questions_assigned.length) {
        return;
      }
      const progress = buildProgressMapFromEntries(saved);
      const nextIndex = findFirstIncompleteIndex(saved, progress);
      setSession(saved);
      setQuestionProgress(progress);
      setViewState("active");
      setCurrentIndex(nextIndex);
      const nextQuestion = saved.questions_assigned[nextIndex];
      if (nextQuestion) {
        const key = keyForQuestion(saved.id, nextQuestion.question_id);
        setSelectedChoice(progress[key]?.userChoice ?? null);
      } else {
        setSelectedChoice(null);
      }
      setActiveDirectives([]);
      setActiveSession(null);
    },
    [buildProgressMapFromEntries, findFirstIncompleteIndex]
  );

  useEffect(() => {
    if (!planBlockId) {
      return;
    }
    let cancelled = false;
    setError(null);
    setCompletionMessage(null);
    setPlanTask(null);
    setViewState("loading");
    startPlanTask(planBlockId)
      .then(({ session: newSession, task }) => {
        if (cancelled) return;
        setPlanTask(task);
        resumeFromSession(newSession);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof AxiosError && err.response?.status === 400) {
          const payload = err.response.data;
          if (payload?.error === "no_questions_for_block") {
            setError(t("practice.error.planBlockEmpty"));
          } else {
            setError(extractErrorMessage(err, t("practice.error.start")));
          }
        } else {
          setError(extractErrorMessage(err, t("practice.error.start")));
        }
        setViewState("prep");
      });
    return () => {
      cancelled = true;
    };
  }, [planBlockId, resumeFromSession, t]);

  const handleAbortActiveSession = useCallback(async () => {
    if (!activeSession) {
      setAbortDialogOpen(false);
      return;
    }
    setIsAborting(true);
    try {
      await abortSession(activeSession.id);
      setActiveSession(null);
    } finally {
      setIsAborting(false);
      setAbortDialogOpen(false);
    }
  }, [activeSession]);

  const handleFinishSession = useCallback(async () => {
    if (!session) return;
    setIsFinishing(true);
    try {
      await endSession(session.id).catch(() => undefined);
      setSession(null);
      setQuestionProgress({});
      setSelectedChoice(null);
      setActiveDirectives([]);
      setViewState(isPlanTaskMode ? "loading" : "prep");
      setCompletionMessage(t("practice.session.complete"));
      setActiveSession(null);
      setCurrentIndex(0);
      if (isPlanTaskMode) {
        setPlanTask((prev) =>
          prev
            ? { ...prev, status: "completed", questions_completed: prev.questions_target }
            : prev
        );
        if (userId) {
          await queryClient
            .invalidateQueries({ queryKey: ["plan-today", userId] })
            .catch(() => undefined);
        }
        router.push("/");
      }
    } finally {
      setIsFinishing(false);
      setFinishDialogOpen(false);
    }
  }, [session, isPlanTaskMode, t, queryClient, router, userId]);

  const handleSelectChoice = useCallback(
    (choiceKey: string) => {
      if (currentQuestion?.unavailable_reason) {
        return;
      }
      setSelectedChoice(choiceKey);
      if (!session || !currentQuestion) return;
      const key = keyForQuestion(session.id, currentQuestion.question_id);
      setQuestionProgress((prev) => ({
        ...prev,
        [key]: {
          ...prev[key],
          userChoice: choiceKey,
        },
      }));
    },
    [session, currentQuestion]
  );

  useEffect(() => {
    if (!autoResumeDiagnostic || hasAutoResumedDiagnostic) {
      return;
    }
    if (activeSession && activeSession.session_type === "diagnostic") {
      resumeFromSession(activeSession);
      setHasAutoResumedDiagnostic(true);
    }
  }, [autoResumeDiagnostic, hasAutoResumedDiagnostic, activeSession, resumeFromSession]);

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6 lg:px-0">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        {isPlanTaskMode ? (
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-sm font-semibold text-white/80 transition hover:text-white"
          >
            <span aria-hidden="true">←</span>
            {t("practice.nav.backPlan")}
          </Link>
        ) : (
          <>
            {viewState === "prep" ? (
              (() => {
                const isDiagnosticContext =
                  session?.session_type === "diagnostic" || activeSession?.session_type === "diagnostic";
                if (isDiagnosticContext) {
                  return (
                    <Link
                      href="/diagnostic"
                      className="inline-flex items-center gap-2 text-sm font-semibold text-white/80 transition hover:text-white"
                    >
                      <span aria-hidden="true">←</span>
                      {t("diagnostic.nav.back")}
                    </Link>
                  );
                }
                return (
                  <Link
                    href="/"
                    className="inline-flex items-center gap-2 text-sm font-semibold text-white/80 transition hover:text-white"
                  >
                    <span aria-hidden="true">←</span>
                    {t("practice.nav.back")}
                  </Link>
                );
              })()
            ) : (
              <button
                type="button"
                onClick={handleBackToPrep}
                className="inline-flex items-center gap-2 text-sm font-semibold text-white/80 transition hover:text-white"
              >
                <span aria-hidden="true">←</span>
                {session?.session_type === "diagnostic" || activeSession?.session_type === "diagnostic"
                  ? t("diagnostic.nav.back")
                  : t("practice.nav.backPrep")}
              </button>
            )}
          </>
        )}
        <div className="flex flex-wrap gap-3">
          {summaryStats.map((stat) => (
            <div key={stat.label} className="stat-pill min-w-[140px] text-white">
              <p className="text-[11px] uppercase tracking-wide text-white/60">{stat.label}</p>
              <p className="text-base font-semibold">{stat.value}</p>
            </div>
          ))}
        </div>
      </div>
      <div className="flex flex-col gap-6 lg:grid lg:grid-cols-[minmax(0,1fr)_360px] lg:items-start">
        <div className="space-y-6">
          {isPlanTaskMode && planBlockDetail && (
            <DashboardCard
              title={t("practice.planTask.title")}
              subtitle={planBlockDetail.focus_skill_label ?? planBlockDetail.focus_skill}
            >
              <p className="text-sm text-white/70">
                {t("practice.planTask.meta", {
                  section: planBlockDetail.section,
                  minutes: planBlockDetail.minutes,
                  questions: planBlockDetail.questions,
                })}
              </p>
              {planTaskProgress ? (
                <p className="mt-2 text-sm font-semibold text-white">
                  {t("practice.planTask.progress", {
                    completed: planTaskProgress.completed,
                    total: planTaskProgress.total,
                  })}
                </p>
              ) : null}
            </DashboardCard>
          )}
      {!isPlanTaskMode && viewState === "prep" && session && (
        <DashboardCard
          title={t("practice.resume.title")}
          subtitle={t("practice.resume.subtitle", { remaining: localSessionStats.remaining })}
        >
          <div className="space-y-3 text-sm text-white/80">
            <p>
              {t("practice.resume.detail", {
                completed: localSessionStats.completed,
                total: localSessionStats.total,
              })}
            </p>
            <div className="flex flex-wrap gap-3">
              <button
                className="btn-cta px-4 py-2 text-sm"
                onClick={() => setViewState("active")}
              >
                {t("practice.resume.continue")}
              </button>
              <button
                className="btn-ghost px-4 py-2 text-sm"
                onClick={() => setFinishDialogOpen(true)}
              >
                {t("practice.resume.discard")}
              </button>
            </div>
          </div>
        </DashboardCard>
      )}
      {!isPlanTaskMode && viewState === "prep" && activeSession && !session && (
        <DashboardCard
          title={t("practice.resume.title")}
          subtitle={t("practice.resume.subtitle", { remaining: activeRemaining })}
        >
          <div className="space-y-3 text-sm text-white/80">
            <p>
              {t("practice.resume.detail", {
                completed: activeCompleted,
                total: activeTotalQuestions,
              })}
            </p>
            <div className="flex flex-wrap gap-3">
              <button
                className="btn-cta px-4 py-2 text-sm"
                onClick={() => resumeFromSession(activeSession)}
              >
                {t("practice.resume.continue")}
              </button>
              <button
                className="btn-ghost px-4 py-2 text-sm"
                onClick={() => setAbortDialogOpen(true)}
                disabled={isAborting}
              >
                {t("practice.resume.discard")}
              </button>
            </div>
          </div>
        </DashboardCard>
      )}
      {!isPlanTaskMode && viewState !== "active" && (
        <DashboardCard
          title={t("practice.getReady.title")}
          subtitle={t("practice.getReady.subtitle")}
        >
          <form className="space-y-4" onSubmit={handleStart}>
            <div className="grid gap-3 sm:grid-cols-2">
              {sectionOptions.map((option) => {
                const isActive = prepConfig.section === option.id;
                return (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() =>
                      setPrepConfig((prev) => ({ ...prev, section: option.id }))
                    }
                    className={`card-ambient border px-4 py-3 text-left transition ${
                      isActive
                        ? "border-white/70 bg-white/10 text-white shadow-lg shadow-white/10"
                        : "border-white/10 bg-transparent text-white/70 hover:border-white/30"
                    }`}
                  >
                    <p className="text-sm font-semibold">{option.label}</p>
                    <p className="text-xs text-white/60">{option.helper}</p>
                  </button>
                );
              })}
            </div>
            <div className="card-ambient flex items-center justify-between rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm">
              <div>
                <p className="text-white/70">{t("practice.questionCount.label")}</p>
                <p className="text-white text-lg font-semibold">{prepConfig.num_questions}</p>
                <p className="text-xs text-white/50">
                  {t("practice.questionCount.goal", { goal: goalSummary })}
                  {planError && <span className="text-red-300"> · {planError}</span>}
                </p>
                <p className="text-xs text-white/40">
                  {t("practice.questionCount.range", {
                    min: MIN_QUESTIONS,
                    max: maxQuestions,
                  })}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="btn-circle text-lg"
                  onClick={() =>
                    setPrepConfig((prev) => ({
                      ...prev,
                      num_questions: Math.max(MIN_QUESTIONS, prev.num_questions - 1),
                    }))
                  }
                >
                  –
                </button>
                <button
                  type="button"
                  className="btn-circle text-lg"
                  onClick={() =>
                    setPrepConfig((prev) => ({
                      ...prev,
                      num_questions: Math.min(maxQuestions, prev.num_questions + 1),
                    }))
                  }
                >
                  +
                </button>
              </div>
            </div>
            <button
              type="submit"
              disabled={viewState === "loading"}
              className="btn-cta w-full justify-center"
            >
              {viewState === "loading"
                ? t("practice.button.startLoading")
                : t("practice.button.start")}
            </button>
            {completionMessage && (
              <p className="text-sm text-emerald-300">{completionMessage}</p>
            )}
            {error && viewState !== "active" && (
              <p className="text-sm text-red-400">{error}</p>
            )}
          </form>
        </DashboardCard>
      )}

      {viewState === "active" && currentQuestion && session && (
        <DashboardCard
          title={t("practice.question.heading", {
            current: currentIndex + 1,
            total: session.questions_assigned.length,
          })}
          subtitle={
            <span className="flex flex-wrap items-center gap-3">
              <span>{sectionLabel}</span>
              <span className="text-[11px] uppercase tracking-wide text-white/40">
                {t("practice.meta.questionId", { id: questionReference || "—" })}
              </span>
              {session?.session_type === "diagnostic" && (
                <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-amber-200">
                  {t("diagnostic.badge.active")}
                </span>
              )}
            </span>
          }
          tone="subtle"
        >
        <div className="mb-4 flex items-center justify-between text-xs text-white/60">
          <button
            type="button"
            className="btn-ghost px-3 py-1 text-xs font-semibold disabled:opacity-30"
            onClick={() => goToQuestion(currentIndex - 1)}
            disabled={!session || currentIndex === 0}
          >
            ← {t("practice.nav.prev")}
          </button>
          <span>
            {t("practice.nav.counter", {
              current: currentIndex + 1,
              total: session.questions_assigned.length,
            })}
          </span>
          <button
            type="button"
            className="btn-ghost px-3 py-1 text-xs font-semibold disabled:opacity-30"
            onClick={() => goToQuestion(currentIndex + 1)}
            disabled={!session || currentIndex >= session.questions_assigned.length - 1}
          >
            {t("practice.nav.next")} →
          </button>
        </div>
            <div className="space-y-4">
            <div className="card-ambient space-y-4 rounded-2xl border border-white/10 bg-white/5 p-5">
              {currentQuestion.figures?.length ? (
                <div className="space-y-4">
                  {currentQuestion.figures.map((figure) => {
                    const src = buildFigureSrc(figure.url);
                    if (!src) return null;
                    const directivesForFigure = figureDirectives.filter((directive) => {
                      if (directive.figure_id === undefined || directive.figure_id === null || directive.figure_id === "") {
                        return true;
                      }
                      return String(directive.figure_id) === String(figure.id);
                    });
                    return (
                      <FigureReference
                        key={figure.id}
                        figure={figure}
                        imageSrc={src}
                        directives={directivesForFigure}
                        t={t}
                      />
                    );
                  })}
                </div>
              ) : currentQuestion.has_figure ? (
                <div className="card-ambient rounded-xl border border-amber-400/40 bg-amber-500/10 p-3 text-xs text-amber-100">
                  {t("practice.figure.missing")}
                </div>
              ) : null}

              {currentQuestion.passage?.content_text && (
                <HighlightedText
                  text={currentQuestion.passage.content_text}
                  directives={passageDirectives}
                  className="max-h-72 overflow-auto rounded-xl border border-white/5 bg-[#0b1528] p-4 text-base text-white/80 whitespace-pre-wrap"
                />
              )}

              <div>
                <p className="text-xs uppercase text-white/50">
                  {currentSectionLine}
                </p>
                <HighlightedText
                  text={currentQuestion.stem_text}
                  directives={stemDirectives}
                  className="text-white text-base font-semibold whitespace-pre-wrap"
                />
              </div>
              {isQuestionUnavailable && questionUnavailableMessage && (
                <div className="rounded-xl border border-amber-400/40 bg-amber-500/10 p-3 text-sm text-amber-100">
                  {questionUnavailableMessage}
                </div>
              )}
            </div>
            <div className="space-y-2">
              {Object.entries(currentQuestion.choices).map(([key, text]) => {
                const wholeChoiceDirectives = choiceDirectives.filter((directive) =>
                  matchesChoiceDirective(directive, key)
                );
                const snippetDirectives = choiceDirectives.filter((directive) => {
                  if (matchesChoiceDirective(directive, key)) {
                    return false;
                  }
                  const snippet = directive.text?.trim();
                  if (!snippet) {
                    return false;
                  }
                  const normalizedSnippet = snippet.replace(/[^A-Za-z0-9]/g, "");
                  if (normalizedSnippet && normalizedSnippet.length <= 1) {
                    return false;
                  }
                  return text.toLowerCase().includes(snippet.toLowerCase());
                });
                const strikeChoice = wholeChoiceDirectives.some((directive) => directive.action === "strike");
                const noteChoice = wholeChoiceDirectives.some((directive) => directive.action === "note");
                const highlightChoice = wholeChoiceDirectives.some(
                  (directive) => !strikeChoice && directive.action !== "note"
                );
                const isChoiceEmphasized = strikeChoice || noteChoice || highlightChoice;
                return (
                  <button
                    key={key}
                    onClick={() => handleSelectChoice(key)}
                    disabled={isQuestionUnavailable}
                    className={`w-full rounded-xl border px-4 py-2 text-left text-sm transition ${
                      isQuestionUnavailable
                        ? "cursor-not-allowed opacity-50"
                        :
                      selectedChoice === key
                        ? "border-white/80 text-white"
                        : hasChecked && currentProgress?.isCorrect && currentProgress?.userChoice === key
                        ? "border-emerald-400 text-emerald-200 bg-emerald-500/10"
                        : hasChecked && currentProgress?.userChoice === key && !currentProgress?.isCorrect
                        ? "border-rose-500 text-rose-100 bg-rose-500/10"
                        : isChoiceEmphasized
                        ? strikeChoice
                          ? "border-rose-500 text-white line-through decoration-rose-300 bg-rose-500/10 shadow-[0_0_0_1px_rgba(248,113,113,0.5)]"
                          : "border-amber-400 text-white shadow-[0_0_0_1px_rgba(251,191,36,0.4)] bg-amber-400/5"
                        : "border-white/15 text-white/70 hover:border-white/40"
                    }`}
                  >
                    <span className="mr-3 font-semibold">{key}.</span>
                    <HighlightedText
                      text={text}
                      directives={snippetDirectives}
                      className="inline whitespace-pre-wrap text-sm"
                    />
                  </button>
                );
              })}
            </div>
              <div className="card-ambient space-y-3 rounded-2xl border border-white/15 bg-white/5 p-4 text-sm">
              <div className="flex flex-col gap-1">
                {hasChecked ? (
                  <>
                    <p
                      className={`font-semibold ${
                        isCorrect ? "text-emerald-200" : "text-rose-300"
                      }`}
                    >
                      {isCorrect ? t("practice.result.correct") : t("practice.result.incorrect")}
                    </p>
                    <p className="text-xs text-white/60">{t("practice.result.subtitle")}</p>
                  </>
                ) : (
                  <p className="text-white/70">{t("practice.prompt.pending")}</p>
                )}
              </div>
              {!hasChecked ? (
                <div className="flex flex-wrap gap-3">
                  <button
                    className="btn-cta px-4 py-2 text-sm disabled:opacity-40"
                    disabled={!selectedChoice || isChecking || isQuestionUnavailable}
                    onClick={handleCheckAnswer}
                  >
                    {isChecking ? t("practice.button.checking") : t("practice.button.check")}
                  </button>
                </div>
              ) : (
                <div className="flex flex-wrap gap-3">
                  <button
                    className="btn-ghost px-4 py-2 text-sm disabled:opacity-40"
                    disabled={Boolean(explanation) || isExplanationLoading}
                    onClick={handleViewExplanation}
                  >
                    {explanation
                      ? t("practice.button.explanation.ready")
                      : isExplanationLoading
                      ? t("practice.button.explanation.loading")
                      : t("practice.button.explanation.generate")}
                  </button>
                  <button
                    className="btn-ghost px-4 py-2 text-sm"
                    onClick={() =>
                      currentIndex + 1 >= session.questions_assigned.length
                        ? setFinishDialogOpen(true)
                        : goToQuestion(currentIndex + 1)
                    }
                  >
                    {currentIndex + 1 >= session.questions_assigned.length
                      ? t("practice.button.finish")
                      : t("practice.button.next")}
                  </button>
                </div>
              )}
              {!revealedAnswer && hasChecked ? (
                <button
                  className="btn-ghost w-full border border-emerald-400/60 text-sm text-emerald-200 hover:bg-emerald-400/10"
                  onClick={() => {
                    if (!progressKey || !session || !currentQuestion) return;
                    setQuestionProgress((prev) => {
                      const existing = prev[progressKey];
                      if (!existing) return prev;
                      return {
                        ...prev,
                        [progressKey]: {
                          ...existing,
                          revealedAnswer: true,
                          userChoice: existing.userChoice ?? selectedChoice,
                        },
                      };
                    });
                  }}
                >
                  {t("practice.button.showAnswer")}
                </button>
              ) : null}
              {revealedAnswer && (
                <div className="rounded-xl border border-emerald-400/40 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-100">
                  <span>{t("practice.correctAnswer.prefix")}</span>{" "}
                  <span className="font-semibold text-emerald-200">
                    {currentQuestion.correct_answer?.value ??
                      t("practice.correctAnswer.unknown")}
                  </span>
                </div>
              )}
            </div>
            {error && viewState === "active" && (
              <p className="text-sm text-red-400">{error}</p>
            )}
          </div>
        </DashboardCard>
      )}
        </div>

        <aside className="w-full space-y-4 lg:sticky lg:top-16">
          <DashboardCard
            title={t("practice.strategy.title")}
            subtitle={t("practice.strategy.subtitle")}
            tone="subtle"
          >
            {isExplanationLoading && !explanation ? (
              <p className="text-sm text-white/70">{t("practice.strategy.loading")}</p>
            ) : explanation ? (
              <ExplanationViewer
                explanation={explanation}
                onDirectivesChange={setActiveDirectives}
                t={t}
              />
            ) : (
              <p className="text-sm text-white/70">{t("practice.strategy.empty")}</p>
            )}
          </DashboardCard>
        </aside>
      </div>
      {isFinishDialogOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[#050E1F]/80 px-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="w-full max-w-md rounded-2xl border border-white/10 bg-[#050E1F] p-6 shadow-2xl">
            <h3 className="text-lg font-semibold text-white">
              {t("practice.finish.confirm.title")}
            </h3>
            <p className="mt-2 text-sm text-white/70">
              {t("practice.finish.confirm.description")}
            </p>
            <div className="mt-6 flex flex-col gap-3 sm:flex-row">
              <button
                className="flex-1 rounded-xl border border-white/30 px-4 py-2 text-sm text-white transition hover:border-white/60"
                onClick={() => setFinishDialogOpen(false)}
                disabled={isFinishing}
              >
                {t("practice.finish.confirm.cancel")}
              </button>
              <button
                className="flex-1 rounded-xl bg-rose-500/80 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-rose-500/30 transition hover:bg-rose-500 disabled:opacity-50"
                onClick={handleFinishSession}
                disabled={isFinishing}
              >
                {isFinishing
                  ? t("practice.button.finishing")
                  : t("practice.finish.confirm.confirm")}
              </button>
            </div>
          </div>
        </div>
      )}
      {isAbortDialogOpen && activeSession && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[#050E1F]/80 px-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="w-full max-w-md rounded-2xl border border-white/10 bg-[#050E1F] p-6 shadow-2xl">
            <h3 className="text-lg font-semibold text-white">
              {t("practice.abort.confirm.title")}
            </h3>
            <p className="mt-2 text-sm text-white/70">
              {t("practice.abort.confirm.description")}
            </p>
            <div className="mt-6 flex flex-col gap-3 sm:flex-row">
              <button
                className="flex-1 rounded-xl border border-white/30 px-4 py-2 text-sm text-white transition hover:border-white/60"
                onClick={() => setAbortDialogOpen(false)}
                disabled={isAborting}
              >
                {t("practice.abort.confirm.cancel")}
              </button>
              <button
                className="flex-1 rounded-xl bg-rose-500/80 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-rose-500/30 transition hover:bg-rose-500 disabled:opacity-50"
                onClick={handleAbortActiveSession}
                disabled={isAborting}
              >
                {isAborting
                  ? t("practice.button.aborting")
                  : t("practice.abort.confirm.confirm")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function FigureReference({
  figure,
  imageSrc,
  directives,
  t,
}: {
  figure: QuestionFigureRef;
  imageSrc: string;
  directives: StepDirective[];
  t: TranslateFn;
}) {
  const showOverlay = directives.length > 0;
  const cueList = directives.filter((d) => d.cue || d.text);
  return (
    <figure className="space-y-2">
      <div className="relative overflow-hidden rounded-xl border border-white/10 bg-black/30 p-3">
        <img
          src={imageSrc}
          alt={figure.description || t("practice.figure.altFallback")}
          className="max-h-[340px] w-full object-contain"
        />
        {showOverlay &&
          directives.map((directive, index) => (
            <div
              key={`${figure.id}-${index}`}
              className="pointer-events-none absolute inset-0 rounded-xl border-2 border-emerald-300/70 bg-emerald-400/10/60 animate-pulse"
              title={directive.cue || undefined}
            />
          ))}
      </div>
      {figure.description ? (
        <figcaption className="text-xs text-white/60">{figure.description}</figcaption>
      ) : null}
      {cueList.length ? (
        <ul className="space-y-1 text-xs text-white/60">
          {cueList.map((directive, idx) => (
            <li key={`cue-${figure.id}-${idx}`} className="rounded bg-white/5 px-2 py-1">
              {directive.cue || directive.text}
            </li>
          ))}
        </ul>
      ) : null}
    </figure>
  );
}

function HighlightedText({
  text,
  directives,
  className,
}: {
  text?: string | null;
  directives: StepDirective[];
  className?: string;
}) {
  const nodes = useMemo<ReactNode[]>(() => {
    if (!text) return [];
    let remaining = text;
    let keyCounter = 0;
    const segments: ReactNode[] = [];
    const usable = directives.filter((d) => (d.text || "").trim().length > 0);
    const pushText = (value: string) => {
      if (!value) return;
      keyCounter += 1;
      segments.push(
        <span key={`txt-${keyCounter}`} className="whitespace-pre-wrap">
          {value}
        </span>
      );
    };
    if (!usable.length) {
      pushText(text);
      return segments;
    }
    usable.forEach((directive) => {
      const snippet = directive.text.trim();
      if (!snippet) {
        return;
      }
      const lowerRemaining = remaining.toLowerCase();
      const matchIndex = lowerRemaining.indexOf(snippet.toLowerCase());
      if (matchIndex === -1) {
        return;
      }
      const before = remaining.slice(0, matchIndex);
      pushText(before);
      const matchText = remaining.slice(matchIndex, matchIndex + snippet.length);
      const styleClass = getDirectiveClass(directive.action);
      keyCounter += 1;
      segments.push(
        <mark
          key={`mark-${keyCounter}`}
          className={`rounded px-0.5 text-white ${styleClass}`}
          style={directive.emphasis ? { color: directive.emphasis } : undefined}
          title={directive.cue}
        >
          {matchText}
        </mark>
      );
      remaining = remaining.slice(matchIndex + snippet.length);
    });
    pushText(remaining);
    return segments;
  }, [text, directives]);

  if (!text) {
    return null;
  }
  return <div className={className}>{nodes}</div>;
}

function getDirectiveClass(action?: string) {
  switch (action) {
    case "underline":
      return "underline decoration-amber-300";
    case "circle":
      return "outline outline-2 outline-amber-300 rounded-full";
    case "strike":
      return "line-through decoration-rose-300";
    case "note":
      return "bg-emerald-400/30 text-emerald-100";
    case "color":
      return "bg-transparent";
    case "font":
      return "italic text-sky-200";
    default:
      return "bg-amber-300/40";
  }
}

/* eslint-disable react-hooks/set-state-in-effect */
function ExplanationViewer({
  explanation,
  onDirectivesChange,
  t,
}: {
  explanation: AnimExplanation;
  onDirectivesChange: (directives: StepDirective[]) => void;
  t: TranslateFn;
}) {
  const rawSteps: AnimStep[] = useMemo(() => explanation.steps ?? [], [explanation]);
  const steps: AnimStep[] = useMemo(() => {
    if (!explanation.summary) {
      return rawSteps;
    }
    return [
      ...rawSteps,
      {
        id: "session-summary",
        type: "summary",
        title: t("practice.explain.summaryTitle"),
        narration: explanation.summary,
        duration_ms: 2800,
        delay_ms: 600,
        animations: [],
        board_notes: [],
      },
    ];
  }, [rawSteps, explanation.summary, t]);
  const language = explanation.language ?? "en";
  const [currentStep, setCurrentStep] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [subtitle, setSubtitle] = useState("");

  useEffect(() => {
    setCurrentStep(0);
    setIsPlaying(false);
  }, [explanation]);

  const narrationFor = useCallback(
    (step: AnimStep | undefined) => {
      if (!step) return "";
      const narration = step.narration;
      if (!narration) return "";
      if (typeof narration === "string") return narration;
      return narration[language] || narration.en || narration.zh || "";
    },
    [language]
  );

  useEffect(() => {
    const step = steps[currentStep];
    const text = narrationFor(step);
    setSubtitle("");
    if (!text) {
      return;
    }
    let index = 0;
    const interval = setInterval(() => {
      index += 1;
      setSubtitle(text.slice(0, index));
      if (index >= text.length) {
        clearInterval(interval);
      }
    }, 25);
    return () => clearInterval(interval);
  }, [currentStep, steps, narrationFor]);

  useEffect(() => {
    if (!isPlaying) return;
    const step = steps[currentStep];
    if (!step) return;
    const total =
      Math.max(step.duration_ms ?? 3000, 500) + Math.max(step.delay_ms ?? 500, 0);
    const timer = setTimeout(() => {
      if (currentStep < steps.length - 1) {
        setCurrentStep((prev) => prev + 1);
      } else {
        setIsPlaying(false);
      }
    }, total);
    return () => clearTimeout(timer);
  }, [isPlaying, currentStep, steps]);

  const goToStep = (nextIndex: number) => {
    if (nextIndex < 0 || nextIndex >= steps.length) return;
    setCurrentStep(nextIndex);
    setIsPlaying(false);
  };

  const togglePlay = () => {
    if (!steps.length) return;
    setIsPlaying((prev) => !prev);
  };

  const step = steps[currentStep];

  useEffect(() => {
    onDirectivesChange(step?.animations ?? []);
    return () => onDirectivesChange([]);
  }, [step, onDirectivesChange]);

  return (
    <div className="space-y-4 rounded-xl border border-white/10 bg-white/5 p-4 text-xs text-white/80">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-white">{t("practice.explain.title")}</p>
          <p className="text-white/60">
            {t("practice.explain.stepIndicator", {
              current: currentStep + 1,
              total: steps.length,
            })}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            className="rounded-full border border-white/20 px-3 py-1 text-xs text-white/80 disabled:opacity-30"
            onClick={() => goToStep(currentStep - 1)}
            disabled={currentStep === 0}
          >
            ◀
          </button>
          <button
            className="rounded-full border border-white/20 px-3 py-1 text-xs text-white/80 disabled:opacity-30"
            onClick={togglePlay}
            disabled={!steps.length}
          >
            {isPlaying ? t("practice.explain.pause") : t("practice.explain.play")}
          </button>
          <button
            className="rounded-full border border-white/20 px-3 py-1 text-xs text-white/80 disabled:opacity-30"
            onClick={() => goToStep(currentStep + 1)}
            disabled={currentStep >= steps.length - 1}
          >
            ▶
          </button>
        </div>
      </div>

      {step && (
        <div className="space-y-2">
          <div className="rounded-lg border border-white/10 bg-[#050E1F]/40 p-3">
            <p className="text-white text-sm font-semibold">
              {step.title ||
                t("practice.explain.stepTitle", { current: currentStep + 1 })}
            </p>
            <p className="text-white/60 text-xs capitalize">
              {step.type || t("practice.explain.defaultType")}
            </p>
          </div>
          {step.board_notes?.length ? (
            <ul className="list-disc space-y-1 rounded-lg border border-white/10 bg-transparent px-5 py-2 text-white/60">
              {step.board_notes.map((note, idx) => (
                <li key={idx}>{note}</li>
              ))}
            </ul>
          ) : null}
          <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white">
            {subtitle || narrationFor(step)}
          </div>
          <p className="text-white/40 text-[11px]">
            {t("practice.explain.duration", {
              seconds: Math.round((step.duration_ms ?? 0) / 100) / 10,
              delay: Math.round((step.delay_ms ?? 0) / 100) / 10,
            })}
          </p>
        </div>
      )}
      {!steps.length && (
        <p className="text-white/60 text-sm">{t("practice.explain.empty")}</p>
      )}
    </div>
  );
}
/* eslint-enable react-hooks/set-state-in-effect */

