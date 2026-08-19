import assert from 'node:assert/strict';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { createServer } from 'vite';

const loadRubric = async (t) => {
  const server = await createServer({
    appType: 'custom',
    logLevel: 'silent',
    root: fileURLToPath(new URL('..', import.meta.url)),
    server: { middlewareMode: true },
  });
  t.after(() => server.close());
  return server.ssrLoadModule('/src/features/tagging/utils/rubric.ts');
};

test('maps XAI criteria before the legacy rubric fallback', async (t) => {
  const { getRubricScores, getRubricTotal } = await loadRubric(t);
  const candidate = {
    rubric: {
      breakdown: { color: 1, context: 1, detail: 1, structure: 1 },
      status: 'Matched',
      totalScore: 4,
      xaiReason: 'legacy result',
    },
    score: 91,
    xaiResult: {
      criteria: [
        { comment: 'structure', label: '구조', score: 30 },
        { comment: 'color', label: 'COLOR', score: 25 },
        { comment: 'detail', label: 'detail', score: 18 },
        { comment: 'context', label: '맥락', score: 18 },
      ],
      summary: 'XAI result',
    },
  };

  const scores = getRubricScores(candidate);

  assert.deepEqual(
    scores.map(({ key, score }) => [key, score]),
    [
      ['structure', 30],
      ['color', 25],
      ['detail', 18],
      ['context', 18],
    ],
  );
  assert.equal(getRubricTotal(candidate, scores), 91);
});

test('uses the legacy rubric when XAI criteria are unavailable', async (t) => {
  const { getRubricScores, getRubricTotal } = await loadRubric(t);
  const candidate = {
    rubric: {
      breakdown: { color: 28, context: 19, detail: 17, structure: 29 },
      status: 'Matched',
      totalScore: 93,
      xaiReason: 'legacy result',
    },
    score: null,
    xaiResult: null,
  };

  const scores = getRubricScores(candidate);

  assert.deepEqual(
    scores.map(({ score }) => score),
    [29, 28, 17, 19],
  );
  assert.equal(getRubricTotal(candidate, scores), 93);
});
