import assert from 'node:assert/strict';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { createServer } from 'vite';

const loadAuthApi = async (t) => {
  const server = await createServer({
    appType: 'custom',
    logLevel: 'silent',
    root: fileURLToPath(new URL('..', import.meta.url)),
    server: { middlewareMode: true },
  });
  t.after(() => server.close());
  return server.ssrLoadModule('/src/features/auth/api/auth.ts');
};

const apiUser = {
  login_id: 'admin',
  role: 'ADMIN',
  session: 'centagging-poc-admin-session',
  user_id: 2,
  user_name: '관리자',
};

test('login sends credentials and returns the authenticated user', async (t) => {
  const { login } = await loadAuthApi(t);
  const originalFetch = globalThis.fetch;
  let request;
  globalThis.fetch = async (input, init) => {
    request = { input, init };
    return new Response(JSON.stringify(apiUser), {
      headers: { 'Content-Type': 'application/json' },
      status: 200,
    });
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  const user = await login({ loginId: 'admin', password: '1234' });

  assert.equal(request.input, '/auth/login');
  assert.equal(request.init.method, 'POST');
  assert.equal(request.init.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(request.init.body), {
    login_id: 'admin',
    password: '1234',
  });
  assert.deepEqual(user, {
    loginId: 'admin',
    role: 'ADMIN',
    session: 'centagging-poc-admin-session',
    userId: 2,
    userName: '관리자',
  });
});

test('current user lookup sends the stored session as a Bearer token', async (t) => {
  const { getCurrentUser } = await loadAuthApi(t);
  const originalFetch = globalThis.fetch;
  let request;
  globalThis.fetch = async (input, init) => {
    request = { input, init };
    return new Response(JSON.stringify(apiUser), {
      headers: { 'Content-Type': 'application/json' },
      status: 200,
    });
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  await getCurrentUser('centagging-poc-admin-session');

  assert.equal(request.input, '/auth/me');
  assert.equal(request.init.method, 'GET');
  assert.equal(
    new Headers(request.init.headers).get('Authorization'),
    'Bearer centagging-poc-admin-session',
  );
});

test('common API error exposes its code, message, and request ID', async (t) => {
  const { ApiRequestError, login } = await loadAuthApi(t);
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        status: 'error',
        error: {
          code: 'AUTH_CREDENTIALS_INVALID',
          message: '아이디 또는 비밀번호가 올바르지 않습니다.',
          details: [],
        },
        meta: { request_id: 'request-123' },
      }),
      { headers: { 'Content-Type': 'application/json' }, status: 401 },
    );
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  await assert.rejects(
    () => login({ loginId: 'user', password: 'wrong' }),
    (error) =>
      error instanceof ApiRequestError &&
      error.code === 'AUTH_CREDENTIALS_INVALID' &&
      error.message === '아이디 또는 비밀번호가 올바르지 않습니다.' &&
      error.requestId === 'request-123',
  );
});
