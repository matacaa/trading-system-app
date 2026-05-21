import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Middleware runs on the edge — we can't access localStorage here.
// Auth protection is handled client-side by the dashboard layout.
// This middleware only handles basic redirects.

const PUBLIC_PATHS = ["/login", "/register", "/"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Allow public paths and static files
  if (
    PUBLIC_PATHS.includes(pathname) ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname.includes(".")
  ) {
    return NextResponse.next();
  }

  // All other routes pass through — client-side auth guard handles the rest
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
