import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = ["/auth/login", "/auth/register", "/auth/forgot-password", "/auth/reset-password"];
const STATIC_PREFIXES = ["/_next", "/api", "/favicon.ico", "/assets"];
const REDIRECT_WHEN_AUTHENTICATED = ["/auth/login", "/auth/register"];

function isStaticPath(pathname: string) {
  return STATIC_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

function isPublicPath(pathname: string) {
  return PUBLIC_PATHS.some((path) => pathname.startsWith(path));
}

function shouldRedirectHome(pathname: string) {
  return REDIRECT_WHEN_AUTHENTICATED.some((path) => pathname.startsWith(path));
}

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (isStaticPath(pathname)) {
    return NextResponse.next();
  }

  const token = request.cookies.get("sat_token")?.value;

  if (!token && !isPublicPath(pathname)) {
    const loginUrl = new URL("/auth/login", request.url);
    loginUrl.searchParams.set("redirect", `${pathname}${search}`);
    return NextResponse.redirect(loginUrl);
  }

  if (token && shouldRedirectHome(pathname)) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};

