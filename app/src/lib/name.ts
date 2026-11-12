// Identical literal in packages/datalab/src/datalab/project.py; vectors in contracts/name_vectors.json.
// eslint-disable-next-line security/detect-unsafe-regex -- anchored; each repetition starts with a literal '-', so matching is linear; literal mirrored from datalab project.py
export const NAME_RE = /^[a-z][a-z0-9]*(-[a-z0-9]+)*$/;

// Test/infra namespaces + the YAML 1.1 bool/null words: PyYAML reads `name: no` as False, the JS parser as "no";
// reserving them keeps both sides agreeing.
export const RESERVED: ReadonlySet<string> = new Set([
  'test',
  'datalab',
  'datalab-test',
  'template',
  'y',
  'n',
  'yes',
  'no',
  'on',
  'off',
  'true',
  'false',
  'null',
]);

export function isValidName(s: unknown): boolean {
  return typeof s === 'string' && NAME_RE.test(s) && !RESERVED.has(s);
}
