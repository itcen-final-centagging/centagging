import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { useAuth } from '@/features/auth/hooks/useAuth';

export const ProtectedRoute = () => {
  const location = useLocation();
  const { status } = useAuth();

  if (status === 'checking') {
    return (
      <main className="studio-content-gradient flex min-h-screen items-center justify-center p-5">
        <p className="text-sm font-medium text-text-secondary">
          세션을 확인하고 있습니다.
        </p>
      </main>
    );
  }

  if (status === 'unauthenticated') {
    return <Navigate replace state={{ from: location }} to="/login" />;
  }

  return <Outlet />;
};
