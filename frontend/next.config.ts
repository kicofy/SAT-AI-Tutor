import type { NextConfig } from "next";

// Single source of truth for backend API base.
// Prefer explicitly configured NEXT_PUBLIC_API_BASE; otherwise fall back to LAN IP.
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ||
  process.env.API_BASE ||
  "http://192.168.50.235:5080";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_BASE.replace(/\/$/, "")}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
