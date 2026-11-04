import { getCollection, type CollectionEntry } from 'astro:content';
import type { Status } from './card.ts';

const STATUS_ORDER: readonly Status[] = ['en cours', 'idée', 'conclu', 'abandonné'];

/** Every card, active first; a card whose `name` differs from its folder fails the build (S-9, D-13). */
export async function loadProjects(): Promise<CollectionEntry<'projects'>[]> {
  const entries = await getCollection('projects');
  for (const e of entries) {
    if (e.data.name !== e.id) {
      throw new Error(`${e.filePath ?? e.id}: name '${e.data.name}' must equal its folder '${e.id}'`);
    }
  }
  return entries.sort(
    (a, b) =>
      STATUS_ORDER.indexOf(a.data.status) - STATUS_ORDER.indexOf(b.data.status) ||
      a.data.title.localeCompare(b.data.title, 'fr') ||
      a.id.localeCompare(b.id),
  );
}
