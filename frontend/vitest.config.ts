import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

/**
 * Unit tests for the pure functions behind the analysis surface.
 *
 * Node environment, no DOM: what is tested here is data going in and data coming out
 * — chart rows, encodings, CSV cells. The components that render them are covered by
 * driving the real app, which is a different kind of test and a slower one.
 */
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
