import js from "@eslint/js";
import { defineConfig, globalIgnores } from "eslint/config";
import tseslint from "typescript-eslint";

const typescriptFiles = [
  "apps/**/*.{ts,tsx,mts,cts}",
  "packages/**/*.{ts,tsx,mts,cts}",
];

export default defineConfig([
  globalIgnores([
    "**/node_modules/**",
    "**/dist/**",
    "**/.next/**",
    "**/.venv/**",
    "**/__pycache__/**",
  ]),
  {
    files: ["**/*.{js,mjs,cjs}"],
    extends: [js.configs.recommended],
  },
  {
    files: typescriptFiles,
    extends: [tseslint.configs.recommendedTypeChecked],
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
]);
