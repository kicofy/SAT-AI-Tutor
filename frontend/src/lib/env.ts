const DEFAULT_API_BASE = "http://127.0.0.1:5080";

export const env = {
  appName: process.env.NEXT_PUBLIC_APP_NAME || "SAT AI Tutor",
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE || DEFAULT_API_BASE,
  gamificationCopy:
    process.env.NEXT_PUBLIC_GAMIFICATION_COPY ||
    "Complete a block to keep your streak alive!",
};

