import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { env } from "@/lib/env";
import { QueryProvider } from "@/components/providers/query-provider";
import { LocaleProvider } from "@/components/providers/locale-provider";
import { CSSTransitionWrapper } from "@/components/ui/css-transition-wrapper";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: env.appName,
  description: "SAT AI Tutor – Edu + AI + Gamification Dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-[#020813]`}
      >
        <QueryProvider>
          <LocaleProvider>
            <CSSTransitionWrapper>{children}</CSSTransitionWrapper>
          </LocaleProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
