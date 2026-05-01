import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  test: {
    globals:     true,
    environment: "node",
    include:     ["lib/__tests__/**/*.test.ts"],
    coverage: {
      provider: "v8",
      include:  ["lib/**/*.ts"],
      exclude:  ["lib/__tests__/**"],
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
});
