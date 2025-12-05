"use client";

import { PropsWithChildren, useMemo } from "react";
import { usePathname } from "next/navigation";

export function CSSTransitionWrapper({ children }: PropsWithChildren) {
  const pathname = usePathname();
  const key = useMemo(() => pathname?.split("?")[0] ?? "root", [pathname]);
  return (
    <div key={key} className="page-fade">
      {children}
    </div>
  );
}

