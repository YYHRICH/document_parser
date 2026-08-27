import { defineConfig, loadEnv } from "vite";
import { fileURLToPath, URL } from "node:url";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiBaseUrl = (env.VITE_API_BASE_URL || "").replace(/\/+$/, "");

  return {
    define: {
      __DOCUMENT_PARSER_API_BASE_URL__: JSON.stringify(apiBaseUrl),
    },
    server: {
      proxy: {
        "/api": {
          target: env.VITE_DEV_API_ORIGIN || "http://127.0.0.1:8011",
          changeOrigin: true,
        },
      },
    },
    build: {
      rollupOptions: {
        input: {
          upload: fileURLToPath(new URL("./index.html", import.meta.url)),
          taskCenter: fileURLToPath(new URL("./task-center.html", import.meta.url)),
          documentDetail: fileURLToPath(new URL("./document-detail.html", import.meta.url)),
        },
      },
    },
  };
});
