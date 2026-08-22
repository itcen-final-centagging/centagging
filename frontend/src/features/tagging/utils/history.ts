import type { TaggingHistory } from '@/features/tagging/types';

export type TaggingHistorySceneGroup = {
  id: string;
  imageName: string;
  imageUrl: string | null;
  latestSavedAt: string;
  records: TaggingHistory[];
};

/** 같은 연출 이미지의 태깅 결과를 묶고, 객체는 탐지 순서로 정렬합니다. */
export const groupTaggingHistoryByScene = (
  history: TaggingHistory[],
): TaggingHistorySceneGroup[] => {
  const groups = new Map<string, TaggingHistorySceneGroup>();

  history.forEach((record) => {
    const existing = groups.get(record.sceneImage.id);
    if (existing) {
      existing.records.push(record);
      return;
    }
    groups.set(record.sceneImage.id, {
      id: record.sceneImage.id,
      imageName: record.imageName,
      imageUrl: record.sceneImage.imageUrl,
      latestSavedAt: record.savedAt,
      records: [record],
    });
  });

  return [...groups.values()].map((group) => ({
    ...group,
    records: [...group.records].sort(
      (left, right) => left.objectIdx - right.objectIdx,
    ),
  }));
};
