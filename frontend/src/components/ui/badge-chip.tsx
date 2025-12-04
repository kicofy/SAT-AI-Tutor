import clsx from "clsx";
import { PropsWithChildren } from "react";

type BadgeChipProps = PropsWithChildren<{
  variant?: "default" | "success" | "warning";
}>;

export function BadgeChip({ children, variant = "default" }: BadgeChipProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-medium",
        {
          "border-white/20 bg-white/10 text-white": variant === "default",
          "border-emerald-400/30 bg-emerald-400/10 text-emerald-100":
            variant === "success",
          "border-amber-400/30 bg-amber-400/10 text-amber-100": variant === "warning",
        }
      )}
    >
      {children}
    </span>
  );
}

