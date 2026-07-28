import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": "/src",
    },
  },
  // @vitejs/plugin-react's automatic JSX runtime (no `import React` needed
  // in any .jsx file, which is how every file in this project is written)
  // is applied correctly by `vite build`/`vite dev`, but Vitest's own
  // transform path doesn't pick it up implicitly — without this it falls
  // back to the classic transform (`React.createElement(...)`), which then
  // throws "ReferenceError: React is not defined" on the first JSX
  // expression in any test file. Spelling it out here makes Vitest use the
  // same automatic runtime as the rest of the build.
  esbuild: {
    jsx: "automatic",
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.js"],
  },
})
