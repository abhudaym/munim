import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev the API runs separately (`munim serve`); the proxy keeps fetch("/api/...") same-origin.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
});
