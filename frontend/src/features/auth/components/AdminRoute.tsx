import { Navigate, Outlet } from 'react-router-dom';

import { useAuth } from '@/features/auth/hooks/useAuth';

/** USER 역할의 직접 URL 접근을 일반 작업 화면으로 돌려보냅니다. */
export const AdminRoute = () => {
  const { user } = useAuth();

  if (user?.role === 'USER') {
    return <Navigate replace to="/" />;
  }

  return <Outlet />;
};
