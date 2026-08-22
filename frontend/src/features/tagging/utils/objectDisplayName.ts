import type { FurnitureObject } from '@/features/tagging/types';

export const getObjectCategoryName = (object: FurnitureObject): string =>
  object.category?.trim() || object.name.trim() || '가구';

/** 동일 카테고리 객체만 objectIdx 순서로 화면용 번호를 부여합니다. */
export const buildObjectDisplayNames = (
  objects: FurnitureObject[],
): Map<string, string> => {
  const orderedObjects = [...objects].sort(
    (left, right) => left.objectIdx - right.objectIdx,
  );
  const categoryCounts = new Map<string, number>();
  const categoryIndexes = new Map<string, number>();

  orderedObjects.forEach((object) => {
    const category = getObjectCategoryName(object);
    categoryCounts.set(category, (categoryCounts.get(category) ?? 0) + 1);
  });

  return new Map(
    orderedObjects.map((object) => {
      const category = getObjectCategoryName(object);
      const categoryIndex = (categoryIndexes.get(category) ?? 0) + 1;
      categoryIndexes.set(category, categoryIndex);

      const displayName =
        categoryCounts.get(category) === 1
          ? category
          : `${category} ${categoryIndex}`;

      return [object.id, displayName];
    }),
  );
};
