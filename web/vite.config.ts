import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * Two things matter here.
 *
 * `base: "/app/"` — the built assets are served from /app on the API's own origin, and
 * Vite writes absolute asset URLs into index.html at build time. Without this they
 * would point at /assets/... and 404 behind the mount.
 *
 * `server.proxy` — in development, Vite serves the UI on :5173 while FastAPI runs on
 * :8000. Proxying the API paths through Vite keeps the browser on one origin, so the
 * dev setup exercises the same same-origin behaviour as production instead of needing
 * CORS that the deployed app does not use.
 */
export default defineConfig({
  plugins: [react()],
  base: "/app/",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: true,
  },
  server: {
    port: 5173,
    proxy: {
      // Everything that is not the app itself or a Vite internal goes to the API.
      //
      // This was a hand-written list of prefixes — /auth, /todos, /assets and so on —
      // which meant every new router needed a matching line here, and forgetting one
      // failed at runtime with a message about base URLs that says nothing about the
      // real cause. Inverting it removes the coupling: a route this file has never
      // heard of is proxied by default, and the only paths kept local are the ones
      // Vite genuinely owns.
      //
      // A key starting with ^ is treated as a regular expression by Vite.
      "^/(?!app/|@|src/|node_modules/|favicon)": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
      },
    },
  },
});
