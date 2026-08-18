import assert from 'node:assert/strict';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { createServer } from 'vite';

const loadApprovalApi = async (t) => {
  const server = await createServer({
    appType: 'custom',
    logLevel: 'silent',
    root: fileURLToPath(new URL('..', import.meta.url)),
    server: { middlewareMode: true },
  });
  t.after(() => server.close());
  return server.ssrLoadModule('/src/features/approvals/api/approvals.ts');
};

test('approval requests send the logged-in session and API contract', async (t) => {
  const { confirmApproval, getApprovalDetail, listApprovals, rejectApproval } =
    await loadApprovalApi(t);
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (input, init) => {
    requests.push({ init, input });
    const url = String(input);
    if (url.endsWith('/approvals?status=PENDING')) {
      return new Response(
        JSON.stringify({
          status: 'success',
          data: { items: [] },
          meta: { request_id: 'request-123' },
        }),
        {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        },
      );
    }
    if (url.endsWith('/approvals/9')) {
      return new Response(
        JSON.stringify({
          status: 'success',
          data: { requestId: 9 },
          meta: { request_id: 'request-123' },
        }),
        {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        },
      );
    }
    return new Response(
      JSON.stringify({
        status: 'success',
        data: { requestId: 9, status: 'ACTIVE' },
        meta: { request_id: 'request-123' },
      }),
      {
        headers: { 'Content-Type': 'application/json' },
        status: 200,
      },
    );
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  await listApprovals('session-token');
  await getApprovalDetail('session-token', 9);
  await confirmApproval('session-token', 9);
  await rejectApproval('session-token', 9, '상품 이미지가 아닙니다.');

  assert.deepEqual(
    requests.map(({ input }) => input),
    [
      '/approvals?status=PENDING',
      '/approvals/9',
      '/approvals/9/confirm',
      '/approvals/9/reject',
    ],
  );
  for (const { init } of requests) {
    assert.equal(init.headers.get('Authorization'), 'Bearer session-token');
  }
  assert.equal(requests[2].init.method, 'POST');
  assert.equal(requests[3].init.method, 'POST');
  assert.equal(
    requests[3].init.body,
    JSON.stringify({ rejectReason: '상품 이미지가 아닙니다.' }),
  );
});
