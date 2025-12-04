"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { extractErrorMessage } from "@/lib/errors";
import { useI18n } from "@/hooks/use-i18n";

export default function RegisterPage() {
  const router = useRouter();
  const { register, loading, error } = useAuth();
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [languagePreference, setLanguagePreference] = useState<"en" | "zh">("en");

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitError(null);
    try {
      await register(email, username, password, languagePreference);
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

      <form className="auth-form" onSubmit={handleSubmit}>
        <input
          className="auth-input"
          placeholder={t("auth.register.email")}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
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

