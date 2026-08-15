import { createContext } from 'react';

import type { AuthenticatedUser, LoginCredentials } from './api/auth';

export type AuthenticationStatus =
  'authenticated' | 'checking' | 'unauthenticated';

export type AuthenticationError = 'expired_session';

export type AuthContextValue = {
  authError?: AuthenticationError;
  login: (credentials: LoginCredentials) => Promise<AuthenticatedUser>;
  logout: () => void;
  status: AuthenticationStatus;
  user?: AuthenticatedUser;
};

export const AuthContext = createContext<AuthContextValue | null>(null);
