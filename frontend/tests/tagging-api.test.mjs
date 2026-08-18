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

test('save request uses its backend contract without refreshing history', async (t) => {
  const { saveTaggingReview } = await loadTaggingApi(t);
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (input, init) => {
    requests.push({ init, input });
    if (init?.method === 'POST') {
      return new Response(
        JSON.stringify({
          status: 'success',
          data: { processing_status: 'CONFIRMED', result_ids: [1, 2] },
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
        object: { bbox: [100, 200, 800, 900] },
        objectIndex: 1,
        selectedSku: {
          category: '의자',
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
      },
      {
        object: { bbox: [50, 60, 400, 500] },
        objectIndex: 2,
        selectedSku: {
          category: '테이블',
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
            tags: ['modern'],
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
          category: '테이블',
          color: '브라운',
          material: '원목',
          mood: '따뜻한 다이닝룸입니다.',
          styleTags: ['null', '내추럴'],
        },
      },
    ],
    sceneImageId: '7',
  });
  assert.equal(requests[0].input, '/tagging/scenes/7/results');
  assert.equal(requests[0].init.method, 'POST');
  assert.deepEqual(JSON.parse(requests[0].init.body), {
    tagging_results: [
      {
        match_rank: 2,
        object_index: 1,
        object_metadata: {
          attrs: { color: 'white', material: 'mesh', style: 'modern' },
          bbox_coord: { xmax: 900, xmin: 200, ymax: 800, ymin: 100 },
          category: '의자',
          object_index: 1,
          sub_category: 'office chair',
        },
        similarity_score: 92,
        sku_id: 50,
        vlm_mood: {
          summary: 'A warm living room.',
          tags: ['natural'],
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
        object_index: 2,
        object_metadata: {
          attrs: { color: '브라운', material: '원목', style: '내추럴' },
          bbox_coord: { xmax: 500, xmin: 60, ymax: 400, ymin: 50 },
          category: '테이블',
          object_index: 2,
          sub_category: 'dining table',
        },
        similarity_score: 88,
        sku_id: 71,
        vlm_mood: {
          summary: '따뜻한 다이닝룸입니다.',
          tags: ['내추럴'],
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
  assert.equal(requests.length, 1);
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
              object_index: 1,
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

test('edited objects are persisted with named normalized bbox coordinates', async (t) => {
  const { updateSceneObjects } = await loadTaggingApi(t);
  const originalFetch = globalThis.fetch;
  let request;
  globalThis.fetch = async (input, init) => {
    request = { init, input };
    return new Response(
      JSON.stringify({
        status: 'success',
        data: { object_count: 1, processing_status: 'DETECTED' },
        meta: { request_id: 'request-123' },
      }),
      { headers: { 'Content-Type': 'application/json' }, status: 200 },
    );
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  await updateSceneObjects('7', [
    {
      bbox: [100, 200, 800, 900],
      category: '의자',
      name: 'chair',
    },
  ]);

  assert.equal(request.input, '/tagging/scenes/7');
  assert.equal(request.init.method, 'POST');
  assert.deepEqual(JSON.parse(request.init.body), {
    objects: [
      {
        bbox: { xmax: 900, xmin: 200, ymax: 800, ymin: 100 },
        label: '의자',
      },
    ],
  });
});
