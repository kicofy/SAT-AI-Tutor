"use client";

import { cva, type VariantProps } from "class-variance-authority";
import { ReactNode } from "react";
import clsx from "clsx";

const cardVariants = cva(
  "rounded-2xl border border-white/8 bg-[#0A1324] p-5 flex flex-col gap-3",
  {
    variants: {
      tone: {
        default: "",
        subtle: "bg-[#0C1529]",
      },
    },
    defaultVariants: { tone: "default" },
  }
);

type DashboardCardProps = VariantProps<typeof cardVariants> & {
  title: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
};

export function DashboardCard({
  title,
  subtitle,
  children,
  tone,
}: DashboardCardProps) {
  return (
    <article className={clsx(cardVariants({ tone }))}>
      <div>
        <p className="text-base font-semibold text-white">{title}</p>
        {subtitle && <p className="text-sm text-white/60 mt-1">{subtitle}</p>}
      </div>
      <div>{children}</div>
    </article>
  );
}

