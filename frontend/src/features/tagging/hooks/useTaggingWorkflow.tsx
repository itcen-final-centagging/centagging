import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
} from 'react';

import { useSkuSelections } from './useSkuSelections';
import { useTaggingObjectEditor } from './useTaggingObjectEditor';
import {
  analyzeImage,
  fetchObjectRecommendations,
  saveTaggingReview,
  searchCatalogItems,
  updateSceneObjects,
} from '../api/tagging';
import { DEMO_IMAGE_URL, DEMO_OBJECTS } from '../constants/demoScenario';
import { validateImage } from '../utils/image';

import type {
  AnalysisScenario,
  ConfirmedSkuSelection,
  FurnitureObject,
  SkuCandidate,
  UploadedImage,
  WorkflowStage,
} from '../types';

type TaggingWorkflowContextValue = {
  analysisMode?: 'live' | 'mock' | null;
  analysisScenario: AnalysisScenario;
  addObject: () => void;
  beginAnalysis: () => Promise<void>;
  catalogResults: SkuCandidate[];
  changeStage: (stage: WorkflowStage) => void;
  clearSelectedSku: () => void;
  confirmedSelections: ConfirmedSkuSelection[];
  clearUploadError: () => void;
  detectedObjects: FurnitureObject[];
  deleteObject: (objectId: string) => void;
  finishEditing: () => void;
  focusObjectForEditing: (object: FurnitureObject) => void;
  isRecommendationLoading: boolean;
  isEditing: boolean;
  loadDemoWorkflow: () => Promise<void>;
  loadSelectedObjectRecommendations: () => Promise<void>;
  redetect: (description: string) => Promise<void>;
  resetWorkflow: () => void;
  saveTagging: () => Promise<void>;
  searchCatalog: (query: string) => Promise<SkuCandidate[]>;
  selectObject: (object: FurnitureObject) => void;
  selectedObject?: FurnitureObject;
  selectedObjectIds: string[];
  selectedSku?: SkuCandidate;
  selectSku: (sku: SkuCandidate) => void;
  setAnalysisScenario: (scenario: AnalysisScenario) => void;
  stage: WorkflowStage;
  startEditing: () => void;
  toggleObjectSelection: (object: FurnitureObject) => void;
  updateObjectBboxes: (
    updates: Array<Pick<FurnitureObject, 'bbox' | 'id'>>,
  ) => void;
  updateObjectCategory: (objectId: string, category: string) => void;
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
  const [analysisMode, setAnalysisMode] = useState<'live' | 'mock' | null>();
  const [catalogResults, setCatalogResults] = useState<SkuCandidate[]>([]);
  const [analysisScenario, setAnalysisScenario] =
    useState<AnalysisScenario>('detected');
  const [isRecommendationLoading, setIsRecommendationLoading] = useState(false);
  const handleMinimumObjectError = useCallback(() => {
    setWorkflowError('최소 한 개의 탐지 객체는 남겨야 합니다.');
  }, []);
  const {
    addObject,
    deleteObject: deleteDetectedObject,
    detectedObjects,
    finishEditing,
    focusObjectForEditing,
    isEditing,
    resetObjectEditor,
    selectedObject,
    selectedObjectIds,
    setDetectedObjects,
    setSelectedObject,
    startEditing: startObjectEditing,
    toggleObjectSelection,
    updateObjectBboxes,
    updateObjectCategory,
  } = useTaggingObjectEditor({
    onMinimumObjectError: handleMinimumObjectError,
  });
  const {
    clearSelectedSku,
    confirmedSelections,
    removeSkuSelection,
    resetSkuSelections,
    selectObjectForSku,
    selectedSku,
    selectSku,
  } = useSkuSelections({
    detectedObjects,
    selectedObject,
    setSelectedObject,
  });

  useEffect(
    () => () => {
      if (uploadedImage) URL.revokeObjectURL(uploadedImage.previewUrl);
    },
    [uploadedImage],
  );

  const uploadImage = useCallback(
    async (file: File): Promise<void> => {
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
        resetObjectEditor();
        resetSkuSelections();
      } catch (error) {
        setUploadError(
          error instanceof Error
            ? error.message
            : '이미지를 읽을 수 없습니다. 다른 파일을 선택해 주세요.',
        );
      }
    },
    [resetObjectEditor, resetSkuSelections],
  );

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
        resetObjectEditor(analysis.objects);
        resetSkuSelections();
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
    [analysisScenario, resetObjectEditor, resetSkuSelections, uploadedImage],
  );

  const beginAnalysis = useCallback(async (): Promise<void> => {
    if (!uploadedImage) return;
    setStage('analyzing');
    await runAnalysis();
  }, [runAnalysis, uploadedImage]);

  const loadDemoWorkflow = useCallback(async (): Promise<void> => {
    setUploadError(undefined);
    setWorkflowError(undefined);
    try {
      const response = await fetch(DEMO_IMAGE_URL);
      if (!response.ok) {
        throw new Error('데모 이미지를 불러오지 못했습니다.');
      }
      const blob = await response.blob();
      const file = new File([blob], 'demo-sofa-bed.png', {
        type: blob.type || 'image/png',
      });
      const nextImage = await validateImage(file);
      setUploadedImage((currentImage) => {
        if (currentImage) URL.revokeObjectURL(currentImage.previewUrl);
        return nextImage;
      });
      setAnalysisId('demo-sofa-bed');
      setAnalysisMode('mock');
      resetObjectEditor(DEMO_OBJECTS);
      resetSkuSelections();
      setCatalogResults([]);
      setStage('detect');
    } catch (error) {
      setWorkflowError(
        error instanceof Error
          ? error.message
          : '데모 작업을 시작하지 못했습니다.',
      );
      setStage('failed');
    }
  }, [resetObjectEditor, resetSkuSelections]);

  const redetect = useCallback(
    async (description: string): Promise<void> => {
      setStage('redetecting');
      await runAnalysis(description);
    },
    [runAnalysis],
  );

  const loadSelectedObjectRecommendations = useCallback(async () => {
    if (!analysisId || detectedObjects.length === 0 || isEditing) return;
    setIsRecommendationLoading(true);
    setWorkflowError(undefined);
    try {
      if (analysisMode === 'mock') {
        const firstCandidateObject = detectedObjects.find(
          (object) => object.candidates.length > 0,
        );
        if (!firstCandidateObject) {
          throw new Error('데모 SKU 후보가 없습니다.');
        }
        setSelectedObject(firstCandidateObject);
        resetSkuSelections();
        setStage('recommend');
        return;
      }
      // 삭제·추가 이후 서버의 object_metadata 배열 순서와 인덱스를 맞춥니다.
      const finalObjects = detectedObjects.map((object, objectIndex) => ({
        ...object,
        objectIndex,
      }));
      await updateSceneObjects(analysisId, finalObjects);
      const candidatesByObjectIndex =
        await fetchObjectRecommendations(analysisId);
      const objectsWithCandidates = finalObjects.map((object) => ({
        ...object,
        candidates: candidatesByObjectIndex.get(object.objectIndex) ?? [],
      }));
      if (
        objectsWithCandidates.every((object) => object.candidates.length === 0)
      ) {
        throw new Error('추천된 SKU가 없습니다.');
      }
      const firstCandidateObject = objectsWithCandidates.find(
        (object) => object.candidates.length > 0,
      );
      setDetectedObjects(objectsWithCandidates);
      setSelectedObject(firstCandidateObject);
      resetSkuSelections();
      setStage('recommend');
    } catch (error) {
      setWorkflowError(
        error instanceof Error
          ? error.message
          : '유사 SKU 추천을 불러오지 못했습니다.',
      );
      setStage('failed');
    } finally {
      setIsRecommendationLoading(false);
    }
  }, [
    analysisId,
    analysisMode,
    detectedObjects,
    isEditing,
    resetSkuSelections,
    setDetectedObjects,
    setSelectedObject,
  ]);

  const startEditing = useCallback(() => {
    setWorkflowError(undefined);
    startObjectEditing();
  }, [startObjectEditing]);

  const deleteObject = useCallback(
    (objectId: string) => {
      if (deleteDetectedObject(objectId)) removeSkuSelection(objectId);
    },
    [deleteDetectedObject, removeSkuSelection],
  );

  const searchCatalog = useCallback(
    async (query: string): Promise<SkuCandidate[]> => {
      setWorkflowError(undefined);
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

  const saveTagging = useCallback(async (): Promise<void> => {
    if (!analysisId || confirmedSelections.length === 0) return;
    const recommendationObjects = detectedObjects.filter(
      (object) => object.candidates.length > 0,
    );
    if (confirmedSelections.length < recommendationObjects.length) {
      setWorkflowError('모든 탐지 객체의 SKU를 확정한 뒤 검수해 주세요.');
      setStage('recommend');
      return;
    }
    setStage('saving');
    setWorkflowError(undefined);
    try {
      if (analysisMode === 'mock') {
        setStage('saved');
        return;
      }
      await saveTaggingReview({
        matching: confirmedSelections.map(({ object, sku }) => ({
          objectIndex: object.objectIndex,
          selectedSku: sku,
        })),
        sceneImageId: analysisId,
      });
      setStage('saved');
    } catch (error) {
      setWorkflowError(
        error instanceof Error
          ? error.message
          : '태깅 결과를 저장하지 못했습니다.',
      );
      setStage('failed');
    }
  }, [analysisId, analysisMode, confirmedSelections, detectedObjects]);

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
    resetObjectEditor();
    resetSkuSelections();
    setCatalogResults([]);
  }, [resetObjectEditor, resetSkuSelections]);

  const value = useMemo<TaggingWorkflowContextValue>(
    () => ({
      analysisMode,
      analysisScenario,
      addObject,
      beginAnalysis,
      catalogResults,
      changeStage: setStage,
      clearSelectedSku,
      confirmedSelections,
      clearUploadError: () => setUploadError(undefined),
      detectedObjects,
      deleteObject,
      finishEditing,
      focusObjectForEditing,
      isRecommendationLoading,
      isEditing,
      loadDemoWorkflow,
      loadSelectedObjectRecommendations,
      redetect,
      resetWorkflow,
      saveTagging,
      searchCatalog,
      selectObject: selectObjectForSku,
      selectedObject,
      selectedObjectIds,
      selectedSku,
      selectSku,
      setAnalysisScenario,
      stage,
      startEditing,
      toggleObjectSelection,
      updateObjectBboxes,
      updateObjectCategory,
      uploadError,
      uploadedImage,
      uploadImage,
      workflowError,
    }),
    [
      analysisMode,
      analysisScenario,
      addObject,
      beginAnalysis,
      catalogResults,
      clearSelectedSku,
      confirmedSelections,
      detectedObjects,
      deleteObject,
      finishEditing,
      focusObjectForEditing,
      isRecommendationLoading,
      isEditing,
      loadDemoWorkflow,
      loadSelectedObjectRecommendations,
      redetect,
      resetWorkflow,
      saveTagging,
      searchCatalog,
      selectedObject,
      selectedObjectIds,
      selectedSku,
      selectObjectForSku,
      selectSku,
      stage,
      startEditing,
      toggleObjectSelection,
      updateObjectBboxes,
      updateObjectCategory,
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
