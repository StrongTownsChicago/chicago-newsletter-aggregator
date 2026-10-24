// Mutation testing (dev-only, not run in CI): `npm run test:mutation`.
// Narrow a run with `npm run test:mutation -- --mutate src/lib/wards.ts`.
/** @type {import("@stryker-mutator/api/core").PartialStrykerOptions} */
export default {
  testRunner: "vitest",
  vitest: { configFile: "vitest.config.ts" },
  coverageAnalysis: "perTest",
  mutate: [
    "src/lib/**/*.ts",
    "src/pages/api/**/*.ts",
    "src/middleware.ts",
    // Constants only: no behavior to mutate.
    "!src/lib/load-messages.ts",
  ],
  reporters: ["clear-text", "progress", "html", "json"],
  htmlReporter: { fileName: "reports/mutation/mutation.html" },
  jsonReporter: { fileName: "reports/mutation/mutation.json" },
  tempDirName: ".stryker-tmp",
};
