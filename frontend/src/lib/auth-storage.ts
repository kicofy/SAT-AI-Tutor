import Cookies from "js-cookie";

const TOKEN_KEY = "sat-token";
const COOKIE_KEY = "sat_token";

export function saveToken(token: string) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(TOKEN_KEY, token);
  Cookies.set(COOKIE_KEY, token, { sameSite: "lax" });
}

export function clearToken() {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(TOKEN_KEY);
  Cookies.remove(COOKIE_KEY);
}

export function getClientToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(TOKEN_KEY);
}

