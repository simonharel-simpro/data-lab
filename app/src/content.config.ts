import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { cardSchema } from './lib/card.ts';
import { projectsDir } from './lib/config.ts';

const projects = defineCollection({
  // Each project owns ../projects/<name>/PROJECT.md; the folder name is the entry id (base: see config.ts).
  // Dot-folders (datalab-new temp dirs) are not matched.
  loader: glob({
    base: projectsDir(),
    pattern: '*/PROJECT.md',
    // `*/PROJECT.md` guarantees a first segment: `?? entry` only satisfies noUncheckedIndexedAccess.
    generateId: ({ entry }) => entry.split('/')[0] ?? entry,
  }),
  schema: cardSchema,
});

export const collections = { projects };
