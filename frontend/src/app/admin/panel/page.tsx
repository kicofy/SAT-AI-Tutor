"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AdminPanelView } from "@/components/admin/admin-panel-view";
import { useAuth } from "@/hooks/use-auth";
import { AppShell } from "@/components/layout/app-shell";

export default function AdminPanelPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && user && user.role !== "admin") {
      router.replace("/");
    }
  }, [user, loading, router]);

  if (!user || user.role !== "admin") {
    return (
      <AppShell>
        <div className="p-10 text-white/70">Checking administrator permissions...</div>
      </AppShell>
    );
  }

  return <AdminPanelView />;
}

