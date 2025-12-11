"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/app-shell";
import { DashboardCard } from "@/components/ui/dashboard-card";
import { submitSuggestion } from "@/services/support";
import { extractErrorMessage } from "@/lib/errors";
import { useI18n } from "@/hooks/use-i18n";

export function SuggestionPageView() {
  const { t } = useI18n();
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [contact, setContact] = useState("");
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [showSuccess, setShowSuccess] = useState(false);

  const suggestionMutation = useMutation({
    mutationFn: () => submitSuggestion({ title, content, contact: contact || undefined }),
    onSuccess: () => {
      setSuccessMessage(t("suggestions.success"));
      setTitle("");
      setContent("");
      setContact("");
      setShowSuccess(true);
    },
  });

  const error =
    suggestionMutation.isError && suggestionMutation.error
      ? extractErrorMessage(suggestionMutation.error, t("suggestions.error"))
      : null;

  const isDisabled = suggestionMutation.isPending || !title.trim() || !content.trim();

  if (showSuccess) {
    return (
      <AppShell>
        <div className="col-span-full mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-16 text-white">
          <DashboardCard
            title={t("suggestions.successTitle")}
            subtitle={t("suggestions.successSubtitle")}
          >
            <p className="text-sm text-white/70">{successMessage}</p>
            <div className="mt-6 flex flex-wrap gap-3">
              <button
                type="button"
                className="btn-cta"
                onClick={() => {
                  setShowSuccess(false);
                  setSuccessMessage(null);
                }}
              >
                {t("suggestions.button.new")}
              </button>
              <a href="/" className="btn-ghost">
                {t("suggestions.button.backHome")}
              </a>
            </div>
          </DashboardCard>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="col-span-full mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-8 text-white">
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-white/50">
            {t("suggestions.breadcrumb")}
          </p>
          <h1 className="mt-1 text-3xl font-semibold">{t("suggestions.title")}</h1>
          <p className="text-sm text-white/60">{t("suggestions.subtitle")}</p>
        </div>
        <DashboardCard
          title={t("suggestions.form.title")}
          subtitle={t("suggestions.form.subtitle")}
        >
          <form
            className="space-y-4 text-white"
            onSubmit={(e) => {
              e.preventDefault();
              setSuccessMessage(null);
              suggestionMutation.mutate();
            }}
            aria-busy={suggestionMutation.isPending}
          >
            <div>
              <label className="text-xs uppercase tracking-wide text-white/50">
                {t("suggestions.field.title")}
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={120}
                className="mt-1 w-full rounded-2xl border border-white/10 bg-transparent px-4 py-2 text-sm text-white placeholder:text-white/40 focus:border-white/60 focus:outline-none"
                placeholder={t("suggestions.placeholder.title")}
                disabled={suggestionMutation.isPending}
                required
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-wide text-white/50">
                {t("suggestions.field.content")}
              </label>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                rows={6}
                maxLength={4000}
                className="mt-1 w-full rounded-2xl border border-white/10 bg-transparent px-4 py-2 text-sm text-white placeholder:text-white/40 focus:border-white/60 focus:outline-none"
                placeholder={t("suggestions.placeholder.content")}
                disabled={suggestionMutation.isPending}
                required
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-wide text-white/50">
                {t("suggestions.field.contact")}
              </label>
              <input
                type="text"
                value={contact}
                onChange={(e) => setContact(e.target.value)}
                maxLength={255}
                className="mt-1 w-full rounded-2xl border border-white/10 bg-transparent px-4 py-2 text-sm text-white placeholder:text-white/40 focus:border-white/60 focus:outline-none"
                placeholder={t("suggestions.placeholder.contact")}
                disabled={suggestionMutation.isPending}
              />
              <p className="mt-1 text-xs text-white/50">{t("suggestions.helper.contact")}</p>
            </div>
            {suggestionMutation.isPending && (
              <p className="text-xs text-white/60">{t("suggestions.status.submitting")}</p>
            )}
            {error && <p className="text-sm text-red-400">{error}</p>}
            <button
              type="submit"
              disabled={isDisabled}
              className="btn-cta mt-4 w-full justify-center disabled:opacity-50"
            >
              {suggestionMutation.isPending
                ? t("suggestions.button.submitting")
                : t("suggestions.button.submit")}
            </button>
          </form>
        </DashboardCard>
      </div>
    </AppShell>
  );
}

