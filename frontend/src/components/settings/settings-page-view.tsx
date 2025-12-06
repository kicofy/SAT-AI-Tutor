"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useI18n } from "@/hooks/use-i18n";
import { useAuthStore } from "@/stores/auth-store";
import * as AuthService from "@/services/auth";
import { extractErrorMessage } from "@/lib/errors";
import { AppShell } from "@/components/layout/app-shell";

type StatusState = {
  state: "idle" | "loading" | "success" | "error";
  message?: string;
};

const languageOptions: Array<{ value: "en" | "zh" | "bilingual"; labelKey: string }> = [
  { value: "en", labelKey: "settings.language.option.en" },
  { value: "zh", labelKey: "settings.language.option.zh" },
  { value: "bilingual", labelKey: "settings.language.option.bilingual" },
];

export function SettingsPageView() {
  const { t } = useI18n();
  const user = useAuthStore((state) => state.user);
  const updateUser = useAuthStore((state) => state.updateUser);

  const [language, setLanguage] = useState<"en" | "zh" | "bilingual">("en");
  const [email, setEmail] = useState("");
  const [langStatus, setLangStatus] = useState<StatusState>({ state: "idle" });
  const [emailStatus, setEmailStatus] = useState<StatusState>({ state: "idle" });
  const [passwordStatus, setPasswordStatus] = useState<StatusState>({ state: "idle" });
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const languagePreference = useMemo(() => normalizeLanguage(user?.profile?.language_preference), [user]);

  useEffect(() => {
    if (!user) return;
    setEmail(user.email ?? "");
    setLanguage(languagePreference);
  }, [user, languagePreference]);

  const loadingFallback = (
    <div className="col-span-full mx-auto w-full max-w-4xl px-4 py-20 text-center text-white/60">
      {t("ai.loading")}
    </div>
  );

  if (!user) {
    return <AppShell>{loadingFallback}</AppShell>;
  }

  const isLangLoading = langStatus.state === "loading";
  const isEmailLoading = emailStatus.state === "loading";
  const isPasswordLoading = passwordStatus.state === "loading";

  async function handleLanguageSave(event: FormEvent) {
    event.preventDefault();
    setLangStatus({ state: "loading" });
    try {
      const updated = await AuthService.updateProfileSettings({ languagePreference: language });
      updateUser(updated);
      setLangStatus({ state: "success", message: t("settings.language.success") });
    } catch (error) {
      setLangStatus({
        state: "error",
        message: extractErrorMessage(error, t("settings.error.generic")),
      });
    }
  }

  async function handleEmailSave(event: FormEvent) {
    event.preventDefault();
    if (!email?.trim()) {
      setEmailStatus({ state: "error", message: t("settings.error.generic") });
      return;
    }
    setEmailStatus({ state: "loading" });
    try {
      const updated = await AuthService.updateProfileSettings({ email: email.trim() });
      updateUser(updated);
      setEmailStatus({ state: "success", message: t("settings.email.success") });
    } catch (error) {
      setEmailStatus({
        state: "error",
        message: extractErrorMessage(error, t("settings.error.generic")),
      });
    }
  }

  async function handlePasswordSave(event: FormEvent) {
    event.preventDefault();
    if (!newPassword || newPassword !== confirmPassword) {
      setPasswordStatus({ state: "error", message: t("settings.password.mismatch") });
      return;
    }
    setPasswordStatus({ state: "loading" });
    try {
      await AuthService.changePassword({
        currentPassword,
        newPassword,
      });
      setPasswordStatus({ state: "success", message: t("settings.password.success") });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (error) {
      setPasswordStatus({
        state: "error",
        message: extractErrorMessage(error, t("settings.error.generic")),
      });
    }
  }

  return (
    <AppShell>
      <div className="col-span-full mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-8 text-white">
        <div className="flex flex-col gap-3">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-sm font-semibold text-white/80 transition hover:text-white w-fit"
          >
            <span aria-hidden="true">←</span>
            {t("aiExplain.cta.home")}
          </Link>
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-white/40">{t("nav.settings")}</p>
            <h1 className="mt-2 text-3xl font-semibold text-white">{t("settings.page.title")}</h1>
            <p className="text-sm text-white/60">{t("settings.page.subtitle")}</p>
          </div>
        </div>

        <section className="card-ambient space-y-5 rounded-3xl border border-white/10 bg-[#0b1424] p-6">
          <SectionHeader title={t("settings.language.title")} description={t("settings.language.description")} />
          <form className="space-y-5" onSubmit={handleLanguageSave}>
            <div className="grid gap-3 sm:grid-cols-3">
              {languageOptions.map((option) => (
                <label
                  key={option.value}
                  className={`card-ambient flex cursor-pointer flex-col gap-2 rounded-2xl border px-4 py-3 text-sm transition ${
                    language === option.value
                      ? "border-white/60 bg-white/10 text-white"
                      : "border-white/10 bg-white/5 text-white/70 hover:border-white/30"
                  }`}
                >
                  <input
                    type="radio"
                    name="language"
                    value={option.value}
                    checked={language === option.value}
                    onChange={() => setLanguage(option.value)}
                    className="sr-only"
                  />
                  <span className="font-semibold">{t(option.labelKey)}</span>
                </label>
              ))}
            </div>
            <div className="flex items-center gap-3">
              <button
                type="submit"
                className="btn-cta px-4 py-2 text-sm"
                disabled={isLangLoading}
              >
                {isLangLoading ? t("settings.saving") : t("settings.language.save")}
              </button>
              <FormStatus status={langStatus} />
            </div>
          </form>
        </section>

        <section className="card-ambient space-y-5 rounded-3xl border border-white/10 bg-[#0b1424] p-6">
          <SectionHeader title={t("settings.email.title")} description={t("settings.email.description")} />
        <form className="space-y-6" onSubmit={handleEmailSave}>
            <label className="text-sm text-white/70">
              <span className="text-xs uppercase tracking-wide text-white/40">{t("settings.email.label")}</span>
              <input
                type="email"
                className="mt-2 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-white/90 placeholder:text-white/40"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder={t("settings.email.placeholder")}
                required
              />
            </label>
          <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                type="submit"
                className="btn-cta px-4 py-2 text-sm"
                disabled={isEmailLoading}
              >
                {isEmailLoading ? t("settings.saving") : t("settings.email.save")}
              </button>
              <FormStatus status={emailStatus} />
            </div>
          </form>
        </section>

        <section className="card-ambient space-y-5 rounded-3xl border border-white/10 bg-[#0b1424] p-6">
          <SectionHeader title={t("settings.password.title")} description={t("settings.password.description")} />
          <form className="space-y-4" onSubmit={handlePasswordSave}>
            <PasswordField
              label={t("settings.password.current")}
              value={currentPassword}
              onChange={setCurrentPassword}
            />
            <PasswordField
              label={t("settings.password.new")}
              value={newPassword}
              onChange={setNewPassword}
            />
            <PasswordField
              label={t("settings.password.confirm")}
              value={confirmPassword}
              onChange={setConfirmPassword}
            />
          <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                type="submit"
                className="btn-cta px-4 py-2 text-sm"
                disabled={isPasswordLoading}
              >
                {isPasswordLoading ? t("settings.saving") : t("settings.password.save")}
              </button>
              <FormStatus status={passwordStatus} />
            </div>
          </form>
        </section>
      </div>
    </AppShell>
  );
}

function SectionHeader({ title, description }: { title: string; description: string }) {
  return (
    <div>
      <h2 className="text-xl font-semibold text-white">{title}</h2>
      <p className="mt-1 text-sm text-white/60">{description}</p>
    </div>
  );
}

function PasswordField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="text-sm text-white/70">
      <span className="text-xs uppercase tracking-wide text-white/40">{label}</span>
      <input
        type="password"
        className="mt-2 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-white/90 placeholder:text-white/40"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required
      />
    </label>
  );
}

function FormStatus({ status }: { status: StatusState }) {
  if (status.state === "idle" || !status.message) {
    return null;
  }
  if (status.state === "success") {
    return <p className="text-sm text-emerald-300">{status.message}</p>;
  }
  if (status.state === "error") {
    return <p className="text-sm text-rose-300">{status.message}</p>;
  }
  return null;
}

function normalizeLanguage(value?: string | null): "en" | "zh" | "bilingual" {
  const normalized = value?.toLowerCase();
  if (!normalized) return "en";
  if (normalized.includes("zh")) return "zh";
  if (normalized.includes("bilingual")) return "bilingual";
  return "en";
}

