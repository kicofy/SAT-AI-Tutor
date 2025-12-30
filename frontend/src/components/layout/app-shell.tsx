import { PropsWithChildren } from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "./sidebar";
import { TopBar } from "./top-bar";
import styles from "./app-shell.module.css";

type AppShellProps = PropsWithChildren<{
  contentClassName?: string;
}>;

export function AppShell({ children, contentClassName }: AppShellProps) {
  const pathname = usePathname();
  const contentClass = contentClassName ?? styles.content;
  return (
    <div className={styles.screen}>
      <Sidebar />
      <main className={styles.main}>
        <TopBar />
        <section key={pathname} className={`${contentClass} ${styles.fade}`}>
          {children}
        </section>
      </main>
    </div>
  );
}

