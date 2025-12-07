import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { env } from "@/lib/env";
import { QueryProvider } from "@/components/providers/query-provider";
import { LocaleProvider } from "@/components/providers/locale-provider";
import { CSSTransitionWrapper } from "@/components/ui/css-transition-wrapper";
import { cookies } from "next/headers";
import { LOCALE_COOKIE_KEY } from "@/i18n/locale-storage";
import { Locale } from "@/i18n/messages";

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

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const cookieStore = await cookies();
  const localeFromCookie = cookieStore.get(LOCALE_COOKIE_KEY)?.value;
  const initialLocale: Locale = localeFromCookie === "zh" ? "zh" : "en";

  return (
    <html lang={initialLocale}>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-[#020813]`}
      >
        <QueryProvider>
          <LocaleProvider initialLocale={initialLocale}>
            <CSSTransitionWrapper>{children}</CSSTransitionWrapper>
          </LocaleProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
