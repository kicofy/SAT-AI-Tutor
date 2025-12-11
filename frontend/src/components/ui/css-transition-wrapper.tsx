"use client";

import { PropsWithChildren, useEffect, useMemo, useRef } from "react";
import { usePathname } from "next/navigation";
import { routeUsesAppShell } from "@/lib/app-shell-routes";

export function CSSTransitionWrapper({ children }: PropsWithChildren) {
  const pathname = usePathname();
  const sanitizedPath = useMemo(() => pathname?.split("?")[0] || "/", [pathname]);
  const currentHasAppShell = routeUsesAppShell(sanitizedPath);

  const previousAppShellRef = useRef(routeUsesAppShell(sanitizedPath));
  const previousPathRef = useRef(sanitizedPath);
  const previousHasAppShell = previousAppShellRef.current;
  const previousPath = previousPathRef.current;

  const shouldReuseShell =
    previousPath !== undefined && previousHasAppShell && currentHasAppShell;

  useEffect(() => {
    previousAppShellRef.current = currentHasAppShell;
    previousPathRef.current = sanitizedPath;
  }, [sanitizedPath, currentHasAppShell]);

  const key = shouldReuseShell ? "app-shell-stable" : sanitizedPath;
  const className = shouldReuseShell ? undefined : "page-fade";

  return <div key={key} className={className}>{children}</div>;
}

