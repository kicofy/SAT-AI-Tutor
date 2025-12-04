import { PropsWithChildren } from "react";
import { Sidebar } from "./sidebar";
import { TopBar } from "./top-bar";
import styles from "./app-shell.module.css";

export function AppShell({ children }: PropsWithChildren) {
  return (
    <div className={styles.screen}>
      <Sidebar />
      <main className={styles.main}>
        <TopBar />
        <section className={styles.content}>{children}</section>
      </main>
    </div>
  );
}

