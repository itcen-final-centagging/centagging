export const AUTH_SESSION_STORAGE_KEY = 'centagging.auth.session';

const getStorage = (): Storage | undefined =>
  typeof localStorage === 'undefined' ? undefined : localStorage;

export const getStoredSession = (): string | undefined => {
  const session = getStorage()?.getItem(AUTH_SESSION_STORAGE_KEY);
  return session || undefined;
};

export const storeSession = (session: string): void => {
  getStorage()?.setItem(AUTH_SESSION_STORAGE_KEY, session);
};

export const clearStoredSession = (): void => {
  getStorage()?.removeItem(AUTH_SESSION_STORAGE_KEY);
};
