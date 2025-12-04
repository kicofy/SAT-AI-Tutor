import { Locale } from "./messages";

export const LOCALE_STORAGE_KEY = "sat-locale";
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
  window.dispatchEvent(new CustomEvent(LOCALE_EVENT, { detail: locale }));
}

