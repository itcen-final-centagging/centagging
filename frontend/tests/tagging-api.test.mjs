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

test('selected recommendation is sent to the scene PUT endpoint', async (t) => {
  const { saveTaggingReview } = await loadTaggingApi(t);
  const originalFetch = globalThis.fetch;
  let request;
  globalThis.fetch = async (input, init) => {
    request = { init, input };
    return new Response(
      JSON.stringify({
        id: '91',
        image_name: 'scene.png',
        object_name: 'chair',
        product_name: 'work chair',
        saved_at: '2026-08-11T00:00:00Z',
        sku: 'CHR-2041',
        tags: {
          category: 'chair',
          color: 'white',
          material: 'mesh',
          mood: 'minimal',
          style_tags: [],
        },
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
    },
  });

  assert.equal(request.input, '/tagging/scenes/7');
  assert.equal(request.init.method, 'PUT');
  assert.deepEqual(JSON.parse(request.init.body), {
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
    ],
  });
});

test('recommendation keeps its rank, full XAI, and VLM mood', async (t) => {
  const { fetchRecommendations } = await loadTaggingApi(t);
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
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
