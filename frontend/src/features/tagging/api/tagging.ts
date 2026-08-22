import { requestJson, type ApiSuccessResponse } from '../../../lib/api-request';

import type { ApprovalStatus } from '../../approvals/api/approvals';
import type {
  FurnitureObject,
  SkuCandidate,
  TaggingHistory,
  TaggingValues,
  VlmMood,
  XaiCriterion,
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

type AiJobAcceptedData = {
  job_id: string;
  scene_image_id: number;
  status: 'PENDING';
};

type DetectionJobResult = {
  objects: DevDetection[];
  scene_image_id: number;
};

type AiJobData<ResultPayload> = {
  error_message: string | null;
  job_id: string;
  result_payload: ResultPayload | null;
  scene_image_id: number;
  status: 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED';
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
  xai_result: {
    criteria: XaiCriterion[];
    summary: string;
    vlm_mood: VlmMood;
    xai_attrs?: Record<string, string>;
  };
};

type DevRecommendationObject = {
  object_idx: number;
  category: string;
  sub_category: string | null;
  bbox_coord: ApiBoundingBox;
  confidence: number;
  attrs: Record<string, string>;
  xai_attrs?: Record<string, string>;
  sku_candidates: DevCandidate[];
};

type RecommendationObject = Omit<DevRecommendationObject, 'sku_candidates'> & {
  sku_candidates: SkuCandidate[];
};

type DevRecommendationData = {
  objects: DevRecommendationObject[];
};

type EditedSceneObject = Pick<FurnitureObject, 'bbox' | 'category' | 'name'> & {
  objectIdx: number;
};

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
  approval_status: ApprovalStatus | null;
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
const JOB_POLL_INTERVAL_MS = 1000;
const JOB_POLL_TIMEOUT_MS = 600_000;

const sleep = async (milliseconds: number): Promise<void> =>
  new Promise((resolve) => {
    globalThis.setTimeout(resolve, milliseconds);
  });

const waitForAiJob = async <ResultPayload>(
  jobId: string,
): Promise<ResultPayload> => {
  const timeoutAt = Date.now() + JOB_POLL_TIMEOUT_MS;

  while (Date.now() < timeoutAt) {
    const response = await requestJson<
      ApiSuccessResponse<AiJobData<ResultPayload>>
    >(`${API_BASE_URL}/ai-jobs/${encodeURIComponent(jobId)}`);
    const job = response.data;

    if (job.status === 'SUCCEEDED') {
      if (!job.result_payload) {
        throw new Error('AI 분석 결과를 확인하지 못했습니다.');
      }
      return job.result_payload;
    }
    if (job.status === 'FAILED') {
      throw new Error(job.error_message ?? '가구 분석에 실패했습니다.');
    }

    await sleep(JOB_POLL_INTERVAL_MS);
  }

  throw new Error('AI 분석 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.');
};

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
): string => (value && value !== NULL_TAG_VALUE ? value : (fallback ?? ''));

const reviewedTags = (tags: string[] | undefined): string[] | undefined =>
  tags?.filter((tag) => tag !== NULL_TAG_VALUE);

/**
 * 카테고리별 소재 속성(material / top_material / frame_material 등)을
 * attrs에 그대로 실어 보냅니다. 검수 값이 없으면 SKU 소재를 기본값으로 씁니다.
 */
const reviewedMaterials = (
  materials: Record<string, string> | undefined,
  fallback: string | null | undefined,
): Record<string, string> => {
  const entries = Object.entries(materials ?? {}).filter(
    ([, value]) => value && value !== NULL_TAG_VALUE,
  );
  if (entries.length > 0) return Object.fromEntries(entries);
  return { material: fallback ?? '' };
};

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
    xaiAttrs: candidate.xai_result.xai_attrs ?? {},
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
  approvalStatus: item.approval_status ?? null,
  id: String(item.result_id),
  imageName: item.scene_image.origin_name,
  objectName: item.object_name ?? '',
  productName: item.product_name,
  savedAt: item.created_at,
  sku: item.sku_code,
  tags: {
    category: '',
    color: '',
    materials: {},
    mood: '',
    styleTags: item.style_tags,
    subCategory: '',
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
  const accepted = await requestJson<ApiSuccessResponse<AiJobAcceptedData>>(
    `${API_BASE_URL}/tagging`,
    {
      body: formData,
      method: 'POST',
    },
  );
  const detectionResult = await waitForAiJob<DetectionJobResult>(
    accepted.data.job_id,
  );

  return {
    analysisId: String(accepted.data.scene_image_id),
    mode: null,
    objects: detectionResult.objects.map((detection) => ({
      bbox: toBbox(detection.bbox_coord),
      candidates: [],
      category: nullableText(detection.category),
      confidence: detection.confidence,
      description: detection.evidence,
      id: `${accepted.data.scene_image_id}-${detection.object_idx}`,
      metadata: {
        attributes: {},
        category: nullableText(detection.category),
        description: detection.evidence,
        keyFeatures: [],
        subCategory: detection.sub_category,
      },
      name: detection.category,
      objectIdx: detection.object_idx,
      xaiAttrs: {},
    })),
  };
};

export const fetchRecommendations = async (
  sceneImageId: string,
  objectIdx: number,
  objects: EditedSceneObject[],
): Promise<SkuCandidate[]> => {
  const candidatesByObjectIndex = await fetchObjectRecommendations(
    sceneImageId,
    objects,
  );
  return candidatesByObjectIndex.get(objectIdx) ?? [];
};

/** 수정 완료된 장면의 모든 객체에 대한 SKU 후보를 한 번에 불러옵니다. */
export const fetchObjectRecommendations = async (
  sceneImageId: string,
  objects: EditedSceneObject[],
): Promise<Map<number, SkuCandidate[]>> => {
  const recommendations = await updateSceneObjects(sceneImageId, objects);
  return new Map(
    [...recommendations].map(([objectIndex, object]) => [
      objectIndex,
      object.sku_candidates,
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
): Promise<Map<number, RecommendationObject>> => {
  const accepted = await requestJson<ApiSuccessResponse<AiJobAcceptedData>>(
    `${API_BASE_URL}/tagging/scenes/${encodeURIComponent(sceneImageId)}`,
    {
      body: JSON.stringify({
        objects: objects.map((object) => {
          const [ymin, xmin, ymax, xmax] = object.bbox;
          return {
            bbox_coord: { xmax, xmin, ymax, ymin },
            category: object.category ?? object.name,
            object_idx: object.objectIdx,
          };
        }),
      }),
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
    },
  );
  const recommendationResult = await waitForAiJob<DevRecommendationData>(
    accepted.data.job_id,
  );

  return new Map<number, RecommendationObject>(
    recommendationResult.objects.map((object) => [
      object.object_idx,
      {
        ...object,
        sku_candidates: object.sku_candidates.map(toDevCandidate),
      },
    ]),
  );
};

type ApiSearchCandidateMoodData = {
  vlm_mood: VlmMood;
};

/**
 * 전체 카탈로그 검색으로 선택한 SKU에 대해, VLM이 크롭 이미지에서 읽어낸
 * 공간 분위기·스타일 태그를 계산합니다. AI 추천 후보와 달리 순위 근거는
 * 만들지 않으므로(match_source가 SEARCH인 결과는 xai_result를 가질 수
 * 없음), vlm_mood 하나만 돌려받습니다.
 */
export const fetchSearchCandidateMood = async (
  sceneImageId: string,
  object: EditedSceneObject,
  skuCode: string,
): Promise<VlmMood> => {
  const [ymin, xmin, ymax, xmax] = object.bbox;
  const response = await requestJson<ApiSuccessResponse<ApiSearchCandidateMoodData>>(
    `${API_BASE_URL}/tagging/scenes/${encodeURIComponent(
      sceneImageId,
    )}/search-candidates/mood`,
    {
      body: JSON.stringify({
        object: {
          bbox_coord: { xmax, xmin, ymax, ymin },
          category: object.category ?? object.name,
          object_idx: object.objectIdx,
        },
        sku_code: skuCode,
      }),
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
    },
  );
  return response.data.vlm_mood;
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
const toMatchSource = (selectedSku: SkuCandidate): 'RECOMMEND' | 'SEARCH' =>
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
            const matchSource = toMatchSource(selectedSku);
            // 검색으로 직접 고른 SKU는 AI 추천 근거가 없으므로 순위·유사도·XAI를
            // 모두 null로 보냅니다(백엔드 ck_result_source 제약과 같은 규칙).
            const isRecommended = matchSource === 'RECOMMEND';
            return {
              match_rank: isRecommended ? selectedSku.matchRank : null,
              object_idx: objectIdx,
              match_source: matchSource,
              object_metadata: {
                attrs: {
                  ...object.metadata.attributes,
                  ...reviewedMaterials(values?.materials, selectedSku.material),
                  color: reviewedText(values?.color, selectedSku.color),
                  style: reviewedText(styleTags?.[0], selectedSku.style),
                },
                bbox_coord: { xmax, xmin, ymax, ymin },
                category: reviewedText(values?.category, selectedSku.category),
                object_idx: objectIdx,
                sub_category: reviewedText(
                  values?.subCategory,
                  object.metadata.subCategory,
                ),
              },
              similarity_score:
                isRecommended && selectedSku.score !== null
                  ? Math.round(selectedSku.score)
                  : null,
              sku_id: selectedSku.skuId,
              sku_image_id: selectedSku.skuImageId ?? null,
              vlm_mood: {
                summary: reviewedText(
                  values?.mood,
                  selectedSku.vlmMood?.summary,
                ),
                // 검수 화면에서 고른 태그만 저장합니다. 검수 값 자체가 없을
                // 때만 VLM이 추출한 원본 태그를 그대로 사용합니다.
                tags: styleTags ?? selectedSku.vlmMood?.tags ?? [],
              },
              xai_result: isRecommended
                ? {
                    criteria: selectedSku.xaiResult?.criteria ?? [],
                    summary: selectedSku.xaiResult?.summary ?? '',
                    xai_attrs:
                      object.xaiAttrs ?? selectedSku.xaiResult?.xaiAttrs ?? {},
                  }
                : null,
            };
          },
        ),
      }),
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
    },
  );
};
