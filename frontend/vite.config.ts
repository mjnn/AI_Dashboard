import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  let base = env.VITE_BASE || "/";
  if (!base.startsWith("/")) {
    base = `/${base}`;
  }
  if (base !== "/" && !base.endsWith("/")) {
    base = `${base}/`;
  }

  return {
    base,
    plugins: [react()],
    server: {
      proxy: {
        "/api": {
          target: "http://localhost:8000",
          changeOrigin: true,
        },
      },
    },
  };
});
