"use client";

import { useMemo, useState } from "react";
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
} from "@/services/admin";
import { AdminQuestion, AdminSource, AdminUser } from "@/types/admin";
import { extractErrorMessage } from "@/lib/errors";

const PAGE_SIZE = 20;

type TabKey = "users" | "questions" | "collections" | "import";

export function AdminPanelView() {
  const [activeTab, setActiveTab] = useState<TabKey>("users");
  const tabs: { key: TabKey; label: string; description: string }[] = [
    { key: "users", label: "Users", description: "Manage accounts and roles" },
    { key: "questions", label: "Question Bank", description: "Edit and review questions" },
    { key: "collections", label: "PDF Collections", description: "Review uploaded sets" },
    { key: "import", label: "Upload & Import", description: "Process new question sets" },
  ];

  return (
    <AppShell>
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-8 text-white">
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
        {activeTab === "questions" && <QuestionTab />}
        {activeTab === "collections" && <CollectionsTab />}
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

  return (
    <div className="space-y-4">
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

      {selectedUser ? (
        <DashboardCard title="User detail" subtitle="Edit account information.">
          <UserDetailCard
            user={selectedUser}
            onSubmit={(payload) =>
              updateUserMutation.mutate({ userId: selectedUser.id, data: payload })
            }
            isSaving={updateUserMutation.isLoading}
            error={updateUserMutation.error}
          />
        </DashboardCard>
      ) : (
        <p className="text-sm text-white/50">Select a user to view details.</p>
      )}
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
  const [role, setRole] = useState(user.role);
  const [language, setLanguage] = useState(
    user.profile?.language_preference?.toLowerCase().includes("zh") ? "zh" : "en"
  );
  const [password, setPassword] = useState("");

  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          email,
          username,
          role,
          language_preference: language,
          reset_password: password || undefined,
        });
        setPassword("");
      }}
    >
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

function QuestionTab() {
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

  return (
    <div className="space-y-4">
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
        <p className="text-sm text-white/50">Select a question to edit it.</p>
      )}
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
  const [correctAnswer, setCorrectAnswer] = useState(
    question.correct_answer?.value ?? ""
  );
  const [choices, setChoices] = useState<Record<string, string>>(question.choices || {});

  const choiceKeys = useMemo(() => {
    const keys = Object.keys(choices);
    return keys.length ? keys : ["A", "B", "C", "D"];
  }, [choices]);

  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          stem_text: stemText,
          section,
          sub_section: subSection || null,
          difficulty_level: difficulty === "" ? null : Number(difficulty),
          correct_answer: { value: correctAnswer },
          choices,
        });
      }}
    >
      <label className="text-sm text-white/70 block">
        Question text
        <textarea
          className="mt-1 w-full rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-sm text-white"
          rows={4}
          value={stemText}
          onChange={(e) => setStemText(e.target.value)}
        />
      </label>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="text-sm text-white/70">
          Section
          <select
            className="mt-1 w-full rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-white"
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
            className="mt-1 w-full rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-white"
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
            className="mt-1 w-full rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-white"
            value={difficulty}
            onChange={(e) => setDifficulty(e.target.value ? Number(e.target.value) : "")}
          />
        </label>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {choiceKeys.map((key) => (
          <label key={key} className="text-sm text-white/70">
            Choice {key}
            <input
              className="mt-1 w-full rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-white"
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
          className="mt-1 w-full rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-white"
          value={correctAnswer}
          onChange={(e) => setCorrectAnswer(e.target.value)}
        />
      </label>
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
  );
}

function CollectionsTab() {
  const [page, setPage] = useState(1);
  const [selectedSourceId, setSelectedSourceId] = useState<number | null>(null);

  const sourcesQuery = useQuery({
    queryKey: ["admin-sources", page],
    queryFn: () =>
      getAdminSources({
        page,
        per_page: PAGE_SIZE,
      }),
  });

  const sourceDetailQuery = useQuery({
    queryKey: ["admin-source-detail", selectedSourceId],
    queryFn: () =>
      selectedSourceId
        ? getAdminSourceDetail(selectedSourceId, { page: 1, per_page: 10 })
        : Promise.resolve(null),
    enabled: Boolean(selectedSourceId),
  });

  return (
    <div className="space-y-4">
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

      {sourceDetailQuery.data ? (
        <DashboardCard
          title="Collection detail"
          subtitle={sourceDetailQuery.data.source.original_name || sourceDetailQuery.data.source.filename}
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
                  <tr key={question.id} className="border-t border-white/5">
                    <td className="px-4 py-3 text-white">
                      {question.question_uid || `#${question.id}`}
                    </td>
                    <td className="px-4 py-3 text-white/80">{question.section}</td>
                    <td className="px-4 py-3 text-white/80">{question.difficulty_level ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </DashboardCard>
      ) : (
        <p className="text-sm text-white/50">Select a collection to preview its questions.</p>
      )}
    </div>
  );
}

function ImportTab() {
  return (
    <DashboardCard
      title="Upload & Import"
      subtitle="Use the importer to parse PDF sets, monitor progress, and review drafts."
    >
      <p className="text-sm text-white/70">
        The importer handles PDF uploads, AI parsing, draft review (including figure cropping), and
        publishing into the question bank. Open the dedicated importer workspace to manage jobs in
        detail.
      </p>
      <div className="mt-4 flex flex-wrap gap-3">
        <Link
          href="/admin/temp-import"
          className="rounded-xl bg-white px-4 py-2 text-sm font-semibold text-[#050E1F]"
        >
          Open importer workspace
        </Link>
        <Link
          href="/admin/temp-import"
          className="rounded-xl border border-white/30 px-4 py-2 text-sm font-semibold text-white/80"
        >
          View OpenAI logs
        </Link>
      </div>
    </DashboardCard>
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

