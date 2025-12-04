import type { Metadata } from "next";
import "./auth.css";

export const metadata: Metadata = {
  title: "登录 - SAT AI Tutor",
};

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="auth-screen">
      <div className="auth-card">{children}</div>
    </div>
  );
}

