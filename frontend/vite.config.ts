import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // 将 /api 请求代理到后端开发服务器
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
