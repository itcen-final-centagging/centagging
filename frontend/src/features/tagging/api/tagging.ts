import { requestJson, type ApiSuccessResponse } from '../../../lib/api-request';

import type {
  FurnitureObject,
  RubricEvaluation,
  SkuCandidate,
  TaggingHistory,
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
  sub_category: string | null;
  bbox_coord: ApiBoundingBox;
  confidence: number | null;
  evidence: string;
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
  attrs: Record<string, unknown>;
  category: string | null;
  matched_sku_image: {
    image_url: string;
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

type ApiRubric = {
  breakdown: RubricEvaluation['breakdown'];
  status: RubricEvaluation['status'];
  total_score: number;
  xai_reason: string;
};

type ApiCandidate = {
  category: string;
  color: string;
  grade: string;
  image_url: string;
  kind: NonNullable<SkuCandidate['kind']>;
  material: string;
  metadata_score: number;
  name: string;
  rubric: ApiRubric;
  score: number;
  size: string;
  sku: string;
  vector_score: number;
};

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
  category: candidate.category,
  color: nullableText(candidate.attrs.color),
  grade: null,
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
  vectorScore: candidate.similarity_score / 100,
  vlmMood: candidate.xai_result.vlm_mood,
  xaiReason: nullableText(candidate.xai_result.summary),
  xaiResult: {
    criteria: candidate.xai_result.criteria,
    summary: candidate.xai_result.summary,
  },
});

const toCandidate = (candidate: ApiCandidate): SkuCandidate => ({
  category: candidate.category,
  color: candidate.color,
  grade: candidate.grade,
  imageUrl: resolveAssetUrl(candidate.image_url),
  kind: candidate.kind,
  material: candidate.material,
  matchRank: null,
  metadataScore: candidate.metadata_score,
  name: candidate.name,
  rubric: {
    breakdown: candidate.rubric.breakdown,
    status: candidate.rubric.status,
    totalScore: candidate.rubric.total_score,
    xaiReason: candidate.rubric.xai_reason,
  },
  score: candidate.score,
  size: candidate.size,
  sku: candidate.sku,
  vectorScore: candidate.vector_score,
  vlmMood: null,
  xaiReason: candidate.rubric.xai_reason,
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

export const searchCatalogItems = async (
  query: string,
): Promise<SkuCandidate[]> => {
  const response = await requestJson<ApiCandidate[]>(
    `${API_BASE_URL}/api/v1/taggings/catalog?query=${encodeURIComponent(query)}`,
  );
  return response.map(toCandidate);
};

export const fetchTaggingHistory = async (): Promise<TaggingHistory[]> => {
  const response = await requestJson<ApiSuccessResponse<ApiHistoryListData>>(
    `${API_BASE_URL}/history/results`,
  );
  return response.data.items.map(toHistory);
};

export const saveTaggingReview = async ({
  objectIdx,
  sceneImageId,
  selectedSku,
}: {
  objectIdx: number;
  sceneImageId: string;
  selectedSku: SkuCandidate;
}): Promise<void> => {
  if (
    selectedSku.matchRank === null ||
    selectedSku.score === null ||
    selectedSku.vlmMood === null ||
    selectedSku.xaiResult === null
  ) {
    throw new Error('추천 후보의 저장 정보가 없습니다.');
  }

  await requestJson<ApiSuccessResponse<{ result_ids: number[] }>>(
    `${API_BASE_URL}/tagging/scenes/${encodeURIComponent(sceneImageId)}`,
    {
      body: JSON.stringify({
        matching: [
          {
            match_rank: selectedSku.matchRank,
            object_idx: objectIdx,
            similarity_score: selectedSku.score,
            sku_code: selectedSku.sku,
            vlm_mood: selectedSku.vlmMood,
            xai_result: selectedSku.xaiResult,
          },
        ],
      }),
      headers: { 'Content-Type': 'application/json' },
      method: 'PUT',
    },
  );
};
