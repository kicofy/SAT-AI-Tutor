import { PropsWithChildren } from "react";
import { Sidebar } from "./sidebar";
import { TopBar } from "./top-bar";
import styles from "./app-shell.module.css";

type AppShellProps = PropsWithChildren<{
  contentClassName?: string;
}>;

export function AppShell({ children, contentClassName }: AppShellProps) {
  const contentClass = contentClassName ?? styles.content;
  return (
    <div className={styles.screen}>
      <Sidebar />
      <main className={styles.main}>
        <TopBar />
        <section className={contentClass}>{children}</section>
      </main>
    </div>
  );
}

