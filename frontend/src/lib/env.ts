// Prefer current host; if running dev on port 3000, map to backend 5080 on same host.
function resolveDefaultApiBase(): string {
  // Server-side渲染或未设置环境变量时的安全默认值：本机 5080
  if (typeof window === "undefined") {
    return "http://127.0.0.1:5080";
  }
  const { protocol, hostname, port } = window.location;
  // 常见本地前端端口 3000/3001，对应后端 5080
  if (port === "3000" || port === "3001") {
    return `${protocol}//${hostname}:5080`;
  }
  // 同域部署则直接用当前来源
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

