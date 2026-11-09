import type { AstroIntegration } from 'astro';
import { readReport } from '../lib/report.ts';
import { isStrictExport, type Env } from '../lib/config.ts';

const LEDGER_KEY = 'run.json:';

/**
 * Log one line per card whose metrics were unavailable (F-1) or whose run.json is invalid (F-20); with
 * DATALAB_STRICT_EXPORT=1 any entry fails the export.
 */
export function checkReport(
  report: ReadonlyMap<string, string>,
  env: Env,
  log: (line: string) => void = console.warn,
): void {
  for (const [key, reason] of report) {
    if (key.startsWith(LEDGER_KEY)) log(`run.json invalid for '${key.slice(LEDGER_KEY.length)}': ${reason}`);
    else log(`metrics unavailable for '${key}': ${reason}`);
  }
  if (isStrictExport(env) && report.size > 0) {
    const names = [...report.keys()].join(', ');
    throw new Error(`DATALAB_STRICT_EXPORT=1: export refused, metrics unavailable or run.json invalid for ${names}`);
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
