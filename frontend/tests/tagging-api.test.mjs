import assert from 'node:assert/strict';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
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

const loadXaiFallbackNotice = async (t) => {
  const server = await createServer({
    appType: 'custom',
    logLevel: 'silent',
    root: fileURLToPath(new URL('..', import.meta.url)),
    server: { middlewareMode: true },
  });
  t.after(() => server.close());
  return server.ssrLoadModule(
    '/src/features/tagging/components/XaiFallbackNotice.tsx',
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

test('rate-limited XAI is explained as an embedding fallback', async (t) => {
  const { XaiFallbackNotice } = await loadXaiFallbackNotice(t);

  const markup = renderToStaticMarkup(
    React.createElement(XaiFallbackNotice, {
      reason: 'RATE_LIMITED',
      status: 'FALLBACK',
    }),
  );

  assert.match(markup, /Gemini 요청 한도를 초과/);
  assert.match(markup, /이미지 유사도 기준/);
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
    objectIndex: 1,
    sceneImageId: '7',
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
      xaiStatus: 'COMPLETED',
      xaiFallbackReason: null,
    },
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
        xai_status: 'COMPLETED',
        xai_fallback_reason: null,
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
                  xai_status: 'COMPLETED',
                  xai_fallback_reason: null,
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
      xaiFallbackReason: candidate.xaiFallbackReason,
      xaiResult: candidate.xaiResult,
      xaiStatus: candidate.xaiStatus,
    },
    {
      matchRank: 1,
      score: 92,
      vlmMood: {
        summary: 'A warm living room.',
        tags: ['natural'],
      },
      xaiFallbackReason: null,
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
      xaiStatus: 'COMPLETED',
    },
  );
});
