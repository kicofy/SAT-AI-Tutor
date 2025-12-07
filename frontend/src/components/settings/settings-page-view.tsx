"use client";

import { FormEvent, MouseEvent, useEffect, useMemo, useState } from "react";
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
  const [langStatus, setLangStatus] = useState<StatusState>({ state: "idle" });
  const [passwordStatus, setPasswordStatus] = useState<StatusState>({ state: "idle" });
  const [emailSendStatus, setEmailSendStatus] = useState<StatusState>({ state: "idle" });
  const [emailVerifyStatus, setEmailVerifyStatus] = useState<StatusState>({ state: "idle" });
  const [newEmail, setNewEmail] = useState("");
  const [verificationCode, setVerificationCode] = useState("");
  const [hasSentCode, setHasSentCode] = useState(false);
  const [sendCooldown, setSendCooldown] = useState(0);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const languagePreference = useMemo(() => normalizeLanguage(user?.profile?.language_preference), [user]);

  useEffect(() => {
    if (!user) return;
    setLanguage(languagePreference);
    setNewEmail("");
    setVerificationCode("");
    setHasSentCode(false);
    setSendCooldown(0);
    setEmailSendStatus({ state: "idle" });
    setEmailVerifyStatus({ state: "idle" });
  }, [user, languagePreference]);

  useEffect(() => {
    if (sendCooldown <= 0) return;
    const timer = setTimeout(() => {
      setSendCooldown((prev) => Math.max(prev - 1, 0));
    }, 1000);
    return () => clearTimeout(timer);
  }, [sendCooldown]);

  const loadingFallback = (
    <div className="col-span-full mx-auto w-full max-w-4xl px-4 py-20 text-center text-white/60">
      {t("ai.loading")}
    </div>
  );

  if (!user) {
    return <AppShell>{loadingFallback}</AppShell>;
  }

  const isLangLoading = langStatus.state === "loading";
  const isSendLoading = emailSendStatus.state === "loading";
  const isVerifyLoading = emailVerifyStatus.state === "loading";
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

  async function handleEmailCodeRequest(event: FormEvent | MouseEvent<HTMLButtonElement>) {
    event.preventDefault();
    if (!newEmail?.trim()) {
      setEmailSendStatus({ state: "error", message: t("settings.error.generic") });
      return;
    }
    if (user?.email && newEmail.trim().toLowerCase() === user.email.toLowerCase()) {
      setEmailSendStatus({ state: "error", message: t("settings.email.sameAsCurrent") });
      return;
    }
    setEmailSendStatus({ state: "loading" });
    try {
      await AuthService.requestEmailChangeCode(newEmail.trim());
      setEmailSendStatus({ state: "success", message: t("settings.email.codeSent") });
      setHasSentCode(true);
      setSendCooldown(60);
    } catch (error) {
      setEmailSendStatus({
        state: "error",
        message: extractErrorMessage(error, t("settings.error.generic")),
      });
    }
  }

  async function handleEmailConfirm(event: FormEvent) {
    event.preventDefault();
    if (!hasSentCode) {
      setEmailVerifyStatus({ state: "error", message: t("settings.email.needCode") });
      return;
    }
    if (!verificationCode?.trim()) {
      setEmailVerifyStatus({ state: "error", message: t("settings.error.generic") });
      return;
    }
    setEmailVerifyStatus({ state: "loading" });
    try {
      const updated = await AuthService.confirmEmailChange({
        newEmail: newEmail.trim(),
        code: verificationCode.trim(),
      });
      updateUser(updated);
      setEmailVerifyStatus({ state: "success", message: t("settings.email.success") });
      setNewEmail("");
      setVerificationCode("");
      setHasSentCode(false);
      setSendCooldown(0);
      setEmailSendStatus({ state: "idle" });
    } catch (error) {
      setEmailVerifyStatus({
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
          <form className="space-y-6" onSubmit={handleEmailConfirm}>
            <label className="text-sm text-white/70">
              <span className="text-xs uppercase tracking-wide text-white/40">{t("settings.email.currentLabel")}</span>
              <input
                type="email"
                className="mt-2 w-full cursor-not-allowed rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-white/70"
                value={user.email ?? ""}
                disabled
              />
            </label>

            <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
              <label className="flex-1 text-sm text-white/70">
                <span className="text-xs uppercase tracking-wide text-white/40">{t("settings.email.newLabel")}</span>
                <input
                  type="email"
                  className="mt-2 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-white/90 placeholder:text-white/40"
                  value={newEmail}
                  onChange={(event) => setNewEmail(event.target.value)}
                  placeholder={t("settings.email.placeholder")}
                  required
                />
              </label>
              <button
                type="button"
                className="btn-cta px-4 py-3 text-sm sm:w-auto"
                onClick={handleEmailCodeRequest}
                disabled={isSendLoading || !newEmail || sendCooldown > 0}
              >
                {isSendLoading
                  ? t("settings.saving")
                  : sendCooldown > 0
                  ? t("settings.email.resendIn", { seconds: sendCooldown })
                  : t("settings.email.send")}
              </button>
            </div>
            <FormStatus status={emailSendStatus} />
            <p className="text-xs text-white/50">{t("settings.email.verificationHint")}</p>

            <label className="text-sm text-white/70">
              <span className="text-xs uppercase tracking-wide text-white/40">{t("settings.email.codeLabel")}</span>
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                className="mt-2 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-white/90 placeholder:text-white/40"
                value={verificationCode}
                onChange={(event) => setVerificationCode(event.target.value)}
                placeholder="000000"
                disabled={!hasSentCode}
              />
            </label>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                type="submit"
                className="btn-cta px-4 py-2 text-sm"
                disabled={!hasSentCode || isVerifyLoading}
              >
                {isVerifyLoading ? t("settings.saving") : t("settings.email.verify")}
              </button>
              <FormStatus status={emailVerifyStatus} />
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

