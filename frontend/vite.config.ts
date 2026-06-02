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
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
        },
        // 若误用生产 VITE_API_BASE 本地仍可代理
        "/tools/ai-dashboard/api": {
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/tools\/ai-dashboard/, ""),
        },
      },
    },
  };
});
