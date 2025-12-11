// Prefer current host; if running dev on port 3000, map to backend 5080 on same host.
function resolveDefaultApiBase(): string {
  if (typeof window === "undefined") {
    // Server-side/default fallback for LAN deployment
    return "http://192.168.50.235:5080";
  }
  const { protocol, hostname, port } = window.location;
  if (port === "3000" || port === "3001") {
    return `${protocol}//${hostname}:5080`;
  }
  return window.location.origin;
}

const DEFAULT_API_BASE = resolveDefaultApiBase();

export const env = {
  appName: process.env.NEXT_PUBLIC_APP_NAME || "SAT AI Tutor",
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE || DEFAULT_API_BASE,
  gamificationCopy:
    process.env.NEXT_PUBLIC_GAMIFICATION_COPY ||
    "Complete a block to keep your streak alive!",
};

