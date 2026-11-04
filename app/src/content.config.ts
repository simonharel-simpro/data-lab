import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { cardSchema } from './lib/card.ts';

const projects = defineCollection({
  // Each project owns ../projects/<name>/PROJECT.md; the folder name is the entry id. DATALAB_PROJECTS_DIR exists
  // only for the CI build fixtures (app/test-fixtures/*). Dot-folders (datalab-new temp dirs) are not matched.
  loader: glob({
    base: process.env.DATALAB_PROJECTS_DIR ?? '../projects',
    pattern: '*/PROJECT.md',
    generateId: ({ entry }) => entry.split('/')[0],
  }),
  schema: cardSchema,
});

export const collections = { projects };
