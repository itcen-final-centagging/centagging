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

test('analysis polls its AI job until detection succeeds', async (t) => {
  const { analyzeImage } = await loadTaggingApi(t);
  const originalFetch = globalThis.fetch;
  const originalSetTimeout = globalThis.setTimeout;
  const requests = [];
  let jobPollCount = 0;
  globalThis.setTimeout = (callback) => {
    callback();
    return 0;
  };
  globalThis.fetch = async (input) => {
    const url = String(input);
    requests.push(url);
    if (url === '/tagging') {
      return new Response(
        JSON.stringify({
          status: 'success',
          data: {
            job_id: 'job-123',
            scene_image_id: 42,
            status: 'PENDING',
          },
          meta: { request_id: 'request-123' },
        }),
        { headers: { 'Content-Type': 'application/json' }, status: 202 },
      );
    }

    jobPollCount += 1;
    const job =
      jobPollCount === 1
        ? {
            error_message: null,
            job_id: 'job-123',
            result_payload: null,
            scene_image_id: 42,
            status: 'RUNNING',
          }
        : {
            error_message: null,
            job_id: 'job-123',
            result_payload: {
              objects: [
                {
                  bbox_coord: { xmin: 200, ymin: 100, xmax: 800, ymax: 700 },
                  confidence: 0.9,
                  evidence: 'chair shape',
                  object_idx: 0,
                  category: 'chair',
                  sub_category: null,
                },
              ],
              scene_image_id: 42,
            },
            scene_image_id: 42,
            status: 'SUCCEEDED',
          };
    return new Response(
      JSON.stringify({
        status: 'success',
        data: job,
        meta: { request_id: 'request-123' },
      }),
      { headers: { 'Content-Type': 'application/json' }, status: 200 },
    );
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
    globalThis.setTimeout = originalSetTimeout;
  });

  const analysis = await analyzeImage(
    new Blob(['image'], { type: 'image/png' }),
  );

  assert.deepEqual(requests, [
    '/tagging',
    '/ai-jobs/job-123',
    '/ai-jobs/job-123',
  ]);
  assert.equal(analysis.analysisId, '42');
  assert.deepEqual(analysis.objects[0], {
    bbox: [100, 200, 700, 800],
    candidates: [],
    category: 'chair',
    confidence: 0.9,
    description: 'chair shape',
    id: '42-0',
    metadata: {
      attributes: {},
      category: 'chair',
      description: 'chair shape',
      keyFeatures: [],
      subCategory: null,
    },
    name: 'chair',
    objectIdx: 0,
    xaiAttrs: {},
  });
});

test('analysis exposes a failed AI job message', async (t) => {
  const { analyzeImage } = await loadTaggingApi(t);
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    if (String(input) === '/tagging') {
      return new Response(
        JSON.stringify({
          status: 'success',
          data: {
            job_id: 'job-456',
            scene_image_id: 42,
            status: 'PENDING',
          },
          meta: { request_id: 'request-123' },
        }),
        { headers: { 'Content-Type': 'application/json' }, status: 202 },
      );
    }
    return new Response(
      JSON.stringify({
        status: 'success',
        data: {
          error_message: '가구 탐지에 실패했습니다.',
          job_id: 'job-456',
          result_payload: null,
          scene_image_id: 42,
          status: 'FAILED',
        },
        meta: { request_id: 'request-123' },
      }),
      { headers: { 'Content-Type': 'application/json' }, status: 200 },
    );
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  await assert.rejects(
    analyzeImage(new Blob(['image'], { type: 'image/png' })),
    /가구 탐지에 실패했습니다/,
  );
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
              approval_status: 'REJECTED',
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
      approvalStatus: 'REJECTED',
      id: '91',
      imageName: 'scene.png',
      objectName: 'chair',
      productName: 'work chair',
      savedAt: '2026-08-11T00:00:00Z',
      sku: 'CHR-2041',
      tags: {
        category: '',
        color: '',
        materials: {},
        mood: '',
        styleTags: ['minimal'],
        subCategory: '',
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
        object: {
          bbox: [100, 200, 800, 900],
          metadata: {
            attributes: { has_backrest: 'yes' },
            subCategory: 'office chair',
          },
          objectIdx: 1,
          xaiAttrs: { material: 'mesh' },
        },
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
          materials: { material: 'mesh' },
          mood: 'A warm living room.',
          styleTags: ['modern'],
        },
      },
      {
        object: {
          bbox: [50, 60, 400, 500],
          metadata: {
            attributes: { leg_type: 'four legs' },
            subCategory: 'dining table',
          },
          objectIdx: 2,
          xaiAttrs: { material: 'oak' },
        },
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
          materials: { frame_material: 'steel', top_material: 'oak' },
          mood: 'A compact dining area.',
          styleTags: ['null', 'natural'],
        },
      },
      {
        object: {
          bbox: [10, 20, 30, 40],
          metadata: { attributes: {}, subCategory: 'bookcase' },
          objectIdx: 3,
        },
        objectIdx: 3,
        // 카탈로그 검색으로 직접 고른 SKU는 순위·유사도·XAI가 없습니다.
        selectedSku: {
          category: 'bookcase',
          color: null,
          matchRank: null,
          material: null,
          score: null,
          sku: 'BOOK-0001',
          skuId: 88,
          style: null,
          subCategory: 'bookcase',
          vlmMood: null,
          xaiResult: null,
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
        match_source: 'RECOMMEND',
        object_idx: 1,
        object_metadata: {
          attrs: {
            color: 'white',
            has_backrest: 'yes',
            material: 'mesh',
            style: 'modern',
          },
          bbox_coord: { xmax: 900, xmin: 200, ymax: 800, ymin: 100 },
          category: 'chair',
          object_idx: 1,
          sub_category: 'office chair',
        },
        similarity_score: 92,
        sku_id: 50,
        sku_image_id: null,
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
          xai_attrs: { material: 'mesh' },
        },
      },
      {
        match_rank: 1,
        match_source: 'RECOMMEND',
        object_idx: 2,
        object_metadata: {
          attrs: {
            color: 'brown',
            frame_material: 'steel',
            leg_type: 'four legs',
            style: 'natural',
            top_material: 'oak',
          },
          bbox_coord: { xmax: 500, xmin: 60, ymax: 400, ymin: 50 },
          category: 'table',
          object_idx: 2,
          sub_category: 'dining table',
        },
        similarity_score: 88,
        sku_id: 71,
        sku_image_id: null,
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
          xai_attrs: { material: 'oak' },
        },
      },
      {
        match_rank: null,
        match_source: 'SEARCH',
        object_idx: 3,
        object_metadata: {
          attrs: { color: '', material: '', style: '' },
          bbox_coord: { xmax: 40, xmin: 20, ymax: 30, ymin: 10 },
          category: 'bookcase',
          object_idx: 3,
          sub_category: 'bookcase',
        },
        similarity_score: null,
        sku_id: 88,
        sku_image_id: null,
        vlm_mood: { summary: '', tags: [] },
        // SEARCH 결과는 XAI 근거가 없으므로 null로 보내야 합니다(422 방지).
        xai_result: null,
      },
    ],
  });
  assert.equal(requests.length, 1);
});

test('recommendation polls its AI job and keeps its XAI result', async (t) => {
  const { fetchRecommendations } = await loadTaggingApi(t);
  const originalFetch = globalThis.fetch;
  const originalSetTimeout = globalThis.setTimeout;
  const requests = [];
  globalThis.setTimeout = (callback) => {
    callback();
    return 0;
  };
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    requests.push({ init, url });
    const data =
      url === '/tagging/scenes/7'
        ? { job_id: 'job-789', scene_image_id: 7, status: 'PENDING' }
        : {
            error_message: null,
            job_id: 'job-789',
            result_payload: {
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
                        xai_attrs: {
                          color: 'brown',
                        },
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
            scene_image_id: 7,
            status: 'SUCCEEDED',
          };
    return new Response(
      JSON.stringify({
        status: 'success',
        data,
        meta: { request_id: 'request-123' },
      }),
      { headers: { 'Content-Type': 'application/json' }, status: 200 },
    );
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
    globalThis.setTimeout = originalSetTimeout;
  });

  const [candidate] = await fetchRecommendations('7', 1, [
    {
      bbox: [100, 200, 700, 800],
      category: 'chair',
      name: 'chair',
      objectIdx: 1,
    },
  ]);

  assert.deepEqual(
    requests.map((request) => request.url),
    ['/tagging/scenes/7', '/ai-jobs/job-789'],
  );
  assert.equal(requests[0].init.method, 'POST');
  assert.deepEqual(JSON.parse(requests[0].init.body), {
    objects: [
      {
        bbox_coord: { xmax: 800, xmin: 200, ymax: 700, ymin: 100 },
        category: 'chair',
        object_idx: 1,
      },
    ],
  });
  assert.equal(candidate.matchRank, 1);
  assert.equal(candidate.score, 92);
  assert.equal(
    candidate.xaiResult.summary,
    'The structure and color are similar.',
  );
  assert.deepEqual(candidate.xaiResult.xaiAttrs, { color: 'brown' });
});
