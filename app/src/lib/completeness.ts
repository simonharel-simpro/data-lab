import type { Card, Status } from './card.ts';

// What a card must contain once it reaches a status (each level adds to the previous one).
const SECTIONS_BY_STATUS: Record<Status, readonly string[]> = {
  'idée': ['Objectif'],
  'en cours': ['Objectif', 'Approche'],
  'conclu': ['Objectif', 'Approche', 'Enseignements', 'Suite'],
  'abandonné': ['Objectif', 'Approche', 'Enseignements', 'Suite'],
};
const NEEDS_DATA_AND_METRIC: readonly Status[] = ['en cours', 'conclu', 'abandonné'];

const HEADING = /^## +(.+)$/;
const FENCE = /^ {0,3}(`{3,}|~{3,})/;
const COMMENT = /<!--[\s\S]*?(-->|$)/g;

/**
 * Section heading (NFC, trimmed, case-sensitive) -> whether any occurrence has content (U-9a/b).
 * Lines inside fenced code blocks are content, never headings (U-9d); HTML comments are not content (U-9c).
 */
export function sections(body: string): Map<string, boolean> {
  const out = new Map<string, boolean>();
  const chunks: { name: string; lines: string[] }[] = [];
  let fence: string | null = null;
  for (const line of body.split(/\r?\n/)) {
    const f = FENCE.exec(line)?.[1];
    if (f && (fence === null || (f[0] === fence[0] && f.length >= fence.length))) {
      fence = fence === null ? f : null;
    } else if (fence === null) {
      const h = HEADING.exec(line);
      if (h) {
        chunks.push({ name: h[1].normalize('NFC').trim(), lines: [] });
        continue;
      }
    }
    chunks.at(-1)?.lines.push(line);
  }
  for (const { name, lines } of chunks) {
    const filled = lines.join('\n').replace(COMMENT, '').trim() !== '';
    out.set(name, (out.get(name) ?? false) || filled);
  }
  return out;
}

/** Names of what is missing for the card's current status; an empty section counts as missing. */
export function missing(card: Pick<Card, 'status' | 'data' | 'metric'>, body: string): string[] {
  const found = sections(body);
  const gaps = SECTIONS_BY_STATUS[card.status].filter((s) => !found.get(s));
  if (NEEDS_DATA_AND_METRIC.includes(card.status)) {
    if (!card.data) gaps.push('Données');
    if (!card.metric) gaps.push('Métrique');
  }
  return gaps;
}
