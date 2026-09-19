import { defineConfig, devices } from "@playwright/test";

const PORT = 3100;

// E2E runs against the real stack: Next.js (started here) -> FastAPI
// (TUNORA_API_URL, default http://127.0.0.1:8000, must already be running)
// -> ACE-Step. See docs/PHASE-3-CREATE-SONG-UI.md for how to start them.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  use: { baseURL: `http://127.0.0.1:${PORT}` },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `npx next dev -p ${PORT}`,
    url: `http://127.0.0.1:${PORT}/create`,
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
