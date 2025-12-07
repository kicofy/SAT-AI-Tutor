"use client";

import { createContext, PropsWithChildren, useEffect, useState } from "react";
import { Locale, TranslationKey, translations } from "@/i18n/messages";
import {
  getStoredLocale,
  LOCALE_EVENT,
  persistLocale,
} from "@/i18n/locale-storage";

type Values = Record<string, string | number>;

type LocaleContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  toggleLocale: () => void;
  t: (key: TranslationKey, values?: Values) => string;
};

export const LocaleContext = createContext<LocaleContextValue>({
  locale: "en",
  setLocale: () => undefined,
  toggleLocale: () => undefined,
  t: (key) => translations.en[key],
});

function formatMessage(template: string, values?: Values) {
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (_, token) =>
    values[token] !== undefined ? String(values[token]) : ""
  );
}

type LocaleProviderProps = PropsWithChildren<{
  initialLocale?: Locale;
}>;

export function LocaleProvider({ children, initialLocale = "en" }: LocaleProviderProps) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  useEffect(() => {
    if (typeof window !== "undefined") {
      setLocaleState(getStoredLocale());
    }

    const handler = (event: Event) => {
      const detail = (event as CustomEvent<Locale>).detail;
      if (detail === "en" || detail === "zh") {
        setLocaleState(detail);
      }
    };

    window.addEventListener(LOCALE_EVENT, handler as EventListener);
    return () => window.removeEventListener(LOCALE_EVENT, handler as EventListener);
  }, []);

  const setLocale = (next: Locale) => {
    persistLocale(next);
    setLocaleState(next);
  };

  const toggleLocale = () => {
    setLocale(nextLocale(locale));
  };

  const value: LocaleContextValue = {
    locale,
    setLocale,
    toggleLocale,
    t: (key, values) => formatMessage(translations[locale][key], values),
  };

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

function nextLocale(current: Locale): Locale {
  return current === "en" ? "zh" : "en";
}

