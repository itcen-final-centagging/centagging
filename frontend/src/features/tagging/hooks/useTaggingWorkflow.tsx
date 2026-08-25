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
  fetchSearchCandidateMood,
  saveTaggingReview,
  searchCatalogItems,
  updateSceneObjects,
} from '../api/tagging';
import { validateImage } from '../utils/image';

import type {
  ConfirmedSkuSelection,
  FurnitureObject,
  SkuCandidate,
  TaggingValues,
  UploadedImage,
  VlmMood,
  WorkflowStage,
} from '../types';

type TaggingWorkflowContextValue = {
  addCatalogSkuToCandidates: (sku: SkuCandidate) => void;
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
  loadSelectedObjectRecommendations: () => Promise<void>;
  resetWorkflow: () => void;
  saveTagging: (
    valuesByObject?: Record<string, TaggingValues>,
  ) => Promise<void>;
  searchCatalog: (query: string) => Promise<SkuCandidate[]>;
  selectObject: (object: FurnitureObject) => void;
  selectedObject?: FurnitureObject;
  selectedObjectIds: string[];
  selectedSku?: SkuCandidate;
  selectSku: (sku: SkuCandidate) => void;
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
  const [catalogResults, setCatalogResults] = useState<SkuCandidate[]>([]);
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
    applySkuMood,
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
    async (): Promise<void> => {
      if (!uploadedImage) return;
      setUploadError(undefined);
      setWorkflowError(undefined);
      try {
        const analysis = await analyzeImage(uploadedImage.file);
        resetObjectEditor(analysis.objects);
        resetSkuSelections();
        if (analysis.objects.length === 0) {
          setAnalysisId(undefined);
          setCatalogResults([]);
          setUploadError(
            '탐지된 가구가 없습니다. 다른 이미지를 업로드해 주세요.',
          );
          setStage('upload');
          return;
        }
        setAnalysisId(analysis.analysisId);
        setStage('detect');
      } catch (error) {
        setWorkflowError(
          error instanceof Error
            ? error.message
            : 'AI 분석 요청을 처리하지 못했습니다.',
        );
        setStage('failed');
      }
    },
    [resetObjectEditor, resetSkuSelections, uploadedImage],
  );

  const beginAnalysis = useCallback(async (): Promise<void> => {
    if (!uploadedImage) return;
    setStage('analyzing');
    await runAnalysis();
  }, [runAnalysis, uploadedImage]);

  const loadSelectedObjectRecommendations = useCallback(async () => {
    if (!analysisId || detectedObjects.length === 0 || isEditing) return;
    setIsRecommendationLoading(true);
    setWorkflowError(undefined);
    setStage('recommending');
    try {
      // 편집된 객체를 임시 요청으로 전달하고 POST 응답의 추천 결과를 반영합니다.
      const finalObjects = detectedObjects.map((object) => ({ ...object }));
      const recommendationsByObjectIdx = await updateSceneObjects(
        analysisId,
        finalObjects,
      );

      const objectsWithCandidates = finalObjects.map((object) => {
        const recommendation = recommendationsByObjectIdx.get(object.objectIdx);

        return {
          ...object,
          attrsDirty: recommendation ? false : object.attrsDirty,
          category: recommendation?.category ?? object.category,
          metadata: {
            ...object.metadata,
            category: recommendation?.category ?? object.metadata.category,
            subCategory:
              recommendation?.sub_category ?? object.metadata.subCategory,
            attributes: recommendation?.attrs ?? object.metadata.attributes,
            vlmMood: recommendation?.vlm_mood ?? object.metadata.vlmMood,
          },
          candidates: recommendation?.sku_candidates ?? [],
          xaiAttrs: recommendation?.xai_attrs ?? object.xaiAttrs ?? {},
          xaiReadings:
            recommendation?.xaiReadings ?? object.xaiReadings ?? [],
        };
      });
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

  // 검색으로 고른 SKU의 후보 카드(detectedObjects/selectedObject)에
  // 뒤늦게 도착한 vlm_mood를 채워 넣습니다. confirmedSelections/검수 화면에
  // 쓰는 사본은 useSkuSelections의 applySkuMood가 별도로 갱신합니다.
  const applyCandidateMood = useCallback(
    (targetObjectId: string, skuCode: string, vlmMood: VlmMood): void => {
      const mergeMood = (object: FurnitureObject): FurnitureObject => {
        // 그 사이 사용자가 다른 SKU를 다시 선택했다면 이 응답은 버립니다.
        if (object.candidates[0]?.sku !== skuCode) return object;
        return {
          ...object,
          candidates: object.candidates.map((candidate, index) =>
            index === 0 ? { ...candidate, vlmMood } : candidate,
          ),
        };
      };
      setDetectedObjects((objects) =>
        objects.map((object) =>
          object.id === targetObjectId ? mergeMood(object) : object,
        ),
      );
      setSelectedObject((object) =>
        object && object.id === targetObjectId ? mergeMood(object) : object,
      );
    },
    [setDetectedObjects, setSelectedObject],
  );

  const addCatalogSkuToCandidates = useCallback(
    (sku: SkuCandidate): void => {
      if (!selectedObject) return;
      const targetObjectId = selectedObject.id;
      const targetObject = selectedObject;

      // 이미 후보 목록에 있는 SKU(AI 추천 후보 또는 이전에 검색으로 추가한
      // 후보 포함)를 다시 선택하면 알려주고 중복 추가하지 않습니다.
      const isDuplicate = selectedObject.candidates.some(
        (candidate) => candidate.sku === sku.sku,
      );
      if (isDuplicate) {
        alert('이미 후보 목록에 있는 SKU입니다.');
        return;
      }

      // 카탈로그 검색으로 선택한 SKU는 항상 후보 목록 최상단에 하나만
      // 유지합니다. 이전에 검색으로 추가한 선택(matchRank가 없는 후보)은
      // 새로 선택한 SKU로 교체하고, AI 추천 후보(matchRank가 있는 후보)는
      // 그대로 둡니다.
      const replaceSearchSelection = (
        object: FurnitureObject,
      ): FurnitureObject => ({
        ...object,
        candidates: [
          sku,
          ...object.candidates.filter(
            (candidate) => candidate.matchRank !== null,
          ),
        ],
      });

      setDetectedObjects((objects) =>
        objects.map((object) =>
          object.id === targetObjectId
            ? replaceSearchSelection(object)
            : object,
        ),
      );
      setSelectedObject((object) =>
        object && object.id === targetObjectId
          ? replaceSearchSelection(object)
          : object,
      );
      selectSku(sku);
      setStage('recommend');

      // 검색으로 고른 SKU도 AI 추천 후보와 마찬가지로 VLM이 공간 분위기·
      // 스타일 태그를 계산해줍니다.
      if (analysisId) {
        fetchSearchCandidateMood(
          analysisId,
          {
            bbox: targetObject.bbox,
            category: targetObject.category,
            name: targetObject.name,
            objectIdx: targetObject.objectIdx,
          },
          sku.sku,
        )
          .then((vlmMood) => {
            applyCandidateMood(targetObjectId, sku.sku, vlmMood);
            applySkuMood(targetObjectId, sku.sku, vlmMood);
          })
          .catch(() => {

          });
      }
    },
    [
      analysisId,
      applyCandidateMood,
      applySkuMood,
      selectSku,
      selectedObject,
      setDetectedObjects,
      setSelectedObject,
    ],
  );

  const saveTagging = useCallback(
    async (valuesByObject?: Record<string, TaggingValues>): Promise<void> => {
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
        await saveTaggingReview({
          matching: confirmedSelections.map(({ object, sku }) => ({
            object,
            objectIdx: object.objectIdx,
            selectedSku: sku,
            values: valuesByObject?.[object.id],
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
    },
    [analysisId, confirmedSelections, detectedObjects],
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
    resetObjectEditor();
    resetSkuSelections();
    setCatalogResults([]);
  }, [resetObjectEditor, resetSkuSelections]);

  const value = useMemo<TaggingWorkflowContextValue>(
    () => ({
      addCatalogSkuToCandidates,
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
      loadSelectedObjectRecommendations,
      resetWorkflow,
      saveTagging,
      searchCatalog,
      selectObject: selectObjectForSku,
      selectedObject,
      selectedObjectIds,
      selectedSku,
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
    }),
    [
      addCatalogSkuToCandidates,
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
      loadSelectedObjectRecommendations,
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
