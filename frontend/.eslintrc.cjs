module.exports = {
  root: true,
  env: { browser: true, es2020: true, node: true },
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:react-hooks/recommended",
  ],
  ignorePatterns: ["dist", ".eslintrc.cjs", "*.config.js", "*.config.ts", "vite.config.d.ts"],
  parser: "@typescript-eslint/parser",
  plugins: ["react-refresh"],
  rules: {
    // v0.1: tests use `as any` for fakeContext mocks; tolerate it.
    "@typescript-eslint/no-explicit-any": "off",
    // Warn (not error) on unused vars; allow `_`-prefixed args for required signatures.
    "@typescript-eslint/no-unused-vars": [
      "warn",
      { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
    ],
    // GraphProvider co-locates context + provider; not worth splitting for fast-refresh.
    "react-refresh/only-export-components": "off",
  },
};
