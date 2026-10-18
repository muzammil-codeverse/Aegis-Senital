import { defineConfig } from "vite";
import { resolve } from "node:path";
const pages = [
  "index",
  "platform",
  "operations",
  "intelligence",
  "technology",
  "login",
  "signup",
  "privacy",
  "404",
];
export default defineConfig({
  build: {
    rollupOptions: {
      input: Object.fromEntries(
        pages.map((p) => [p, resolve(import.meta.dirname, `${p}.html`)]),
      ),
    },
  },
  server: { allowedHosts: ["terminal.local"] },
});
