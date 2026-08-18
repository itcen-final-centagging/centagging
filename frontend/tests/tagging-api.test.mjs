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
              detections: [
                {
                  box_2d: [100, 200, 700, 800],
                  confidence: 90,
                  evidence: 'chair shape',
                  label: 'chair',
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
    confidence: 90,
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
    objectIndex: 0,
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
    if (init?.method === 'PUT') {
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
        objectIndex: 1,
        selectedSku: {
          matchRank: 2,
          score: 92,
          sku: 'CHR-2041',
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
        objectIndex: 2,
        selectedSku: {
          matchRank: 1,
          score: 88,
          sku: 'TBL-1007',
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
      },
    ],
    sceneImageId: '7',
  });
  const history = await fetchTaggingHistory();

  assert.equal(requests[0].input, '/tagging/scenes/7');
  assert.equal(requests[0].init.method, 'PUT');
  assert.deepEqual(JSON.parse(requests[0].init.body), {
    matching: [
      {
        match_rank: 2,
        object_index: 1,
        similarity_score: 92,
        sku_code: 'CHR-2041',
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
        similarity_score: 88,
        sku_code: 'TBL-1007',
        vlm_mood: {
          summary: 'A compact dining area.',
          tags: ['modern'],
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
