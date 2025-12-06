import { Home, LineChart, Sparkles, Layers, Settings, Shield } from "lucide-react";
import Link from "next/link";
import { env } from "@/lib/env";
import styles from "./sidebar.module.css";
import { useI18n } from "@/hooks/use-i18n";
import { useAuthStore } from "@/stores/auth-store";

const navItems = [
  { key: "nav.dashboard" as const, href: "/", icon: Home },
  { key: "nav.practice" as const, href: "/practice", icon: Sparkles },
  { key: "nav.ai" as const, href: "/ai/explain", icon: Layers },
  { key: "nav.analytics" as const, href: "/analytics", icon: LineChart },
];

const settingsNav = { key: "nav.settings" as const, href: "/settings", icon: Settings };
const adminNav = { key: "nav.admin" as const, href: "/admin/panel", icon: Shield };

export function Sidebar() {
  const { t } = useI18n();
  const isAdmin = useAuthStore((state) => state.user?.role === "admin");
  return (
    <aside className={styles.wrapper}>
      <div className={styles.brand}>
        <div className={styles.logo}>AI</div>
        <div>
          <p className={styles.brandTitle}>{env.appName}</p>
          <p className={styles.brandTagline}>{t("sidebar.tagline")}</p>
        </div>
      </div>
      <nav className={styles.nav}>
        {navItems.map((item) => (
          <Link key={item.href} href={item.href} className={styles.navItem}>
            <item.icon size={18} />
            <span>{t(item.key)}</span>
          </Link>
        ))}
      </nav>
      <div className={styles.footerNav}>
        <Link href={settingsNav.href} className={styles.navItem}>
          <settingsNav.icon size={18} />
          <span>{t(settingsNav.key)}</span>
        </Link>
        {isAdmin ? (
          <Link href={adminNav.href} className={styles.navItem}>
            <adminNav.icon size={18} />
            <span>{t("nav.admin")}</span>
          </Link>
        ) : null}
      </div>
    </aside>
  );
}

