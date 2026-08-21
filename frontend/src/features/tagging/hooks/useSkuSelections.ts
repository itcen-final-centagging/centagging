import { useCallback, useMemo, useState } from 'react';

import type {
  ConfirmedSkuSelection,
  FurnitureObject,
  SkuCandidate,
  VlmMood,
} from '../types';

interface UseSkuSelectionsOptions {
  detectedObjects: FurnitureObject[];
  selectedObject?: FurnitureObject;
  setSelectedObject: (object?: FurnitureObject) => void;
}

export const useSkuSelections = ({
  detectedObjects,
  selectedObject,
  setSelectedObject,
}: UseSkuSelectionsOptions) => {
  const [selectedSku, setSelectedSku] = useState<SkuCandidate>();
  const [selectedSkusByObject, setSelectedSkusByObject] = useState<
    Record<string, SkuCandidate>
  >({});
  const confirmedSelections = useMemo<ConfirmedSkuSelection[]>(
    () =>
      detectedObjects.flatMap((object) => {
        const sku = selectedSkusByObject[object.id];
        return sku ? [{ object, sku }] : [];
      }),
    [detectedObjects, selectedSkusByObject],
  );

  const resetSkuSelections = useCallback(() => {
    setSelectedSku(undefined);
    setSelectedSkusByObject({});
  }, []);

  const selectObjectForSku = useCallback(
    (object: FurnitureObject) => {
      setSelectedObject(object);
      setSelectedSku(selectedSkusByObject[object.id]);
    },
    [selectedSkusByObject, setSelectedObject],
  );

  const selectSku = useCallback(
    (sku: SkuCandidate) => {
      setSelectedSku(sku);
      if (!selectedObject) return;
      setSelectedSkusByObject((selections) => ({
        ...selections,
        [selectedObject.id]: sku,
      }));
    },
    [selectedObject],
  );

  const clearSelectedSku = useCallback(() => {
    setSelectedSku(undefined);
    if (!selectedObject) return;
    setSelectedSkusByObject((selections) => {
      const remainingSelections = { ...selections };
      delete remainingSelections[selectedObject.id];
      return remainingSelections;
    });
  }, [selectedObject]);

  const removeSkuSelection = useCallback((objectId: string) => {
    setSelectedSkusByObject((selections) => {
      const remainingSelections = { ...selections };
      delete remainingSelections[objectId];
      return remainingSelections;
    });
  }, []);


  const applySkuMood = useCallback(
    (objectId: string, skuCode: string, vlmMood: VlmMood) => {
      setSelectedSkusByObject((selections) => {
        const current = selections[objectId];
        if (!current || current.sku !== skuCode) return selections;
        return { ...selections, [objectId]: { ...current, vlmMood } };
      });
      // 지금 화면에 보여주는 selectedSku도 같은 객체·같은 SKU일 때만 갱신합니다.
      if (selectedObject?.id !== objectId) return;
      setSelectedSku((current) =>
        current && current.sku === skuCode ? { ...current, vlmMood } : current,
      );
    },
    [selectedObject],
  );

  return {
    applySkuMood,
    clearSelectedSku,
    confirmedSelections,
    removeSkuSelection,
    resetSkuSelections,
    selectObjectForSku,
    selectedSku,
    selectSku,
  };
};
