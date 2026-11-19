// Vite build for the site. Output goes to dist/, which the engine copies into the private archive.
// Data (data/arena.json, data/days/*.json) is not part of the build: the engine writes it next to it.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "./",
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    target: "es2022",
    sourcemap: false,
    assetsInlineLimit: 0,
    modulePreload: { polyfill: false },
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      // the main site plus the two Experience v3 prototypes (same data, same login)
      input: { main: "index.html", classic: "classic/index.html", world: "p/world/index.html" },
    },   // the 3D world chunk is big by nature and loads after the first frame
  },
  server: { port: 5173 },
});
