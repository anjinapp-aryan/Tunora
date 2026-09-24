import type { NextConfig } from "next";

// The browser only ever talks to Next.js; /api/* is proxied server-side to
// Tunora's FastAPI backend. Keeps the backend origin out of client code and
// avoids CORS. The frontend never calls ACE-Step.
const TUNORA_API_URL = process.env.TUNORA_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Lets a second dev server (for example the E2E run) use its own build directory.
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  // Lets the dev server hydrate when opened via 127.0.0.1 (Playwright, some browsers).
  allowedDevOrigins: ["127.0.0.1"],
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${TUNORA_API_URL}/api/:path*` }];
  },
};

export default nextConfig;
