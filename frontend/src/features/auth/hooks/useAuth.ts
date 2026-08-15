import { useContext } from 'react';

import { AuthContext, type AuthContextValue } from '../authContext';

export const useAuth = (): AuthContextValue => {
  const value = useContext(AuthContext);
  if (value === null) {
    throw new Error('useAuth는 AuthProvider 내부에서 사용해야 합니다.');
  }
  return value;
};
