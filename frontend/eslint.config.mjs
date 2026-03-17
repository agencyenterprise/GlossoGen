import nextConfig from "eslint-config-next";
import eslintConfigPrettier from "eslint-config-prettier";

const eslintConfig = [
  {
    ignores: [
      "build/",
      "node_modules/",
      ".next/",
      "*.config.js",
      "*.config.ts",
      "*.config.mjs",
      "coverage/",
      "public/",
      "src/types/api.gen.ts",
    ],
  },
  ...nextConfig,
  eslintConfigPrettier,
  {
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          args: "all",
          argsIgnorePattern: "^_",
          caughtErrors: "all",
          caughtErrorsIgnorePattern: "^_",
          destructuredArrayIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          ignoreRestSiblings: true,
        },
      ],
      "@typescript-eslint/no-non-null-assertion": "off",
      "@typescript-eslint/prefer-as-const": "error",
      "no-console": "warn",
      "no-debugger": "error",
      "prefer-const": "error",
      "no-var": "error",
      "no-restricted-globals": [
        "warn",
        {
          name: "fetch",
          message:
            "Use the typed API client from '@/shared/lib/api-client' instead of raw fetch(). This ensures compile-time path validation and type-safe responses.",
        },
      ],
    },
  },
  {
    files: ["**/*.js", "**/*.jsx"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "Program",
          message:
            "JavaScript files are not allowed. Please use TypeScript (.ts/.tsx) files instead.",
        },
      ],
    },
  },
];

export default eslintConfig;
