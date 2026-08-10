import type React from 'react';

import { TaggingWorkflowProvider } from '@/features/tagging/hooks/useTaggingWorkflow';
import { AppRouter } from '@/router';

export const App: React.FC = () => {
  return (
    <TaggingWorkflowProvider>
      <AppRouter />
    </TaggingWorkflowProvider>
  );
};
