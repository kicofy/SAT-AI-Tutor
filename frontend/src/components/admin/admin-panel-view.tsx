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
  updateUserMembership,
  getAdminQuestions,
  getAdminQuestion,
  updateAdminQuestion,
  getAdminSources,
  getAdminSourceDetail,
  fetchQuestionFigureSource,
  uploadQuestionFigure,
  deleteQuestionFigure,
  getGeneralSettings,
  updateGeneralSettings,
  deleteQuestionsBulk,
  deleteSource,
  listAIPaperJobs,
  createAIPaperJob,
  resumeAIPaperJob,
  fetchOpenaiLogs,
  deleteAIPaperJob,
  getQuestionCategories,
} from "@/services/admin";
import {
  AdminQuestion,
  AdminSource,
  AdminUser,
  GeneralSettings,
  UserLearningSnapshot,
  AIPaperJob,
  OpenAILogEntry,
  PaginatedResponse,
  QuestionCategory,
} from "@/types/admin";
import type { MembershipOrder } from "@/types/membership";
import { extractErrorMessage } from "@/lib/errors";
import { FigureCropper } from "@/components/admin/figure-cropper";
import { ImportWorkspace } from "@/components/admin/import-workspace";
import { FigureSource } from "@/types/figure";
import { getCroppedBlob, SelectionRect } from "@/lib/image";
import { env } from "@/lib/env";
import { getClientToken } from "@/lib/auth-storage";
import { useI18n } from "@/hooks/use-i18n";
import { listMembershipOrdersAdmin, decideMembershipOrder } from "@/services/membership";
import type { StepDirective } from "@/components/practice/explanation-viewer";
import { getQuestionDecorations } from "@/lib/question-decorations";

const PAGE_SIZE = 20;
const DETAIL_PAGE_SIZE = 20;
const STAGE_LABELS: Record<string, string> = {
  pending: "Queued",
  queued: "Queued",
  outline: "Planning outline",
  finalizing: "Finalizing",
};
const OPENAI_LOG_LIMIT = 200;

type TabKey =
  | "users"
  | "questions"
  | "collections"
  | "categories"
  | "import"
  | "membership"
  | "settings"
  | "aiPapers";

export function AdminPanelView() {
  const [activeTab, setActiveTab] = useState<TabKey>("users");
  const [questionFocusId, setQuestionFocusId] = useState<number | null>(null);
  const tabs: { key: TabKey; label: string; description: string }[] = [
    { key: "users", label: "Users", description: "Manage accounts and roles" },
    { key: "questions", label: "Question Bank", description: "Edit and review questions" },
    { key: "collections", label: "PDF Collections", description: "Review uploaded sets" },
    {
      key: "categories",
      label: "Question Categories",
      description: "Browse questions grouped by skill tags",
    },
    { key: "import", label: "Upload & Import", description: "Process new question sets" },
    { key: "membership", label: "Membership Orders", description: "Review subscription intents" },
    { key: "aiPapers", label: "AI Papers", description: "Auto-generate SAT-ready sets" },
    { key: "settings", label: "General Settings", description: "Manage platform defaults" },
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
        {activeTab === "categories" && (
          <QuestionCategoriesTab
            onJumpToQuestion={(questionId) => {
              setQuestionFocusId(questionId);
              setActiveTab("questions");
            }}
          />
        )}
        {activeTab === "import" && <ImportTab />}
        {activeTab === "membership" && <MembershipTab />}
        {activeTab === "aiPapers" && <AIPaperGeneratorTab />}
        {activeTab === "settings" && <GeneralSettingsTab />}
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
  const membershipMutation = useMutation({
    mutationFn: (payload: { userId: number; action: "extend" | "set" | "revoke"; days?: number }) =>
      updateUserMembership(payload.userId, { action: payload.action, days: payload.days }),
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
                isSaving={updateUserMutation.isPending}
                error={updateUserMutation.error}
                onAdjustMembership={(payload) =>
                  membershipMutation.mutate({ userId: selectedUser.id, ...payload })
                }
                membershipPending={membershipMutation.isPending}
                membershipError={membershipMutation.error}
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
  onAdjustMembership,
  membershipPending,
  membershipError,
}: {
  user: AdminUser;
  onSubmit: (payload: any) => void;
  isSaving: boolean;
  error: unknown;
  onAdjustMembership: (payload: { action: "extend" | "set" | "revoke"; days?: number }) => void;
  membershipPending: boolean;
  membershipError: unknown;
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
    <div className="space-y-4">
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
      <MembershipPanel
        membership={user.membership}
        aiQuota={user.ai_explain_quota}
        onAdjust={onAdjustMembership}
        isUpdating={membershipPending}
        error={membershipError}
      />
    </div>
  );
}

function MembershipPanel({
  membership,
  aiQuota,
  onAdjust,
  isUpdating,
  error,
}: {
  membership?: AdminUser["membership"];
  aiQuota?: AdminUser["ai_explain_quota"];
  onAdjust: (payload: { action: "extend" | "set" | "revoke"; days?: number }) => void;
  isUpdating: boolean;
  error: unknown;
}) {
  const { t } = useI18n();
  const expires =
    membership?.expires_at && membership.is_member
      ? new Date(membership.expires_at).toLocaleDateString()
      : null;
  let status = t("admin.membership.expired");
  if (membership?.is_member) {
    status = t("admin.membership.active", { date: expires ?? "—" });
  } else if (membership?.trial_active) {
    status = t("admin.membership.trial", { days: membership.trial_days_remaining ?? 0 });
  }
  const quotaLimit = aiQuota?.limit;
  const quotaLabel =
    quotaLimit === null || quotaLimit === undefined
      ? t("admin.membership.quotaUnlimited")
      : t("admin.membership.quota", { used: aiQuota?.used ?? 0, limit: quotaLimit });
  return (
    <div className="mt-4 rounded-2xl border border-white/15 bg-white/5 p-4 text-sm text-white/70">
      <div className="space-y-1">
        <p className="text-xs uppercase tracking-wide text-white/40">Membership</p>
        <p className="text-base font-semibold text-white">{status}</p>
        <p className="text-xs text-white/50">{quotaLabel}</p>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-xl border border-white/20 px-3 py-1 text-xs text-white/80 hover:border-white/60 disabled:opacity-40"
          disabled={isUpdating}
          onClick={() => onAdjust({ action: "extend", days: 30 })}
        >
          {t("admin.membership.extend30")}
        </button>
        <button
          type="button"
          className="rounded-xl border border-white/20 px-3 py-1 text-xs text-white/80 hover:border-white/60 disabled:opacity-40"
          disabled={isUpdating}
          onClick={() => onAdjust({ action: "extend", days: 90 })}
        >
          {t("admin.membership.extend90")}
        </button>
        <button
          type="button"
          className="rounded-xl border border-white/20 px-3 py-1 text-xs text-white/80 hover:border-white/60 disabled:opacity-40"
          disabled={isUpdating}
          onClick={() => onAdjust({ action: "revoke" })}
        >
          {t("admin.membership.revoke")}
        </button>
      </div>
      {error ? (
        <p className="mt-2 text-xs text-rose-300">
          {extractErrorMessage(error, t("admin.membership.error"))}
        </p>
      ) : null}
    </div>
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

  const lastActive = snapshot.last_active_at
    ? formatTimestamp(snapshot.last_active_at) ?? "No activity"
    : "No activity";
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

function formatLogTimestamp(timestamp?: string) {
  if (!timestamp) return "—";
  try {
    return new Date(timestamp).toLocaleString();
  } catch {
    return timestamp;
  }
}

function formatDuration(ms?: number | null) {
  if (typeof ms !== "number" || Number.isNaN(ms)) {
    return "";
  }
  if (ms < 1000) {
    return `${ms.toFixed(0)} ms`;
  }
  const seconds = ms / 1000;
  if (seconds < 60) {
    return `${seconds.toFixed(1)} s`;
  }
  const minutes = seconds / 60;
  return `${minutes.toFixed(1)} min`;
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
                isSaving={updateQuestionMutation.isPending}
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
  const [decorations, setDecorations] = useState<StepDirective[]>(
    parseDecorationsFromMetadata(question.metadata)
  );
  const [highlightModal, setHighlightModal] = useState<HighlightModalState | null>(null);
  const [highlightError, setHighlightError] = useState<string | null>(null);
  const [sourcePreview, setSourcePreview] = useState<FigureSource | null>(null);
  const [sourcePreviewLoading, setSourcePreviewLoading] = useState(false);
  const [sourcePreviewError, setSourcePreviewError] = useState<string | null>(null);
  const linkedSourceName =
    question.source?.original_name || question.source?.filename || "—";
  const linkedPageLabel = question.source_page ?? question.page ?? "—";

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

  const loadSourcePreview = useCallback(async () => {
    if (!question.source?.id) {
      setSourcePreview(null);
      setSourcePreviewError(null);
      setSourcePreviewLoading(false);
      return;
    }
    setSourcePreviewLoading(true);
    setSourcePreviewError(null);
    try {
      const preview = await fetchQuestionFigureSource(
        question.id,
        question.source_page ?? undefined
      );
      setSourcePreview(preview);
    } catch (err) {
      setSourcePreview(null);
      setSourcePreviewError(extractErrorMessage(err, "Failed to load PDF preview"));
    } finally {
      setSourcePreviewLoading(false);
    }
  }, [question.id, question.source?.id, question.source_page]);

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
    setDecorations(parseDecorationsFromMetadata(question.metadata));
    setHighlightModal(null);
    setHighlightError(null);
    if (question.source?.id) {
      loadSourcePreview();
    } else {
      setSourcePreview(null);
      setSourcePreviewError(null);
      setSourcePreviewLoading(false);
    }
  }, [question, buildMediaUrl, loadSourcePreview]);

  useEffect(() => {
    if (!metadataRaw.trim()) {
      setDecorations([]);
      return;
    }
    try {
      const parsed = JSON.parse(metadataRaw);
      setDecorations(parseDecorationsFromMetadata(parsed));
    } catch {
      // Ignore invalid JSON to avoid interrupting manual edits.
    }
  }, [metadataRaw]);

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
    if (!question.source?.id) {
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
  }, [computeSelectionFromFigure, question.id, question.source?.id]);

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

  const updateDecorations = useCallback((next: StepDirective[]) => {
    setDecorations(next);
    setMetadataRaw((prev) => {
      let parsed: Record<string, unknown>;
      try {
        parsed = prev.trim() ? JSON.parse(prev) : {};
      } catch {
        parsed = {};
      }
      parsed.decorations = sanitizeDecorationsForMetadata(next);
      return JSON.stringify(parsed, null, 2);
    });
  }, []);

  const openHighlightModal = useCallback(async () => {
    if (!question.source?.id) {
      setHighlightError("Link this question to a PDF source before annotating underlines.");
      return;
    }
    setHighlightError(null);
    setHighlightModal({
      questionId: question.id,
      loading: true,
    });
    try {
      const source = await fetchQuestionFigureSource(
        question.id,
        question.source_page ?? undefined
      );
      setHighlightModal((prev) =>
        prev && prev.questionId === question.id
          ? { ...prev, source, loading: false, page: source.page }
          : prev
      );
    } catch (err) {
      setHighlightError(extractErrorMessage(err, "Failed to load PDF page"));
      setHighlightModal((prev) =>
        prev && prev.questionId === question.id ? { ...prev, loading: false } : prev
      );
    }
  }, [question.id, question.source?.id, question.source_page]);

  const closeHighlightModal = useCallback(() => {
    setHighlightModal(null);
    setHighlightError(null);
  }, []);

  const handleApplyDecorations = useCallback(
    (next: StepDirective[]) => {
      updateDecorations(next);
      setHighlightModal(null);
      setHighlightError(null);
    },
    [updateDecorations]
  );

  const handleRemoveDecoration = useCallback(
    (index: number) => {
      updateDecorations(decorations.filter((_, idx) => idx !== index));
    },
    [decorations, updateDecorations]
  );

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
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wide text-white/50">Linked PDF</p>
            <p className="text-[13px] text-white/60">
              {linkedSourceName} · Page {linkedPageLabel}
            </p>
          </div>
          {question.source?.id && (
            <button
              type="button"
              className="rounded-xl border border-white/20 px-4 py-2 text-sm font-semibold text-white/80 disabled:opacity-40"
              onClick={loadSourcePreview}
              disabled={sourcePreviewLoading}
            >
              {sourcePreviewLoading ? "Loading..." : "Reload preview"}
            </button>
          )}
        </div>
        {question.source?.id ? (
          sourcePreviewLoading ? (
            <div className="flex h-48 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-sm text-white/60">
              Loading preview...
            </div>
          ) : sourcePreview ? (
            <div className="overflow-hidden rounded-2xl border border-white/10 bg-black/30 p-2">
              <img
                src={sourcePreview.image}
                alt="Linked PDF page"
                className="max-h-[480px] w-full rounded-xl object-contain"
              />
            </div>
          ) : (
            <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-rose-200">
              {sourcePreviewError || "Preview unavailable."}
            </div>
          )
        ) : (
          <p className="text-sm text-white/60">
            Link this question to a PDF source and page to view the preview.
          </p>
        )}
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
            disabled={!question.source?.id}
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
        {!question.source?.id && (
          <p className="text-xs text-amber-200">
            Link this question to a PDF source and page to enable figure cropping.
          </p>
        )}
        {figureError && !figureModal && <p className="text-xs text-red-400">{figureError}</p>}
      </section>

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wide text-white/50">Manual underlines</p>
            <p className="text-[13px] text-white/60">仅支持 Passage 段落中的下划线。</p>
          </div>
          <button
            type="button"
            className="rounded-xl border border-white/30 px-4 py-2 text-sm font-semibold text-white/80 disabled:opacity-40"
            onClick={openHighlightModal}
            disabled={!question.source?.id}
          >
            {decorations.length ? "Edit underlines" : "Annotate underlines"}
          </button>
        </div>
        {highlightError && <p className="text-xs text-red-400">{highlightError}</p>}
        {!question.source?.id && (
          <p className="text-xs text-amber-200">
            Link this question to a PDF source/page to enable underline annotation.
          </p>
        )}
        {decorations.length ? (
          <ul className="space-y-2">
            {decorations.map((entry, index) => (
              <li
                key={`${entry.target}-${entry.choice_id ?? "0"}-${index}`}
                className="flex items-start justify-between gap-3 rounded-2xl border border-white/10 bg-white/5 px-4 py-3"
              >
                <div className="text-sm text-white/80">
                  <p className="font-semibold text-white">{entry.text}</p>
                  <p className="text-xs text-white/50">
                    Target: {entry.target === "stem" ? "Question" : entry.target}
                    {entry.choice_id ? ` · Choice ${entry.choice_id}` : ""}
                    {entry.action ? ` · ${entry.action}` : ""}
                  </p>
                </div>
                <button
                  type="button"
                  className="rounded-full border border-white/20 px-3 py-1 text-xs text-white/70 hover:text-white"
                  onClick={() => handleRemoveDecoration(index)}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-white/60">
            No manual highlights recorded yet. Use the annotate tool to add them.
          </p>
        )}
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
    {highlightModal && (
      <HighlightAnnotationModal
        question={question}
        stemText={stemText}
        passageText={passageText}
        decorations={decorations}
        modal={highlightModal}
        onClose={closeHighlightModal}
        onSave={handleApplyDecorations}
      />
    )}
    </>
  );
}

type HighlightAnnotationModalProps = {
  question: AdminQuestion;
  stemText: string;
  passageText: string;
  decorations: StepDirective[];
  modal: HighlightModalState;
  onClose: () => void;
  onSave: (decorations: StepDirective[]) => void;
};

function HighlightAnnotationModal({
  question,
  stemText,
  passageText,
  decorations,
  modal,
  onClose,
  onSave,
}: HighlightAnnotationModalProps) {
  const { t } = useI18n();
  const [draft, setDraft] = useState<StepDirective[]>(decorations);
  const [pendingText, setPendingText] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const pageLabel = question.source_page ?? question.page ?? "—";

  useEffect(() => {
    setDraft(decorations);
  }, [decorations]);

  const handleTextSelection = useCallback((event: React.SyntheticEvent<HTMLTextAreaElement>) => {
    const el = event.currentTarget;
    const start = el.selectionStart ?? 0;
    const end = el.selectionEnd ?? 0;
    if (start === end) return;
    const snippet = el.value.slice(start, end).trim();
    if (!snippet) return;
    setPendingText(snippet);
    setLocalError(null);
  }, []);

  const handleAddDecoration = useCallback(() => {
    const snippet = pendingText.trim();
    if (!snippet) {
      setLocalError("请先在文本里选择需要高亮的内容。");
      return;
    }
    const entry: StepDirective = {
      target: "passage",
      text: snippet,
      action: "underline",
    };
    setDraft((prev) => [...prev, entry]);
    setPendingText("");
    setLocalError(null);
  }, [pendingText]);

  const handleRemoveDraft = useCallback((index: number) => {
    setDraft((prev) => prev.filter((_, idx) => idx !== index));
  }, []);

  const hasChanges = useMemo(() => {
    if (draft.length !== decorations.length) return true;
    return draft.some((entry, index) => {
      const existing = decorations[index];
      return (
        entry.target !== existing.target ||
        entry.text !== existing.text ||
        entry.action !== existing.action
      );
    });
  }, [draft, decorations]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
      <div className="flex h-full w-full max-w-6xl flex-col rounded-2xl bg-[#050E1F] shadow-2xl max-h-[95vh]">
        <div className="flex items-center justify-between border-b border-white/10 px-5 py-3">
          <div>
            <p className="text-base font-semibold text-white">
              Manual underline · {question.question_uid || `Question #${question.id}`}
            </p>
            <p className="text-xs text-white/60">Page {pageLabel}</p>
          </div>
          <button
            className="rounded-full border border-white/20 px-3 py-1 text-xs text-white/70 hover:text-white"
            onClick={onClose}
          >
            Close
          </button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          <div className="space-y-3">
            <div className="space-y-2">
              <p className="text-sm font-semibold text-white">Linked PDF page preview</p>
              <p className="text-xs text-white/60">
                来自题目关联的 PDF 页（不能切换其他页）。
              </p>
              <div className="rounded-2xl border border-white/10 bg-black/40 p-3">
                {modal.loading ? (
                  <div className="flex h-[320px] items-center justify-center text-sm text-white/60">
                    Loading page preview...
                  </div>
                ) : modal.source ? (
                  <img
                    src={modal.source.image}
                    alt="PDF page preview"
                    className="max-h-[520px] w-full rounded-xl object-contain"
                  />
                ) : (
                  <div className="flex h-[320px] items-center justify-center text-sm text-rose-200">
                    Unable to load PDF preview.
                  </div>
                )}
              </div>
            </div>
            <div>
              <div>
                <p className="text-sm font-semibold text-white">Select passage text</p>
                <p className="text-xs text-white/60">仅支持 Passage 中的下划线。</p>
              </div>
              <label className="text-xs uppercase tracking-wide text-white/40">
                Passage
                <textarea
                  className="mt-1 h-48 w-full rounded-2xl border border-white/15 bg-white/5 px-3 py-2 text-sm text-white"
                  value={passageText}
                  readOnly
                  onSelect={handleTextSelection}
                />
              </label>
            </div>
          </div>
          <div className="grid gap-4 lg:grid-cols-[1.1fr_minmax(0,1fr)]">
            <div className="space-y-3 rounded-2xl border border-white/10 bg-white/5 p-4">
              <p className="text-sm font-semibold text-white">New underline</p>
              <p className="text-xs text-white/60">
                SAT official passages只会在原文中以下划线标注重点。请在上方 Passage 文本中拖拽
                选择后点击“Add underline”。
              </p>
              <label className="text-xs uppercase tracking-wide text-white/50">
                Selected text
                <textarea
                  className="mt-1 w-full rounded-xl border border-white/20 bg-white/5 px-3 py-2 text-sm text-white"
                  rows={3}
                  value={pendingText}
                  onChange={(e) => setPendingText(e.target.value)}
                  placeholder="Select text above or paste content here"
                />
              </label>
              {localError && <p className="text-xs text-red-400">{localError}</p>}
              <button
                type="button"
                className="rounded-xl border border-white/20 px-3 py-2 text-sm font-semibold text-white/80"
                onClick={handleAddDecoration}
              >
                Add underline
              </button>
              <p className="text-xs text-white/50">
                记得在关闭窗口后点击“Save question”保存最终更改。
              </p>
            </div>
            <div className="space-y-3 rounded-2xl border border-white/10 bg-white/5 p-4">
              <p className="text-sm font-semibold text-white">
                Highlights ({draft.length})
              </p>
              {draft.length ? (
                <ul className="space-y-2 text-sm text-white/80">
                  {draft.map((entry, idx) => (
                    <li
                      key={`${entry.target}-${entry.choice_id ?? "none"}-${idx}`}
                      className="rounded-xl border border-white/10 bg-black/30 p-3"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="font-semibold text-white">{entry.text}</p>
                          <p className="text-xs text-white/50">
                            {entry.target === "stem" ? "Question" : entry.target}
                            {entry.choice_id ? ` · Choice ${entry.choice_id}` : ""}
                            {entry.action ? ` · ${entry.action}` : ""}
                          </p>
                        </div>
                        <button
                          type="button"
                          className="rounded-full border border-white/20 px-3 py-1 text-xs text-white/70 hover:text-white"
                          onClick={() => handleRemoveDraft(idx)}
                        >
                          Remove
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-white/60">No annotations yet.</p>
              )}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap justify-end gap-3 border-t border-white/10 px-5 py-4">
          <button
            className="rounded-xl border border-white/20 px-4 py-2 text-sm text-white/80"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            className="rounded-xl bg-white px-4 py-2 text-sm font-semibold text-[#050E1F] disabled:opacity-50"
            onClick={() => onSave(draft)}
            disabled={!hasChanges}
          >
            Save highlights
          </button>
        </div>
      </div>
    </div>
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
  const [selectedQuestionIds, setSelectedQuestionIds] = useState<number[]>([]);
  const [deleteSourceError, setDeleteSourceError] = useState<string | null>(null);
  const queryClient = useQueryClient();

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
    setSelectedQuestionIds([]);
  }, [selectedSourceId]);

  const sourceDetailQuery = useQuery({
    queryKey: ["admin-source-detail", selectedSourceId, detailPage],
    queryFn: () =>
      selectedSourceId
        ? getAdminSourceDetail(selectedSourceId, { page: detailPage, per_page: DETAIL_PAGE_SIZE })
        : Promise.resolve(null),
    enabled: Boolean(selectedSourceId),
  });

  const detailPagination = sourceDetailQuery.data?.pagination;
  const hasDetailPagination = detailPagination && detailPagination.pages > 1;
  const detailQuestions = sourceDetailQuery.data?.questions ?? [];

  useEffect(() => {
    setSelectedQuestionIds([]);
  }, [detailPage, selectedSourceId]);

  const deleteQuestionsMutation = useMutation({
    mutationFn: (ids: number[]) => deleteQuestionsBulk(ids),
    onSuccess: () => {
      setSelectedQuestionIds([]);
      queryClient.invalidateQueries({ queryKey: ["admin-source-detail"] });
      queryClient.invalidateQueries({ queryKey: ["admin-sources"] });
    },
  });

  const deleteSourceMutation = useMutation({
    mutationFn: (sourceId: number) => deleteSource(sourceId),
    onSuccess: () => {
      setSelectedSourceId(null);
      setDeleteSourceError(null);
      queryClient.invalidateQueries({ queryKey: ["admin-sources"] });
    },
    onError: (error: unknown) => {
      setDeleteSourceError(extractErrorMessage(error, "Failed to delete collection."));
    },
  });

  const toggleQuestionSelection = (questionId: number) => {
    setSelectedQuestionIds((prev) =>
        prev.includes(questionId)
        ? prev.filter((id) => id !== questionId)
        : [...prev, questionId]
    );
  };

  const allVisibleSelected =
    detailQuestions.length > 0 &&
    detailQuestions.every((question) => selectedQuestionIds.includes(question.id));

  const handleToggleAll = () => {
    if (allVisibleSelected) {
      setSelectedQuestionIds([]);
      return;
    }
    setSelectedQuestionIds(detailQuestions.map((question) => question.id));
  };

  const handleBulkDelete = () => {
    if (!selectedQuestionIds.length) {
      return;
    }
    if (
      !window.confirm(
        `Delete ${selectedQuestionIds.length} selected question(s)? This cannot be undone.`
      )
    ) {
      return;
    }
    deleteQuestionsMutation.mutate(selectedQuestionIds);
  };

  const handleDeleteCollection = () => {
    if (!selectedSourceId) return;
    if (
      !window.confirm(
        "Delete this PDF collection permanently? This will remove the collection record."
      )
    ) {
      return;
    }
    deleteSourceMutation.mutate(selectedSourceId);
  };

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
              <div className="mt-3 flex items-center justify-between gap-4">
                <p className="text-xs text-white/50">
                  {selectedQuestionIds.length
                    ? `${selectedQuestionIds.length} selected`
                    : "Select questions to delete"}
                </p>
                <div className="flex items-center gap-2">
                  {selectedSourceId ? (
                    <Link
                      href={`/practice?sourceId=${selectedSourceId}`}
                      target="_blank"
                      className="rounded-full border border-white/30 px-3 py-1 text-xs font-semibold text-white/80 hover:border-white/60"
                    >
                      Test this collection
                    </Link>
                  ) : null}
                  <button
                    type="button"
                    className="rounded-full border border-white/20 px-3 py-1 text-xs text-white/70 hover:border-white/50"
                    onClick={handleToggleAll}
                    disabled={!detailQuestions.length}
                  >
                    {allVisibleSelected ? "Deselect page" : "Select page"}
                  </button>
                  <button
                    type="button"
                    className="rounded-full border border-rose-500/60 px-3 py-1 text-xs font-semibold text-rose-100 hover:bg-rose-500/10 disabled:opacity-40"
                    disabled={!selectedQuestionIds.length || deleteQuestionsMutation.isPending}
                    onClick={handleBulkDelete}
                  >
                    {deleteQuestionsMutation.isPending
                      ? "Deleting..."
                      : `Delete selected (${selectedQuestionIds.length})`}
                  </button>
                  <button
                    type="button"
                    className="rounded-full border border-rose-300/60 px-3 py-1 text-xs font-semibold text-rose-100 hover:bg-rose-500/10 disabled:opacity-40"
                    disabled={
                      !!sourceDetailQuery.data.source.question_count ||
                      deleteSourceMutation.isPending
                    }
                    onClick={handleDeleteCollection}
                  >
                    {deleteSourceMutation.isPending ? "Deleting..." : "Delete collection"}
                  </button>
                </div>
              </div>
              <div className="mt-3 overflow-auto rounded-xl border border-white/10">
                <table className="w-full text-left text-sm">
                  <thead className="bg-white/5 text-xs uppercase tracking-wide text-white/60">
                    <tr>
                      <th className="px-4 py-3 w-10">
                        <input
                          type="checkbox"
                          className="scale-110 accent-white"
                          checked={detailQuestions.length > 0 && allVisibleSelected}
                          onChange={handleToggleAll}
                          disabled={!detailQuestions.length}
                        />
                      </th>
                      <th className="px-4 py-3">Question</th>
                      <th className="px-4 py-3">Section</th>
                      <th className="px-4 py-3">Difficulty</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detailQuestions.map((question) => {
                      const checked = selectedQuestionIds.includes(question.id);
                      return (
                      <tr
                        key={question.id}
                        className="border-t border-white/5 hover:bg-white/5 cursor-pointer"
                        onClick={() => onJumpToQuestion(question.id)}
                      >
                        <td className="px-4 py-3">
                          <input
                            type="checkbox"
                            className="scale-110 accent-white"
                            checked={checked}
                            onChange={(event) => {
                              event.stopPropagation();
                              toggleQuestionSelection(question.id);
                            }}
                            onClick={(event) => event.stopPropagation()}
                          />
                        </td>
                        <td className="px-4 py-3 text-white">
                          {question.question_uid || `#${question.id}`}
                        </td>
                        <td className="px-4 py-3 text-white/80">{question.section}</td>
                        <td className="px-4 py-3 text-white/80">
                          {question.difficulty_level ?? "—"}
                        </td>
                      </tr>
                    )})}
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
              {deleteQuestionsMutation.isError ? (
                <p className="mt-2 text-xs text-rose-300">
                  {extractErrorMessage(deleteQuestionsMutation.error, "Failed to delete questions.")}
                </p>
              ) : null}
              {deleteSourceError ? (
                <p className="mt-1 text-xs text-rose-300">{deleteSourceError}</p>
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

function QuestionCategoriesTab({
  onJumpToQuestion,
}: {
  onJumpToQuestion: (questionId: number) => void;
}) {
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const categoriesQuery = useQuery({
    queryKey: ["admin-question-categories"],
    queryFn: getQuestionCategories,
  });
  const categories = categoriesQuery.data ?? [];

  useEffect(() => {
    if (categories.length && !selectedKey) {
      setSelectedKey(categories[0].key);
      setPage(1);
    } else if (selectedKey && categories.every((cat) => cat.key !== selectedKey)) {
      setSelectedKey(categories[0]?.key ?? null);
      setPage(1);
    }
  }, [categories, selectedKey]);

  const questionsQuery = useQuery({
    queryKey: ["admin-category-questions", selectedKey, page],
    queryFn: () =>
      selectedKey ? getAdminQuestions({ page, per_page: PAGE_SIZE, skill_tag: selectedKey }) : Promise.resolve(null),
    enabled: Boolean(selectedKey),
  });

  const selectedCategory = categories.find((cat) => cat.key === selectedKey) || null;
  const questions = questionsQuery.data?.items ?? [];

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[0.9fr_2fr]">
        <DashboardCard
          title="Question categories"
          subtitle="Browse skill tags and inspect the questions they contain."
        >
          {categoriesQuery.isLoading ? (
            <p className="py-6 text-center text-white/60">Loading categories…</p>
          ) : categories.length ? (
            <div className="space-y-2">
              {categories.map((category) => {
                const isActive = selectedKey === category.key;
                const rwCount = category.section_counts?.RW ?? 0;
                const mathCount = category.section_counts?.Math ?? 0;
                return (
                  <button
                    key={category.key}
                    className={`w-full rounded-2xl border px-4 py-3 text-left transition ${
                      isActive ? "border-white bg-white/10" : "border-white/10 hover:border-white/30"
                    }`}
                    onClick={() => {
                      setSelectedKey(category.key);
                      setPage(1);
                    }}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-semibold text-white">{category.label}</p>
                        <p className="text-xs text-white/60">{category.domain}</p>
                      </div>
                      <span className="chip-soft bg-white/10 text-white">
                        {category.question_count} question{category.question_count === 1 ? "" : "s"}
                      </span>
                    </div>
                    <div className="mt-2 flex gap-2 text-xs text-white/60">
                      <span className="chip-soft bg-blue-400/10 text-blue-200">RW {rwCount}</span>
                      <span className="chip-soft bg-emerald-400/10 text-emerald-200">Math {mathCount}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          ) : (
            <p className="py-6 text-center text-white/60">No categories found.</p>
          )}
        </DashboardCard>
        <DashboardCard
          title={selectedCategory ? selectedCategory.label : "Questions"}
          subtitle={
            selectedCategory
              ? `Showing questions tagged with ${selectedCategory.label}`
              : "Select a category to load its questions."
          }
        >
          {selectedCategory ? (
            <div className="space-y-3">
              <div className="overflow-auto rounded-xl border border-white/10">
                <table className="w-full text-left text-sm">
                  <thead className="bg-white/5 text-xs uppercase tracking-wide text-white/60">
                    <tr>
                      <th className="px-4 py-3">ID</th>
                      <th className="px-4 py-3">UID</th>
                      <th className="px-4 py-3">Section</th>
                      <th className="px-4 py-3">Skill tags</th>
                      <th className="px-4 py-3">Difficulty</th>
                    </tr>
                  </thead>
                  <tbody>
                    {questionsQuery.isLoading ? (
                      <tr>
                        <td colSpan={5} className="px-4 py-6 text-center text-white/60">
                          Loading questions…
                        </td>
                      </tr>
                    ) : questions.length ? (
                      questions.map((question) => (
                        <tr
                          key={question.id}
                          className="cursor-pointer border-t border-white/5 hover:bg-white/5"
                          onClick={() => onJumpToQuestion(question.id)}
                        >
                          <td className="px-4 py-3 text-white">{question.id}</td>
                          <td className="px-4 py-3 text-white/80">{question.question_uid || "—"}</td>
                          <td className="px-4 py-3 text-white/80">{question.section || "—"}</td>
                          <td className="px-4 py-3 text-white/70">
                            {(question.skill_tags || []).slice(0, 2).join(", ") || "—"}
                          </td>
                          <td className="px-4 py-3 text-white/70">
                            {question.difficulty_level != null ? question.difficulty_level : "—"}
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={5} className="px-4 py-6 text-center text-white/60">
                          No questions in this category.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              {questionsQuery.data ? (
                <PaginationControls
                  page={questionsQuery.data.page}
                  pages={Math.max(
                    Math.ceil((questionsQuery.data.total || 0) / (questionsQuery.data.per_page || PAGE_SIZE)),
                    1
                  )}
                  onPageChange={setPage}
                />
              ) : null}
            </div>
          ) : (
            <p className="py-6 text-center text-white/60">Select a category to view its questions.</p>
          )}
        </DashboardCard>
      </div>
    </div>
  );
}

function ImportTab() {
  return <ImportWorkspace variant="embedded" />;
}

function AIPaperGeneratorTab() {
  const OPENAI_LOG_STORAGE_KEY = "admin-ai-paper-openai-logs";
  const [name, setName] = useState("");
  const [page, setPage] = useState(1);
  const queryClient = useQueryClient();
  const [openaiLogs, setOpenaiLogs] = useState<OpenAILogEntry[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState<string | null>(null);
  const [logHeartbeatMap, setLogHeartbeatMap] = useState<Record<number, number>>({});
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteTargetId, setDeleteTargetId] = useState<number | null>(null);
  const jobsQuery = useQuery<PaginatedResponse<AIPaperJob>>({
    queryKey: ["admin-ai-papers", page],
    queryFn: () => listAIPaperJobs({ page, per_page: PAGE_SIZE }),
    refetchInterval: 2000,
    refetchIntervalInBackground: true,
  });
  const jobs = jobsQuery.data?.items ?? [];
  const deleteMutation = useMutation({
    mutationFn: (jobId: number) => deleteAIPaperJob(jobId),
    onMutate: (jobId) => {
      setDeleteTargetId(jobId);
      setDeleteError(null);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-ai-papers"] });
    },
    onError: (error: unknown) => {
      setDeleteError(extractErrorMessage(error, "Failed to delete AI paper job."));
    },
    onSettled: () => {
      setDeleteTargetId(null);
    },
  });
  useEffect(() => {
    const now = Date.now();
    setLogHeartbeatMap((prev) => {
      const changed: Record<number, number> = {};
      jobsQuery.data?.items?.forEach((job) => {
        if (prev[job.id] === undefined && job.created_at) {
          const createdMs = new Date(job.created_at).getTime();
          if (!Number.isNaN(createdMs)) {
            changed[job.id] = createdMs;
          }
        }
      });
      if (Object.keys(changed).length === 0) {
        return prev;
      }
      return { ...prev, ...changed };
    });
  }, [jobsQuery.data?.items]);

  const createMutation = useMutation({
    mutationFn: (payload: { name?: string }) => createAIPaperJob(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-ai-papers"] });
      setName("");
      jobsQuery.refetch();
    },
  });

  const resumeMutation = useMutation({
    mutationFn: (jobId: number) => resumeAIPaperJob(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-ai-papers"] });
    },
  });

  const loadOpenaiLogs = useCallback(async () => {
    try {
      setLogsLoading(true);
      setLogsError(null);
      const data = await fetchOpenaiLogs(OPENAI_LOG_LIMIT);
      const logs = Array.isArray(data?.logs) ? (data.logs as OpenAILogEntry[]) : [];
      const trimmed = logs.slice(0, OPENAI_LOG_LIMIT);
      setOpenaiLogs(trimmed);
      if (typeof window !== "undefined") {
        sessionStorage.setItem(OPENAI_LOG_STORAGE_KEY, JSON.stringify(trimmed));
      }
      if (logs.length) {
        setLogHeartbeatMap((prev) => {
          const next = { ...prev };
          let changed = false;
          logs.forEach((entry) => {
            if (!entry?.job_id || !entry.timestamp) {
              return;
            }
            const ts = new Date(entry.timestamp).getTime();
            if (!Number.isNaN(ts)) {
              next[entry.job_id] = ts;
              changed = true;
            }
          });
          return changed ? next : prev;
        });
      }
    } catch (error: unknown) {
      setLogsError(extractErrorMessage(error, "Failed to load OpenAI logs"));
    } finally {
      setLogsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const cached = sessionStorage.getItem(OPENAI_LOG_STORAGE_KEY);
      if (cached) {
        try {
          const parsed = JSON.parse(cached) as OpenAILogEntry[];
          if (Array.isArray(parsed) && parsed.length) {
            setOpenaiLogs(parsed.slice(0, OPENAI_LOG_LIMIT));
          }
        } catch {
          sessionStorage.removeItem(OPENAI_LOG_STORAGE_KEY);
        }
      }
    }
    loadOpenaiLogs();
  }, [loadOpenaiLogs]);

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
        if (payload?.type === "openai_log" && payload?.payload) {
          const entry = payload.payload as OpenAILogEntry;
          setOpenaiLogs((prev) => {
            const next = [entry, ...prev].slice(0, OPENAI_LOG_LIMIT);
            if (typeof window !== "undefined") {
              sessionStorage.setItem(OPENAI_LOG_STORAGE_KEY, JSON.stringify(next));
            }
            return next;
          });
          if (entry.job_id && entry.timestamp) {
            const ts = new Date(entry.timestamp).getTime();
            if (!Number.isNaN(ts)) {
              setLogHeartbeatMap((prev) => ({
                ...prev,
                [entry.job_id as number]: ts,
              }));
            }
          }
        }
      } catch (err) {
        console.error("Failed to parse OpenAI log event", err);
      }
    };
    source.onerror = () => {
      source.close();
    };

    return () => {
      source.close();
    };
  }, []);

  const pagination = jobsQuery.data?.pagination;

  const handleCreate = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = name.trim();
    createMutation.mutate({ name: trimmed || undefined });
  };

  const aiLogs = useMemo(
    () =>
      openaiLogs.filter((entry) =>
        (entry.purpose || "").toLowerCase().includes("ai-paper")
      ),
    [openaiLogs]
  );

  return (
    <div className="space-y-4">
      <DashboardCard
        title="AI Paper Studio"
        subtitle="Create fully structured SAT mock sets with one click. The generator will follow the Digital SAT blueprint and attach the output as a new PDF Collection."
      >
        <form className="flex flex-col gap-3 lg:flex-row" onSubmit={handleCreate}>
          <input
            className="flex-1 rounded-xl border border-white/20 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-white/40"
            placeholder="Custom paper name (optional)"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <button
            className="rounded-xl bg-white px-4 py-2 text-sm font-semibold text-[#050E1F]"
            disabled={createMutation.isPending}
          >
            {createMutation.isPending ? "Generating…" : "Create AI Paper"}
          </button>
        </form>
        <p className="mt-4 text-sm leading-relaxed text-white/70">
          Each paper contains 2 Reading &amp; Writing modules (27 questions each) and 2 Math modules (22 questions each).
          The system precomputes module blueprints (difficulty, passage requirements, figure slots) before calling the
          OpenAI pipelines for passage, problem, answer, explanation, and figure generation.
        </p>
      </DashboardCard>

      <DashboardCard
        title="Generation history"
        subtitle="Track the most recent AI paper jobs, monitor progress, and jump into their resulting collections."
      >
        <div className="overflow-auto rounded-xl border border-white/10">
          <table className="w-full text-left text-sm">
            <thead className="bg-white/5 text-xs uppercase tracking-wide text-white/60">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Stage & progress</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Source</th>
                <th className="px-4 py-3">Created</th>
              </tr>
            </thead>
            <tbody>
              {jobsQuery.isLoading ? (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-white/60">
                    Loading jobs...
                  </td>
                </tr>
              ) : jobs.length ? (
                jobs.map((job: AIPaperJob) => {
                  const stageLabel = getJobStageLabel(job);
                  const progressPercent = Math.min(100, Math.max(0, job.progress));
                  const totalSlotsLabel =
                    job.total_tasks > 0
                      ? `${job.completed_tasks}/${job.total_tasks} slots`
                      : "—";
                  const lastLogMs =
                    logHeartbeatMap[job.id] ??
                    (job.created_at ? new Date(job.created_at).getTime() : Date.now());
                  const now = Date.now();
                  const canResume =
                    job.status !== "completed" &&
                    !resumeMutation.isPending &&
                    lastLogMs !== undefined &&
                    now - lastLogMs > 120_000;
                  return (
                    <tr key={job.id} className="border-t border-white/5 align-top">
                      <td className="px-4 py-3 font-semibold text-white">{job.name}</td>
                      <td className="px-4 py-3">
                        <div className="flex flex-col gap-1.5">
                          <div className="flex items-center justify-between text-xs text-white/60">
                            <span>{stageLabel}</span>
                            <span>{progressPercent.toFixed(0)}%</span>
                          </div>
                          <div className="h-2 w-full rounded-full bg-white/10">
                            <div
                              className="h-full rounded-full bg-gradient-to-r from-sky-400 via-indigo-400 to-fuchsia-400 shadow-lg transition-[width]"
                              style={{ width: `${progressPercent}%` }}
                            />
                          </div>
                          <div className="flex items-center justify-between text-[11px] text-white/45">
                            <span>{job.status_message || "..."}</span>
                            <span>{totalSlotsLabel}</span>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <span
                            className={`rounded-full px-2 py-1 text-xs font-semibold ${
                              job.status === "completed"
                                ? "bg-emerald-400/20 text-emerald-300"
                                : job.status === "running"
                                ? "bg-sky-400/20 text-sky-200"
                                : job.status === "cancelling"
                                ? "bg-amber-400/20 text-amber-200"
                                : job.status === "cancelled"
                                ? "bg-amber-500/20 text-amber-200"
                                : job.status === "failed"
                                ? "bg-rose-500/20 text-rose-200"
                                : "bg-white/10 text-white/70"
                            }`}
                          >
                            {job.status}
                          </span>
                          {job.status !== "completed" && (
                            <button
                              type="button"
                              className="rounded-full border border-white/30 px-2 py-0.5 text-xs text-white/80 hover:border-white/60 disabled:opacity-40"
                              onClick={() => resumeMutation.mutate(job.id)}
                              disabled={!canResume}
                            >
                              {resumeMutation.isPending ? "Resuming..." : "Resume"}
                            </button>
                          )}
                          <button
                            type="button"
                            className="rounded-full border border-red-500/40 px-2 py-0.5 text-xs text-red-200 hover:border-red-400 disabled:opacity-40"
                            onClick={() => {
                              const confirmMessage =
                                job.status === "running"
                                  ? `Job "${job.name}" is still running. Deleting it will immediately cancel generation and remove all linked questions. Continue?`
                                  : `Delete "${job.name}"? This removes the generated collection and all linked questions.`;
                              if (window.confirm(confirmMessage)) {
                                deleteMutation.mutate(job.id);
                              }
                            }}
                            disabled={deleteMutation.isPending}
                          >
                            {deleteMutation.isPending && deleteTargetId === job.id
                              ? "Deleting…"
                              : job.status === "running"
                              ? "Force delete"
                              : "Delete"}
                          </button>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        {job.source_id ? (
                          <span className="text-white">#{job.source_id}</span>
                        ) : (
                          <span className="text-white/40">Pending</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-white/60">
                        {job.created_at ? new Date(job.created_at).toLocaleString() : "—"}
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-white/60">
                    No jobs yet. Kick off your first AI-generated paper using the form above.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {deleteError && (
          <p className="mt-3 text-sm text-rose-300">{deleteError}</p>
        )}
        {pagination && (
          <div className="mt-4 flex items-center justify-between text-sm text-white/70">
            <button
              className="rounded-full border border-white/20 px-3 py-1 disabled:border-white/5 disabled:text-white/30"
              onClick={() => setPage((prev) => Math.max(prev - 1, 1))}
              disabled={!pagination.has_prev}
            >
              Previous
            </button>
            <span>
              Page {pagination.page} / {Math.max(pagination.pages, 1)}
            </span>
            <button
              className="rounded-full border border-white/20 px-3 py-1 disabled:border-white/5 disabled:text-white/30"
              onClick={() => setPage((prev) => (pagination.has_next ? prev + 1 : prev))}
              disabled={!pagination.has_next}
            >
              Next
            </button>
          </div>
        )}
      </DashboardCard>

      <DashboardCard
        title="OpenAI API Logs"
        subtitle={`AI paper generation calls · showing ${aiLogs.length} entr${
          aiLogs.length === 1 ? "y" : "ies"
        }`}
      >
        <div className="mb-3 flex flex-wrap items-center justify-between text-xs text-white/60">
          <span>
            Includes only log entries whose purpose contains <code>ai-paper</code>
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
        {aiLogs.length === 0 && !logsLoading ? (
          <p className="text-sm text-white/50">
            No AI paper logs yet. Start or resume a job to see real-time activity.
          </p>
        ) : (
          <div className="space-y-2 overflow-auto pr-1 text-xs text-white/70 max-h-[60vh] min-h-[240px]">
            {aiLogs.map((entry, index) => (
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
                  Job #{entry.job_id ?? "—"} · {entry.purpose || entry.stage || "AI paper"}
                </p>
                <p className="text-[11px] text-white/60">
                  {entry.attempt !== undefined
                    ? `Attempt ${entry.attempt}/${entry.max_attempts ?? "?"}`
                    : "Attempt —"}
                  {entry.model ? ` · ${entry.model}` : ""}
                  {entry.status_code ? ` · HTTP ${entry.status_code}` : ""}
                  {entry.duration_ms !== undefined && entry.duration_ms !== null
                    ? ` · ${formatDuration(entry.duration_ms)}`
                    : ""}
                </p>
                {entry.message && (
                  <p className="text-[11px] text-white/60">Message: {entry.message}</p>
                )}
                {entry.error && (
                  <p className="text-[11px] text-red-300 break-words">Error: {entry.error}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </DashboardCard>
    </div>
  );
}

function getJobStageLabel(job: AIPaperJob): string {
  const fallback = job.stage
    ? job.stage.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase())
    : job.status?.replace(/_/g, " ") ?? "Queued";

  if (!job.stage) {
    return STAGE_LABELS[job.status ?? "pending"] ?? fallback;
  }
  if (STAGE_LABELS[job.stage]) {
    return STAGE_LABELS[job.stage];
  }
  if (job.stage.startsWith("module_")) {
    const configWithBlueprint = job.config as {
      blueprint?: { modules?: Array<{ code: string; label: string }> };
    };
    const matched = configWithBlueprint.blueprint?.modules?.find(
      (module) => `module_${module.code?.toLowerCase()}` === job.stage
    );
    if (matched?.label) {
      return matched.label;
    }
    const code = job.stage.replace("module_", "").toUpperCase();
    return `Module ${code}`;
  }
  return fallback;
}

type MembershipStatusFilter = "pending" | "approved" | "rejected" | "all";

function MembershipTab() {
  const [status, setStatus] = useState<MembershipStatusFilter>("pending");
  const [page, setPage] = useState(1);

  const ordersQuery = useQuery({
    queryKey: ["admin-membership-orders", page, status],
    queryFn: () =>
      listMembershipOrdersAdmin({
        page,
        per_page: PAGE_SIZE,
        status: status === "all" ? undefined : status,
      }),
  });

  const decisionMutation = useMutation({
    mutationFn: (payload: { id: number; action: "approve" | "reject"; note?: string }) =>
      decideMembershipOrder(payload.id, { action: payload.action, note: payload.note }),
    onSuccess: () => {
      ordersQuery.refetch();
    },
  });

  const orders = ordersQuery.data?.orders ?? [];
  const pagination = ordersQuery.data?.pagination;

  const statusOptions: { value: MembershipStatusFilter; label: string }[] = [
    { value: "pending", label: "Pending" },
    { value: "approved", label: "Approved" },
    { value: "rejected", label: "Rejected" },
    { value: "all", label: "All" },
  ];

  function formatOrderPrice(order: MembershipOrder) {
    try {
      return new Intl.NumberFormat(undefined, {
        style: "currency",
        currency: order.currency || "USD",
      }).format(order.price_cents / 100);
    } catch {
      return `$${order.price_cents / 100}`;
    }
  }

  function handleDecision(orderId: number, action: "approve" | "reject") {
    const note =
      action === "reject"
        ? window.prompt("Add a note for the user? (optional)") || undefined
        : undefined;
    decisionMutation.mutate({ id: orderId, action, note });
  }

  return (
    <div className="space-y-4">
      <DashboardCard title="Membership orders" subtitle="Review and approve manual subscription requests.">
        <div className="flex flex-wrap gap-2">
          {statusOptions.map((option) => (
            <button
              key={option.value}
              className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                status === option.value
                  ? "bg-white text-[#050E1F]"
                  : "border border-white/30 text-white/70 hover:border-white/50"
              }`}
              onClick={() => {
                setStatus(option.value as typeof status);
                setPage(1);
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="mt-4 overflow-x-auto rounded-2xl border border-white/10">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wide text-white/50">
                <th className="px-4 py-3">Order</th>
                <th className="px-4 py-3">User</th>
                <th className="px-4 py-3">Plan</th>
                <th className="px-4 py-3">Price</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {ordersQuery.isLoading ? (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-white/60">
                    Loading orders...
                  </td>
                </tr>
              ) : orders.length ? (
                orders.map((order) => (
                  <tr key={order.id} className="border-t border-white/10">
                    <td className="px-4 py-3">
                      <div className="text-white font-semibold">#{order.id}</div>
                      <div className="text-xs text-white/50">
                        {new Date(order.created_at).toLocaleString()}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <p className="text-white">{order.user?.email ?? "—"}</p>
                      <p className="text-xs text-white/50">{order.user?.username ?? "—"}</p>
                    </td>
                    <td className="px-4 py-3 text-white">
                      {order.plan === "monthly"
                        ? "Monthly"
                        : "Quarterly"}
                    </td>
                    <td className="px-4 py-3 text-white/80">{formatOrderPrice(order)}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`rounded-full px-2 py-1 text-xs font-semibold ${
                          order.status === "pending"
                            ? "bg-amber-500/20 text-amber-100"
                            : order.status === "approved"
                            ? "bg-emerald-500/20 text-emerald-100"
                            : "bg-rose-500/20 text-rose-100"
                        }`}
                      >
                        {order.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {order.status === "pending" ? (
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            className="rounded-full border border-emerald-400/60 px-3 py-1 text-xs text-emerald-100 hover:bg-emerald-500/10 disabled:opacity-40"
                            onClick={() => handleDecision(order.id, "approve")}
                            disabled={decisionMutation.isPending}
                          >
                            Approve
                          </button>
                          <button
                            type="button"
                            className="rounded-full border border-rose-400/60 px-3 py-1 text-xs text-rose-100 hover:bg-rose-500/10 disabled:opacity-40"
                            onClick={() => handleDecision(order.id, "reject")}
                            disabled={decisionMutation.isPending}
                          >
                            Reject
                          </button>
                        </div>
                      ) : (
                        <span className="text-xs text-white/40">—</span>
                      )}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-white/60">
                    No orders found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {pagination && (
          <PaginationControls
            page={pagination.page}
            pages={pagination.pages || 1}
            onPageChange={setPage}
          />
        )}
        {decisionMutation.isError && (
          <p className="mt-3 text-xs text-rose-300">
            {extractErrorMessage(decisionMutation.error, "Failed to update order.")}
          </p>
        )}
      </DashboardCard>
    </div>
  );
}

function GeneralSettingsTab() {
  const { t } = useI18n();
  const [emailInput, setEmailInput] = useState<string | null>(null);
  const [localMessage, setLocalMessage] = useState<string | null>(null);

  const settingsQuery = useQuery({
    queryKey: ["admin-general-settings"],
    queryFn: getGeneralSettings,
  });

  useEffect(() => {
    if (settingsQuery.data && emailInput === null) {
      setEmailInput(settingsQuery.data.suggestion_email ?? "");
    }
  }, [settingsQuery.data, emailInput]);

  const updateMutation = useMutation({
    mutationFn: (payload: GeneralSettings) => updateGeneralSettings(payload),
    onSuccess: (settings) => {
      setLocalMessage(t("admin.generalSettings.saved"));
      setEmailInput(settings.suggestion_email ?? "");
    },
  });

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setLocalMessage(null);
    updateMutation.mutate({ suggestion_email: (emailInput ?? "").trim() || null });
  };

  return (
    <div className="space-y-4">
      <DashboardCard
        title={t("admin.generalSettings.title")}
        subtitle={t("admin.generalSettings.subtitle")}
      >
        <form className="space-y-4 text-sm text-white" onSubmit={handleSubmit}>
          <div>
            <label className="text-xs uppercase tracking-wide text-white/50">
              {t("admin.generalSettings.emailLabel")}
            </label>
            <input
              type="email"
              value={emailInput ?? settingsQuery.data?.suggestion_email ?? ""}
              onChange={(e) => setEmailInput(e.target.value)}
              placeholder="support@example.com"
              className="mt-1 w-full rounded-2xl border border-white/10 bg-transparent px-4 py-2 text-sm text-white placeholder:text-white/40 focus:border-white/60 focus:outline-none"
            />
            <p className="mt-1 text-xs text-white/50">
              {t("admin.generalSettings.emailHelper")}
            </p>
          </div>
          {updateMutation.isError && (
            <p className="text-sm text-red-400">
              {extractErrorMessage(updateMutation.error, t("admin.generalSettings.error"))}
            </p>
          )}
          {localMessage && <p className="text-sm text-emerald-300">{localMessage}</p>}
          <button
            type="submit"
                disabled={updateMutation.isPending}
            className="btn-cta w-full justify-center sm:w-auto"
          >
                {updateMutation.isPending
              ? t("admin.generalSettings.saving")
              : t("admin.generalSettings.save")}
          </button>
        </form>
      </DashboardCard>
    </div>
  );
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

type HighlightModalState = {
  questionId: number;
  source?: FigureSource;
  loading: boolean;
  page?: number;
};

function parseDecorationsFromMetadata(
  metadata: Record<string, unknown> | null | undefined
): StepDirective[] {
  if (!metadata || typeof metadata !== "object") {
    return [];
  }
  return getQuestionDecorations({ metadata } as { metadata: Record<string, unknown> });
}

function sanitizeDecorationsForMetadata(next: StepDirective[]): Array<Record<string, unknown>> {
  return next.map((entry) => {
    const payload: Record<string, unknown> = {
      target: "passage",
      text: entry.text,
    };
    payload.action = "underline";
    return payload;
  });
}

