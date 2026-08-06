import type {
  ExtractedMetadata,
  FurnitureObject,
  RubricEvaluation,
  SkuCandidate,
  TaggingHistory,
  TaggingValues,
} from '../types';

type ApiRubric = {
  breakdown: RubricEvaluation['breakdown'];
  status: RubricEvaluation['status'];
  total_score: number;
  xai_reason: string;
};

type ApiCandidate = {
  category: string;
  color: string;
  grade: SkuCandidate['grade'];
  image_url: string;
  kind: SkuCandidate['kind'];
  material: string;
  metadata_score: number;
  name: string;
  rubric: ApiRubric;
  score: number;
  size: string;
  sku: string;
  vector_score: number;
};

type ApiMetadata = {
  attributes: Record<string, unknown>;
  category: string;
  description: string;
  key_features: string[];
  sub_category: string;
};

type ApiObject = {
  bbox: [number, number, number, number];
  candidates: ApiCandidate[];
  category: string;
  confidence: number;
  description: string;
  id: string;
  metadata: ApiMetadata;
  name: string;
};

type ApiAnalysis = {
  analysis_id: string;
  mode: 'live' | 'mock';
  objects: ApiObject[];
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
  mode: 'live' | 'mock';
  objects: FurnitureObject[];
};

const getErrorMessage = async (response: Response): Promise<string> => {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? '요청을 처리하지 못했습니다.';
  } catch {
    return '요청을 처리하지 못했습니다.';
  }
};

const request = async <ResponseData>(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<ResponseData> => {
  const response = await fetch(input, init);
  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }
  return (await response.json()) as ResponseData;
};

const toRubric = (rubric: ApiRubric): RubricEvaluation => ({
  breakdown: rubric.breakdown,
  status: rubric.status,
  totalScore: rubric.total_score,
  xaiReason: rubric.xai_reason,
});

const toCandidate = (candidate: ApiCandidate): SkuCandidate => ({
  category: candidate.category,
  color: candidate.color,
  grade: candidate.grade,
  imageUrl: candidate.image_url,
  kind: candidate.kind,
  material: candidate.material,
  metadataScore: candidate.metadata_score,
  name: candidate.name,
  rubric: toRubric(candidate.rubric),
  score: candidate.score,
  size: candidate.size,
  sku: candidate.sku,
  vectorScore: candidate.vector_score,
});

const toMetadata = (metadata: ApiMetadata): ExtractedMetadata => ({
  attributes: metadata.attributes,
  category: metadata.category,
  description: metadata.description,
  keyFeatures: metadata.key_features,
  subCategory: metadata.sub_category,
});

const toObject = (object: ApiObject): FurnitureObject => ({
  bbox: object.bbox,
  candidates: object.candidates.map(toCandidate),
  category: object.category,
  confidence: object.confidence,
  description: object.description,
  id: object.id,
  metadata: toMetadata(object.metadata),
  name: object.name,
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
  formData.append('image', file);
  if (targetDescription) {
    formData.append('target_description', targetDescription);
  }
  const response = await request<ApiAnalysis>('/api/v1/taggings/analyze', {
    body: formData,
    method: 'POST',
  });
  return {
    analysisId: response.analysis_id,
    mode: response.mode,
    objects: response.objects.map(toObject),
  };
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
  analysisId,
  imageName,
  objectId,
  objectName,
  selectedSku,
  tags,
}: {
  analysisId: string;
  imageName: string;
  objectId: string;
  objectName: string;
  selectedSku: string;
  tags: TaggingValues;
}): Promise<TaggingHistory> => {
  const response = await request<ApiHistory>('/api/v1/taggings/reviews', {
    body: JSON.stringify({
      analysis_id: analysisId,
      image_name: imageName,
      object_id: objectId,
      object_name: objectName,
      selected_sku: selectedSku,
      tags: {
        category: tags.category,
        color: tags.color,
        material: tags.material,
        mood: tags.mood,
        style_tags: tags.styleTags,
      },
    }),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  });
  return toHistory(response);
};

export const fetchTaggingHistory = async (): Promise<TaggingHistory[]> => {
  const response = await request<ApiHistory[]>('/api/v1/taggings/history');
  return response.map(toHistory);
};
