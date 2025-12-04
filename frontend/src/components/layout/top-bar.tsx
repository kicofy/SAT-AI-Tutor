"use client";

import styles from "./top-bar.module.css";
import { useAuth } from "@/hooks/use-auth";
import { useRouter } from "next/navigation";
import { useI18n } from "@/hooks/use-i18n";

export function TopBar() {
  const { logout } = useAuth();
  const router = useRouter();
  const { t, locale } = useI18n();

  const formatter = new Intl.DateTimeFormat(
    locale === "zh" ? "zh-CN" : "en-US",
    {
      month: "long",
      day: "numeric",
      weekday: "long",
    }
  );
  const dateLabel = formatter.format(new Date());

  function handleLogout() {
    logout();
    router.push("/auth/login");
  }

  return (
    <header className={styles.wrapper}>
      <div>
        <p className={styles.title}>{t("topbar.title")}</p>
        <p className={styles.subtitle}>{dateLabel}</p>
      </div>
      <button className={styles.logout} onClick={handleLogout}>
        {t("common.logout")}
      </button>
    </header>
  );
}

