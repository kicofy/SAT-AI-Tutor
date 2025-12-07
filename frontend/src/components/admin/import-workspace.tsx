"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { isAxiosError } from "axios";
import { useMutation } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/app-shell";
import { DashboardCard } from "@/components/ui/dashboard-card";
import { FigureCropper } from "@/components/admin/figure-cropper";
import { FigureSource } from "@/types/figure";
import { AdminQuestion, AdminSource } from "@/types/admin";
import {
  ingestPdf,
  fetchImportStatus,
  deleteDraft,
  publishDraft,
  cancelImport,
  fetchDraftFigureSource,
  uploadDraftFigure,
  fetchDraftFigures,
  fetchOpenaiLogs,
  updateDraft,
} from "@/services/admin";
import { useAuth } from "@/hooks/use-auth";
import { extractErrorMessage } from "@/lib/errors";
import { env } from "@/lib/env";
import { getClientToken } from "@/lib/auth-storage";
import { getCroppedBlob, SelectionRect } from "@/lib/image";
import { X } from "lucide-react";

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
  is_verified?: boolean;
  created_at?: string;
  updated_at?: string;
};

type FigureModalState = {
  draft: DraftPreview;
  source?: FigureSource;
  selection: SelectionRect | null;
  zoom: number;
  loading: boolean;
};

type DuplicatePromptState = {
  file: File;
  filename: string;
  existing?: AdminSource | null;
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

type ImportWorkspaceProps = {
  variant?: "standalone" | "embedded";
};

export function ImportWorkspace({ variant = "standalone" }: ImportWorkspaceProps) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [file, setFile] = useState<File | null>(null);
  const [uploadState, setUploadState] = useState<"idle" | "uploading">("idle");
  const [jobResult, setJobResult] = useState<unknown>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<ImportJob[]>([]);
  const [drafts, setDrafts] = useState<DraftPreview[]>([]);
  const [importsLoading, setImportsLoading] = useState(false);
  const [importsError, setImportsError] = useState<string | null>(null);

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
  const [duplicatePrompt, setDuplicatePrompt] = useState<DuplicatePromptState | null>(null);
  const [duplicateConfirming, setDuplicateConfirming] = useState(false);
  const [openaiLogs, setOpenaiLogs] = useState<OpenAILogEntry[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState<string | null>(null);
  const [selectedDraftId, setSelectedDraftId] = useState<number | null>(null);

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

  const syncFigureState = useCallback((draftList: DraftPreview[]) => {
    const map: Record<number, number> = {};
    draftList.forEach((draft) => {
      map[draft.id] = draft.figure_count || 0;
    });
    setFigureState(map);
  }, []);

  const loadImports = useCallback(async () => {
    try {
      setImportsLoading(true);
      setImportsError(null);
      const data = await fetchImportStatus();
      const jobList = (data?.jobs as ImportJob[]) || [];
      const draftList = (data?.drafts as DraftPreview[]) || [];
      setJobs(jobList);
      setDrafts(draftList);
      syncFigureState(draftList);
    } catch (error: unknown) {
      setImportsError(extractErrorMessage(error, "Failed to load import status"));
    } finally {
      setImportsLoading(false);
    }
  }, [syncFigureState]);

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

  const upsertDraft = useCallback(
    (incoming: DraftPreview) => {
      setDrafts((prev) => {
        const filtered = prev.filter((draft) => draft.id !== incoming.id);
        const next = [incoming, ...filtered];
        syncFigureState(next);
        return next.sort((a, b) => b.id - a.id);
      });
    },
    [syncFigureState]
  );

  const removeDraft = useCallback(
    (draftId: number) => {
      setDrafts((prev) => {
        const next = prev.filter((draft) => draft.id !== draftId);
        syncFigureState(next);
        return next;
      });
    },
    [syncFigureState]
  );

  useEffect(() => {
    loadImports();
    loadOpenaiLogs();
  }, [loadImports, loadOpenaiLogs]);

  useEffect(() => {
    if (drafts.length === 0) {
      setSelectedDraftId(null);
      return;
    }
    if (!selectedDraftId || !drafts.some((draft) => draft.id === selectedDraftId)) {
      setSelectedDraftId(drafts[0]?.id ?? null);
    }
  }, [drafts, selectedDraftId]);

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
        } else if (payload?.type === "draft_snapshot" && Array.isArray(payload.payload)) {
          setDrafts(payload.payload as DraftPreview[]);
          syncFigureState(payload.payload as DraftPreview[]);
        } else if (payload?.type === "job" && payload.payload) {
          upsertJob(payload.payload as ImportJob);
        } else if (payload?.type === "job_removed" && payload?.payload?.id) {
          removeJob(Number(payload.payload.id));
        } else if (payload?.type === "draft" && payload.payload) {
          upsertDraft(payload.payload as DraftPreview);
        } else if (payload?.type === "draft_removed" && payload?.payload?.id) {
          removeDraft(Number(payload.payload.id));
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
  }, [upsertJob, removeJob, pushOpenaiLog, upsertDraft, removeDraft, syncFigureState]);

  const selectedDraft = useMemo(
    () => drafts.find((draft) => draft.id === selectedDraftId) || null,
    [drafts, selectedDraftId]
  );

  const draftUpdateMutation = useMutation({
    mutationFn: (payload: { draftId: number; data: Partial<AdminQuestion> }) =>
      updateDraft(payload.draftId, payload.data),
    onSuccess: (response) => {
      if (response?.draft) {
        upsertDraft(response.draft as DraftPreview);
      }
      setDraftActionMessage("Draft updated.");
    },
    onError: (error: unknown) => {
      setDraftActionMessage(extractErrorMessage(error, "Failed to update draft."));
    },
  });

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
  const runIngest = useCallback(
    async (selectedFile: File, options?: { force?: boolean }) => {
      try {
        setUploadState("uploading");
        setUploadError(null);
        const response = await ingestPdf(selectedFile, { force: options?.force });
        setJobResult(response);
        await loadImports();
        setDuplicatePrompt(null);
      } catch (error: unknown) {
        if (
          isAxiosError(error) &&
          error.response?.status === 409 &&
          error.response?.data?.error === "duplicate_source"
        ) {
          const existingSource = error.response.data?.source as AdminSource | undefined;
          setDuplicatePrompt({
            file: selectedFile,
            filename: selectedFile.name,
            existing: existingSource,
          });
          return;
        }
        setUploadError(extractErrorMessage(error, "Upload failed"));
      } finally {
        setUploadState("idle");
        setDuplicateConfirming(false);
      }
    },
    [loadImports]
  );
  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setUploadError("Please select a PDF file.");
      return;
    }
    await runIngest(file);
  }

  const handleDuplicateCancel = useCallback(() => {
    setDuplicatePrompt(null);
    setDuplicateConfirming(false);
  }, []);

  const handleDuplicateConfirm = useCallback(async () => {
    if (!duplicatePrompt?.file) {
      setDuplicatePrompt(null);
      return;
    }
    setDuplicateConfirming(true);
    await runIngest(duplicatePrompt.file, { force: true });
  }, [duplicatePrompt, runIngest]);


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
      await loadImports();
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

  const formatSourceTimestamp = (value?: string | null) => {
    if (!value) return "—";
    try {
      return new Date(value).toLocaleString();
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

  const workspaceCore = (
    <>
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

            <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
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
                  className={`rounded-xl border px-4 py-3 text-sm text-white/80 transition ${
                    selectedDraftId === draft.id
                      ? "border-white/60 bg-white/10"
                      : "border-white/10 bg-white/5 hover:border-white/30"
                  }`}
                  onClick={() => setSelectedDraftId(draft.id)}
                  role="button"
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
                title="Draft editor"
                subtitle="Edit the draft content before publishing."
                tone="subtle"
              >
        {selectedDraft ? (
          <DraftEditor
            draft={selectedDraft}
            onSubmit={(payload) =>
              draftUpdateMutation.mutate({ draftId: selectedDraft.id, data: payload })
            }
            isSaving={draftUpdateMutation.isLoading}
            error={draftUpdateMutation.error}
          />
        ) : (
          <p className="text-sm text-white/60">
            Select a draft from the list to review and edit its content.
          </p>
        )}
              </DashboardCard>
            </div>

          </>
        ) : (
          <DashboardCard title="Admin Only" subtitle="">
            <p className="text-sm text-white/60">
              The temporary import tool is only available for administrator accounts.
            </p>
          </DashboardCard>
        )}
    </>
  );

  const figureModalOverlay = !isAdmin || !figureModal ? null : (
    <div className="modal-overlay fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
      <div className="modal-panel flex max-h-[95vh] w-full max-w-4xl flex-col rounded-2xl bg-[#050E1F] shadow-2xl">
        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-base font-semibold text-white">
                Capture figure · Draft #{figureModal.draft.id}
              </p>
              <p className="text-xs text-white/60">Page {figureModal.source?.page ?? "…"}</p>
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
                <div className="rounded-xl bg-black/30 p-4">
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
                    Click and drag to highlight the exact chart/table. Drag the white handles to adjust
                    the selection.
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
                      <img src={figurePreviewUrl} alt="Figure preview" className="max-h-48 w-auto rounded" />
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
        </div>

        {figureError && <p className="px-5 text-xs text-red-400">{figureError}</p>}

        <div className="flex flex-wrap justify-end gap-3 border-t border-white/5 px-5 py-4">
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
              figureSaving || figureModal.loading || !figureModal.source || !figureModal.selection
            }
          >
            {figureSaving ? "Saving..." : "Save figure"}
          </button>
        </div>
      </div>
    </div>
  );

  const duplicateModalOverlay = !duplicatePrompt
    ? null
    : (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur">
          <div className="card-ambient w-full max-w-md rounded-2xl border border-white/10 bg-[#050E1F] p-6 shadow-2xl">
            <p className="text-xs uppercase tracking-[0.3em] text-white/50">Duplicate filename</p>
            <h2 className="mt-2 text-xl font-semibold text-white">PDF already exists</h2>
            <p className="mt-2 text-sm text-white/70">
              A PDF named <span className="text-white">{duplicatePrompt.filename}</span> is already in Collections.
              Uploading again may create a new source with the same title. Continue?
            </p>
            {duplicatePrompt.existing && (
              <div className="mt-4 rounded-xl border border-white/10 bg-white/5 p-4 text-sm text-white/80">
                <p className="font-semibold">
                  Existing PDF · #{duplicatePrompt.existing.id}
                </p>
                <p className="text-xs text-white/60">
                  Uploaded {formatSourceTimestamp(duplicatePrompt.existing.created_at)}
                </p>
                {typeof duplicatePrompt.existing.total_pages === "number" && (
                  <p className="text-xs text-white/60">
                    Pages: {duplicatePrompt.existing.total_pages}
                  </p>
                )}
              </div>
            )}
            <div className="mt-6 flex flex-wrap justify-end gap-3">
              <button
                className="rounded-xl border border-white/30 px-4 py-2 text-sm text-white/80"
                onClick={handleDuplicateCancel}
                disabled={duplicateConfirming}
              >
                Cancel
              </button>
              <button
                className="rounded-xl bg-white px-4 py-2 text-sm font-semibold text-[#050E1F]"
                onClick={handleDuplicateConfirm}
                disabled={duplicateConfirming}
              >
                {duplicateConfirming ? "Uploading..." : "Upload anyway"}
              </button>
            </div>
          </div>
        </div>
      );

  if (variant === "standalone") {
    return (
      <>
        <AppShell>{workspaceCore}</AppShell>
        {figureModalOverlay}
        {duplicateModalOverlay}
      </>
    );
  }

  return (
    <>
      <div className="flex w-full flex-col gap-6 text-white">
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-white/50">Upload & Import</p>
          <h1 className="mt-1 text-2xl font-semibold text-white">AI Import Workspace</h1>
          <p className="text-sm text-white/60">
            Upload PDFs, monitor AI parsing, and review drafts without leaving the admin console.
          </p>
        </div>
        {workspaceCore}
      </div>
      {figureModalOverlay}
      {duplicateModalOverlay}
    </>
  );
}

export default ImportWorkspace;

type DraftEditorProps = {
  draft: DraftPreview;
  onSubmit: (payload: Partial<AdminQuestion>) => void;
  isSaving: boolean;
  error: unknown;
};

function DraftEditor({ draft, onSubmit, isSaving, error }: DraftEditorProps) {
  const payload = draft.payload || {};
  const [stemText, setStemText] = useState(payload.stem_text ?? "");
  const [section, setSection] = useState(payload.section ?? "RW");
  const [subSection, setSubSection] = useState(payload.sub_section ?? "");
  const [difficulty, setDifficulty] = useState<number | "">(payload.difficulty_level ?? "");
  const [correctAnswer, setCorrectAnswer] = useState(payload.correct_answer?.value ?? "");
  const [choices, setChoices] = useState<Record<string, string>>(
    Array.isArray(payload.choices)
      ? payload.choices.reduce<Record<string, string>>((acc, entry, index) => {
          if (entry && typeof entry === "object") {
            const label = entry.label || String.fromCharCode(65 + index);
            acc[label.toUpperCase()] = entry.text || entry.value || "";
          }
          return acc;
        }, {})
      : payload.choices || {}
  );
  const [passageText, setPassageText] = useState(
    typeof payload.passage === "string" ? payload.passage : payload.passage?.content_text ?? ""
  );
  const [passageMetaRaw, setPassageMetaRaw] = useState(
    typeof payload.passage === "object" && payload.passage?.metadata
      ? JSON.stringify(payload.passage.metadata, null, 2)
      : ""
  );
  const [skillTagsInput, setSkillTagsInput] = useState((payload.skill_tags || []).join(", "));
  const [estimatedTime, setEstimatedTime] = useState<number | "">(payload.estimated_time_sec ?? "");
  const [irtA, setIrtA] = useState<number | "">(payload.irt_a ?? "");
  const [irtB, setIrtB] = useState<number | "">(payload.irt_b ?? "");
  const [pageRef, setPageRef] = useState<number | "">(
    typeof payload.source_page === "number" ? payload.source_page : payload.page ?? ""
  );
  const [indexInSet, setIndexInSet] = useState<number | "">(payload.index_in_set ?? "");
  const [metadataRaw, setMetadataRaw] = useState(
    payload.metadata ? JSON.stringify(payload.metadata, null, 2) : ""
  );
  const [hasFigure, setHasFigure] = useState(Boolean(payload.has_figure));
  const [metadataError, setMetadataError] = useState<string | null>(null);
  const [passageMetaError, setPassageMetaError] = useState<string | null>(null);

  useEffect(() => {
    const nextPayload = draft.payload || {};
    setStemText(nextPayload.stem_text ?? "");
    setSection(nextPayload.section ?? "RW");
    setSubSection(nextPayload.sub_section ?? "");
    setDifficulty(nextPayload.difficulty_level ?? "");
    setCorrectAnswer(nextPayload.correct_answer?.value ?? "");
    setChoices(
      Array.isArray(nextPayload.choices)
        ? nextPayload.choices.reduce<Record<string, string>>((acc, entry, index) => {
            if (entry && typeof entry === "object") {
              const label = entry.label || String.fromCharCode(65 + index);
              acc[label.toUpperCase()] = entry.text || entry.value || "";
            }
            return acc;
          }, {})
        : nextPayload.choices || {}
    );
    setPassageText(
      typeof nextPayload.passage === "string"
        ? nextPayload.passage
        : nextPayload.passage?.content_text ?? ""
    );
    setPassageMetaRaw(
      typeof nextPayload.passage === "object" && nextPayload.passage?.metadata
        ? JSON.stringify(nextPayload.passage.metadata, null, 2)
        : ""
    );
    setSkillTagsInput((nextPayload.skill_tags || []).join(", "));
    setEstimatedTime(nextPayload.estimated_time_sec ?? "");
    setIrtA(nextPayload.irt_a ?? "");
    setIrtB(nextPayload.irt_b ?? "");
    setPageRef(
      typeof nextPayload.source_page === "number"
        ? nextPayload.source_page
        : nextPayload.page ?? ""
    );
    setIndexInSet(nextPayload.index_in_set ?? "");
    setMetadataRaw(nextPayload.metadata ? JSON.stringify(nextPayload.metadata, null, 2) : "");
    setHasFigure(Boolean(nextPayload.has_figure));
    setMetadataError(null);
    setPassageMetaError(null);
  }, [draft]);

  const choiceKeys = useMemo(() => {
    const keys = Object.keys(choices);
    return keys.length ? keys : ["A", "B", "C", "D"];
  }, [choices]);

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        let parsedMetadata: Record<string, unknown> | null = null;
        let parsedPassageMetadata: Record<string, unknown> | null = null;

        if (metadataRaw.trim()) {
          try {
            parsedMetadata = JSON.parse(metadataRaw);
            setMetadataError(null);
          } catch (err) {
            setMetadataError("Metadata must be valid JSON");
            return;
          }
        } else {
          setMetadataError(null);
        }

        if (passageMetaRaw.trim()) {
          try {
            parsedPassageMetadata = JSON.parse(passageMetaRaw);
            setPassageMetaError(null);
          } catch (err) {
            setPassageMetaError("Passage metadata must be valid JSON");
            return;
          }
        } else {
          setPassageMetaError(null);
        }

        const skillTags = skillTagsInput
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean);

        const payload: Partial<AdminQuestion> = {
          stem_text: stemText,
          section,
          sub_section: subSection || null,
          difficulty_level: difficulty === "" ? null : Number(difficulty),
          correct_answer: { value: correctAnswer },
          choices,
          skill_tags: skillTags,
          estimated_time_sec: estimatedTime === "" ? null : Number(estimatedTime),
          irt_a: irtA === "" ? null : Number(irtA),
          irt_b: irtB === "" ? null : Number(irtB),
          source_page: pageRef === "" ? null : Number(pageRef),
          page: pageRef === "" ? null : String(pageRef),
          index_in_set: indexInSet === "" ? null : Number(indexInSet),
          metadata: parsedMetadata,
          has_figure: hasFigure,
        };

        if (passageText.trim()) {
          payload.passage = {
            content_text: passageText,
            metadata: parsedPassageMetadata,
          };
        }

        onSubmit(payload);
      }}
    >
      <div className="flex flex-wrap gap-2 text-xs uppercase tracking-wide text-white/60">
        <span className="chip-soft bg-white/10 text-white">Draft #{draft.id}</span>
        {draft.source_id ? (
          <span className="chip-soft bg-white/10 text-white/80">PDF #{draft.source_id}</span>
        ) : null}
        {draft.payload?.has_figure ? (
          <span className="chip-soft bg-amber-500/20 text-amber-100">Figure required</span>
        ) : (
          <span className="chip-soft bg-emerald-500/20 text-emerald-100">No figure</span>
        )}
      </div>
      <label className="text-sm text-white/70 block">
        Question text
        <textarea
          className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-sm text-white"
          rows={4}
          value={stemText}
          onChange={(e) => setStemText(e.target.value)}
        />
      </label>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="text-sm text-white/70">
          Section
          <select
            className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-white"
            value={section}
            onChange={(e) => setSection(e.target.value)}
          >
            <option value="Math">Math</option>
            <option value="RW">Reading & Writing</option>
          </select>
        </label>
        <label className="text-sm text-white/70">
          Sub-section
          <input
            className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-white"
            value={subSection}
            onChange={(e) => setSubSection(e.target.value)}
          />
        </label>
        <label className="text-sm text-white/70">
          Difficulty
          <input
            type="number"
            min={1}
            max={5}
            className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-white"
            value={difficulty}
            onChange={(e) => setDifficulty(e.target.value ? Number(e.target.value) : "")}
          />
        </label>
      </div>
      <label className="text-sm text-white/70 block">
        Skill tags
        <input
          className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-white"
          placeholder="Comma separated, e.g. transitions,grammar"
          value={skillTagsInput}
          onChange={(e) => setSkillTagsInput(e.target.value)}
        />
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        {choiceKeys.map((key) => (
          <label key={key} className="text-sm text-white/70">
            Choice {key}
            <input
              className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-white"
              value={choices[key] ?? ""}
              onChange={(e) =>
                setChoices((prev) => ({
                  ...prev,
                  [key]: e.target.value,
                }))
              }
            />
          </label>
        ))}
      </div>
      <label className="text-sm text-white/70 block">
        Correct answer
        <input
          className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-white"
          placeholder="A"
          value={correctAnswer}
          onChange={(e) => setCorrectAnswer(e.target.value.trim().toUpperCase())}
        />
      </label>
      <label className="text-sm text-white/70 block">
        Passage text (optional)
        <textarea
          className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-sm text-white"
          rows={3}
          value={passageText}
          onChange={(e) => setPassageText(e.target.value)}
        />
      </label>
      <label className="text-sm text-white/70 block">
        Passage metadata (JSON)
        <textarea
          className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-sm text-white"
          rows={2}
          placeholder='{ "source": "pdf" }'
          value={passageMetaRaw}
          onChange={(e) => setPassageMetaRaw(e.target.value)}
        />
        {passageMetaError && <p className="text-xs text-red-400">{passageMetaError}</p>}
      </label>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="text-sm text-white/70">
          Estimated time (sec)
          <input
            type="number"
            className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-white"
            value={estimatedTime}
            onChange={(e) => setEstimatedTime(e.target.value ? Number(e.target.value) : "")}
          />
        </label>
        <label className="text-sm text-white/70">
          IRT a
          <input
            type="number"
            className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-white"
            value={irtA}
            onChange={(e) => setIrtA(e.target.value ? Number(e.target.value) : "")}
          />
        </label>
        <label className="text-sm text-white/70">
          IRT b
          <input
            type="number"
            className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-white"
            value={irtB}
            onChange={(e) => setIrtB(e.target.value ? Number(e.target.value) : "")}
          />
        </label>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm text-white/70">
          Source page
          <input
            type="number"
            className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-white"
            value={pageRef}
            onChange={(e) => setPageRef(e.target.value ? Number(e.target.value) : "")}
          />
        </label>
        <label className="text-sm text-white/70">
          Index in set
          <input
            type="number"
            className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-white"
            value={indexInSet}
            onChange={(e) => setIndexInSet(e.target.value ? Number(e.target.value) : "")}
          />
        </label>
      </div>
      <label className="text-sm text-white/70 block">
        Metadata (JSON)
        <textarea
          className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-sm text-white"
          rows={2}
          placeholder='{ "topic": "algebra" }'
          value={metadataRaw}
          onChange={(e) => setMetadataRaw(e.target.value)}
        />
        {metadataError && <p className="text-xs text-red-400">{metadataError}</p>}
      </label>
      <label className="flex items-center gap-2 text-sm text-white/70">
        <input
          type="checkbox"
          checked={hasFigure}
          onChange={(e) => setHasFigure(e.target.checked)}
        />
        Question requires figure before publishing
      </label>
      {error ? (
        <p className="text-sm text-red-400">
          {extractErrorMessage(error, "Unable to save draft")}
        </p>
      ) : null}
      <div className="flex items-center gap-3">
        <button
          type="submit"
          className="rounded-xl bg-white px-4 py-2 text-sm font-semibold text-[#050E1F]"
          disabled={isSaving}
        >
          {isSaving ? "Saving..." : "Save draft"}
        </button>
        <p className="text-xs text-white/50">
          Updated {draft.updated_at ? new Date(draft.updated_at).toLocaleString() : "recently"}
        </p>
      </div>
    </form>
  );
}

