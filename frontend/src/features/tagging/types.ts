export type AnalysisScenario = 'detected' | 'not-detected';

export type WorkflowStage =
  | 'upload'
  | 'analyzing'
  | 'detect'
  | 'not-found'
  | 'redetecting'
  | 'recommend'
  | 'catalog'
  | 'review'
  | 'saving'
  | 'saved'
  | 'failed';

export interface UploadedImage {
  file: File;
  height: number;
  name: string;
  previewUrl: string;
  size: number;
  width: number;
}

export interface FurnitureObject {
  bbox: [number, number, number, number];
  candidates: SkuCandidate[];
  category: string | null;
  confidence: number | null;
  description: string | null;
  id: string;
  /**
   * 브라우저에서 새로 추가한 객체인지 나타냅니다. 추천을 요청하기 직전에
   * 서버가 객체 목록을 다시 색인하므로, 이 값은 화면 상태에만 사용합니다.
   */
  isNew?: boolean;
  metadata: ExtractedMetadata;
  name: string;
  objectIndex: number;
}

export interface ExtractedMetadata {
  attributes: Record<string, unknown>;
  category: string | null;
  description: string | null;
  keyFeatures: string[];
  subCategory: string | null;
}

export interface RubricEvaluation {
  breakdown: {
    color: number;
    context: number;
    detail: number;
    structure: number;
  };
  status: 'Matched' | 'Rejected';
  totalScore: number;
  xaiReason: string;
}

export interface XaiCriterion {
  comment: string;
  label: string;
  score: number;
}

export interface XaiResult {
  criteria: XaiCriterion[];
  summary: string;
}

export interface VlmMood {
  summary: string;
  tags: string[];
}

export interface SkuCandidate {
  skuId?: number;
  skuImageId?: number | null;
  style?: string | null;
  subCategory?: string | null;
  brand?: string | null;
  price?: number | null;
  attrs: Record<string, unknown>;
  category: string | null;
  color: string | null;
  imageUrl: string | null;
  kind: 'sofa' | 'table' | 'lamp' | 'chair' | 'cabinet' | null;
  material: string | null;
  matchRank: number | null;
  metadataScore: number | null;
  name: string;
  rubric: RubricEvaluation | null;
  score: number | null;
  size: string | null;
  sku: string;
  vectorScore: number | null;
  vlmMood: VlmMood | null;
  xaiReason: string | null;
  xaiResult: XaiResult | null;
}

export interface ConfirmedSkuSelection {
  object: FurnitureObject;
  sku: SkuCandidate;
}

export interface TaggingValues {
  category: string;
  color: string;
  material: string;
  mood: string;
  styleTags: string[];
}

export interface TaggingHistory {
  id: string;
  imageName: string;
  objectName: string;
  productName: string;
  savedAt: string;
  sku: string;
  tags: TaggingValues;
}
