import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_PATHS = ["/auth/login", "/auth/register", "/auth/forgot-password", "/auth/reset-password"];
const REDIRECT_WHEN_AUTHENTICATED = ["/auth/login", "/auth/register"];

function isPublicPath(pathname: string) {
  return PUBLIC_PATHS.some((path) => pathname.startsWith(path));
}

function shouldRedirectHome(pathname: string) {
  return REDIRECT_WHEN_AUTHENTICATED.some((path) => pathname.startsWith(path));
}

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname.startsWith("/static") ||
    pathname === "/favicon.ico"
  ) {
    return NextResponse.next();
  }

  const token = request.cookies.get("sat_token")?.value;

  if (!token && !isPublicPath(pathname)) {
    const loginUrl = new URL("/auth/login", request.url);
    const redirectTarget = `${pathname}${search}`;
    loginUrl.searchParams.set("redirect", redirectTarget);
    return NextResponse.redirect(loginUrl);
  }

  if (token && shouldRedirectHome(pathname)) {
    const homeUrl = new URL("/", request.url);
    return NextResponse.redirect(homeUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};

