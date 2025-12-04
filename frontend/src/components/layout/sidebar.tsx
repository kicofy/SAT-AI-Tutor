import { Home, LineChart, Sparkles, Layers, Upload } from "lucide-react";
import Link from "next/link";
import { env } from "@/lib/env";
import styles from "./sidebar.module.css";
import { useI18n } from "@/hooks/use-i18n";

const navItems = [
  { key: "nav.dashboard" as const, href: "/", icon: Home },
  { key: "nav.practice" as const, href: "/practice", icon: Sparkles },
  { key: "nav.ai" as const, href: "/ai/explain", icon: Layers },
  { key: "nav.analytics" as const, href: "/analytics", icon: LineChart },
  { key: "nav.import" as const, href: "/admin/imports", icon: Upload },
];

export function Sidebar() {
  const { t } = useI18n();
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
    </aside>
  );
}

