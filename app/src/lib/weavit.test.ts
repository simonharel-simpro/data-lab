import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runCollection, weavitCollectionUrl } from './weavit.ts';

test('weavitCollectionUrl defaults to the local Weavit web server', () => {
  assert.equal(weavitCollectionUrl('MiniRag_x_1', {}), 'http://127.0.0.1:3080/?collection=MiniRag_x_1');
});

test('weavitCollectionUrl reads DATALAB_WEAVIT_URL', () => {
  assert.equal(weavitCollectionUrl('A', { DATALAB_WEAVIT_URL: 'http://h:9' }), 'http://h:9/?collection=A');
});

test('weavitCollectionUrl refuses a value that is not a collection name', () => {
  for (const bad of ['', 'lower', 'A b', 'A&x=1', '"><x']) {
    assert.throws(() => weavitCollectionUrl(bad, {}), /invalid collection name/, bad);
  }
});

test('runCollection picks the collection param and ignores invalid names', () => {
  assert.equal(
    runCollection([
      { key: 'k', value: '3' },
      { key: 'collection', value: 'MiniRag_x' },
    ]),
    'MiniRag_x',
  );
  assert.equal(runCollection([{ key: 'collection', value: 'mini-rag' }]), undefined);
  assert.equal(runCollection([]), undefined);
});
