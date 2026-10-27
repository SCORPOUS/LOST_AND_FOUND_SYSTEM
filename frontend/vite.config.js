import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/items": "http://127.0.0.1:8000",
      "/claims": "http://127.0.0.1:8000",
      "/my": "http://127.0.0.1:8000",
      "/admin": "http://127.0.0.1:8000",
      "/stats": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
      "/config": "http://127.0.0.1:8000",
<<<<<<< HEAD
      "/auth": "http://127.0.0.1:8000",
=======
>>>>>>> 8211c2f3d11a4ca8a3cf071dc5d4a4adc1e5020d
    },
  },
});
