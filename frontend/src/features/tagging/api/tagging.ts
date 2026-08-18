import { requestJson, type ApiSuccessResponse } from '../../../lib/api-request';

import type {
  FurnitureObject,
  SkuCandidate,
  TaggingHistory,
  TaggingValues,
  VlmMood,
  XaiResult,
} from '../types';

type ApiBoundingBox = {
  xmin: number;
  ymin: number;
  xmax: number;
  ymax: number;
};

type DevDetection = {
  object_idx: number;
  category: string;
  sub_category: string;
  bbox_coord: ApiBoundingBox;
  confidence: number | null;
  evidence: string;
  label: string;
};

type DevUploadResponse = {
  scene_image: {
    scene_image_id: number;
    image_url: string;
    origin_name: string;
    mime_type: string;
    file_size: number;
    analysis_status: string;
    analysis_error: string | null;
    width_px: number;
    height_px: number;
    created_at: string;
  };
  object_count: number;
  objects: DevDetection[];
};

type DevCandidate = {
  sku_id: number;
  attrs: Record<string, unknown>;
  category: string | null;
  matched_sku_image: {
    image_url: string;
    sku_image_id: number;
  };
  product_name: string;
  similarity_score: number;
  sku_code: string;
  sub_category: string | null;
  xai_result: XaiResult & { vlm_mood: VlmMood };
};

type DevRecommendationData = {
  objects: Array<{
    object_idx: number;
    sku_candidates: DevCandidate[];
  }>;
};

type EditedSceneObject = Pick<FurnitureObject, 'bbox' | 'category' | 'name'>;

type ApiSkuSearchItem = {
  brand: string | null;
  category: string | null;
  image_url: string | null;
  price: number | null;
  product_name: string;
  similarity_score: number;
  sku_code: string;
  sub_category: string | null;
};

type SkuSearchResponseData = { skus: ApiSkuSearchItem[] };

type ApiHistoryListItem = {
  result_id: number;
  sku_code: string;
  product_name: string;
  object_name: string | null;
  similarity_score: number | null;
  created_by: string;
  created_at: string;
  style_tags: string[];
  scene_image: {
    image_url: string;
    origin_name: string;
    bbox: {
      xmin: number;
      ymin: number;
      xmax: number;
      ymax: number;
    };
  };
};

type ApiHistoryListData = {
  items: ApiHistoryListItem[];
};

export type TaggingAnalysis = {
  analysisId: string;
  mode: 'live' | 'mock' | null;
  objects: FurnitureObject[];
};

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(
    /\/$/,
    '',
  ) ?? '';

const toBbox = (bbox: ApiBoundingBox): [number, number, number, number] => [
  bbox.ymin,
  bbox.xmin,
  bbox.ymax,
  bbox.xmax,
];

const nullableText = (value: unknown): string | null =>
  typeof value === 'string' && value.length > 0 ? value : null;

const NULL_TAG_VALUE = 'null';

const reviewedText = (
  value: string | undefined,
  fallback: string | null | undefined,
): string =>
  value && value !== NULL_TAG_VALUE ? value : (fallback ?? '');

const reviewedTags = (tags: string[] | undefined): string[] | undefined =>
  tags?.filter((tag) => tag !== NULL_TAG_VALUE);

const resolveAssetUrl = (value: unknown): string | null => {
  const path = nullableText(value);
  if (!path || /^https?:\/\//.test(path)) return path;
  const separator = path.startsWith('/') ? '' : '/';
  return `${API_BASE_URL}${separator}${path}`;
};

const toKind = (category: string | null, subCategory: string | null) => {
  const value = `${category ?? ''} ${subCategory ?? ''}`.toLowerCase();
  if (value.includes('sofa') || value.includes('소파')) return 'sofa' as const;
  if (value.includes('table') || value.includes('테이블'))
    return 'table' as const;
  if (value.includes('lamp') || value.includes('조명')) return 'lamp' as const;
  if (value.includes('chair') || value.includes('의자'))
    return 'chair' as const;
  if (value.includes('cabinet') || value.includes('수납'))
    return 'cabinet' as const;
  return null;
};

const toDevCandidate = (
  candidate: DevCandidate,
  candidateIndex: number,
): SkuCandidate => ({
  skuId: candidate.sku_id,
  style: nullableText(candidate.attrs.style),
  attrs: candidate.attrs ?? {},
  category: candidate.category,
  subCategory: candidate.sub_category,
  color: nullableText(candidate.attrs.color),
  imageUrl: resolveAssetUrl(candidate.matched_sku_image.image_url),
  kind: toKind(candidate.category, candidate.sub_category),
  material: nullableText(candidate.attrs.material),
  matchRank: candidateIndex + 1,
  metadataScore: null,
  name: candidate.product_name,
  rubric: null,
  score: candidate.similarity_score,
  size: nullableText(candidate.attrs.size),
  sku: candidate.sku_code,
  skuImageId: candidate.matched_sku_image.sku_image_id,
  vectorScore: candidate.similarity_score / 100,
  vlmMood: candidate.xai_result.vlm_mood,
  xaiReason: nullableText(candidate.xai_result.summary),
  xaiResult: {
    criteria: candidate.xai_result.criteria,
    summary: candidate.xai_result.summary,
  },
});

/** GET /search/skus 결과 한 건을 화면 카드가 쓰는 SkuCandidate로 변환합니다. */
const toSearchCandidate = (item: ApiSkuSearchItem): SkuCandidate => ({
  attrs: {},
  brand: item.brand,
  category: item.category,
  color: null,
  imageUrl: resolveAssetUrl(item.image_url),
  kind: toKind(item.category, item.sub_category),
  material: null,
  matchRank: null,
  metadataScore: null,
  name: item.product_name,
  price: item.price,
  rubric: null,
  // 유사도 점수는 AI 루브릭 점수와 비교 불가능한 다른 지표이므로 화면에 노출하지 않습니다.
  score: null,
  size: null,
  sku: item.sku_code,
  subCategory: item.sub_category,
  vectorScore: null,
  vlmMood: null,
  xaiReason: null,
  xaiResult: null,
});

type ApiSkuDetail = {
  attrs: Record<string, unknown>;
  brand: string | null;
  category: string | null;
  image_url: string | null;
  price: number | null;
  product_name: string;
  sku_code: string;
  sku_id: number;
  sku_image_id: number | null;
  sub_category: string | null;
};

export type SkuDetail = {
  attrs: Record<string, unknown>;
  brand: string | null;
  category: string | null;
  imageUrl: string | null;
  price: number | null;
  productName: string;
  skuCode: string;
  skuId: number;
  skuImageId: number | null;
  subCategory: string | null;
};

const toSkuDetail = (detail: ApiSkuDetail): SkuDetail => ({
  attrs: detail.attrs ?? {},
  brand: detail.brand,
  category: detail.category,
  imageUrl: resolveAssetUrl(detail.image_url),
  price: detail.price,
  productName: detail.product_name,
  skuCode: detail.sku_code,
  skuId: detail.sku_id,
  skuImageId: detail.sku_image_id,
  subCategory: detail.sub_category,
});

/** SKU 코드로 카테고리별 속성을 포함한 상세 정보를 조회합니다. */
export const fetchSkuDetail = async (skuCode: string): Promise<SkuDetail> => {
  const response = await requestJson<ApiSuccessResponse<ApiSkuDetail>>(
    `${API_BASE_URL}/search/skus/${encodeURIComponent(skuCode)}`,
  );
  return toSkuDetail(response.data);
};

/**
 * SKU 상세 정보를 추천 후보 카드가 쓰는 SkuCandidate로 변환합니다.
 * 검색 목록 항목(toSearchCandidate)과 달리 attrs가 실제 카탈로그 속성으로
 * 채워져 있어, "이 SKU 선택"으로 추천 목록에 추가할 때 사용합니다.
 */
export const toCandidateFromDetail = (detail: SkuDetail): SkuCandidate => ({
  attrs: detail.attrs ?? {},
  brand: detail.brand,
  category: detail.category,
  color: nullableText(detail.attrs.color),
  imageUrl: detail.imageUrl,
  kind: toKind(detail.category, detail.subCategory),
  material: nullableText(detail.attrs.material),
  matchRank: null,
  metadataScore: null,
  name: detail.productName,
  price: detail.price,
  rubric: null,
  score: null,
  size: nullableText(detail.attrs.size),
  sku: detail.skuCode,
  skuId: detail.skuId,
  skuImageId: detail.skuImageId,
  style: nullableText(detail.attrs.style),
  subCategory: detail.subCategory,
  vectorScore: null,
  vlmMood: null,
  xaiReason: null,
  xaiResult: null,
});

const toHistory = (item: ApiHistoryListItem): TaggingHistory => ({
  id: String(item.result_id),
  imageName: item.scene_image.origin_name,
  objectName: item.object_name ?? '',
  productName: item.product_name,
  savedAt: item.created_at,
  sku: item.sku_code,
  tags: {
    category: '',
    color: '',
    material: '',
    mood: '',
    styleTags: item.style_tags,
  },
});

export const analyzeImage = async (
  file: File,
  targetDescription?: string,
): Promise<TaggingAnalysis> => {
  const formData = new FormData();

  if (targetDescription) {
    formData.append('image', file);
    formData.append('target_description', targetDescription);
    await requestJson(`${API_BASE_URL}/api/v1/taggings/analyze`, {
      body: formData,
      method: 'POST',
    });
    throw new Error('재탐지 인터페이스가 구현되지 않았습니다.');
  }

  formData.append('file', file);
  const response = await requestJson<ApiSuccessResponse<DevUploadResponse>>(
    `${API_BASE_URL}/tagging`,
    {
      body: formData,
      method: 'POST',
    },
  );
  const sceneImageId = response.data.scene_image.scene_image_id;

  return {
    analysisId: String(sceneImageId),
    mode: null,
    objects: response.data.objects.map((detection) => ({
      bbox: toBbox(detection.bbox_coord),
      candidates: [],
      category: nullableText(detection.category),
      confidence: detection.confidence,
      description: detection.evidence,
      id: `${sceneImageId}-${detection.object_idx}`,
      metadata: {
        attributes: {},
        category: nullableText(detection.category),
        description: detection.evidence,
        keyFeatures: [],
        subCategory: detection.sub_category,
      },
      name: detection.category,
      objectIdx: detection.object_idx,
    })),
  };
};

export const fetchRecommendations = async (
  sceneImageId: string,
  objectIdx: number,
): Promise<SkuCandidate[]> => {
  const query = new URLSearchParams();
  query.append('object_idxs', String(objectIdx));
  const response = await requestJson<ApiSuccessResponse<DevRecommendationData>>(
    `${API_BASE_URL}/tagging/scenes/${encodeURIComponent(sceneImageId)}?${query.toString()}`,
  );
  const object = response.data.objects.find(
    (item) => item.object_idx === objectIdx,
  );
  return object?.sku_candidates.map(toDevCandidate) ?? [];
};

/** 수정 완료된 장면의 모든 객체에 대한 SKU 후보를 한 번에 불러옵니다. */
export const fetchObjectRecommendations = async (
  sceneImageId: string,
): Promise<Map<number, SkuCandidate[]>> => {
  const response = await requestJson<ApiSuccessResponse<DevRecommendationData>>(
    `${API_BASE_URL}/tagging/scenes/${encodeURIComponent(sceneImageId)}`,
  );

  return new Map(
    response.data.objects.map((object) => [
      object.object_idx,
      object.sku_candidates.map(toDevCandidate),
    ]),
  );
};

/**
 * 사용자가 확정한 객체 목록을 서버에 반영합니다. bbox는 API 계약에 맞춰
 * [ymin, xmin, ymax, xmax] 배열에서 명시적인 좌표 객체로 변환합니다.
 */
export const updateSceneObjects = async (
  sceneImageId: string,
  objects: EditedSceneObject[],
): Promise<void> => {
  await requestJson(
    `${API_BASE_URL}/tagging/scenes/${encodeURIComponent(sceneImageId)}`,
    {
      body: JSON.stringify({
        objects: objects.map((object) => {
          const [ymin, xmin, ymax, xmax] = object.bbox;
          return {
            bbox_coord: { xmax, xmin, ymax, ymin },
            category: object.category ?? object.name,
          };
        }),
      }),
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
    },
  );
};

/** 검색어와 의미적으로 유사한 SKU를 전체 카탈로그에서 조회합니다. */
export const searchCatalogItems = async (
  query: string,
): Promise<SkuCandidate[]> => {
  const response = await requestJson<ApiSuccessResponse<SkuSearchResponseData>>(
    `${API_BASE_URL}/search/skus?q=${encodeURIComponent(query)}`,
  );
  return response.data.skus.map(toSearchCandidate);
};

export const fetchTaggingHistory = async (): Promise<TaggingHistory[]> => {
  const response = await requestJson<ApiSuccessResponse<ApiHistoryListData>>(
    `${API_BASE_URL}/history/results`,
  );
  return response.data.items.map(toHistory);
};

type TaggingReviewMatch = {
  object: FurnitureObject;
  objectIdx: number;
  selectedSku: SkuCandidate;
  values?: TaggingValues;
};

type SaveTaggingReviewInput = {
  matching: TaggingReviewMatch[];
  sceneImageId: string;
};

/**
 * AI 추천인지 직접 검색한 결과인지 구분해서 저장합니다.
 * matchRank가 있으면 RECOMMEND, 없으면 SEARCH입니다.
 */
const toMatchSource = (
  selectedSku: SkuCandidate,
): 'RECOMMEND' | 'SEARCH' =>
  selectedSku.matchRank !== null ? 'RECOMMEND' : 'SEARCH';

export const saveTaggingReview = async (
  input: SaveTaggingReviewInput,
): Promise<void> => {
  const { matching, sceneImageId } = input;

  if (
    matching.length === 0 ||
    matching.some(({ selectedSku }) => !selectedSku.skuId)
  ) {
    throw new Error('추천 후보의 저장 정보가 없습니다.');
  }

  await requestJson<ApiSuccessResponse<{ result_ids: number[] }>>(
    `${API_BASE_URL}/tagging/scenes/${encodeURIComponent(sceneImageId)}/results`,
    {
      body: JSON.stringify({
        tagging_results: matching.map(
          ({ object, objectIdx, selectedSku, values }) => {
            const [ymin, xmin, ymax, xmax] = object.bbox;
            const styleTags = reviewedTags(values?.styleTags);
            return {
              match_rank: selectedSku.matchRank,
              object_idx: objectIdx,
              match_source: toMatchSource(selectedSku),
              object_index: objectIdx,
              object_metadata: {
                attrs: {
                  color: reviewedText(values?.color, selectedSku.color),
                  material: reviewedText(
                    values?.material,
                    selectedSku.material,
                  ),
                  style: reviewedText(styleTags?.[0], selectedSku.style),
                },
                bbox_coord: { xmax, xmin, ymax, ymin },
                category: reviewedText(values?.category, selectedSku.category),
                object_idx: objectIdx,
                sub_category: selectedSku.subCategory ?? '',
              },
              similarity_score:
                selectedSku.score === null
                  ? null
                  : Math.round(selectedSku.score),
              sku_id: selectedSku.skuId,
              sku_image_id: selectedSku.skuImageId ?? null,
              vlm_mood: {
                summary: reviewedText(
                  values?.mood,
                  selectedSku.vlmMood?.summary,
                ),
                tags: styleTags?.length
                  ? styleTags
                  : (selectedSku.vlmMood?.tags ?? []),
              },
              xai_result: selectedSku.xaiResult,
            };
          },
        ),
      }),
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
    },
  );
};
