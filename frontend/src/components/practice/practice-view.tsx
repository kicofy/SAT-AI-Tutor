"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { DashboardCard } from "@/components/ui/dashboard-card";
import { AppShell } from "@/components/layout/app-shell";
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
  ExplanationResponse,
} from "@/types/session";
import type { AiExplainQuota } from "@/types/auth";
import {
  ExplanationViewer,
  HighlightedText,
  StepDirective,
  AnimExplanation,
  type Translator,
} from "@/components/practice/explanation-viewer";
import { extractErrorMessage } from "@/lib/errors";
import { AxiosError } from "axios";
import { env } from "@/lib/env";
import { getClientToken } from "@/lib/auth-storage";
import { useI18n } from "@/hooks/use-i18n";
import { useAuthStore } from "@/stores/auth-store";
import { getQuestionDecorations } from "@/lib/question-decorations";

const API_BASE_URL = (env.apiBaseUrl || "").replace(/\/$/, "");

type ViewState = "prep" | "loading" | "active";

type PracticeViewProps = {
  planBlockId?: string;
  autoResumeDiagnostic?: boolean;
  sourceId?: number;
  draftId?: number;
};

type TranslateFn = ReturnType<typeof useI18n>["t"];

type QuestionProgress = {
  isCorrect?: boolean;
  logId?: number;
  explanation?: AnimExplanation;
  revealedAnswer?: boolean;
  userChoice?: string | null;
  timeSpentSec?: number;
};

const MIN_QUESTIONS = 1;
const DEFAULT_MAX_QUESTIONS = 12;

const keyForQuestion = (sessionId: number, questionId: number) =>
  `${sessionId}-${questionId}`;

const formatSeconds = (value: number): string => {
  if (!Number.isFinite(value) || value <= 0) {
    return "—";
  }
  if (value < 60) {
    return `${value}s`;
  }
  const minutes = Math.floor(value / 60);
  const seconds = value % 60;
  return `${minutes}m ${seconds.toString().padStart(2, "0")}s`;
};

export function PracticeView({
  planBlockId,
  autoResumeDiagnostic = false,
  sourceId,
  draftId,
}: PracticeViewProps = {}) {
  const { t } = useI18n();
  const translator = useMemo<Translator>(
    () => ((key, params) => t(key as any, params as any)) as Translator,
    [t]
  );
  const queryClient = useQueryClient();
  const router = useRouter();
  const isPlanTaskMode = Boolean(planBlockId);
  const userId = useAuthStore((state) => state.user?.id);
  const isDraftPreview = Boolean(draftId);
  const initialViewState: ViewState =
    isPlanTaskMode || autoResumeDiagnostic || sourceId || isDraftPreview ? "loading" : "prep";
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
  const authUser = useAuthStore((state) => state.user);
  const updateAuthUser = useAuthStore((state) => state.updateUser);
  const applyQuotaUpdate = useCallback(
    (quota?: AiExplainQuota) => {
      if (!quota || !authUser) return;
      updateAuthUser({ ...authUser, ai_explain_quota: quota });
    },
    [authUser, updateAuthUser]
  );
  const [error, setError] = useState<string | null>(null);
  const [completionMessage, setCompletionMessage] = useState<string | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  const [isExplanationLoading, setExplanationLoading] = useState(false);
  const [maxQuestions, setMaxQuestions] = useState(DEFAULT_MAX_QUESTIONS);
  const [activeDirectives, setActiveDirectives] = useState<StepDirective[]>([]);
  const [isFinishDialogOpen, setFinishDialogOpen] = useState(false);
  const [isAbortDialogOpen, setAbortDialogOpen] = useState(false);
  const [isFinishing, setIsFinishing] = useState(false);
  const [isAborting, setIsAborting] = useState(false);
  const [planTask, setPlanTask] = useState<PlanTask | null>(null);
  const [hasAutoResumedDiagnostic, setHasAutoResumedDiagnostic] = useState(false);
  const [questionStartTime, setQuestionStartTime] = useState<number | null>(null);
  const lastQuestionIdRef = useRef<number | null>(null);

  const updateLocalSessionProgress = useCallback(
    (entry: SessionProgressEntry) => {
      setSession((prev) => {
        if (!prev) return prev;
        const progress = Array.isArray(prev.questions_done) ? [...prev.questions_done] : [];
        const index = progress.findIndex((item) => item?.question_id === entry.question_id);
        if (index >= 0) {
          progress[index] = { ...progress[index], ...entry };
        } else {
          progress.push(entry);
        }
        return { ...prev, questions_done: progress };
      });
    },
    []
  );

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

  const buildFigureSrc = useCallback((url?: string) => {
    if (!url) return null;
    return url.startsWith("http://") || url.startsWith("https://") ? url : `${API_BASE_URL}${url}`;
  }, []);

  const currentQuestion: SessionQuestion | undefined =
    session?.questions_assigned[currentIndex];

  const isFillQuestion = useMemo(() => {
    const type = (currentQuestion?.question_type || "choice").toLowerCase();
    const choiceCount = currentQuestion?.choices
      ? Object.keys(currentQuestion.choices || {}).length
      : 0;
    const hasNoChoices = choiceCount === 0;
    const hasAnswerSchema = Boolean(currentQuestion?.answer_schema);
    // Fallback: if marked choice but no options and has answer schema, treat as fill.
    if (type === "fill") return true;
    if ((type === "choice" || !type) && hasNoChoices && hasAnswerSchema) return true;
    return false;
  }, [currentQuestion]);

  const showChoiceList =
    !isFillQuestion && currentQuestion?.choices && Object.keys(currentQuestion.choices).length;

  const choiceFigureIds = useMemo(() => {
    const set = new Set<number>();
    if (currentQuestion?.choice_figures) {
      Object.values(currentQuestion.choice_figures).forEach((ref) => {
        if (ref?.id != null) set.add(ref.id);
      });
    }
    return set;
  }, [currentQuestion]);

  const displayFigures = useMemo(() => {
    if (!currentQuestion?.figures?.length) return [];
    return currentQuestion.figures.filter((fig) => !choiceFigureIds.has(fig.id));
  }, [currentQuestion, choiceFigureIds]);

  const hasChoiceImages = useMemo(() => choiceFigureIds.size > 0, [choiceFigureIds]);

  // Detect whether choice images are “wide” (very horizontal). If wide, keep a single-column layout
  // to avoid squashing; otherwise allow 2-column grid for square-ish images.
  const [isChoiceImageWide, setIsChoiceImageWide] = useState(false);
  useEffect(() => {
    let cancelled = false;
    setIsChoiceImageWide(false);
    if (!currentQuestion?.choice_figures) return;
    const refs = Object.values(currentQuestion.choice_figures).filter((ref) => !!ref?.url);
    if (!refs.length) return;
    const url = refs[0].url;
    const img = new Image();
    img.onload = () => {
      if (cancelled) return;
      const ratio = img.width && img.height ? img.width / img.height : 1;
      setIsChoiceImageWide(ratio > 1.4); // heuristic: wider than ~7:5 treats as wide
    };
    img.onerror = () => {
      if (!cancelled) setIsChoiceImageWide(false);
    };
    img.src = url;
    return () => {
      cancelled = true;
    };
  }, [currentQuestion?.choice_figures]);

  const currentQuestionId = currentQuestion?.question_id ?? null;

  useEffect(() => {
    if (!currentQuestionId) {
      setQuestionStartTime(null);
      lastQuestionIdRef.current = null;
      return;
    }
    if (lastQuestionIdRef.current !== currentQuestionId) {
      lastQuestionIdRef.current = currentQuestionId;
      setQuestionStartTime(Date.now());
    }
  }, [currentQuestionId]);

  const isLastQuestion =
    session && currentQuestion
      ? currentIndex + 1 >= session.questions_assigned.length
      : false;

  const progressKey =
    session && currentQuestion
      ? keyForQuestion(session.id, currentQuestion.question_id)
      : null;
  const currentProgress = progressKey ? questionProgress[progressKey] : undefined;
  const explanation = currentProgress?.explanation;

  const questionDecorations = useMemo(
    () => getQuestionDecorations(currentQuestion ?? null),
    [currentQuestion]
  );

  const combinedDirectives = useMemo(
    () => [...questionDecorations, ...activeDirectives],
    [questionDecorations, activeDirectives]
  );

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

  const choiceCount = currentQuestion?.choices
    ? Object.keys(currentQuestion.choices || {}).length
    : 0;
  const hasMissingChoices =
    !!currentQuestion &&
    !isFillQuestion &&
    (currentQuestion.question_type === "choice" || !currentQuestion.question_type) &&
    choiceCount === 0;
  const hasMissingAnswer =
    !!currentQuestion &&
    (currentQuestion.question_type === "choice" ||
      currentQuestion.question_type === "fill" ||
      !currentQuestion.question_type) &&
    (!currentQuestion.correct_answer || currentQuestion.correct_answer?.value == null);

  const derivedUnavailableReason =
    currentQuestion?.unavailable_reason ||
    (hasMissingChoices ? "missing_choices" : hasMissingAnswer ? "missing_answer" : "");

  const isQuestionUnavailable = Boolean(derivedUnavailableReason);
  const questionUnavailableMessage = (() => {
    if (!derivedUnavailableReason) return "";
    if (derivedUnavailableReason === "missing_choices") {
      return "This question is unavailable because the choices are missing.";
    }
    if (derivedUnavailableReason === "missing_answer") {
      return "This question is unavailable because the answer data is missing.";
    }
    return t("practice.unavailable.message" as any);
  })();

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
    () => combinedDirectives.filter((d) => d.target === "passage"),
    [combinedDirectives]
  );
  const stemDirectives = useMemo(
    () => combinedDirectives.filter((d) => d.target === "stem"),
    [combinedDirectives]
  );
  const choiceDirectives = useMemo(
    () => combinedDirectives.filter((d) => d.target === "choices"),
    [combinedDirectives]
  );
  const figureDirectives = useMemo(
    () => combinedDirectives.filter((d) => d.target === "figure"),
    [combinedDirectives]
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

  const localAnsweredCount = useMemo(() => {
    if (!session) {
      return 0;
    }
    const prefix = `${session.id}-`;
    return Object.entries(questionProgress).reduce((count, [key, entry]) => {
      if (!key.startsWith(prefix)) {
        return count;
      }
      return entry?.logId ? count + 1 : count;
    }, 0);
  }, [questionProgress, session]);

  const planTaskProgress = useMemo(() => {
    if (!isPlanTaskMode) {
      return null;
    }
    let completed = session?.questions_done?.length ?? null;
    if (!completed) {
      completed =
        localAnsweredCount ||
        planTask?.questions_completed ||
        planTasksMap[planBlockId || ""]?.questions_completed ||
        0;
    }
    const total =
      planTask?.questions_target ??
      planBlockDetail?.questions ??
      session?.questions_assigned.length ??
      planTasksMap[planBlockId || ""]?.questions_target ??
      0;
    return { completed, total };
  }, [
    isPlanTaskMode,
    planTask,
    planTasksMap,
    planBlockDetail,
    planBlockId,
    session,
    localAnsweredCount,
  ]);

  const goalSummary =
    planDetail?.target_questions !== undefined
      ? t("practice.goalSummary.value", { count: planDetail.target_questions })
      : t("practice.goalSummary.custom");

  const planSessionStats = useMemo(() => {
    if (!isPlanTaskMode) {
      return null;
    }
    const sectionValue =
      planBlockDetail?.section ||
      session?.questions_assigned?.[0]?.section ||
      sectionLabel ||
      "";
    let normalizedSection = sectionValue;
    if (sectionValue === "Math") {
      normalizedSection = t("practice.section.math.label");
    } else if (sectionValue === "RW") {
      normalizedSection = t("practice.section.rw.label");
    }
    const questionsTarget =
      planBlockDetail?.questions ??
      planTask?.questions_target ??
      session?.questions_assigned.length ??
      0;
    const targetValue =
      questionsTarget > 0 ? t("plan.block.questions", { count: questionsTarget }) : goalSummary;
    return [
      {
        label: t("practice.summary.section"),
        value: normalizedSection || t("common.unknown"),
      },
      {
        label: t("practice.summary.target"),
        value: targetValue,
      },
    ];
  }, [
    goalSummary,
    isPlanTaskMode,
    planBlockDetail,
    planTask,
    sectionLabel,
    session,
    t,
  ]);

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
          source_id: sourceId,
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
  }, [planBlockId, prepConfig.num_questions, prepConfig.section, maxQuestions, t, sourceId]);

  const loadDraftPreview = useCallback(async (): Promise<boolean> => {
    if (!draftId) return false;
    try {
      const token = await getClientToken();
      const resp = await fetch(`${API_BASE_URL}/api/admin/questions/drafts/${draftId}/preview`, {
        headers: {
          Authorization: token ? `Bearer ${token}` : "",
        },
      });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(text || `Preview failed (${resp.status})`);
      }
      const data = (await resp.json()) as { question?: SessionQuestion };
      if (!data?.question) {
        throw new Error("Preview question missing");
      }
      const previewSession: Session = {
        id: -draftId,
        session_type: "preview",
        questions_assigned: [data.question],
        questions_done: [],
      };
      setSession(previewSession);
      setQuestionProgress({});
      setCurrentIndex(0);
      setSelectedChoice(null);
      setActiveDirectives([]);
      setViewState("active");
      setActiveSession(null);
      return true;
    } catch (err: unknown) {
      const message = extractErrorMessage(err, t("practice.error.start"));
      setError(message);
      setViewState("prep");
      return false;
    }
  }, [draftId, t]);

  async function handleStart(e: React.FormEvent) {
    e.preventDefault();
    if (planBlockId) return;
    setCompletionMessage(null);
    setError(null);
    setViewState("loading");
    await attemptStart();
  }

  useEffect(() => {
    if (sourceId && viewState === "loading" && !session && !activeSession) {
      attemptStart().catch(() => undefined);
    }
  }, [sourceId, viewState, session, activeSession, attemptStart]);

  useEffect(() => {
    if (isDraftPreview && viewState === "loading" && !session && !activeSession) {
      loadDraftPreview().catch(() => undefined);
    }
  }, [isDraftPreview, viewState, session, activeSession, loadDraftPreview]);

  async function handleCheckAnswer() {
    if (!session || !currentQuestion || selectedChoice === null || selectedChoice === undefined || !progressKey)
      return;
    if (isFillQuestion && String(selectedChoice).trim() === "") return;
    setIsChecking(true);
    setError(null);
    try {
      const elapsedSeconds =
        questionStartTime !== null
          ? Math.max(1, Math.round((Date.now() - questionStartTime) / 1000))
          : undefined;
      if (isDraftPreview) {
        const correct = (
          (currentQuestion.correct_answer as { value?: string } | undefined)?.value || ""
        )
          .toString()
          .trim()
          .toUpperCase();
        const isCorrect = correct ? correct === selectedChoice.toUpperCase() : false;
        setQuestionProgress((prev) => ({
          ...prev,
          [progressKey]: {
            ...prev[progressKey],
            isCorrect,
            logId: -1,
            userChoice: selectedChoice,
            timeSpentSec: elapsedSeconds ?? prev[progressKey]?.timeSpentSec,
          },
        }));
        setQuestionStartTime(null);
        return;
      }
      const response = await submitAnswer({
        session_id: session.id,
        question_id: currentQuestion.question_id,
        user_answer: { value: selectedChoice },
        time_spent_sec: elapsedSeconds,
      });
      setQuestionStartTime(null);
      setQuestionProgress((prev) => ({
        ...prev,
        [progressKey]: {
          ...prev[progressKey],
          isCorrect: response.is_correct,
          logId: response.log_id,
          userChoice: selectedChoice,
          timeSpentSec: elapsedSeconds ?? prev[progressKey]?.timeSpentSec,
        },
      }));
      updateLocalSessionProgress({
        question_id: currentQuestion.question_id,
        log_id: response.log_id,
        is_correct: response.is_correct,
        user_answer: { value: selectedChoice },
        answered_at: new Date().toISOString(),
        time_spent_sec: elapsedSeconds,
      });
      if (isPlanTaskMode) {
        setPlanTask((prev) => {
          if (!prev) return prev;
          const target = prev.questions_target ?? session.questions_assigned.length ?? 0;
          const nextCompleted = Math.min((prev.questions_completed ?? 0) + 1, target);
          if (nextCompleted === prev.questions_completed) {
            return prev;
          }
          return { ...prev, questions_completed: nextCompleted };
        });
        if (planBlockId) {
          setPlanTasksMap((prev) => {
            const existing = prev[planBlockId];
            if (!existing) return prev;
            const target =
              existing.questions_target ??
              planBlockDetail?.questions ??
              session.questions_assigned.length ??
              0;
            const nextCompleted = Math.min((existing.questions_completed ?? 0) + 1, target);
            if (nextCompleted === existing.questions_completed) {
              return prev;
            }
            return {
              ...prev,
              [planBlockId]: { ...existing, questions_completed: nextCompleted },
            };
          });
        }
        if (userId) {
          queryClient
            .invalidateQueries({ queryKey: ["plan-today", userId] })
            .catch(() => undefined);
        }
      }
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
    if (isDraftPreview) return;
    if (!session || !currentQuestion || !progressKey || explanation) return;
    setExplanationLoading(true);
    setError(null);
    try {
      const response = (await fetchExplanation({
        session_id: session.id,
        question_id: currentQuestion.question_id,
      })) as ExplanationResponse;
      applyQuotaUpdate(response.quota as AiExplainQuota | undefined);
      const payload = response.explanation as AnimExplanation;
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
      if (
        err instanceof AxiosError &&
        err.response?.status === 429 &&
        err.response.data?.error === "ai_explain_quota_exceeded"
      ) {
        applyQuotaUpdate(err.response.data.quota as AiExplainQuota | undefined);
        setError(t("practice.error.aiQuota"));
        return;
      }
      setError(extractErrorMessage(err, t("practice.error.explanation")));
    } finally {
      setExplanationLoading(false);
    }
  }

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

  const livePracticeStats = useMemo(() => {
    if (!session) {
      return null;
    }
    const total = session.questions_assigned.length;
    if (!total) {
      return { total: 0, completed: 0, accuracy: null, avgTime: null };
    }
    let completed = 0;
    let correct = 0;
    let totalTime = 0;
    let timedCount = 0;
    session.questions_assigned.forEach((question) => {
      const key = keyForQuestion(session.id, question.question_id);
      const entry = questionProgress[key];
      if (!entry?.logId) {
        return;
      }
      completed += 1;
      if (entry.isCorrect) {
        correct += 1;
      }
      if (typeof entry.timeSpentSec === "number") {
        totalTime += entry.timeSpentSec;
        timedCount += 1;
      }
    });
    const accuracy = completed ? Math.round((correct / completed) * 100) : null;
    const avgTime = completed ? Math.round(totalTime / (timedCount || completed)) : null;
    return { total, completed, accuracy, avgTime };
  }, [questionProgress, session]);
  const summaryStats = useMemo(() => {
    const stats = [
      {
        label: t("practice.summary.section"),
        value:
          sectionOptions.find((opt) => opt.id === prepConfig.section)?.label ?? prepConfig.section,
      },
      {
        label: t("practice.summary.target"),
        value: goalSummary,
      },
    ];
    if (livePracticeStats && (session || livePracticeStats.completed > 0)) {
      stats.push(
        {
          label: t("practice.summary.completed"),
          value: `${livePracticeStats.completed}/${livePracticeStats.total || 0}`,
        },
        {
          label: t("practice.summary.accuracy"),
          value:
            livePracticeStats.accuracy !== null
              ? `${livePracticeStats.accuracy}%`
              : t("common.placeholderDash"),
        },
        {
          label: t("practice.summary.avgTime"),
          value:
            livePracticeStats.avgTime !== null
              ? formatSeconds(livePracticeStats.avgTime)
              : t("common.placeholderDash"),
        }
      );
    }
    return stats;
  }, [goalSummary, livePracticeStats, prepConfig.section, sectionOptions, session, t]);

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
          timeSpentSec: entry.time_spent_sec,
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
        } else if (err instanceof AxiosError && err.response?.status === 402) {
          const message = err.response?.data?.message || t("plan.locked.title");
          setError(message);
          setPlanError(message);
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
      if (isDraftPreview) {
        setSession(null);
        setQuestionProgress({});
        setSelectedChoice(null);
        setActiveDirectives([]);
        setViewState("prep");
        setCompletionMessage(t("practice.session.complete"));
        setActiveSession(null);
        setCurrentIndex(0);
        return;
      }
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
  }, [session, isPlanTaskMode, t, queryClient, router, userId, isDraftPreview]);

  const handleSelectChoice = useCallback(
    (choiceKey: string) => {
      if (isQuestionUnavailable || hasChecked) {
        return;
      }
      if (!session || !currentQuestion) return;
      setSelectedChoice(choiceKey);
      const key = keyForQuestion(session.id, currentQuestion.question_id);
      setQuestionProgress((prev) => ({
        ...prev,
        [key]: {
          ...prev[key],
          userChoice: choiceKey,
        },
      }));
    },
    [currentQuestion, hasChecked, isQuestionUnavailable, session]
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

  const pageContent = (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6 lg:px-0">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
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
        {session && viewState === "active" && (
          <button
            type="button"
            className="btn-ghost px-4 py-2 text-sm"
            onClick={() => setFinishDialogOpen(true)}
          >
            {t("practice.button.finish")}
          </button>
        )}
      </div>
      <div className="flex flex-col gap-6 lg:grid lg:grid-cols-[minmax(0,1fr)_360px] lg:items-start mt-6">
        <div className="space-y-6">
          {!isPlanTaskMode && viewState === "active" && summaryStats.length > 0 && (
            <DashboardCard
              tone="subtle"
              className="px-4 py-3 text-sm text-white/80"
              title={t("practice.summary.cardTitle")}
              subtitle={t("practice.summary.cardSubtitle")}
            >
              <dl className="mt-2 grid gap-x-6 gap-y-2 sm:grid-cols-2">
                {summaryStats.map((stat) => (
                  <div key={stat.label} className="flex flex-col gap-0.5">
                    <dt className="text-[11px] uppercase tracking-wide text-white/50">
                      {stat.label}
                    </dt>
                    <dd className="text-base font-semibold text-white">{stat.value}</dd>
                  </div>
                ))}
              </dl>
            </DashboardCard>
          )}
          {isPlanTaskMode && planBlockDetail && (
            <DashboardCard
              title={t("practice.planTask.title")}
              subtitle={planBlockDetail.focus_skill_label ?? planBlockDetail.focus_skill}
            >
              <div className="space-y-2">
                <p className="text-sm text-white/70">
                  {t("practice.planTask.meta", {
                    section: planBlockDetail.section,
                    minutes: planBlockDetail.minutes,
                    questions: planBlockDetail.questions,
                  })}
                </p>
                {planTaskProgress ? (
                  <p className="text-sm font-semibold text-white">
                    {t("practice.planTask.progress", {
                      completed: planTaskProgress.completed,
                      total: planTaskProgress.total,
                    })}
                  </p>
                ) : null}
              </div>
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
            {error && (
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
              {displayFigures.length ? (
                <div className="space-y-4">
                  {displayFigures.map((figure) => {
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
              {isFillQuestion ? (
                <div className="space-y-2">
                  <label className="text-sm text-white/70">Enter your answer</label>
                  <input
                    type="text"
                    value={selectedChoice ?? ""}
                    onChange={(e) => {
                      if (isQuestionUnavailable || hasChecked) return;
                      setSelectedChoice(e.target.value);
                    }}
                    disabled={isQuestionUnavailable || hasChecked}
                    className="w-full rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-white placeholder:text-white/40 focus:border-white/40 focus:outline-none"
                    placeholder="e.g., 3.5 or 7/2"
                  />
                </div>
              ) : showChoiceList ? (
                <div
                  className={
                    hasChoiceImages
                      ? isChoiceImageWide
                        ? "grid grid-cols-1 gap-3"
                        : "grid grid-cols-1 gap-3 sm:grid-cols-2"
                      : "space-y-2"
                  }
                >
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
                const imageRef = currentQuestion.choice_figures?.[key];
                const isSelectedChoice = !hasChecked && selectedChoice === key;
                const isUserChoice = currentProgress?.userChoice === key;
                const isUserCorrectChoice = hasChecked && currentProgress?.isCorrect && isUserChoice;
                const isUserIncorrectChoice = hasChecked && isUserChoice && !currentProgress?.isCorrect;

                const baseClasses =
                  "h-full w-full rounded-xl border px-4 py-3 text-left text-sm transition relative overflow-hidden";
                let stateClasses =
                  "border-white/15 text-white/70 hover:border-white/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white/50";

                if (isQuestionUnavailable) {
                  stateClasses = "cursor-not-allowed opacity-50 border-white/10 text-white/40";
                } else if (isUserCorrectChoice) {
                  stateClasses =
                    "border-emerald-400 text-emerald-200 bg-emerald-500/10 shadow-[0_10px_25px_rgba(16,185,129,0.25)]";
                } else if (isUserIncorrectChoice) {
                  stateClasses =
                    "border-rose-500 text-rose-100 bg-rose-500/10 shadow-[0_10px_25px_rgba(244,63,94,0.2)]";
                } else if (isSelectedChoice) {
                  stateClasses =
                    "border-white/80 text-white bg-white/5 shadow-[0_12px_30px_rgba(5,14,31,0.45)]";
                }

                const emphasisClasses = isChoiceEmphasized
                  ? strikeChoice
                    ? "ring-2 ring-rose-400/70 shadow-[0_0_0_1px_rgba(248,113,113,0.4)]"
                    : noteChoice
                    ? "ring-2 ring-emerald-300/60 shadow-[0_0_0_1px_rgba(16,185,129,0.35)]"
                    : "ring-2 ring-amber-300/70 shadow-[0_0_0_1px_rgba(251,191,36,0.35)]"
                  : "";

                const strikeDecoration = strikeChoice ? "line-through decoration-rose-300" : "";

                return (
                  <button
                    key={key}
                    onClick={() => handleSelectChoice(key)}
                    disabled={isQuestionUnavailable || hasChecked}
                    className={clsx(baseClasses, stateClasses, emphasisClasses)}
                  >
                    <div className="flex items-start gap-3">
                      <span className={clsx("mt-1 font-semibold", strikeDecoration)}>{key}.</span>
                      <div className="flex flex-1 flex-col gap-2">
                        {imageRef ? (
                          <div className="flex w-full justify-start">
                            <img
                              src={buildFigureSrc(imageRef.url) || imageRef.url}
                              alt={imageRef.description || `Choice ${key}`}
                              className="w-full rounded-lg border border-white/10 bg-black/20 p-2 object-contain"
                            />
                          </div>
                        ) : null}
                        {text ? (
                          <HighlightedText
                            text={text}
                            directives={snippetDirectives}
                            className={clsx("whitespace-pre-wrap text-sm leading-relaxed", strikeDecoration)}
                          />
                        ) : null}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
              ) : null}
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
                    disabled={isDraftPreview || Boolean(explanation) || isExplanationLoading}
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
                      isLastQuestion ? setFinishDialogOpen(true) : goToQuestion(currentIndex + 1)
                    }
                  >
                    {isLastQuestion ? t("practice.button.finish") : t("practice.button.next")}
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
                t={translator}
              />
            ) : (
              <p className="text-sm text-white/70">{t("practice.strategy.empty")}</p>
            )}
          </DashboardCard>
        </aside>
      </div>
      {isFinishDialogOpen && (
        <div
          className="modal-overlay fixed inset-0 z-50 flex items-center justify-center bg-[#050E1F]/80 px-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="modal-panel w-full max-w-md rounded-2xl border border-white/10 bg-[#050E1F] p-6 shadow-2xl">
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
          className="modal-overlay fixed inset-0 z-50 flex items-center justify-center bg-[#050E1F]/80 px-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="modal-panel w-full max-w-md rounded-2xl border border-white/10 bg-[#050E1F] p-6 shadow-2xl">
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

  if (viewState === "active") {
    return pageContent;
  }

  return <AppShell contentClassName="w-full">{pageContent}</AppShell>;
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

