import assert from 'node:assert/strict';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { createServer } from 'vite';

const loadHistoryGrouping = async (t) => {
  const server = await createServer({
    appType: 'custom',
    logLevel: 'silent',
    root: fileURLToPath(new URL('..', import.meta.url)),
    server: { middlewareMode: true },
  });
  t.after(() => server.close());
  return server.ssrLoadModule('/src/features/tagging/utils/history.ts');
};

const historyRecord = ({ id, objectIdx, sceneImageId }) => ({
  approvalStatus: null,
  id,
  imageName: `scene-${sceneImageId}.png`,
  objectIdx,
  objectName: '의자',
  productName: `상품-${id}`,
  savedAt: `2026-08-2${id}T10:00:00Z`,
  sceneImage: {
    bbox: null,
    id: sceneImageId,
    imageUrl: `/uploads/scene-${sceneImageId}.png`,
  },
  sku: `SKU-${id}`,
  skuImageUrl: null,
  tags: {
    category: '',
    color: '',
    materials: {},
    mood: '',
    styleTags: [],
    subCategory: '',
  },
});

test('groups history by scene image and orders objects by object index', async (t) => {
  const { groupTaggingHistoryByScene } = await loadHistoryGrouping(t);

  const groups = groupTaggingHistoryByScene([
    historyRecord({ id: '1', objectIdx: 2, sceneImageId: '10' }),
    historyRecord({ id: '2', objectIdx: 1, sceneImageId: '10' }),
    historyRecord({ id: '3', objectIdx: 0, sceneImageId: '11' }),
  ]);

  assert.deepEqual(
    groups.map((group) => ({
      id: group.id,
      objectIndexes: group.records.map((record) => record.objectIdx),
    })),
    [
      { id: '10', objectIndexes: [1, 2] },
      { id: '11', objectIndexes: [0] },
    ],
  );
});
