import { useCallback, useState } from 'react';

import type { FurnitureObject } from '../types';

const DEFAULT_FURNITURE_CATEGORY = '소파';

interface UseTaggingObjectEditorOptions {
  onMinimumObjectError: () => void;
}

export const useTaggingObjectEditor = ({
  onMinimumObjectError,
}: UseTaggingObjectEditorOptions) => {
  const [detectedObjects, setDetectedObjects] = useState<FurnitureObject[]>([]);
  const [selectedObject, setSelectedObject] = useState<FurnitureObject>();
  const [selectedObjectIds, setSelectedObjectIds] = useState<string[]>([]);
  const [isEditing, setIsEditing] = useState(false);

  const resetObjectEditor = useCallback((objects: FurnitureObject[] = []) => {
    setDetectedObjects(objects);
    setSelectedObject(undefined);
    setSelectedObjectIds([]);
    setIsEditing(false);
  }, []);

  const toggleObjectSelection = useCallback((object: FurnitureObject) => {
    setSelectedObject(object);
    setSelectedObjectIds((selectedIds) =>
      selectedIds.includes(object.id)
        ? selectedIds.filter((selectedId) => selectedId !== object.id)
        : [...selectedIds, object.id],
    );
  }, []);

  const startEditing = useCallback(() => {
    setSelectedObjectIds((selectedIds) => {
      if (selectedObject) return [selectedObject.id];
      if (selectedIds.length > 0) return [selectedIds[0]];
      return detectedObjects[0] ? [detectedObjects[0].id] : [];
    });
    setSelectedObject((currentObject) => currentObject ?? detectedObjects[0]);
    setIsEditing(true);
  }, [detectedObjects, selectedObject]);

  const finishEditing = useCallback(() => {
    setIsEditing(false);
  }, []);

  const focusObjectForEditing = useCallback((object: FurnitureObject) => {
    setSelectedObject(object);
    setSelectedObjectIds([object.id]);
  }, []);

  const updateObjectBboxes = useCallback(
    (updates: Array<Pick<FurnitureObject, 'bbox' | 'id'>>) => {
      const nextBboxes = new Map(
        updates.map((object) => [object.id, object.bbox]),
      );
      setDetectedObjects((objects) =>
        objects.map((object) => {
          const nextBbox = nextBboxes.get(object.id);
          if (!nextBbox) return object;

          return {
            ...object,
            attrsDirty: true,
            bbox: nextBbox,
            description: null,
            metadata: {
              ...object.metadata,
              attributes: {},
              description: null,
              subCategory: null,
              vlmMood: undefined,
            },
          };
        }),
      );
      setSelectedObject((object) =>
        object && nextBboxes.has(object.id)
          ? {
              ...object,
              attrsDirty: true,
              bbox: nextBboxes.get(object.id) ?? object.bbox,
              description: null,
              metadata: {
                ...object.metadata,
                attributes: {},
                description: null,
                subCategory: null,
                vlmMood: undefined,
              },
            }
          : object,
      );
    },
    [],
  );

  const updateObjectCategory = useCallback(
    (objectId: string, category: string) => {
      const nextCategory = category.trim() || DEFAULT_FURNITURE_CATEGORY;
      setDetectedObjects((objects) =>
        objects.map((object) =>
          object.id === objectId
            ? {
                ...object,
                attrsDirty: true,
                category: nextCategory,
                description: null,
                metadata: {
                  ...object.metadata,
                  attributes: {},
                  category: nextCategory,
                  description: null,
                  subCategory: null,
                  vlmMood: undefined,
                },
                name: nextCategory,
              }
            : object,
        ),
      );
      setSelectedObject((object) =>
        object?.id === objectId
          ? {
              ...object,
              attrsDirty: true,
              category: nextCategory,
              description: null,
              metadata: {
                ...object.metadata,
                attributes: {},
                category: nextCategory,
                description: null,
                subCategory: null,
                vlmMood: undefined,
              },
              name: nextCategory,
            }
          : object,
      );
    },
    [],
  );

  const deleteObject = useCallback(
    (objectId: string): boolean => {
      if (detectedObjects.length === 1) {
        onMinimumObjectError();
        return false;
      }
      setDetectedObjects((objects) =>
        objects.filter((object) => object.id !== objectId),
      );
      setSelectedObjectIds((selectedIds) =>
        selectedIds.filter((selectedId) => selectedId !== objectId),
      );
      setSelectedObject((object) =>
        object?.id === objectId ? undefined : object,
      );
      return true;
    },
    [detectedObjects.length, onMinimumObjectError],
  );

  const addObject = useCallback(() => {
    const id = `new-${crypto.randomUUID()}`;
    const category = DEFAULT_FURNITURE_CATEGORY;
    const object: FurnitureObject = {
      bbox: [350, 350, 650, 650],
      candidates: [],
      attrsDirty: true,
      category,
      confidence: null,
      description: '사용자가 추가한 객체',
      id,
      isNew: true,
      metadata: {
        attributes: {},
        category,
        description: '사용자가 추가한 객체',
        keyFeatures: [],
        subCategory: null,
      },
      name: category,
      objectIdx: detectedObjects.length,
    };
    setDetectedObjects((objects) => [...objects, object]);
    setSelectedObject(object);
    setSelectedObjectIds([id]);
  }, [detectedObjects.length]);

  return {
    addObject,
    deleteObject,
    detectedObjects,
    finishEditing,
    focusObjectForEditing,
    isEditing,
    resetObjectEditor,
    selectedObject,
    selectedObjectIds,
    setDetectedObjects,
    setSelectedObject,
    startEditing,
    toggleObjectSelection,
    updateObjectBboxes,
    updateObjectCategory,
  };
};
