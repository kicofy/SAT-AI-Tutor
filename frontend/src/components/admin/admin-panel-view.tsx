"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { DashboardCard } from "@/components/ui/dashboard-card";
import {
  getAdminUsers,
  getAdminUser,
  updateAdminUser,
  getAdminQuestions,
  getAdminQuestion,
  updateAdminQuestion,
  getAdminSources,
  getAdminSourceDetail,
  fetchQuestionFigureSource,
  uploadQuestionFigure,
  deleteQuestionFigure,
} from "@/services/admin";
import { AdminQuestion, AdminSource, AdminUser, UserLearningSnapshot } from "@/types/admin";
import { extractErrorMessage } from "@/lib/errors";
import { FigureCropper } from "@/components/admin/figure-cropper";
import { ImportWorkspace } from "@/components/admin/import-workspace";
import { FigureSource } from "@/types/figure";
import { getCroppedBlob, SelectionRect } from "@/lib/image";
import { env } from "@/lib/env";
import { getClientToken } from "@/lib/auth-storage";

const PAGE_SIZE = 20;
const DETAIL_PAGE_SIZE = 20;

type TabKey = "users" | "questions" | "collections" | "import";

export function AdminPanelView() {
  const [activeTab, setActiveTab] = useState<TabKey>("users");
  const [questionFocusId, setQuestionFocusId] = useState<number | null>(null);
  const tabs: { key: TabKey; label: string; description: string }[] = [
    { key: "users", label: "Users", description: "Manage accounts and roles" },
    { key: "questions", label: "Question Bank", description: "Edit and review questions" },
    { key: "collections", label: "PDF Collections", description: "Review uploaded sets" },
    { key: "import", label: "Upload & Import", description: "Process new question sets" },
  ];

  return (
    <AppShell>
      <div className="col-span-full mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-8 text-white">
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-white/50">Admin Panel</p>
          <h1 className="mt-1 text-3xl font-semibold">Administrator Console</h1>
          <p className="text-sm text-white/60">
            Manage users, question banks, collections, and new imports from a single workspace.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${
                activeTab === tab.key
                  ? "border-white bg-white text-[#050E1F]"
                  : "border-white/30 text-white/70 hover:border-white/60"
              }`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === "users" && <UsersTab />}
        {activeTab === "questions" && (
          <QuestionTab
            focusQuestionId={questionFocusId}
            onConsumeFocus={() => setQuestionFocusId(null)}
          />
        )}
        {activeTab === "collections" && (
          <CollectionsTab
            onJumpToQuestion={(questionId) => {
              setQuestionFocusId(questionId);
              setActiveTab("questions");
            }}
          />
        )}
        {activeTab === "import" && <ImportTab />}
      </div>
    </AppShell>
  );
}

function UsersTab() {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const queryClient = useQueryClient();

  const usersQuery = useQuery({
    queryKey: ["admin-users", page, query],
    queryFn: () =>
      getAdminUsers({
        page,
        per_page: PAGE_SIZE,
        search: query || undefined,
      }),
  });

  const userDetailQuery = useQuery({
    queryKey: ["admin-user-detail", selectedUserId],
    queryFn: () => (selectedUserId ? getAdminUser(selectedUserId) : Promise.resolve(null)),
    enabled: Boolean(selectedUserId),
  });

  const updateUserMutation = useMutation({
    mutationFn: (payload: { userId: number; data: any }) =>
      updateAdminUser(payload.userId, payload.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      queryClient.invalidateQueries({ queryKey: ["admin-user-detail"] });
    },
  });

  const handleSearch = (event: React.FormEvent) => {
    event.preventDefault();
    setPage(1);
    setQuery(search.trim());
  };

  const selectedUser = userDetailQuery.data?.user;
  const snapshot = userDetailQuery.data?.snapshot;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr] items-start">
        <DashboardCard title="Users" subtitle="Search, inspect, and edit accounts.">
        <form className="flex flex-col gap-3 sm:flex-row" onSubmit={handleSearch}>
          <input
            className="flex-1 rounded-xl border border-white/20 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-white/40"
            placeholder="Search by email or username"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button className="rounded-xl bg-white px-4 py-2 text-sm font-semibold text-[#050E1F]">
            Search
          </button>
        </form>
        <div className="mt-4 overflow-auto rounded-xl border border-white/10">
          <table className="w-full text-left text-sm">
            <thead className="bg-white/5 text-xs uppercase tracking-wide text-white/60">
              <tr>
                <th className="px-4 py-3">User</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Verified</th>
                <th className="px-4 py-3">Created</th>
              </tr>
            </thead>
            <tbody>
              {usersQuery.isLoading ? (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-white/60">
                    Loading users...
                  </td>
                </tr>
              ) : (
                usersQuery.data?.items.map((user) => (
                  <tr
                    key={user.id}
                    className={`cursor-pointer border-t border-white/5 hover:bg-white/5 ${
                      selectedUserId === user.id ? "bg-white/10" : ""
                    }`}
                    onClick={() => setSelectedUserId(user.id)}
                  >
                    <td className="px-4 py-3">
                      <p className="font-semibold text-white">{user.username || "—"}</p>
                      <p className="text-xs text-white/60">{user.email}</p>
                    </td>
                    <td className="px-4 py-3">
                      <span className="rounded-full bg-white/10 px-3 py-1 text-xs uppercase tracking-wide text-white">
                        {user.role}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-white/80">
                      {user.is_email_verified ? "Yes" : "No"}
                    </td>
                    <td className="px-4 py-3 text-white/60">
                      {user.created_at ? new Date(user.created_at).toLocaleDateString() : "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {usersQuery.data ? (
          <PaginationControls
            page={usersQuery.data.pagination.page}
            pages={usersQuery.data.pagination.pages || 1}
            onPageChange={setPage}
          />
        ) : null}
        </DashboardCard>
        <div className="space-y-4">
          <DashboardCard title="User detail" subtitle="Edit account information.">
            {selectedUser ? (
              <UserDetailCard
                user={selectedUser}
                onSubmit={(payload) =>
                  updateUserMutation.mutate({ userId: selectedUser.id, data: payload })
                }
                isSaving={updateUserMutation.isLoading}
                error={updateUserMutation.error}
              />
            ) : (
              <p className="text-sm text-white/60">
                Choose a user from the list to view their profile and edit permissions.
              </p>
            )}
          </DashboardCard>
          <DashboardCard
            title="Learning snapshot"
            subtitle="Live progress signals for the selected learner."
          >
            {selectedUser ? (
              <LearningSnapshotCard
                snapshot={snapshot}
                isLoading={userDetailQuery.isLoading}
              />
            ) : (
              <p className="text-sm text-white/60">
                Select a user to preview their recent activity, accuracy, and plan status.
              </p>
            )}
          </DashboardCard>
        </div>
      </div>
    </div>
  );
}

function UserDetailCard({
  user,
  onSubmit,
  isSaving,
  error,
}: {
  user: AdminUser;
  onSubmit: (payload: any) => void;
  isSaving: boolean;
  error: unknown;
}) {
  const [email, setEmail] = useState(user.email);
  const [username, setUsername] = useState(user.username || "");
  const [role, setRole] = useState<"student" | "admin">(user.role);
  const [language, setLanguage] = useState(
    user.profile?.language_preference?.toLowerCase().includes("zh") ? "zh" : "en"
  );
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<"active" | "suspended">(
    user.is_active === false ? "suspended" : "active"
  );
  const [lockedReason, setLockedReason] = useState(user.locked_reason || "");

  useEffect(() => {
    setEmail(user.email);
    setUsername(user.username || "");
    setRole(user.role);
    setLanguage(
      user.profile?.language_preference?.toLowerCase().includes("zh") ? "zh" : "en"
    );
    setPassword("");
    setStatus(user.is_active === false ? "suspended" : "active");
    setLockedReason(user.locked_reason || "");
  }, [user]);

  const lockedAt = user.locked_at ? new Date(user.locked_at) : null;

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          email,
          username,
          role,
          language_preference: language,
          reset_password: password || undefined,
          is_active: status === "active",
          locked_reason: status === "suspended" ? lockedReason.trim() || null : null,
        });
        setPassword("");
      }}
    >
      <div className="flex flex-wrap gap-2 text-xs uppercase tracking-wide text-white/70">
        <span className="chip-soft bg-white/10 text-white">
          #{user.id.toString().padStart(4, "0")}
        </span>
        <span
          className={`chip-soft ${
            user.is_email_verified ? "bg-emerald-500/20 text-emerald-200" : "bg-yellow-500/20 text-yellow-200"
          }`}
        >
          {user.is_email_verified ? "Email verified" : "Email pending"}
        </span>
        <span
          className={`chip-soft ${
            status === "active" ? "bg-emerald-500/20 text-emerald-200" : "bg-red-500/20 text-red-200"
          }`}
        >
          {status === "active" ? "Active" : "Suspended"}
        </span>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm text-white/70">
          Email
          <input
            className="mt-1 w-full rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-white"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="text-sm text-white/70">
          Username
          <input
            className="mt-1 w-full rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-white"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </label>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm text-white/70">
          Role
          <select
            className="mt-1 w-full rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-white"
            value={role}
            onChange={(e) => setRole(e.target.value as "student" | "admin")}
          >
            <option value="student">Student</option>
            <option value="admin">Admin</option>
          </select>
        </label>
        <label className="text-sm text-white/70">
          Language
          <select
            className="mt-1 w-full rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-white"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
          >
            <option value="en">English</option>
            <option value="zh">中文</option>
          </select>
        </label>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm text-white/70">
          Account status
          <select
            className="mt-1 w-full rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-white"
            value={status}
            onChange={(e) => setStatus(e.target.value as "active" | "suspended")}
          >
            <option value="active">Active</option>
            <option value="suspended">Suspended</option>
          </select>
        </label>
        <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/70">
          <p>Created: {user.created_at ? new Date(user.created_at).toLocaleDateString() : "—"}</p>
          <p>Last lock: {lockedAt ? lockedAt.toLocaleString() : "—"}</p>
        </div>
      </div>
      {status === "suspended" ? (
        <label className="text-sm text-white/70 block">
          Suspension reason
          <textarea
            className="mt-1 w-full rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-white"
            rows={2}
            placeholder="Optional note for the team"
            value={lockedReason}
            onChange={(e) => setLockedReason(e.target.value)}
          />
        </label>
      ) : null}
      <label className="text-sm text-white/70 block">
        Reset password
        <input
          type="text"
          className="mt-1 w-full rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-white"
          placeholder="Leave blank to keep current password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      {error ? (
        <p className="text-sm text-red-400">
          {extractErrorMessage(error, "Failed to update user")}
        </p>
      ) : null}
      <button
        type="submit"
        className="rounded-xl bg-white px-4 py-2 text-sm font-semibold text-[#050E1F]"
        disabled={isSaving}
      >
        {isSaving ? "Saving..." : "Save changes"}
      </button>
    </form>
  );
}

function LearningSnapshotCard({
  snapshot,
  isLoading,
}: {
  snapshot: UserLearningSnapshot | null | undefined;
  isLoading: boolean;
}) {
  if (isLoading) {
    return <p className="text-sm text-white/60">Loading snapshot...</p>;
  }
  if (!snapshot) {
    return <p className="text-sm text-white/60">No learning history yet for this user.</p>;
  }

  const lastActive = snapshot.last_active_at ? formatTimestamp(snapshot.last_active_at) : "No activity";
  const accuracy =
    typeof snapshot.accuracy_percent === "number" ? `${snapshot.accuracy_percent.toFixed(1)}%` : "—";
  const avgTime = formatSeconds(snapshot.avg_time_sec);
  const planProgress = `${snapshot.plan_tasks_completed}/${snapshot.plan_tasks_total}`;
  const predictedScores =
    snapshot.predicted_score_rw || snapshot.predicted_score_math
      ? `${snapshot.predicted_score_rw ?? "—"} RW · ${snapshot.predicted_score_math ?? "—"} Math`
      : "—";

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <SnapshotStat label="Last active" value={lastActive} />
        <SnapshotStat label="Questions answered" value={snapshot.total_questions.toString()} />
        <SnapshotStat label="Accuracy" value={accuracy} />
        <SnapshotStat label="Avg time / question" value={avgTime} />
        <SnapshotStat label="Plan completion" value={planProgress} />
        <SnapshotStat label="Predicted scores" value={predictedScores} />
      </div>
      <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
        <p className="text-sm font-semibold text-white">Active plan block</p>
        {snapshot.active_plan ? (
          <div className="mt-2 text-sm text-white/80">
            <p className="font-medium">
              {snapshot.active_plan.block_id || "Unlabeled"} · {snapshot.active_plan.status}
            </p>
            <p className="text-white/70">
              {snapshot.active_plan.focus_skill || "General focus"} ·{" "}
              {snapshot.active_plan.questions_target ?? 0} questions target
            </p>
            <p className="text-xs text-white/50">
              Updated {formatTimestamp(snapshot.active_plan.updated_at) || "—"}
            </p>
          </div>
        ) : (
          <p className="mt-2 text-sm text-white/60">No plan task in progress.</p>
        )}
      </div>
    </div>
  );
}

function SnapshotStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
      <p className="text-xs uppercase tracking-wide text-white/50">{label}</p>
      <p className="text-lg font-semibold text-white">{value}</p>
    </div>
  );
}

function formatTimestamp(value?: string | null) {
  if (!value) return null;
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function formatSeconds(value?: number | null) {
  if (!value) return "—";
  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60);
  if (minutes === 0) {
    return `${seconds}s`;
  }
  return `${minutes}m ${seconds.toString().padStart(2, "0")}s`;
}

function QuestionTab({
  focusQuestionId,
  onConsumeFocus,
}: {
  focusQuestionId: number | null;
  onConsumeFocus: () => void;
}) {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [selectedQuestionId, setSelectedQuestionId] = useState<number | null>(null);
  const queryClient = useQueryClient();

  const questionsQuery = useQuery({
    queryKey: ["admin-questions", page, query],
    queryFn: () =>
      getAdminQuestions({
        page,
        per_page: PAGE_SIZE,
        question_uid: query || undefined,
      }),
  });

  const questionDetailQuery = useQuery({
    queryKey: ["admin-question-detail", selectedQuestionId],
    queryFn: () => (selectedQuestionId ? getAdminQuestion(selectedQuestionId) : Promise.resolve(null)),
    enabled: Boolean(selectedQuestionId),
  });

  const updateQuestionMutation = useMutation({
    mutationFn: (payload: { questionId: number; data: Partial<AdminQuestion> }) =>
      updateAdminQuestion(payload.questionId, payload.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-questions"] });
      queryClient.invalidateQueries({ queryKey: ["admin-question-detail"] });
    },
  });

  const handleSearch = (event: React.FormEvent) => {
    event.preventDefault();
    setPage(1);
    setQuery(search.trim());
  };

  const selectedQuestion = questionDetailQuery.data?.question;

  useEffect(() => {
    if (focusQuestionId) {
      setSelectedQuestionId(focusQuestionId);
      onConsumeFocus();
    }
  }, [focusQuestionId, onConsumeFocus]);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr] items-start">
        <DashboardCard title="Question bank" subtitle="Search and edit individual questions.">
        <form className="flex flex-col gap-3 sm:flex-row" onSubmit={handleSearch}>
          <input
            className="flex-1 rounded-xl border border-white/20 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-white/40"
            placeholder="Filter by question UID or ID"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button className="rounded-xl bg-white px-4 py-2 text-sm font-semibold text-[#050E1F]">
            Search
          </button>
        </form>
        <div className="mt-4 overflow-auto rounded-xl border border-white/10">
          <table className="w-full text-left text-sm">
            <thead className="bg-white/5 text-xs uppercase tracking-wide text-white/60">
              <tr>
                <th className="px-4 py-3">Question</th>
                <th className="px-4 py-3">Section</th>
                <th className="px-4 py-3">Difficulty</th>
                <th className="px-4 py-3">Source</th>
              </tr>
            </thead>
            <tbody>
              {questionsQuery.isLoading ? (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-white/60">
                    Loading questions...
                  </td>
                </tr>
              ) : (
                questionsQuery.data?.items.map((question) => (
                  <tr
                    key={question.id}
                    className={`cursor-pointer border-t border-white/5 hover:bg-white/5 ${
                      selectedQuestionId === question.id ? "bg-white/10" : ""
                    }`}
                    onClick={() => setSelectedQuestionId(question.id)}
                  >
                    <td className="px-4 py-3">
                      <p className="font-semibold text-white">
                        {question.question_uid || `#${question.id}`}
                      </p>
                      <p className="text-xs text-white/60 line-clamp-1">{question.stem_text}</p>
                    </td>
                    <td className="px-4 py-3 text-white/80">{question.section}</td>
                    <td className="px-4 py-3 text-white/80">
                      {question.difficulty_level ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-white/60">
                      {question.source?.original_name || question.source?.filename || "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {questionsQuery.data ? (
          <PaginationControls
            page={questionsQuery.data.page}
            pages={Math.max(
              1,
              Math.ceil((questionsQuery.data.total || PAGE_SIZE) / PAGE_SIZE)
            )}
            onPageChange={setPage}
          />
        ) : null}
        </DashboardCard>
        <div>
          {selectedQuestion ? (
            <DashboardCard
              title="Question editor"
              subtitle={selectedQuestion.question_uid || `Question #${selectedQuestion.id}`}
            >
              <QuestionEditor
                question={selectedQuestion}
                onSubmit={(payload) =>
                  updateQuestionMutation.mutate({ questionId: selectedQuestion.id, data: payload })
                }
                isSaving={updateQuestionMutation.isLoading}
                error={updateQuestionMutation.error}
              />
            </DashboardCard>
          ) : (
            <DashboardCard title="Question editor" subtitle="Select a question to edit.">
              <p className="text-sm text-white/60">
                Click a question from the list to view and edit its content, difficulty, and answers.
              </p>
            </DashboardCard>
          )}
        </div>
      </div>
    </div>
  );
}

function QuestionEditor({
  question,
  onSubmit,
  isSaving,
  error,
}: {
  question: AdminQuestion;
  onSubmit: (payload: Partial<AdminQuestion>) => void;
  isSaving: boolean;
  error: unknown;
}) {
  const [stemText, setStemText] = useState(question.stem_text ?? "");
  const [section, setSection] = useState(question.section);
  const [subSection, setSubSection] = useState(question.sub_section ?? "");
  const [difficulty, setDifficulty] = useState<number | "">(question.difficulty_level ?? "");
  const [correctAnswer, setCorrectAnswer] = useState(question.correct_answer?.value ?? "");
  const [choices, setChoices] = useState<Record<string, string>>(question.choices || {});
  const [passageText, setPassageText] = useState(question.passage?.content_text ?? "");
  const [passageMetaRaw, setPassageMetaRaw] = useState(
    question.passage?.metadata ? JSON.stringify(question.passage.metadata, null, 2) : ""
  );
  const [skillTagsInput, setSkillTagsInput] = useState((question.skill_tags || []).join(", "));
  const [estimatedTime, setEstimatedTime] = useState<number | "">(question.estimated_time_sec ?? "");
  const [irtA, setIrtA] = useState<number | "">(question.irt_a ?? "");
  const [irtB, setIrtB] = useState<number | "">(question.irt_b ?? "");
  const derivePageValue = (value?: number | string | null) => {
    if (typeof value === "number" && !Number.isNaN(value)) return value;
    if (typeof value === "string" && value.trim() !== "" && !Number.isNaN(Number(value))) {
      return Number(value);
    }
    return "";
  };

  const [pageRef, setPageRef] = useState<number | "">(
    derivePageValue(question.source_page ?? question.page ?? null)
  );
  const [indexInSet, setIndexInSet] = useState<number | "">(question.index_in_set ?? "");
  const [metadataRaw, setMetadataRaw] = useState(
    question.metadata ? JSON.stringify(question.metadata, null, 2) : ""
  );
  const [hasFigure, setHasFigure] = useState(Boolean(question.has_figure));
  const [metadataError, setMetadataError] = useState<string | null>(null);
  const [passageMetaError, setPassageMetaError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const baseApiUrl = useMemo(() => (env.apiBaseUrl || "").replace(/\/$/, ""), []);
  const [figureModal, setFigureModal] = useState<QuestionFigureModalState | null>(null);
  const [figureError, setFigureError] = useState<string | null>(null);
  const [figureSaving, setFigureSaving] = useState(false);
  const [figureDeleting, setFigureDeleting] = useState(false);
  const [figurePreviewUrl, setFigurePreviewUrl] = useState<string | null>(null);
  const [figurePageInput, setFigurePageInput] = useState("");
  const primaryFigure = question.figures?.[0];

  const buildMediaUrl = useCallback(
    (url?: string | null) => {
      if (!url) return null;
      const absolute =
        url.startsWith("http://") || url.startsWith("https://") ? url : `${baseApiUrl}${url}`;
      const token = getClientToken();
      if (!token) return absolute;
      const separator = absolute.includes("?") ? "&" : "?";
      return `${absolute}${separator}token=${encodeURIComponent(token)}`;
    },
    [baseApiUrl]
  );

  useEffect(() => {
    setStemText(question.stem_text ?? "");
    setSection(question.section);
    setSubSection(question.sub_section ?? "");
    setDifficulty(question.difficulty_level ?? "");
    setCorrectAnswer(question.correct_answer?.value ?? "");
    setChoices(question.choices || {});
    setPassageText(question.passage?.content_text ?? "");
    setPassageMetaRaw(
      question.passage?.metadata ? JSON.stringify(question.passage.metadata, null, 2) : ""
    );
    setSkillTagsInput((question.skill_tags || []).join(", "));
    setEstimatedTime(question.estimated_time_sec ?? "");
    setIrtA(question.irt_a ?? "");
    setIrtB(question.irt_b ?? "");
    setPageRef(derivePageValue(question.source_page ?? question.page ?? null));
    setIndexInSet(question.index_in_set ?? "");
    setMetadataRaw(question.metadata ? JSON.stringify(question.metadata, null, 2) : "");
    setHasFigure(Boolean(question.has_figure));
    setMetadataError(null);
    setPassageMetaError(null);
    setFigurePreviewUrl(buildMediaUrl(question.figures?.[0]?.url));
    setFigurePageInput(
      question.source_page
        ? String(question.source_page)
        : typeof question.page === "string"
        ? question.page
        : ""
    );
    setFigureModal(null);
    setFigureError(null);
  }, [question, buildMediaUrl]);

  const computeSelectionFromFigure = useCallback(
    (source?: FigureSource) => {
      if (!primaryFigure?.bbox || typeof primaryFigure.bbox !== "object") {
        return null;
      }
      const bbox = primaryFigure.bbox as Record<string, unknown>;
      const baseWidth = Number(bbox.imageWidth ?? source?.width ?? 0);
      const baseHeight = Number(bbox.imageHeight ?? source?.height ?? 0);
      const rawWidth = Number(bbox.width ?? 0);
      const rawHeight = Number(bbox.height ?? 0);
      if (
        !Number.isFinite(baseWidth) ||
        !Number.isFinite(baseHeight) ||
        !Number.isFinite(rawWidth) ||
        !Number.isFinite(rawHeight) ||
        baseWidth <= 0 ||
        baseHeight <= 0 ||
        rawWidth <= 0 ||
        rawHeight <= 0
      ) {
        return null;
      }
      const scaleX = source ? source.width / baseWidth : 1;
      const scaleY = source ? source.height / baseHeight : 1;
      return {
        x: Number(bbox.x ?? 0) * scaleX,
        y: Number(bbox.y ?? 0) * scaleY,
        width: rawWidth * scaleX,
        height: rawHeight * scaleY,
      };
    },
    [primaryFigure]
  );

  const openFigureModal = useCallback(async () => {
    if (!question.source_id) {
      setFigureError("Link this question to a PDF source before capturing figures.");
      return;
    }
    setFigureError(null);
    setFigureModal({
      questionId: question.id,
      selection: null,
      zoom: 1,
      loading: true,
      page: question.source_page ?? undefined,
    });
    try {
      const source = await fetchQuestionFigureSource(question.id);
      const selection = computeSelectionFromFigure(source);
      setFigureModal((prev) =>
        prev && prev.questionId === question.id
          ? { ...prev, source, selection, loading: false, zoom: 1, page: source.page }
          : prev
      );
      setFigurePageInput(String(source.page ?? ""));
    } catch (err) {
      setFigureError(extractErrorMessage(err, "Failed to load PDF page"));
      setFigureModal((prev) =>
        prev && prev.questionId === question.id ? { ...prev, loading: false } : prev
      );
    }
  }, [computeSelectionFromFigure, question.id, question.source_id]);

  const closeFigureModal = useCallback(() => {
    setFigureModal(null);
    setFigureError(null);
  }, []);

  const handleFigureSelectionChange = useCallback((rect: SelectionRect | null) => {
    setFigureModal((prev) => (prev ? { ...prev, selection: rect } : prev));
  }, []);

  const handleFigureSelectionComplete = useCallback((rect: SelectionRect | null) => {
    setFigureModal((prev) => (prev ? { ...prev, selection: rect } : prev));
  }, []);

  const handleFigureZoomChange = useCallback((value: number) => {
    setFigureModal((prev) => (prev ? { ...prev, zoom: value } : prev));
  }, []);

  const handleReloadFigurePage = useCallback(async () => {
    if (!figureModal) return;
    const trimmed = figurePageInput.trim();
    const pageNumber =
      trimmed && !Number.isNaN(Number(trimmed)) ? Number(trimmed) : undefined;
    setFigureModal((prev) =>
      prev && prev.questionId === question.id ? { ...prev, loading: true } : prev
    );
    try {
      const source = await fetchQuestionFigureSource(question.id, pageNumber);
      const selection = computeSelectionFromFigure(source);
      setFigureModal((prev) =>
        prev && prev.questionId === question.id
          ? { ...prev, source, selection, loading: false, page: source.page }
          : prev
      );
      setFigurePageInput(String(source.page ?? ""));
    } catch (err) {
      setFigureError(extractErrorMessage(err, "Unable to load requested page"));
      setFigureModal((prev) =>
        prev && prev.questionId === question.id ? { ...prev, loading: false } : prev
      );
    }
  }, [computeSelectionFromFigure, figureModal, figurePageInput, question.id]);

  const handleSaveQuestionFigure = useCallback(async () => {
    if (!figureModal?.source || !figureModal.selection) {
      setFigureError("Please drag to select the figure region before saving.");
      return;
    }
    setFigureSaving(true);
    setFigureError(null);
    try {
      const blob = await getCroppedBlob(figureModal.source.image, figureModal.selection);
      const file = new File(
        [blob],
        `question-${question.id}-${Date.now()}.png`,
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
      await uploadQuestionFigure(question.id, formData);
      setFigureModal(null);
      queryClient.invalidateQueries({ queryKey: ["admin-question-detail", question.id] });
      queryClient.invalidateQueries({ queryKey: ["admin-questions"] });
    } catch (err) {
      setFigureError(extractErrorMessage(err, "Failed to save figure"));
    } finally {
      setFigureSaving(false);
    }
  }, [figureModal, question.id, queryClient]);

  const handleDeleteFigure = useCallback(async () => {
    if (!primaryFigure) return;
    const confirmed = window.confirm("Remove the existing figure for this question?");
    if (!confirmed) {
      return;
    }
    setFigureDeleting(true);
    setFigureError(null);
    try {
      await deleteQuestionFigure(question.id, primaryFigure.id);
      queryClient.invalidateQueries({ queryKey: ["admin-question-detail", question.id] });
      queryClient.invalidateQueries({ queryKey: ["admin-questions"] });
      setFigurePreviewUrl(null);
    } catch (err) {
      setFigureError(extractErrorMessage(err, "Failed to remove figure"));
    } finally {
      setFigureDeleting(false);
    }
  }, [primaryFigure, question.id, queryClient]);

  const choiceKeys = useMemo(() => {
    const keys = Object.keys(choices);
    return keys.length ? keys : ["A", "B", "C", "D"];
  }, [choices]);

  return (
    <>
      <form
      className="space-y-5"
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
      <section className="space-y-3">
        <p className="text-xs uppercase tracking-wide text-white/50">Question body</p>
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
        <label className="text-sm text-white/70">
          Skill tags
          <input
            className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-white"
            placeholder="Comma separated, e.g. transitions,grammar"
            value={skillTagsInput}
            onChange={(e) => setSkillTagsInput(e.target.value)}
          />
        </label>
      </section>

      <section className="space-y-3">
        <p className="text-xs uppercase tracking-wide text-white/50">Choices</p>
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
        <label className="text-sm text-white/70">
          Correct answer
          <input
            className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-white"
            value={correctAnswer}
            onChange={(e) => setCorrectAnswer(e.target.value)}
          />
        </label>
      </section>

      <section className="space-y-3">
        <p className="text-xs uppercase tracking-wide text-white/50">Passage</p>
        <textarea
          className="w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-sm text-white"
          rows={5}
          placeholder="Optional passage text"
          value={passageText}
          onChange={(e) => setPassageText(e.target.value)}
        />
        <label className="text-sm text-white/70 block">
          Passage metadata (JSON)
          <textarea
            className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-xs text-white"
            rows={3}
            value={passageMetaRaw}
            onChange={(e) => setPassageMetaRaw(e.target.value)}
          />
          {passageMetaError ? (
            <p className="mt-1 text-xs text-red-400">{passageMetaError}</p>
          ) : (
            <p className="mt-1 text-xs text-white/50">Leave blank to keep metadata empty.</p>
          )}
        </label>
      </section>

      <section className="space-y-3">
        <p className="text-xs uppercase tracking-wide text-white/50">Performance metadata</p>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-sm text-white/70">
            Estimated time (sec)
            <input
              type="number"
              min={0}
              className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-white"
              value={estimatedTime}
              onChange={(e) =>
                setEstimatedTime(e.target.value === "" ? "" : Number(e.target.value))
              }
            />
          </label>
          <label className="text-sm text-white/70">
            IRT a
            <input
              type="number"
              className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-white"
              value={irtA}
              onChange={(e) => setIrtA(e.target.value === "" ? "" : Number(e.target.value))}
            />
          </label>
          <label className="text-sm text-white/70">
            IRT b
            <input
              type="number"
              className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-white"
              value={irtB}
              onChange={(e) => setIrtB(e.target.value === "" ? "" : Number(e.target.value))}
            />
          </label>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-sm text-white/70">
            PDF page
            <input
              type="number"
              min={1}
              className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-white"
              value={pageRef}
              onChange={(e) => setPageRef(e.target.value === "" ? "" : Number(e.target.value))}
            />
          </label>
          <label className="text-sm text-white/70">
            Index in set
            <input
              type="number"
              min={0}
              className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-white"
              value={indexInSet}
              onChange={(e) =>
                setIndexInSet(e.target.value === "" ? "" : Number(e.target.value))
              }
            />
          </label>
          <label className="text-sm text-white/70 flex items-center gap-3">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-white/40 bg-transparent accent-white"
              checked={hasFigure}
              onChange={(e) => setHasFigure(e.target.checked)}
            />
            <span>Has figure / illustration</span>
          </label>
        </div>
        <label className="text-sm text-white/70 block">
          Question metadata (JSON)
          <textarea
            className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-xs text-white"
            rows={3}
            value={metadataRaw}
            onChange={(e) => setMetadataRaw(e.target.value)}
          />
          {metadataError ? (
            <p className="mt-1 text-xs text-red-400">{metadataError}</p>
          ) : (
            <p className="mt-1 text-xs text-white/50">Optional contextual payload stored with question.</p>
          )}
        </label>
      </section>

      <section className="space-y-3">
        <p className="text-xs uppercase tracking-wide text-white/50">Figure capture</p>
        {figurePreviewUrl ? (
          <div className="overflow-hidden rounded-2xl border border-white/10 bg-black/40 p-2">
            <img src={figurePreviewUrl} alt="Current figure" className="max-h-48 w-auto rounded-xl" />
          </div>
        ) : question.has_figure ? (
          <div className="rounded-2xl border border-amber-400/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
            This question expects a figure, but none is currently attached.
          </div>
        ) : (
          <p className="text-sm text-white/60">No figure has been uploaded for this question yet.</p>
        )}
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            className="rounded-xl border border-white/30 px-4 py-2 text-sm font-semibold text-white/80 disabled:opacity-40"
            onClick={openFigureModal}
            disabled={!question.source_id}
          >
            {figurePreviewUrl ? "Re-crop figure" : "Capture figure"}
          </button>
          {figurePreviewUrl && (
            <button
              type="button"
              className="rounded-xl border border-white/20 px-4 py-2 text-sm font-semibold text-white/80 disabled:opacity-40"
              onClick={handleDeleteFigure}
              disabled={figureDeleting}
            >
              {figureDeleting ? "Removing..." : "Remove figure"}
            </button>
          )}
        </div>
        {!question.source_id && (
          <p className="text-xs text-amber-200">
            Link this question to a PDF source and page to enable figure cropping.
          </p>
        )}
        {figureError && !figureModal && <p className="text-xs text-red-400">{figureError}</p>}
      </section>

      {error ? (
        <p className="text-sm text-red-400">
          {extractErrorMessage(error, "Failed to update question")}
        </p>
      ) : null}
      <button
        type="submit"
        className="rounded-xl bg-white px-4 py-2 text-sm font-semibold text-[#050E1F]"
        disabled={isSaving}
      >
        {isSaving ? "Saving..." : "Save question"}
      </button>
    </form>
    {figureModal && (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
        <div className="flex w-full max-w-4xl flex-col rounded-2xl bg-[#050E1F] shadow-2xl max-h-[95vh]">
          <div className="flex items-center justify-between border-b border-white/5 px-5 py-3">
            <div>
              <p className="text-base font-semibold text-white">
                Capture figure · {question.question_uid || `Question #${question.id}`}
              </p>
              <p className="text-xs text-white/60">
                Page {figureModal.page ?? question.source_page ?? "—"}
              </p>
            </div>
            <button
              className="rounded-full border border-white/20 px-3 py-1 text-xs text-white/70 hover:text-white"
              onClick={closeFigureModal}
              disabled={figureSaving}
            >
              Close
            </button>
          </div>
          <div className="flex-1 space-y-4 overflow-y-auto p-5">
            {figureModal.loading ? (
              <div className="flex h-[360px] items-center justify-center text-sm text-white/60">
                Loading page preview...
              </div>
            ) : figureModal.source ? (
              <>
                <FigureCropper
                  source={figureModal.source}
                  selection={figureModal.selection}
                  zoom={figureModal.zoom}
                  onSelectionChange={handleFigureSelectionChange}
                  onSelectionComplete={handleFigureSelectionComplete}
                  onZoomChange={handleFigureZoomChange}
                />
                <div className="flex flex-wrap items-center gap-3 text-xs text-white/60">
                  <span>Zoom</span>
                  <input
                    type="range"
                    min={0.8}
                    max={2.5}
                    step={0.1}
                    value={figureModal.zoom}
                    onChange={(e) => handleFigureZoomChange(Number(e.target.value))}
                    className="w-40 accent-white"
                  />
                  <span>{figureModal.zoom.toFixed(2)}x</span>
                  <button
                    type="button"
                    className="rounded-full border border-white/20 px-3 py-1 text-white/70 hover:text-white"
                    onClick={() => handleFigureSelectionChange(null)}
                  >
                    Clear selection
                  </button>
                </div>
                <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
                  <label className="text-sm text-white/70">
                    Page number
                    <input
                      className="mt-1 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-white"
                      value={figurePageInput}
                      onChange={(e) => setFigurePageInput(e.target.value)}
                    />
                  </label>
                  <button
                    type="button"
                    className="self-end rounded-xl border border-white/20 px-4 py-2 text-sm font-semibold text-white/80"
                    onClick={handleReloadFigurePage}
                  >
                    Load page
                  </button>
                </div>
                {figurePreviewUrl && (
                  <div>
                    <p className="mb-2 text-xs text-white/60">Current figure preview</p>
                    <div className="overflow-hidden rounded-xl border border-white/10 bg-black/40 p-2">
                      <img
                        src={figurePreviewUrl}
                        alt="Existing figure"
                        className="max-h-40 w-auto rounded"
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
            <p className="px-5 text-xs text-red-400">{figureError}</p>
          )}
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
              onClick={handleSaveQuestionFigure}
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
    )}
    </>
  );
}

function CollectionsTab({
  onJumpToQuestion,
}: {
  onJumpToQuestion: (questionId: number) => void;
}) {
  const [page, setPage] = useState(1);
  const [selectedSourceId, setSelectedSourceId] = useState<number | null>(null);
  const [detailPage, setDetailPage] = useState(1);

  const sourcesQuery = useQuery({
    queryKey: ["admin-sources", page],
    queryFn: () =>
      getAdminSources({
        page,
        per_page: PAGE_SIZE,
      }),
  });

  useEffect(() => {
    setDetailPage(1);
  }, [selectedSourceId]);

  const sourceDetailQuery = useQuery({
    queryKey: ["admin-source-detail", selectedSourceId, detailPage],
    queryFn: () =>
      selectedSourceId
        ? getAdminSourceDetail(selectedSourceId, { page: detailPage, per_page: DETAIL_PAGE_SIZE })
        : Promise.resolve(null),
    enabled: Boolean(selectedSourceId),
    keepPreviousData: true,
  });

  const detailPagination = sourceDetailQuery.data?.pagination;
  const hasDetailPagination = detailPagination && detailPagination.pages > 1;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr] items-start">
        <DashboardCard
          title="Collections"
          subtitle="Each PDF upload groups related questions into one collection."
        >
        <div className="overflow-auto rounded-xl border border-white/10">
          <table className="w-full text-left text-sm">
            <thead className="bg-white/5 text-xs uppercase tracking-wide text-white/60">
              <tr>
                <th className="px-4 py-3">Collection</th>
                <th className="px-4 py-3">Pages</th>
                <th className="px-4 py-3">Questions</th>
                <th className="px-4 py-3">Uploaded</th>
              </tr>
            </thead>
            <tbody>
              {sourcesQuery.isLoading ? (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-white/60">
                    Loading collections...
                  </td>
                </tr>
              ) : (
                sourcesQuery.data?.items.map((source) => (
                  <tr
                    key={source.id}
                    className={`cursor-pointer border-t border-white/5 hover:bg-white/5 ${
                      selectedSourceId === source.id ? "bg-white/10" : ""
                    }`}
                    onClick={() => setSelectedSourceId(source.id)}
                  >
                    <td className="px-4 py-3 text-white">{source.original_name || source.filename}</td>
                    <td className="px-4 py-3 text-white/80">{source.total_pages ?? "—"}</td>
                    <td className="px-4 py-3 text-white/80">{source.question_count ?? "—"}</td>
                    <td className="px-4 py-3 text-white/60">
                      {source.created_at ? new Date(source.created_at).toLocaleDateString() : "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {sourcesQuery.data ? (
          <PaginationControls
            page={sourcesQuery.data.pagination.page}
            pages={sourcesQuery.data.pagination.pages || 1}
            onPageChange={setPage}
          />
        ) : null}
        </DashboardCard>
        <div>
          {sourceDetailQuery.data ? (
            <DashboardCard
              title="Collection detail"
              subtitle={
                sourceDetailQuery.data.source.original_name ||
                sourceDetailQuery.data.source.filename
              }
            >
              <p className="text-sm text-white/60">
                Total questions: {sourceDetailQuery.data.source.question_count ?? "—"}
              </p>
              <div className="mt-3 overflow-auto rounded-xl border border-white/10">
                <table className="w-full text-left text-sm">
                  <thead className="bg-white/5 text-xs uppercase tracking-wide text-white/60">
                    <tr>
                      <th className="px-4 py-3">Question</th>
                      <th className="px-4 py-3">Section</th>
                      <th className="px-4 py-3">Difficulty</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sourceDetailQuery.data.questions.map((question) => (
                      <tr
                        key={question.id}
                        className="border-t border-white/5 hover:bg-white/5 cursor-pointer"
                        onClick={() => onJumpToQuestion(question.id)}
                      >
                        <td className="px-4 py-3 text-white">
                          {question.question_uid || `#${question.id}`}
                        </td>
                        <td className="px-4 py-3 text-white/80">{question.section}</td>
                        <td className="px-4 py-3 text-white/80">
                          {question.difficulty_level ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {hasDetailPagination ? (
                <PaginationControls
                  page={detailPagination!.page}
                  pages={detailPagination!.pages || 1}
                  onPageChange={setDetailPage}
                />
              ) : null}
            </DashboardCard>
          ) : (
            <DashboardCard title="Collection detail" subtitle="Select a collection to inspect.">
              <p className="text-sm text-white/60">
                Pick a collection on the left to preview its questions, drill down into individual
                items, or jump to the question editor.
              </p>
            </DashboardCard>
          )}
        </div>
      </div>
    </div>
  );
}

function ImportTab() {
  return <ImportWorkspace variant="embedded" />;
}

function PaginationControls({
  page,
  pages,
  onPageChange,
}: {
  page: number;
  pages: number;
  onPageChange: (page: number) => void;
}) {
  if (pages <= 1) return null;
  return (
    <div className="mt-4 flex items-center justify-between text-sm text-white/70">
      <button
        className="rounded-full border border-white/20 px-3 py-1 disabled:border-white/5 disabled:text-white/30"
        onClick={() => onPageChange(Math.max(1, page - 1))}
        disabled={page <= 1}
      >
        Previous
      </button>
      <p>
        Page {page} / {pages}
      </p>
      <button
        className="rounded-full border border-white/20 px-3 py-1 disabled:border-white/5 disabled:text-white/30"
        onClick={() => onPageChange(Math.min(pages, page + 1))}
        disabled={page >= pages}
      >
        Next
      </button>
    </div>
  );
}

type QuestionFigureModalState = {
  questionId: number;
  source?: FigureSource;
  selection: SelectionRect | null;
  zoom: number;
  loading: boolean;
  page?: number;
};

