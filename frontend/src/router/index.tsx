import type React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { AdminLayout } from '@/commons/components/AdminLayout';
import { Layout } from '@/commons/components/Layout';
import { AdminRoute } from '@/features/auth/components/AdminRoute';
import { LoginPage } from '@/features/auth/components/LoginPage';
import { ProtectedRoute } from '@/features/auth/components/ProtectedRoute';
import { TaggingHeader } from '@/features/tagging/components/TaggingHeader';
import { TaggingWorkflowProvider } from '@/features/tagging/hooks/useTaggingWorkflow';
import { AdminCatalogPage } from '@/pages/AdminCatalogPage';
import { ApprovalPage } from '@/pages/ApprovalPage';
import { HistoryPage } from '@/pages/HistoryPage';
import { ProductImageRegistrationPage } from '@/pages/ProductImageRegistrationPage';
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
                <Layout header={<TaggingHeader />} />
              </TaggingWorkflowProvider>
            }
          >
            <Route path="/" element={<TaggingPage />} />
            <Route path="/history" element={<HistoryPage />} />
          </Route>
          <Route element={<AdminRoute />}>
            <Route element={<AdminLayout />}>
              <Route path="/admin" element={<AdminCatalogPage />} />
              <Route
                path="/admin/product-images"
                element={<ProductImageRegistrationPage />}
              />
              <Route path="/admin/approvals" element={<ApprovalPage />} />
            </Route>
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
};
