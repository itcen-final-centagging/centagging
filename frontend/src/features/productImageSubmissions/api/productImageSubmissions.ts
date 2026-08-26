import { createAuthorizationHeaders } from '@/features/auth/api/auth';
import type {
  SkuCandidate,
  XaiCriterion,
  VlmMood,
} from '@/features/tagging/types';
import { requestJson, type ApiSuccessResponse } from '@/lib/api-request';

export type ProductImageSubmissionStatus =
  'DRAFT' | 'PENDING' | 'APPROVED' | 'REJECTED';
export type ProductImageTargetType = 'EXISTING' | 'NEW';
export type ProductImageType = 'MAIN' | 'ANGLE' | 'DETAIL' | 'STYLING';

export type ProductImageSubmissionCandidateSku = {
  attributes: Record<string, unknown>;
  brand: string | null;
  category: string | null;
  imageUrl: string | null;
  matchRank: number;
  price: number | null;
  productName: string;
  similarityScore: number | null;
  skuCode: string;
  skuId: number;
  subCategory: string | null;
  viaSearch: boolean;
  xaiCommon: string;
  xaiDifference: string;
};

export type ProductImageSubmission = {
  candidates: ProductImageSubmissionCandidateSku[];
  finalSkuId: number | null;
  finalSkuImageId: number | null;
  imageType: ProductImageType;
  imageUrl: string;
  jobId: string | null;
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
  targetAttributes: Record<string, unknown>;
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

type ApiSubmissionCandidate = {
  attributes: Record<string, unknown>;
  brand: string | null;
  category: string | null;
  image_url: string | null;
  match_rank: number;
  price: number | null;
  product_name: string;
  similarity_score: number | null;
  sku_code: string;
  sku_id: number;
  sub_category: string | null;
  via_search: boolean;
  xai_common: string;
  xai_difference: string;
};

type ApiSubmission = {
  candidates?: ApiSubmissionCandidate[];
  final_sku_id: number | null;
  final_sku_image_id: number | null;
  image_type: ProductImageType;
  image_url: string;
  job_id?: string | null;
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
  target_attributes?: Record<string, unknown>;
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

const toSubmissionCandidate = (
  candidate: ApiSubmissionCandidate,
): ProductImageSubmissionCandidateSku => ({
  attributes: candidate.attributes ?? {},
  brand: candidate.brand,
  category: candidate.category,
  imageUrl: toOptionalAssetUrl(candidate.image_url),
  matchRank: candidate.match_rank,
  price: candidate.price,
  productName: candidate.product_name,
  similarityScore: candidate.similarity_score,
  skuCode: candidate.sku_code,
  skuId: candidate.sku_id,
  subCategory: candidate.sub_category,
  viaSearch: candidate.via_search,
  xaiCommon: candidate.xai_common,
  xaiDifference: candidate.xai_difference,
});

const toSubmission = (item: ApiSubmission): ProductImageSubmission => ({
  candidates: (item.candidates ?? []).map(toSubmissionCandidate),
  finalSkuId: item.final_sku_id,
  finalSkuImageId: item.final_sku_image_id,
  imageType: item.image_type,
  imageUrl: toAssetUrl(item.image_url),
  jobId: item.job_id ?? null,
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
  targetAttributes: item.target_attributes ?? {},
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

export type ProductImageSubmissionJobStatus =
  'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED';

export type ProductImageSubmissionJobResult = {
  proposedAttributes: Record<string, unknown>;
  proposedCategory: string | null;
  proposedSubCategory: string | null;
  skuCandidates: SkuCandidate[];
};

export type ProductImageSubmissionJob = {
  errorMessage: string | null;
  jobId: string;
  result: ProductImageSubmissionJobResult | null;
  status: ProductImageSubmissionJobStatus;
};

type ApiCandidate = {
  attrs: Record<string, unknown>;
  category: string;
  matched_sku_image: {
    image_type: 'MAIN' | 'ANGLE';
    image_url: string;
    sku_image_id: number;
  };
  product_name: string;
  similarity_score: number;
  sku_code: string;
  sku_id: number;
  sub_category: string;
  vlm_mood?: VlmMood;
  xai_result: {
    common?: string;
    criteria: XaiCriterion[];
    difference?: string;
    match_rate?: number | null;
    summary: string;
  };
};

type ApiJobResultPayload = {
  proposed_attributes?: Record<string, unknown>;
  proposed_category: string | null;
  proposed_sub_category: string | null;
  sku_candidates?: ApiCandidate[];
};

type ApiSubmissionJob = {
  error_message: string | null;
  job_id: string;
  result_payload: ApiJobResultPayload | null;
  status: ProductImageSubmissionJobStatus;
  submission_id: number;
};

type ApiSubmissionJobResponse = ApiSuccessResponse<ApiSubmissionJob>;

/** 후보 카드의 대체 썸네일에 쓸 대략적인 가구 종류를 분류합니다. */
const toJobCandidateKind = (
  category: string | null,
  subCategory: string | null,
): SkuCandidate['kind'] => {
  const value = `${category ?? ''} ${subCategory ?? ''}`.toLowerCase();
  if (value.includes('sofa') || value.includes('소파')) return 'sofa';
  if (value.includes('table') || value.includes('테이블')) return 'table';
  if (value.includes('lamp') || value.includes('조명')) return 'lamp';
  if (value.includes('chair') || value.includes('의자')) return 'chair';
  if (value.includes('cabinet') || value.includes('수납')) return 'cabinet';
  return null;
};

const toJobCandidateText = (value: unknown): string | null =>
  typeof value === 'string' && value.length > 0 ? value : null;

/** 추천 작업 결과의 SKU 후보 1건을 후보 카드가 쓰는 형태로 변환합니다. */
const toJobCandidate = (
  candidate: ApiCandidate,
  candidateIndex: number,
): SkuCandidate => ({
  attrs: candidate.attrs ?? {},
  category: candidate.category,
  color: toJobCandidateText(candidate.attrs.color),
  imageUrl: toAssetUrl(candidate.matched_sku_image.image_url),
  kind: toJobCandidateKind(candidate.category, candidate.sub_category),
  material: toJobCandidateText(candidate.attrs.material),
  matchRank: candidateIndex + 1,
  metadataScore: candidate.xai_result.match_rate ?? candidate.similarity_score,
  name: candidate.product_name,
  rubric: null,
  score: candidate.similarity_score,
  size: toJobCandidateText(candidate.attrs.size),
  sku: candidate.sku_code,
  skuId: candidate.sku_id,
  skuImageId: candidate.matched_sku_image.sku_image_id,
  subCategory: candidate.sub_category,
  vectorScore: candidate.similarity_score / 100,
  vlmMood: candidate.vlm_mood ?? null,
  xaiReason: toJobCandidateText(candidate.xai_result.summary),
  xaiResult: {
    common: candidate.xai_result.common,
    criteria: candidate.xai_result.criteria,
    difference: candidate.xai_result.difference,
    matchRate: candidate.xai_result.match_rate ?? candidate.similarity_score,
    summary: candidate.xai_result.summary,
  },
});

const toJobResult = (
  payload: ApiJobResultPayload,
): ProductImageSubmissionJobResult => ({
  proposedAttributes: payload.proposed_attributes ?? {},
  proposedCategory: payload.proposed_category,
  proposedSubCategory: payload.proposed_sub_category,
  skuCandidates: (payload.sku_candidates ?? []).map(toJobCandidate),
});

/** 업로드 직후 접수한 제품 이미지 추천 작업의 현재 상태를 조회합니다. */
export const getProductImageSubmissionJob = async (
  session: string,
  jobId: string,
): Promise<ProductImageSubmissionJob> => {
  const response = await requestJson<ApiSubmissionJobResponse>(
    `${API_BASE_URL}/product-image-submission-jobs/${encodeURIComponent(jobId)}`,
    { headers: createAuthorizationHeaders(session) },
  );
  const job = response.data;
  return {
    errorMessage: job.error_message,
    jobId: job.job_id,
    result: job.result_payload ? toJobResult(job.result_payload) : null,
    status: job.status,
  };
};
