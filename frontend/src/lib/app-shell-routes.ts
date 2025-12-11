const STATIC_APP_SHELL_PATHS = new Set([
  "/",
  "/dashboard",
  "/practice",
  "/analytics",
  "/settings",
  "/feedback",
  "/suggestions",
  "/diagnostic",
  "/ai",
  "/ai/explain",
  "/membership",
  "/support",
  "/admin",
  "/admin/panel",
]);

const PREFIX_APP_SHELL_PATHS = [
  "/dashboard",
  "/practice",
  "/analytics",
  "/settings",
  "/feedback",
  "/suggestions",
  "/diagnostic",
  "/ai",
  "/admin",
  "/support",
  "/membership",
];

function normalizePath(pathname: string | null): string {
  if (!pathname) return "/";
  const stripped = pathname.split("?")[0] || "/";
  if (stripped === "/") return "/";
  return stripped.endsWith("/") ? stripped.slice(0, -1) : stripped;
}

export function routeUsesAppShell(pathname: string | null): boolean {
  const path = normalizePath(pathname);
  if (STATIC_APP_SHELL_PATHS.has(path)) {
    return true;
  }
  return PREFIX_APP_SHELL_PATHS.some(
    (prefix) => path === prefix || path.startsWith(`${prefix}/`)
  );
}

