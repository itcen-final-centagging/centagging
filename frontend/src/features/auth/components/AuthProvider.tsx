import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
} from 'react';

import {
  getCurrentUser,
  login as requestLogin,
  type AuthenticatedUser,
  type LoginCredentials,
} from '../api/auth';
import {
  AuthContext,
  type AuthenticationError,
  type AuthenticationStatus,
} from '../authContext';
import {
  clearStoredSession,
  getStoredSession,
  storeSession,
} from '../authSession';

const getInitialStatus = (): AuthenticationStatus =>
  getStoredSession() ? 'checking' : 'unauthenticated';

export const AuthProvider = ({ children }: PropsWithChildren) => {
  const [status, setStatus] = useState<AuthenticationStatus>(getInitialStatus);
  const [authError, setAuthError] = useState<AuthenticationError>();
  const [user, setUser] = useState<AuthenticatedUser>();

  useEffect(() => {
    let isMounted = true;
    const session = getStoredSession();
    if (!session) return undefined;

    void getCurrentUser(session)
      .then((nextUser) => {
        if (!isMounted) return;
        setUser(nextUser);
        setStatus('authenticated');
      })
      .catch(() => {
        clearStoredSession();
        if (!isMounted) return;
        setAuthError('expired_session');
        setUser(undefined);
        setStatus('unauthenticated');
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const login = useCallback(
    async (credentials: LoginCredentials): Promise<AuthenticatedUser> => {
      setAuthError(undefined);
      const nextUser = await requestLogin(credentials);
      storeSession(nextUser.session);
      setUser(nextUser);
      setStatus('authenticated');
      return nextUser;
    },
    [],
  );

  const logout = useCallback((): void => {
    clearStoredSession();
    setAuthError(undefined);
    setUser(undefined);
    setStatus('unauthenticated');
  }, []);

  const value = useMemo(
    () => ({ authError, login, logout, status, user }),
    [authError, login, logout, status, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
