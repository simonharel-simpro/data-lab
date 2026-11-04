declare global {
  // Build report shared across Astro module instances (src/lib/report.ts).
  var __datalabBuildReport: Map<string, string> | undefined;
}

export {};
