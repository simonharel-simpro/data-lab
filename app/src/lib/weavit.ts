// Deep link from a project card to its Weaviate collection in Weavit UI's web mode.
import { weavitUrl, type Env } from './config.ts';

// Weaviate class names: an uppercase letter, then letters, digits or underscores. Same rule as Weavit's deepLink.ts.
export const COLLECTION_RE = /^[A-Z][_0-9A-Za-z]*$/;

/** The `collection` param a run logged, when it is a valid Weaviate collection name. */
export function runCollection(params: readonly { key: string; value: string }[]): string | undefined {
  const value = params.find((p) => p.key === 'collection')?.value;
  return value !== undefined && COLLECTION_RE.test(value) ? value : undefined;
}

export function weavitCollectionUrl(collection: string, env: Env = process.env): string {
  if (!COLLECTION_RE.test(collection)) throw new Error(`invalid collection name ${JSON.stringify(collection)}`);
  return `${weavitUrl(env)}/?collection=${encodeURIComponent(collection)}`;
}
