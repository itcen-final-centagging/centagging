import { createContext } from 'react';

import type { AuthenticatedUser, LoginCredentials } from './api/auth';

export type AuthenticationStatus =
  'authenticated' | 'checking' | 'unauthenticated';

export type AuthContextValue = {
  login: (credentials: LoginCredentials) => Promise<AuthenticatedUser>;
  logout: () => void;
  status: AuthenticationStatus;
  user?: AuthenticatedUser;
};

export const AuthContext = createContext<AuthContextValue | null>(null);
