import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const apiTarget = process.env.API_PROXY_TARGET || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    allowedHosts: [".trycloudflare.com"],
    proxy: {
      "/auth": apiTarget,
      "/account": apiTarget,
      "/items": apiTarget,
      "/reports": apiTarget,
      "/leaderboard": apiTarget,
      "/uploads": apiTarget,
      "/claims": apiTarget,
      "/my": apiTarget,
      "/admin": apiTarget,
      "/dashboard": apiTarget,
      "/stats": apiTarget,
      "/health": apiTarget,
      "/config": apiTarget,
    },
  },
});
