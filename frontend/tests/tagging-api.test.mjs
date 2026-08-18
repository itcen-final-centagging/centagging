import assert from 'node:assert/strict';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { createServer } from 'vite';

const loadTaggingApi = async (t) => {
  const server = await createServer({
    appType: 'custom',
    logLevel: 'silent',
    root: fileURLToPath(new URL('..', import.meta.url)),
    server: { middlewareMode: true },
  });
  t.after(() => server.close());
  return server.ssrLoadModule('/src/features/tagging/api/tagging.ts');
};

const loadSaveWorkflow = async (t) => {
  const server = await createServer({
    appType: 'custom',
    logLevel: 'silent',
    root: fileURLToPath(new URL('..', import.meta.url)),
    server: { middlewareMode: true },
  });
  t.after(() => server.close());
  return server.ssrLoadModule(
    '/src/features/tagging/services/save-tagging-workflow.ts',
  );
};

test('history refresh failure does not undo a successful save', async (t) => {
  const { saveTaggingAndRefreshHistory } = await loadSaveWorkflow(t);
  const events = [];

  const result = await saveTaggingAndRefreshHistory({
    onSaved: () => events.push('saved'),
    refreshHistory: async () => {
      events.push('history');
      throw new Error('이력 서버 오류');
    },
    save: async () => events.push('put'),
  });

  assert.deepEqual(events, ['put', 'saved', 'history']);
  assert.deepEqual(result, {
    historyError: '이력 서버 오류',
  });
});

test('save failure does not mark saved or refresh history', async (t) => {
  const { saveTaggingAndRefreshHistory } = await loadSaveWorkflow(t);
  const events = [];

  await assert.rejects(
    saveTaggingAndRefreshHistory({
      onSaved: () => events.push('saved'),
      refreshHistory: async () => {
        events.push('history');
        return [];
      },
      save: async () => {
        events.push('put');
        throw new Error('저장 서버 오류');
      },
    }),
    /저장 서버 오류/,
  );

  assert.deepEqual(events, ['put']);
});

test('history results are mapped from the backend response', async (t) => {
  const { fetchTaggingHistory } = await loadTaggingApi(t);
  const originalFetch = globalThis.fetch;
  let requestUrl;
  globalThis.fetch = async (input) => {
    requestUrl = input;
    return new Response(
      JSON.stringify({
        status: 'success',
        data: {
          items: [
            {
              result_id: 91,
              sku_code: 'CHR-2041',
              product_name: 'work chair',
              object_name: 'chair',
              similarity_score: 92,
              created_by: 'mvp-user',
              created_at: '2026-08-11T00:00:00Z',
              style_tags: ['minimal'],
              scene_image: {
                image_url: '/uploads/scene.png',
                origin_name: 'scene.png',
                bbox: { xmin: 10, ymin: 20, xmax: 30, ymax: 40 },
              },
            },
          ],
        },
        meta: { request_id: 'request-123' },
      }),
      { headers: { 'Content-Type': 'application/json' }, status: 200 },
    );
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  const history = await fetchTaggingHistory();

  assert.equal(requestUrl, '/history/results');
  assert.deepEqual(history, [
    {
      id: '91',
      imageName: 'scene.png',
      objectName: 'chair',
      productName: 'work chair',
      savedAt: '2026-08-11T00:00:00Z',
      sku: 'CHR-2041',
      tags: {
        category: '',
        color: '',
        material: '',
        mood: '',
        styleTags: ['minimal'],
      },
    },
  ]);
});

test('save and history requests use their backend contracts', async (t) => {
  const { fetchTaggingHistory, saveTaggingReview } = await loadTaggingApi(t);
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (input, init) => {
    requests.push({ init, input });
    if (init?.method === 'POST') {
      return new Response(
        JSON.stringify({
          status: 'success',
          data: { processing_status: 'CONFIRMED', result_ids: [1] },
          meta: { request_id: 'request-123' },
        }),
        { headers: { 'Content-Type': 'application/json' }, status: 200 },
      );
    }
    return new Response(
      JSON.stringify({
        status: 'success',
        data: {
          items: [
            {
              result_id: 91,
              sku_code: 'CHR-2041',
              product_name: 'work chair',
              object_name: 'chair',
              similarity_score: 92,
              created_by: 'mvp-user',
              created_at: '2026-08-11T00:00:00Z',
              style_tags: [],
              scene_image: {
                image_url: '/uploads/scene.png',
                origin_name: 'scene.png',
                bbox: { xmin: 10, ymin: 20, xmax: 30, ymax: 40 },
              },
            },
          ],
        },
        meta: { request_id: 'request-123' },
      }),
      { headers: { 'Content-Type': 'application/json' }, status: 200 },
    );
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  await saveTaggingReview({
    matching: [
      {
        object: { bbox: [100, 200, 800, 900], objectIdx: 1 },
        objectIdx: 1,
        selectedSku: {
          category: 'chair',
          color: 'white',
          matchRank: 2,
          material: 'mesh',
          score: 92,
          sku: 'CHR-2041',
          skuId: 50,
          style: 'modern',
          subCategory: 'office chair',
          vlmMood: {
            summary: 'A warm living room.',
            tags: ['modern'],
          },
          xaiResult: {
            criteria: [
              {
                comment: 'The backrest structure matches.',
                label: 'structure',
                score: 29,
              },
            ],
            summary: 'The structure and color are similar.',
          },
        },
        values: {
          category: 'chair',
          color: 'white',
          material: 'mesh',
          mood: 'A warm living room.',
          styleTags: ['modern'],
        },
      },
      {
        object: { bbox: [50, 60, 400, 500], objectIdx: 2 },
        objectIdx: 2,
        selectedSku: {
          category: 'table',
          color: 'oak',
          matchRank: 1,
          material: 'wood',
          score: 88,
          sku: 'TBL-1007',
          skuId: 71,
          style: 'natural',
          subCategory: 'dining table',
          vlmMood: {
            summary: 'A compact dining area.',
            tags: ['natural'],
          },
          xaiResult: {
            criteria: [
              {
                comment: 'The table legs and top shape match.',
                label: 'structure',
                score: 27,
              },
            ],
            summary: 'The table shape is a close match.',
          },
        },
        values: {
          category: 'table',
          color: 'brown',
          material: 'oak',
          mood: 'A compact dining area.',
          styleTags: ['null', 'natural'],
        },
      },
    ],
    sceneImageId: '7',
  });
  const history = await fetchTaggingHistory();

  assert.equal(requests[0].input, '/tagging/scenes/7/results');
  assert.equal(requests[0].init.method, 'POST');
  assert.deepEqual(JSON.parse(requests[0].init.body), {
    tagging_results: [
      {
        match_rank: 2,
        object_idx: 1,
        object_metadata: {
          attrs: { color: 'white', material: 'mesh', style: 'modern' },
          bbox_coord: { xmax: 900, xmin: 200, ymax: 800, ymin: 100 },
          category: 'chair',
          object_idx: 1,
          sub_category: 'office chair',
        },
        similarity_score: 92,
        sku_id: 50,
        vlm_mood: {
          summary: 'A warm living room.',
          tags: ['modern'],
        },
        xai_result: {
          criteria: [
            {
              comment: 'The backrest structure matches.',
              label: 'structure',
              score: 29,
            },
          ],
          summary: 'The structure and color are similar.',
        },
      },
      {
        match_rank: 1,
        object_idx: 2,
        object_metadata: {
          attrs: { color: 'brown', material: 'oak', style: 'natural' },
          bbox_coord: { xmax: 500, xmin: 60, ymax: 400, ymin: 50 },
          category: 'table',
          object_idx: 2,
          sub_category: 'dining table',
        },
        similarity_score: 88,
        sku_id: 71,
        vlm_mood: {
          summary: 'A compact dining area.',
          tags: ['natural'],
        },
        xai_result: {
          criteria: [
            {
              comment: 'The table legs and top shape match.',
              label: 'structure',
              score: 27,
            },
          ],
          summary: 'The table shape is a close match.',
        },
      },
    ],
  });
  assert.equal(requests[1].input, '/history/results');
  assert.equal(history[0].id, '91');
});

test('recommendation keeps its rank, full XAI, and VLM mood', async (t) => {
  const { fetchRecommendations } = await loadTaggingApi(t);
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        status: 'success',
        data: {
          objects: [
            {
              object_idx: 1,
              sku_candidates: [
                {
                  attrs: { color: 'white', material: 'mesh' },
                  category: 'chair',
                  matched_sku_image: { image_url: '/images/chair.png' },
                  product_name: 'work chair',
                  similarity_score: 92,
                  sku_code: 'CHR-2041',
                  sub_category: 'office chair',
                  xai_result: {
                    criteria: [
                      {
                        comment: 'The backrest structure matches.',
                        label: 'structure',
                        score: 29,
                      },
                    ],
                    summary: 'The structure and color are similar.',
                    vlm_mood: {
                      summary: 'A warm living room.',
                      tags: ['natural'],
                    },
                  },
                },
              ],
            },
          ],
        },
        meta: { request_id: 'request-123' },
      }),
      { headers: { 'Content-Type': 'application/json' }, status: 200 },
    );
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  const [candidate] = await fetchRecommendations('7', 1);

  assert.deepEqual(
    {
      matchRank: candidate.matchRank,
      score: candidate.score,
      vlmMood: candidate.vlmMood,
      xaiResult: candidate.xaiResult,
    },
    {
      matchRank: 1,
      score: 92,
      vlmMood: {
        summary: 'A warm living room.',
        tags: ['natural'],
      },
      xaiResult: {
        criteria: [
          {
            comment: 'The backrest structure matches.',
            label: 'structure',
            score: 29,
          },
        ],
        summary: 'The structure and color are similar.',
      },
    },
  );
});
