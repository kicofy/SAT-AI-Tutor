import { useContext } from "react";
import { LocaleContext } from "@/components/providers/locale-provider";

export function useI18n() {
  const ctx = useContext(LocaleContext);
  if (!ctx) {
    throw new Error("useI18n must be used within LocaleProvider");
  }
  return ctx;
}

