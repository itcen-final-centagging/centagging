import type React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { Layout } from '@/commons/components/Layout';
import { LoginPage } from '@/features/auth/components/LoginPage';
import { ProtectedRoute } from '@/features/auth/components/ProtectedRoute';
import { TaggingWorkflowProvider } from '@/features/tagging/hooks/useTaggingWorkflow';
import { HistoryPage } from '@/pages/HistoryPage';
import { TaggingPage } from '@/pages/TaggingPage';

export const AppRouter: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<ProtectedRoute />}>
          <Route
            element={
              <TaggingWorkflowProvider>
                <Layout />
              </TaggingWorkflowProvider>
            }
          >
            <Route path="/" element={<TaggingPage />} />
            <Route path="/history" element={<HistoryPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
};
