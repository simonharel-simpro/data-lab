import type { AstroIntegration } from 'astro';
import { readReport } from '../lib/report.ts';

type Env = Record<string, string | undefined>;

/** Log one line per card whose metrics were unavailable; with DATALAB_STRICT_EXPORT=1 any such card fails (F-1). */
export function checkReport(report: ReadonlyMap<string, string>, env: Env, log: (line: string) => void = console.warn): void {
  for (const [project, reason] of report) log(`metrics unavailable for '${project}': ${reason}`);
  if (env.DATALAB_STRICT_EXPORT === '1' && report.size > 0) {
    const names = [...report.keys()].join(', ');
    throw new Error(`DATALAB_STRICT_EXPORT=1: export refused, MLflow metrics unavailable for ${names}`);
  }
}

export function exportGuard(env: Env = process.env): AstroIntegration {
  return {
    name: 'datalab-export-guard',
    hooks: {
      'astro:build:done': ({ logger }) => checkReport(readReport(), env, (line) => logger.warn(line)),
    },
  };
}
