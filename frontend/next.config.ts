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
  experimental: {
    // Music Video backgrounds (Phase 23) are uploaded through the /api rewrite. Next buffers a
    // proxied request body up to this size (default 10 MB) and fails larger ones; match the
    // backend's own cap (200 MB for a background video) so the backend stays the one enforcing it.
    proxyClientMaxBodySize: "201mb",
    // The /api rewrite proxy aborts a request after 30 s by default and answers 500. The AI Song
    // Director's plan/refine calls run ACE-Step's LM (observed up to ~90 s, longer on the first call
    // while the LM loads; the backend allows 180 s), so keep the proxy above the backend's own limit.
    proxyTimeout: 240_000,
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${TUNORA_API_URL}/api/:path*` }];
  },
};

export default nextConfig;
