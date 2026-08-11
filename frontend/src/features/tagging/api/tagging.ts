import type {
  FurnitureObject,
  RubricEvaluation,
  SkuCandidate,
  TaggingHistory,
  VlmMood,
  XaiResult,
} from '../types';

type DevDetection = {
  box_2d: number[];
  label: string;
};

type DevUploadResponse = {
  detections: DevDetection[];
  scene_image_id: number;
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

type DevRecommendationResponse = {
  data: {
    objects: Array<{
      object_index: number;
      sku_candidates: DevCandidate[];
    }>;
  };
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

type ApiHistory = {
  id: string;
  image_name: string;
  object_name: string;
  product_name: string;
  saved_at: string;
  sku: string;
  tags: {
    category: string;
    color: string;
    material: string;
    mood: string;
    style_tags: string[];
  };
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

const getErrorMessage = async (response: Response): Promise<string> => {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? '요청을 처리하지 못했습니다.';
  } catch {
    return '요청을 처리하지 못했습니다.';
  }
};

const request = async <ResponseData>(
  input: string,
  init?: RequestInit,
): Promise<ResponseData> => {
  const response = await fetch(`${API_BASE_URL}${input}`, init);
  if (!response.ok) throw new Error(await getErrorMessage(response));
  return (await response.json()) as ResponseData;
};

const toBbox = (coordinates: number[]): [number, number, number, number] => [
  coordinates[0] ?? 0,
  coordinates[1] ?? 0,
  coordinates[2] ?? 0,
  coordinates[3] ?? 0,
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

const toHistory = (item: ApiHistory): TaggingHistory => ({
  id: item.id,
  imageName: item.image_name,
  objectName: item.object_name,
  productName: item.product_name,
  savedAt: item.saved_at,
  sku: item.sku,
  tags: {
    category: item.tags.category,
    color: item.tags.color,
    material: item.tags.material,
    mood: item.tags.mood,
    styleTags: item.tags.style_tags,
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
    await request('/api/v1/taggings/analyze', {
      body: formData,
      method: 'POST',
    });
    throw new Error('재탐지 인터페이스가 구현되지 않았습니다.');
  }

  formData.append('file', file);
  const response = await request<DevUploadResponse>('/tagging', {
    body: formData,
    method: 'POST',
  });

  return {
    analysisId: String(response.scene_image_id),
    mode: null,
    objects: response.detections.map((detection, objectIndex) => ({
      bbox: toBbox(detection.box_2d),
      candidates: [],
      category: nullableText(detection.label),
      confidence: null,
      description: null,
      id: `${response.scene_image_id}-${objectIndex}`,
      metadata: {
        attributes: {},
        category: nullableText(detection.label),
        description: null,
        keyFeatures: [],
        subCategory: null,
      },
      name: detection.label,
      objectIndex,
    })),
  };
};

export const fetchRecommendations = async (
  sceneImageId: string,
  objectIndex: number,
): Promise<SkuCandidate[]> => {
  const query = new URLSearchParams();
  query.append('object_indexes', String(objectIndex));
  const response = await request<DevRecommendationResponse>(
    `/tagging/scenes/${encodeURIComponent(sceneImageId)}?${query.toString()}`,
  );
  const object = response.data.objects.find(
    (item) => item.object_index === objectIndex,
  );
  return object?.sku_candidates.map(toDevCandidate) ?? [];
};

export const searchCatalogItems = async (
  query: string,
): Promise<SkuCandidate[]> => {
  const response = await request<ApiCandidate[]>(
    `/api/v1/taggings/catalog?query=${encodeURIComponent(query)}`,
  );
  return response.map(toCandidate);
};

export const saveTaggingReview = async ({
  objectIndex,
  sceneImageId,
  selectedSku,
}: {
  objectIndex: number;
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

  await request(`/tagging/scenes/${encodeURIComponent(sceneImageId)}`, {
    body: JSON.stringify({
      matching: [
        {
          match_rank: selectedSku.matchRank,
          object_index: objectIndex,
          similarity_score: selectedSku.score,
          sku_code: selectedSku.sku,
          vlm_mood: selectedSku.vlmMood,
          xai_result: selectedSku.xaiResult,
        },
      ],
    }),
    headers: { 'Content-Type': 'application/json' },
    method: 'PUT',
  });
};

export const fetchTaggingHistory = async (): Promise<TaggingHistory[]> => {
  const response = await request<ApiHistory[]>('/api/v1/taggings/history');
  return response.map(toHistory);
};
