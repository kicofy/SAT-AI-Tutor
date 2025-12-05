"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { DashboardCard } from "@/components/ui/dashboard-card";
import {
  ingestPdf,
  deleteQuestion,
  fetchImportStatus,
  listQuestions,
  deleteDraft,
  publishDraft,
  cancelImport,
  fetchDraftFigureSource,
  uploadDraftFigure,
  fetchDraftFigures,
  fetchOpenaiLogs,
  clearQuestionExplanation,
} from "@/services/admin";
import { useAuth } from "@/hooks/use-auth";
import { extractErrorMessage } from "@/lib/errors";
import { env } from "@/lib/env";
import { getClientToken } from "@/lib/auth-storage";
import { getCroppedBlob, SelectionRect } from "@/lib/image";
import { X } from "lucide-react";

const QUESTION_PAGE_SIZE = 10;
const OPENAI_LOG_LIMIT = 200;

type ImportJob = {
  id: number;
  status: string;
  parsed_questions: number;
  total_blocks: number;
  processed_pages: number;
  total_pages: number;
  current_page?: number | null;
  status_message?: string | null;
  last_progress_at?: string | null;
  created_at?: string;
  ingest_strategy?: string;
  error_message?: string | null;
};

type DraftPayloadPreview = {
  stem_text?: string;
  has_figure?: boolean;
  section?: string | null;
  question_number?: string | number;
  original_question_number?: string | number;
  source_question_number?: string | number;
  question_index?: number;
  normalized_index?: number;
  local_number?: number;
  metadata?: Record<string, unknown> | null;
};

type DraftPreview = {
  id: number;
  job_id: number;
  source_id?: number | null;
  source?: {
    id: number;
    filename?: string | null;
    original_name?: string | null;
    total_pages?: number | null;
  } | null;
  payload?: DraftPayloadPreview;
  figure_count?: number;
};

type FigureSource = {
  page: number;
  image: string;
  width: number;
  height: number;
};

type FigureModalState = {
  draft: DraftPreview;
  source?: FigureSource;
  selection: SelectionRect | null;
  zoom: number;
  loading: boolean;
};

type OpenAILogEntry = {
  timestamp: string;
  kind: string;
  job_id?: number | null;
  stage?: string;
  purpose?: string;
  page?: number;
  total_pages?: number;
  attempt?: number;
  max_attempts?: number;
  wait_seconds?: number;
  normalized_count?: number;
  status_code?: number;
  duration_ms?: number;
  model?: string;
  error?: string | null;
  message?: string;
  state?: string;
};

type QuestionRecord = {
  id: number;
  question_uid?: string | null;
  section: string;
  sub_section?: string | null;
  stem_text?: string | null;
  source_id?: number | null;
  source?: {
    id: number;
    filename?: string | null;
    original_name?: string | null;
    total_pages?: number | null;
  } | null;
};

type QuestionFilters = {
  section?: string;
  question_id?: number;
  question_uid?: string;
  source_id?: number;
};

type HandleId = "nw" | "ne" | "sw" | "se";
type DragState =
  | { mode: "create"; origin: { x: number; y: number } }
  | { mode: "resize"; handle: HandleId; startRect: SelectionRect }
  | null;

type FigureCropperProps = {
  source: FigureSource;
  selection: SelectionRect | null;
  zoom: number;
  onSelectionChange: (rect: SelectionRect | null) => void;
  onSelectionComplete: (rect: SelectionRect | null) => void;
  onZoomChange: (value: number) => void;
};

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

function FigureCropper({
  source,
  selection,
  zoom,
  onSelectionChange,
  onSelectionComplete,
  onZoomChange,
}: FigureCropperProps & { onZoomChange: (value: number) => void }) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const dragState = useRef<DragState>(null);
  const activePointerId = useRef<number | null>(null);
  const [internalSelection, setInternalSelection] = useState<SelectionRect | null>(selection);
  const baseZoomRef = useRef(zoom);

  useEffect(() => {
    setInternalSelection(selection);
  }, [selection]);

  const updateSelection = useCallback(
    (rect: SelectionRect | null) => {
      setInternalSelection(rect);
      onSelectionChange(rect);
    },
    [onSelectionChange]
  );

  const clientToSource = useCallback(
    (clientX: number, clientY: number) => {
      const overlay = overlayRef.current;
      if (!overlay) return null;
      const rect = overlay.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return null;
      const x = clamp(((clientX - rect.left) / rect.width) * source.width, 0, source.width);
      const y = clamp(((clientY - rect.top) / rect.height) * source.height, 0, source.height);
      return { x, y };
    },
    [source.height, source.width]
  );

  const normalizeRect = useCallback(
    (x1: number, y1: number, x2: number, y2: number): SelectionRect => {
      const left = clamp(Math.min(x1, x2), 0, source.width);
      const right = clamp(Math.max(x1, x2), 0, source.width);
      const top = clamp(Math.min(y1, y2), 0, source.height);
      const bottom = clamp(Math.max(y1, y2), 0, source.height);
      return {
        x: left,
        y: top,
        width: Math.max(1, right - left),
        height: Math.max(1, bottom - top),
      };
    },
    [source.height, source.width]
  );

  const resizeFromHandle = useCallback(
    (rect: SelectionRect, handle: HandleId, point: { x: number; y: number }) => {
      const left = rect.x;
      const top = rect.y;
      const right = rect.x + rect.width;
      const bottom = rect.y + rect.height;
      switch (handle) {
        case "nw":
          return normalizeRect(point.x, point.y, right, bottom);
        case "ne":
          return normalizeRect(left, point.y, point.x, bottom);
        case "sw":
          return normalizeRect(point.x, top, right, point.y);
        case "se":
        default:
          return normalizeRect(left, top, point.x, point.y);
      }
    },
    [normalizeRect]
  );

  const handlePointerMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (activePointerId.current !== event.pointerId) return;
      const state = dragState.current;
      if (!state) return;
      const point = clientToSource(event.clientX, event.clientY);
      if (!point) return;
      event.preventDefault();
      if (state.mode === "create") {
        updateSelection(normalizeRect(state.origin.x, state.origin.y, point.x, point.y));
      } else if (state.mode === "resize") {
        updateSelection(resizeFromHandle(state.startRect, state.handle, point));
      }
    },
    [clientToSource, normalizeRect, resizeFromHandle, updateSelection]
  );

  const handlePointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (event.pointerType === "touch") {
        const overlay = event.currentTarget;
        overlay.releasePointerCapture(event.pointerId);
        return;
      }
      event.preventDefault();
      const point = clientToSource(event.clientX, event.clientY);
      if (!point) return;
      const target = event.target as HTMLElement;
      const handleId = (target?.dataset?.handle as HandleId | undefined) || undefined;
      const overlay = event.currentTarget;
      overlay.setPointerCapture(event.pointerId);
      activePointerId.current = event.pointerId;
      if (handleId && internalSelection) {
        dragState.current = { mode: "resize", handle: handleId, startRect: internalSelection };
        return;
      }
      dragState.current = { mode: "create", origin: point };
      updateSelection({ x: point.x, y: point.y, width: 1, height: 1 });
    },
    [clientToSource, internalSelection, updateSelection]
  );

  const handlePointerUp = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (activePointerId.current !== event.pointerId) return;
      activePointerId.current = null;
      const overlay = event.currentTarget;
      try {
        overlay.releasePointerCapture(event.pointerId);
      } catch {
        /* noop */
      }
      dragState.current = null;
      onSelectionComplete(internalSelection);
    },
    [internalSelection, onSelectionComplete]
  );

  const handleWheel = useCallback(
    (event: React.WheelEvent<HTMLDivElement>) => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      const delta = -event.deltaY;
      const scaleChange = delta > 0 ? 0.05 : -0.05;
      const newZoom = clamp(zoom + scaleChange, 0.8, 2.5);
      baseZoomRef.current = newZoom;
      onZoomChange(newZoom);
    },
    [zoom, onZoomChange]
  );

  const selectionStyle = internalSelection
    ? {
        left: `${(internalSelection.x / source.width) * 100}%`,
        top: `${(internalSelection.y / source.height) * 100}%`,
        width: `${(internalSelection.width / source.width) * 100}%`,
        height: `${(internalSelection.height / source.height) * 100}%`,
      }
    : undefined;

  const handleOffsets: Record<HandleId, { left: string; top: string; cursor: string }> = {
    nw: { left: "-6px", top: "-6px", cursor: "nwse-resize" },
    ne: { left: "calc(100% - 6px)", top: "-6px", cursor: "nesw-resize" },
    sw: { left: "-6px", top: "calc(100% - 6px)", cursor: "nesw-resize" },
    se: { left: "calc(100% - 6px)", top: "calc(100% - 6px)", cursor: "nwse-resize" },
  };

  const dimensions = {
    width: source.width * zoom,
    height: source.height * zoom,
  };

  const BASE_WIDTH = 720;
  const BASE_HEIGHT = 520;
  const baseScale = Math.min(BASE_WIDTH / source.width, BASE_HEIGHT / source.height);
  const safeBaseScale = Number.isFinite(baseScale) && baseScale > 0 ? baseScale : 1;
  const displayWidth = source.width * safeBaseScale * zoom;
  const displayHeight = source.height * safeBaseScale * zoom;

  return (
    <div className="flex justify-center">
      <div
        className="relative inline-block rounded-xl bg-[#0f172a] p-2"
        style={{ width: displayWidth + 16 }}
      >
        <div className="relative inline-block rounded-xl bg-white shadow-2xl">
          <img
            src={source.image}
            alt={`PDF page ${source.page}`}
            className="select-none rounded-xl"
            draggable={false}
            style={{
              width: displayWidth,
              height: displayHeight,
            }}
          />
          <div
            ref={overlayRef}
            className="absolute inset-0 cursor-crosshair rounded-xl"
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
          >
            {internalSelection && selectionStyle && (
              <div
                className="absolute border-2 border-sky-300 bg-sky-300/25 backdrop-brightness-150"
                style={selectionStyle}
              >
                {(Object.keys(handleOffsets) as HandleId[]).map((handle) => (
                  <div
                    key={handle}
                    data-handle={handle}
                    className="absolute h-3 w-3 rounded-full border border-white bg-sky-400 shadow"
                    style={{
                      left: handleOffsets[handle].left,
                      top: handleOffsets[handle].top,
                      cursor: handleOffsets[handle].cursor,
                    }}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function TempImportPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [file, setFile] = useState<File | null>(null);
  const [uploadState, setUploadState] = useState<"idle" | "uploading">("idle");
  const [jobResult, setJobResult] = useState<unknown>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [questionId, setQuestionId] = useState("1");
  const [deleteState, setDeleteState] = useState<"idle" | "loading">("idle");
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null);

  const [jobs, setJobs] = useState<ImportJob[]>([]);
  const [drafts, setDrafts] = useState<DraftPreview[]>([]);
  const [importsLoading, setImportsLoading] = useState(false);
  const [importsError, setImportsError] = useState<string | null>(null);

  const [questions, setQuestions] = useState<QuestionRecord[]>([]);
  const [questionPage, setQuestionPage] = useState(1);
  const [questionTotal, setQuestionTotal] = useState(0);
  const [questionFilters, setQuestionFilters] = useState<QuestionFilters>({});
  const questionFiltersRef = useRef<QuestionFilters>({});
  const [questionSearchValue, setQuestionSearchValue] = useState("");
  const [sourceFilterValue, setSourceFilterValue] = useState("");
  const [questionsLoading, setQuestionsLoading] = useState(false);
  const [questionsError, setQuestionsError] = useState<string | null>(null);
  const [rowDeleteId, setRowDeleteId] = useState<number | null>(null);
  const [clearExplainId, setClearExplainId] = useState<number | null>(null);
  const [draftDeleteId, setDraftDeleteId] = useState<number | null>(null);
  const [draftPublishId, setDraftPublishId] = useState<number | null>(null);
  const [draftActionMessage, setDraftActionMessage] = useState<string | null>(null);
  const [cancelJobId, setCancelJobId] = useState<number | null>(null);
  const [eventError, setEventError] = useState<string | null>(null);
  const [figureState, setFigureState] = useState<Record<number, number>>({});
  const [figureModal, setFigureModal] = useState<FigureModalState | null>(null);
  const [figurePreviewUrl, setFigurePreviewUrl] = useState<string | null>(null);
  const [figureError, setFigureError] = useState<string | null>(null);
  const [figureSaving, setFigureSaving] = useState(false);
  const [openaiLogs, setOpenaiLogs] = useState<OpenAILogEntry[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState<string | null>(null);
  const [questionActionNotice, setQuestionActionNotice] = useState<
    { text: string; tone: "success" | "error" } | null
  >(null);

  const getPdfQuestionNumber = useCallback((draft: DraftPreview) => {
    const payload = draft.payload || {};
    const metadata = (payload.metadata || {}) as Record<string, unknown>;
    const pickNumber = (value: unknown): string | number | null => {
      if (typeof value === "string" && value.trim()) return value;
      if (typeof value === "number") return value;
      return null;
    };
    return (
      pickNumber(metadata?.source_question_number) ??
      pickNumber(payload.source_question_number) ??
      pickNumber(payload.question_number) ??
      pickNumber(payload.original_question_number) ??
      pickNumber(payload.question_index) ??
      null
    );
  }, []);

  const getLocalQuestionNumber = useCallback((draft: DraftPreview) => {
    const payload = draft.payload || {};
    const metadata = (payload.metadata || {}) as Record<string, unknown>;
    const pickNumber = (value: unknown): string | number | null => {
      if (typeof value === "string" && value.trim()) return value;
      if (typeof value === "number") return value;
      return null;
    };
    return (
      pickNumber(metadata?.source_question_number) ??
      pickNumber(payload.source_question_number) ??
      pickNumber(payload.question_number) ??
      pickNumber(payload.original_question_number) ??
      pickNumber(payload.normalized_index) ??
      pickNumber(payload.question_index) ??
      pickNumber(payload.local_number) ??
      draft.id
    );
  }, []);

  const pushOpenaiLog = useCallback((entry: OpenAILogEntry | null | undefined) => {
    if (!entry) return;
    setOpenaiLogs((prev) => {
      const next = [entry, ...prev];
      return next.slice(0, OPENAI_LOG_LIMIT);
    });
  }, []);

  const resetPreview = useCallback(() => {
    setFigurePreviewUrl((prev) => {
      if (prev?.startsWith("blob:")) {
        URL.revokeObjectURL(prev);
      }
      return null;
    });
  }, []);

  const loadImports = useCallback(async () => {
    try {
      setImportsLoading(true);
      setImportsError(null);
      const data = await fetchImportStatus();
      setJobs((data?.jobs as ImportJob[]) || []);
      const draftList = (data?.drafts as DraftPreview[]) || [];
      setDrafts(draftList);
      const map: Record<number, number> = {};
      draftList.forEach((draft) => {
        map[draft.id] = draft.figure_count || 0;
      });
      setFigureState(map);
    } catch (error: unknown) {
      setImportsError(extractErrorMessage(error, "Failed to load import status"));
    } finally {
      setImportsLoading(false);
    }
  }, []);

  const loadOpenaiLogs = useCallback(async () => {
    try {
      setLogsLoading(true);
      setLogsError(null);
      const data = await fetchOpenaiLogs(OPENAI_LOG_LIMIT);
      const logs = Array.isArray(data?.logs) ? (data.logs as OpenAILogEntry[]) : [];
      setOpenaiLogs(logs.slice(0, OPENAI_LOG_LIMIT));
    } catch (error: unknown) {
      setLogsError(extractErrorMessage(error, "Failed to load OpenAI logs"));
    } finally {
      setLogsLoading(false);
    }
  }, []);

  useEffect(() => {
    questionFiltersRef.current = questionFilters;
  }, [questionFilters]);

  const loadQuestions = useCallback(
    async (page = 1, nextFilters?: QuestionFilters) => {
      try {
        setQuestionsLoading(true);
        setQuestionsError(null);
        const filters = nextFilters ?? questionFiltersRef.current;
        const data = (await listQuestions({
          page,
          per_page: QUESTION_PAGE_SIZE,
          ...filters,
        })) as {
          items: QuestionRecord[];
          page: number;
          per_page: number;
          total: number;
        };
        setQuestions(data.items || []);
        setQuestionPage(data.page || 1);
        setQuestionTotal(data.total || 0);
        if (nextFilters !== undefined) {
          setQuestionFilters(nextFilters);
        }
      } catch (error: unknown) {
        setQuestionsError(extractErrorMessage(error, "Failed to load questions"));
      } finally {
        setQuestionsLoading(false);
      }
    },
    []
  );

  const upsertJob = useCallback((incoming: ImportJob) => {
    setJobs((prev) => {
      const filtered = prev.filter((job) => job.id !== incoming.id);
      const next = [incoming, ...filtered];
      return next.sort((a, b) => b.id - a.id).slice(0, 20);
    });
  }, []);

  const removeJob = useCallback((jobId: number) => {
    setJobs((prev) => prev.filter((job) => job.id !== jobId));
  }, []);

  useEffect(() => {
    loadImports();
    loadQuestions();
    loadOpenaiLogs();
  }, [loadImports, loadQuestions, loadOpenaiLogs]);

  useEffect(() => {
    return () => {
      resetPreview();
    };
  }, [resetPreview]);

  useEffect(() => {
    const token = getClientToken();
    if (!token) {
      return undefined;
    }
    const baseUrl = env.apiBaseUrl.replace(/\/$/, "");
    const url = new URL("/api/admin/questions/imports/events", baseUrl);
    url.searchParams.set("token", token);
    const source = new EventSource(url.toString());

    source.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload?.type === "snapshot" && Array.isArray(payload.payload)) {
          const snapshot = [...payload.payload].sort(
            (a, b) => Number(b.id || 0) - Number(a.id || 0)
          );
          setJobs(snapshot);
        } else if (payload?.type === "job" && payload.payload) {
          upsertJob(payload.payload as ImportJob);
        } else if (payload?.type === "job_removed" && payload?.payload?.id) {
          removeJob(Number(payload.payload.id));
        } else if (payload?.type === "openai_log" && payload?.payload) {
          pushOpenaiLog(payload.payload as OpenAILogEntry);
        }
        setEventError(null);
      } catch (err) {
        console.error("Failed to parse job event", err);
      }
    };

    source.onerror = () => {
      setEventError("Real-time updates disconnected. Refresh to reconnect.");
      source.close();
    };

    return () => {
      source.close();
    };
  }, [upsertJob, removeJob, pushOpenaiLog]);

  const activeJobs = useMemo(
    () =>
      jobs.filter((job) =>
        ["processing", "pending"].includes((job.status || "").toLowerCase())
      ),
    [jobs]
  );
  const recentJobs = useMemo(
    () =>
      jobs
        .filter(
          (job) =>
            !["processing", "pending"].includes((job.status || "").toLowerCase())
        )
        .slice(0, 5),
    [jobs]
  );
  const hasNextPage = useMemo(() => {
    return questionPage * QUESTION_PAGE_SIZE < questionTotal;
  }, [questionPage, questionTotal]);
  const hasPrevPage = questionPage > 1;
  const totalPages = Math.max(1, Math.ceil(questionTotal / QUESTION_PAGE_SIZE));
  const activeQuestionFilterLabel = useMemo(() => {
    if (questionFilters.question_id) {
      return `ID #${questionFilters.question_id}`;
    }
    if (questionFilters.question_uid) {
      return `UID ${questionFilters.question_uid}`;
    }
    if (questionFilters.source_id) {
      return `PDF #${questionFilters.source_id}`;
    }
    return null;
  }, [questionFilters]);

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setUploadError("Please select a PDF file.");
      return;
    }
    try {
      setUploadState("uploading");
      setUploadError(null);
      const response = await ingestPdf(file);
      setJobResult(response);
      await loadImports();
    } catch (error: unknown) {
      setUploadError(extractErrorMessage(error, "Upload failed"));
    } finally {
      setUploadState("idle");
    }
  }

  async function handleDelete() {
    const id = Number(questionId);
    if (!Number.isFinite(id)) {
      setDeleteMessage("Invalid question ID.");
      return;
    }
    try {
      setDeleteState("loading");
      setDeleteMessage(null);
      await deleteQuestion(id);
      setDeleteMessage(`Question ${id} deleted.`);
      await Promise.all([loadImports(), loadQuestions(questionPage)]);
    } catch (error: unknown) {
      setDeleteMessage(extractErrorMessage(error, "Delete failed."));
    } finally {
      setDeleteState("idle");
    }
  }

  async function handleRowDelete(id: number) {
    try {
      setRowDeleteId(id);
      setQuestionActionNotice(null);
      await deleteQuestion(id);
      const nextPage =
        questions.length === 1 && questionPage > 1 ? questionPage - 1 : questionPage;
      await Promise.all([loadImports(), loadQuestions(nextPage)]);
      setQuestionActionNotice({
        text: `Question ${id} deleted.`,
        tone: "success",
      });
    } catch (error: unknown) {
      setQuestionActionNotice({
        text: extractErrorMessage(error, "Delete failed."),
        tone: "error",
      });
    } finally {
      setRowDeleteId(null);
    }
  }
  async function handleClearExplanation(id: number) {
    try {
      setClearExplainId(id);
      setQuestionActionNotice(null);
      await clearQuestionExplanation(id);
      setQuestionActionNotice({
        text: `Cleared AI explanations for question ${id}.`,
        tone: "success",
      });
    } catch (error: unknown) {
      setQuestionActionNotice({
        text: extractErrorMessage(error, "Failed to clear explanations."),
        tone: "error",
      });
    } finally {
      setClearExplainId(null);
    }
  }

  async function handleQuestionSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSourceFilterValue("");
    const trimmed = questionSearchValue.trim();
    if (!trimmed) {
      await loadQuestions(1, {});
      return;
    }
    if (/^\d+$/.test(trimmed)) {
      await loadQuestions(1, { question_id: Number(trimmed) });
      return;
    }
    await loadQuestions(1, { question_uid: trimmed });
  }

  async function handleClearQuestionFilters() {
    setQuestionSearchValue("");
    setSourceFilterValue("");
    setQuestionFilters({});
    await loadQuestions(1, {});
  }

  async function handleSourceFilter(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = sourceFilterValue.trim();
    if (!trimmed) {
      setQuestionFilters({});
      await loadQuestions(1, {});
      return;
    }
    if (!/^\d+$/.test(trimmed)) {
      setQuestionActionNotice({
        text: "PDF source ID must be numeric.",
        tone: "error",
      });
      return;
    }
    setQuestionSearchValue("");
    setQuestionActionNotice(null);
    await loadQuestions(1, { source_id: Number(trimmed) });
  }


  async function handleDraftDelete(id: number) {
    try {
      setDraftActionMessage(null);
      setDraftDeleteId(id);
      await deleteDraft(id);
      await loadImports();
    } catch (error: unknown) {
      setDraftActionMessage(extractErrorMessage(error, "Failed to delete draft."));
    } finally {
      setDraftDeleteId(null);
    }
  }

  async function handleDraftPublish(draft: DraftPreview) {
    try {
      setDraftActionMessage(null);
      setDraftPublishId(draft.id);
      const requiresFigure = Boolean(draft.payload?.has_figure);
      const figureReady = (figureState[draft.id] ?? draft.figure_count ?? 0) > 0;
      if (requiresFigure && !figureReady) {
        setDraftActionMessage("Please capture and upload the chart before publishing.");
        return;
      }
      await publishDraft(draft.id);
      await Promise.all([loadImports(), loadQuestions(questionPage)]);
      setDraftActionMessage("Draft published to the question bank.");
    } catch (error: unknown) {
      setDraftActionMessage(extractErrorMessage(error, "Failed to publish draft."));
    } finally {
      setDraftPublishId(null);
    }
  }

  const handleCancelJob = useCallback(
    async (jobId: number) => {
      const confirmed = window.confirm(
        `Cancel job #${jobId}? This will stop ingestion and delete any intermediate drafts.`
      );
      if (!confirmed) return;
      try {
        setCancelJobId(jobId);
        await cancelImport(jobId);
        removeJob(jobId);
      } catch (error: unknown) {
        setImportsError(extractErrorMessage(error, "Failed to cancel job."));
      } finally {
        setCancelJobId(null);
      }
    },
    [removeJob]
  );

  const openFigureModal = useCallback(
    async (draft: DraftPreview) => {
      setFigureError(null);
      resetPreview();
      setFigureModal({
        draft,
        selection: null,
        zoom: 1,
        loading: true,
      });
      try {
        const [source, figuresResponse] = await Promise.all([
          fetchDraftFigureSource(draft.id),
          fetchDraftFigures(draft.id).catch(() => ({ figures: [] })),
        ]);
        const existingFigure = Array.isArray(figuresResponse?.figures)
          ? figuresResponse.figures[0]
          : undefined;
        const existingSelection =
          existingFigure?.bbox &&
          typeof existingFigure.bbox === "object" &&
          typeof existingFigure.bbox.width === "number" &&
          typeof existingFigure.bbox.height === "number"
            ? {
                x: Number(existingFigure.bbox.x ?? 0),
                y: Number(existingFigure.bbox.y ?? 0),
                width: Math.max(1, Number(existingFigure.bbox.width)),
                height: Math.max(1, Number(existingFigure.bbox.height)),
              }
            : null;
        if (existingFigure?.url) {
          setFigurePreviewUrl(existingFigure.url);
        }
        setFigureModal((prev) =>
          prev && prev.draft.id === draft.id
            ? { ...prev, source, selection: existingSelection, loading: false }
            : prev
        );
      } catch (error: unknown) {
        setFigureError(extractErrorMessage(error, "Failed to load figure reference"));
        setFigureModal((prev) =>
          prev && prev.draft.id === draft.id ? { ...prev, loading: false } : prev
        );
      }
    },
    [resetPreview]
  );

  const closeFigureModal = useCallback(() => {
    resetPreview();
    setFigureModal(null);
    setFigureError(null);
  }, [resetPreview]);

  const handleSelectionChange = useCallback((rect: SelectionRect | null) => {
    setFigureModal((prev) => (prev ? { ...prev, selection: rect } : prev));
  }, []);

  const handleZoomChange = useCallback((value: number) => {
    setFigureModal((prev) => (prev ? { ...prev, zoom: value } : prev));
  }, []);

  const refreshPreview = useCallback(
    async (rect: SelectionRect | null, source?: FigureSource) => {
      if (!source) {
        return;
      }
      if (!rect || rect.width < 5 || rect.height < 5) {
        setFigurePreviewUrl((prev) => {
          if (prev?.startsWith("blob:")) {
            URL.revokeObjectURL(prev);
          }
          return null;
        });
        return;
      }
      try {
        const blob = await getCroppedBlob(source.image, rect);
        const url = URL.createObjectURL(blob);
        setFigurePreviewUrl((prev) => {
          if (prev?.startsWith("blob:")) {
            URL.revokeObjectURL(prev);
          }
          return url;
        });
      } catch (error) {
        console.error("Failed to build preview", error);
      }
    },
    []
  );

  const handleSelectionComplete = useCallback(
    async (rect: SelectionRect | null) => {
      if (!figureModal?.source) return;
      await refreshPreview(rect, figureModal.source);
    },
    [figureModal?.source, refreshPreview]
  );

  const handleSaveFigure = useCallback(async () => {
    if (!figureModal?.draft || !figureModal.source) {
      return;
    }
    if (
      !figureModal.selection ||
      figureModal.selection.width < 5 ||
      figureModal.selection.height < 5
    ) {
      setFigureError("Please drag to select the figure region before saving.");
      return;
    }
    setFigureSaving(true);
    setFigureError(null);
    try {
      const blob = await getCroppedBlob(figureModal.source.image, figureModal.selection);
      const file = new File(
        [blob],
        `draft-${figureModal.draft.id}-${Date.now()}.png`,
        { type: blob.type || "image/png" }
      );
      const formData = new FormData();
      formData.append("image", file);
      formData.append(
        "bbox",
        JSON.stringify({
          ...figureModal.selection,
          imageWidth: figureModal.source.width,
          imageHeight: figureModal.source.height,
        })
      );
      await uploadDraftFigure(figureModal.draft.id, formData);
      await loadImports();
      setDraftActionMessage("Figure saved for draft.");
      setFigureModal(null);
    } catch (error: unknown) {
      setFigureError(extractErrorMessage(error, "Failed to save figure"));
    } finally {
      setFigureSaving(false);
    }
  }, [figureModal, loadImports]);

  const truncateStem = (value?: string | null) => {
    if (!value) return "No stem text";
    return value.length > 160 ? `${value.slice(0, 160)}…` : value;
  };

  const formatPageProgress = (job: ImportJob) => {
    const total = job.total_pages || 0;
    const current = job.current_page ?? job.processed_pages ?? 0;
    if (total > 0) {
      const clamped = Math.max(0, Math.min(current, total));
      return `Page ${clamped}/${total}`;
    }
    return current ? `Page ${current}` : "Page ?";
  };

  const formatRelative = (timestamp?: string | null) => {
    if (!timestamp) return "just now";
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) {
      return "Unknown time";
    }
    const diffMs = Date.now() - date.getTime();
    const diffSec = Math.max(0, Math.floor(diffMs / 1000));
    if (diffSec < 30) return "just now";
    if (diffSec < 60) return `${diffSec}s ago`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDay = Math.floor(diffHr / 24);
    return `${diffDay}d ago`;
  };

  const formatAbsolute = (timestamp?: string | null) => {
    if (!timestamp) return "";
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) {
      return "";
    }
    try {
      const formatter = new Intl.DateTimeFormat(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      });
      return formatter.format(date);
    } catch {
      return date.toISOString();
    }
  };

  const formatLastUpdated = (job: ImportJob) => {
    const relative = formatRelative(job.last_progress_at);
    const absolute = formatAbsolute(job.last_progress_at);
    return absolute ? `${relative} · ${absolute}` : relative;
  };

  const formatLogTimestamp = (value?: string) => {
    if (!value) return "—";
    try {
      return new Date(value).toLocaleTimeString();
    } catch {
      return value;
    }
  };

  const formatDuration = (ms?: number) => {
    if (ms === undefined || ms === null) return null;
    if (ms < 1000) {
      return `${ms} ms`;
    }
    const seconds = ms / 1000;
    if (seconds >= 10) {
      return `${seconds.toFixed(0)} s`;
    }
    return `${seconds.toFixed(1)} s`;
  };

  return (
    <>
      <AppShell>
        {isAdmin ? (
          <>
            <DashboardCard
              title="Temporary PDF Import"
              subtitle="Upload a PDF and send it to the AI ingestion pipeline."
            >
              <form className="space-y-3" onSubmit={handleUpload}>
          <input
            type="file"
            accept="application/pdf"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="w-full rounded-xl border border-white/15 bg-transparent px-4 py-2 text-sm text-white"
          />
          <button
            type="submit"
            className="rounded-xl bg-white/90 px-5 py-2 text-sm font-semibold text-[#050E1F]"
            disabled={uploadState === "uploading"}
          >
            {uploadState === "uploading" ? "Uploading..." : "Upload PDF"}
          </button>
          {uploadError && <p className="text-sm text-red-400">{uploadError}</p>}
          {!!jobResult && (
            <pre className="rounded-xl border border-white/10 bg-white/5 p-4 text-xs text-white/80 whitespace-pre-wrap">
              {JSON.stringify(jobResult, null, 2)}
            </pre>
          )}
              </form>
            </DashboardCard>

            <DashboardCard
              title="Delete Default Question"
              subtitle="Remove the seeded sample question by ID."
              tone="subtle"
            >
              <div className="flex items-center gap-3">
                <input
                  type="number"
                  min={1}
                  className="rounded-xl border border-white/15 bg-transparent px-4 py-2 text-sm text-white"
                  value={questionId}
                  onChange={(e) => setQuestionId(e.target.value)}
                />
                <button
                  className="rounded-xl border border-white/20 px-4 py-2 text-sm text-white/80"
                  onClick={handleDelete}
                  disabled={deleteState === "loading"}
                >
                  {deleteState === "loading" ? "Deleting..." : "Delete"}
                </button>
              </div>
              {deleteMessage && (
                <p className="mt-2 text-sm text-white/70">{deleteMessage}</p>
              )}
            </DashboardCard>

            <DashboardCard
              title="Import Progress"
              subtitle="Monitor ingestion jobs and normalized drafts"
              tone="subtle"
            >
        {importsLoading ? (
          <p className="text-sm text-white/60">Loading progress...</p>
        ) : importsError ? (
          <p className="text-sm text-red-400">{importsError}</p>
        ) : (
          <div className="space-y-4">
            {eventError && (
              <p className="rounded-lg border border-amber-400/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                {eventError}
              </p>
            )}
            <div>
              <p className="text-sm font-semibold text-white/80 mb-2">
                Active Imports
              </p>
              {activeJobs.length === 0 ? (
                <p className="text-sm text-white/50">No active jobs.</p>
              ) : (
                <div className="space-y-2 text-sm text-white/70">
                  {activeJobs.map((job) => (
                    <div
                      key={job.id}
                      className="rounded-xl border border-white/10 px-4 py-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between"
                    >
                      <div className="flex-1 space-y-1">
                        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between">
                          <span className="font-semibold text-white">
                            Job #{job.id}
                          </span>
                          <span className="text-xs text-white/70">
                            {formatPageProgress(job)}
                          </span>
                        </div>
                        <p className="text-xs text-white/60">
                          {job.status_message || `Status: ${job.status}`}
                        </p>
                        <p className="text-xs text-white/60">
                          Questions {job.parsed_questions}
                          {job.total_blocks ? ` / ${job.total_blocks}` : ""}{" "}
                          {job.ingest_strategy ? `· ${job.ingest_strategy}` : ""}
                        </p>
                        <p className="text-xs text-white/40">
                          Updated {formatLastUpdated(job)}
                        </p>
                        {job.error_message && (
                          <p className="text-xs text-red-300">
                            Error: {job.error_message}
                          </p>
                        )}
                      </div>
                      {["processing", "pending"].includes(
                        (job.status || "").toLowerCase()
                      ) && (
                        <button
                          className="rounded-xl border border-white/20 px-3 py-1 text-xs text-white/80"
                          onClick={() => handleCancelJob(job.id)}
                          disabled={cancelJobId === job.id}
                        >
                          {cancelJobId === job.id ? "Cancelling..." : "Cancel"}
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div>
              <p className="text-sm font-semibold text-white/80 mb-2">
                Recent Jobs
              </p>
              {recentJobs.length === 0 ? (
                <p className="text-sm text-white/50">
                  No recently finished jobs.
                </p>
              ) : (
                <div className="space-y-2 text-sm text-white/70">
                  {recentJobs.map((job) => (
                    <div
                      key={job.id}
                      className="rounded-xl border border-white/10 px-4 py-2"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-white">
                          Job #{job.id}
                        </span>
                        <span className="text-xs text-white/60 uppercase">
                          {job.status}
                        </span>
                      </div>
                      <p className="text-xs text-white/60">
                        Finished {formatLastUpdated(job)}
                      </p>
                      {job.error_message && (
                        <p className="text-xs text-red-300">
                          Error: {job.error_message}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
            </DashboardCard>

            <DashboardCard
              title="OpenAI API Logs"
              subtitle={`Recent OpenAI calls (latest ${OPENAI_LOG_LIMIT})`}
              tone="subtle"
            >
        <div className="mb-3 flex flex-wrap items-center justify-between text-xs text-white/60">
          <span>
            Showing {openaiLogs.length} entr{openaiLogs.length === 1 ? "y" : "ies"}
            {logsLoading ? " · refreshing…" : ""}
          </span>
          <div className="flex items-center gap-2">
            {logsError && <span className="text-red-400">{logsError}</span>}
            <button
              className="rounded-xl border border-white/20 px-3 py-1 text-xs text-white/80"
              onClick={loadOpenaiLogs}
              disabled={logsLoading}
            >
              {logsLoading ? "Loading..." : "Refresh"}
            </button>
          </div>
        </div>
        {openaiLogs.length === 0 && !logsLoading ? (
          <p className="text-sm text-white/50">No log entries yet.</p>
        ) : (
          <div className="space-y-2 text-xs text-white/70 max-h-[70vh] min-h-[320px] overflow-auto pr-1 w-full">
            {openaiLogs.map((entry, index) => (
              <div
                key={`${entry.timestamp}-${index}`}
                className="rounded-xl border border-white/10 bg-black/30 px-3 py-2"
              >
                <div className="flex items-center justify-between text-white">
                  <span>{formatLogTimestamp(entry.timestamp)}</span>
                  <span className="text-[10px] uppercase tracking-wide text-white/70">
                    {entry.kind}
                  </span>
                </div>
                <p className="text-[11px] text-white/70">
                  Job #{entry.job_id ?? "—"} · {entry.stage || entry.purpose || "Unknown stage"}
                  {typeof entry.page === "number"
                    ? ` · page ${entry.page}${entry.total_pages ? `/${entry.total_pages}` : ""}`
                    : ""}
                  {typeof entry.normalized_count === "number" ? ` · questions ${entry.normalized_count}` : ""}
                </p>
                <p className="text-[11px] text-white/60">
                  {typeof entry.attempt === "number"
                    ? `Attempt ${entry.attempt}/${entry.max_attempts ?? "?"}`
                    : "Attempt —"}
                  {entry.state ? ` · ${entry.state}` : ""}
                  {entry.model ? ` · ${entry.model}` : ""}
                  {entry.status_code ? ` · HTTP ${entry.status_code}` : ""}
                  {entry.duration_ms !== undefined && entry.duration_ms !== null
                    ? ` · ${formatDuration(entry.duration_ms)}`
                    : ""}
                </p>
                {entry.message && (
                  <p className="text-[11px] text-white/60">Message: {entry.message}</p>
                )}
                {typeof entry.wait_seconds === "number" && entry.wait_seconds > 0 && (
                  <p className="text-[11px] text-white/50">
                    Retry in {entry.wait_seconds.toFixed(1)}s
                  </p>
                )}
                {entry.error && (
                  <p className="text-[11px] text-red-300 break-words">Error: {entry.error}</p>
                )}
              </div>
            ))}
          </div>
        )}
            </DashboardCard>

            <DashboardCard
              title="Draft Review"
              subtitle="Inspect AI-normalized drafts before publishing them to the live bank."
              tone="subtle"
            >
        {draftActionMessage && (
          <p className="mb-3 text-sm text-white/70">{draftActionMessage}</p>
        )}
        {drafts.length === 0 ? (
          <p className="text-sm text-white/50">
            No drafts available. Upload a PDF to generate new drafts.
          </p>
        ) : (
          <div className="space-y-3">
            {drafts.slice(0, 10).map((draft) => {
              const requiresFigure = Boolean(draft.payload?.has_figure);
              const figureReady = (figureState[draft.id] ?? draft.figure_count ?? 0) > 0;
              const pdfQuestionNumber = getPdfQuestionNumber(draft);
              const localQuestionNumber = getLocalQuestionNumber(draft);
              return (
                <div
                  key={draft.id}
                  className="rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/80"
                >
                  <div className="mb-2">
                    <p className="font-semibold text-white">
                      Draft #{draft.id} · Job {draft.job_id}
                    </p>
                    <p className="text-xs text-white/60">
                      {draft.payload?.section || "Unknown section"}
                    </p>
                    <p className="text-xs text-white/50">
                      PDF Question: {pdfQuestionNumber ?? "—"} · Local Draft ID: {localQuestionNumber}
                    </p>
                    <p className="text-xs text-white/50">
                      PDF Source:{" "}
                      {draft.source_id ? `#${draft.source_id}` : "—"}
                      {draft.source?.filename ? ` · ${draft.source.filename}` : ""}
                    </p>
                  </div>
                  <p className="text-xs text-white/70 mb-3">
                    {truncateStem(draft.payload?.stem_text)}
                  </p>
                  {requiresFigure && (
                    <p
                      className={`mb-2 text-xs ${
                        figureReady ? "text-emerald-300" : "text-amber-300"
                      }`}
                    >
                      {figureReady
                        ? "Figure ready · you can publish this question."
                        : "Figure screenshot required before publishing."}
                    </p>
                  )}
                  <div className="mb-2 flex flex-wrap gap-2">
                    {requiresFigure && (
                      <button
                        className="rounded-xl border border-white/30 px-3 py-1 text-xs text-white/80"
                        onClick={() => openFigureModal(draft)}
                      >
                        {figureReady ? "Edit figure" : "Prepare figure"}
                      </button>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      className="rounded-xl bg-white/90 px-3 py-1 text-xs font-semibold text-[#050E1F]"
                      onClick={() => handleDraftPublish(draft)}
                      disabled={draftPublishId === draft.id || (requiresFigure && !figureReady)}
                      title={
                        requiresFigure && !figureReady
                          ? "Upload the figure snapshot before publishing."
                          : undefined
                      }
                    >
                      {draftPublishId === draft.id ? "Publishing..." : "Publish to bank"}
                    </button>
                    <button
                      className="rounded-xl border border-white/30 px-3 py-1 text-xs text-white/80"
                      onClick={() => handleDraftDelete(draft.id)}
                      disabled={draftDeleteId === draft.id}
                    >
                      {draftDeleteId === draft.id ? "Deleting..." : "Delete draft"}
                    </button>
                  </div>
                </div>
              );
            })}
            {drafts.length > 10 && (
              <p className="text-xs text-white/50">
                Showing 10 of {drafts.length} drafts. Use the API to access more.
              </p>
            )}
          </div>
        )}
            </DashboardCard>

            <DashboardCard
              title="Question Bank (Temporary)"
              subtitle="Browse recently ingested questions and delete incorrect entries."
              tone="subtle"
            >
        <form
          className="mb-3 flex w-full flex-col gap-2 text-sm text-white/70 md:flex-row"
          onSubmit={handleQuestionSearch}
        >
          <input
            value={questionSearchValue}
            onChange={(e) => setQuestionSearchValue(e.target.value)}
            placeholder="Search by numeric ID or UID (e.g., 214 or QAB12CD)"
            className="flex-1 rounded-xl border border-white/20 bg-transparent px-3 py-2 text-sm text-white placeholder:text-white/40 focus:border-white/60 focus:outline-none"
          />
          <div className="flex gap-2">
            <button
              type="submit"
              className="rounded-xl border border-white/20 px-3 py-2 text-xs font-semibold text-white/80 hover:border-white/40"
              disabled={questionsLoading}
            >
              Locate
            </button>
          </div>
        </form>
        <form
          className="mb-3 flex w-full flex-col gap-2 text-sm text-white/70 md:flex-row"
          onSubmit={handleSourceFilter}
        >
          <input
            value={sourceFilterValue}
            onChange={(e) => setSourceFilterValue(e.target.value)}
            placeholder="Filter by PDF source ID (e.g., 12)"
            className="flex-1 rounded-xl border border-white/20 bg-transparent px-3 py-2 text-sm text-white placeholder:text-white/40 focus:border-white/60 focus:outline-none"
          />
          <div className="flex gap-2">
            <button
              type="submit"
              className="rounded-xl border border-white/20 px-3 py-2 text-xs font-semibold text-white/80 hover:border-white/40"
              disabled={questionsLoading}
            >
              Apply PDF filter
            </button>
          </div>
        </form>
        {(questionFilters.question_id ||
          questionFilters.question_uid ||
          questionFilters.source_id) && (
          <div className="mb-2">
            <button
              type="button"
              className="rounded-xl border border-white/10 px-3 py-2 text-xs text-white/60 hover:border-white/30"
              onClick={handleClearQuestionFilters}
              disabled={questionsLoading}
            >
              Clear filters
            </button>
          </div>
        )}
        {activeQuestionFilterLabel && (
          <p className="mb-2 text-xs text-white/60">
            Filtering by {activeQuestionFilterLabel}. Showing newest matches first.
          </p>
        )}
        {questionActionNotice && (
          <p
            className={`mb-2 text-xs ${
              questionActionNotice.tone === "success" ? "text-emerald-300" : "text-red-400"
            }`}
          >
            {questionActionNotice.text}
          </p>
        )}
        <div className="mb-3 flex flex-wrap items-center gap-3 text-sm text-white/70">
          <span>
            Page {questionPage} / {totalPages} · {questionTotal} questions
          </span>
          <button
            className="rounded-xl border border-white/20 px-3 py-1 text-xs text-white/80"
            onClick={() => loadQuestions(questionPage)}
            disabled={questionsLoading}
          >
            Refresh
          </button>
        </div>
        {questionsError ? (
          <p className="text-sm text-red-400">{questionsError}</p>
        ) : questions.length === 0 ? (
          questionsLoading ? (
            <p className="text-sm text-white/60">Loading question list...</p>
          ) : (
            <p className="text-sm text-white/50">
              No questions found. Import a PDF to populate the bank.
            </p>
          )
        ) : (
          <>
            <div className="space-y-2">
              {questions.map((question) => (
                <div
                  key={question.id}
                  className="rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/80 flex flex-col gap-2 md:flex-row md:items-center md:gap-4"
                >
                  <div className="flex-1">
                    <p className="font-semibold text-white">
                      #{question.id} · {question.question_uid ?? "No UID"} · {question.section}
                      {question.sub_section ? ` · ${question.sub_section}` : ""}
                    </p>
                    <p className="text-xs text-white/70">
                      {truncateStem(question.stem_text)}
                    </p>
                    <p className="text-xs text-white/50">
                      PDF Source:{" "}
                      {question.source_id ? `#${question.source_id}` : "—"}
                      {question.source?.filename ? ` · ${question.source.filename}` : ""}
                    </p>
                  </div>
                  <button
                    className="self-start rounded-xl border border-white/20 px-3 py-1 text-xs text-white/80"
                    onClick={() => handleClearExplanation(question.id)}
                    disabled={clearExplainId === question.id}
                  >
                    {clearExplainId === question.id ? "Resetting..." : "Reset AI explanation"}
                  </button>
                  <button
                    className="self-start rounded-xl border border-white/20 px-3 py-1 text-xs text-white/80"
                    onClick={() => handleRowDelete(question.id)}
                    disabled={rowDeleteId === question.id}
                  >
                    {rowDeleteId === question.id ? "Deleting..." : "Delete"}
                  </button>
                </div>
              ))}
            </div>
            {questionsLoading && (
              <p className="text-xs text-white/50">Refreshing question list...</p>
            )}
          </>
        )}
        <div className="mt-4 flex items-center gap-3 text-xs text-white/60">
          <button
            className="rounded-xl border border-white/15 px-3 py-1 disabled:opacity-40"
            onClick={() => hasPrevPage && loadQuestions(questionPage - 1)}
            disabled={!hasPrevPage || questionsLoading}
          >
            Previous
          </button>
          <button
            className="rounded-xl border border-white/15 px-3 py-1 disabled:opacity-40"
            onClick={() => hasNextPage && loadQuestions(questionPage + 1)}
            disabled={!hasNextPage || questionsLoading}
          >
            Next
          </button>
        </div>
            </DashboardCard>
          </>
        ) : (
          <DashboardCard title="Admin Only" subtitle="">
            <p className="text-sm text-white/60">
              The temporary import tool is only available for administrator accounts.
            </p>
          </DashboardCard>
        )}
      </AppShell>

      {isAdmin && figureModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 px-4 py-6">
          <div className="w-full max-w-4xl rounded-2xl bg-[#050E1F] shadow-2xl">
            <div className="max-h-[90vh] overflow-y-auto p-5 space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-base font-semibold text-white">
                    Capture figure · Draft #{figureModal.draft.id}
                  </p>
                  <p className="text-xs text-white/60">
                    Page {figureModal.source?.page ?? "…"}
                  </p>
                </div>
                <button
                  className="rounded-full border border-white/20 p-1 text-white/70 hover:text-white"
                  onClick={closeFigureModal}
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="rounded-xl border border-white/10 bg-black/20 p-4">
                {figureModal.loading ? (
                  <div className="flex h-[360px] items-center justify-center text-sm text-white/60">
                    Loading page preview...
                  </div>
                ) : figureModal.source ? (
                  <>
                    <div className="max-h-[560px] overflow-auto rounded-xl bg-black/30 p-4">
                      <FigureCropper
                        source={figureModal.source}
                        selection={figureModal.selection}
                        zoom={figureModal.zoom}
                        onSelectionChange={handleSelectionChange}
                        onSelectionComplete={handleSelectionComplete}
                        onZoomChange={(value) => handleZoomChange(value)}
                      />
                    </div>
                    <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-white/60">
                      <span>
                        Click and drag to highlight the exact chart/table. Drag the white handles to
                        adjust the selection.
                      </span>
                      {figureModal.selection && (
                        <button
                          className="rounded-full border border-white/20 px-3 py-1 text-xs text-white/70 hover:text-white"
                          onClick={() => {
                            handleSelectionChange(null);
                            resetPreview();
                          }}
                        >
                          Clear selection
                        </button>
                      )}
                    </div>
                    <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-white/60">
                      <span>Zoom</span>
                      <input
                        type="range"
                        min={0.8}
                        max={2.5}
                        step={0.1}
                        value={figureModal.zoom}
                        onChange={(e) => handleZoomChange(Number(e.target.value))}
                        className="w-40 accent-white"
                      />
                      <span>{figureModal.zoom.toFixed(2)}x</span>
                    </div>
                    {figurePreviewUrl && (
                      <div className="mt-4">
                        <p className="mb-2 text-xs text-white/60">Preview</p>
                        <div className="overflow-hidden rounded-xl border border-white/15 bg-black/40 p-2">
                          <img
                            src={figurePreviewUrl}
                            alt="Figure preview"
                            className="max-h-48 w-auto rounded"
                          />
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="flex h-[360px] items-center justify-center text-sm text-red-300">
                    Unable to load page preview.
                  </div>
                )}
              </div>
              {figureError && (
                <p className="text-xs text-red-400">{figureError}</p>
              )}
              <div className="flex flex-wrap justify-end gap-3">
                <button
                  className="rounded-xl border border-white/20 px-4 py-2 text-sm text-white/80"
                  onClick={closeFigureModal}
                  disabled={figureSaving}
                >
                  Cancel
                </button>
                <button
                  className="rounded-xl bg-white px-4 py-2 text-sm font-semibold text-[#050E1F]"
                  onClick={handleSaveFigure}
                  disabled={
                    figureSaving ||
                    figureModal.loading ||
                    !figureModal.source ||
                    !figureModal.selection
                  }
                >
                  {figureSaving ? "Saving..." : "Save figure"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

