import { useCallback, useMemo, useState } from 'react';

import type {
  ConfirmedSkuSelection,
  FurnitureObject,
  SkuCandidate,
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

  return {
    clearSelectedSku,
    confirmedSelections,
    removeSkuSelection,
    resetSkuSelections,
    selectObjectForSku,
    selectedSku,
    selectSku,
  };
};
