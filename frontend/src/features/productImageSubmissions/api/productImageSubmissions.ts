import { createAuthorizationHeaders } from '@/features/auth/api/auth';
import { requestJson, type ApiSuccessResponse } from '@/lib/api-request';

export type ProductImageSubmissionStatus =
  'DRAFT' | 'PENDING' | 'APPROVED' | 'REJECTED';
export type ProductImageTargetType = 'EXISTING' | 'NEW';
export type ProductImageType = 'MAIN' | 'ANGLE' | 'DETAIL' | 'STYLING';

export type ProductImageSubmission = {
  finalSkuId: number | null;
  finalSkuImageId: number | null;
  imageType: ProductImageType;
  imageUrl: string;
  proposedAttributes: Record<string, unknown>;
  proposedBrand: string | null;
  proposedCategory: string | null;
  proposedPrice: number | null;
  proposedProductName: string | null;
  proposedSkuCode: string | null;
  proposedSubCategory: string | null;
  rejectReason: string | null;
  requestedAt: string;
  requestedByName: string;
  reviewedAt: string | null;
  reviewedByName: string | null;
  status: ProductImageSubmissionStatus;
  submissionId: number;
  submittedAt: string | null;
  targetBrand: string | null;
  targetCategory: string | null;
  targetMainImageUrl: string | null;
  targetPrice: number | null;
  targetProductName: string | null;
  targetSkuCode: string | null;
  targetSubCategory: string | null;
  targetType: ProductImageTargetType | null;
};

export type ProductImageSubmissionDraft = {
  imageType: ProductImageType;
  proposedAttributes: Record<string, unknown>;
  proposedBrand: string | null;
  proposedCategory: string | null;
  proposedPrice: number | null;
  proposedProductName: string | null;
  proposedSkuCode: string | null;
  proposedSubCategory: string | null;
  targetSkuCode: string | null;
  targetType: ProductImageTargetType;
};

type ApiSubmission = {
  final_sku_id: number | null;
  final_sku_image_id: number | null;
  image_type: ProductImageType;
  image_url: string;
  proposed_attributes?: Record<string, unknown>;
  proposed_brand?: string | null;
  proposed_category?: string | null;
  proposed_price?: number | null;
  proposed_product_name: string | null;
  proposed_sku_code: string | null;
  proposed_sub_category?: string | null;
  reject_reason: string | null;
  requested_at: string;
  requested_by_name: string;
  reviewed_at: string | null;
  reviewed_by_name: string | null;
  status: ProductImageSubmissionStatus;
  submission_id: number;
  submitted_at: string | null;
  target_brand?: string | null;
  target_category?: string | null;
  target_main_image_url: string | null;
  target_price?: number | null;
  target_product_name: string | null;
  target_sku_code: string | null;
  target_sub_category?: string | null;
  target_type: ProductImageTargetType | null;
};

type ApiSubmissionListResponse = ApiSuccessResponse<{
  items: ApiSubmission[];
}>;

type ApiSubmissionResponse = ApiSuccessResponse<ApiSubmission>;

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(
    /\/$/,
    '',
  ) ?? '';

const toAssetUrl = (imageUrl: string): string => {
  if (/^https?:\/\//.test(imageUrl)) return imageUrl;
  return `${API_BASE_URL}${imageUrl.startsWith('/') ? '' : '/'}${imageUrl}`;
};

const toOptionalAssetUrl = (imageUrl: string | null): string | null =>
  imageUrl ? toAssetUrl(imageUrl) : null;

const toSubmission = (item: ApiSubmission): ProductImageSubmission => ({
  finalSkuId: item.final_sku_id,
  finalSkuImageId: item.final_sku_image_id,
  imageType: item.image_type,
  imageUrl: toAssetUrl(item.image_url),
  proposedAttributes: item.proposed_attributes ?? {},
  proposedBrand: item.proposed_brand ?? null,
  proposedCategory: item.proposed_category ?? null,
  proposedPrice: item.proposed_price ?? null,
  proposedProductName: item.proposed_product_name,
  proposedSkuCode: item.proposed_sku_code,
  proposedSubCategory: item.proposed_sub_category ?? null,
  rejectReason: item.reject_reason,
  requestedAt: item.requested_at,
  requestedByName: item.requested_by_name,
  reviewedAt: item.reviewed_at,
  reviewedByName: item.reviewed_by_name,
  status: item.status,
  submissionId: item.submission_id,
  submittedAt: item.submitted_at,
  targetBrand: item.target_brand ?? null,
  targetCategory: item.target_category ?? null,
  targetMainImageUrl: toOptionalAssetUrl(item.target_main_image_url),
  targetPrice: item.target_price ?? null,
  targetProductName: item.target_product_name,
  targetSkuCode: item.target_sku_code,
  targetSubCategory: item.target_sub_category ?? null,
  targetType: item.target_type,
});

const toRequestPayload = (draft: ProductImageSubmissionDraft) => ({
  image_type: draft.imageType,
  proposed_attributes: draft.proposedAttributes,
  proposed_brand: draft.proposedBrand || null,
  proposed_category: draft.proposedCategory || null,
  proposed_price: draft.proposedPrice,
  proposed_product_name: draft.proposedProductName || null,
  proposed_sku_code: draft.proposedSkuCode || null,
  proposed_sub_category: draft.proposedSubCategory || null,
  target_sku_code: draft.targetSkuCode || null,
  target_type: draft.targetType,
});

/** 여러 제품 파일을 한 번에 독립적인 승인 초안으로 업로드합니다. */
export const uploadProductImageDrafts = async (
  session: string,
  files: File[],
): Promise<ProductImageSubmission[]> => {
  const body = new FormData();
  files.forEach((file) => body.append('images', file));
  const response = await requestJson<ApiSubmissionListResponse>(
    `${API_BASE_URL}/product-image-submissions`,
    {
      body,
      headers: createAuthorizationHeaders(session),
      method: 'POST',
    },
  );
  return response.data.items.map(toSubmission);
};

/** 역할과 상태 범위에 맞는 제품 이미지 등록 큐를 조회합니다. */
export const listProductImageSubmissions = async (
  session: string,
  status: ProductImageSubmissionStatus | 'ALL' = 'ALL',
): Promise<ProductImageSubmission[]> => {
  const response = await requestJson<ApiSubmissionListResponse>(
    `${API_BASE_URL}/product-image-submissions?status=${status}`,
    { headers: createAuthorizationHeaders(session) },
  );
  return response.data.items.map(toSubmission);
};

export const getProductImageSubmission = async (
  session: string,
  submissionId: number,
): Promise<ProductImageSubmission> => {
  const response = await requestJson<ApiSubmissionResponse>(
    `${API_BASE_URL}/product-image-submissions/${encodeURIComponent(submissionId)}`,
    { headers: createAuthorizationHeaders(session) },
  );
  return toSubmission(response.data);
};

/** 초안 한 건에 기존 SKU 연결 또는 신규 SKU 메타데이터를 저장합니다. */
export const configureProductImageSubmission = async (
  session: string,
  submissionId: number,
  draft: ProductImageSubmissionDraft,
): Promise<ProductImageSubmission> => {
  const response = await requestJson<ApiSubmissionResponse>(
    `${API_BASE_URL}/product-image-submissions/${encodeURIComponent(submissionId)}`,
    {
      body: JSON.stringify(toRequestPayload(draft)),
      headers: createAuthorizationHeaders(session, {
        'Content-Type': 'application/json',
      }),
      method: 'PUT',
    },
  );
  return toSubmission(response.data);
};

export const submitProductImageSubmission = async (
  session: string,
  submissionId: number,
): Promise<ProductImageSubmission> => {
  const response = await requestJson<ApiSubmissionResponse>(
    `${API_BASE_URL}/product-image-submissions/${encodeURIComponent(submissionId)}/submit`,
    {
      headers: createAuthorizationHeaders(session),
      method: 'POST',
    },
  );
  return toSubmission(response.data);
};

export const approveProductImageSubmission = async (
  session: string,
  submissionId: number,
): Promise<ProductImageSubmission> => {
  const response = await requestJson<ApiSubmissionResponse>(
    `${API_BASE_URL}/product-image-submissions/${encodeURIComponent(submissionId)}/approve`,
    {
      headers: createAuthorizationHeaders(session),
      method: 'POST',
    },
  );
  return toSubmission(response.data);
};

export const rejectProductImageSubmission = async (
  session: string,
  submissionId: number,
  rejectReason: string,
): Promise<ProductImageSubmission> => {
  const response = await requestJson<ApiSubmissionResponse>(
    `${API_BASE_URL}/product-image-submissions/${encodeURIComponent(submissionId)}/reject`,
    {
      body: JSON.stringify({ reject_reason: rejectReason }),
      headers: createAuthorizationHeaders(session, {
        'Content-Type': 'application/json',
      }),
      method: 'POST',
    },
  );
  return toSubmission(response.data);
};
