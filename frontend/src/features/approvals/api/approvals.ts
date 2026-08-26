import { createAuthorizationHeaders } from '@/features/auth/api/auth';
import type { XaiCriterion } from '@/features/tagging/types';
import { requestJson, type ApiSuccessResponse } from '@/lib/api-request';

export type ApprovalStatus = 'PENDING' | 'ACTIVE' | 'REJECTED';

export type ApprovalListItem = {
  category: string | null;
  objectIdx: number;
  originName: string;
  productName: string;
  requestId: number;
  requestedAt: string;
  requestedByName: string | null;
  reviewedAt: string | null;
  reviewedByName: string | null;
  sceneImageId: number;
  sceneImageUrl: string;
  similarityScore: number | null;
  skuCode: string;
  status: ApprovalStatus;
};

export type ApprovalCandidateSku = {
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
};

export type ApprovalDetail = {
  actions: {
    canConfirm: boolean;
    canReject: boolean;
  };
  candidates: ApprovalCandidateSku[];
  object: {
    attrs: Record<string, unknown>;
    bbox: { xmax: number; xmin: number; ymax: number; ymin: number } | null;
    category: string | null;
    objectIdx: number;
    subCategory: string | null;
  };
  rejectReason: string | null;
  requestId: number;
  requestedAt: string;
  requestedByName: string | null;
  sceneImage: {
    imageUrl: string;
    originName: string;
    sceneImageId: number;
  };
  similarityScore: number | null;
  sku: {
    attributes: Record<string, unknown>;
    brand: string | null;
    category: string | null;
    imageUrl: string | null;
    price: number | null;
    productName: string;
    skuCode: string;
    skuId: number;
    subCategory: string | null;
  };
  status: ApprovalStatus;
  xaiResult: {
    common: string;
    criteria: XaiCriterion[];
    difference: string;
    summary: string;
  } | null;
};

type ApprovalListResponse = ApiSuccessResponse<{
  items: ApprovalListItem[];
}>;

type ApprovalDetailResponse = ApiSuccessResponse<ApprovalDetail>;

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(
    /\/$/,
    '',
  ) ?? '';

const authorization = (session: string): Headers =>
  createAuthorizationHeaders(session);

export const listApprovals = async (
  session: string,
  status: ApprovalStatus | 'ALL' = 'PENDING',
): Promise<ApprovalListItem[]> => {
  const response = await requestJson<ApprovalListResponse>(
    `${API_BASE_URL}/approvals?status=${status}`,
    { headers: authorization(session) },
  );
  return response.data.items;
};

export const getApprovalDetail = async (
  session: string,
  requestId: number,
): Promise<ApprovalDetail> =>
  requestJson<ApprovalDetailResponse>(
    `${API_BASE_URL}/approvals/${encodeURIComponent(requestId)}`,
    { headers: authorization(session) },
  ).then((response) => response.data);

export const confirmApproval = async (
  session: string,
  requestId: number,
): Promise<void> => {
  await requestJson<ApiSuccessResponse<unknown>>(
    `${API_BASE_URL}/approvals/${encodeURIComponent(requestId)}/confirm`,
    {
      headers: authorization(session),
      method: 'POST',
    },
  );
};

export const rejectApproval = async (
  session: string,
  requestId: number,
  rejectReason: string,
): Promise<void> => {
  await requestJson<ApiSuccessResponse<unknown>>(
    `${API_BASE_URL}/approvals/${encodeURIComponent(requestId)}/reject`,
    {
      body: JSON.stringify({ rejectReason }),
      headers: createAuthorizationHeaders(session, {
        'Content-Type': 'application/json',
      }),
      method: 'POST',
    },
  );
};
