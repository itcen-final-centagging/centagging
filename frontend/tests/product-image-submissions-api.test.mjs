import assert from 'node:assert/strict';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { createServer } from 'vite';

const loadProductImageSubmissionApi = async (t) => {
  const server = await createServer({
    appType: 'custom',
    logLevel: 'silent',
    root: fileURLToPath(new URL('..', import.meta.url)),
    server: { middlewareMode: true },
  });
  t.after(() => server.close());
  return server.ssrLoadModule(
    '/src/features/productImageSubmissions/api/productImageSubmissions.ts',
  );
};

const apiSubmission = {
  final_sku_id: null,
  final_sku_image_id: null,
  image_type: 'MAIN',
  image_url: '/uploads/sku/submissions/chair.png',
  proposed_attributes: { color: 'walnut' },
  proposed_brand: 'Cen Home',
  proposed_category: '의자',
  proposed_price: 210000,
  proposed_product_name: '월넛 체어',
  proposed_sku_code: 'CHR-2042',
  proposed_space: '다이닝룸',
  proposed_sub_category: '다이닝 체어',
  reject_reason: null,
  requested_at: '2026-08-15T00:00:00Z',
  requested_by_name: '관리자',
  reviewed_at: null,
  reviewed_by_name: null,
  status: 'DRAFT',
  submission_id: 9,
  submitted_at: null,
  target_product_name: null,
  target_sku_code: null,
  target_type: 'NEW',
};

test('product image queue maps snake-case API data and sends the admin session', async (t) => {
  const { listProductImageSubmissions } =
    await loadProductImageSubmissionApi(t);
  const originalFetch = globalThis.fetch;
  let request;
  globalThis.fetch = async (input, init) => {
    request = { input, init };
    return new Response(
      JSON.stringify({
        status: 'success',
        data: { items: [apiSubmission] },
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

  const items = await listProductImageSubmissions(
    'centagging-poc-admin-session',
    'DRAFT',
  );

  assert.equal(request.input, '/product-image-submissions?status=DRAFT');
  assert.equal(
    new Headers(request.init.headers).get('Authorization'),
    'Bearer centagging-poc-admin-session',
  );
  assert.deepEqual(items[0], {
    finalSkuId: null,
    finalSkuImageId: null,
    imageType: 'MAIN',
    imageUrl: '/uploads/sku/submissions/chair.png',
    proposedAttributes: { color: 'walnut' },
    proposedBrand: 'Cen Home',
    proposedCategory: '의자',
    proposedPrice: 210000,
    proposedProductName: '월넛 체어',
    proposedSkuCode: 'CHR-2042',
    proposedSpace: '다이닝룸',
    proposedSubCategory: '다이닝 체어',
    rejectReason: null,
    requestedAt: '2026-08-15T00:00:00Z',
    requestedByName: '관리자',
    reviewedAt: null,
    reviewedByName: null,
    status: 'DRAFT',
    submissionId: 9,
    submittedAt: null,
    targetProductName: null,
    targetSkuCode: null,
    targetType: 'NEW',
  });
});

test('draft configuration uses the backend metadata contract', async (t) => {
  const { configureProductImageSubmission } =
    await loadProductImageSubmissionApi(t);
  const originalFetch = globalThis.fetch;
  let request;
  globalThis.fetch = async (input, init) => {
    request = { input, init };
    return new Response(
      JSON.stringify({
        status: 'success',
        data: apiSubmission,
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

  await configureProductImageSubmission('session-1', 9, {
    imageType: 'DETAIL',
    proposedAttributes: { material: 'wood' },
    proposedBrand: 'Cen Home',
    proposedCategory: '의자',
    proposedPrice: 210000,
    proposedProductName: '월넛 체어',
    proposedSkuCode: 'CHR-2042',
    proposedSpace: '다이닝룸',
    proposedSubCategory: '다이닝 체어',
    targetSkuCode: null,
    targetType: 'NEW',
  });

  assert.equal(request.input, '/product-image-submissions/9');
  assert.equal(request.init.method, 'PUT');
  assert.deepEqual(JSON.parse(request.init.body), {
    image_type: 'DETAIL',
    proposed_attributes: { material: 'wood' },
    proposed_brand: 'Cen Home',
    proposed_category: '의자',
    proposed_price: 210000,
    proposed_product_name: '월넛 체어',
    proposed_sku_code: 'CHR-2042',
    proposed_space: '다이닝룸',
    proposed_sub_category: '다이닝 체어',
    target_sku_code: null,
    target_type: 'NEW',
  });
});
