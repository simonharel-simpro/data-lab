// Build report on globalThis, never a module variable: during `astro build` the pages and the export-guard
// integration load separate module instances, so a module-level map would stay empty in the build hook (B-1).

/** Record that `project`'s metrics could not be read (one entry per project, deduped across pages). */
export function reportUnavailable(project: string, reason: string): void {
  const report = readReport();
  if (report.get(project) !== reason) console.warn(`[mlflow] ${project}: ${reason}`);
  report.set(project, reason);
}

export function readReport(): Map<string, string> {
  return (globalThis.__datalabBuildReport ??= new Map<string, string>());
}
