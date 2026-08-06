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
  category: string;
  confidence: number;
  description: string;
  id: string;
  metadata: ExtractedMetadata;
  name: string;
}

export interface ExtractedMetadata {
  attributes: Record<string, unknown>;
  category: string;
  description: string;
  keyFeatures: string[];
  subCategory: string;
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

export interface SkuCandidate {
  category?: string;
  color: string;
  grade?: '높음' | '중간' | '낮음' | '검수 필요';
  imageUrl?: string;
  kind: 'sofa' | 'table' | 'lamp' | 'chair' | 'cabinet';
  material: string;
  metadataScore?: number;
  name: string;
  rubric?: RubricEvaluation;
  score?: number;
  size: string;
  sku: string;
  vectorScore?: number;
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
