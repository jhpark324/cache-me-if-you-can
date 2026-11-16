import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const backendPort =
    loadEnv(mode, ".", "CACHE_ME_").CACHE_ME_PORT?.trim() ?? "52761";
  if (
    !/^[0-9]+$/.test(backendPort) ||
    Number(backendPort) < 1 ||
    Number(backendPort) > 65535
  ) {
    throw new Error("CACHE_ME_PORT must be an integer between 1 and 65535.");
  }

  return {
    server: {
      port: 5173,
      strictPort: true,
      proxy: {
        "/api": {
          target: `http://127.0.0.1:${Number(backendPort)}`,
          changeOrigin: false,
        },
      },
    },
    build: { target: "es2022", sourcemap: false },
  };
});
