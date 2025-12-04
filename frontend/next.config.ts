import type { NextConfig } from "next";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:5080";

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
