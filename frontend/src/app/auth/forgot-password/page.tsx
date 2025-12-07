"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import * as AuthService from "@/services/auth";
import { extractErrorMessage } from "@/lib/errors";
import { useI18n } from "@/hooks/use-i18n";

export default function ForgotPasswordPage() {
  const { t } = useI18n();
  const [identifier, setIdentifier] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("loading");
    setMessage(null);
    try {
      await AuthService.requestPasswordReset(identifier.trim());
      setStatus("success");
      setMessage(t("auth.forgot.success"));
    } catch (error) {
      setStatus("error");
      setMessage(extractErrorMessage(error, t("auth.forgot.error")));
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="auth-title">{t("auth.forgot.title")}</p>
        <p className="auth-subtitle">{t("auth.forgot.subtitle")}</p>
      </div>

      <form className="auth-form" onSubmit={handleSubmit}>
        <input
          className="auth-input"
          placeholder={t("auth.forgot.placeholder")}
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
          required
        />
        {message && (
          <p className={`text-sm ${status === "success" ? "text-emerald-300" : "text-rose-300"}`}>{message}</p>
        )}
        <button className="auth-button" disabled={status === "loading"}>
          {status === "loading" ? t("auth.forgot.loading") : t("auth.forgot.submit")}
        </button>
      </form>

      <p className="auth-footer">
        {t("auth.forgot.back")}{" "}
        <Link className="auth-link" href="/auth/login">
          {t("auth.login.submit")}
        </Link>
      </p>
    </div>
  );
}

