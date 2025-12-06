"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { extractErrorMessage } from "@/lib/errors";
import { useI18n } from "@/hooks/use-i18n";
import { requestRegistrationCode } from "@/services/auth";

export default function RegisterPage() {
  const router = useRouter();
  const { register, loading, error } = useAuth();
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [codeStatus, setCodeStatus] = useState<string | null>(null);
  const [codeError, setCodeError] = useState<string | null>(null);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [sendingCode, setSendingCode] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [languagePreference, setLanguagePreference] = useState<"en" | "zh">("en");

  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = setInterval(() => {
      setResendCooldown((prev) => Math.max(prev - 1, 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [resendCooldown]);

  async function handleSendCode() {
    if (!email) {
      setCodeError(t("auth.register.codeEmailRequired"));
      return;
    }
    setCodeError(null);
    setCodeStatus(null);
    setSendingCode(true);
    try {
      await requestRegistrationCode({ email, languagePreference });
      setCodeStatus(t("auth.register.codeSent", { email }));
      setResendCooldown(60);
    } catch (err: unknown) {
      setCodeError(extractErrorMessage(err, t("auth.register.codeSendError")));
    } finally {
      setSendingCode(false);
    }
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitError(null);
    if (code.trim().length !== 6) {
      setSubmitError(t("auth.register.codeInvalid"));
      return;
    }
    try {
      await register(email, username, password, code.trim(), languagePreference);
      router.push("/");
    } catch (err: unknown) {
      setSubmitError(extractErrorMessage(err, "注册失败"));
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="auth-title">{t("auth.register.title")}</p>
        <p className="auth-subtitle">{t("auth.register.subtitle")}</p>
      </div>

      <form className="auth-form space-y-4" onSubmit={handleSubmit}>
        <input
          className="auth-input"
          placeholder={t("auth.register.email")}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <div className="space-y-2">
          <label className="text-xs text-white/50 uppercase tracking-[0.3em]">
            {t("auth.register.codeLabel")}
          </label>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
            <input
              className="auth-input flex-1 text-center text-2xl tracking-[0.35em] caret-white"
              placeholder="••••••"
              inputMode="numeric"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/[^\d]/g, "").slice(0, 6))}
            />
            <button
              type="button"
              className="w-full rounded-xl border border-white/20 bg-white/90 px-5 py-3 text-sm font-semibold text-[#050E1F] transition hover:bg-white focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto sm:flex-shrink-0"
              onClick={handleSendCode}
              disabled={sendingCode || loading || resendCooldown > 0}
            >
              {sendingCode
                ? t("auth.register.codeSending")
                : resendCooldown > 0
                ? t("auth.register.resendCountdown", { seconds: resendCooldown })
                : t("auth.register.sendCode")}
            </button>
          </div>
          {codeStatus && <p className="text-xs text-emerald-300">{codeStatus}</p>}
          {codeError && <p className="text-xs text-red-400">{codeError}</p>}
        </div>
        <div>
          <label className="text-xs text-white/50 mb-2 block">
            {t("auth.register.languageLabel")}
          </label>
          <select
            className="auth-input bg-[#050E1F]"
            value={languagePreference}
            onChange={(e) => setLanguagePreference(e.target.value as "en" | "zh")}
          >
            <option value="en">English</option>
            <option value="zh">简体中文</option>
          </select>
        </div>
        <input
          className="auth-input"
          placeholder={t("auth.register.username")}
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
        <input
          className="auth-input"
          type="password"
          placeholder={t("auth.register.password")}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {(submitError || error) && (
          <p className="text-sm text-red-400">
            {submitError || error || t("auth.register.error")}
          </p>
        )}
        <button className="auth-button" disabled={loading}>
          {loading ? t("auth.register.loading") : t("auth.register.submit")}
        </button>
      </form>

      <p className="auth-footer">
        {t("auth.register.switch")}{" "}
        <Link className="auth-link" href="/auth/login">
          {t("auth.login.submit")}
        </Link>
      </p>
    </div>
  );
}

