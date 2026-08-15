import type React from 'react';

import { AuthProvider } from '@/features/auth/components/AuthProvider';
import { AppRouter } from '@/router';

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <AppRouter />
    </AuthProvider>
  );
};
