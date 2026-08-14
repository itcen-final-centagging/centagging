import type { TaggingHistory } from '../types';

type SaveTaggingWorkflowOptions = {
  onSaved: () => void;
  refreshHistory: () => Promise<TaggingHistory[]>;
  save: () => Promise<void>;
};

type SaveTaggingWorkflowResult = {
  history?: TaggingHistory[];
  historyError?: string;
};

export const saveTaggingAndRefreshHistory = async ({
  onSaved,
  refreshHistory,
  save,
}: SaveTaggingWorkflowOptions): Promise<SaveTaggingWorkflowResult> => {
  await save();
  onSaved();

  try {
    return { history: await refreshHistory() };
  } catch (error) {
    return {
      historyError:
        error instanceof Error
          ? error.message
          : '최신 이력을 불러오지 못했습니다.',
    };
  }
};
