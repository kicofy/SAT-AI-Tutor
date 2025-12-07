import { Locale } from "./messages";

export const LOCALE_STORAGE_KEY = "sat-locale";
export const LOCALE_COOKIE_KEY = "sat_locale";
export const LOCALE_EVENT = "sat:locale-changed";

export function getStoredLocale(): Locale {
  if (typeof window === "undefined") {
    return "en";
  }
  const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY) as Locale | null;
  if (stored === "en" || stored === "zh") {
    return stored;
  }
  return "en";
}

export function persistLocale(locale: Locale) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  if (typeof document !== "undefined") {
    const maxAge = 60 * 60 * 24 * 365;
    document.cookie = `${LOCALE_COOKIE_KEY}=${locale};path=/;max-age=${maxAge};samesite=lax`;
  }
  window.dispatchEvent(new CustomEvent(LOCALE_EVENT, { detail: locale }));
}

