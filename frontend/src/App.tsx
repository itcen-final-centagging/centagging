import type React from 'react';

import { AuthProvider } from '@/features/auth/components/AuthProvider';
import { TaggingWorkflowProvider } from '@/features/tagging/hooks/useTaggingWorkflow';
import { AppRouter } from '@/router';

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <TaggingWorkflowProvider>
        <AppRouter />
      </TaggingWorkflowProvider>
    </AuthProvider>
  );
};
