"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import * as AuthService from "@/services/auth";
import { extractErrorMessage } from "@/lib/errors";
import { useI18n } from "@/hooks/use-i18n";

export default function ResetPasswordPage() {
  const { t } = useI18n();
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams?.get("token") ?? "";
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      setStatus("error");
      setMessage(t("auth.reset.tokenMissing"));
      return;
    }
    if (!newPassword || newPassword !== confirmPassword) {
      setStatus("error");
      setMessage(t("auth.reset.mismatch"));
      return;
    }
    setStatus("loading");
    setMessage(null);
    try {
      await AuthService.confirmPasswordReset({ token, newPassword });
      setStatus("success");
      setMessage(t("auth.reset.success"));
      setTimeout(() => router.push("/auth/login"), 1500);
    } catch (error) {
      setStatus("error");
      setMessage(extractErrorMessage(error, t("auth.reset.error")));
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="auth-title">{t("auth.reset.title")}</p>
        <p className="auth-subtitle">{t("auth.reset.subtitle")}</p>
      </div>

      <form className="auth-form" onSubmit={handleSubmit}>
        <input
          className="auth-input"
          type="password"
          placeholder={t("auth.reset.newPassword")}
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          required
        />
        <input
          className="auth-input"
          type="password"
          placeholder={t("auth.reset.confirmPassword")}
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          required
        />
        {message && (
          <p className={`text-sm ${status === "success" ? "text-emerald-300" : "text-rose-300"}`}>{message}</p>
        )}
        <button className="auth-button" disabled={status === "loading"}>
          {status === "loading" ? t("auth.reset.loading") : t("auth.reset.submit")}
        </button>
      </form>

      <p className="auth-footer">
        <Link className="auth-link" href="/auth/login">
          {t("auth.reset.backToLogin")}
        </Link>
      </p>
    </div>
  );
}

