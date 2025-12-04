"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { extractErrorMessage } from "@/lib/errors";
import { useI18n } from "@/hooks/use-i18n";

export default function LoginPage() {
  const router = useRouter();
  const { login, loading, error } = useAuth();
  const { t } = useI18n();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitError(null);
    try {
      await login(identifier, password);
      router.push("/");
    } catch (err: unknown) {
      setSubmitError(extractErrorMessage(err, "登录失败"));
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="auth-title">{t("auth.login.title")}</p>
        <p className="auth-subtitle">{t("auth.login.subtitle")}</p>
      </div>

      <form className="auth-form" onSubmit={handleSubmit}>
        <input
          className="auth-input"
          placeholder={t("auth.login.identifier")}
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
          required
        />
        <input
          className="auth-input"
          type="password"
          placeholder={t("auth.login.password")}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {(submitError || error) && (
          <p className="text-sm text-red-400">
            {submitError || error || t("auth.login.error")}
          </p>
        )}
        <button className="auth-button" disabled={loading}>
          {loading ? t("auth.login.loading") : t("auth.login.submit")}
        </button>
      </form>

      <p className="auth-footer">
        {t("auth.login.switch")}{" "}
        <Link className="auth-link" href="/auth/register">
          {t("auth.register.submit")}
        </Link>
      </p>
    </div>
  );
}

