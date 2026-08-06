import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
} from 'react';

import {
  analyzeImage,
  fetchTaggingHistory,
  saveTaggingReview,
  searchCatalogItems,
} from '../api/tagging';
import { validateImage } from '../utils/image';

import type {
  AnalysisScenario,
  FurnitureObject,
  SkuCandidate,
  TaggingHistory,
  TaggingValues,
  UploadedImage,
  WorkflowStage,
} from '../types';

type TaggingWorkflowContextValue = {
  analysisMode?: 'live' | 'mock';
  analysisScenario: AnalysisScenario;
  beginAnalysis: () => Promise<void>;
  catalogResults: SkuCandidate[];
  changeStage: (stage: WorkflowStage) => void;
  clearUploadError: () => void;
  detectedObjects: FurnitureObject[];
  history: TaggingHistory[];
  redetect: (description: string) => Promise<void>;
  resetWorkflow: () => void;
  saveTagging: (tags: TaggingValues) => Promise<void>;
  searchCatalog: (query: string) => Promise<SkuCandidate[]>;
  selectObject: (object: FurnitureObject) => void;
  selectedObject?: FurnitureObject;
  selectedSku?: SkuCandidate;
  selectSku: (sku: SkuCandidate) => void;
  setAnalysisScenario: (scenario: AnalysisScenario) => void;
  stage: WorkflowStage;
  uploadError?: string;
  uploadedImage?: UploadedImage;
  uploadImage: (file: File) => Promise<void>;
  workflowError?: string;
};

const TaggingWorkflowContext =
  createContext<TaggingWorkflowContextValue | null>(null);

export const TaggingWorkflowProvider = ({ children }: PropsWithChildren) => {
  const [stage, setStage] = useState<WorkflowStage>('upload');
  const [uploadedImage, setUploadedImage] = useState<UploadedImage>();
  const [uploadError, setUploadError] = useState<string>();
  const [workflowError, setWorkflowError] = useState<string>();
  const [analysisId, setAnalysisId] = useState<string>();
  const [analysisMode, setAnalysisMode] = useState<'live' | 'mock'>();
  const [detectedObjects, setDetectedObjects] = useState<FurnitureObject[]>([]);
  const [selectedObject, setSelectedObject] = useState<FurnitureObject>();
  const [selectedSku, setSelectedSku] = useState<SkuCandidate>();
  const [catalogResults, setCatalogResults] = useState<SkuCandidate[]>([]);
  const [analysisScenario, setAnalysisScenario] =
    useState<AnalysisScenario>('detected');
  const [history, setHistory] = useState<TaggingHistory[]>([]);

  useEffect(() => {
    let isMounted = true;
    void fetchTaggingHistory()
      .then((nextHistory) => {
        if (isMounted) setHistory(nextHistory);
      })
      .catch(() => undefined);
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(
    () => () => {
      if (uploadedImage) URL.revokeObjectURL(uploadedImage.previewUrl);
    },
    [uploadedImage],
  );

  const uploadImage = useCallback(async (file: File): Promise<void> => {
    setUploadError(undefined);
    try {
      const nextImage = await validateImage(file);
      setUploadedImage((currentImage) => {
        if (currentImage) URL.revokeObjectURL(currentImage.previewUrl);
        return nextImage;
      });
      setWorkflowError(undefined);
      setAnalysisId(undefined);
      setAnalysisMode(undefined);
      setDetectedObjects([]);
      setSelectedObject(undefined);
      setSelectedSku(undefined);
    } catch (error) {
      setUploadError(
        error instanceof Error
          ? error.message
          : '이미지를 읽을 수 없습니다. 다른 파일을 선택해 주세요.',
      );
    }
  }, []);

  const runAnalysis = useCallback(
    async (targetDescription?: string): Promise<void> => {
      if (!uploadedImage) return;
      setWorkflowError(undefined);
      try {
        const description =
          analysisScenario === 'not-detected'
            ? '가구를 찾지 못했습니다'
            : targetDescription;
        const analysis = await analyzeImage(uploadedImage.file, description);
        setAnalysisId(analysis.analysisId);
        setAnalysisMode(analysis.mode);
        setDetectedObjects(analysis.objects);
        setSelectedObject(undefined);
        setSelectedSku(undefined);
        setStage(analysis.objects.length > 0 ? 'detect' : 'not-found');
      } catch (error) {
        setWorkflowError(
          error instanceof Error
            ? error.message
            : 'AI 분석 요청을 처리하지 못했습니다.',
        );
        setStage('failed');
      }
    },
    [analysisScenario, uploadedImage],
  );

  const beginAnalysis = useCallback(async (): Promise<void> => {
    if (!uploadedImage) return;
    setStage('analyzing');
    await runAnalysis();
  }, [runAnalysis, uploadedImage]);

  const redetect = useCallback(
    async (description: string): Promise<void> => {
      setStage('redetecting');
      await runAnalysis(description);
    },
    [runAnalysis],
  );

  const searchCatalog = useCallback(
    async (query: string): Promise<SkuCandidate[]> => {
      try {
        const results = await searchCatalogItems(query);
        setCatalogResults(results);
        return results;
      } catch (error) {
        setWorkflowError(
          error instanceof Error
            ? error.message
            : '카탈로그를 검색하지 못했습니다.',
        );
        setCatalogResults([]);
        return [];
      }
    },
    [],
  );

  const saveTagging = useCallback(
    async (tags: TaggingValues): Promise<void> => {
      if (!analysisId || !uploadedImage || !selectedObject || !selectedSku)
        return;
      setStage('saving');
      try {
        const savedHistory = await saveTaggingReview({
          analysisId,
          imageName: uploadedImage.name,
          objectId: selectedObject.id,
          objectName: selectedObject.name,
          selectedSku: selectedSku.sku,
          tags,
        });
        setHistory((currentHistory) => [savedHistory, ...currentHistory]);
        setStage('saved');
      } catch (error) {
        setWorkflowError(
          error instanceof Error
            ? error.message
            : '태깅 결과를 저장하지 못했습니다.',
        );
        setStage('failed');
      }
    },
    [analysisId, selectedObject, selectedSku, uploadedImage],
  );

  const resetWorkflow = useCallback((): void => {
    setStage('upload');
    setUploadedImage((currentImage) => {
      if (currentImage) URL.revokeObjectURL(currentImage.previewUrl);
      return undefined;
    });
    setUploadError(undefined);
    setWorkflowError(undefined);
    setAnalysisId(undefined);
    setAnalysisMode(undefined);
    setDetectedObjects([]);
    setSelectedObject(undefined);
    setSelectedSku(undefined);
    setCatalogResults([]);
  }, []);

  const value = useMemo<TaggingWorkflowContextValue>(
    () => ({
      analysisMode,
      analysisScenario,
      beginAnalysis,
      catalogResults,
      changeStage: setStage,
      clearUploadError: () => setUploadError(undefined),
      detectedObjects,
      history,
      redetect,
      resetWorkflow,
      saveTagging,
      searchCatalog,
      selectObject: setSelectedObject,
      selectedObject,
      selectedSku,
      selectSku: setSelectedSku,
      setAnalysisScenario,
      stage,
      uploadError,
      uploadedImage,
      uploadImage,
      workflowError,
    }),
    [
      analysisMode,
      analysisScenario,
      beginAnalysis,
      catalogResults,
      detectedObjects,
      history,
      redetect,
      resetWorkflow,
      saveTagging,
      searchCatalog,
      selectedObject,
      selectedSku,
      stage,
      uploadError,
      uploadedImage,
      uploadImage,
      workflowError,
    ],
  );

  return (
    <TaggingWorkflowContext.Provider value={value}>
      {children}
    </TaggingWorkflowContext.Provider>
  );
};

// Context hook is exported alongside its provider so feature consumers share one state.
// eslint-disable-next-line react-refresh/only-export-components
export const useTaggingWorkflow = (): TaggingWorkflowContextValue => {
  const context = useContext(TaggingWorkflowContext);
  if (!context) {
    throw new Error(
      'useTaggingWorkflow must be used within TaggingWorkflowProvider.',
    );
  }
  return context;
};
